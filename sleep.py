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
from datetime import datetime, timedelta

from PySide6 import QtCore, QtGui, QtWidgets


Qt = QtCore.Qt

STAGES = ["Awake", "REM", "Light", "Deep"]  # top to bottom on the chart
ONE_HOUR = timedelta(hours=1)               # hour grid step on the chart

# Explicit colours, same palette as the other tabs. Nothing here reads the
# widget palette: QPalette.WindowText resolves to white in this app, which
# made every label on this page invisible against the light background.
INK = "#151a21"          # primary text
MUTED = "#5a6779"        # secondary text (>=4.5:1 on white)
FAINT = "#5c6b7f"        # captions (>=4.5:1 on white)
GRID = "#e2e8ef"         # chart grid lines
PANEL_BG = "#ffffff"
PANEL_BORDER = "#dde4ec"
STAGE_COLORS = {
    "Awake": "#e4572e",
    "REM": "#a45ee5",
    "Light": "#4aa3df",
    "Deep": "#2a4bb5",
}
# the shared data folder, not next to this file
DEFAULT_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "server", "sleep_data.json")


# --------------------------------------------------------------------------- data
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


def load_sleepers(path):
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


# --------------------------------------------------------------------------- chart
class HypnogramWidget(QtWidgets.QWidget):
    """Paints the sleep stages of one Sleeper as a stepped timeline."""

    MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 66, 28, 16, 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sleeper = None
        self.setMinimumHeight(240)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        # styled background so the QSS below is actually painted by Qt
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"background: {PANEL_BG}; border: 1px solid {PANEL_BORDER}; border-radius: 6px;")

    def set_sleeper(self, sleeper):
        self.sleeper = sleeper
        self.update()

    # -- geometry helpers
    def _axis(self):
        """Plot time range, rounded outward to whole hours."""
        s = self.sleeper
        t0 = s.start.replace(minute=0, second=0, microsecond=0)
        t1 = s.end.replace(minute=0, second=0, microsecond=0)
        if t1 < s.end:                       # end mid-hour -> show the whole hour
            t1 = t1 + ONE_HOUR
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
        text_col = QtGui.QColor(INK)
        muted_col = QtGui.QColor(MUTED)
        grid_col = QtGui.QColor(GRID)

        if self.sleeper is None or self.sleeper.start is None:
            p.setPen(muted_col)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No sleep data")
            return

        s = self.sleeper
        rect = self._plot_rect()
        t0, t1 = self._axis()
        row_h = rect.height() / len(STAGES)

        # row guides and stage labels
        axis_font = QtGui.QFont(self.font())
        axis_font.setPointSizeF(max(7.0, axis_font.pointSizeF() * 0.85))
        p.setFont(axis_font)
        for i, st in enumerate(STAGES):
            y = rect.top() + i * row_h
            p.setPen(QtGui.QPen(grid_col, 1))
            p.drawLine(QtCore.QPointF(rect.left(), y + row_h), QtCore.QPointF(rect.right(), y + row_h))
            p.setPen(muted_col)
            p.drawText(
                QtCore.QRectF(0, y, self.MARGIN_L - 10, row_h),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                st,
            )

        # hour ticks
        total_h = max(1, int((t1 - t0).total_seconds() // 3600))
        step = 1 if rect.width() / total_h > 46 else 2
        for h in range(0, total_h + 1, step):
            t = t0 + ONE_HOUR * h
            x = self._x(t, t0, t1, rect)
            p.setPen(QtGui.QPen(grid_col, 1))
            p.drawLine(QtCore.QPointF(x, rect.top()), QtCore.QPointF(x, rect.bottom()))
            p.setPen(muted_col)
            p.drawText(
                QtCore.QRectF(x - 24, rect.bottom() + 6, 48, 18),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                t.strftime("%H:%M"),
            )

        # connectors between consecutive stages
        conn = QtGui.QColor(MUTED)
        conn.setAlpha(120)
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
        if self.sleeper is None or self.sleeper.start is None:
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
        self.name.setStyleSheet(f"color: {INK}; font-size: 12px;")
        self.time = QtWidgets.QLabel()
        self.time.setMinimumWidth(70)
        self.time.setStyleSheet(f"color: {MUTED}; font-family: Consolas, monospace; font-size: 12px;")
        self.bar = QtWidgets.QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setStyleSheet(
            "QProgressBar{border:none;border-radius:4px;background:#e9edf2;}"
            f"QProgressBar::chunk{{border-radius:4px;background:{STAGE_COLORS[stage]};}}"
        )
        self.pct = QtWidgets.QLabel()
        self.pct.setMinimumWidth(40)
        self.pct.setStyleSheet(f"color: {INK}; font-family: Consolas, monospace; font-size: 12px;")
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

    selection_changed = QtCore.Signal(str)

    def __init__(self, json_path=None, parent=None):
        """json_path=None means "the app will hand me the data" (set_data()).

        Passing a path makes the page read it itself, which is what the
        standalone preview at the bottom of this file does.
        """
        super().__init__(parent)
        self.json_path = json_path
        self.date = ""
        self.sleepers = []
        self._current = None
        self._build_ui()
        if json_path:
            self.load(json_path)

    # -- UI
    def _build_ui(self):
        d = QtWidgets.QVBoxLayout(self)
        d.setContentsMargins(0, 0, 0, 0)
        d.setSpacing(12)

        self.night = QtWidgets.QLabel()
        self.night.setStyleSheet(
            f"color: {FAINT}; font-family: Consolas, monospace;"
            f"font-size: 11px; letter-spacing: 2px;")

        self.title = QtWidgets.QLabel()
        self.title.setStyleSheet(f"color: {INK}; font-size: 21px; font-weight: 600;")

        self.span = QtWidgets.QLabel()
        self.span.setStyleSheet(f"color: {MUTED}; font-size: 12.5px;")

        d.addWidget(self.night)
        d.addWidget(self.title)
        d.addWidget(self.span)

        # totals in the same card style the other tabs use
        card = QtWidgets.QFrame()
        card.setObjectName("Placeholder")          # styled by theme.py
        card_row = QtWidgets.QHBoxLayout(card)
        card_row.setContentsMargins(16, 12, 16, 12)
        card_row.setSpacing(34)

        self.stat_labels = {}
        for key, caption in (("in_bed", "IN BED"), ("asleep", "ASLEEP"), ("eff", "EFFICIENCY")):
            box = QtWidgets.QVBoxLayout()
            box.setSpacing(2)
            cap = QtWidgets.QLabel(caption)
            cap.setStyleSheet(
                f"color: {FAINT}; font-size: 10px; font-weight: 600; letter-spacing: 1px;")
            val = QtWidgets.QLabel("-")
            val.setStyleSheet(f"color: {INK}; font-family: Consolas, monospace; font-size: 19px;")
            box.addWidget(cap)
            box.addWidget(val)
            card_row.addLayout(box)
            self.stat_labels[key] = val
        card_row.addStretch(1)
        d.addWidget(card)

        self.chart = HypnogramWidget()
        d.addWidget(self.chart, 1)

        rows_card = QtWidgets.QFrame()
        rows_card.setObjectName("Placeholder")
        rows_box = QtWidgets.QVBoxLayout(rows_card)
        rows_box.setContentsMargins(16, 12, 16, 12)
        rows_box.setSpacing(8)

        self.rows = {}
        for st in STAGES:
            row = StageRow(st)
            self.rows[st] = row
            rows_box.addWidget(row)
        d.addWidget(rows_card)

    # -- data
    def set_data(self, date, sleepers):
        """Receive already-parsed data. The page reads no file of its own."""
        previous = self._current.name if self._current else None
        self.date = date
        self.sleepers = list(sleepers)
        names = self.astronaut_names()
        if names:
            self.show_astronaut(previous if previous in names else names[0])
        else:
            self._current = None
            self.chart.set_sleeper(None)

    def load(self, path):
        """Standalone helper: read the file and pass it to set_data()."""
        self.json_path = path
        self.set_data(*load_sleepers(path))

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
        self.chart.set_sleeper(s)

        if s.start is None or not s.in_bed:
            self.span.setText("no usable segments in the sleep file")
            for key in ("in_bed", "asleep", "eff"):
                self.stat_labels[key].setText("-")
            for row_w in self.rows.values():
                row_w.set_values(0.0, 0.0)
            self.selection_changed.emit(s.name)
            return

        self.span.setText(f"Asleep from {s.start:%H:%M} to {s.end:%H:%M}")
        self.stat_labels["in_bed"].setText(fmt_dur(s.in_bed))
        self.stat_labels["asleep"].setText(fmt_dur(s.asleep))
        self.stat_labels["eff"].setText(f"{s.asleep / s.in_bed * 100:.0f}%")
        for st, row_w in self.rows.items():
            row_w.set_values(s.minutes[st], s.in_bed)
        self.selection_changed.emit(s.name)


# --------------------------------------------------------------------------- standalone preview
if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    # Demo only: a stand-in sidebar. In the real application your own sidebar
    # calls page.show_astronaut(name).
    page = SleepPage(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_JSON)
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