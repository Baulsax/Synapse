
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPen,
    QLinearGradient,
)
from PySide6.QtWidgets import QPushButton


def _format_download_size(size):
    size = max(0, int(size))

    if size >= 1024 ** 3:
        return f"{size / (1024 ** 3):.1f} GB"

    if size >= 1024 ** 2:
        return f"{size / (1024 ** 2):.1f} MB"

    if size >= 1024:
        return f"{size / 1024:.1f} KB"

    return f"{size} B"


class UpdateButton(QPushButton):
    """
    Update status control displayed beside the application version.

    States:
    - Up to date: muted checkmark and readable status text.
    - Update available: gold status with animated shine.
    - Downloading: progress bar, downloaded size, and percentage.
    """

    clicked_for_update = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._update_available = False
        self._downloading = False

        self._shine_position = -0.5

        self._downloaded = 0
        self._download_total = 0
        self._download_percentage = 0

        self.setFixedSize(91, 25)

        self.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.setFocusPolicy(
            Qt.FocusPolicy.NoFocus
        )

        self.setToolTip(
            "You're up to date"
        )

        self.clicked.connect(
            self.clicked_for_update.emit
        )

        self._shine_timer = QTimer(self)
        self._shine_timer.setInterval(35)
        self._shine_timer.timeout.connect(
            self._advance_shine
        )

    def set_update_available(self, available):
        self._update_available = bool(available)

        if self._update_available:
            if not self._downloading:
                self.setToolTip(
                    "An update is available — click to view"
                )

                self.setFixedSize(126, 25)

                self._shine_position = -0.5
                self._shine_timer.start()

        else:
            self._downloading = False

            self._downloaded = 0
            self._download_total = 0
            self._download_percentage = 0

            self._shine_timer.stop()

            self.setToolTip(
                "You're up to date"
            )

            self.setFixedSize(91, 25)

        self.updateGeometry()
        self.update()

    def set_downloading(self, downloading):
        self._downloading = bool(downloading)

        if self._downloading:
            self._shine_timer.stop()

            self.setToolTip(
                "Downloading the update…"
            )

            self.setFixedSize(138, 27)

        else:
            self._downloaded = 0
            self._download_total = 0
            self._download_percentage = 0

            if self._update_available:
                self.setFixedSize(126, 25)

                self.setToolTip(
                    "An update is available — click to view"
                )

                self._shine_timer.start()

            else:
                self.setFixedSize(91, 25)

                self.setToolTip(
                    "You're up to date"
                )

        self.updateGeometry()
        self.update()

    def set_download_progress(self, downloaded, total):
        self._downloaded = max(
            0,
            int(downloaded),
        )

        self._download_total = max(
            0,
            int(total),
        )

        if self._download_total > 0:
            self._download_percentage = min(
                100,
                int(
                    self._downloaded
                    * 100
                    / self._download_total
                ),
            )
        else:
            self._download_percentage = 0

        if self._downloading:
            self.update()

    def _advance_shine(self):
        if self._downloading or not self._update_available:
            self._shine_timer.stop()
            return

        self._shine_position += 0.045

        if self._shine_position > 1.5:
            self._shine_position = -0.5

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)

        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )

        rect = self.rect().adjusted(
            1,
            1,
            -1,
            -1,
        )

        if self._downloading:
            self._paint_download_progress(
                painter,
                rect,
            )

        elif self._update_available:
            self._paint_update_available(
                painter,
                rect,
            )

        else:
            self._paint_up_to_date(
                painter,
                rect,
            )

        painter.end()

    def _paint_up_to_date(self, painter, rect):
        background = QColor("#20232b")
        foreground = QColor("#858995")
        border = QColor("#343842")

        if self.underMouse():
            background = QColor("#252831")
            foreground = QColor("#a4a8b2")
            border = QColor("#454a56")

        painter.setPen(
            QPen(border, 1)
        )

        painter.setBrush(background)

        painter.drawRoundedRect(
            rect,
            5,
            5,
        )

        painter.setPen(foreground)

        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)

        painter.drawText(
            rect.adjusted(4, 0, -4, 0),
            Qt.AlignmentFlag.AlignCenter,
            "Up to date",
        )

    def _paint_update_available(self, painter, rect):
        background = QColor("#3a3020")
        foreground = QColor("#e8bd62")
        border = QColor("#80602b")

        if self.underMouse():
            background = QColor("#493b25")
            foreground = QColor("#ffda85")
            border = QColor("#a17a36")

        painter.setPen(
            QPen(border, 1)
        )

        painter.setBrush(background)

        painter.drawRoundedRect(
            rect,
            5,
            5,
        )

        if self._shine_timer.isActive():
            shine = QLinearGradient(
                rect.left()
                + rect.width() * self._shine_position,
                rect.top(),
                rect.left()
                + rect.width()
                * (self._shine_position + 0.35),
                rect.bottom(),
            )

            shine.setColorAt(
                0.0,
                QColor(255, 255, 255, 0),
            )

            shine.setColorAt(
                0.5,
                QColor(255, 235, 180, 75),
            )

            shine.setColorAt(
                1.0,
                QColor(255, 255, 255, 0),
            )

            painter.setPen(
                Qt.PenStyle.NoPen
            )

            painter.setBrush(shine)

            painter.drawRoundedRect(
                rect,
                5,
                5,
            )

        painter.setPen(foreground)

        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)

        painter.drawText(
            rect.adjusted(4, 0, -4, 0),
            Qt.AlignmentFlag.AlignCenter,
            "↑  Update available",
        )

    def _paint_download_progress(self, painter, rect):
        background = QColor("#20232b")
        border = QColor("#494255")
        foreground = QColor("#e0d9f4")
        progress_color = QColor("#a78bfa")

        painter.setPen(
            QPen(border, 1)
        )

        painter.setBrush(background)

        painter.drawRoundedRect(
            rect,
            5,
            5,
        )

        percentage = self._download_percentage

        progress_rect = rect.adjusted(
            1,
            1,
            -1,
            -1,
        )

        progress_width = int(
            progress_rect.width()
            * percentage
            / 100
        )

        if progress_width > 0:
            progress_rect.setWidth(
                progress_width
            )

            painter.setPen(
                Qt.PenStyle.NoPen
            )

            painter.setBrush(
                QColor(
                    progress_color.red(),
                    progress_color.green(),
                    progress_color.blue(),
                    65,
                )
            )

            painter.drawRoundedRect(
                progress_rect,
                4,
                4,
            )

        if self._download_total > 0:
            amount = (
                f"{_format_download_size(self._downloaded)}"
                f" / "
                f"{_format_download_size(self._download_total)}"
            )
        else:
            amount = (
                f"{_format_download_size(self._downloaded)}"
                " downloaded"
            )

        text = (
            f"{amount}  ·  {percentage}%"
        )

        painter.setPen(foreground)

        font = painter.font()
        font.setPointSize(7)
        font.setBold(True)
        painter.setFont(font)

        painter.drawText(
            rect.adjusted(4, 0, -4, 0),
            Qt.AlignmentFlag.AlignCenter,
            text,
        )


class UpdateNotification(QPushButton):
    """
    Dedicated clickable update notification.

    Separate from the existing transient toast notifications.
    """

    notification_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName(
            "update_notification"
        )

        self.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.setFocusPolicy(
            Qt.FocusPolicy.NoFocus
        )

        self.setText("")
        self.hide()

        self.setStyleSheet("""
            QPushButton#update_notification {
                background: #292820;
                border: 1px solid #806b3b;
                border-radius: 8px;
                color: #f0e5c9;
                text-align: left;
                padding: 12px 16px;
            }

            QPushButton#update_notification:hover {
                background: #353024;
                border-color: #b8954e;
            }
        """)

        self.clicked.connect(
            self.notification_clicked.emit
        )

    def show_update(self, version):
        self.setText(
            f"↑   Synapse {version} is available\n"
            "      Click to view the update"
        )

        self.setMinimumWidth(280)
        self.setMinimumHeight(62)
        self.adjustSize()

        self.show()
        self.raise_()

    def dismiss(self):
        self.hide()
