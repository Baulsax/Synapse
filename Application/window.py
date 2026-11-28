import json
import math
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QSize,
    QPointF,
    QUrl,
    QRect,
    QRectF,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QPixmap,
    QIcon,
    QPainter,
    QPen,
    QColor,
    QPainterPath,
    QPolygonF,
    QFont,
    QDesktopServices,
    QLinearGradient,
)
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QStackedWidget,
    QButtonGroup,
    QMessageBox,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
)

from core.version import APP_VERSION
from core.workflow_manager import WorkflowManager
from core.update_manager import UpdateManager
from core.update_dialog import UpdateDialog
from core.update_controls import UpdateNotification

from pages.workflows_page import WorkflowsPage
from pages.macros_page import MacrosPage
from pages.settings_page import SettingsPage
from pages.workflow_editor_page import WorkflowEditorPage
from pages.updates_page import UpdatesPage


BUY_ME_A_COFFEE_URL = "https://buymeacoffee.com/baulsax"


class SynapseWorkflowsPage(WorkflowsPage):
    """
    Workflows page that reports successfully persisted setting values
    so an already-open Blockly editor can stay synchronized.
    """

    workflow_setting_saved = Signal(str, str, str)

    def save_workflow_setting(
        self,
        workflow_name,
        setting_id,
        value
    ):
        super().save_workflow_setting(
            workflow_name,
            setting_id,
            value
        )

        try:
            _, workflow_data = self._load_workflow_data(
                workflow_name
            )

            block = self._find_setting_block(
                workflow_data,
                setting_id
            )

            if block is None:
                return

            fields = block.get("fields", {})

            if not isinstance(fields, dict):
                return

            stored_value = str(
                fields.get("VALUE", "")
            )

            self.workflow_setting_saved.emit(
                workflow_name,
                setting_id,
                stored_value
            )

        except Exception:
            return


class SidebarButton(QPushButton):
    """Sidebar button with independently positioned icon and text."""

    def __init__(self, text, icon, parent=None):
        super().__init__("", parent)

        self._label_text = text
        self._sidebar_icon = icon

        self._is_support_button = text == "Support Me"
        self._is_updates_button = text == "Updates"

        self._shine_offset = -180
        self._shine_paused = False
        self._update_available = False

        self.setObjectName("nav_button")
        self.setCheckable(True)
        self.setFixedHeight(42)
        self.setIcon(QIcon())

        if self._is_support_button or self._is_updates_button:
            self._shine_timer = QTimer(self)
            self._shine_timer.setInterval(25)
            self._shine_timer.timeout.connect(
                self._advance_shine
            )

            self._shine_pause_timer = QTimer(self)
            self._shine_pause_timer.setSingleShot(True)
            self._shine_pause_timer.setInterval(2000)
            self._shine_pause_timer.timeout.connect(
                self._resume_shine
            )

        if self._is_support_button:
            self._shine_timer.start()

    def set_update_available(self, available):
        if not self._is_updates_button:
            return

        available = bool(available)

        if self._update_available == available:
            return

        self._update_available = available
        self._shine_offset = -180
        self._shine_paused = False

        self._shine_pause_timer.stop()

        # Keep the icon palette in sync with the full button state.
        self._sidebar_icon = create_nav_icon(
            "updates",
            gold=available,
        )

        if available:
            self._shine_timer.start()
        else:
            self._shine_timer.stop()

        self.update()

    def _advance_shine(self):
        if self._is_updates_button and not self._update_available:
            return

        if self._shine_paused:
            return

        self._shine_offset += 3.75

        if self._shine_offset > self.width() + 180:
            self._shine_offset = -180
            self._shine_paused = True

            self._shine_timer.stop()
            self._shine_pause_timer.start()

        self.update()

    def _resume_shine(self):
        if self._is_updates_button and not self._update_available:
            return

        self._shine_paused = False
        self._shine_timer.start()
        self.update()

    def _paint_shine(self, painter):
        """Paint the moving highlight over the button background."""

        painter.save()

        button_rect = QRect(
            1,
            1,
            self.width() - 2,
            self.height() - 2,
        )

        clip_path = QPainterPath()
        clip_path.addRoundedRect(
            button_rect,
            6,
            6,
        )

        painter.setClipPath(clip_path)

        if self._is_updates_button:
            colors = (
                QColor(255, 190, 75, 0),
                QColor(255, 190, 75, 28),
                QColor(255, 221, 145, 105),
                QColor(255, 190, 75, 28),
                QColor(255, 190, 75, 0),
            )
        else:
            colors = (
                QColor(185, 162, 255, 0),
                QColor(185, 162, 255, 22),
                QColor(235, 225, 255, 75),
                QColor(185, 162, 255, 22),
                QColor(185, 162, 255, 0),
            )

        gradient = QLinearGradient(
            self._shine_offset,
            self.height(),
            self._shine_offset - 75,
            0,
        )

        for position, color in zip(
            (0.0, 0.35, 0.5, 0.65, 1.0),
            colors,
        ):
            gradient.setColorAt(position, color)

        painter.fillRect(
            button_rect,
            gradient,
        )

        painter.restore()

    def _paint_update_background(self, painter):
        """Paint the full gold state used when an update is available."""

        painter.save()

        rect = QRectF(
            1,
            1,
            self.width() - 2,
            self.height() - 2,
        )

        gradient = QLinearGradient(
            0,
            rect.top(),
            0,
            rect.bottom(),
        )

        gradient.setColorAt(0.0, QColor("#70552e"))
        gradient.setColorAt(0.5, QColor("#624a29"))
        gradient.setColorAt(1.0, QColor("#513e25"))

        painter.setPen(QPen(QColor("#92703d"), 1))
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, 6, 6)

        painter.restore()

    def paintEvent(self, event):
        option = QStyleOptionButton()
        self.initStyleOption(option)

        if self._is_support_button:
            option.state |= QStyle.StateFlag.State_On

        option.text = ""
        option.icon = QIcon()

        painter = QStylePainter(self)
        painter.drawControl(
            QStyle.ControlElement.CE_PushButton,
            option,
        )

        if self._is_updates_button and self._update_available:
            self._paint_update_background(painter)
            self._paint_shine(painter)

        elif self._is_support_button:
            self._paint_shine(painter)

        icon_size = 19
        icon_rect = QRect(
            12,
            (self.height() - icon_size) // 2,
            icon_size,
            icon_size,
        )

        text_rect = QRect(
            42,
            -2,
            self.width() - 54,
            self.height(),
        )

        self._sidebar_icon.paint(
            painter,
            icon_rect,
            Qt.AlignmentFlag.AlignCenter,
            QIcon.Mode.Normal,
            QIcon.State.On if (
                self.isChecked() or self._is_support_button
            ) else QIcon.State.Off,
        )

        font = self.font()
        font.setBold(
            self._is_support_button
            or self.isChecked()
            or (
                self._is_updates_button
                and self._update_available
            )
        )

        painter.setFont(font)

        if self._is_support_button:
            text_color = QColor("#b9a2ff")

        elif self._is_updates_button and self._update_available:
            text_color = QColor("#ffe0a3")

        elif self.isChecked():
            text_color = QColor("#b9a2ff")

        elif self.underMouse():
            text_color = QColor("#e5e7eb")

        else:
            text_color = QColor("#aeb3c0")

        painter.setPen(text_color)

        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter,
            self._label_text,
        )


