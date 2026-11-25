
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)


class ActivityPanel(QFrame):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.expanded = False
        self.setObjectName("activity_panel")

        self.setStyleSheet("""
            QFrame#activity_panel {
                background-color: #1d2028;
                border: 1px solid #303540;
                border-radius: 9px;
            }
            QLabel#activity_heading {
                color: #e5e7eb;
                font-size: 10pt;
                font-weight: 600;
                border: none;
                background: transparent;
            }
            QLabel#activity_count {
                color: #9299a7;
                font-size: 8pt;
                border: none;
                background: transparent;
            }
            QLabel#activity_empty {
                color: #858c99;
                font-size: 9pt;
                border: none;
                background: transparent;
                padding: 8px 2px;
            }
            QLabel#activity_entry_title {
                color: #d7dae0;
                font-size: 9pt;
                font-weight: 600;
                border: none;
                background: transparent;
            }
            QLabel#activity_entry_message {
                color: #9299a7;
                font-size: 8pt;
                border: none;
                background: transparent;
            }
            QLabel#activity_entry_time {
                color: #777f8d;
                font-size: 8pt;
                border: none;
                background: transparent;
            }
            QPushButton#activity_toggle {
                background: transparent;
                color: #aeb5c2;
                border: none;
                padding: 4px 8px;
                font-size: 9pt;
            }
            QPushButton#activity_toggle:hover {
                background-color: #292e38;
                border-radius: 5px;
            }
        """)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(12, 7, 12, 7)
        outer_layout.setSpacing(5)

        header = QHBoxLayout()
        header.setSpacing(8)

        heading = QLabel("Activity")
        heading.setObjectName("activity_heading")

        self.count_label = QLabel("No recent events")
        self.count_label.setObjectName("activity_count")

        self.toggle_button = QPushButton("Show")
        self.toggle_button.setObjectName("activity_toggle")
        self.toggle_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.toggle_button.clicked.connect(
            self.toggle_expanded
        )

        header.addWidget(heading)
        header.addWidget(self.count_label)
        header.addStretch()
        header.addWidget(self.toggle_button)

        outer_layout.addLayout(header)

        self.body = QWidget()
        self.body.setStyleSheet(
            "background: transparent; border: none;"
        )

        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(2, 2, 2, 2)
        self.body_layout.setSpacing(7)

        self.empty_label = QLabel(
            "Workflow activity will appear here."
        )
        self.empty_label.setObjectName("activity_empty")
        self.body_layout.addWidget(self.empty_label)

        self.body.hide()
        outer_layout.addWidget(self.body)

        self.history = []

    def toggle_expanded(self):
        self.expanded = not self.expanded
        self.body.setVisible(self.expanded)

        self.toggle_button.setText(
            "Hide" if self.expanded else "Show"
        )

        self.updateGeometry()

    def set_history(self, history):
        self.history = list(history or [])

        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()

            if widget:
                widget.deleteLater()

        if not self.history:
            self.empty_label = QLabel(
                "Workflow activity will appear here."
            )
            self.empty_label.setObjectName("activity_empty")
            self.body_layout.addWidget(self.empty_label)

        else:
            for activity in self.history[:8]:
                self._add_entry(activity)

        count = len(self.history)

        self.count_label.setText(
            f"{count} recent event"
            + ("" if count == 1 else "s")
        )

    def _add_entry(self, activity):
        row = QHBoxLayout()
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(12)

        details = QVBoxLayout()
        details.setSpacing(2)

        title = QLabel(
            str(activity.get("title", "Workflow activity"))
        )
        title.setObjectName("activity_entry_title")

        message = QLabel(
            str(activity.get("message", ""))
        )
        message.setObjectName("activity_entry_message")
        message.setWordWrap(True)

        details.addWidget(title)
        details.addWidget(message)

        timestamp = str(activity.get("timestamp", ""))

        try:
            from datetime import datetime

            parsed = datetime.fromisoformat(timestamp)
            timestamp = parsed.astimezone().strftime(
                "%I:%M:%S %p"
            )
        except (TypeError, ValueError):
            pass

        time_label = QLabel(timestamp)
        time_label.setObjectName("activity_entry_time")
        time_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter
        )

        row.addLayout(details, 1)
        row.addWidget(
            time_label,
            0,
            Qt.AlignmentFlag.AlignTop
        )

        container = QWidget()
        container.setStyleSheet(
            "background: transparent; border: none;"
        )
        container.setLayout(row)

        self.body_layout.addWidget(container)
