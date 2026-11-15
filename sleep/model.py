"""Sleep data: parsing a night of stage segments into totals. No Qt in here.

Supported JSON layouts (read-only, never written):
    {"date": ..., "people": [{"person": ..., "segments": [...]}, ...]}
    {"person": ..., "date": ..., "segments": [...]}          (single person)
Each segment: {"start": "YYYY-MM-DDTHH:MM", "end": "...",
               "stage": "Awake|REM|Light|Deep"}
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from paths import SLEEP_FILE

STAGES = ["Awake", "REM", "Light", "Deep"]


class Sleeper:
    """One astronaut's night, parsed from JSON."""

    def __init__(self, name, segments):
        self.name = name
        parsed = []
        for entry in segments:
            # one malformed segment must not lose the whole night
            try:
                start = datetime.fromisoformat(entry["start"])
                end = datetime.fromisoformat(entry["end"])
            except (KeyError, TypeError, ValueError):
                continue
            stage = entry.get("stage", "Light") if isinstance(entry, dict) else "Light"
            if stage not in STAGES:
                stage = "Light"          # unknown label, keep the minutes somewhere
            parsed.append((start, end, stage))

        self.segments = sorted(parsed, key=lambda s: s[0])
        self.minutes = {st: 0.0 for st in STAGES}
        for a, b, st in self.segments:
            self.minutes[st] += (b - a).total_seconds() / 60

        if self.segments:
            self.start = self.segments[0][0]
            self.end = self.segments[-1][1]
            self.in_bed = (self.end - self.start).total_seconds() / 60
            self.asleep = self.in_bed - self.minutes["Awake"]
        else:
            self.start = self.end = None
            self.in_bed = 0.0
            self.asleep = 0.0

    @property
    def valid(self):
        return bool(self.segments)


def load_sleepers(path: Path | str = SLEEP_FILE):
    """Read the sleep file. Returns (date, sleepers); skips unusable people."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)

    if isinstance(data, list):                      # bare list of people
        data = {"people": data}
    if not isinstance(data, dict):
        raise ValueError("sleep file is neither an object nor a list")

    people = []
    for person in data.get("people", [data]):
        try:
            sleeper = Sleeper(person.get("person", "Unknown"), person.get("segments", []))
        except (AttributeError, TypeError, ValueError):
            continue
        if sleeper.valid:
            people.append(sleeper)
    return data.get("date", ""), people


def fmt_dur(minutes):
    minutes = int(round(minutes))
    return f"{minutes // 60}h {minutes % 60:02d}m"
