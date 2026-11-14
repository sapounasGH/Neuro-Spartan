r"""NeuroSpartan - application entry point.

Run:
    .venv\Scripts\python.exe main.py
    (or activate the venv first, then just: python main.py)

Layout:  [ collapsible crew sidebar | main content ]
The sidebar pulls the live crew list from Open-Notify (see crew.py) on a
background thread, so the window never freezes while it waits for the API.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from crew import Astronaut, Crew, CrewError, fetch_crew

EXPANDED_WIDTH = 232
COLLAPSED_WIDTH = 54

STYLESHEET = """
QMainWindow { background: #f4f7fa; }

QFrame#Sidebar { background: #15181d; }

QLabel#Brand { color: #e7ecf2; font-size: 13px; font-weight: 600; letter-spacing: 2px; }
QLabel#BrandMark { background: #7fc0f5; color: #0f1318; font-size: 11px; font-weight: 700;
                   border-radius: 4px; }
QLabel#Section { color: #7f8a99; font-size: 10px; font-weight: 600; letter-spacing: 2px; }
QLabel#Count   { color: #7fc0f5; font-size: 11px; font-family: Consolas, monospace; }
QLabel#Status  { color: #8e99a8; font-size: 11px; font-family: Consolas, monospace; }
QLabel#Status[state="error"] { color: #ff8b7a; }

QListWidget#CrewList { background: transparent; border: none; outline: 0;
                       color: #d7dfe9; font-size: 12.5px; }
QListWidget#CrewList::item { padding: 9px 10px; border-left: 3px solid transparent; }
QListWidget#CrewList::item:hover { background: #1e242d; }
QListWidget#CrewList::item:selected { background: #1c3554; border-left: 3px solid #7fc0f5;
                                      color: #ffffff; }

QPushButton { background: transparent; color: #9aa6b6; border: 1px solid #2c333d;
              border-radius: 4px; padding: 6px 8px; font-size: 12px; }
