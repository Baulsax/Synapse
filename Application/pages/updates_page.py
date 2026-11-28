import json
import urllib.request
from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QListWidget,
    QListWidgetItem,
    QTextBrowser,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
)


RELEASES_URL = (
    "https://api.github.com/repos/Baulsax/Synapse/releases"
)


class ReleaseHistoryWorker(QThread):
    """Fetch published GitHub releases without blocking the UI."""

    releases_loaded = Signal(list)
    failed = Signal(str)

    def run(self):
        try:
            request = urllib.request.Request(
                RELEASES_URL,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "Synapse-Updater",
                },
            )

            with urllib.request.urlopen(
                request,
                timeout=15,
            ) as response:
                releases = json.loads(
                    response.read().decode("utf-8")
                )

            if not isinstance(releases, list):
                raise ValueError(
                    "GitHub returned an unexpected release list."
                )

            published = [
                release
                for release in releases
                if isinstance(release, dict)
                and not release.get("draft", False)
                and not release.get("prerelease", False)
            ]

            self.releases_loaded.emit(published)

        except Exception as error:
            self.failed.emit(str(error))


class UpdatesPage(QWidget):
    """Dedicated Synapse update status and release history page."""

    check_requested = Signal()
    update_details_requested = Signal()

    def __init__(self, current_version, parent=None):
        super().__init__(parent)

        self.current_version = current_version
        self._releases = []
        self._release_worker = None

        self.setObjectName("updates_page")

        # Match the Settings page's outer layout.
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("updates_scroll_area")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll_area.setAlignment(
            Qt.AlignmentFlag.AlignHCenter
            | Qt.AlignmentFlag.AlignTop
        )

        self.scroll_area.setStyleSheet("""
            QScrollArea#updates_scroll_area {
                background: transparent;
                border: none;
            }

            QWidget#qt_scrollarea_viewport {
                background: transparent;
            }

            QWidget#updates_content {
                background: transparent;
            }
        """)

        self.scroll_area.viewport().setAutoFillBackground(False)

        content = QWidget()
        content.setObjectName("updates_content")
        content.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )
        content.setAutoFillBackground(False)
        content.setMinimumWidth(600)
        content.setMaximumWidth(760)

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Page heading.
        heading = QLabel("Updates")
        heading.setObjectName("page_heading")

        subtitle = QLabel(
            "Keep Synapse up to date and see what's changed."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)

        content_layout.addWidget(heading)
        content_layout.addSpacing(5)
        content_layout.addWidget(subtitle)
        content_layout.addSpacing(30)

        # Current version and update status.
        status_card = QFrame()
        status_card.setObjectName("updates_card")

        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(20, 18, 20, 18)
        status_layout.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        version_column = QVBoxLayout()
        version_column.setSpacing(4)

        version_caption = QLabel("INSTALLED VERSION")
        version_caption.setObjectName("updates_caption")

        self.version_label = QLabel(
            f"Version {self.current_version}"
        )
        self.version_label.setObjectName("updates_version")

        version_column.addWidget(version_caption)
        version_column.addWidget(self.version_label)

        top_row.addLayout(version_column)
        top_row.addStretch()

        self.status_label = QLabel("Waiting for update check")
        self.status_label.setObjectName("updates_status")
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter
        )
        self.status_label.setWordWrap(True)

        top_row.addWidget(self.status_label)

        status_layout.addLayout(top_row)

        self.status_description = QLabel(
            "Check GitHub to see whether a newer version is available."
        )
        self.status_description.setObjectName("muted")
        self.status_description.setWordWrap(True)

        status_layout.addWidget(self.status_description)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("updates_progress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()

        status_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        self.progress_label.setObjectName("muted")
        self.progress_label.hide()

        status_layout.addWidget(self.progress_label)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.check_button = QPushButton("Check for Update")
        self.check_button.setObjectName("primary_button")
        self.check_button.setMinimumHeight(38)
        self.check_button.clicked.connect(
            self.check_requested.emit
        )

        self.view_update_button = QPushButton("View Update")
        self.view_update_button.setObjectName("secondary_button")
        self.view_update_button.setMinimumHeight(38)
        self.view_update_button.clicked.connect(
            self.update_details_requested.emit
        )
        self.view_update_button.hide()

        action_row.addWidget(self.check_button)
        action_row.addWidget(self.view_update_button)
        action_row.addStretch()

        status_layout.addLayout(action_row)

        content_layout.addWidget(status_card)
        content_layout.addSpacing(30)

        # Release history heading.
        history_heading = QHBoxLayout()
        history_heading.setSpacing(10)

        history_title = QLabel("Release History")
        history_title.setObjectName("section_heading")

        self.history_status = QLabel("Loading releases…")
        self.history_status.setObjectName("muted")

        history_heading.addWidget(history_title)
        history_heading.addStretch()
        history_heading.addWidget(self.history_status)

        content_layout.addLayout(history_heading)
        content_layout.addSpacing(12)

        # Release history card.
        history_card = QFrame()
        history_card.setObjectName("updates_card")
        history_card.setMinimumHeight(330)
        history_card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        history_layout = QHBoxLayout(history_card)
        history_layout.setContentsMargins(12, 12, 12, 12)
        history_layout.setSpacing(12)

        self.release_list = QListWidget()
        self.release_list.setObjectName("release_list")
        self.release_list.setMinimumWidth(190)
        self.release_list.setMaximumWidth(235)
        self.release_list.setMinimumHeight(300)
        self.release_list.currentRowChanged.connect(
            self._show_selected_release
        )

        self.release_notes = QTextBrowser()
        self.release_notes.setObjectName("release_notes")
        self.release_notes.setOpenExternalLinks(True)
        self.release_notes.setPlaceholderText(
            "Select a release to view its notes."
        )
        self.release_notes.setMinimumWidth(0)
        self.release_notes.setMinimumHeight(300)

        history_layout.addWidget(self.release_list)
        history_layout.addWidget(self.release_notes, 1)

        content_layout.addWidget(history_card, 1)
        content_layout.addStretch(1)

        self.scroll_area.setWidget(content)
        root.addWidget(self.scroll_area, 1)

        self.content_widget = content

        self.setStyleSheet("""
            QWidget#updates_page {
                background: #17191f;
            }

            QScrollArea#updates_scroll_area {
                background: transparent;
                border: none;
            }

            QWidget#updates_content {
                background: transparent;
            }

            QLabel#page_heading {
                color: #f2f0f7;
                font-size: 23px;
                font-weight: 700;
            }

            QLabel#section_heading {
                color: #f2f0f7;
                font-size: 16px;
                font-weight: 650;
            }

            QLabel#muted {
                color: #9298a6;
                font-size: 12px;
            }

            QFrame#updates_card {
                background: #20232b;
                border: 1px solid #30343e;
                border-radius: 9px;
            }

            QLabel#updates_caption {
                color: #9298a6;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }

            QLabel#updates_version {
                color: #f2f0f7;
                font-size: 25px;
                font-weight: 700;
            }

            QLabel#updates_status {
                color: #b9a2ff;
                font-size: 13px;
                font-weight: 650;
            }

            QPushButton#primary_button {
                color: #17131f;
                background: #b9a2ff;
                border: none;
                border-radius: 6px;
                padding: 0 16px;
                font-size: 12px;
                font-weight: 650;
            }

            QPushButton#primary_button:hover {
                background: #c8b7ff;
            }

            QPushButton#primary_button:disabled {
                color: #777180;
                background: #393541;
            }

            QPushButton#secondary_button {
                color: #d8d2e8;
                background: #2b2e38;
                border: 1px solid #45404f;
                border-radius: 6px;
                padding: 0 16px;
                font-size: 12px;
                font-weight: 600;
            }

            QPushButton#secondary_button:hover {
                background: #35313f;
                border-color: #76649c;
            }

            QListWidget#release_list {
                color: #c4c8d2;
                background: #1a1d24;
                border: 1px solid #30343e;
                border-radius: 6px;
                outline: none;
                padding: 4px;
            }

            QListWidget#release_list::item {
                padding: 10px 8px;
                border-radius: 4px;
            }

            QListWidget#release_list::item:hover {
                background: #292d37;
            }

            QListWidget#release_list::item:selected {
                color: #e6ddff;
                background: #373044;
            }

            QTextBrowser#release_notes {
                color: #c4c8d2;
                background: #1a1d24;
                border: 1px solid #30343e;
                border-radius: 6px;
                padding: 12px;
                font-size: 12px;
            }

            QProgressBar#updates_progress {
                color: #eee9fa;
                background: #17191f;
                border: 1px solid #30343e;
                border-radius: 4px;
                height: 8px;
                text-align: center;
            }

            QProgressBar#updates_progress::chunk {
                background: #a78bfa;
                border-radius: 3px;
            }

            QScrollBar:vertical {
                background: #17191f;
                width: 9px;
                margin: 0;
            }

            QScrollBar::handle:vertical {
                background: #3b3f4b;
                min-height: 28px;
                border-radius: 4px;
            }

            QScrollBar::handle:vertical:hover {
                background: #555b6a;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }

            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)

        self.load_release_history()

    def load_release_history(self):
        if (
            self._release_worker is not None
            and self._release_worker.isRunning()
        ):
            return

        self.history_status.setText("Loading releases…")

        worker = ReleaseHistoryWorker(self)
        worker.releases_loaded.connect(self.set_releases)
        worker.failed.connect(self.set_release_history_error)
        worker.finished.connect(worker.deleteLater)

        self._release_worker = worker
        worker.start()

    def set_releases(self, releases):
        self._releases = releases
        self.release_list.clear()

        if not releases:
            self.history_status.setText("No releases found")
            self.release_notes.setMarkdown(
                "No published releases were found."
            )
            return

        self.history_status.setText(
            f"{len(releases)} release"
            f"{'s' if len(releases) != 1 else ''}"
        )

        for release in releases:
            version = (
                release.get("tag_name")
                or release.get("name")
                or "Unknown version"
            )

            published_at = self._format_date(
                release.get("published_at", "")
            )

            item = QListWidgetItem(
                f"{version}\n{published_at}"
            )
            item.setData(
                Qt.ItemDataRole.UserRole,
                release,
            )

            self.release_list.addItem(item)

        self.release_list.setCurrentRow(0)

    def set_release_history_error(self, message):
        self.history_status.setText(
            "Could not load release history"
        )
        self.release_notes.setMarkdown(
            "### Release history unavailable\n\n"
            f"{message}\n\n"
            "You can try again by reopening the Updates page."
        )

    def _show_selected_release(self, row):
        if row < 0 or row >= len(self._releases):
            return

        release = self._releases[row]

        name = (
            release.get("name")
            or release.get("tag_name")
            or "Unknown release"
        )

        tag = release.get("tag_name", "")
        published = self._format_date(
            release.get("published_at", "")
        )
        body = release.get("body") or "No release notes were provided."

        heading = f"# {name}"

        if tag and tag != name:
            heading += f"\n\n**Version:** {tag}"

        if published:
            heading += f"\n\n**Released:** {published}"

        self.release_notes.setMarkdown(
            f"{heading}\n\n---\n\n{body}"
        )

    @staticmethod
    def _format_date(value):
        if not value:
            return "Date unavailable"

        try:
            parsed = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )
            return parsed.strftime("%b %d, %Y")
        except (TypeError, ValueError):
            return str(value)

    def set_checking(self):
        self.status_label.setText("Checking for updates…")
        self.status_description.setText(
            "Contacting GitHub to check the latest published version."
        )
        self.check_button.setText("Checking…")
        self.check_button.setEnabled(False)

    def set_up_to_date(self, version):
        self.status_label.setText("You're up to date")
        self.status_description.setText(
            f"You're running the latest version of Synapse ({version})."
        )
        self.check_button.setText("Check Again")
        self.check_button.setEnabled(True)
        self.view_update_button.hide()

    def set_update_available(self, metadata):
        version = metadata.get("version", "unknown")

        self.status_label.setText(
            f"Update available · {version}"
        )
        self.status_description.setText(
            f"Synapse {version} is available. "
            "View the update details to download and install it."
        )
        self.check_button.setText("Check Again")
        self.check_button.setEnabled(True)
        self.view_update_button.show()

    def set_check_failed(self, message):
        self.status_label.setText("Update check failed")
        self.status_description.setText(
            f"Could not check for updates: {message}"
        )
        self.check_button.setText("Try Again")
        self.check_button.setEnabled(True)

    def set_unavailable(self, message):
        """Display the expected limitation of a development build."""

        self.status_label.setText(
            "Unavailable in development build"
        )
        self.status_description.setText(message)
        self.check_button.setText("Installed Version Only")
        self.check_button.setEnabled(False)
        self.view_update_button.hide()

    def set_download_started(self):
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.progress_label.setText("Preparing download…")
        self.progress_label.show()
        self.check_button.setEnabled(False)

    def set_download_progress(self, downloaded, total):
        if total > 0:
            percentage = int(downloaded * 100 / total)
            self.progress_bar.setValue(
                max(0, min(100, percentage))
            )
            self.progress_label.setText(
                f"{self._format_size(downloaded)} / "
                f"{self._format_size(total)} · {percentage}%"
            )
        else:
            self.progress_label.setText(
                f"{self._format_size(downloaded)} downloaded"
            )

        self.progress_bar.show()
        self.progress_label.show()

    def set_download_complete(self):
        self.progress_bar.setValue(100)
        self.progress_bar.show()
        self.progress_label.setText(
            "Download complete. Ready to install."
        )
        self.progress_label.show()
        self.check_button.setEnabled(True)

    def set_download_failed(self, message):
        self.progress_bar.hide()
        self.progress_label.hide()
        self.check_button.setEnabled(True)
        self.status_description.setText(message)

    @staticmethod
    def _format_size(size):
        size = max(0, int(size))

        if size >= 1024 ** 3:
            return f"{size / (1024 ** 3):.2f} GB"

        if size >= 1024 ** 2:
            return f"{size / (1024 ** 2):.1f} MB"

        return f"{size / 1024:.0f} KB"