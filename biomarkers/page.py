"""Biomarkers tab: live crew names from Open-Notify, charts from the static file.

Names are never hardcoded - set_crew() receives the people the window fetched,
and every lookup goes through biomarkers.resolve_crew_name(). If the crew
rotates, this tab follows automatically; a crew member with no records in the
static file is shown as such rather than silently skipped.

Charts (QtCharts, ships inside PySide6):
    1. NFL_pg_mL     per flight day
    2. GFAP_pg_mL    per flight day
    3. Ab40_pg_mL    per flight day
    4. morning vs evening mean, per marker
    5. normalised slope across the whole live crew
Points marked "Elevated Risk (SANS)" are drawn on top of each trend line.
"""

from __future__ import annotations

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QLineSeries,
    QScatterSeries,
    QValueAxis,
)
from PySide6.QtCore import Qt, QMargins, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from crew import Astronaut
from . import analysis as biomarkers

INK = QColor("#151a21")
MUTED = QColor("#6b7787")
BLUE = QColor("#2f6fdb")
RED = QColor("#dd3b28")
AMBER = QColor("#c9821b")
GREEN = QColor("#1d9d6f")
GRID = QColor("#e2e8ef")

MARKER_COLOURS = {"NFL": BLUE, "GFAP": AMBER, "Abeta40": GREEN}


