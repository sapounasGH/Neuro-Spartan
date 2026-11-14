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
from sidebar import CrewSidebar


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

        # Tabs: Neurogames | Biomarkers | Info | History
        page_names = ("Neurogames", "Biomarkers", "Info", "History")
        page_blurbs = (
            "Cognitive games and daily sessions.",
            "NFL, GFAP and Aβ-40 readings.",
            "Score, trend chart and recommendations.",
            "Past sessions, dose and crew events.",
        )

        self.tabs = QTabBar()
        self.tabs.setObjectName("Tabs")
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        for label in page_names:
            self.tabs.addTab(label)

        self.pages = QStackedWidget()
        for name, blurb in zip(page_names, page_blurbs):
            self.pages.addWidget(self._make_page(name, blurb))

        # One tab switch changes only the stacked panel below.
        self.tabs.currentChanged.connect(self.pages.setCurrentIndex)

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
        loader.failed.connect(self.sidebar.show_error)
        loader.finished.connect(loader.deleteLater)
        loader.finished.connect(lambda: setattr(self, "_loader", None))
        self._loader = loader
        loader.start()

    # ------------------------------------------------------------ ui updates
    def show_astronaut(self, member: Astronaut) -> None:
        self.selected.setText(
            f"Selected crew member: <b>{member.name}</b> aboard {member.craft}"
        )

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        # A request can take up to the fetch timeout; don't tear down under it.
        if self._loader is not None and self._loader.isRunning():
            if not self._loader.wait(11000):
                self._loader.terminate()
                self._loader.wait(1000)
        super().closeEvent(event)
