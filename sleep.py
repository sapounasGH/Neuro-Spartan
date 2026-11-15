"""sleep_page.py - "Sleep" tab for a Qt application.

Usage in the main application:

    from sleep_page import SleepPage

    self.sleep = SleepPage()                      # reads sleep_data.json next to this file
    self.sleep = SleepPage("path/to/other.json")  # or an explicit file
    tabs.addTab(self.sleep, "Sleep")

    names = self.sleep.astronaut_names()          # to fill your sidebar
    sidebar.currentTextChanged.connect(self.sleep.show_astronaut)

show_astronaut(name) shows that astronaut's sleep diagram (hypnogram), totals and
stage breakdown. The JSON file is only read, never modified.

Supported JSON layouts:
    {"date": ..., "people": [{"person": ..., "segments": [...]}, ...]}
    {"person": ..., "date": ..., "segments": [...]}          (single person)
Each segment: {"start": "YYYY-MM-DDTHH:MM", "end": "...", "stage": "Awake|REM|Light|Deep"}

"""
import json
import os
from datetime import datetime

import PySide6 as QtCore
import PySide6.QtWidgets as QtWidgets, PySide6.QtGui as QtGui


Qt = QtCore.Qt

STAGES = ["Awake", "REM", "Light", "Deep"]  # top to bottom on the chart
STAGE_COLORS = {
    "Awake": "#e4572e",
    "REM": "#a45ee5",
    "Light": "#4aa3df",
    "Deep": "#2a4bb5",
}
DEFAULT_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sleep_data.json")


# --------------------------------------------------------------------------- data
class Sleeper:
    """One astronaut's night, parsed from JSON."""

    def __init__(self, name, segments):
        self.name = name
        self.segments = sorted(
            (
                (datetime.fromisoformat(s["start"]), datetime.fromisoformat(s["end"]), s["stage"])
                for s in segments
            ),
            key=lambda s: s[0],
        )
        self.minutes = {st: 0.0 for st in STAGES}
        for a, b, st in self.segments:
            self.minutes[st] = self.minutes.get(st, 0.0) + (b - a).total_seconds() / 60
        self.start = self.segments[0][0]
        self.end = self.segments[-1][1]
        self.in_bed = (self.end - self.start).total_seconds() / 60
        self.asleep = self.in_bed - self.minutes["Awake"]


