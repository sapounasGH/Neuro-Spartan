"""Read, store and analyse the static biomarker dataset, keyed by live crew.

Source: server/Astronaut_Biomarkers_All_Crew.json - 900 records, two per
astronaut per day (Morning / Evening), days 1-50, for 9 astronauts:

    {
        "Astronaut": "Oleg Kononenko",
        "Date": "2026-09-25",
        "Day_in_Space": 1,
        "Time_of_Day": "Morning",
        "NFL_pg_mL": 10.08,
        "GFAP_pg_mL": 84.0,
        "Ab40_pg_mL": 184.88,
        "Clinical_Status": "Normal",
        "Simulated_Anomaly": "None"
    }

The dataset is static, but WHO we look up comes from the Open-Notify crew list,
so names are resolved rather than hardcoded:

    load_rows()          READ    file -> list of dicts
    group_by_astronaut() STORE    list -> {name: [records in flight order]}
    resolve_crew_name()  MATCH    live API name -> dataset name, or None
    print_by_astronaut() PRINT    one block per astronaut

Nothing in here knows about Qt.
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Iterable
from pathlib import Path

DATA_FILE = Path(__file__).parent / "server" / "Astronaut_Biomarkers_All_Crew.json"

# json key -> display label. ASCII on purpose: printing to a Windows console
# (cp1252) raises UnicodeEncodeError on the beta glyph. Qt labels can show "Aβ40".
MARKERS = {
    "NFL_pg_mL": "NFL",
    "GFAP_pg_mL": "GFAP",
    "Ab40_pg_mL": "Abeta40",
}

BASELINE_SAMPLES = 20        # first 10 days x 2 samples = that person's baseline
SLOPE_THRESHOLD = 0.5        # normalised slope (baseline SD per day) worth flagging

MORNING_FIRST = {"Morning": 0, "Evening": 1}


# --------------------------------------------------------------- 1. READ
def load_rows(path: Path = DATA_FILE) -> list[dict]:
    """Read the JSON file and return its records."""
    if not path.exists():
        raise FileNotFoundError(f"biomarker file not found: {path}")

    with path.open(encoding="utf-8") as handle:
        rows = json.load(handle)

    if not isinstance(rows, list):
        raise ValueError(f"expected a list of records, got {type(rows).__name__}")

    clean: list[dict] = []
    for row in rows:                       # keep only complete records
        if not isinstance(row, dict) or "Astronaut" not in row:
            continue
        if not all(key in row for key in MARKERS):
            continue
        clean.append(row)
    return clean


# -------------------------------------------------------------- 2. STORE
def group_by_astronaut(rows: list[dict]) -> dict[str, list[dict]]:
    """Store every record under its astronaut, in flight-day order.

    Sorted by (Day_in_Space, Time_of_Day) so index 0 is the first sample and
    index -1 the most recent.
    """
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["Astronaut"], []).append(row)
    for samples in grouped.values():
        samples.sort(key=lambda r: (r["Day_in_Space"], MORNING_FIRST.get(r["Time_of_Day"], 2)))
    return grouped


# -------------------------------------------------------------- 3. MATCH
def _surname(name: str) -> str:
    return name.strip().split()[-1].lower() if name.strip() else ""


def resolve_crew_name(api_name: str, available: Iterable[str]) -> str | None:
    """Find the dataset entry for a live API crew name.

    Order: exact, case-insensitive, then a *unique* surname match. The surname
    rule is what links "Butch Wilmore" (API) to "Barry Wilmore" (dataset)
    without hardcoding either name, and the uniqueness requirement means we
    never guess when two crew share a surname.
    """
    names = list(available)

    if api_name in names:
        return api_name

    lowered = {n.lower(): n for n in names}
    if api_name.lower() in lowered:
        return lowered[api_name.lower()]

    target = _surname(api_name)
    candidates = [n for n in names if _surname(n) == target]
    if len(candidates) == 1:
        return candidates[0]
    return None


# ---------------------------------------------------------- derived stats
def trend_per_day(pairs: list[tuple[int, float]]) -> float:
    """Least-squares slope per flight day."""
    if len(pairs) < 2:
        return 0.0
    xs = [x for x, _ in pairs]
    ys = [y for _, y in pairs]
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return 0.0
    return sum((x - mean_x) * (y - mean_y) for x, y in pairs) / denominator


def series(samples: list[dict], key: str) -> list[tuple[int, float]]:
    """(day, value) pairs for one marker."""
    return [(s["Day_in_Space"], s[key]) for s in samples]


def baseline_sd(values: list[float], window: int = BASELINE_SAMPLES) -> float:
    """Spread of that astronaut's own early baseline - the normaliser."""
    return statistics.pstdev(values[:window]) or 1.0


