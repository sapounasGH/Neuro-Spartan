"""Crew data from the Open-Notify human-spaceflight API.

    http://api.open-notify.org/astros.json  ->  {
        "people": [ {"craft": "ISS", "name": "Oleg Kononenko"}, ... ],
        "number": 14,
        "status": "ok"
    }

Everything network related lives here so the UI code stays about the UI.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

API_URL = "http://api.open-notify.org/astros.json"


class CrewError(RuntimeError):
    """Raised when the crew list cannot be retrieved or parsed."""


@dataclass(frozen=True)
class Astronaut:
    name: str
    craft: str

    def __str__(self) -> str:
        return f"{self.name} ({self.craft})"


@dataclass(frozen=True)
class Crew:
    total: int
    members: tuple[Astronaut, ...]

    def crafts(self) -> tuple[str, ...]:
        """Distinct vehicles, in the order they first appear."""
        seen: dict[str, None] = {}
        for member in self.members:
            seen.setdefault(member.craft, None)
        return tuple(seen)


def fetch_crew(timeout: float = 10.0) -> Crew:
    """Return the people currently in space. Raises CrewError on any failure."""
    try:
        response = requests.get(API_URL, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise CrewError(f"Open-Notify is unreachable: {exc}") from exc
    except ValueError as exc:  # json decode errors
        raise CrewError("Open-Notify returned something that is not JSON.") from exc

    if not isinstance(data, dict) or "people" not in data:
        raise CrewError("Open-Notify response is missing the 'people' list.")

    members: list[Astronaut] = []
    for person in data["people"]:
        try:
            if person["craft"] == "ISS":
                members.append(Astronaut(name=str(person["name"]), craft=str(person["craft"])))
        except (KeyError, TypeError):
            continue  # skip malformed entries instead of failing the whole list
        

    if not members:
        raise CrewError("Open-Notify returned an empty crew list.")

    total = data.get("number") ## ISS filtering
    for person in data["people"]:
        if person["craft"] != "ISS":
            total = total - 1

    if not isinstance(total, int):
        total = len(members)

    return Crew(total=total, members=tuple(members))
