"""Main application window: crew sidebar on the left, tabbed page panel on the right."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
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

        # Tab 0 - the real WinSCAT game page.
        self.neurogames = NeuroGamesPage()
        self.neurogames.session_recorded.connect(self._record_session)

        # Tab 1 - biomarkers plotted from the static file, for live crew names.
        self.biomarkers = BiomarkersPage()

        pages: list[tuple[str, QWidget]] = [
            ("Neurogames", self.neurogames),
            ("Biomarkers", self.biomarkers),
            ("Info", self._make_page("Info", "Score, trend chart and recommendations.")),
            ("History", self._make_page("History", "Past sessions, dose and crew events.")),
            ("Sleep", self._make_page("Sleep", "Sleep data and circadian rhythm.")),
        ]

        self.pages = QStackedWidget()
        for label, widget in pages:
            self.pages.addWidget(widget)
            self.tabs.addTab(label)

        self.biomarkers_tab = next(index for index, (label, _) in enumerate(pages)
                                   if label == "Biomarkers")

        # A tab switch changes only the stacked panel below. Opening the
        # biomarkers tab re-fetches the crew list so its names stay live.
        self.tabs.currentChanged.connect(self._on_tab_changed)

        content_layout.addWidget(self.tabs)
        content_layout.addWidget(self.pages, 1)
        layout.addWidget(content, 1)

        self.setCentralWidget(central)

        self._loader: CrewLoader | None = None
        self.load_crew()

    # ---------------------------------------------------------------- pages
    def _make_page(self, name: str, blurb: str) -> QFrame:
        """One panel: the tab's name large (placeholder for now) + a blurb."""
        page = QFrame()
        page.setObjectName("Placeholder")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(8)

        header = QLabel(name.upper())
        header.setObjectName("PageTitle")
        lay.addWidget(header)

        big = QLabel(name)
        big.setObjectName("PageName")
        lay.addWidget(big)

        note = QLabel(f"{blurb}\n\nThis panel changes when you select the "
                      f"'{name}' tab. Content goes here next.")
        note.setObjectName("Hint")
        note.setWordWrap(True)
        lay.addWidget(note)

        lay.addStretch(1)
        return page

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
    def _on_tab_changed(self, index: int) -> None:
        """Switch the panel; refresh live names when markers are opened."""
        self.pages.setCurrentIndex(index)
        if index == self.biomarkers_tab:
            self.biomarkers.load_data()      # static file is cheap to re-read
            self.load_crew()                 # crew names come from the API

    def show_astronaut(self, member: Astronaut) -> None:
        self.selected.setText(
            f"Selected crew member: <b>{member.name}</b> aboard {member.craft}"
        )
        self.neurogames.set_astronaut(member)
        self.biomarkers.select_astronaut(member.name)

    def _record_session(self, session) -> None:
        """Keep finished runs so Info and History can read them later."""
        self.sessions.append(session)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        # Release the SDL surface before Qt tears the window down.
        self.neurogames.close()

        # A request can take up to the fetch timeout; don't tear down under it.
        if self._loader is not None and self._loader.isRunning():
            if not self._loader.wait(11000):
                self._loader.terminate()
                self._loader.wait(1000)
        super().closeEvent(event)