def normalised_slopes(samples: list[dict]) -> dict[str, float]:
    """Slope divided by baseline SD, per marker: the 'normalised slope'.

    Comparable across people and across markers with wildly different units.
    """
    out: dict[str, float] = {}
    for key, label in MARKERS.items():
        values = [s[key] for s in samples]
        out[label] = trend_per_day(series(samples, key)) / baseline_sd(values)
    return out


def latest_flagged_day(samples: list[dict]) -> int | None:
    """First flight day on which the record is not 'Normal'."""
    days = [s["Day_in_Space"] for s in samples if s.get("Clinical_Status") != "Normal"]
    return min(days) if days else None


def morning_evening_means(samples: list[dict]) -> dict[str, tuple[float, float]]:
    """Mean of each marker split by time of day."""
    out: dict[str, tuple[float, float]] = {}
    for key, label in MARKERS.items():
        morning = [s[key] for s in samples if s.get("Time_of_Day") == "Morning"]
        evening = [s[key] for s in samples if s.get("Time_of_Day") == "Evening"]
        out[label] = (
            statistics.fmean(morning) if morning else 0.0,
            statistics.fmean(evening) if evening else 0.0,
        )
    return out


def summary(api_name: str, grouped: dict[str, list[dict]]) -> dict:
    """Everything the UI needs for one crew member, keyed by the API's name."""
    resolved = resolve_crew_name(api_name, grouped)
    samples = grouped.get(resolved, []) if resolved else []

    result: dict = {
        "api_name": api_name,
        "dataset_name": resolved,
        "found": bool(samples),
        "samples": len(samples),
        "markers": {},
    }
    if not samples:
        return result

    slopes = normalised_slopes(samples)
    for key, label in MARKERS.items():
        values = [s[key] for s in samples]
        result["markers"][label] = {
            "series": series(samples, key),
            "first": values[0],
            "latest": values[-1],
            "mean": statistics.fmean(values),
            "slope_per_day": trend_per_day(series(samples, key)),
            "baseline_sd": baseline_sd(values),
            "normalised_slope": slopes[label],
            "flagged": abs(slopes[label]) >= SLOPE_THRESHOLD,
        }

    result["status"] = samples[-1].get("Clinical_Status", "Unknown")
    result["anomaly"] = samples[-1].get("Simulated_Anomaly", "None")
    result["flagged_day"] = latest_flagged_day(samples)
    result["morning_evening"] = morning_evening_means(samples)
    return result


# -------------------------------------------------------------- 4. PRINT
def print_by_astronaut(grouped: dict[str, list[dict]], limit: int | None = None) -> None:
    """One block per astronaut: header, then a line per marker."""
    names = sorted(grouped)
    if limit is not None:
        names = names[:limit]

    for name in names:
        samples = grouped[name]
        days = {s["Day_in_Space"] for s in samples}
        flagged = latest_flagged_day(samples)

        print("=" * 70)
        print(f"{name}   {len(samples)} samples   days {min(days)}-{max(days)}"
              f"   onset day {flagged if flagged else 'none'}")
        print(f"  status now : {samples[-1].get('Clinical_Status')} "
              f"({samples[-1].get('Simulated_Anomaly')})")
        print(f"  {'marker':9s}{'first':>10s}{'latest':>10s}{'mean':>10s}"
              f"{'slope/d':>10s}{'normSlope':>11s}")

        slopes = normalised_slopes(samples)
        for key, label in MARKERS.items():
            values = [s[key] for s in samples]
            mark = "  <- flag" if abs(slopes[label]) >= SLOPE_THRESHOLD else ""
            print(f"  {label:9s}{values[0]:10.2f}{values[-1]:10.2f}"
                  f"{statistics.fmean(values):10.2f}"
                  f"{trend_per_day(series(samples, key)):+10.3f}{slopes[label]:+11.3f}{mark}")
        print()


if __name__ == "__main__":
    from crew import fetch_crew                     # live names, not hardcoded

    grouped = group_by_astronaut(load_rows())
    print(f"dataset holds {sum(len(v) for v in grouped.values())} records "
          f"for {len(grouped)} astronauts\n")

    live = fetch_crew()
    print(f"live crew from Open-Notify: {live.total} people")
    for member in live.members:
        record = summary(member.name, grouped)
        if record["found"]:
            slopes = ", ".join(f"{m} {v['normalised_slope']:+.2f}"
                               for m, v in record["markers"].items())
            print(f"  {member.name:24s} matched '{record['dataset_name']:22s}' {slopes}")
        else:
            print(f"  {member.name:24s} no biomarker records for this crew member")

    print()
    print_by_astronaut(grouped, limit=2)