QPushButton:hover { background: #222a34; color: #ffffff; }
QPushButton:pressed { background: #2b333f; }
QPushButton#Toggle { font-family: Consolas, monospace; font-size: 13px;
                     padding: 4px 0px; min-width: 0px; }

QLabel#Title { color: #151a21; font-size: 24px; font-weight: 600; }
QLabel#Title span { color: #2f6fdb; }
QLabel#Selected { color: #3c4753; font-size: 13px; }
QLabel#Hint { color: #6b7787; font-size: 12px; }
QFrame#Placeholder { background: #ffffff; border: 1px solid #dde4ec; border-radius: 6px; }
"""


class CrewLoader(QThread):
    """Fetches the crew list off the UI thread."""

    loaded = Signal(object)  # Crew
    failed = Signal(str)

    def run(self) -> None:  # noqa: D102 - QThread entry point
        try:
            self.loaded.emit(fetch_crew())
        except CrewError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # never let a thread die silently
            self.failed.emit(f"Unexpected error while loading crew: {exc!r}")


class CrewSidebar(QFrame):
    """Left bar: expands/collapses with the toggle button, lists the crew."""

    astronaut_selected = Signal(object)  # Astronaut

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(EXPANDED_WIDTH)
        self._expanded = True
        self._crew: Crew | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 10, 8, 10)
        root.setSpacing(6)

        # --- top row: brand mark + toggle button ---------------------------
        header = QHBoxLayout()
        header.setSpacing(8)

        mark = QLabel("NS")
        mark.setObjectName("BrandMark")
        mark.setFixedSize(24, 24)
        mark.setAlignment(Qt.AlignCenter)
        header.addWidget(mark)

        self.brand = QLabel("NEUROSPARTAN")
        self.brand.setObjectName("Brand")
        self.brand.setTextInteractionFlags(Qt.TextSelectableByMouse)
        header.addWidget(self.brand, 1)

        self.toggle = QPushButton("\N{LEFT-POINTING DOUBLE ANGLE QUOTATION MARK}")
        self.toggle.setObjectName("Toggle")
        self.toggle.setFixedSize(28, 26)
        self.toggle.setCursor(Qt.PointingHandCursor)
        self.toggle.setToolTip("Collapse panel")
        self.toggle.clicked.connect(self.toggle_expanded)
        header.addWidget(self.toggle)
        root.addLayout(header)

        # --- crew section --------------------------------------------------
        self.section = QLabel("MISSION CREW")
        self.section.setObjectName("Section")
        self.section.setIndent(8)
        root.addWidget(self.section)

        self.count = QLabel("connecting\N{HORIZONTAL ELLIPSIS}")
        self.count.setObjectName("Count")
        self.count.setIndent(8)
        self.count.setWordWrap(True)
        root.addWidget(self.count)

        self.crew_list = QListWidget()
        self.crew_list.setObjectName("CrewList")
        self.crew_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.crew_list.setFrameShape(QFrame.NoFrame)
        self.crew_list.itemSelectionChanged.connect(self._emit_selection)
        root.addWidget(self.crew_list, 1)

        # --- bottom row: status + refresh ---------------------------------
        self.status = QLabel("")
        self.status.setObjectName("Status")
        self.status.setIndent(8)
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self.refresh = QPushButton("Refresh")
        self.refresh.setCursor(Qt.PointingHandCursor)
        self.refresh.clicked.connect(self.reload)
        root.addWidget(self.refresh)

    # ------------------------------------------------------------------ width
    def toggle_expanded(self) -> None:
        """Grow/shrink the bar. Labels hide so the icon row stays readable."""
        self._expanded = not self._expanded
        self.setFixedWidth(EXPANDED_WIDTH if self._expanded else COLLAPSED_WIDTH)

        arrow = "\N{LEFT-POINTING DOUBLE ANGLE QUOTATION MARK}" if self._expanded else "\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}"
        self.toggle.setText(arrow)
        self.toggle.setToolTip("Collapse panel" if self._expanded else "Expand panel")

        for widget in (self.brand, self.section, self.count, self.status):
            widget.setVisible(self._expanded)
        self.refresh.setText("Refresh" if self._expanded else "R")

    # ------------------------------------------------------------------- data
    def set_loading(self) -> None:
        self.count.setText("connecting\N{HORIZONTAL ELLIPSIS}")
        self.status.setText("")
        self.status.setProperty("state", "")
        self.crew_list.clear()
        self.crew_list.setEnabled(False)
        self.refresh.setEnabled(False)

    def show_crew(self, crew: Crew) -> None:
        self._crew = crew
        self.crew_list.setEnabled(True)
        self.refresh.setEnabled(True)
        self.count.setText(f"{crew.total} people in space right now")

        self.crew_list.clear()
        for member in crew.members:
            item = QListWidgetItem(str(member))  # "Name (craft)"
            item.setData(Qt.UserRole, member)
            item.setToolTip(f"{member.name}\naboard {member.craft}")
            self.crew_list.addItem(item)

        crafts = " · ".join(crew.crafts())
        self.status.setText(f"{len(crew.members)} loaded from Open-Notify\n{crafts}")
        self.status.setProperty("state", "")

        self.crew_list.setCurrentRow(0)

    def show_error(self, message: str) -> None:
        self.refresh.setEnabled(True)
        self.crew_list.setEnabled(True)
        self.count.setText("crew unavailable")
        self.status.setText(f"{message}\nUse Refresh to retry.")
        self.status.setProperty("state", "error")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def reload(self) -> None:
        """Kick off a fetch. The window owns the worker lifetime."""
        self.window().load_crew()  # type: ignore[union-attr]

    # -------------------------------------------------------------- selection
    def _emit_selection(self) -> None:
        current = self.crew_list.currentItem()
        if current is not None:
            self.astronaut_selected.emit(current.data(Qt.UserRole))


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

        # --- main content: still a shell, pages come next ------------------
        content = QWidget()
        content.setObjectName("Content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(12)

        title = QLabel("NEUROSPARTAN")
        title.setObjectName("Title")
        content_layout.addWidget(title)

        self.placeholder = QFrame()
        self.placeholder.setObjectName("Placeholder")
        placeholder_layout = QVBoxLayout(self.placeholder)
        placeholder_layout.setContentsMargins(18, 18, 18, 18)
        placeholder_layout.setSpacing(8)

        self.selected = QLabel("No astronaut selected yet.")
        self.selected.setObjectName("Selected")
        self.selected.setWordWrap(True)
        placeholder_layout.addWidget(self.selected)

        hint = QLabel("The three pages - Neuro Games, Mission Data & Sensors, "
                      "Earth Manager - will be mounted here.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        placeholder_layout.addWidget(hint)
        placeholder_layout.addStretch(1)

        content_layout.addWidget(self.placeholder, 1)
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
        if self._loader is not None and self._loader.isRunning():
            self._loader.wait(2000)
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NeuroSpartan")
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
