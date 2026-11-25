
import math
from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QSize,
    QPointF,
    QUrl,
    QRect,
    QTimer,
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
    QPalette,
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

from core.workflow_manager import WorkflowManager
from pages.workflows_page import WorkflowsPage
from pages.macros_page import MacrosPage
from pages.settings_page import SettingsPage
from pages.workflow_editor_page import WorkflowEditorPage


BUY_ME_A_COFFEE_URL = "https://buymeacoffee.com/baulsax"


class SidebarButton(QPushButton):
    """Sidebar button with independently positioned icon and text."""

    def __init__(self, text, icon, parent=None):
        super().__init__("", parent)

        self._label_text = text
        self._sidebar_icon = icon
        self._is_support_button = text == "Support Me"

        self._shine_offset = -180
        self._shine_paused = False

        self.setObjectName("nav_button")
        self.setCheckable(True)
        self.setFixedHeight(42)
        self.setIcon(QIcon())

        if self._is_support_button:
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

            self._shine_timer.start()

    def _advance_shine(self):
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
        self._shine_paused = False
        self._shine_timer.start()
        self.update()

    def _paint_support_shine(self, painter):
        """Paint a diagonal moving highlight over the selected-style background."""
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

        gradient = QLinearGradient(
            self._shine_offset,
            self.height(),
            self._shine_offset - 75,
            0,
        )

        gradient.setColorAt(
            0.0,
            QColor(185, 162, 255, 0),
        )
        gradient.setColorAt(
            0.35,
            QColor(185, 162, 255, 22),
        )
        gradient.setColorAt(
            0.5,
            QColor(235, 225, 255, 75),
        )
        gradient.setColorAt(
            0.65,
            QColor(185, 162, 255, 22),
        )
        gradient.setColorAt(
            1.0,
            QColor(185, 162, 255, 0),
        )

        painter.fillRect(
            button_rect,
            gradient,
        )

        painter.restore()

    def paintEvent(self, event):
        option = QStyleOptionButton()
        self.initStyleOption(option)

        # The support button uses the same background appearance
        # as a selected navigation button without actually selecting it.
        if self._is_support_button:
            option.state |= QStyle.StateFlag.State_On

        # Draw the button background and interaction states.
        option.text = ""
        option.icon = QIcon()

        painter = QStylePainter(self)
        painter.drawControl(
            QStyle.ControlElement.CE_PushButton,
            option,
        )

        # The animated highlight belongs to the background,
        # so it doesn't interfere with the font or icon rendering.
        if self._is_support_button:
            self._paint_support_shine(painter)

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

        # Draw the icon.
        self._sidebar_icon.paint(
            painter,
            icon_rect,
            Qt.AlignmentFlag.AlignCenter,
            QIcon.Mode.Normal,
            QIcon.State.On if (
                self.isChecked() or self._is_support_button
            ) else QIcon.State.Off,
        )

        # Keep the normal font rendering while restoring bold
        # styling for selected navigation buttons.
        font = self.font()
        font.setBold(
            self._is_support_button or self.isChecked()
        )

        painter.setFont(font)

        if self._is_support_button or self.isChecked():
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


def create_nav_icon(icon_type):
    """Create minimal navigation icons for the sidebar."""
    icon = QIcon()

    for color, state in (
        ("#9298a6", QIcon.State.Off),
        ("#b9a2ff", QIcon.State.On),
    ):
        if icon_type == "support":
            color = "#b9a2ff"

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

        elif icon_type == "support":
            # Coffee cup.
            painter.drawRoundedRect(
                3.5, 8, 11, 8,
                1.5, 1.5,
            )

            # Cup handle.
            painter.drawArc(
                12, 9, 5, 6,
                -90 * 16,
                180 * 16,
            )

            # Coffee surface.
            painter.drawLine(5, 8, 13, 8)

            # Steam.
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

        self.workflow_manager = WorkflowManager()
        self.input_manager = None
        self.macro_engine = macro_engine

        self.setWindowTitle("Synapse")
        self.resize(1540, 900)
        self.setMinimumSize(1150, 700)

        central = QWidget()
        self.setCentralWidget(central)

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

        # Logo image.
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

        # Wordmark.
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

        # Divider between Support Me and the version label.
        support_divider_container = QWidget()
        support_divider_container.setFixedHeight(1)

        support_divider_layout = QHBoxLayout(
            support_divider_container
        )
        support_divider_layout.setContentsMargins(0, 0, 0, 0)
        support_divider_layout.setSpacing(0)

        support_divider = QFrame()
        support_divider.setObjectName("sidebar_divider")
        support_divider.setFixedHeight(1)

        support_divider_layout.addWidget(support_divider)

        content_layout.addWidget(support_divider_container)

        # Version label.
        version = QLabel("Version 0.1.0")
        version.setObjectName("muted")
        version.setContentsMargins(4, 0, 0, 2)
        content_layout.addWidget(version)

        sidebar_layout.addWidget(sidebar_content, 1)

        # -------------------------
        # Main workspace
        # -------------------------

        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)

        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.addWidget(self.pages)

        # Workflows page
        self.workflows_page = WorkflowsPage()

        self.workflows_page.workflow_opened.connect(
            self.open_workflow
        )

        self.workflows_page.workflow_run_requested.connect(
            self.run_workflow_from_dashboard
        )

        self.workflows_page.workflow_delete_requested.connect(
            self.delete_workflow_from_dashboard
        )

        self.pages.addWidget(self.workflows_page)

        # Connect manager lifecycle notifications.
        self.workflow_manager.signals.activity_event.connect(
            self.on_activity_event
        )

        self.workflow_manager.signals.status_changed.connect(
            self.refresh_dashboard_state
        )

        # Macros page
        self.macros_page = MacrosPage(self.macro_engine)
        self.pages.addWidget(self.macros_page)

        # Settings page
        self.settings_page = SettingsPage()

        self.settings_page.workflows_directory_changed.connect(
            self.on_workflows_directory_changed
        )

        self.pages.addWidget(self.settings_page)

        main_layout.addWidget(sidebar)
        main_layout.addWidget(workspace, 1)

        self.refresh_dashboard_state()

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
            self.shutdown_runtime()
            event.accept()
            return

        if not current_page.bridge.is_dirty:
            self.shutdown_runtime()
            event.accept()
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

            self.shutdown_runtime()
            event.accept()

        else:
            event.ignore()
