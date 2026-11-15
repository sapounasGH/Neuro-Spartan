"""pygame renderer for the WinSCAT delayed-MTS task, embedded in a Qt widget.

pygame does all drawing and owns the task clock. The widget hands its native
window handle to SDL through ``SDL_WINDOWID`` so pygame paints inside the
Neurogames panel instead of opening a separate window.

Clicks are taken from both SDL's event queue and Qt's own mouse events,
because with an embedded window either side may receive them. That is safe:
``DelayedMTS.answer()`` only reacts while the phase is TEST and moves to
FEEDBACK on the first accepted answer, so a duplicate is ignored by design.
"""

from __future__ import annotations

import os
import time

# Silence pygame's "Hello from the pygame community" banner: this is a desktop
# app, not a console game, and the line would show up on every launch.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QWidget

from .task import PRACTICE_TRIALS, TRIALS, DelayedMTS, Phase, Side

VIEW_SIZE = (720, 470)
CELL = 46
GRID_PX = CELL * 4                     # GRID_SIZE is 4
PANEL_GAP = 56
HEADER_H = 52
FOOTER_H = 44

BG = (244, 247, 250)
PANEL_BG = (255, 255, 255)
BORDER = (200, 211, 224)
INK = (21, 26, 33)
MUTED = (107, 119, 135)
BLUE = (47, 111, 219)
SKY = (127, 192, 245)
RED = (221, 59, 40)
GREEN = (29, 157, 111)
AMBER = (201, 130, 27)

PHASE_TITLE = {
    Phase.IDLE: "Ready",
    Phase.SAMPLE: "Remember this pattern",
    Phase.DELAY: "Hold it in memory",
    Phase.TEST: "Which grid matches the sample?",
    Phase.FEEDBACK: "Result",
    Phase.DONE: "Session complete",
}

PHASE_HINT = {
    Phase.IDLE: "press Start session to begin",
    Phase.SAMPLE: "memorise the red / white pattern",
    Phase.DELAY: "keep it in mind - the choices are coming",
    Phase.TEST: "click the matching grid (right-click also means the right one)",
    Phase.FEEDBACK: " ",
    Phase.DONE: "",
}


