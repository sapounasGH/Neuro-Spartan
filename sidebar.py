"""Left crew bar: expands/collapses with a toggle button, lists the crew."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from crew import Crew

EXPANDED_WIDTH = 232
COLLAPSED_WIDTH = 54


class CrewSidebar(QFrame):
    """Left bar: expands/collapses with the toggle button, lists the crew."""

    astronaut_selected = Signal(object)  # Astronaut

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(EXPANDED_WIDTH)
        self._expanded = True
        self._crew: Crew | None = None
        self._selected_name: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 10, 8, 10)
        root.setSpacing(6)

        # --- top row: brand mark + toggle button ---------------------------
        header = QHBoxLayout()
        header.setSpacing(8)

        mark = QLabel("NS")
        mark.setObjectName("BrandMark")
        mark.setFixedSize(24, 24)
        mark.setAlignment(Qt.AlignCenter)
        header.addWidget(mark)

        self.brand = QLabel("NEUROSPARTAN")
        self.brand.setObjectName("Brand")
        self.brand.setTextInteractionFlags(Qt.TextSelectableByMouse)
        header.addWidget(self.brand, 1)

        self.toggle = QPushButton("\N{LEFT-POINTING DOUBLE ANGLE QUOTATION MARK}")
        self.toggle.setObjectName("Toggle")
        self.toggle.setFixedSize(28, 26)
        self.toggle.setCursor(Qt.PointingHandCursor)
        self.toggle.setToolTip("Collapse panel")
        self.toggle.clicked.connect(self.toggle_expanded)
        header.addWidget(self.toggle)
        root.addLayout(header)

        # --- crew section --------------------------------------------------
        self.section = QLabel("MISSION CREW")
        self.section.setObjectName("Section")
        self.section.setIndent(8)
        root.addWidget(self.section)

        self.count = QLabel("connecting\N{HORIZONTAL ELLIPSIS}")
        self.count.setObjectName("Count")
        self.count.setIndent(8)
        self.count.setWordWrap(True)
        root.addWidget(self.count)

        self.crew_list = QListWidget()
        self.crew_list.setObjectName("CrewList")
        self.crew_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.crew_list.setFrameShape(QFrame.NoFrame)
        self.crew_list.itemSelectionChanged.connect(self._emit_selection)
        root.addWidget(self.crew_list, 1)

        # --- bottom row: status + refresh ---------------------------------
        self.status = QLabel("")
        self.status.setObjectName("Status")
        self.status.setIndent(8)
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self.refresh = QPushButton("Refresh")
        self.refresh.setCursor(Qt.PointingHandCursor)
        self.refresh.clicked.connect(self.reload)
        root.addWidget(self.refresh)

    # ------------------------------------------------------------------ width
    def toggle_expanded(self) -> None:
        """Grow/shrink the bar. Labels hide so the icon row stays readable."""
        self._expanded = not self._expanded
        self.setFixedWidth(EXPANDED_WIDTH if self._expanded else COLLAPSED_WIDTH)

        arrow = "\N{LEFT-POINTING DOUBLE ANGLE QUOTATION MARK}" if self._expanded else "\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}"
        self.toggle.setText(arrow)
        self.toggle.setToolTip("Collapse panel" if self._expanded else "Expand panel")

        for widget in (self.brand, self.section, self.count, self.status):
            widget.setVisible(self._expanded)
        self.refresh.setText("Refresh" if self._expanded else "R")

    # ------------------------------------------------------------------- data
    def set_loading(self) -> None:
        # Remember who is selected BEFORE clearing, because clear() destroys the
        # current item and the selection would otherwise be lost to refresh().
        current = self.crew_list.currentItem()
        if current is not None:
            chosen = current.data(Qt.UserRole)
            if chosen is not None:
                self._selected_name = chosen.name

        self.count.setText("connecting\N{HORIZONTAL ELLIPSIS}")
        self.status.setText("")
        self.status.setProperty("state", "")
        self.crew_list.clear()
        self.crew_list.setEnabled(False)
        self.refresh.setEnabled(False)

    def show_crew(self, crew: Crew) -> None:
        # Open-Notify does not guarantee the order of its people list, so sort
        # for a stable list and restore the selection by name rather than by
        # index - otherwise every refresh snaps to whoever sorts first.
        previous = self._selected_name

        self._crew = crew
        self.crew_list.setEnabled(True)
        self.refresh.setEnabled(True)
        self.count.setText(f"{crew.total} people in space right now")

        members = sorted(crew.members, key=lambda m: (m.craft, m.name))
        self.crew_list.clear()
        for member in members:
            item = QListWidgetItem(str(member))  # "Name (craft)"
            item.setData(Qt.UserRole, member)
            item.setToolTip(f"{member.name}\naboard {member.craft}")
            self.crew_list.addItem(item)

        crafts = " · ".join(crew.crafts())
        self.status.setText(f"{len(crew.members)} loaded from Open-Notify\n{crafts}")
        self.status.setProperty("state", "")

        index = 0
        if previous:
            for position, member in enumerate(members):
                if member.name == previous:
                    index = position
                    break
        self.crew_list.setCurrentRow(index)

    def show_error(self, message: str) -> None:
        self.refresh.setEnabled(True)
        self.crew_list.setEnabled(True)
        self.count.setText("crew unavailable")
        self.status.setText(f"{message}\nUse Refresh to retry.")
        self.status.setProperty("state", "error")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def reload(self) -> None:
        """Kick off a fetch. The window owns the worker lifetime."""
        self.window().load_crew()  # type: ignore[union-attr]

    # -------------------------------------------------------------- selection
    def _emit_selection(self) -> None:
        current = self.crew_list.currentItem()
        if current is not None:
            member = current.data(Qt.UserRole)
            if member is not None:
                self._selected_name = member.name
            self.astronaut_selected.emit(member)
