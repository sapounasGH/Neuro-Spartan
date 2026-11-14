"""Reading, storing and printing the crew biomarker dataset.

Source: server/Astronaut_Biomarkers_All_Crew.json - a list of 900 records,
two per astronaut per day (Morning / Evening), days 1-50, for 9 astronauts:

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

Three steps, one function each, and the loops are written out longhand:

    load_rows()             READ   file -> list of dicts
    group_by_astronaut()    STORE  list  -> {name: [records...]}
    print_by_astronaut()    PRINT  per astronaut, latest + trend

MARKERS maps the JSON key to the label used in the UI.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

DATA_FILE = Path(__file__).parent / "server" / "Astronaut_Biomarkers_All_Crew.json"

# json key -> display label. ASCII on purpose: printing to a Windows console
# (cp1252) raises UnicodeEncodeError on "\u03b2". Qt labels can show "Aβ40".
MARKERS = {
    "NFL_pg_mL": "NFL",
    "GFAP_pg_mL": "GFAP",
    "Ab40_pg_mL": "Abeta40",
}

# The live Open-Notify API and this dataset disagree on one name.
ALIASES = {
    "Butch Wilmore": "Barry Wilmore",
}

MORNING_FIRST = {"Morning": 0, "Evening": 1}


def normalise_name(name: str) -> str:
    """Map a crew name onto the name used in the biomarker file."""
    return ALIASES.get(name, name)


# --------------------------------------------------------------- 1. READ
def load_rows(path: Path = DATA_FILE) -> list[dict]:
    """Read the JSON file and return the list of records."""
    if not path.exists():
        raise FileNotFoundError(f"biomarker file not found: {path}")

    with path.open(encoding="utf-8") as handle:
        rows = json.load(handle)

    if not isinstance(rows, list):
        raise ValueError(f"expected a list of records, got {type(rows).__name__}")

    clean: list[dict] = []
    for row in rows:                          # keep only complete records
        if not isinstance(row, dict) or "Astronaut" not in row:
            continue
        clean.append(row)
    return clean


# -------------------------------------------------------------- 2. STORE
def group_by_astronaut(rows: list[dict]) -> dict[str, list[dict]]:
    """Store every record under its astronaut, in flight-day order.

    Sorting by (Day_in_Space, Time_of_Day) means index 0 is the first sample
    and index -1 is the most recent, for any marker we later want to trend.
    """
    grouped: dict[str, list[dict]] = {}

    for row in rows:
        name = normalise_name(row["Astronaut"])
        if name not in grouped:               # first time we see this astronaut
            grouped[name] = []
        grouped[name].append(row)

    for name in grouped:
        grouped[name].sort(
            key=lambda r: (r["Day_in_Space"], MORNING_FIRST.get(r["Time_of_Day"], 2))
        )

    return grouped


# -------------------------------------------------------------- 3. PRINT
def print_by_astronaut(grouped: dict[str, list[dict]], limit: int | None = None) -> None:
    """One block per astronaut: header, then the markers, then anomalies."""
    names = sorted(grouped)
    if limit is not None:
        names = names[:limit]

    for name in names:
        samples = grouped[name]
        first, last = samples[0], samples[-1]
        days = {s["Day_in_Space"] for s in samples}

        print("=" * 62)
        print(f"{name}   {len(samples)} samples   days {min(days)}-{max(days)}")
        print(f"  status now : {last['Clinical_Status']}  ({last['Simulated_Anomaly']})")
        print(f"  {'marker':6s} {'first':>10s} {'latest':>10s} {'mean':>10s} {'slope/day':>10s}")

        for key, label in MARKERS.items():
            values = [s[key] for s in samples]           # one loop per marker
            slope = trend_per_day([(s["Day_in_Space"], v) for s, v in zip(samples, values)])
            print(f"  {label:6s} {values[0]:10.2f} {values[-1]:10.2f}"
                  f" {statistics.fmean(values):10.2f} {slope:+10.3f}")
        print()


def trend_per_day(pairs: list[tuple[int, float]]) -> float:
    """Least-squares slope, samples per flight day (the dataset's 'normalised slope')."""
    n = len(pairs)
    if n < 2:
        return 0.0
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return 0.0
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    return numerator / denominator


def latest(astronaut: str, grouped: dict[str, list[dict]]) -> dict | None:
    """Most recent record for one astronaut - what the Biomarkers tab shows."""
    samples = grouped.get(normalise_name(astronaut))
    return samples[-1] if samples else None


def summary(astronaut: str, grouped: dict[str, list[dict]]) -> dict:
    """Per-astronaut marker averages + slopes, ready for the UI."""
    name = normalise_name(astronaut)
    samples = grouped.get(name, [])
    out: dict = {"astronaut": name, "samples": len(samples), "markers": {}}
    if not samples:
        return out

    out["status"] = samples[-1]["Clinical_Status"]
    out["anomaly"] = samples[-1]["Simulated_Anomaly"]
    for key, label in MARKERS.items():
        values = [s[key] for s in samples]
        out["markers"][label] = {
            "first": values[0],
            "latest": values[-1],
            "mean": statistics.fmean(values),
            "slope_per_day": trend_per_day(
                [(s["Day_in_Space"], v) for s, v in zip(samples, values)]
            ),
        }
    return out


if __name__ == "__main__":
    rows = load_rows()
    grouped = group_by_astronaut(rows)
    print(f"read {len(rows)} records for {len(grouped)} astronauts\n")
    print_by_astronaut(grouped, limit=2)
    print("lookup by live-crew name (handles Butch/Barry aliasing):")
    for crew_name in ("Oleg Kononenko", "Butch Wilmore", "Nobody At All"):
        record = latest(crew_name, grouped)
        if record:
            print(f"  {crew_name:16s} -> day {record['Day_in_Space']:>2} "
                  f"NFL {record['NFL_pg_mL']:6.2f}  {record['Clinical_Status']}")
        else:
            print(f"  {crew_name:16s} -> no data")
