"""Persistent history of Neuro Games sessions, as JSON in server/.

One record per finished WinSCAT run. Written the moment a session ends, so the
Profile tab can show a real history across app restarts instead of whatever
happens to be in memory.

    server/game_sessions.json
    [
        {
            "astronaut": "Butch Wilmore",
            "craft": "ISS",
            "started_at": "2026-11-15T09:42:11",
            "trials": 20,
            "correct": 18,
            "accuracy": 0.9,
            "median_rt_ms": 273.0,
            "throughput": 61.7,
            "elapsed_ms": 17500
        }
    ]

Writes go through a temporary file and os.replace(), so a crash mid-write
cannot leave a half-written file that the next launch refuses to parse.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from paths import SESSIONS_FILE


class SessionStore:
    """Append-only store of game sessions, loaded once at startup."""

    def __init__(self, path: Path = SESSIONS_FILE) -> None:
        self.path = Path(path)
        self.error: str | None = None
        self._records: list[dict] = []
        self.load()

    # ------------------------------------------------------------------ read
    def load(self) -> list[dict]:
        self._records = []
        self.error = None

        if not self.path.exists():
            return []                       # no history yet is normal, not an error

        try:
            with self.path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            # Quarantine rather than delete: the history is the demo's evidence.
            backup = self.path.with_suffix(".corrupt.json")
            try:
                os.replace(self.path, backup)
                self.error = (f"session file was unreadable ({exc}); "
                              f"moved it to {backup.name} and started fresh")
            except OSError:
                self.error = f"session file unreadable and could not be set aside: {exc}"
            return []

        if not isinstance(data, list):
            self.error = "session file is not a JSON list; ignoring its contents"
            return []

        for record in data:
            if isinstance(record, dict) and "astronaut" in record:
                self._records.append(record)

        self._records.sort(key=lambda r: str(r.get("started_at", "")))
        return self._records

    # ----------------------------------------------------------------- write
    def add(self, record: dict) -> dict:
        """Append one session and save immediately."""
        clean = {
            "astronaut": str(record.get("astronaut", "unknown")),
            "craft": str(record.get("craft", "unknown")),
            "started_at": str(record.get("started_at", datetime.now().isoformat(timespec="seconds"))),
            "trials": int(record.get("trials", 0)),
            "correct": int(record.get("correct", 0)),
            "accuracy": round(float(record.get("accuracy", 0.0)), 4),
            "median_rt_ms": (None if record.get("median_rt_ms") is None
                             else round(float(record["median_rt_ms"]), 1)),
            "throughput": round(float(record.get("throughput", 0.0)), 2),
            "elapsed_ms": int(record.get("elapsed_ms", 0)),
        }
        self._records.append(clean)
        self._records.sort(key=lambda r: str(r.get("started_at", "")))
        self.save()
        return clean

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(self._records, handle, indent=2)
            os.replace(temporary, self.path)
            self.error = None
        except OSError as exc:
            self.error = f"could not write {self.path.name}: {exc}"
            try:
                temporary.unlink()
            except OSError:
                pass

    # ---------------------------------------------------------------- views
    @property
    def records(self) -> list[dict]:
        return list(self._records)

    def for_astronaut(self, api_name: str) -> list[dict]:
        """Sessions for one crew member, oldest first.

        The live API name is matched case-insensitively and also by unique
        surname, because the game stores whatever name was on screen and the
        API spelling can differ from an older record.
        """
        target = (api_name or "").strip()
        if not target:
            return []

        exact = [r for r in self._records
                 if str(r.get("astronaut", "")).strip().lower() == target.lower()]
        if exact:
            return exact

        surname = target.split()[-1].lower() if target.split() else ""
        names = {str(r.get("astronaut", "")).strip() for r in self._records
                 if str(r.get("astronaut", "")).strip().split()
                 and str(r.get("astronaut", "")).strip().split()[-1].lower() == surname}
        if len(names) == 1:
            return [r for r in self._records
                    if str(r.get("astronaut", "")).strip() in names]
        return []

    def astronaut_names(self) -> list[str]:
        seen: dict[str, None] = {}
        for record in self._records:
            seen.setdefault(str(record.get("astronaut", "unknown")), None)
        return list(seen)

    def stats(self, api_name: str) -> dict:
        """Aggregate numbers for the profile header."""
        records = self.for_astronaut(api_name)
        empty = {"sessions": 0, "best_accuracy": None, "latest_accuracy": None,
                 "mean_rt": None, "latest_throughput": None, "last_played": None}
        if not records:
            return empty

        accuracies = [float(r.get("accuracy", 0.0)) for r in records]
        reaction_times = [float(r["median_rt_ms"]) for r in records
                          if r.get("median_rt_ms") is not None]

        return {
            "sessions": len(records),
            "best_accuracy": max(accuracies),
            "latest_accuracy": accuracies[-1],
            "mean_rt": sum(reaction_times) / len(reaction_times) if reaction_times else None,
            "latest_throughput": float(records[-1].get("throughput", 0.0)),
            "last_played": records[-1].get("started_at"),
        }


def record_from_session(session) -> dict:
    """Turn a games.page.Session into a storable dict."""
    metrics = session.metrics
    return {
        "astronaut": session.member.name,
        "craft": session.member.craft,
        "started_at": session.started_at.isoformat(timespec="seconds"),
        "trials": metrics.trials,
        "correct": metrics.correct,
        "accuracy": metrics.accuracy,
        "median_rt_ms": metrics.median_rt_ms,
        "throughput": metrics.throughput,
        "elapsed_ms": metrics.elapsed_ms,
    }
