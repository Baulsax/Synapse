
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
)


def format_size(size):
    size = max(0, int(size))

    if size >= 1024 ** 3:
        return f"{size / (1024 ** 3):.2f} GB"

    if size >= 1024 ** 2:
        return f"{size / (1024 ** 2):.1f} MB"

    if size >= 1024:
        return f"{size / 1024:.1f} KB"

    return f"{size} bytes"


class UpdateDialog(QWidget):
    download_requested = Signal()
    restart_requested = Signal()
    install_on_exit_requested = Signal()
    later_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("update_overlay")
        self.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )

        self.current_version = "0.0.0"
        self.new_version = "0.0.0"
        self.package_size = 0

        self.download_complete = False
        self.download_active = False
        self.error_state = False

        self._build_ui()

        self.hide()

    def _build_ui(self):
        self.setStyleSheet("""
            QWidget#update_overlay {
                background: rgba(0, 0, 0, 165);
            }

            QFrame#update_panel {
                background: #20232b;
                border: 1px solid #373b47;
                border-radius: 12px;
            }

            QLabel#update_title {
                color: #f2f0f7;
                font-size: 17px;
                font-weight: 700;
            }

            QLabel#update_description {
                color: #aeb3c0;
                font-size: 10pt;
            }

            QLabel#update_versions {
                color: #e5e7eb;
                background: #191c23;
                border: 1px solid #30343e;
                border-radius: 7px;
                padding: 12px;
                font-size: 10pt;
            }

            QLabel#update_status {
                color: #aeb3c0;
                font-size: 9pt;
            }

            QProgressBar {
                background: #17191f;
                border: 1px solid #343844;
                border-radius: 5px;
                height: 9px;
                text-align: center;
            }

            QProgressBar::chunk {
                background: #a78bfa;
                border-radius: 4px;
            }

            QPushButton {
                min-height: 34px;
                border-radius: 6px;
                padding: 0 14px;
                font-weight: 600;
            }

            QPushButton#update_primary {
                background: #a78bfa;
                color: #17191f;
                border: none;
            }

            QPushButton#update_primary:hover {
                background: #b9a2ff;
            }

            QPushButton#update_primary:disabled {
                background: #494255;
                color: #a6a0b4;
            }

            QPushButton#update_secondary {
                background: #292d37;
                color: #d7d9e0;
                border: 1px solid #3b404c;
            }

            QPushButton#update_secondary:hover {
                background: #343946;
            }

            QPushButton#update_gold {
                background: #b88b38;
                color: #17191f;
                border: none;
            }

            QPushButton#update_gold:hover {
                background: #d0a34d;
            }
        """)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(20, 20, 20, 20)
        outer_layout.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.panel = QFrame()
        self.panel.setObjectName("update_panel")
        self.panel.setFixedWidth(470)

        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(
            26, 24, 26, 22
        )
        panel_layout.setSpacing(15)

        self.title_label = QLabel("Synapse Update")
        self.title_label.setObjectName("update_title")

        panel_layout.addWidget(self.title_label)

        self.description_label = QLabel(
            "A new version of Synapse is available."
        )
        self.description_label.setObjectName(
            "update_description"
        )
        self.description_label.setWordWrap(True)

        panel_layout.addWidget(
            self.description_label
        )

        self.versions_label = QLabel()
        self.versions_label.setObjectName(
            "update_versions"
        )
        self.versions_label.setWordWrap(True)

        panel_layout.addWidget(
            self.versions_label
        )

        self.size_label = QLabel()
        self.size_label.setObjectName(
            "update_description"
        )

        panel_layout.addWidget(
            self.size_label
        )

        self.status_label = QLabel("")
        self.status_label.setObjectName(
            "update_status"
        )
        self.status_label.setWordWrap(True)

        panel_layout.addWidget(
            self.status_label
        )

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()

        panel_layout.addWidget(
            self.progress_bar
        )

        self.progress_detail = QLabel("")
        self.progress_detail.setObjectName(
            "update_status"
        )
        self.progress_detail.hide()

        panel_layout.addWidget(
            self.progress_detail
        )

        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        self.primary_button = QPushButton(
            "Download Update"
        )
        self.primary_button.setObjectName(
            "update_primary"
        )
        self.primary_button.clicked.connect(
            self._on_primary_clicked
        )

        self.secondary_button = QPushButton(
            "Maybe Later"
        )
        self.secondary_button.setObjectName(
            "update_secondary"
        )
        self.secondary_button.clicked.connect(
            self._on_secondary_clicked
        )

        button_layout.addWidget(
            self.secondary_button
        )
        button_layout.addWidget(
            self.primary_button
        )

        panel_layout.addLayout(
            button_layout
        )

        self.exit_button = QPushButton(
            "Install When I Close Synapse"
        )
        self.exit_button.setObjectName(
            "update_secondary"
        )
        self.exit_button.clicked.connect(
            self.install_on_exit_requested.emit
        )
        self.exit_button.hide()

        panel_layout.addWidget(
            self.exit_button
        )

        outer_layout.addWidget(
            self.panel
        )

    # ======================================
    # BUTTON HANDLING
    # ======================================

    def _on_primary_clicked(self):
        if self.error_state:
            self.hide()
            return

        if self.download_active:
            return

        if self.download_complete:
            self.restart_requested.emit()
            return

        self.download_requested.emit()

    def _on_secondary_clicked(self):
        self.hide()
        self.later_requested.emit()

    # ======================================
    # UPDATE INFORMATION
    # ======================================

    def show_update(
        self,
        current_version,
        new_version,
        package_size,
        release_notes="",
    ):
        self.current_version = str(
            current_version
        )

        self.new_version = str(
            new_version
        )

        self.package_size = max(
            0,
            int(package_size or 0),
        )

        self.download_complete = False
        self.download_active = False
        self.error_state = False

        self.title_label.setText(
            "A Synapse Update Is Available"
        )

        self.description_label.setText(
            "A newer version is ready to download. "
            "Your workflows and settings will be preserved."
        )

        self.versions_label.setText(
            f"Current version:  {self.current_version}\n"
            f"New version:       {self.new_version}"
        )

        self.size_label.setText(
            f"Download size: {format_size(self.package_size)}"
        )

        if release_notes:
            notes = str(
                release_notes
            ).strip()

            if len(notes) > 1200:
                notes = (
                    notes[:1200].rstrip()
                    + "…"
                )

            self.status_label.setText(
                notes
            )

        else:
            self.status_label.setText(
                "You can continue using Synapse while "
                "the update downloads."
            )

        self.progress_bar.setValue(0)
        self.progress_bar.hide()

        self.progress_detail.clear()
        self.progress_detail.hide()

        self.exit_button.hide()

        self.primary_button.setText(
            "Download Update"
        )
        self.primary_button.setEnabled(True)

        self.secondary_button.setText(
            "Maybe Later"
        )
        self.secondary_button.show()

        self.show()
        self.raise_()

    # ======================================
    # DOWNLOAD
    # ======================================

    def set_download_started(self):
        self.download_active = True
        self.download_complete = False
        self.error_state = False

        self.title_label.setText(
            "Downloading Update"
        )

        self.description_label.setText(
            "Synapse is downloading the update in the "
            "background. You can continue working."
        )

        self.status_label.setText(
            "Please keep Synapse open until the download finishes."
        )

        self.progress_bar.setValue(0)
        self.progress_bar.show()

        self.progress_detail.setText(
            "Preparing download…"
        )
        self.progress_detail.show()

        self.primary_button.setText(
            "Downloading…"
        )
        self.primary_button.setEnabled(False)

        self.secondary_button.setText(
            "Hide"
        )
        self.secondary_button.show()

        self.exit_button.hide()

    def set_download_progress(
        self,
        downloaded,
        total,
    ):
        downloaded = max(
            0,
            int(downloaded),
        )

        total = max(
            0,
            int(total),
        )

        if total > 0:
            percentage = min(
                100,
                int(downloaded * 100 / total),
            )

            self.progress_bar.setValue(
                percentage
            )

            self.progress_detail.setText(
                f"{format_size(downloaded)} / "
                f"{format_size(total)}  ·  "
                f"{percentage}%"
            )

        else:
            self.progress_detail.setText(
                f"{format_size(downloaded)} downloaded"
            )

    # ======================================
    # COMPLETED DOWNLOAD
    # ======================================

    def set_download_complete(self):
        self.download_active = False
        self.download_complete = True
        self.error_state = False

        self.title_label.setText(
            "Update Ready"
        )

        self.description_label.setText(
            "The update has been downloaded and verified. "
            "Choose when you want to apply it."
        )

        self.status_label.setText(
            "Restart & Update will close Synapse, apply "
            "the update, and reopen the application."
        )

        self.progress_bar.setValue(100)
        self.progress_bar.show()

        self.progress_detail.setText(
            "Download complete · Verification successful"
        )
        self.progress_detail.show()

        self.primary_button.setText(
            "Restart & Update"
        )
        self.primary_button.setEnabled(True)

        self.secondary_button.setText(
            "Maybe Later"
        )
        self.secondary_button.show()

        self.exit_button.show()

        self.show()
        self.raise_()

    # ======================================
    # ERRORS
    # ======================================

    def set_error(self, message):
        self.download_active = False
        self.download_complete = False
        self.error_state = True

        self.title_label.setText(
            "Update Problem"
        )

        self.description_label.setText(
            "Synapse couldn't complete the update operation."
        )

        self.status_label.setText(
            str(message)
        )

        self.progress_bar.hide()
        self.progress_detail.hide()
        self.exit_button.hide()

        self.primary_button.setText(
            "Close"
        )
        self.primary_button.setEnabled(True)

        self.secondary_button.hide()

        self.show()
        self.raise_()

    # ======================================
    # LAYOUT
    # ======================================

    def resizeEvent(self, event):
        super().resizeEvent(event)

        self.panel.setMaximumHeight(
            max(300, self.height() - 40)
        )