class WinSCATView(QWidget):
    """One MTS session, drawn with pygame inside a Qt widget."""

    session_finished = Signal(object)  # Metrics
    render_failed = Signal(str)        # error text, if the draw loop dies

    def __init__(self, parent: QWidget | None = None, seed: int | None = None,
                 trials: int | None = None, practice: int | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(*VIEW_SIZE)
        # SDL needs a real window handle to paint into.
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, True)

        # trial counts the tab can shorten for a demo; None = WinSCAT defaults
        self.trials = TRIALS if trials is None else trials
        self.practice = PRACTICE_TRIALS if practice is None else practice
        self.game = DelayedMTS(seed=seed, trials=self.trials, practice=self.practice)
        self._screen: pygame.Surface | None = None
        self._error: str | None = None
        self._render_error: str | None = None
        self._detached = False
        self._fonts: dict[int, pygame.font.Font] = {}
        self._hover: Side | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(16)                     # ~60 fps
        self._timer.timeout.connect(self._frame)

    # ------------------------------------------------------------- lifecycle
    def _ensure_display(self) -> bool:
        """Get a pygame surface: embedded in this widget, else own window."""
        if self._screen is not None:
            return True
        if self._embed_in_widget():
            return True
        return self._open_own_window()

    def _embed_in_widget(self) -> bool:
        """Paint inside the Qt panel through SDL_WINDOWID. Preferred."""
        try:
            handle = int(self.winId())
            if handle <= 1:
                # Not a real window handle (e.g. Qt's offscreen platform).
                raise pygame.error("this widget has no native window handle")

            os.environ["SDL_WINDOWID"] = str(handle)
            os.environ["SDL_VIDEO_CENTERED"] = "0"
            pygame.display.init()
            pygame.font.init()
            self._screen = pygame.display.set_mode(VIEW_SIZE)
            self._detached = False
            self._error = None
            return True
        except pygame.error as exc:
            self._error = f"embedding failed ({exc}); falling back to a game window"
            os.environ.pop("SDL_WINDOWID", None)
            return False

    def _open_own_window(self) -> bool:
        """Fallback: a normal pygame window, still driven from Qt's timer."""
        try:
            os.environ.pop("SDL_WINDOWID", None)
            pygame.display.init()
            pygame.font.init()
            self._screen = pygame.display.set_mode(VIEW_SIZE)
            pygame.display.set_caption("NeuroSpartan - WinSCAT delayed MTS")
            self._detached = True
            return True
        except pygame.error as exc:
            self._screen = None
            self._error = f"pygame could not start: {exc}"
            return False

    @property
    def detached(self) -> bool:
        """True when the game runs in its own window rather than the panel."""
        return self._detached

    def prepare(self) -> None:
        """Called when the tab becomes visible: create the surface, draw idle."""
        if not self._ensure_display():
            return
        self._frame()

    @property
    def error(self) -> str | None:
        return self._error

    def start_session(self, seed: int | None = None) -> bool:
        """Reset the model and drive it from the timer. False if pygame failed."""
        if not self._ensure_display():
            return False
        if seed is not None:
            self.game = DelayedMTS(seed=seed, trials=self.trials, practice=self.practice)
        self._hover = None
        self._timer.stop()
        self.game.start(self._clock_ms())
        self._timer.start()
        self._frame()
        return True

    def cancel(self) -> None:
        """Abort a running session - used when the tab is hidden mid-trial,
        because a paused task would leave phase deadlines in the past."""
        self._timer.stop()
        self.game.reset()

    def stop(self) -> None:
        self._timer.stop()

    def shutdown(self) -> None:
        self._timer.stop()
        if self._screen is not None:
            self._screen = None
            pygame.display.quit()

    def is_ready(self) -> bool:
        return self._screen is not None

    # ----------------------------------------------------------------- input
    def _clock_ms(self) -> int:
        """Monotonic millisecond clock.

        Deliberately NOT pygame.time.get_ticks(): that counter comes from SDL's
        video/timer subsystem and can sit still (it was frozen at 0 in our
        headless runs). A stuck counter means phase deadlines never expire, so
        the session paints trial 1 forever. time.monotonic() always advances,
        and its sub-millisecond resolution makes reaction times more accurate.
        """
        return time.monotonic_ns() // 1_000_000

    @staticmethod
    def _side_for_x(x: float) -> Side:
        return Side.LEFT if x < VIEW_SIZE[0] / 2 else Side.RIGHT

    def _choose(self, side: Side) -> None:
        if self.game.answer(side, self._clock_ms()):
            self._frame()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self.game.phase is Phase.TEST:
            if event.button() == Qt.RightButton:
                self._choose(Side.RIGHT)
            else:
                self._choose(self._side_for_x(event.position().x()))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self.game.phase is Phase.TEST:
            self._hover = self._side_for_x(event.position().x())
        # Repaint on movement whenever a session is live. If the QTimer ever
        # stopped firing, moving the mouse still drives the task forward, so the
        # session cannot silently freeze on one frame.
        if self.game.is_running:
            self._frame()
        super().mouseMoveEvent(event)

    # ------------------------------------------------------------ main loop
    def _frame(self) -> None:
        if self._screen is None:
            return

        # A raise here would otherwise leave the panel showing the last good
        # frame forever - which looks exactly like a stuck clock. Surface it.
        try:
            self._step_and_draw()
        except Exception as exc:  # noqa: BLE001 - keep the app alive, report clearly
            self._timer.stop()
            self._render_error = f"{type(exc).__name__}: {exc}"
            self.render_failed.emit(self._render_error)

    def _step_and_draw(self) -> None:
        now = self._clock_ms()
        self._pump_sdl_events()

        if self.game.is_running:
            leaving = self.game.phase
            self.game.tick(now)
            if leaving is Phase.FEEDBACK and self.game.phase is Phase.DONE:
                self._timer.stop()
                self.session_finished.emit(self.game.metrics())

        self._draw(now)

    def _pump_sdl_events(self) -> None:
        """Drain SDL so the embedded window stays responsive."""
        for event in pygame.event.get():
            if event.type == pygame.MOUSEBUTTONDOWN and self.game.phase is Phase.TEST:
                if event.button == 3:
                    self._choose(Side.RIGHT)
                elif event.button in (1, 2):
                    self._choose(self._side_for_x(event.pos[0]))
            elif event.type == pygame.MOUSEMOTION and self.game.phase is Phase.TEST:
                self._hover = self._side_for_x(event.pos[0])

    # ------------------------------------------------------------ rendering
    def _font(self, size: int) -> pygame.font.Font:
        font = self._fonts.get(size)
        if font is None:
            font = pygame.font.SysFont("segoeui,arial", size)
            self._fonts[size] = font
        return font

    def _text(self, screen, text: str, size: int, colour, pos, align: str = "tl") -> pygame.Rect:
        image = self._font(size).render(text, True, colour)
        rect = image.get_rect()
        if align == "c":
            rect.center = pos
        elif align == "r":
            rect.topright = pos
        else:
            rect.topleft = pos
        screen.blit(image, rect)
        return rect

    def _draw(self, now: int) -> None:
        assert self._screen is not None
        screen = self._screen
        width, height = VIEW_SIZE
        phase = self.game.phase

        screen.fill(BG)

        # header: phase name + remaining time + trial counter
        pygame.draw.rect(screen, BORDER, (0, 0, width, HEADER_H))
        self._text(screen, PHASE_TITLE[phase], 19, INK, (16, 16))

        # A visible countdown on every timed phase: if this number stops moving
        # the loop is dead, which is far better than silently painting frame 1.
        if self.game.is_running and self.game.phase_duration_ms:
            secs = self.game.remaining_ms(now) / 1000
            self._text(screen, f"{secs:4.1f} s", 19, MUTED, (250, 16))

        counter = f"trial {self.game.trial_number} / {self.game.total_trials}"
        if self.game.is_practice and phase is not Phase.DONE:
            counter += "  (practice)"
        self._text(screen, counter, 14, MUTED, (width - 16, 19), align="r")

        # phase countdown bar
        if self.game.is_running and self.game.phase_duration_ms:
            left = self.game.remaining_ms(now)
            fraction = 1.0 - left / self.game.phase_duration_ms
            fraction = max(0.0, min(1.0, fraction))
            bar_w = width - 32
            pygame.draw.rect(screen, BORDER, (16, HEADER_H - 6, bar_w, 4), border_radius=2)
            if fraction > 0:
                colour = AMBER if phase is Phase.TEST else SKY
                pygame.draw.rect(screen, colour, (16, HEADER_H - 6, max(4, int(bar_w * fraction)), 4),
                                 border_radius=2)

        top = HEADER_H + 20
        bottom = height - FOOTER_H - 10
        cy = (top + bottom) // 2
        trial = self.game.trial

        if phase is Phase.SAMPLE and trial:
            self._grid(screen, trial.sample, width // 2 - GRID_PX // 2, cy - GRID_PX // 2,
                       ring=SKY)
        elif phase is Phase.DELAY:
            self._blank(screen, width // 2 - GRID_PX // 2, cy - GRID_PX // 2)
            self._text(screen, f"{int(self.game.remaining_ms(now) / 1000)} s", 34, SKY,
                       (width // 2, cy - GRID_PX // 2 + GRID_PX // 2), align="c")
        elif phase is Phase.TEST and trial:
            left_x = width // 2 - GRID_PX - PANEL_GAP // 2
            right_x = width // 2 + PANEL_GAP // 2
            self._grid(screen, trial.left, left_x, cy - GRID_PX // 2,
                       active=self._hover is Side.LEFT)
            self._grid(screen, trial.right, right_x, cy - GRID_PX // 2,
                       active=self._hover is Side.RIGHT)
            self._text(screen, "LEFT", 13, MUTED, (left_x + GRID_PX // 2, cy + GRID_PX // 2 + 12),
                       align="c")
            self._text(screen, "RIGHT", 13, MUTED, (right_x + GRID_PX // 2, cy + GRID_PX // 2 + 12),
                       align="c")
        elif phase is Phase.FEEDBACK and (last := self.game.last_response):
            if not last.responded:
                caption, colour = "no response", AMBER
            elif last.correct:
                caption, colour = f"correct  -  {last.reaction_ms} ms", GREEN
            else:
                caption, colour = "incorrect", RED
            self._text(screen, caption, 27, colour, (width // 2, cy - 40), align="c")
            if trial:
                self._grid(screen, trial.sample, width // 2 - GRID_PX // 2, cy, ring=SKY, scale=0.55,
                           label="sample")
        elif phase is Phase.DONE:
            self._summary(screen, width // 2, cy)
        else:
            self._text(screen, "Press Start session to begin", 20, MUTED,
                       (width // 2, cy), align="c")

        # footer hint
        pygame.draw.rect(screen, BORDER, (0, height - FOOTER_H, width, FOOTER_H))
        self._text(screen, PHASE_HINT[phase], 14, MUTED, (width // 2, height - FOOTER_H // 2),
                   align="c")

        pygame.display.flip()

    def _grid(self, screen, cells, x: int, y: int, ring=None, active: bool = False,
              scale: float = 1.0, label: str = "") -> None:
        step = int(CELL * scale)
        side = step - 4
        overall = step * 4 - 4

        if ring or active:
            pad = 6
            pygame.draw.rect(screen, ring or BLUE,
                             (x - pad, y - pad, overall + pad * 2, overall + pad * 2),
                             border_radius=7, width=3)

        for index, is_red in enumerate(cells):
            row, column = divmod(index, 4)
            rect = pygame.Rect(x + column * step, y + row * step, side, side)
            pygame.draw.rect(screen, RED if is_red else PANEL_BG, rect, border_radius=3)
            pygame.draw.rect(screen, BORDER, rect, width=1, border_radius=3)

        if label:
            self._text(screen, label.upper(), 11, MUTED, (x, y - 22))

    def _blank(self, screen, x: int, y: int) -> None:
        rect = pygame.Rect(x, y, GRID_PX - 4, GRID_PX - 4)
        pygame.draw.rect(screen, PANEL_BG, rect, border_radius=7)
        pygame.draw.rect(screen, BORDER, rect, width=2, border_radius=7)

    def _summary(self, screen, cx: int, cy: int) -> None:
        metrics = self.game.metrics()
        self._text(screen, "Thank you - data received", 26, GREEN, (cx, cy - 74), align="c")

        if metrics.median_rt_ms is None:
            rt_text = "no correct answers"
        else:
            rt_text = f"{metrics.median_rt_ms:.0f} ms"

        rows = (
            ("accuracy", f"{metrics.accuracy * 100:.0f} %   ({metrics.correct}/{metrics.trials})"),
            ("median reaction time", rt_text),
            ("throughput", f"{metrics.throughput:.1f} correct/min"),
        )
        for offset, (label, value) in enumerate(rows):
            y = cy - 24 + offset * 30
            self._text(screen, label, 15, MUTED, (cx - 150, y))
            self._text(screen, value, 16, INK, (cx + 150, y), align="r")

        self._text(screen, "stored for this crew member", 13, MUTED, (cx, cy + 74), align="c")
