"""Profile tab: one astronaut's identity, game history and biomarker record.

Replaces the old "History" placeholder. Everything here is data the app
already has - nothing is typed in by hand:

    identity     from the live Open-Notify crew list (name + station)
    games        from server/game_sessions.json via SessionStore
    biomarkers   from server/Astronaut_Biomarkers_All_Crew.json

Both datasets are loaded once by MainWindow and handed in through
set_store() / set_biomarkers(), so this page never reads a file itself.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import QMargins, QPointF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from crew import Astronaut
import biomarkers
from session_store import SessionStore

INK = QColor("#151a21")
MUTED = QColor("#6b7787")
BLUE = QColor("#2f6fdb")
AMBER = QColor("#c9821b")
GREEN = QColor("#1d9d6f")
RED = QColor("#dd3b28")
GRID = QColor("#e2e8ef")

MARKER_COLOURS = {"NFL": BLUE, "GFAP": AMBER, "Abeta40": GREEN}

# the hand-drawn face from assets/, used as the button icon
SEND_ICON = Path(__file__).resolve().parent / "assets" / "image.png"

# The app-wide QPushButton rule in theme.py is built for the dark sidebar
# (#9aa6b6 text on transparent) - unreadable on this white card, so this
# button styles itself explicitly.
SEND_BUTTON_QSS = """
QPushButton {
    background: #ffffff;
    color: #1b4d9e;
    border: 1px solid #c8d3e0;
    border-radius: 5px;
    padding: 5px 10px 5px 6px;
    font-size: 12px;
}
QPushButton:hover { background: #eaf3fd; border-color: #2f6fdb; }
QPushButton:pressed { background: #d6e9fb; }
QPushButton:disabled { color: #93a0b1; border-color: #e2e8ef; background: #f4f7fa; }
"""


def load_send_icon(path: Path = SEND_ICON) -> QIcon:
    """The hand-drawn face, or an empty icon if the asset is missing.

    An empty QIcon leaves the button's text intact, so a teammate whose
    checkout lacks assets/ still gets a working, readable button.
    """
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return QIcon()
    return QIcon(pixmap)


def initials(name: str) -> str:
    parts = [p for p in name.replace(".", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def pretty_timestamp(value: str | None) -> str:
    """ISO text from the store -> '15 Nov 09:42'; odd values pass through."""
    if not value:
        return "-"
    try:
        return datetime.fromisoformat(str(value)).strftime("%d %b %H:%M")
    except ValueError:
        return str(value)


class ProfilePage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._member: Astronaut | None = None
        self._store: SessionStore | None = None
        self._grouped: dict[str, list[dict]] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        heading = QLabel("Profile")
        heading.setObjectName("PageTitle")
        root.addWidget(heading)

        # ---------------- identity card -------------------------------------
        card = QFrame()
        card.setObjectName("Placeholder")
        card_row = QHBoxLayout(card)
        card_row.setContentsMargins(14, 12, 14, 12)
        card_row.setSpacing(14)

        self.avatar = QLabel("?")
        self.avatar.setAlignment(Qt.AlignCenter)
        self.avatar.setStyleSheet(
            "background:#2f6fdb;color:#ffffff;font-size:17px;font-weight:700;"
            "border-radius:24px;")
        self.avatar.setFixedSize(48, 48)
        card_row.addWidget(self.avatar)

        who = QVBoxLayout()
        who.setSpacing(2)
        self.name = QLabel("No crew member selected")
        self.name.setStyleSheet("font-size:17px;font-weight:600;color:#151a21;")
        who.addWidget(self.name)
        self.station = QLabel("station: -")
        self.station.setObjectName("Hint")
        who.addWidget(self.station)
        self.record_note = QLabel("")
        self.record_note.setObjectName("Hint")
        who.addWidget(self.record_note)
        card_row.addLayout(who)

        card_row.addStretch(1)

        # top-right, where the send button belongs
        right_side = QVBoxLayout()
        right_side.setSpacing(6)

        self.send_button = QPushButton("Send to Cimon")
        self.send_button.setCursor(Qt.PointingHandCursor)
        self.send_button.setStyleSheet(SEND_BUTTON_QSS)
        self.send_button.setIcon(load_send_icon())
        self.send_button.setIconSize(QSize(22, 22))
        self.send_button.setToolTip("Dead button - prints this astronaut's data.")
        self.send_button.setEnabled(False)
        self.send_button.clicked.connect(self.print_data)
        right_side.addWidget(self.send_button, 0, Qt.AlignRight)

        self.counters = QLabel("")
        self.counters.setObjectName("Hint")
        self.counters.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        right_side.addWidget(self.counters)
        right_side.addStretch(1)

        card_row.addLayout(right_side)
        root.addWidget(card)

        self.send_note = QLabel("")
        self.send_note.setObjectName("Hint")
        self.send_note.setWordWrap(True)
        root.addWidget(self.send_note)

        # ---------------- two columns ---------------------------------------
        columns = QGridLayout()
        columns.setHorizontalSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(8)

        self.game_table = QTableWidget(0, 6)
        self.game_table.setHorizontalHeaderLabels(
            ["when", "trials", "correct", "accuracy", "median RT", "throughput"])
        self.game_table.verticalHeader().setVisible(False)
        self.game_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.game_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.game_table.setWordWrap(False)
        header = self.game_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        left.addWidget(self.game_table, 1)

        self.accuracy_view = self._view("accuracy % per session")
        self.rt_view = self._view("median reaction time per session")
        left.addWidget(self.accuracy_view)
        left.addWidget(self.rt_view)

        left_box = QGroupBox("Neuro Games history")
        left_box.setLayout(left)

        right = QVBoxLayout()
        right.setSpacing(8)

        self.marker_table = QTableWidget(0, 6)
        self.marker_table.setHorizontalHeaderLabels(
            ["marker", "first", "latest", "slope/day", "norm slope", "flag"])
        self.marker_table.verticalHeader().setVisible(False)
        self.marker_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.marker_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.marker_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        right.addWidget(self.marker_table)

        self.clinical = QLabel("")
        self.clinical.setWordWrap(True)
        self.clinical.setObjectName("Hint")
        right.addWidget(self.clinical)

        self.marker_view = self._view("NFL and GFAP per flight day")
        right.addWidget(self.marker_view, 1)

        right_box = QGroupBox("Biomarkers")
        right_box.setLayout(right)

        columns.addWidget(left_box, 0, 0)
        columns.addWidget(right_box, 0, 1)
        root.addLayout(columns, 1)

    # ------------------------------------------------------------- plumbing
    def set_store(self, store: SessionStore) -> None:
        self._store = store
        self.refresh()

    def set_biomarkers(self, grouped: dict[str, list[dict]]) -> None:
        self._grouped = grouped
        self.refresh()

    def show_astronaut(self, member: Astronaut | None) -> None:
        self._member = member
        self.refresh()

    # ------------------------------------------------------------- painting
    def refresh(self) -> None:
        member = self._member
        if member is None:
            self.avatar.setText("?")
            self.name.setText("No crew member selected")
            self.station.setText("station: -")
            self.record_note.setText("")
            self.counters.setText("")
            self.game_table.setRowCount(0)
            self.marker_table.setRowCount(0)
            self.clinical.setText("select a crew member in the left rail")
            self._empty(self.accuracy_view, "accuracy % per session")
            self._empty(self.rt_view, "median reaction time per session")
            self._empty(self.marker_view, "NFL and GFAP per flight day")
            self.send_button.setEnabled(False)
            self.send_button.setToolTip("Select a crew member first")
            return

        self.avatar.setText(initials(member.name))
        self.name.setText(member.name)
        self.station.setText(f"Station: {member.craft}")

        records = self._store.for_astronaut(member.name) if self._store else []
        summary = biomarkers.summary(member.name, self._grouped)
        stats = self._store.stats(member.name) if self._store else {}

        self.send_button.setEnabled(True)
        self.send_button.setToolTip(
            f"Dead button - prints {member.name}'s profile data "
            f"({len(records)} game sessions, {summary['samples']} marker samples) "
            f"to the console."
        )

        self.record_note.setText(
            f"Astronaut: {summary['dataset_name']}" if summary["found"]
            else "no biomarker records for this crew member"
        )
        self.counters.setText(
            f"Sessions: {stats.get('sessions', 0)}<br>"
            f"Last played: {pretty_timestamp(stats.get('last_played'))}<br>"
            f"Marker Samples: {summary['samples']}"
        )

        self._fill_games(records)
        self._fill_markers(summary)

    def _fill_games(self, records: list[dict]) -> None:
        self.game_table.setRowCount(len(records))
        for row, record in enumerate(records):
            median_rt = record.get("median_rt_ms")
            values = (
                pretty_timestamp(record.get("started_at")),
                str(record.get("trials", 0)),
                str(record.get("correct", 0)),
                f"{float(record.get('accuracy', 0.0)) * 100:.0f} %",
                "-" if median_rt is None else f"{float(median_rt):.0f} ms",
                f"{float(record.get('throughput', 0.0)):.1f}/min",
            )
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.game_table.setItem(row, column, item)

        if not records:
            self._empty(self.accuracy_view, "accuracy % per session",
                        "no sessions recorded yet")
            self._empty(self.rt_view, "median reaction time per session",
                        "no sessions recorded yet")
            return

        self._trend(self.accuracy_view, "accuracy % per session", [
            (index + 1, float(r.get("accuracy", 0.0)) * 100)
            for index, r in enumerate(records)
        ], BLUE, fixed_low=0.0, fixed_high=100.0)

        self._trend(self.rt_view, "median reaction time per session", [
            (index + 1, float(r["median_rt_ms"]))
            for index, r in enumerate(records)
            if r.get("median_rt_ms") is not None
        ], AMBER)

    def _fill_markers(self, summary: dict) -> None:
        if not summary["found"]:
            self.marker_table.setRowCount(0)
            self.clinical.setText(
                "In the live crew list, but has no entries in the biomarker file."
            )
            self._empty(self.marker_view, "NFL and GFAP per flight day",
                        "no biomarker records")
            return

        markers = summary["markers"]
        self.marker_table.setRowCount(len(markers))
        for row, (label, stats) in enumerate(markers.items()):
            values = (
                label,
                f"{stats['first']:.1f}",
                f"{stats['latest']:.1f}",
                f"{stats['slope_per_day']:+.3f}",
                f"{stats['normalised_slope']:+.3f}",
                "FLAG" if stats["flagged"] else "ok",
            )
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if column == 5:
                    item.setForeground(RED if stats["flagged"] else GREEN)
                if column == 0:
                    item.setForeground(MARKER_COLOURS.get(label, INK))
                self.marker_table.setItem(row, column, item)

        onset = summary.get("flagged_day")
        self.clinical.setText(
            f"{summary['status']}  -  anomaly {summary['anomaly']}"
            + (f"  -  first flagged on flight day {onset}" if onset else "")
        )

        self._two_lines(
            self.marker_view, "NFL and GFAP per flight day",
            [("NFL", markers["NFL"]["series"], BLUE),
             ("GFAP", markers["GFAP"]["series"], AMBER)],
        )

    # ------------------------------------------------------------- dead button
    def build_payload(self) -> dict:
        """Everything this tab knows about the selected astronaut."""
        member = self._member
        if member is None:
            return {}

        records = self._store.for_astronaut(member.name) if self._store else []
        summary = biomarkers.summary(member.name, self._grouped)
        stats = self._store.stats(member.name) if self._store else {}

        markers = {}
        for label, values in summary["markers"].items():
            markers[label] = {
                key: value for key, value in values.items() if key != "series"
            }
            markers[label]["series"] = [
                [int(day), float(value)] for day, value in values["series"]
            ]

        return {
            "destination": "Cimon",
            "transport": "console only - nothing is transmitted",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "astronaut": {
                "name": member.name,
                "station": member.craft,
                "dataset_name": summary["dataset_name"],
                "biomarkers_found": summary["found"],
            },
            "neuro_games": {
                "sessions": stats.get("sessions", 0),
                "best_accuracy": stats.get("best_accuracy"),
                "latest_accuracy": stats.get("latest_accuracy"),
                "mean_rt_ms": stats.get("mean_rt"),
                "latest_throughput_per_min": stats.get("latest_throughput"),
                "last_played": stats.get("last_played"),
                "history": records,
            },
            "biomarkers": {
                "samples": summary["samples"],
                "clinical_status": summary.get("status"),
                "anomaly": summary.get("anomaly"),
                "first_flagged_day": summary.get("flagged_day"),
                "markers": markers,
            },
        }

    def print_data(self) -> str:
        """The dead button: builds the payload and prints it. No network."""
        payload = self.build_payload()
        if not payload:
            self.send_note.setText("nothing to print - select a crew member first")
            return ""

        text = json.dumps(payload, indent=2)
        print(f"\n===== NeuroSpartan >> Cimon  (printed only, not sent) =====\n{text}")

        games = payload["neuro_games"]["sessions"]
        samples = payload["biomarkers"]["samples"]
        name = payload["astronaut"]["name"]
        self.send_note.setText(
            f"Sent {name}: {games} game sessions, {samples} marker samples "
        )
        return text

    # --------------------------------------------------------------- charts
    def _view(self, title: str) -> QChartView:
        chart = QChart()
        chart.setTitle(title)
        chart.setMargins(QMargins(8, 8, 8, 8))
        chart.legend().setVisible(False)
        chart.setAnimationOptions(QChart.NoAnimation)
        chart.setBackgroundBrush(QColor("#ffffff"))
        view = QChartView(chart)
        view.setRenderHint(QPainter.Antialiasing)
        view.setMinimumHeight(150)
        return view

    def _reset(self, view: QChartView, title: str) -> QChart:
        chart = view.chart()
        chart.removeAllSeries()
        for axis in list(chart.axes()):
            chart.removeAxis(axis)
        chart.setTitle(title)
        return chart

    def _empty(self, view: QChartView, title: str, message: str = "") -> None:
        chart = self._reset(view, title)
        series = QLineSeries()
        series.append(QPointF(0, 0))
        series.append(QPointF(1, 1))
        series.setName(message or "no data")
        chart.addSeries(series)

        axis_x = QValueAxis()
        axis_x.setRange(0, 1)
        axis_x.setVisible(False)
        axis_y = QValueAxis()
        axis_y.setRange(0, 1)
        axis_y.setVisible(False)
        chart.addAxis(axis_x, Qt.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)
        chart.legend().setVisible(bool(message))

    def _axes(self, chart: QChart, xs: list[float], ys: list[float],
              fixed_low: float | None, fixed_high: float | None):
        axis_x = QValueAxis()
        if xs:
            axis_x.setRange(min(xs), max(xs))
        else:
            axis_x.setRange(0, 1)
        axis_y = QValueAxis()
        if ys:
            axis_y.setRange(fixed_low if fixed_low is not None else 0.0,
                            fixed_high if fixed_high is not None else max(ys) * 1.15)
        else:
            axis_y.setRange(0, 1)
        for axis in (axis_x, axis_y):
            axis.setLabelsColor(MUTED)
            axis.setGridLineColor(GRID)
        chart.addAxis(axis_x, Qt.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignLeft)
        return axis_x, axis_y

    def _series(self, name: str, points: list[tuple[int, float]], colour: QColor) -> QLineSeries:
        series = QLineSeries()
        for x, y in points:
            series.append(QPointF(x, y))
        series.setName(name)
        pen = QPen(colour)
        pen.setWidth(2)
        series.setPen(pen)
        return series

    def _trend(self, view: QChartView, title: str, points: list[tuple[int, float]],
               colour: QColor, fixed_low: float | None = None,
               fixed_high: float | None = None) -> None:
        chart = self._reset(view, title)
        series = self._series(title.split(" ")[0], points, colour)
        chart.addSeries(series)
        axis_x, axis_y = self._axes(
            chart, [p[0] for p in points], [p[1] for p in points], fixed_low, fixed_high)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)
        chart.legend().setVisible(False)

    def _two_lines(self, view: QChartView, title: str,
                   lines: list[tuple[str, list[tuple[int, float]], QColor]]) -> None:
        chart = self._reset(view, title)
        xs = [p[0] for _, points, _ in lines for p in points]
        ys = [p[1] for _, points, _ in lines for p in points]
        axis_x, axis_y = self._axes(chart, xs, ys, None, None)
        for name, points, colour in lines:
            series = self._series(name, points, colour)
            chart.addSeries(series)
            series.attachAxis(axis_x)
            series.attachAxis(axis_y)
        chart.legend().setVisible(True)
        chart.legend().setLabelColor(INK)
