
import logging

from PySide6.QtCore import QObject, Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
)


logger = logging.getLogger(__name__)


class WorkflowUIRuntime(QObject):

    request_received = Signal(str, str, object)
    button_clicked = Signal(str, str)

    window_closed = Signal(str)

    AUTO_WIDGET_SPACING = 10
    AUTO_WIDGET_TOP = 10
    AUTO_WIDGET_SIDE = 10
    AUTO_WIDGET_HEIGHT = 30

    def __init__(self, parent=None):
        super().__init__(parent)

        self.windows = {}
        self.widgets = {}

        self.request_received.connect(
            self._dispatch,
            Qt.ConnectionType.QueuedConnection
        )

    def submit(self, workflow_id, action, payload):
        self.request_received.emit(
            str(workflow_id),
            str(action),
            payload
        )

    @Slot(str, str, object)
    def _dispatch(self, workflow_id, action, payload):
        try:
            handlers = {
                "create_window": self._create_window,
                "create_label": self._create_label,
                "create_button": self._create_button,
                "set_text": self._set_text,
                "close_window": self._close_window,
            }

            handler = handlers.get(action)

            if handler is None:
                logger.warning(
                    "Unknown UI action: %s",
                    action
                )
                return

            handler(workflow_id, payload or {})

        except Exception:
            logger.exception(
                "UI operation failed: %s",
                action
            )

    # ======================================
    # WINDOW MANAGEMENT
    # ======================================

    def _create_window(self, workflow_id, payload):
        window_id = str(payload.get("window_id", ""))

        if not window_id:
            return

        existing_window = self._get_window(
            workflow_id,
            window_id
        )

        if existing_window is not None:
            if existing_window.isVisible():
                existing_window.setWindowTitle(
                    str(payload.get("title") or "Workflow Window")
                )

                window_width = self._safe_dimension(
                    payload.get("width", 400),
                    400
                )

                window_height = self._safe_dimension(
                    payload.get("height", 300),
                    300
                )

                existing_window.resize(
                    window_width,
                    window_height
                )

                self._refresh_auto_widgets(
                    workflow_id,
                    window_id
                )

                existing_window.show()
                existing_window.raise_()
                existing_window.activateWindow()
                return

            self._forget_window(
                workflow_id,
                window_id,
                existing_window,
                notify=False
            )

        window = QWidget()

        window.setAttribute(
            Qt.WidgetAttribute.WA_DeleteOnClose,
            True
        )

        window.setWindowTitle(
            str(payload.get("title") or "Workflow Window")
        )

        width = self._safe_dimension(
            payload.get("width", 400),
            400
        )

        height = self._safe_dimension(
            payload.get("height", 300),
            300
        )

        window.resize(width, height)

        self.windows.setdefault(
            workflow_id, {}
        )[window_id] = window

        self.widgets.setdefault(
            workflow_id, {}
        )[window_id] = {}

        window.destroyed.connect(
            lambda *_,
            wid=workflow_id,
            win_id=window_id,
            win=window: self._forget_window(
                wid,
                win_id,
                win
            )
        )

        window.show()

    def _close_window(self, workflow_id, payload):
        window_id = str(payload.get("window_id", ""))

        window = self._get_window(
            workflow_id,
            window_id
        )

        if window is not None:
            window.close()

    def _forget_window(
        self,
        workflow_id,
        window_id,
        window=None,
        notify=True
    ):
        workflow_windows = self.windows.get(
            workflow_id,
            {}
        )

        if window is not None:
            if workflow_windows.get(window_id) is not window:
                return

        workflow_windows.pop(window_id, None)

        workflow_widgets = self.widgets.get(
            workflow_id,
            {}
        )

        workflow_widgets.pop(window_id, None)

        if not workflow_windows:
            self.windows.pop(workflow_id, None)

        if not workflow_widgets:
            self.widgets.pop(workflow_id, None)

        if notify and not workflow_windows:
            self.window_closed.emit(workflow_id)

    def close_workflow_windows(self, workflow_id):
        """Close every window belonging to a workflow."""
        workflow_windows = list(
            self.windows.get(workflow_id, {}).values()
        )

        for window in workflow_windows:
            if window is not None:
                window.close()

    def close_all_windows(self):
        """Close every workflow-created window."""
        all_windows = [
            window
            for workflow_windows in self.windows.values()
            for window in workflow_windows.values()
        ]

        for window in all_windows:
            if window is not None:
                window.close()

    # ======================================
    # WIDGET MANAGEMENT
    # ======================================

    def _create_label(self, workflow_id, payload):
        window_id = str(payload.get("window_id", ""))
        widget_id = str(payload.get("widget_id", ""))

        window = self._get_window(
            workflow_id,
            window_id
        )

        if window is None or not widget_id:
            return

        text = self._safe_text(
            payload.get("text")
        )

        existing_widget = self._get_widget(
            workflow_id,
            window_id,
            widget_id
        )

        if isinstance(existing_widget, QLabel):
            existing_widget.setText(text)

            self._apply_widget_geometry(
                workflow_id,
                window_id,
                widget_id,
                existing_widget,
                payload
            )
            return

        if existing_widget is not None:
            self._remove_widget(
                workflow_id,
                window_id,
                widget_id
            )

        label = QLabel(text, window)

        self._register_widget(
            workflow_id,
            window_id,
            widget_id,
            label
        )

        self._apply_widget_geometry(
            workflow_id,
            window_id,
            widget_id,
            label,
            payload
        )

        label.show()

    def _create_button(self, workflow_id, payload):
        window_id = str(payload.get("window_id", ""))
        widget_id = str(payload.get("widget_id", ""))

        window = self._get_window(
            workflow_id,
            window_id
        )

        if window is None or not widget_id:
            return

        text = self._safe_text(
            payload.get("text")
        )

        existing_widget = self._get_widget(
            workflow_id,
            window_id,
            widget_id
        )

        if isinstance(existing_widget, QPushButton):
            existing_widget.setText(text)

            self._apply_widget_geometry(
                workflow_id,
                window_id,
                widget_id,
                existing_widget,
                payload
            )
            return

        if existing_widget is not None:
            self._remove_widget(
                workflow_id,
                window_id,
                widget_id
            )

        button = QPushButton(text, window)

        button.clicked.connect(
            lambda checked=False,
            wid=workflow_id,
            bid=widget_id:
            self.button_clicked.emit(wid, bid)
        )

        self._register_widget(
            workflow_id,
            window_id,
            widget_id,
            button
        )

        self._apply_widget_geometry(
            workflow_id,
            window_id,
            widget_id,
            button,
            payload
        )

        button.show()

    def _set_text(self, workflow_id, payload):
        widget_id = str(payload.get("widget_id", ""))

        text = self._safe_text(
            payload.get("text")
        )

        widget = self._find_widget(
            workflow_id,
            widget_id
        )

        if widget is None:
            return

        if isinstance(widget, (QLabel, QPushButton)):
            widget.setText(text)

    # ======================================
    # WIDGET GEOMETRY
    # ======================================

    def _apply_widget_geometry(
        self,
        workflow_id,
        window_id,
        widget_id,
        widget,
        payload
    ):
        window = self._get_window(
            workflow_id,
            window_id
        )

        if window is None:
            return

        # The engine sends custom geometry nested inside
        # payload["geometry"]. No geometry means AUTO.
        geometry = payload.get("geometry")

        if isinstance(geometry, dict):
            x = self._safe_position(
                geometry.get("x", 10),
                10
            )

            y = self._safe_position(
                geometry.get("y", 10),
                10
            )

            width = self._safe_widget_dimension(
                geometry.get("width", 200),
                200
            )

            height = self._safe_widget_dimension(
                geometry.get("height", 30),
                30
            )

            widget._automation_layout = "CUSTOM"

            widget.setGeometry(
                x,
                y,
                width,
                height
            )

            return

        widget._automation_layout = "AUTO"

        window_widgets = self.widgets.get(
            workflow_id,
            {}
        ).get(
            window_id,
            {}
        )

        widget_ids = list(window_widgets)

        try:
            widget_index = widget_ids.index(widget_id)
        except ValueError:
            widget_index = len(widget_ids)

        x = self.AUTO_WIDGET_SIDE

        y = self.AUTO_WIDGET_TOP + (
            widget_index * (
                self.AUTO_WIDGET_HEIGHT
                + self.AUTO_WIDGET_SPACING
            )
        )

        width = max(
            1,
            window.width() - (self.AUTO_WIDGET_SIDE * 2)
        )

        widget.setGeometry(
            x,
            y,
            width,
            self.AUTO_WIDGET_HEIGHT
        )

    def _refresh_auto_widgets(self, workflow_id, window_id):
        window_widgets = self.widgets.get(
            workflow_id,
            {}
        ).get(
            window_id,
            {}
        )

        for widget_id, widget in window_widgets.items():
            if widget is None:
                continue

            if getattr(widget, "_automation_layout", "AUTO") == "AUTO":
                self._apply_widget_geometry(
                    workflow_id,
                    window_id,
                    widget_id,
                    widget,
                    {}
                )

    # ======================================
    # WIDGET HELPERS
    # ======================================

    def _get_window(self, workflow_id, window_id):
        return self.windows.get(
            workflow_id,
            {}
        ).get(window_id)

    def _get_widget(self, workflow_id, window_id, widget_id):
        return self.widgets.get(
            workflow_id,
            {}
        ).get(
            window_id,
            {}
        ).get(widget_id)

    def _register_widget(
        self,
        workflow_id,
        window_id,
        widget_id,
        widget
    ):
        window_widgets = self.widgets.setdefault(
            workflow_id, {}
        ).setdefault(
            window_id, {}
        )

        window_widgets[widget_id] = widget

    def _remove_widget(
        self,
        workflow_id,
        window_id,
        widget_id
    ):
        window_widgets = self.widgets.get(
            workflow_id,
            {}
        ).get(
            window_id,
            {}
        )

        widget = window_widgets.pop(
            widget_id,
            None
        )

        if widget is not None:
            widget.deleteLater()

    def _find_widget(self, workflow_id, widget_id):
        for window_widgets in self.widgets.get(
            workflow_id,
            {}
        ).values():

            if widget_id in window_widgets:
                return window_widgets[widget_id]

        return None

    # ======================================
    # VALUE HELPERS
    # ======================================

    @staticmethod
    def _safe_text(value):
        if value is None:
            return ""

        return str(value)

    @staticmethod
    def _safe_dimension(value, default):
        try:
            return max(100, min(2000, int(value)))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_widget_dimension(value, default):
        try:
            return max(1, min(2000, int(value)))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_position(value, default):
        try:
            return max(-10000, min(10000, int(value)))
        except (TypeError, ValueError):
            return default
