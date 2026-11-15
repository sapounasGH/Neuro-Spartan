"""Games: the WinSCAT delayed-MTS task, its pygame renderer and the tab."""

from .page import NeuroGamesPage, Session
from .renderer import WinSCATView
from .task import (
    DELAY_MS,
    FEEDBACK_MS,
    RESPONSE_WINDOW_MS,
    SAMPLE_MS,
    DelayedMTS,
    Metrics,
    Phase,
    Response,
    Side,
    Trial,
)

__all__ = [
    "DelayedMTS", "Metrics", "Phase", "Response", "Side", "Trial",
    "WinSCATView", "NeuroGamesPage", "Session",
    "SAMPLE_MS", "DELAY_MS", "RESPONSE_WINDOW_MS", "FEEDBACK_MS",
]
