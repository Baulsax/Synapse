
import json
import logging
import ctypes

from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import Signal, QTimer, QUrl, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QMessageBox,
    QLineEdit,
    QCheckBox,
    QTreeWidget,
    QTreeWidgetItem,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
)

from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel

from pynput.mouse import Controller as MouseController

from core.bridge import WorkflowBridge


logger = logging.getLogger(__name__)


# ==========================================
# WINDOWS MONITOR INFORMATION
# ==========================================

class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


def get_monitor_bounds():
    monitors = []

    if not hasattr(ctypes, "windll"):
        return monitors

    user32 = ctypes.windll.user32

    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HANDLE,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )

    def monitor_callback(
        monitor_handle,
        device_context,
        monitor_rect,
        data
    ):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)

        if user32.GetMonitorInfoW(
            monitor_handle,
            ctypes.byref(info)
        ):
            rect = info.rcMonitor

            monitors.append({
                "name": info.szDevice,
                "left": rect.left,
                "top": rect.top,
                "right": rect.right,
                "bottom": rect.bottom,
                "width": rect.right - rect.left,
                "height": rect.bottom - rect.top,
            })

        return True

    callback = callback_type(monitor_callback)

    user32.EnumDisplayMonitors(
        None,
        None,
        callback,
        0
    )

    return monitors


# ==========================================
# PROPERTY TREE
# ==========================================

class PropertyTreeWidget(QTreeWidget):
    """
    Property tree with full-width horizontal row separators.
    """

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setPen(
            QPen(QColor("#30343e"), 1)
        )

        def draw_item_lines(item):
            if not item:
                return

            rect = self.visualItemRect(item)

            if rect.isValid() and rect.bottom() >= 0:
                painter.drawLine(
                    0,
                    rect.bottom(),
                    self.viewport().width(),
                    rect.bottom()
                )

            for index in range(item.childCount()):
                draw_item_lines(item.child(index))

        for index in range(self.topLevelItemCount()):
            draw_item_lines(self.topLevelItem(index))

        painter.end()


# ==========================================
# WORKFLOW EDITOR
# ==========================================

