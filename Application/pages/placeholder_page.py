from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QFrame,
)


class PlaceholderPage(QWidget):
    def __init__(self, title, description):
        super().__init__()

        layout = QVBoxLayout(self)

        # Page heading
        header = QLabel(title)
        header.setObjectName("page_title")
        header.setFixedHeight(55)

        layout.addWidget(header)

        # Page content
        content = QFrame()
        content.setObjectName("canvas")

        content_layout = QVBoxLayout(content)

        placeholder = QLabel(description)
        placeholder.setObjectName("muted")

        content_layout.addWidget(placeholder)

        layout.addWidget(content, 1)