def load_sleepers(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "people" in data:
        people = [Sleeper(p["person"], p["segments"]) for p in data["people"]]
    else:
        people = [Sleeper(data.get("person", "Unknown"), data["segments"])]
    return data.get("date", ""), people


def fmt_dur(minutes):
    minutes = int(round(minutes))
    return f"{minutes // 60}h {minutes % 60:02d}m"


# --------------------------------------------------------------------------- chart
class HypnogramWidget(QtWidgets.QWidget):
    """Paints the sleep stages of one Sleeper as a stepped timeline."""

    MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 62, 28, 10, 28

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sleeper = None
        self.setMinimumHeight(230)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    def set_sleeper(self, sleeper):
        self.sleeper = sleeper
        self.update()

    # -- geometry helpers
    def _axis(self):
        s = self.sleeper
        t0 = s.start.replace(minute=0, second=0, microsecond=0)
        t1 = s.end.replace(minute=0, second=0, microsecond=0)
        if t1 < s.end:
            t1 = t1.replace() + (datetime(2000, 1, 1, 1) - datetime(2000, 1, 1))
        return t0, t1

    def _plot_rect(self):
        return QtCore.QRectF(
            self.MARGIN_L, self.MARGIN_T,
            max(10, self.width() - self.MARGIN_L - self.MARGIN_R),
            max(10, self.height() - self.MARGIN_T - self.MARGIN_B),
        )

    def _x(self, t, t0, t1, rect):
        span = (t1 - t0).total_seconds()
        return rect.left() + (t - t0).total_seconds() / span * rect.width()

    def _row_center(self, stage, rect):
        row_h = rect.height() / len(STAGES)
        return rect.top() + STAGES.index(stage) * row_h + row_h / 2

    # -- painting
    def paintEvent(self, _event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        text_col = pal.color(QtGui.QPalette.ColorRole.WindowText)
        grid_col = QtGui.QColor(text_col)
        grid_col.setAlpha(40)

        if self.sleeper is None:
            p.setPen(text_col)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No sleep data")
            return

        s = self.sleeper
        rect = self._plot_rect()
        t0, t1 = self._axis()
        row_h = rect.height() / len(STAGES)

        # row guides and stage labels
        p.setFont(self.font())
        for i, st in enumerate(STAGES):
            y = rect.top() + i * row_h
            p.setPen(QtGui.QPen(grid_col, 1))
            p.drawLine(QtCore.QPointF(rect.left(), y + row_h), QtCore.QPointF(rect.right(), y + row_h))
            p.setPen(text_col)
            p.drawText(
                QtCore.QRectF(0, y, self.MARGIN_L - 8, row_h),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                st,
            )

        # hour ticks
        total_h = max(1, int((t1 - t0).total_seconds() // 3600))
        step = 1 if rect.width() / total_h > 46 else 2
        for h in range(0, total_h + 1, step):
            t = t0 + (datetime(2000, 1, 1, 1) - datetime(2000, 1, 1)) * h
            x = self._x(t, t0, t1, rect)
            p.setPen(QtGui.QPen(grid_col, 1))
            p.drawLine(QtCore.QPointF(x, rect.top()), QtCore.QPointF(x, rect.bottom()))
            p.setPen(text_col)
            p.drawText(
                QtCore.QRectF(x - 24, rect.bottom() + 4, 48, 18),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                t.strftime("%H:%M"),
            )

        # connectors between consecutive stages
        conn = QtGui.QColor(text_col)
        conn.setAlpha(110)
        p.setPen(QtGui.QPen(conn, 1))
        prev = None
        for a, b, st in s.segments:
            if prev is not None:
                x = self._x(a, t0, t1, rect)
                p.drawLine(
                    QtCore.QPointF(x, self._row_center(prev, rect)),
                    QtCore.QPointF(x, self._row_center(st, rect)),
                )
            prev = st

        # stage bars
        bar_h = min(18.0, row_h * 0.6)
        p.setPen(Qt.PenStyle.NoPen)
        for a, b, st in s.segments:
            x0, x1 = self._x(a, t0, t1, rect), self._x(b, t0, t1, rect)
            yc = self._row_center(st, rect)
            p.setBrush(QtGui.QColor(STAGE_COLORS[st]))
            p.drawRoundedRect(QtCore.QRectF(x0, yc - bar_h / 2, max(2.0, x1 - x0), bar_h), 3, 3)

    # -- hover tooltip
    def mouseMoveEvent(self, event):
        if self.sleeper is None:
            return
        pos = event.position() if hasattr(event, "position") else QtCore.QPointF(event.pos())
        rect = self._plot_rect()
        t0, t1 = self._axis()
        for a, b, st in self.sleeper.segments:
            x0, x1 = self._x(a, t0, t1, rect), self._x(b, t0, t1, rect)
            yc = self._row_center(st, rect)
            if x0 <= pos.x() <= max(x1, x0 + 2) and abs(pos.y() - yc) <= 12:
                mins = (b - a).total_seconds() / 60
                QtWidgets.QToolTip.showText(
                    event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos(),
                    f"{st}  {a:%H:%M}-{b:%H:%M}  ({mins:.0f} min)",
                    self,
                )
                return
        QtWidgets.QToolTip.hideText()


# --------------------------------------------------------------------------- stage legend row
class StageRow(QtWidgets.QWidget):
    def __init__(self, stage, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        swatch = QtWidgets.QLabel()
        swatch.setFixedSize(12, 12)
        swatch.setStyleSheet(f"background:{STAGE_COLORS[stage]}; border-radius:3px;")
        self.name = QtWidgets.QLabel(stage)
        self.name.setMinimumWidth(48)
        self.time = QtWidgets.QLabel()
        self.time.setMinimumWidth(70)
        self.bar = QtWidgets.QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setStyleSheet(
            "QProgressBar{border:none;border-radius:4px;background:rgba(128,128,128,60);}"
            f"QProgressBar::chunk{{border-radius:4px;background:{STAGE_COLORS[stage]};}}"
        )
        self.pct = QtWidgets.QLabel()
        self.pct.setMinimumWidth(40)
        self.pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        for w in (swatch, self.name, self.time):
            lay.addWidget(w)
        lay.addWidget(self.bar, 1)
        lay.addWidget(self.pct)

    def set_values(self, minutes, total):
        share = minutes / total if total else 0
        self.time.setText(fmt_dur(minutes))
        self.bar.setValue(int(share * 1000))
        self.pct.setText(f"{share * 100:.0f}%")


# --------------------------------------------------------------------------- the tab
class SleepPage(QtWidgets.QWidget):
    """Sidebar of astronauts + sleep diagram for the selected one."""

    selection_changed = QtCore.Signal(str) if hasattr(QtCore, "Signal") else QtCore.pyqtSignal(str)

    def __init__(self, json_path=None, parent=None):
        super().__init__(parent)
        self.json_path = json_path or DEFAULT_JSON
        self.date = ""
        self.sleepers = []
        self._current = None
        self._build_ui()
        self.load(self.json_path)

    # -- UI
    def _build_ui(self):
        d = QtWidgets.QVBoxLayout(self)
        d.setContentsMargins(20, 16, 20, 16)
        d.setSpacing(14)

        self.night = QtWidgets.QLabel()
        self.night.setStyleSheet("color: palette(mid);")
        self.title = QtWidgets.QLabel()
        tf = self.title.font()
        tf.setPointSizeF(tf.pointSizeF() * 1.7)
        tf.setBold(True)
        self.title.setFont(tf)
        self.span = QtWidgets.QLabel()
        self.span.setStyleSheet("color: palette(mid);")
        d.addWidget(self.night)
        d.addWidget(self.title)
        d.addWidget(self.span)

        stats = QtWidgets.QHBoxLayout()
        stats.setSpacing(28)
        self.stat_labels = {}
        for key, caption in (("in_bed", "IN BED"), ("asleep", "ASLEEP"), ("eff", "EFFICIENCY")):
            box = QtWidgets.QVBoxLayout()
            box.setSpacing(0)
            cap = QtWidgets.QLabel(caption)
            cf = cap.font()
            cf.setPointSizeF(cf.pointSizeF() * 0.8)
            cap.setFont(cf)
            cap.setStyleSheet("color: palette(mid);")
            val = QtWidgets.QLabel("-")
            vf = val.font()
            vf.setPointSizeF(vf.pointSizeF() * 1.6)
            val.setFont(vf)
            box.addWidget(cap)
            box.addWidget(val)
            stats.addLayout(box)
            self.stat_labels[key] = val
        stats.addStretch(1)
        d.addLayout(stats)

        self.chart = HypnogramWidget()
        d.addWidget(self.chart, 1)

        self.rows = {}
        for st in STAGES:
            row = StageRow(st)
            self.rows[st] = row
            d.addWidget(row)

    # -- data
    def load(self, path):
        """(Re)load the JSON file; keeps the current astronaut if still present."""
        previous = self._current.name if self._current else None
        self.json_path = path
        self.date, self.sleepers = load_sleepers(path)
        names = self.astronaut_names()
        if names:
            self.show_astronaut(previous if previous in names else names[0])
        else:
            self._current = None
            self.chart.set_sleeper(None)

    def astronaut_names(self):
        """Names in file order, e.g. to fill the application's sidebar."""
        return [s.name for s in self.sleepers]

    def current_name(self):
        return self._current.name if self._current else None

    def show_astronaut(self, name):
        """Show the sleep diagram for one astronaut. Unknown names are ignored."""
        for s in self.sleepers:
            if s.name == name:
                self._show(s)
                return

    def _show(self, s):
        self._current = s
        self.night.setText(f"NIGHT OF {self.date}" if self.date else "")
        self.title.setText(s.name)
        self.span.setText(f"Asleep from {s.start:%H:%M} to {s.end:%H:%M}")
        self.stat_labels["in_bed"].setText(fmt_dur(s.in_bed))
        self.stat_labels["asleep"].setText(fmt_dur(s.asleep))
        self.stat_labels["eff"].setText(f"{s.asleep / s.in_bed * 100:.0f}%")
        for st, row_w in self.rows.items():
            row_w.set_values(s.minutes[st], s.in_bed)
        self.chart.set_sleeper(s)
        self.selection_changed.emit(s.name)


# --------------------------------------------------------------------------- standalone preview
if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    # Demo only: a stand-in sidebar. In the real application your own sidebar
    # calls page.show_astronaut(name).
    page = SleepPage(sys.argv[1] if len(sys.argv) > 1 else None)
    demo = QtWidgets.QWidget()
    demo.setWindowTitle("Sleep (demo)")
    lay = QtWidgets.QHBoxLayout(demo)
    side = QtWidgets.QListWidget()
    side.setFixedWidth(200)
    side.addItems(page.astronaut_names())
    side.currentTextChanged.connect(page.show_astronaut)
    side.setCurrentRow(0)
    lay.addWidget(side)
    lay.addWidget(page, 1)
    demo.resize(1000, 640)
    demo.show()
    sys.exit(getattr(app, "exec", None) and app.exec() or app.exec_())