class WorkflowEditorPage(QWidget):

    back_requested = Signal()

    PROPERTY_FIELD_NAMES = {
        "WINDOW_ID": "Window ID",
        "WIDGET_ID": "Widget ID",
        "BUTTON_ID": "Button ID",
        "X": "Position X",
        "Y": "Position Y",
        "WIDTH": "Width",
        "HEIGHT": "Height",
        "TITLE": "Title",
        "TEXT": "Text",
        "DURATION": "Duration",
        "KEY": "Key",
        "BUTTON": "Button",
        "AMOUNT": "Amount",
        "MODE": "Action",
        "CONTROL": "Control",
        "DEVICE": "Device",
    }

    FIELD_ORDER = [
        "WINDOW_ID",
        "WIDGET_ID",
        "BUTTON_ID",
        "TITLE",
        "X",
        "Y",
        "WIDTH",
        "HEIGHT",
        "DURATION",
        "KEY",
        "BUTTON",
        "AMOUNT",
        "MODE",
        "CONTROL",
        "DEVICE",
        "TEXT",
    ]

    # ======================================
    # PROPERTY SCHEMAS
    # ======================================
    #
    # Each block type declares:
    # - Which categories it uses.
    # - Which fields belong in each category.
    # - Which internal fields should never be displayed.
    #
    # Adding a new UI block type should generally only
    # require adding a schema entry here.
    #
    # Categories with no matching fields are skipped.
    # This allows us to define future categories without
    # displaying empty sections prematurely.

    PROPERTY_SCHEMAS = {
        "automation_ui_create_label": {
            "categories": (
                (
                    "General",
                    ("WINDOW_ID", "WIDGET_ID")
                ),
                (
                    "Appearance",
                    ()
                ),
                (
                    "Transform",
                    ("X", "Y", "WIDTH", "HEIGHT")
                ),
                (
                    "Text",
                    ("TEXT",)
                ),
            ),
            "hidden_fields": (
                "LAYOUT",
            ),
        },

        "automation_ui_create_button": {
            "categories": (
                (
                    "General",
                    ("WINDOW_ID", "WIDGET_ID")
                ),
                (
                    "Appearance",
                    ()
                ),
                (
                    "Transform",
                    ("X", "Y", "WIDTH", "HEIGHT")
                ),
                (
                    "Text",
                    ("TEXT",)
                ),
            ),
            "hidden_fields": (
                "LAYOUT",
            ),
        },

        "automation_ui_create_window": {
            "categories": (
                (
                    "General",
                    ("WINDOW_ID", "TITLE")
                ),
                (
                    "Size",
                    ("WIDTH", "HEIGHT")
                ),
            ),
            "hidden_fields": (),
        },
    }

    def __init__(
        self,
        workflow_name,
        workflow_engine=None,
        input_manager=None
    ):
        super().__init__()

        self.mouse_controller = MouseController()
        self.current_mouse_position = (0, 0)
        self.monitors = get_monitor_bounds()

        self._loading_name = False
        self._loading_inspector = False
        self._selected_block_id = None

        self._category_expansion_state = {}

        self._leave_after_save = False

        self.bridge = WorkflowBridge(
            workflow_name,
            workflow_engine,
            input_manager
        )

        self.build_interface(workflow_name)
        self.connect_signals()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(
            self.update_run_indicator
        )
        self.status_timer.start(250)

        self.coordinate_timer = QTimer(self)
        self.coordinate_timer.timeout.connect(
            self.update_mouse_coordinates
        )
        self.coordinate_timer.start(50)

    # ======================================
    # INTERFACE
    # ======================================

    def build_interface(self, workflow_name):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        self.setStyleSheet("""
            QWidget {
                color: #e5e7eb;
            }

            QPushButton {
                background-color: #303541;
                color: #e5e7eb;
                border: 1px solid #414754;
                border-radius: 4px;
                padding: 6px 12px;
            }

            QPushButton:hover {
                background-color: #3b414f;
            }

            QPushButton:pressed {
                background-color: #292e38;
            }

            QPushButton#primary_button {
                background-color: #4569a8;
                border: 1px solid #547bbd;
            }

            QPushButton#primary_button:hover {
                background-color: #5279ba;
            }

            QPushButton#secondary_button {
                background-color: #303541;
            }

            QLabel#page_title {
                color: #f3f4f6;
                font-size: 16px;
                font-weight: 600;
            }

            QLabel#muted {
                color: #9ca3af;
                font-size: 11px;
            }

            QLabel#property_status_idle {
                color: #e05252;
                font-size: 12px;
            }

            QLabel#property_status_running {
                color: #45c878;
                font-size: 12px;
            }
        """)

        self.build_header(layout)
        self.build_workspace(layout)

    # ======================================
    # HEADER
    # ======================================

    def build_header(self, layout):
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        header_layout.setContentsMargins(0, 0, 0, 4)

        back_button = QPushButton("< Back")
        back_button.clicked.connect(self.request_back)

        title = QLabel("Workflow Editor")
        title.setObjectName("page_title")

        self.save_status = QLabel("")
        self.save_status.setObjectName("muted")

        self.run_indicator = QLabel("● Idle")
        self.run_indicator.setObjectName(
            "property_status_idle"
        )

        self.run_button = QPushButton("Run")
        self.run_button.setObjectName("primary_button")
        self.run_button.clicked.connect(
            self.run_workflow
        )

        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("secondary_button")
        self.stop_button.clicked.connect(
            self.stop_workflow
        )

        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("primary_button")
        self.save_button.clicked.connect(
            self.save_workflow
        )

        header_layout.addWidget(back_button)
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.save_status)
        header_layout.addWidget(self.run_indicator)
        header_layout.addWidget(self.run_button)
        header_layout.addWidget(self.stop_button)
        header_layout.addWidget(self.save_button)

        layout.addLayout(header_layout)

    # ======================================
    # WORKSPACE
    # ======================================

    def build_workspace(self, layout):
        workspace = QHBoxLayout()
        workspace.setSpacing(10)

        self.blockly_view = QWebEngineView()

        self.blockly_view.setStyleSheet(
            "background-color: #17171d;"
        )

        self.blockly_view.page().setBackgroundColor(
            QColor("#17171d")
        )

        self.channel = QWebChannel()
        self.channel.registerObject(
            "bridge",
            self.bridge
        )

        self.blockly_view.page().setWebChannel(
            self.channel
        )

        editor_path = (
            Path(__file__).parent.parent
            / "web"
            / "index.html"
        )

        self.blockly_view.setUrl(
            QUrl.fromLocalFile(str(editor_path.resolve()))
        )

        self.blockly_view.loadFinished.connect(
            self._on_editor_loaded
        )

        workspace.addWidget(self.blockly_view, 1)

        self.build_properties_panel(workspace)

        layout.addLayout(workspace, 1)

        # ----------------------------------
        # BOTTOM BAR
        # ----------------------------------

        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 0, 0, 0)
        bottom_bar.setSpacing(8)

        self.mouse_status = QLabel("Mouse: 0, 0")
        self.mouse_status.setObjectName("muted")

        self.settings_button = QPushButton(
            "Workflow Settings"
        )
        self.settings_button.clicked.connect(
            self.open_workflow_settings
        )

        bottom_bar.addWidget(self.mouse_status)
        bottom_bar.addStretch()
        bottom_bar.addWidget(self.settings_button)

        layout.addLayout(bottom_bar)

    # ======================================
    # PROPERTIES PANEL
    # ======================================

    def build_properties_panel(self, workspace):
        self.properties_panel = QFrame()
        self.properties_panel.setObjectName(
            "properties_panel"
        )
        self.properties_panel.setFixedWidth(285)

        self.properties_panel.setStyleSheet("""
            QFrame#properties_panel {
                background-color: #20232b;
                border: 1px solid #30343e;
                border-radius: 6px;
            }

            QLabel#properties_title {
                color: #e5e7eb;
                font-size: 14px;
                font-weight: 600;
                border: none;
            }

            QLabel#inspector_empty {
                color: #858c99;
                font-size: 11px;
                border: none;
            }

            QTreeWidget#property_tree {
                background-color: transparent;
                color: #e5e7eb;
                border: none;
                outline: none;
                font-size: 11px;
                alternate-background-color: #252933;
                show-decoration-selected: 0;
            }

            QTreeWidget#property_tree::item {
                height: 27px;
                padding-left: 3px;
                border: none;
            }

            QTreeWidget#property_tree::item:selected {
                background-color: #35445d;
                color: #ffffff;
            }

            QTreeWidget#property_tree::item:hover {
                background-color: #2c323e;
            }

            QTreeWidget#property_tree QHeaderView::section {
                background-color: #252933;
                color: #aeb4c0;
                border: none;
                border-bottom: 1px solid #3a404c;
                padding: 6px 7px;
                font-size: 10px;
                font-weight: 600;
            }

            QTreeWidget#property_tree QLineEdit {
                background-color: #17191f;
                color: #e5e7eb;
                border: 1px solid #668ed0;
                padding: 2px 4px;
                font-size: 11px;
            }
        """)

        properties_layout = QVBoxLayout(
            self.properties_panel
        )
        properties_layout.setContentsMargins(
            10, 12, 10, 10
        )
        properties_layout.setSpacing(8)

        title = QLabel("Properties")
        title.setObjectName("properties_title")

        properties_layout.addWidget(title)

        self.inspector_empty = QLabel(
            "Select an object to view its properties."
        )
        self.inspector_empty.setObjectName(
            "inspector_empty"
        )
        self.inspector_empty.setWordWrap(True)
        self.inspector_empty.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        properties_layout.addWidget(
            self.inspector_empty,
            1
        )

        self.inspector_tree = PropertyTreeWidget()
        self.inspector_tree.setObjectName(
            "property_tree"
        )
        self.inspector_tree.setColumnCount(2)
        self.inspector_tree.setHeaderLabels([
            "Property",
            "Value"
        ])
        self.inspector_tree.setAlternatingRowColors(True)
        self.inspector_tree.setRootIsDecorated(True)
        self.inspector_tree.setItemsExpandable(True)
        self.inspector_tree.setUniformRowHeights(True)
        self.inspector_tree.setIndentation(14)

        self.inspector_tree.setEditTriggers(
            QTreeWidget.EditTrigger.DoubleClicked
            | QTreeWidget.EditTrigger.EditKeyPressed
        )

        self.inspector_tree.setColumnWidth(0, 125)
        self.inspector_tree.header().setStretchLastSection(
            True
        )

        self.inspector_tree.itemChanged.connect(
            self.on_inspector_item_changed
        )

        self.inspector_tree.hide()

        properties_layout.addWidget(
            self.inspector_tree,
            1
        )

        workspace.addWidget(self.properties_panel)

    # ======================================
    # BRIDGE CONNECTIONS
    # ======================================

    def connect_signals(self):
        self.bridge.workflow_changed.connect(
            lambda: self.save_status.setText(
                "Unsaved changes"
            )
        )

        self.bridge.workflow_saved.connect(
            self.on_workflow_saved
        )

        self.bridge.selected_block_changed.connect(
            self.on_selected_block_changed
        )

    # ======================================
    # INSPECTOR UPDATES
    # ======================================

    def on_selected_block_changed(self, block_json):
        try:
            block_data = json.loads(block_json)
        except (TypeError, ValueError):
            logger.warning(
                "Received invalid inspector data."
            )
            block_data = {}

        if not isinstance(block_data, dict):
            block_data = {}

        if not block_data.get("id"):
            self.clear_inspector()
            return

        self.populate_inspector(block_data)

    def clear_inspector(self):
        self._loading_inspector = True

        try:
            self._selected_block_id = None
            self._category_expansion_state.clear()

            self.inspector_tree.clear()
            self.inspector_tree.hide()
            self.inspector_empty.show()

        finally:
            self._loading_inspector = False

    def get_category_expansion_state(self):
        """
        Capture the expanded/collapsed state of current categories.
        """
        state = {}

        for index in range(
            self.inspector_tree.topLevelItemCount()
        ):
            category = self.inspector_tree.topLevelItem(index)

            state[category.text(0)] = category.isExpanded()

        return state

    def restore_category_expansion_state(self):
        """
        Restore remembered category states.

        Categories encountered for the first time default to expanded.
        """
        for index in range(
            self.inspector_tree.topLevelItemCount()
        ):
            category = self.inspector_tree.topLevelItem(index)
            category_name = category.text(0)

            expanded = self._category_expansion_state.get(
                category_name,
                True
            )

            category.setExpanded(expanded)

    def populate_inspector(self, block_data):
        block_id = block_data.get("id")
        block_type = block_data.get("type", "")
        fields = block_data.get("fields", {})

        if not isinstance(fields, dict):
            fields = {}

        self._loading_inspector = True

        try:
            self._category_expansion_state.update(
                self.get_category_expansion_state()
            )

            self._selected_block_id = block_id

            self.inspector_tree.clear()

            self.inspector_empty.hide()
            self.inspector_tree.show()

            self.add_block_categories(
                block_type,
                fields
            )

            self.restore_category_expansion_state()

        finally:
            self._loading_inspector = False

    def add_block_categories(self, block_type, fields):
        schema = self.PROPERTY_SCHEMAS.get(block_type)

        if schema is None:
            self.add_general_block_properties(fields)
            return

        self.add_schema_properties(
            fields,
            schema
        )

    # ======================================
    # SCHEMA-DRIVEN PROPERTIES
    # ======================================

    def add_schema_properties(self, fields, schema):
        categorized_fields = set()

        hidden_fields = set(
            schema.get("hidden_fields", ())
        )

        for category_name, field_names in schema.get(
            "categories",
            ()
        ):
            available_fields = [
                field_name
                for field_name in field_names
                if (
                    field_name in fields
                    and field_name not in hidden_fields
                )
            ]

            if not available_fields:
                continue

            self.add_property_category(
                category_name,
                available_fields,
                fields
            )

            categorized_fields.update(
                available_fields
            )

        remaining_fields = [
            field_name
            for field_name in fields
            if (
                field_name not in categorized_fields
                and field_name not in hidden_fields
            )
        ]

        if remaining_fields:
            remaining_fields = self.order_fields(
                remaining_fields
            )

            self.add_property_category(
                "Other",
                remaining_fields,
                fields
            )

    def order_fields(self, fields):
        ordered_fields = [
            field_name
            for field_name in self.FIELD_ORDER
            if field_name in fields
        ]

        remaining_fields = [
            field_name
            for field_name in fields
            if field_name not in ordered_fields
        ]

        ordered_fields.extend(remaining_fields)

        return ordered_fields

    def add_general_block_properties(self, fields):
        ordered_fields = self.order_fields(
            list(fields.keys())
        )

        if ordered_fields:
            self.add_property_category(
                "Properties",
                ordered_fields,
                fields
            )

    # ======================================
    # PROPERTY GRID HELPERS
    # ======================================

    def add_property_category(
        self,
        category_name,
        field_names,
        fields
    ):
        available_fields = [
            field_name
            for field_name in field_names
            if field_name in fields
        ]

        if not available_fields:
            return

        category = QTreeWidgetItem([
            category_name,
            ""
        ])

        category.setFlags(
            Qt.ItemFlag.ItemIsEnabled
        )

        category.setForeground(
            0,
            QColor("#aeb8c8")
        )

        self.inspector_tree.addTopLevelItem(
            category
        )

        for field_name in available_fields:
            self.add_property_item(
                category,
                field_name,
                fields[field_name]
            )

    def add_property_item(
        self,
        category,
        field_name,
        value
    ):
        display_name = self.PROPERTY_FIELD_NAMES.get(
            field_name,
            field_name.replace("_", " ").title()
        )

        item = QTreeWidgetItem([
            display_name,
            str(value)
        ])

        item.setData(
            0,
            Qt.ItemDataRole.UserRole,
            field_name
        )

        item.setData(
            0,
            Qt.ItemDataRole.UserRole + 1,
            self._selected_block_id
        )

        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )

        item.setForeground(
            0,
            QColor("#aeb4c0")
        )

        item.setForeground(
            1,
            QColor("#e5e7eb")
        )

        category.addChild(item)

    # ======================================
    # PROPERTY EDITING
    # ======================================

    def on_inspector_item_changed(self, item, column):
        if self._loading_inspector:
            return

        if column != 1:
            return

        field_name = item.data(
            0,
            Qt.ItemDataRole.UserRole
        )

        block_id = item.data(
            0,
            Qt.ItemDataRole.UserRole + 1
        )

        if not field_name or not block_id:
            return

        self.set_inspector_property(
            block_id,
            field_name,
            item.text(1)
        )

    def set_inspector_property(
        self,
        block_id,
        property_name,
        value
    ):
        if not block_id or not property_name:
            return

        self.bridge.set_block_property(
            block_id,
            property_name,
            str(value)
        )

    # ======================================
    # WORKFLOW SETTINGS
    # ======================================

    def open_workflow_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Workflow Settings")
        dialog.setMinimumWidth(340)

        dialog.setStyleSheet("""
            QDialog {
                background-color: #20232b;
                color: #e5e7eb;
            }

            QLabel {
                color: #cbd0da;
            }

            QLineEdit {
                background-color: #17191f;
                color: #e5e7eb;
                border: 1px solid #3b414d;
                border-radius: 4px;
                padding: 6px;
            }

            QCheckBox {
                color: #cbd0da;
                spacing: 8px;
            }

            QDialogButtonBox QPushButton {
                min-width: 70px;
            }
        """)

        dialog_layout = QVBoxLayout(dialog)

        form = QFormLayout()
        form.setSpacing(12)

        name_input = QLineEdit(
            self.bridge.workflow_name
        )
        name_input.setClearButtonEnabled(True)

        multiple_checkbox = QCheckBox(
            "Allow multiple executions"
        )
        multiple_checkbox.setToolTip(
            "When enabled, clicking a button can start another "
            "execution even if that button's previous execution "
            "is still running."
        )

        multiple_checkbox.setChecked(
            bool(
                getattr(
                    self.bridge.engine,
                    "allow_multiple_ui_executions",
                    False
                )
            )
        )

        form.addRow("Workflow name:", name_input)
        form.addRow("", multiple_checkbox)

        dialog_layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        dialog_layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_name = name_input.text().strip()

        if not new_name:
            QMessageBox.warning(
                self,
                "Invalid Name",
                "Workflow name cannot be empty."
            )
            return

        if new_name != self.bridge.workflow_name:
            if not self.bridge.rename_workflow(new_name):
                QMessageBox.warning(
                    self,
                    "Rename Failed",
                    "Could not rename this workflow.\n\n"
                    "Make sure the name is valid and another "
                    "workflow doesn't already use it."
                )

        self.bridge.engine.allow_multiple_ui_executions = bool(
            multiple_checkbox.isChecked()
        )

    # ======================================
    # EDITOR LOADING
    # ======================================

    def _on_editor_loaded(self, success):
        if success:
            self.blockly_view.page().runJavaScript(
                "window.loadWorkflow()"
            )
        else:
            logger.error(
                "Blockly editor failed to load."
            )

    # ======================================
    # MOUSE COORDINATES
    # ======================================

    def update_mouse_coordinates(self):
        try:
            x, y = self.mouse_controller.position

            x = int(x)
            y = int(y)

            self.current_mouse_position = (x, y)

            monitor = self.get_current_monitor(x, y)

            if monitor:
                monitor_name = monitor["name"].split("\\")[-1]

                self.mouse_status.setText(
                    f"Mouse: {x}, {y}    "
                    f"Monitor: {monitor_name}    "
                    f"{monitor['width']} × {monitor['height']}"
                )
            else:
                self.mouse_status.setText(
                    f"Mouse: {x}, {y}    Monitor: Unavailable"
                )

        except Exception:
            logger.exception(
                "Failed to read mouse coordinates."
            )

    def get_current_monitor(self, x, y):
        for monitor in self.monitors:
            if (
                monitor["left"] <= x < monitor["right"]
                and monitor["top"] <= y < monitor["bottom"]
            ):
                return monitor

        return None

    # ======================================
    # SAVE / NAVIGATION
    # ======================================

    def save_workflow(self):
        self.save_status.setText("Saving...")

        self.blockly_view.page().runJavaScript(
            "window.saveWorkflow()"
        )

    def request_back(self):
        if not self.bridge.is_dirty:
            self.back_requested.emit()
            return

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Unsaved Changes")
        dialog.setText(
            "You have unsaved changes."
        )
        dialog.setInformativeText(
            "Would you like to save before leaving?"
        )
        dialog.setIcon(
            QMessageBox.Icon.Warning
        )

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
            self._leave_after_save = True
            self.save_workflow()

        elif clicked == discard_button:
            self.bridge.is_dirty = False
            self.back_requested.emit()

    def on_workflow_saved(self):
        self.save_status.setText("")

        if self._leave_after_save:
            self._leave_after_save = False
            self.back_requested.emit()

    # ======================================
    # WORKFLOW EXECUTION
    # ======================================

    def run_workflow(self):
        self.blockly_view.page().runJavaScript(
            """
            bridge.start_workflow(
                JSON.stringify(getWorkflowData())
            );
            """
        )

    def stop_workflow(self):
        self.bridge.stop_workflow()

    def update_run_indicator(self):
        is_active = getattr(
            self.bridge.engine,
            "is_active",
            self.bridge.engine.is_running
        )

        if is_active:
            self.run_indicator.setText("● Running")
            self.run_indicator.setObjectName(
                "property_status_running"
            )
            self.run_indicator.setStyleSheet(
                "color: #45c878; font-size: 12px;"
            )
            self.run_indicator.setToolTip(
                "Workflow is active."
            )
        else:
            self.run_indicator.setText("● Idle")
            self.run_indicator.setObjectName(
                "property_status_idle"
            )
            self.run_indicator.setStyleSheet(
                "color: #e05252; font-size: 12px;"
            )
            self.run_indicator.setToolTip(
                "Workflow is idle."
            )
