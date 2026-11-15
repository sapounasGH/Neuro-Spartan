"""Main application window: crew sidebar on the left, tabbed page panel on the right."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from crew import Astronaut
from crew_loader import CrewLoader
from neurogames_page import NeuroGamesPage
from sidebar import CrewSidebar
from biomarkers_page import BiomarkersPage
from profile_page import ProfilePage
from session_store import SessionStore, record_from_session
from sleep import SleepPage, load_sleepers, DEFAULT_JSON as SLEEP_JSON
import biomarkers


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NeuroSpartan")
        self.resize(1280, 800)
        self.setMinimumSize(960, 600)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = CrewSidebar()
        self.sidebar.astronaut_selected.connect(self.show_astronaut)
        layout.addWidget(self.sidebar)

        # --- main content: tabs above a swappable panel ---------------------
        content = QWidget()
        content.setObjectName("Content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(12)

        title = QLabel("NEUROSPARTAN")
        title.setObjectName("Title")
        content_layout.addWidget(title)

        self.selected = QLabel("No astronaut selected yet.")
        self.selected.setObjectName("Selected")
        self.selected.setWordWrap(True)
        content_layout.addWidget(self.selected)

        # Tabs and pages are built from ONE list below, so they cannot drift
        # out of sync the way two separate hardcoded lists can.
        self.tabs = QTabBar()
        self.tabs.setObjectName("Tabs")
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)

        self.sessions: list = []

        # --- shared data, loaded once here and handed to the pages ----------
        self.store = SessionStore()
        self.biomarker_data: dict[str, list[dict]] = {}
        self.biomarker_error: str | None = None
        self.sleep_date: str = ""
        self.sleep_people: list = []
        self.sleep_error: str | None = None

        # Tab 0 - the real WinSCAT game page. MainWindow persists finished runs,
        # so the page itself does not hold the store.
        self.neurogames = NeuroGamesPage()
        self.neurogames.session_recorded.connect(self._record_session)

        # Tab 1 - biomarkers plotted from the static file, for live crew names.
        self.biomarkers = BiomarkersPage()
        self.biomarkers.reload_requested.connect(self.reload_biomarkers)

        # Tab 2 - profile: identity + game history + biomarker record.
        self.profile = ProfilePage()
        self.profile.set_store(self.store)

        # Tab 4 - sleep: hypnogram per astronaut, data handed in like the rest.
        self.sleep = SleepPage()

        pages: list[tuple[str, QWidget]] = [
            ("Neurogames", self.neurogames),
            ("Biomarkers", self.biomarkers),
            ("Sleep", self.sleep),
            ("Profile", self.profile),
        ]

        self.reload_biomarkers()
        self.reload_sleep()

        self.pages = QStackedWidget()
        for label, widget in pages:
            self.pages.addWidget(widget)
            self.tabs.addTab(label)

        # A tab switch changes only the stacked panel below. Crew names are
        # fetched once at startup and handed to each page - see load_crew().
        self.tabs.currentChanged.connect(self.pages.setCurrentIndex)

        content_layout.addWidget(self.tabs)
        content_layout.addWidget(self.pages, 1)
        layout.addWidget(content, 1)

        self.setCentralWidget(central)

        self._loader: CrewLoader | None = None
        self.load_crew()

    # ---------------------------------------------------------------- network
    def load_crew(self) -> None:
        if self._loader is not None and self._loader.isRunning():
            return
        self.sidebar.set_loading()

        loader = CrewLoader(self)
        loader.loaded.connect(self.sidebar.show_crew)
        loader.loaded.connect(self.biomarkers.set_crew)   # names, not hardcoded
        loader.failed.connect(self.sidebar.show_error)
        loader.failed.connect(self.biomarkers.show_error)
        loader.finished.connect(loader.deleteLater)
        loader.finished.connect(lambda: setattr(self, "_loader", None))
        self._loader = loader
        loader.start()

    # ------------------------------------------------------------ ui updates
    def show_astronaut(self, member: Astronaut) -> None:
        self.selected.setText(
            f"Selected crew member: <b>{member.name}</b> aboard {member.craft}"
        )
        self.neurogames.set_astronaut(member)
        self.biomarkers.select_astronaut(member.name)
        self.profile.show_astronaut(member)
        self.sleep.show_astronaut(member.name)

    def reload_biomarkers(self) -> None:
        """Read the biomarker file once, then hand the same dict to each page."""
        try:
            self.biomarker_data = biomarkers.group_by_astronaut(biomarkers.load_rows())
            self.biomarker_error = None
        except (FileNotFoundError, ValueError, OSError) as exc:
            self.biomarker_data = {}
            self.biomarker_error = str(exc)

        self.biomarkers.set_biomarkers(self.biomarker_data, self.biomarker_error)
        self.profile.set_biomarkers(self.biomarker_data)

    def reload_sleep(self) -> None:
        """Read the sleep file once, then hand it to the page."""
        try:
            self.sleep_date, self.sleep_people = load_sleepers(SLEEP_JSON)
            self.sleep_error = None
        except (FileNotFoundError, ValueError, OSError, KeyError) as exc:
            self.sleep_date, self.sleep_people = "", []
            self.sleep_error = str(exc)
        self.sleep.set_data(self.sleep_date, self.sleep_people)

    def _record_session(self, session) -> None:
        """Persist a finished run, then let the profile tab show it."""
        self.store.add(record_from_session(session))
        self.sessions.append(session)
        self.profile.set_store(self.store)
        if self.store.error:
            self.statusBar().showMessage(self.store.error, 8000)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        # Release the SDL surface before Qt tears the window down.
        self.neurogames.close()

        # A request can take up to the fetch timeout; don't tear down under it.
        if self._loader is not None and self._loader.isRunning():
            if not self._loader.wait(11000):
                self._loader.terminate()
                self._loader.wait(1000)
        super().closeEvent(event)