def create_nav_icon(icon_type, gold=False):
    """Create minimal navigation icons for the sidebar."""

    icon = QIcon()

    for color, state in (
        ("#9298a6", QIcon.State.Off),
        ("#b9a2ff", QIcon.State.On),
    ):
        if icon_type == "support":
            color = "#b9a2ff"

        elif icon_type == "updates" and gold:
            color = "#f4c36e"

        pixmap = QPixmap(20, 20)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(QColor(color))
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if icon_type == "workflows":
            painter.drawLine(10, 7, 10, 10)
            painter.drawLine(5, 10, 15, 10)
            painter.drawLine(5, 10, 5, 13)
            painter.drawLine(15, 10, 15, 13)

            painter.drawRoundedRect(7.5, 2, 5, 5, 1.2, 1.2)

            painter.drawEllipse(QPointF(5, 15), 2, 2)
            painter.drawEllipse(QPointF(15, 15), 2, 2)

        elif icon_type == "macros":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))

            painter.drawRoundedRect(3, 7, 2.5, 6, 1.2, 1.2)
            painter.drawRoundedRect(7.5, 4, 2.5, 12, 1.2, 1.2)
            painter.drawRoundedRect(12, 2, 2.5, 16, 1.2, 1.2)
            painter.drawRoundedRect(16.5, 6, 2.5, 8, 1.2, 1.2)

        elif icon_type == "settings":
            points = []

            for tooth in range(8):
                base_angle = math.radians(tooth * 45)

                for offset, radius in (
                    (-13, 7.0),
                    (-7, 9.0),
                    (7, 9.0),
                    (13, 7.0),
                ):
                    angle = base_angle + math.radians(offset)

                    points.append(
                        QPointF(
                            10 + math.cos(angle) * radius,
                            10 + math.sin(angle) * radius,
                        )
                    )

            gear_path = QPainterPath()
            gear_path.addPolygon(QPolygonF(points))
            gear_path.addEllipse(
                QPointF(10, 10),
                3.1,
                3.1,
            )
            gear_path.setFillRule(
                Qt.FillRule.OddEvenFill
            )

            painter.drawPath(gear_path)

        elif icon_type == "updates":
            # A single smooth refresh arc.
            refresh_path = QPainterPath()
            refresh_path.moveTo(5.0, 5.1)
            refresh_path.cubicTo(
                7.2, 2.8,
                11.1, 2.4,
                14.0, 4.3,
            )
            refresh_path.cubicTo(
                17.2, 6.3,
                18.1, 10.2,
                16.3, 13.5,
            )
            refresh_path.cubicTo(
                14.5, 16.8,
                10.7, 18.0,
                7.3, 16.5,
            )
            refresh_path.cubicTo(
                4.1, 15.1,
                2.6, 11.7,
                3.5, 8.4,
            )

            painter.drawPath(refresh_path)

            # Arrowhead follows the tangent at the arc's endpoint.
            arrow = QPolygonF([
                QPointF(3.5, 8.4),
                QPointF(3.0, 12.1),
                QPointF(6.7, 9.8),
            ])

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            painter.drawPolygon(arrow)

        elif icon_type == "support":
            painter.drawRoundedRect(
                3.5, 8, 11, 8,
                1.5, 1.5,
            )

            painter.drawArc(
                12, 9, 5, 6,
                -90 * 16,
                180 * 16,
            )

            painter.drawLine(5, 8, 13, 8)

            steam = QPainterPath()
            steam.moveTo(7, 6)
            steam.cubicTo(5, 4, 9, 3, 7, 1.5)

            steam.moveTo(12, 6)
            steam.cubicTo(10, 4, 14, 3, 12, 1.5)

            painter.drawPath(steam)

        painter.end()

        icon.addPixmap(
            pixmap,
            QIcon.Mode.Normal,
            state,
        )

    return icon


