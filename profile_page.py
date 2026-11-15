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

from datetime import datetime

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import QMargins, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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

        self.counters = QLabel("")
        self.counters.setObjectName("Hint")
        self.counters.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        card_row.addWidget(self.counters)
        root.addWidget(card)

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
            return

        self.avatar.setText(initials(member.name))
        self.name.setText(member.name)
        self.station.setText(f"station: {member.craft}")

        records = self._store.for_astronaut(member.name) if self._store else []
        summary = biomarkers.summary(member.name, self._grouped)
        stats = self._store.stats(member.name) if self._store else {}

        self.record_note.setText(
            f"dataset name: {summary['dataset_name']}" if summary["found"]
            else "no biomarker records for this crew member"
        )
        self.counters.setText(
            f"sessions: {stats.get('sessions', 0)}<br>"
            f"last played: {pretty_timestamp(stats.get('last_played'))}<br>"
            f"marker samples: {summary['samples']}"
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
