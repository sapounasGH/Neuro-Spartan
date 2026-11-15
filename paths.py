"""Single place where the project's data and asset files are located.

Every module used to compute its own path from ``__file__``, which broke the
moment files moved into packages: ``Path(__file__).parent / "server"`` resolves
differently for a file at the root than for one inside ``biomarkers/``. These
constants are anchored to the project root, so moving a file can no longer
move its data.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVER_DIR = ROOT / "server"
ASSETS_DIR = ROOT / "assets"

BIOMARKERS_FILE = SERVER_DIR / "Astronaut_Biomarkers_All_Crew.json"
SLEEP_FILE = SERVER_DIR / "sleep_data.json"
SESSIONS_FILE = SERVER_DIR / "game_sessions.json"
SEND_ICON = ASSETS_DIR / "image.png"
