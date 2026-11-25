
import sys
import subprocess
from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QSize,
    QRectF,
    QSettings,
    QPropertyAnimation,
    QEasingCurve,
    Property,
    QUrl,
    Signal,
)
from PySide6.QtGui import QPainter, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QCheckBox,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QScrollArea,
)

from core.app_paths import (
    get_workflows_dir,
    get_logs_dir,
    get_templates_dir,
    set_workflows_dir,
    set_logs_dir,
    set_templates_dir,
)


class ToggleSwitch(QCheckBox):
    """A compact, animated toggle that retains QCheckBox behavior."""

    def __init__(self, accessible_name=""):
        super().__init__()

        self.setObjectName("settings_toggle")
        self.setAccessibleName(accessible_name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(48, 28)

        self._thumb_position = 4.0

        self._animation = QPropertyAnimation(
            self, b"thumbPosition", self
        )
        self._animation.setDuration(160)
        self._animation.setEasingCurve(
            QEasingCurve.Type.OutCubic
        )

        self.toggled.connect(self._animate_toggle)

    def sizeHint(self):
        return QSize(48, 28)

    def hitButton(self, pos):
        """Make the entire custom-painted switch clickable."""
        return self.rect().contains(pos)

    def get_thumb_position(self):
        return self._thumb_position

    def set_thumb_position(self, position):
        self._thumb_position = position
        self.update()

    thumbPosition = Property(
        float,
        get_thumb_position,
        set_thumb_position
    )

    def _animate_toggle(self, checked):
        self._animation.stop()
        self._animation.setStartValue(self._thumb_position)
        self._animation.setEndValue(26.0 if checked else 4.0)
        self._animation.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )

        enabled = self.isEnabled()
        checked = self.isChecked()
        hovered = self.underMouse()

        if not enabled:
            track_color = QColor("#292c34")
            thumb_color = QColor("#777d8c")
        elif checked:
            track_color = QColor(
                "#9276ed" if hovered else "#7c5ce0"
            )
            thumb_color = QColor("#ffffff")
        else:
            track_color = QColor(
                "#454a57" if hovered else "#343844"
            )
            thumb_color = QColor("#ffffff")

        track = QRectF(2, 3, 44, 22)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, 11, 11)

        thumb = QRectF(
            self._thumb_position,
            6,
            16,
            16
        )

        painter.setBrush(thumb_color)
        painter.drawEllipse(thumb)

        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor("#b9a2ff"))
            painter.drawRoundedRect(
                QRectF(0.5, 1.5, 47, 25),
                12,
                12
            )

        painter.end()


