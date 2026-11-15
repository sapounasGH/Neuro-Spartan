"""Background worker that fetches the crew list off the UI thread."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .api import CrewError, fetch_crew


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
