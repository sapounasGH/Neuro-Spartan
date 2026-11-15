"""Small widget that shows the live position of the ISS.

Data source: http://api.open-notify.org/iss-now.json
Polls every few seconds using Qt's non-blocking network stack, so the UI
never freezes while waiting for the API.
"""

from __future__ import annotations

import json

# Use whichever Qt binding is installed. If your app uses a specific one,
# delete the other branch so the two can never be mixed.

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

ISS_URL = "http://api.open-notify.org/iss-now.json"
REFRESH_MS = 10000
TIMEOUT_MS = 5000


class ISSWidget(QWidget):
    """Shows 'ISS  12.3456° N, 98.7654° W' and refreshes itself."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ISSWidget")

        self._title = QLabel("ISS POSITION")
        self._title.setObjectName("ISSTitle")

        self._value = QLabel("Locating…")
        self._value.setObjectName("ISSValue")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._title)
        layout.addWidget(self._value)

        self._manager = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(REFRESH_MS)

        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        # Skip if the previous request is still in flight.
        if self._reply is not None:
            return

        request = QNetworkRequest(QUrl(ISS_URL))
        request.setTransferTimeout(TIMEOUT_MS)
        self._reply = self._manager.get(request)
        self._reply.finished.connect(self._on_finished)

    def _on_finished(self) -> None:
        reply = self._reply
        self._reply = None
        if reply is None:
            return

        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self._show_error()
                return

            data = json.loads(bytes(reply.readAll()).decode("utf-8"))
            pos = data["iss_position"]
            self._show_position(float(pos["latitude"]), float(pos["longitude"]))
        except (ValueError, KeyError, TypeError):
            self._show_error()
        finally:
            reply.deleteLater()

    # ------------------------------------------------------------------
    def _show_position(self, lat: float, lon: float) -> None:
        ns = "N" if lat >= 0 else "S"
        ew = "E" if lon >= 0 else "W"
        self._value.setText(f"{abs(lat):.4f}° {ns},  {abs(lon):.4f}° {ew}")

    def _show_error(self) -> None:
        self._value.setText("Unavailable")