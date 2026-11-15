"""Neurogames tab: run a WinSCAT delayed-MTS session for the selected crew member.

Flow the panel walks the astronaut through:

1. "Start session for <name>"      - button, enabled once a crew member is selected
2. the game itself                 - sample -> 5 s delay -> two grids, 3 practice + 20 trials
3. "Thank you - data received"     - shown inside the game, mirrored into the summary line

Every finished session is reported through ``session_recorded`` and persisted
by MainWindow into server/game_sessions.json, so the Profile tab can show a
real history that survives restarts.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from crew import Astronaut
from winscat import Metrics
from winscat_view import WinSCATView

# WinSCAT defaults; drop these to 6 / 1 for a short demo run.
TRIALS = 20
PRACTICE = 3


class Session:
    """One completed MTS run, attributed to a crew member."""

    def __init__(self, member: Astronaut, metrics: Metrics, started_at: datetime) -> None:
        self.member = member
        self.metrics = metrics
        self.started_at = started_at

    @property
    def accuracy(self) -> float:
        return self.metrics.accuracy

    @property
    def throughput(self) -> float:
        return self.metrics.throughput

    def summary_line(self) -> str:
        rt = "n/a" if self.metrics.median_rt_ms is None else f"{self.metrics.median_rt_ms:.0f} ms"
        return (
            f"{self.started_at:%d %b %H:%M}  -  {self.member.name}: "
            f"accuracy {self.metrics.accuracy * 100:.0f} %, "
            f"median RT {rt}, "
            f"throughput {self.metrics.throughput:.1f} correct/min"
        )


class NeuroGamesPage(QWidget):
    """Start / stop a session and report the recorded data."""

    session_recorded = Signal(object)  # Session

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._member: Astronaut | None = None
        self._started_at: datetime | None = None
        self.sessions: list[Session] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # --- what this page is ---------------------------------------------
        heading = QLabel("Delayed Matching to Sample  -  WinSCAT")
        heading.setObjectName("PageTitle")
        root.addWidget(heading)

        about = QLabel(
            f"A 4x4 red/white pattern is shown, held in memory for 5 s, then matched "
            f"against two grids. {PRACTICE} practice + {TRIALS} scored trials record "
            f"accuracy, median reaction time and throughput."
        )
        about.setObjectName("Hint")
        about.setWordWrap(True)
        root.addWidget(about)

        # --- control row ----------------------------------------------------
        controls = QHBoxLayout()
        controls.setSpacing(10)

        self.start = QPushButton("Select a crew member to start")
        self.start.setDefault(True)
        self.start.setEnabled(False)
        self.start.setMinimumHeight(34)
        self.start.setCursor(Qt.PointingHandCursor)
        self.start.clicked.connect(self._start_session)
        controls.addWidget(self.start)

        self.state = QLabel("idle")
        self.state.setObjectName("Hint")
        controls.addWidget(self.state, 1)
        root.addLayout(controls)

        # --- the game -------------------------------------------------------
        self.view = WinSCATView()
        self.view.session_finished.connect(self._finish_session)
        self.view.render_failed.connect(self._render_broke)
        root.addWidget(self.view, 0, Qt.AlignHCenter)

        # --- result line ----------------------------------------------------
        self.result = QLabel("No session recorded yet.")
        self.result.setObjectName("Hint")
        self.result.setWordWrap(True)
        root.addWidget(self.result)

    # ------------------------------------------------------------------ crew
    def set_astronaut(self, member: Astronaut | None) -> None:
        """Called when the crew list selection changes."""
        self._member = member
        self._refresh_button()

    def _refresh_button(self) -> None:
        if self._member is None:
            self.start.setText("Select a crew member to start")
            self.start.setEnabled(False)
            return
        if self.view.game.is_running:
            self.start.setText("Session running...")
            self.start.setEnabled(False)
            return
        self.start.setText(f"Start session for {self._member.name}")
        self.start.setEnabled(True)

    # ---------------------------------------------------------------- session
    def _start_session(self) -> None:
        if self._member is None:
            return
        self._started_at = datetime.now()
        if not self.view.start_session():
            self.state.setText("engine unavailable")
            self.result.setText(self.view.error or "pygame failed to start.")
            self._started_at = None
            self._refresh_button()
            return

        self.state.setText(f"running - {self._member.name} ({self._member.craft})")
        self.result.setText("Collecting responses...")
        self._refresh_button()

    def _finish_session(self, metrics: Metrics) -> None:
        if self._member is None or self._started_at is None:
            return
        session = Session(self._member, metrics, self._started_at)
        self.sessions.append(session)

        self.state.setText("session complete")
        self.result.setText("Thank you, data received.  " + session.summary_line())
        self._started_at = None
        self.session_recorded.emit(session)
        self._refresh_button()

    # ------------------------------------------------------------- lifecycle
    def _render_broke(self, message: str) -> None:
        """The game loop raised - say so instead of freezing on one frame."""
        self.state.setText("game stopped unexpectedly")
        self.result.setText(f"The game loop hit an error and stopped: {message}")
        self._started_at = None
        self._refresh_button()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Paint the idle frame as soon as the tab is visible."""
        super().showEvent(event)
        self.view.prepare()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt naming
        # A session cannot be paused: the phase deadlines would fall into the
        # past and trials would cascade on return. Abandon it instead so no
        # corrupted data is recorded.
        if self.view.game.is_running:
            self.view.cancel()
            self._started_at = None
            self.state.setText("session cancelled")
            self.result.setText("You left the tab - the session was cancelled, "
                                "nothing was recorded.")
            self._refresh_button()
        super().hideEvent(event)

    def close(self) -> bool:
        self.view.shutdown()
        return super().close()