class SynapseWindow(QMainWindow):

    def __init__(self, macro_engine=None):
        super().__init__()

        self._close_after_save = False
        self._runtime_shutdown = False

        # Update state.
        self._update_enabled = bool(
            getattr(sys, "frozen", False)
        )

        self._update_release_data = None
        self._update_staging_directory = None
        self._update_download_in_progress = False
        self._pending_update_action = None

        self.workflow_manager = WorkflowManager()
        self.input_manager = None
        self.macro_engine = macro_engine

        self.setWindowTitle("Synapse")
        self.resize(1540, 900)
        self.setMinimumSize(1150, 700)

        central = QWidget()
        self.setCentralWidget(central)
        self._central_widget = central

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.pages = QStackedWidget()

        self.workflow_editors = {}
        self.last_workflow_editor = None

        # -------------------------
        # Sidebar
        # -------------------------

        sidebar = QFrame()
        sidebar.setFixedWidth(210)
        sidebar.setObjectName("sidebar")

        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # -------------------------
        # Branding header
        # -------------------------

        branding_container = QWidget()
        branding_container.setFixedHeight(88)
        branding_container.setObjectName("branding_container")

        branding_container.setStyleSheet("""
            QWidget#branding_container {
                background: qlineargradient(
                    x1: 0, y1: 0,
                    x2: 0, y2: 1,
                    stop: 0 #17191f,
                    stop: 0.45 #1a1d24,
                    stop: 0.8 #1e2129,
                    stop: 1 #20232b
                );
                border-right: 1px solid #30343e;
            }
        """)

        branding_layout = QVBoxLayout(branding_container)
        branding_layout.setContentsMargins(8, 5, 13, 5)
        branding_layout.setSpacing(0)
        branding_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        branding_top_row = QWidget()
        branding_top_row.setFixedHeight(64)

        branding_top_layout = QHBoxLayout(branding_top_row)
        branding_top_layout.setContentsMargins(0, 0, 0, 0)
        branding_top_layout.setSpacing(6)

        logo_icon = QLabel()
        logo_icon.setObjectName("logo_icon")
        logo_icon.setFixedSize(60, 60)
        logo_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo_path = (
            Path(__file__).resolve().parent
            / "assets"
            / "synapse_logo.png"
        )

        logo_pixmap = QPixmap(str(logo_path))

        if not logo_pixmap.isNull():
            logo_icon.setPixmap(
                logo_pixmap.scaled(
                    60,
                    60,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        brand_text_container = QWidget()
        brand_text_container.setObjectName("brand_text_container")

        brand_text_layout = QVBoxLayout(brand_text_container)
        brand_text_layout.setContentsMargins(0, 0, 0, 0)
        brand_text_layout.setSpacing(0)
        brand_text_layout.setAlignment(
            Qt.AlignmentFlag.AlignVCenter
        )

        logo_text = QLabel("SYNAPSE")
        logo_text.setObjectName("logo")
        logo_text.setAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter
        )
        logo_text.setWordWrap(False)
        logo_text.setFixedHeight(60)

        logo_font = logo_text.font()
        logo_font.setPointSizeF(20)
        logo_font.setBold(True)
        logo_font.setLetterSpacing(
            QFont.SpacingType.AbsoluteSpacing,
            0.35,
        )

        logo_text.setFont(logo_font)

        logo_text.setStyleSheet("""
            QLabel#logo {
                color: #f2f0f7;
                background: transparent;
                padding: 0;
                margin: 0;
                font-size: 20pt;
                font-weight: bold;
                letter-spacing: 0.35px;
            }
        """)

        brand_text_layout.addWidget(logo_text)

        branding_top_layout.addWidget(logo_icon)
        branding_top_layout.addWidget(
            brand_text_container,
            1,
        )

        branding_layout.addWidget(branding_top_row)

        sidebar_layout.addWidget(branding_container)

        # Divider between branding and navigation.
        divider_container = QWidget()
        divider_container.setFixedHeight(1)

        divider_layout = QHBoxLayout(divider_container)
        divider_layout.setContentsMargins(12, 0, 12, 0)
        divider_layout.setSpacing(0)

        sidebar_divider = QFrame()
        sidebar_divider.setObjectName("sidebar_divider")
        sidebar_divider.setFixedHeight(1)

        divider_layout.addWidget(sidebar_divider)

        sidebar_layout.addWidget(divider_container)

        # -------------------------
        # Navigation content
        # -------------------------

        sidebar_content = QWidget()

        content_layout = QVBoxLayout(sidebar_content)
        content_layout.setContentsMargins(12, 7, 12, 12)
        content_layout.setSpacing(7)

        button_group = QButtonGroup(self)
        button_group.setExclusive(True)

        navigation_items = [
            ("Workflows", "workflows"),
            ("Macros", "macros"),
            ("Settings", "settings"),
        ]

        for index, (name, icon_type) in enumerate(navigation_items):
            button = SidebarButton(
                name,
                create_nav_icon(icon_type),
            )

            button.clicked.connect(
                lambda checked=False, page_index=index:
                self.navigate_to_page(page_index)
            )

            button_group.addButton(button)

            if index == 0:
                button.setChecked(True)

            content_layout.addWidget(button)

        content_layout.addStretch()

        # -------------------------
        # Updates navigation button
        # -------------------------

        self.updates_nav_button = SidebarButton(
            "Updates",
            create_nav_icon("updates"),
        )

        self.updates_nav_button.setToolTip(
            "View updates and release notes"
        )

        self.updates_nav_button.clicked.connect(
            lambda: self.navigate_to_page(3)
        )

        button_group.addButton(
            self.updates_nav_button
        )

        content_layout.addWidget(
            self.updates_nav_button
        )

        # -------------------------
        # Support button
        # -------------------------

        support_button = SidebarButton(
            "Support Me",
            create_nav_icon("support"),
        )

        support_button.setCheckable(False)
        support_button.setToolTip(
            "Support Synapse on Buy Me a Coffee"
        )

        support_button.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl(BUY_ME_A_COFFEE_URL)
            )
        )

        content_layout.addWidget(support_button)

        sidebar_layout.addWidget(sidebar_content, 1)

        # -------------------------
        # Version footer
        # -------------------------

        version_divider_container = QWidget()
        version_divider_container.setFixedHeight(1)

        version_divider_layout = QHBoxLayout(
            version_divider_container
        )
        version_divider_layout.setContentsMargins(
            12, 0, 12, 0
        )
        version_divider_layout.setSpacing(0)

        version_divider = QFrame()
        version_divider.setObjectName("sidebar_divider")
        version_divider.setFixedHeight(1)

        version_divider_layout.addWidget(version_divider)

        sidebar_layout.addWidget(
            version_divider_container
        )

        version_label = QLabel(
            f"Version {APP_VERSION}"
        )
        version_label.setObjectName("sidebar_version")
        version_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter
        )
        version_label.setContentsMargins(
            16, 0, 12, 0
        )
        version_label.setFixedHeight(34)
        version_label.setStyleSheet("""
            QLabel#sidebar_version {
                color: #858995;
                background: transparent;
                font-size: 9pt;
                padding: 0;
            }
        """)

        sidebar_layout.addWidget(version_label)

        # -------------------------
        # Main workspace
        # -------------------------

        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)

        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.addWidget(self.pages)

        # Workflows page.
        self.workflows_page = SynapseWorkflowsPage()

        self.workflows_page.workflow_opened.connect(
            self.open_workflow
        )

        self.workflows_page.workflow_run_requested.connect(
            self.run_workflow_from_dashboard
        )

        self.workflows_page.workflow_delete_requested.connect(
            self.delete_workflow_from_dashboard
        )

        self.workflows_page.workflow_setting_saved.connect(
            self.on_workflow_setting_saved
        )

        self.pages.addWidget(self.workflows_page)

        # Connect manager lifecycle notifications.
        self.workflow_manager.signals.activity_event.connect(
            self.on_activity_event
        )

        self.workflow_manager.signals.status_changed.connect(
            self.refresh_dashboard_state
        )

        # Macros page.
        self.macros_page = MacrosPage(self.macro_engine)
        self.pages.addWidget(self.macros_page)

        # Settings page.
        self.settings_page = SettingsPage()

        self.settings_page.workflows_directory_changed.connect(
            self.on_workflows_directory_changed
        )

        self.pages.addWidget(self.settings_page)

        # Updates page.
        self.updates_page = UpdatesPage(APP_VERSION)

        self.updates_page.check_requested.connect(
            self.check_for_updates
        )

        self.updates_page.update_details_requested.connect(
            self.open_update_dialog
        )

        if not self._update_enabled:
            self.updates_page.set_unavailable(
                "Update checking and installation are available "
                "in the installed version of Synapse. Install Synapse "
                "using its setup program to use the updater."
            )

        self.pages.addWidget(self.updates_page)

        main_layout.addWidget(sidebar)
        main_layout.addWidget(workspace, 1)

        self.refresh_dashboard_state()

        # -------------------------
        # Update overlay and notification
        # -------------------------

        self.update_dialog = UpdateDialog(
            self._central_widget
        )

        self.update_dialog.download_requested.connect(
            self.start_update_download
        )

        self.update_dialog.restart_requested.connect(
            self.request_update_restart
        )

        self.update_dialog.install_on_exit_requested.connect(
            self.request_update_on_exit
        )

        self.update_notification = UpdateNotification(
            self._central_widget
        )

        self.update_notification.notification_clicked.connect(
            self.open_update_dialog
        )

        self._position_update_controls()

        # -------------------------
        # Update manager
        # -------------------------

        self.update_manager = None

        if self._update_enabled:
            install_directory = Path(
                sys.executable
            ).resolve().parent

            self.update_manager = UpdateManager(
                APP_VERSION,
                install_directory,
                self,
            )

            self.update_manager.update_available.connect(
                self.on_update_available
            )

            self.update_manager.up_to_date.connect(
                self.on_up_to_date
            )

            self.update_manager.download_progress.connect(
                self.on_update_download_progress
            )

            self.update_manager.download_finished.connect(
                self.on_update_download_finished
            )

            self.update_manager.failed.connect(
                self.on_update_failed
            )

            # Exactly one update check when the installed app launches.
            self.updates_page.set_checking()
            self.check_for_updates()

    # ======================================
    # UPDATE SYSTEM
    # ======================================

    def _get_valid_staging_directory(self):
        """
        Return the downloaded update directory only when its required
        metadata files are present.

        This lets the dialog restore its completed state after being
        dismissed and reopened.
        """

        if not self._update_staging_directory:
            return None

        try:
            staging = Path(
                self._update_staging_directory
            ).resolve()

            if not staging.is_dir():
                return None

            if not (staging / "plan.json").is_file():
                return None

            if not (
                staging / "update-manifest.json"
            ).is_file():
                return None

            return staging

        except (OSError, TypeError, ValueError):
            return None

    def check_for_updates(self):
        if not self.update_manager:
            return

        self.updates_page.set_checking()

        # The manager emits a failure signal if the request is blocked
        # by a cooldown or another active update operation.
        # That signal restores the page's enabled Try Again button.
        self.update_manager.check_for_updates()

    def on_update_available(self, metadata):
        if not isinstance(metadata, dict):
            return

        self._update_release_data = metadata

        new_version = metadata.get(
            "version",
            "unknown",
        )

        self.updates_page.set_update_available(
            metadata
        )

        self.updates_nav_button.set_update_available(True)

        self.update_notification.show_update(
            new_version
        )

        self._position_update_controls()

    def on_up_to_date(self, version):
        self._update_release_data = None

        self.updates_page.set_up_to_date(
            version or APP_VERSION
        )

        self.updates_nav_button.set_update_available(False)
        self.update_notification.dismiss()

    def open_update_dialog(self):
        if not self._update_release_data:
            self.check_for_updates()
            return

        metadata = self._update_release_data

        self.update_dialog.show_update(
            current_version=metadata.get(
                "current_version",
                APP_VERSION,
            ),
            new_version=metadata.get(
                "version",
                "unknown",
            ),
            package_size=metadata.get(
                "package_size",
                0,
            ),
            release_notes=metadata.get(
                "release_notes",
                "",
            ),
        )

        if self._update_download_in_progress:
            self.update_dialog.set_download_started()

        elif self._get_valid_staging_directory():
            self.update_dialog.set_download_complete()

        self._position_update_controls()
        self.update_dialog.raise_()

    def start_update_download(self):
        if not self.update_manager:
            return

        if self._update_download_in_progress:
            return

        if self._get_valid_staging_directory():
            self.update_dialog.set_download_complete()
            self.updates_page.set_download_complete()
            return

        self._update_staging_directory = None

        started = self.update_manager.download_update()

        if started:
            self._update_download_in_progress = True

            self.updates_page.set_download_started()
            self.update_dialog.set_download_started()

    def on_update_download_progress(
        self,
        downloaded,
        total,
    ):
        if not self._update_download_in_progress:
            return

        self.updates_page.set_download_progress(
            downloaded,
            total,
        )

        self.update_dialog.set_download_progress(
            downloaded,
            total,
        )

    def on_update_download_finished(self, staging_directory):
        self._update_download_in_progress = False

        self._update_staging_directory = Path(
            staging_directory
        ).resolve()

        if self._get_valid_staging_directory():
            self.update_dialog.set_download_complete()
            self.updates_page.set_download_complete()
            self.update_notification.dismiss()
        else:
            self._update_staging_directory = None

            self.updates_page.set_download_failed(
                "The downloaded update could not be verified. "
                "Please try downloading it again."
            )

            self.update_dialog.set_error(
                "The downloaded update could not be verified. "
                "Please try downloading it again."
            )

    def on_update_failed(self, message):
        was_downloading = self._update_download_in_progress

        self._update_download_in_progress = False

        if was_downloading:
            self._update_staging_directory = None

            self.updates_page.set_download_failed(message)
            self.update_dialog.set_error(message)

        else:
            self.updates_page.set_check_failed(message)

    def request_update_restart(self):
        if not self._get_valid_staging_directory():
            self.update_dialog.set_error(
                "The downloaded update could not be located. "
                "Please download it again."
            )
            return

        self._pending_update_action = "restart"
        self.close()

    def request_update_on_exit(self):
        if not self._get_valid_staging_directory():
            self.update_dialog.set_error(
                "The downloaded update could not be located. "
                "Please download it again."
            )
            return

        self._pending_update_action = "exit"
        self.close()

    def _launch_update_helper(self):
        """
        Start the separately packaged updater helper.

        The helper requests elevation and waits for this Synapse
        process to exit before replacing installed application files.
        """

        if not self._update_enabled:
            return False, (
                "The updater is only available in installed builds."
            )

        install_directory = Path(
            sys.executable
        ).resolve().parent

        helper_path = (
            install_directory / "SynapseUpdater.exe"
        )

        if not helper_path.is_file():
            return False, (
                "The update helper is missing:\n\n"
                f"{helper_path}\n\n"
                "Please reinstall Synapse using the latest installer."
            )

        staging = self._get_valid_staging_directory()

        if staging is None:
            return False, (
                "The downloaded update is incomplete. "
                "Please download it again."
            )

        arguments = [
            str(helper_path),
            "--pid",
            str(os.getpid()),
            "--install-dir",
            str(install_directory),
        ]

        if self._pending_update_action == "restart":
            arguments.append("--restart")

        try:
            subprocess.Popen(
                arguments,
                cwd=str(install_directory),
                close_fds=True,
                creationflags=getattr(
                    subprocess,
                    "CREATE_NO_WINDOW",
                    0,
                ),
            )

            return True, ""

        except Exception as error:
            return False, (
                "Could not start the update helper:\n\n"
                f"{error}"
            )

    def _complete_pending_update_close(self, event):
        """
        Launch the helper only after the existing close confirmation
        has been accepted.
        """

        if self._pending_update_action:
            success, error = self._launch_update_helper()

            if not success:
                self._pending_update_action = None

                QMessageBox.critical(
                    self,
                    "Update Could Not Start",
                    error,
                )

                event.ignore()
                return False

        self.shutdown_runtime()
        event.accept()
        return True

    # ======================================
    # UPDATE CONTROL POSITIONING
    # ======================================

    def _position_update_controls(self):
        if not hasattr(self, "_central_widget"):
            return

        rect = self._central_widget.rect()

        if hasattr(self, "update_dialog"):
            self.update_dialog.setGeometry(rect)

        if (
            hasattr(self, "update_notification")
            and self.update_notification.isVisible()
        ):
            margin = 22

            self.update_notification.adjustSize()

            x = max(
                margin,
                rect.width()
                - self.update_notification.width()
                - margin,
            )

            y = max(
                margin,
                rect.height()
                - self.update_notification.height()
                - margin,
            )

            self.update_notification.move(x, y)
            self.update_notification.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_update_controls()

    # ======================================
    # ACTIVITY AND STATUS
    # ======================================

    def refresh_dashboard_state(self, *_args):
        folder = self._current_workflows_folder()

        statuses = self.workflow_manager.get_workflow_statuses(
            folder
        )

        self.workflows_page.set_workflow_statuses(statuses)

        history = self.workflow_manager.get_activity_history(
            limit=20
        )

        self.workflows_page.set_activity_history(history)

    def on_activity_event(self, _activity):
        self.refresh_dashboard_state()

    # ======================================
    # WORKFLOW IDENTITY
    # ======================================

    def _current_workflows_folder(self):
        self.workflow_manager._sync_storage_paths()

        return Path(
            self.workflow_manager.workflows_folder
        ).resolve()

    @staticmethod
    def _editor_key(workflow_name, folder):
        return (
            str(Path(folder).resolve()),
            workflow_name
        )

    # ======================================
    # NAVIGATION
    # ======================================

    def navigate_to_page(self, page_index):
        self.pages.setCurrentIndex(page_index)

        if page_index == 1:
            self.macros_page.refresh_library()

        if page_index == 0:
            self.refresh_dashboard_state()

    # ======================================
    # STORAGE CHANGES
    # ======================================

    def on_workflows_directory_changed(self, directory):
        self.workflows_page.refresh_workflows()
        self.workflow_manager.refresh_input_bindings()
        self.refresh_dashboard_state()

    # ======================================
    # WORKFLOW EDITOR
    # ======================================

    def open_workflow(self, workflow_name):
        folder = self._current_workflows_folder()

        editor_key = self._editor_key(
            workflow_name,
            folder
        )

        if editor_key not in self.workflow_editors:

            engine = self.workflow_manager.get_engine(
                workflow_name,
                folder
            )

            editor = WorkflowEditorPage(
                workflow_name,
                engine,
                self.input_manager
            )

            editor.bridge.workflow_saved.connect(
                self.on_workflow_saved
            )

            editor.bridge.workflow_renamed.connect(
                lambda old_name, new_name, page=editor:
                self.on_workflow_renamed(
                    old_name,
                    new_name,
                    page
                )
            )

            editor.back_requested.connect(
                self.return_to_workflow_list
            )

            self.workflow_editors[editor_key] = editor
            self.pages.addWidget(editor)

        editor = self.workflow_editors[editor_key]

        self.last_workflow_editor = editor
        self.pages.setCurrentWidget(editor)

        self.refresh_dashboard_state()

    def on_workflow_renamed(self, old_name, new_name, editor):
        folder = editor.bridge.workflows_folder

        old_key = self._editor_key(
            old_name,
            folder
        )

        new_key = self._editor_key(
            new_name,
            folder
        )

        self.workflow_editors.pop(old_key, None)
        self.workflow_editors[new_key] = editor

        self.workflow_manager.rename_workflow(
            old_name,
            new_name,
            folder
        )

        current_folder = self._current_workflows_folder()

        if Path(folder).resolve() == current_folder:
            self.workflows_page.rename_workflow(
                old_name,
                new_name
            )

        self.refresh_dashboard_state()

    def return_to_workflow_list(self):
        self.pages.setCurrentWidget(self.workflows_page)
        self.refresh_dashboard_state()

    # ======================================
    # WORKFLOW SETTINGS LIVE SYNCHRONIZATION
    # ======================================

    def on_workflow_setting_saved(
        self,
        workflow_name,
        setting_id,
        value
    ):
        """
        Update the matching block in an already-open editor.

        Blockly events are disabled during this external update so
        the editor does not become dirty when the dashboard has
        already persisted the setting to the workflow JSON file.
        """

        folder = Path(
            self.workflows_page.save_folder
        ).resolve()

        editor_key = self._editor_key(
            workflow_name,
            folder
        )

        editor = self.workflow_editors.get(editor_key)

        if editor is None:
            return

        block_id_json = json.dumps(str(setting_id))
        value_json = json.dumps(str(value))

        script = f"""
        (() => {{
            if (typeof Blockly === "undefined") {{
                return false;
            }}

            const workspace = Blockly.getMainWorkspace();

            if (!workspace) {{
                return false;
            }}

            const block = workspace.getBlockById(
                {block_id_json}
            );

            if (
                !block ||
                block.type !== "automation_workflow_setting"
            ) {{
                return false;
            }}

            Blockly.Events.disable();

            try {{
                block.setFieldValue(
                    {value_json},
                    "VALUE"
                );
            }}
            finally {{
                Blockly.Events.enable();
            }}

            return true;
        }})();
        """

        editor.blockly_view.page().runJavaScript(script)

    # ======================================
    # DASHBOARD ACTIONS
    # ======================================

    def run_workflow_from_dashboard(self, workflow_name):
        folder = self._current_workflows_folder()

        current_status = self.workflows_page.workflow_statuses.get(
            workflow_name,
            "Idle"
        )

        if current_status == "Running":
            self.workflow_manager.stop_workflow(
                workflow_name,
                folder
            )
        else:
            self.workflow_manager.start_workflow(
                workflow_name
            )

        self.refresh_dashboard_state()

    def delete_workflow_from_dashboard(self, workflow_name):
        folder = self._current_workflows_folder()

        workflow_path = (
            folder / f"{workflow_name}.json"
        )

        settings_folder = folder / ".synapse_settings"

        settings_path = (
            settings_folder / f"{workflow_name}.json"
        )

        settings_temp_path = (
            settings_folder / f"{workflow_name}.tmp"
        )

        editor_key = self._editor_key(
            workflow_name,
            folder
        )

        editor = self.workflow_editors.get(editor_key)

        if editor and editor.bridge.is_dirty:

            result = QMessageBox.question(
                self,
                "Unsaved Changes",
                "This workflow has unsaved changes.\n\n"
                "Delete it anyway?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if result != QMessageBox.StandardButton.Yes:
                return

        result = QMessageBox.question(
            self,
            "Delete Workflow",
            f"Are you sure you want to delete '{workflow_name}'?",
            QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        self.workflow_manager.stop_workflow(
            workflow_name,
            folder
        )

        if editor:

            if self.pages.currentWidget() is editor:
                self.pages.setCurrentWidget(self.workflows_page)

            self.pages.removeWidget(editor)
            editor.deleteLater()

            self.workflow_editors.pop(
                editor_key,
                None
            )

            if self.last_workflow_editor is editor:
                self.last_workflow_editor = None

        self.workflow_manager.remove_engine(
            workflow_name,
            folder
        )

        try:
            if workflow_path.exists():
                workflow_path.unlink()

        except Exception as error:

            QMessageBox.critical(
                self,
                "Delete Failed",
                f"Could not delete workflow:\n{error}"
            )
            return

        settings_cleanup_error = None

        for settings_file in (
            settings_path,
            settings_temp_path,
        ):
            try:
                if settings_file.exists():
                    settings_file.unlink()

            except Exception as error:
                settings_cleanup_error = error
                break

        if settings_cleanup_error is None:
            try:
                if settings_folder.exists():
                    settings_folder.rmdir()

            except OSError:
                pass

        self.workflow_manager.refresh_input_bindings()
        self.workflows_page.refresh_after_delete()
        self.refresh_dashboard_state()

        if settings_cleanup_error is not None:
            QMessageBox.warning(
                self,
                "Settings Cleanup Warning",
                "The workflow was deleted, but its saved settings "
                "could not be completely removed.\n\n"
                f"{settings_cleanup_error}"
            )

    # ======================================
    # SAVE HANDLING
    # ======================================

    def on_workflow_saved(self):
        self.workflow_manager.refresh_input_bindings()

        self.workflows_page.refresh_workflows()

        self.refresh_dashboard_state()

        if self._close_after_save:
            self._close_after_save = False
            self.close()

    # ======================================
    # SHUTDOWN
    # ======================================

    def shutdown_runtime(self):

        if self._runtime_shutdown:
            return

        self._runtime_shutdown = True

        if self.macro_engine:
            self.macro_engine.stop_all()

        self.workflow_manager.stop_listener()
        self.workflow_manager.stop_all()
        self.workflow_manager.close_all_windows()

    def closeEvent(self, event):

        current_page = self.pages.currentWidget()

        if not isinstance(current_page, WorkflowEditorPage):
            self._complete_pending_update_close(event)
            return

        if not current_page.bridge.is_dirty:
            self._complete_pending_update_close(event)
            return

        dialog = QMessageBox(self)

        dialog.setWindowTitle("Unsaved Changes")
        dialog.setText("You have unsaved changes.")
        dialog.setInformativeText(
            "Would you like to save before closing Synapse?"
        )

        dialog.setIcon(QMessageBox.Icon.Warning)

        save_button = dialog.addButton(
            "Save",
            QMessageBox.ButtonRole.AcceptRole
        )

        discard_button = dialog.addButton(
            "Discard",
            QMessageBox.ButtonRole.DestructiveRole
        )

        dialog.addButton(
            "Cancel",
            QMessageBox.ButtonRole.RejectRole
        )

        dialog.setDefaultButton(save_button)
        dialog.exec()

        clicked = dialog.clickedButton()

        if clicked == save_button:

            event.ignore()

            self._close_after_save = True
            current_page.save_workflow()

        elif clicked == discard_button:

            self._complete_pending_update_close(event)

        else:
            self._pending_update_action = None
            event.ignore()