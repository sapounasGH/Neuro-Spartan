r"""NeuroSpartan - application entry point.

Run:
    .venv\Scripts\python.exe main.py
    (or activate the venv first, then just: python main.py)

This is deliberately a blank window: it proves the Qt toolchain works and
gives us an empty shell to build the Neuro Games / Mission Data / Earth
Manager screens into.
"""

import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget


class NeuroSpartanWindow(QMainWindow):
    """Blank main window."""

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("NeuroSpartan")
        self.resize(1280, 800)
        self.setMinimumSize(960, 600)

        # Empty central widget - pages get added here later.
        self.setCentralWidget(QWidget(self))


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NeuroSpartan")

    window = NeuroSpartanWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
