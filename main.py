r"""NeuroSpartan - application entry point.

Run:
    .venv\Scripts\python.exe main.py
    (or activate the venv first, then just: python main.py)

This file only wires the app together. The functionality lives in packages:
    crew/        api.py (Open-Notify crew), loader.py (background thread),
                 iss.py (live ISS position widget)
    games/       task.py (WinSCAT delayed-MTS logic, no Qt), renderer.py
                 (pygame view), page.py (the Neurogames tab)
    biomarkers/  analysis.py (read/store/match/stats, no Qt), page.py (charts tab)
    user/        session_store.py (game history JSON), profile_page.py (tab)
    sleep/       model.py (stage parsing, no Qt), page.py (hypnogram tab)
And at the root: main_window.py, sidebar.py, theme.py, paths.py.
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