class BiomarkersPage(QWidget):
    """Pick a live crew member, see every statistic plotted."""

    # the file is owned by MainWindow; this only asks it to re-read on demand
    reload_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._grouped: dict[str, list[dict]] = {}
        self._members: list[Astronaut] = []
        self._load_error: str | None = None
        self._pending: str | None = None   # crew name chosen before names arrived

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # --- heading -------------------------------------------------------
        heading = QLabel("Biomarkers  -  NFL, GFAP and Abeta-40")
        heading.setObjectName("PageTitle")
        root.addWidget(heading)

        blurb = QLabel(
            "Blood-brain-barrier markers measured twice a day."
        )
        blurb.setObjectName("Hint")
        blurb.setWordWrap(True)
        root.addWidget(blurb)

        # --- crew picker: driven entirely by the live API ------------------
        row = QHBoxLayout()
        label = QLabel("Crew member")
        label.setStyleSheet("color: #333; font-weight: bold; padding: 4px;")
        row.addWidget(label)

        self.picker = QComboBox()
        self.picker.setMinimumWidth(260)
        self.picker.currentIndexChanged.connect(self._show_selected)
        row.addWidget(self.picker, 1)

        self.reload = QPushButton("Reload data")
        self.reload.clicked.connect(self.reload_requested.emit)
        row.addWidget(self.reload)

        self.status = QLabel("waiting for the crew list")
        self.status.setObjectName("Hint")
        row.addWidget(self.status)
        root.addLayout(row)

        # --- charts --------------------------------------------------------
        grid = QGridLayout()
        grid.setSpacing(10)
        self.views: dict[str, QChartView] = {}

        for column, (key, name) in enumerate(
            (("NFL", "NFL_pg_mL"), ("GFAP", "GFAP_pg_mL"), ("Abeta40", "Ab40_pg_mL"))
        ):
            view = self._make_view(f"{name}  per flight day")
            self.views[key] = view
            grid.addWidget(view, 0, column)

        self.views["MORNING"] = self._make_view("Morning vs Evening mean")
        grid.addWidget(self.views["MORNING"], 1, 0)
        self.views["SLOPE"] = self._make_view("Normalised slope, whole crew")
        grid.addWidget(self.views["SLOPE"], 1, 1, 1, 2)

        root.addLayout(grid, 1)

        # data arrives from MainWindow via set_biomarkers(); this page reads no
        # files itself, so it starts in an explicitly empty state.
        self._show_selected()

    # -------------------------------------------------------------- loading
    def set_biomarkers(self, grouped: dict[str, list[dict]],
                       error: str | None = None) -> None:
        """Receive the parsed dataset. This page never reads the file itself."""
        self._grouped = grouped
        self._load_error = error

        records = sum(len(v) for v in self._grouped.values())
        self._show_selected()

    # ------------------------------------------------------------ live crew
    def set_crew(self, crew) -> None:
        """Receive the people currently in space from the window's fetch."""
        self._members = list(getattr(crew, "members", []))
        wanted = self._pending or self.picker.currentData()

        self.picker.blockSignals(True)
        self.picker.clear()
        for index, member in enumerate(self._members):
            self.picker.addItem(f"{member.name}  ({member.craft})", member.name)
            if member.name == wanted:
                self.picker.setCurrentIndex(index)
        self.picker.blockSignals(False)

        if not self._members:
            self.status.setText("no crew returned by the API")
        self._pending = None
        self._show_selected()

    def select_astronaut(self, api_name: str) -> None:
        """Follow the crew selection made in the left rail."""
        for index in range(self.picker.count()):
            if self.picker.itemData(index) == api_name:
                self.picker.setCurrentIndex(index)
                return
        # Names may not have arrived yet - remember it and apply on set_crew().
        self._pending = api_name

    def show_error(self, message: str) -> None:
        self.status.setText(f"crew lookup failed: {message}")

    # ------------------------------------------------------------- painting
    def _make_view(self, title: str) -> QChartView:
        chart = QChart()
        chart.setTitle(title)
        chart.setMargins(QMargins(8, 8, 8, 8))
        chart.legend().setVisible(True)
        chart.legend().setLabelColor(INK)
        chart.setAnimationOptions(QChart.NoAnimation)
        chart.setBackgroundBrush(QColor("#ffffff"))
        view = QChartView(chart)
        view.setRenderHint(QPainter.Antialiasing)
        view.setMinimumSize(300, 190)
        return view

    def _reset(self, view: QChartView, title: str) -> QChart:
        view.chart().removeAllSeries()
        for axis in list(view.chart().axes()):
            view.chart().removeAxis(axis)
        view.chart().setTitle(title)
        return view.chart()

    def _show_selected(self) -> None:
        name = self.picker.currentData()

        if self._load_error:
            self.status.setText("data file could not be read")
            for key in self.views:
                self._empty(key, self._title_for(key), self._load_error)
            return

        if not name:
            self.status.setText("no crew selected")
            for key in self.views:
                self._empty(key, self._title_for(key), "waiting for the crew list")
            return

        record = biomarkers.summary(name, self._grouped)
        if not record["found"]:
            self.status.setText(f"{name} has no records in the biomarker file")
            for key in self.views:
                self._empty(key, self._title_for(key), "no data for this crew member")
            return

        onset = record["flagged_day"]
        self.status.setText(
            f"matched to '{record['dataset_name']}'  -  {record['samples']} samples  -  "
            f"{record['status']}"
            + (f"  -  onset day {onset}" if onset else "")
            + (f"  ({record['anomaly']})" if record["anomaly"] not in ("None", "") else "")
        )

        for key in ("NFL", "GFAP", "Abeta40"):
            self._plot_marker(key, name, record)
        self._plot_morning_evening(name, record)
        self._plot_crew_slopes(name)

    def _title_for(self, key: str) -> str:
        return {
            "NFL": "NFL_pg_mL  per flight day",
            "GFAP": "GFAP_pg_mL  per flight day",
            "Abeta40": "Ab40_pg_mL  per flight day",
            "MORNING": "Morning vs Evening mean",
            "SLOPE": "Normalised slope, whole crew",
        }[key]

    def _empty(self, key: str, title: str, message: str) -> None:
        chart = self._reset(self.views[key], title)
        series = QLineSeries()
        series.append(QPointF(0, 0))
        series.append(QPointF(1, 1))
        series.setName(message)
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
        chart.legend().setVisible(True)

    def _plot_marker(self, key: str, astronaut: str, record: dict) -> None:
        stats = record["markers"][key]
        points: list[tuple[int, float]] = stats["series"]
        colour = MARKER_COLOURS.get(key, BLUE)

        chart = self._reset(
            self.views[key],
            f"{key}  -  {astronaut.split()[-1]}",
        )

        line = QLineSeries()
        for day, value in points:
            line.append(QPointF(day, value))
        # legend carries the numbers so the title stays on one line
        line.setName(
            f"{key}   slope {stats['slope_per_day']:+.3f}/day   "
            f"normalised {stats['normalised_slope']:+.3f}"
            + ("   [FLAG]" if stats["flagged"] else "")
        )
        pen = QPen(colour)
        pen.setWidth(2)
        line.setPen(pen)
        chart.addSeries(line)

        # the anomalous readings, drawn on top of the trend
        flagged = QScatterSeries()
        flagged.setName("Elevated Risk (SANS)")
        flagged.setMarkerSize(7)
        flagged.setColor(RED)
        flagged.setBorderColor(RED)
        for sample in self._samples_for(astronaut):
            if sample.get("Clinical_Status") != "Normal":
                flagged.append(QPointF(sample["Day_in_Space"], sample[self._json_key(key)]))
        chart.addSeries(flagged)

        axis_x = QValueAxis()
        axis_x.setTitleText("flight day")
        chart.addAxis(axis_x, Qt.AlignBottom)
        axis_y = QValueAxis()
        axis_y.setTitleText("pg/ml")
        chart.addAxis(axis_y, Qt.AlignLeft)
        line.attachAxis(axis_x)
        line.attachAxis(axis_y)
        flagged.attachAxis(axis_x)
        flagged.attachAxis(axis_y)

        values = [v for _, v in points]
        axis_x.setRange(min(p[0] for p in points), max(p[0] for p in points))
        axis_y.setRange(0, max(values) * 1.15)
        for axis in (axis_x, axis_y):
            axis.setGridLineColor(GRID)
            axis.setLabelsColor(MUTED)
            axis.setTitleVisible(False)
        chart.legend().setVisible(True)

    def _plot_morning_evening(self, astronaut: str, record: dict) -> None:
        means: dict[str, tuple[float, float]] = record["morning_evening"]
        chart = self._reset(self.views["MORNING"], f"Morning vs Evening  -  {astronaut}")

        morning = QBarSet("Morning")
        evening = QBarSet("Evening")
        morning.setColor(BLUE)
        evening.setColor(AMBER)
        for key in MARKER_COLOURS:
            morning << means[key][0]
            evening << means[key][1]

        series = QBarSeries()
        series.append(morning)
        series.append(evening)
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(list(MARKER_COLOURS.keys()))
        chart.addAxis(axis_x, Qt.AlignBottom)
        axis_y = QValueAxis()
        axis_y.setRange(0, max(max(pair) for pair in means.values()) * 1.2)
        axis_y.setTitleText("pg/ml")
        chart.addAxis(axis_y, Qt.AlignLeft)
        chart.axisX().setLabelsColor(MUTED)
        axis_y.setGridLineColor(GRID)
        axis_y.setLabelsColor(MUTED)
        chart.legend().setVisible(True)

    def _plot_crew_slopes(self, selected: str) -> None:
        """Every live crew member's normalised slope - the comparison view."""
        chart = self._reset(self.views["SLOPE"],
                           "Normalised slope (baseline SD per day) by marker")

        sets: dict[str, QBarSet] = {}
        for key in ("NFL", "GFAP", "Abeta40"):
            bar = QBarSet(key)
            bar.setColor(MARKER_COLOURS[key])
            sets[key] = bar

        labels: list[str] = []
        for member in self._members:
            record = biomarkers.summary(member.name, self._grouped)
            if not record["found"]:
                continue
            surname = member.name.split()[-1]
            labels.append(surname if member.name != selected else f"* {surname}")
            for key in ("NFL", "GFAP", "Abeta40"):
                sets[key] << record["markers"][key]["normalised_slope"]

        if not labels:
            self._empty("SLOPE", self._title_for("SLOPE"), "no overlapping crew")
            return

        series = QBarSeries()
        for key in ("NFL", "GFAP", "Abeta40"):
            series.append(sets[key])
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(labels)
        chart.addAxis(axis_x, Qt.AlignBottom)
        axis_y = QValueAxis()
        axis_y.setTitleText("normalised slope")
        chart.addAxis(axis_y, Qt.AlignLeft)
        axis_y.setGridLineColor(GRID)
        axis_y.setLabelsColor(MUTED)
        axis_x.setLabelsColor(MUTED)
        chart.legend().setVisible(True)

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _json_key(label: str) -> str:
        for key, name in biomarkers.MARKERS.items():
            if name == label:
                return key
        return label

    def _samples_for(self, astronaut: str) -> list[dict]:
        resolved = biomarkers.resolve_crew_name(astronaut, self._grouped)
        return self._grouped.get(resolved, []) if resolved else []