class SettingsPage(QWidget):

    workflows_directory_changed = Signal(str)
    logs_directory_changed = Signal(str)
    templates_directory_changed = Signal(str)

    def __init__(self):
        super().__init__()

        self.settings = QSettings(
            "Synapse",
            "Synapse"
        )

        self.startup_registry = None

        if sys.platform == "win32":
            self.startup_registry = QSettings(
                r"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run",
                QSettings.Format.NativeFormat
            )

        self._build_ui()
        self._load_settings()
        self._refresh_storage_paths()

    # --------------------------------------------------
    # UI
    # --------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("settings_scroll_area")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        scroll_area.setAlignment(
            Qt.AlignmentFlag.AlignHCenter
            | Qt.AlignmentFlag.AlignTop
        )

        scroll_area.setStyleSheet(
            """
            QScrollArea#settings_scroll_area {
                background: transparent;
                border: none;
            }

            QWidget#qt_scrollarea_viewport {
                background: transparent;
            }

            QWidget#settings_content {
                background: transparent;
            }
            """
        )

        scroll_area.viewport().setAutoFillBackground(False)

        content = QWidget()
        content.setObjectName("settings_content")
        content.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True
        )
        content.setAutoFillBackground(False)
        content.setMinimumWidth(600)
        content.setMaximumWidth(760)

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        title = QLabel("Settings")
        title.setObjectName("settings_page_title")

        subtitle = QLabel(
            "Customize how Synapse behaves."
        )
        subtitle.setObjectName("settings_page_subtitle")

        content_layout.addWidget(title)
        content_layout.addSpacing(5)
        content_layout.addWidget(subtitle)
        content_layout.addSpacing(30)

        # GENERAL SECTION
        general_header = self._create_section_header(
            "General",
            "Startup and application behavior"
        )

        content_layout.addWidget(general_header)
        content_layout.addSpacing(12)

        general_card = QFrame()
        general_card.setObjectName("settings_section")

        general_layout = QVBoxLayout(general_card)
        general_layout.setContentsMargins(18, 8, 18, 8)
        general_layout.setSpacing(0)

        self.startup_toggle = ToggleSwitch(
            "Launch on Windows startup"
        )

        self.minimized_toggle = ToggleSwitch(
            "Start minimized"
        )

        general_layout.addWidget(
            self._create_setting_row(
                "Launch on Windows startup",
                "Automatically open Synapse when you sign in.",
                self.startup_toggle
            )
        )

        general_layout.addWidget(self._create_divider())

        general_layout.addWidget(
            self._create_setting_row(
                "Start minimized",
                "Open in the background when launched at sign-in.",
                self.minimized_toggle
            )
        )

        content_layout.addWidget(general_card)
        content_layout.addSpacing(12)

        self.settings_status = QLabel("")
        self.settings_status.setObjectName("settings_status")
        self.settings_status.setWordWrap(True)
        content_layout.addWidget(self.settings_status)

        content_layout.addSpacing(30)

        # STORAGE SECTION
        storage_header = self._create_section_header(
            "Storage Locations",
            "Choose where Synapse keeps your workflows, logs, and templates."
        )

        content_layout.addWidget(storage_header)
        content_layout.addSpacing(12)

        storage_card = QFrame()
        storage_card.setObjectName("settings_section")

        storage_layout = QVBoxLayout(storage_card)
        storage_layout.setContentsMargins(18, 12, 18, 12)
        storage_layout.setSpacing(0)

        # Workflows location.
        self.workflows_path_input = self._create_path_input()

        workflows_controls = self._create_path_controls(
            self.workflows_path_input,
            self._browse_workflows_directory,
            self._open_workflows_directory
        )

        storage_layout.addWidget(
            self._create_storage_row(
                "Workflows",
                "Your workflow JSON files. You can manually add or remove files here.",
                workflows_controls
            )
        )

        storage_layout.addWidget(self._create_divider())

        # Logs location.
        self.logs_path_input = self._create_path_input()

        logs_controls = self._create_path_controls(
            self.logs_path_input,
            self._browse_logs_directory,
            self._open_logs_directory
        )

        storage_layout.addWidget(
            self._create_storage_row(
                "Logs",
                "Application log files for troubleshooting.",
                logs_controls
            )
        )

        storage_layout.addWidget(self._create_divider())

        # Templates location.
        self.templates_path_input = self._create_path_input()

        templates_controls = self._create_path_controls(
            self.templates_path_input,
            self._browse_templates_directory,
            self._open_templates_directory
        )

        storage_layout.addWidget(
            self._create_storage_row(
                "Templates",
                "Workflow templates used by the New Workflow dialog. Add or remove .txt share-code template files here.",
                templates_controls
            )
        )

        content_layout.addWidget(storage_card)

        self.storage_status = QLabel("")
        self.storage_status.setObjectName("settings_status")
        self.storage_status.setWordWrap(True)

        content_layout.addSpacing(10)
        content_layout.addWidget(self.storage_status)

        content_layout.addSpacing(30)

        # APPEARANCE SECTION
        appearance_header = self._create_section_header(
            "Appearance",
            "Visual preferences"
        )

        content_layout.addWidget(appearance_header)
        content_layout.addSpacing(12)

        appearance_card = QFrame()
        appearance_card.setObjectName("settings_section")

        appearance_layout = QVBoxLayout(appearance_card)
        appearance_layout.setContentsMargins(18, 16, 18, 16)
        appearance_layout.setSpacing(5)

        appearance_title = QLabel("Theme")
        appearance_title.setObjectName("settings_label")

        appearance_description = QLabel(
            "Synapse currently uses the dark theme. "
            "Additional appearance options will be added here."
        )
        appearance_description.setObjectName(
            "settings_description"
        )
        appearance_description.setWordWrap(True)

        appearance_layout.addWidget(appearance_title)
        appearance_layout.addWidget(appearance_description)

        content_layout.addWidget(appearance_card)
        content_layout.addSpacing(12)

        scroll_area.setWidget(content)
        root.addWidget(scroll_area, 1)

        self.scroll_area = scroll_area
        self.content_widget = content

        # SIGNALS
        self.startup_toggle.toggled.connect(
            self._set_startup_enabled
        )

        self.minimized_toggle.toggled.connect(
            self._save_minimized_setting
        )

    # --------------------------------------------------
    # UI HELPERS
    # --------------------------------------------------

    def _create_section_header(self, title_text, description):
        container = QWidget()

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title = QLabel(title_text)
        title.setObjectName("settings_section_heading")

        subtitle = QLabel(description)
        subtitle.setObjectName("settings_section_subtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)

        return container

    def _create_setting_row(
        self,
        title_text,
        description,
        control
    ):
        row = QWidget()

        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 13, 0, 13)
        layout.setSpacing(20)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)

        title = QLabel(title_text)
        title.setObjectName("settings_label")

        subtitle = QLabel(description)
        subtitle.setObjectName("settings_description")
        subtitle.setWordWrap(True)

        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)

        layout.addLayout(text_layout, 1)

        layout.addWidget(
            control,
            0,
            Qt.AlignmentFlag.AlignVCenter
        )

        return row

    def _create_storage_row(
        self,
        title_text,
        description,
        controls
    ):
        row = QWidget()

        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(7)

        title = QLabel(title_text)
        title.setObjectName("settings_label")

        subtitle = QLabel(description)
        subtitle.setObjectName("settings_description")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(controls)

        return row

    def _create_path_input(self):
        path_input = QLineEdit()
        path_input.setReadOnly(True)
        path_input.setObjectName("settings_path_input")
        path_input.setToolTip(
            "Current storage directory"
        )
        return path_input

    def _create_path_controls(
        self,
        path_input,
        browse_callback,
        open_callback
    ):
        container = QWidget()

        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(path_input, 1)

        browse_button = QPushButton("Browse")
        browse_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        browse_button.setObjectName("settings_path_button")
        browse_button.clicked.connect(browse_callback)

        open_button = QPushButton()
        open_button.setText("Open")
        open_button.setToolTip("Open this folder in File Explorer")
        open_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        open_button.setObjectName("settings_path_button")
        open_button.clicked.connect(open_callback)

        layout.addWidget(browse_button)
        layout.addWidget(open_button)

        return container

    def _create_divider(self):
        divider = QFrame()
        divider.setObjectName("settings_divider")
        divider.setFixedHeight(1)
        return divider

    # --------------------------------------------------
    # STORAGE LOCATIONS
    # --------------------------------------------------

    def _refresh_storage_paths(self):
        workflows_directory = get_workflows_dir()
        logs_directory = get_logs_dir()
        templates_directory = get_templates_dir()

        self.workflows_path_input.setText(
            str(workflows_directory)
        )
        self.workflows_path_input.setToolTip(
            str(workflows_directory)
        )

        self.logs_path_input.setText(
            str(logs_directory)
        )
        self.logs_path_input.setToolTip(
            str(logs_directory)
        )

        self.templates_path_input.setText(
            str(templates_directory)
        )
        self.templates_path_input.setToolTip(
            str(templates_directory)
        )

    def _browse_workflows_directory(self):
        current_directory = get_workflows_dir()

        selected_directory = QFileDialog.getExistingDirectory(
            self,
            "Choose Workflows Folder",
            str(current_directory)
        )

        if not selected_directory:
            return

        try:
            set_workflows_dir(selected_directory)
            self._refresh_storage_paths()

            updated_directory = str(get_workflows_dir())

            self.storage_status.setText(
                "Workflows folder updated. Existing files were not moved."
            )

            self.workflows_directory_changed.emit(
                updated_directory
            )

        except Exception:
            self.storage_status.setText(
                "Could not update the workflows folder."
            )

    def _browse_logs_directory(self):
        current_directory = get_logs_dir()

        selected_directory = QFileDialog.getExistingDirectory(
            self,
            "Choose Logs Folder",
            str(current_directory)
        )

        if not selected_directory:
            return

        try:
            set_logs_dir(selected_directory)
            self._refresh_storage_paths()

            updated_directory = str(get_logs_dir())

            self.storage_status.setText(
                "Logs folder updated. Existing files were not moved."
            )

            self.logs_directory_changed.emit(
                updated_directory
            )

        except Exception:
            self.storage_status.setText(
                "Could not update the logs folder."
            )

    def _browse_templates_directory(self):
        current_directory = get_templates_dir()

        selected_directory = QFileDialog.getExistingDirectory(
            self,
            "Choose Templates Folder",
            str(current_directory)
        )

        if not selected_directory:
            return

        try:
            set_templates_dir(selected_directory)
            self._refresh_storage_paths()

            updated_directory = str(get_templates_dir())

            self.storage_status.setText(
                "Templates folder updated. Existing templates were not moved."
            )

            self.templates_directory_changed.emit(
                updated_directory
            )

        except Exception:
            self.storage_status.setText(
                "Could not update the templates folder."
            )

    def _open_workflows_directory(self):
        self._open_directory(get_workflows_dir())

    def _open_logs_directory(self):
        self._open_directory(get_logs_dir())

    def _open_templates_directory(self):
        self._open_directory(get_templates_dir())

    @staticmethod
    def _open_directory(directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(directory.resolve()))
        )

    # --------------------------------------------------
    # SETTINGS
    # --------------------------------------------------

    def _load_settings(self):
        if self.startup_registry is not None:
            self.startup_registry.sync()

            startup_enabled = (
                self.startup_registry.contains(
                    "Synapse"
                )
            )

            if startup_enabled:
                startup_command = self._get_startup_command()

                if startup_command is None:
                    self.startup_registry.remove("Synapse")
                    self.startup_registry.sync()
                    startup_enabled = False

                    self.settings_status.setText(
                        "Could not find Synapse.exe. "
                        "Windows startup has been disabled."
                    )
                else:
                    self.startup_registry.setValue(
                        "Synapse",
                        startup_command
                    )
                    self.startup_registry.sync()

                    if (
                        self.startup_registry.status()
                        != QSettings.Status.NoError
                    ):
                        self.settings_status.setText(
                            "Could not update the Windows startup command."
                        )

            self.startup_toggle.setChecked(startup_enabled)

            self.minimized_toggle.setChecked(
                self.settings.value(
                    "general/start_minimized",
                    False,
                    type=bool
                )
            )

            self.minimized_toggle.setEnabled(startup_enabled)

            if startup_enabled:
                self.settings_status.setText(
                    "Synapse.exe will launch when you sign in."
                )
            elif not self.settings_status.text():
                self.settings_status.setText(
                    "Startup launch is currently disabled."
                )

        else:
            self.startup_toggle.setEnabled(False)
            self.minimized_toggle.setEnabled(False)

            self.settings_status.setText(
                "Windows startup options are only available on Windows."
            )

    def _set_startup_enabled(self, enabled):
        if self.startup_registry is None:
            return

        if enabled:
            startup_command = self._get_startup_command()

            if startup_command is None:
                self.startup_toggle.blockSignals(True)
                self.startup_toggle.setChecked(False)
                self.startup_toggle.blockSignals(False)

                self.settings_status.setText(
                    "Could not find Synapse.exe. "
                    "Place the packaged executable in the Synapse "
                    "project folder before enabling startup."
                )
                return

            self.startup_registry.setValue(
                "Synapse",
                startup_command
            )
        else:
            self.startup_registry.remove("Synapse")

        self.startup_registry.sync()

        if (
            self.startup_registry.status()
            != QSettings.Status.NoError
        ):
            self.startup_toggle.blockSignals(True)
            self.startup_toggle.setChecked(not enabled)
            self.startup_toggle.blockSignals(False)

            self.settings_status.setText(
                "Could not update the Windows startup setting."
            )
            return

        self.minimized_toggle.setEnabled(enabled)

        if enabled:
            self.settings_status.setText(
                "Synapse.exe will launch when you sign in."
            )
        else:
            self.settings_status.setText(
                "Startup launch is currently disabled."
            )

    def _save_minimized_setting(self, enabled):
        self.settings.setValue(
            "general/start_minimized",
            enabled
        )
        self.settings.sync()

    def _get_startup_command(self):
        if getattr(sys, "frozen", False):
            executable = Path(sys.executable).resolve()

        else:
            project_directory = (
                Path(__file__).resolve().parent.parent
            )

            executable = project_directory / "Synapse.exe"

        if not executable.is_file():
            return None

        command = [
            str(executable),
            "--startup"
        ]

        return subprocess.list2cmdline(command)
