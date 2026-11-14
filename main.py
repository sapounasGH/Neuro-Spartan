r"""NeuroSpartan - application entry point.

Run:
    .venv\Scripts\python.exe main.py
    (or activate the venv first, then just: python main.py)

This file only wires the app together. Everything lives in its own module:
    crew.py         - Open-Notify data layer (no Qt)
    theme.py        - application stylesheet (QSS)
    crew_loader.py  - CrewLoader, the background fetch thread
    sidebar.py      - CrewSidebar, the collapsible crew bar
    main_window.py  - MainWindow, the window + tabbed page panel
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from main_window import MainWindow
from theme import STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NeuroSpartan")
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
