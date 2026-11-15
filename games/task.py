"""Delayed Matching to Sample (MTS / M2S) - the WinSCAT subtest, pure logic.

No Qt, no pygame in here: the state machine advances through ``tick(now_ms)``,
so the whole test can be unit-tested headless and driven by any clock
(``pygame.time.get_ticks()`` in the app, ``time.monotonic()`` in tests).

Task, as specified by NASA's WinSCAT (Johnson Space Center, from ANAM):

1. SAMPLE    a 4x4 red/white grid is shown
2. DELAY     blank retention interval (5 s)
3. TEST      two 4x4 grids appear; one equals the sample, the other is altered
4. answer     left or right, as fast and accurately as possible
5. FEEDBACK   correct / incorrect / no response, then the next trial

Recorded metrics: accuracy, median reaction time of correct responses, and
throughput (correct responses per minute) as the composite score.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass
from enum import Enum

GRID_SIZE = 4                      # 4 x 4 = 16 cells
CELLS = GRID_SIZE * GRID_SIZE
TRIALS = 20                        # scored trials
PRACTICE_TRIALS = 3                # excluded from metrics, kills the learning curve
SAMPLE_MS = 1000                   # sample presentation
DELAY_MS = 5000                    # retention interval
RESPONSE_WINDOW_MS = 4000          # time allowed to answer
FEEDBACK_MS = 1000                 # inter-trial feedback
FLIP_CELLS = 3                     # how many cells the distractor changes


class Phase(str, Enum):
    IDLE = "idle"
    SAMPLE = "sample"
    DELAY = "delay"
    TEST = "test"
    FEEDBACK = "feedback"
    DONE = "done"


class Side(str, Enum):
    LEFT = "left"
    RIGHT = "right"


def _make_pattern(rng: random.Random) -> tuple[bool, ...]:
    """A 16-cell grid; True = red, False = white, kept visually balanced."""
    while True:
        cells = tuple(rng.random() < 0.5 for _ in range(CELLS))
        if 4 <= sum(cells) <= CELLS - 4:
            return cells


def _make_distractor(pattern: tuple[bool, ...], rng: random.Random) -> tuple[bool, ...]:
    cells = list(pattern)
    for index in rng.sample(range(CELLS), FLIP_CELLS):
        cells[index] = not cells[index]
    return tuple(cells)


@dataclass(frozen=True)
class Trial:
    """One MTS trial: the sample plus the two comparison grids."""

    sample: tuple[bool, ...]
    left: tuple[bool, ...]
    right: tuple[bool, ...]

    @property
    def match(self) -> Side:
        return Side.LEFT if self.left == self.sample else Side.RIGHT


@dataclass(frozen=True)
class Response:
    trial_number: int              # 1-based, across practice + scored
    practice: bool
    correct: bool
    reaction_ms: int | None        # None when there was no response
    responded: bool


@dataclass(frozen=True)
class Metrics:
    trials: int
    correct: int
    accuracy: float                # 0..1
    median_rt_ms: float | None     # over correct responses only
    throughput: float              # correct responses per minute
    elapsed_ms: int
    responses: tuple[Response, ...]


class DelayedMTS:
    """The MTS state machine for one session."""

    def __init__(
        self,
        seed: int | None = None,
        trials: int = TRIALS,
        practice: int = PRACTICE_TRIALS,
    ) -> None:
        self._rng = random.Random(seed)
        self._scored_total = trials
        self._practice_total = practice
        self._total = trials + practice

        self.phase: Phase = Phase.IDLE
        self.responses: list[Response] = []
        self.started_ms: int | None = None
        self.finished_ms: int | None = None

        self._trial_index = 0                    # 0-based, current trial
        self._deadline_ms = 0
        self._phase_ms = 0
        self._trial: Trial | None = None
        self._test_started_ms = 0
        self._last: Response | None = None

    # ------------------------------------------------------------------ flow
    def start(self, now_ms: int) -> None:
        self.phase = Phase.SAMPLE
        self._trial_index = 0
        self.started_ms = now_ms
        self.finished_ms = None
        self.responses = []
        self._begin_phase(now_ms)

    def reset(self) -> None:
        """Abandon the session; the next start() begins from a clean slate."""
        self.phase = Phase.IDLE
        self._trial = None
        self._last = None
        self._trial_index = 0
        self._deadline_ms = 0
        self._phase_ms = 0
        self.started_ms = None
        self.finished_ms = None
        self.responses = []

    @property
    def is_running(self) -> bool:
        return self.phase not in (Phase.IDLE, Phase.DONE)

    @property
    def trial_number(self) -> int:
        """1-based trial number for display."""
        return min(self._trial_index + 1, self._total)

    @property
    def is_practice(self) -> bool:
        return self._trial_index < self._practice_total

    @property
    def trial(self) -> Trial | None:
        return self._trial

    @property
    def last_response(self) -> Response | None:
        return self._last

    def remaining_ms(self, now_ms: int) -> int:
        """Milliseconds left in the current phase, for the on-screen countdown."""
        return max(0, self._deadline_ms - now_ms)

    @property
    def phase_duration_ms(self) -> int:
        """Length of the phase we are currently in, so a fraction can be drawn."""
        return self._phase_ms

    @property
    def total_trials(self) -> int:
        """Practice + scored trials, for the on-screen counter."""
        return self._total

    @property
    def practice_total(self) -> int:
        return self._practice_total

    @property
    def scored_total(self) -> int:
        return self._scored_total

    def tick(self, now_ms: int) -> None:
        """Advance timed transitions. Call every frame."""
        if not self.is_running or now_ms < self._deadline_ms:
            return

        if self.phase is Phase.SAMPLE:
            self._enter(Phase.DELAY, now_ms, DELAY_MS)
        elif self.phase is Phase.DELAY:
            self._enter(Phase.TEST, now_ms, RESPONSE_WINDOW_MS)
            self._test_started_ms = now_ms
        elif self.phase is Phase.TEST:
            self._record(now_ms, correct=False, reaction_ms=None, responded=False)
        elif self.phase is Phase.FEEDBACK:
            self._advance(now_ms)

    def answer(self, side: Side, now_ms: int) -> bool:
        """Register a left/right choice. Returns False if ignored."""
        if self.phase is not Phase.TEST:
            return False
        assert self._trial is not None
        correct = side is self._trial.match
        self._record(now_ms, correct=correct, reaction_ms=now_ms - self._test_started_ms,
                     responded=True)
        return True

    # ------------------------------------------------------------- internals
    def _begin_phase(self, now_ms: int) -> None:
        self._trial = self._make_trial()
        self._enter(Phase.SAMPLE, now_ms, SAMPLE_MS)

    def _enter(self, phase: Phase, now_ms: int, duration_ms: int) -> None:
        self.phase = phase
        self._phase_ms = duration_ms
        self._deadline_ms = now_ms + duration_ms

    def _record(self, now_ms: int, *, correct: bool, reaction_ms: int | None,
                responded: bool) -> None:
        self._last = Response(
            trial_number=self._trial_index + 1,
            practice=self.is_practice,
            correct=correct,
            reaction_ms=reaction_ms,
            responded=responded,
        )
        self.responses.append(self._last)
        self._enter(Phase.FEEDBACK, now_ms, FEEDBACK_MS)

    def _advance(self, now_ms: int) -> None:
        self._trial_index += 1
        if self._trial_index >= self._total:
            self.phase = Phase.DONE
            self.finished_ms = now_ms
            self._trial = None
        else:
            self._begin_phase(now_ms)

    def _make_trial(self) -> Trial:
        sample = _make_pattern(self._rng)
        distractor = _make_distractor(sample, self._rng)
        if self._rng.random() < 0.5:
            return Trial(sample=sample, left=sample, right=distractor)
        return Trial(sample=sample, left=distractor, right=sample)

    # --------------------------------------------------------------- metrics
    def metrics(self) -> Metrics:
        scored = [r for r in self.responses if not r.practice]
        correct = [r for r in scored if r.correct]
        elapsed = (self.finished_ms or 0) - (self.started_ms or 0)

        rt_values = [r.reaction_ms for r in correct if r.reaction_ms is not None]
        median_rt = statistics.median(rt_values) if rt_values else None
        minutes = elapsed / 60000
        throughput = len(correct) / minutes if minutes > 0 else 0.0

        return Metrics(
            trials=len(scored),
            correct=len(correct),
            accuracy=len(correct) / len(scored) if scored else 0.0,
            median_rt_ms=median_rt,
            throughput=throughput,
            elapsed_ms=elapsed,
            responses=tuple(scored),
        )
