
import logging

from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QSize
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPen,
    QIcon,
    QTransform,
)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QSplitterHandle,
    QDoubleSpinBox,
    QSpinBox,
    QInputDialog,
    QMessageBox,
    QAbstractItemView,
    QStyle,
    QStyleOptionSpinBox,
)


logger = logging.getLogger(__name__)

ARROW_PATH = (
    Path(__file__).resolve().parent.parent
    / "assets"
    / "dropdown-arrow.svg"
)

SPINBOX_ARROW = QIcon(str(ARROW_PATH))


class MacroSpinBoxArrowMixin:

    def paintEvent(self, event):
        super().paintEvent(event)

        if SPINBOX_ARROW.isNull():
            return

        option = QStyleOptionSpinBox()
        self.initStyleOption(option)

        style = self.style()

        up_rect = style.subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            option,
            QStyle.SubControl.SC_SpinBoxUp,
            self,
        )

        down_rect = style.subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            option,
            QStyle.SubControl.SC_SpinBoxDown,
            self,
        )

        if up_rect.isEmpty() or down_rect.isEmpty():
            return

        # Use the SVG at its original 10x10 size.
        down_pixmap = SPINBOX_ARROW.pixmap(QSize(10, 10))

        if down_pixmap.isNull():
            return

        up_pixmap = down_pixmap.transformed(
            QTransform().rotate(180),
            Qt.TransformationMode.SmoothTransformation,
        )

        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform
        )
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )

        # Center each arrow independently, with a slight
        # rightward adjustment to compensate for its visual alignment.
        horizontal_adjustment = 1.5

        up_x = (
            up_rect.center().x()
            - up_pixmap.width() // 2
            + horizontal_adjustment
        )
        up_y = up_rect.center().y() - up_pixmap.height() // 2

        down_x = (
            down_rect.center().x()
            - down_pixmap.width() // 2
            + horizontal_adjustment
        )
        down_y = down_rect.center().y() - down_pixmap.height() // 2

        painter.drawPixmap(up_x, up_y, up_pixmap)
        painter.drawPixmap(down_x, down_y, down_pixmap)

        painter.end()


class MacroDoubleSpinBox(
    MacroSpinBoxArrowMixin,
    QDoubleSpinBox,
):
    pass


class MacroIntSpinBox(
    MacroSpinBoxArrowMixin,
    QSpinBox,
):
    pass


class MacroSplitterHandle(QSplitterHandle):

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = self.contentsRect().center()

        color = QColor(
            "#a78bfa" if self.underMouse() else "#626775"
        )

        pen = QPen(color)
        pen.setWidth(2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        painter.setPen(pen)

        painter.drawLine(
            QPointF(center.x() + 0.5, center.y() - 16),
            QPointF(center.x() + 0.5, center.y() + 16)
        )

        painter.end()


class MacroSplitter(QSplitter):

    def createHandle(self):
        return MacroSplitterHandle(self.orientation(), self)


class MacrosPage(QWidget):

    def __init__(self, macro_engine, parent=None):
        super().__init__(parent)

        self.macro_engine = macro_engine
        self._updating_timeline = False
        self._capturing_hotkey = None

        self._build_interface()
        self._connect_signals()

        self.refresh_timeline()
        self.refresh_library()
        self.refresh_hotkeys()

        self.update_recording_state("stopped")
        self.update_playback_state("stopped")

    # ======================================
    # INTERFACE
    # ======================================

    def _build_interface(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 20)
        root.setSpacing(14)

        # Header
        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(3)

        title = QLabel("Macros")
        title.setObjectName("page_title")
        title.setContentsMargins(0, 0, 0, 0)
        title.setIndent(0)
        title.setAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter
        )
        title.setStyleSheet("""
            QLabel#page_title {
                padding: 0px;
                margin: 0px;
                border: none;
            }
        """)

        subtitle = QLabel(
            "Record, edit, and replay keyboard and mouse actions."
        )
        subtitle.setObjectName("muted")

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        root.addLayout(header_layout)

        # Main controls
        controls = QFrame()
        controls.setObjectName("macro_controls")

        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(16, 14, 16, 14)
        controls_layout.setSpacing(22)

        # Recording controls
        recording_layout = QVBoxLayout()
        recording_layout.setSpacing(9)

        recording_heading = QLabel("RECORDING")
        recording_heading.setObjectName("macro_section_heading")

        recording_buttons = QHBoxLayout()
        recording_buttons.setSpacing(7)

        self.record_button = QPushButton("Record")
        self.record_button.setObjectName("primary_button")

        self.record_pause_button = QPushButton("Pause")
        self.record_pause_button.setObjectName("secondary_button")
        self.record_pause_button.setEnabled(False)

        self.record_stop_button = QPushButton("Stop")
        self.record_stop_button.setObjectName("danger_button")
        self.record_stop_button.setEnabled(False)

        recording_buttons.addWidget(self.record_button)
        recording_buttons.addWidget(self.record_pause_button)
        recording_buttons.addWidget(self.record_stop_button)

        self.recording_status = QLabel("Ready to record")
        self.recording_status.setObjectName("macro_status")

        # Recording hotkey
        recording_hotkey_layout = QHBoxLayout()
        recording_hotkey_layout.setContentsMargins(0, 0, 0, 0)
        recording_hotkey_layout.setSpacing(9)

        self.record_hotkey_label = QLabel("Record / Stop: Not set")
        self.record_hotkey_label.setObjectName("macro_hotkey_label")

        self.record_hotkey_button = QPushButton("Listen for Input")
        self.record_hotkey_button.setObjectName("secondary_button")

        recording_hotkey_layout.addWidget(self.record_hotkey_label)
        recording_hotkey_layout.addWidget(self.record_hotkey_button)
        recording_hotkey_layout.addStretch()

        recording_layout.addWidget(recording_heading)
        recording_layout.addLayout(recording_buttons)
        recording_layout.addWidget(self.recording_status)
        recording_layout.addLayout(recording_hotkey_layout)

        # Playback controls
        playback_layout = QVBoxLayout()
        playback_layout.setSpacing(9)

        playback_heading = QLabel("PLAYBACK")
        playback_heading.setObjectName("macro_section_heading")

        playback_buttons = QHBoxLayout()
        playback_buttons.setSpacing(7)

        self.play_button = QPushButton("Play")
        self.play_button.setObjectName("primary_button")

        self.play_pause_button = QPushButton("Pause")
        self.play_pause_button.setObjectName("secondary_button")
        self.play_pause_button.setEnabled(False)

        self.play_stop_button = QPushButton("Stop")
        self.play_stop_button.setObjectName("danger_button")
        self.play_stop_button.setEnabled(False)

        playback_buttons.addWidget(self.play_button)
        playback_buttons.addWidget(self.play_pause_button)
        playback_buttons.addWidget(self.play_stop_button)

        settings_layout = QHBoxLayout()
        settings_layout.setSpacing(12)

        speed_layout = QVBoxLayout()
        speed_layout.setSpacing(3)

        speed_label = QLabel("Speed")
        speed_label.setObjectName("muted")

        self.speed_spin = MacroDoubleSpinBox()
        self.speed_spin.setRange(0.1, 5.0)
        self.speed_spin.setSingleStep(0.1)
        self.speed_spin.setValue(1.0)
        self.speed_spin.setSuffix("x")
        self.speed_spin.setObjectName("macro_spin")
        self.speed_spin.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        speed_layout.addWidget(speed_label)
        speed_layout.addWidget(self.speed_spin)

        repeat_layout = QVBoxLayout()
        repeat_layout.setSpacing(3)

        repeat_label = QLabel("Repeats")
        repeat_label.setObjectName("muted")

        self.repeat_spin = MacroIntSpinBox()
        self.repeat_spin.setRange(0, 9999)
        self.repeat_spin.setValue(1)
        self.repeat_spin.setSpecialValueText("Infinite")
        self.repeat_spin.setObjectName("macro_spin")
        self.repeat_spin.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        repeat_layout.addWidget(repeat_label)
        repeat_layout.addWidget(self.repeat_spin)

        settings_layout.addLayout(speed_layout)
        settings_layout.addLayout(repeat_layout)

        self.playback_status = QLabel("Ready to play")
        self.playback_status.setObjectName("macro_status")

        # Playback hotkey
        playback_hotkey_layout = QHBoxLayout()
        playback_hotkey_layout.setContentsMargins(0, 0, 0, 0)
        playback_hotkey_layout.setSpacing(9)

        self.playback_hotkey_label = QLabel("Playback: Not set")
        self.playback_hotkey_label.setObjectName("macro_hotkey_label")

        self.playback_hotkey_button = QPushButton("Listen for Input")
        self.playback_hotkey_button.setObjectName("secondary_button")

        playback_hotkey_layout.addWidget(self.playback_hotkey_label)
        playback_hotkey_layout.addWidget(self.playback_hotkey_button)
        playback_hotkey_layout.addStretch()

        playback_layout.addWidget(playback_heading)
        playback_layout.addLayout(playback_buttons)
        playback_layout.addLayout(settings_layout)
        playback_layout.addWidget(self.playback_status)
        playback_layout.addLayout(playback_hotkey_layout)

        controls_layout.addLayout(recording_layout, 1)

        separator = QFrame()
        separator.setObjectName("macro_vertical_divider")
        separator.setFixedWidth(1)
        controls_layout.addWidget(separator)

        controls_layout.addLayout(playback_layout, 1)

        root.addWidget(controls)

        # Workspace
        splitter = MacroSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("macro_splitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(9)

        splitter.setStyleSheet("""
            QSplitter#macro_splitter::handle:horizontal {
                background-color: #252832;
                border-left: 1px solid #30343f;
                border-right: 1px solid #30343f;
                margin: 3px 0px;
                border-radius: 3px;
            }

            QSplitter#macro_splitter::handle:horizontal:hover {
                background-color: #383246;
                border-left: 1px solid #a78bfa;
                border-right: 1px solid #a78bfa;
            }
        """)

        # Timeline panel
        timeline_panel = QFrame()
        timeline_panel.setObjectName("macro_panel")

        timeline_layout = QVBoxLayout(timeline_panel)
        timeline_layout.setContentsMargins(15, 14, 15, 14)
        timeline_layout.setSpacing(10)

        timeline_header = QHBoxLayout()

        timeline_title = QLabel("Action Timeline")
        timeline_title.setObjectName("macro_panel_title")

        self.action_count_label = QLabel("0 actions")
        self.action_count_label.setObjectName("muted")

        timeline_header.addWidget(timeline_title)
        timeline_header.addStretch()
        timeline_header.addWidget(self.action_count_label)

        timeline_layout.addLayout(timeline_header)

        self.timeline_list = QListWidget()
        self.timeline_list.setObjectName("macro_timeline")
        self.timeline_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.timeline_list.setAlternatingRowColors(False)

        timeline_layout.addWidget(self.timeline_list, 1)

        timeline_tools = QHBoxLayout()
        timeline_tools.setSpacing(7)

        self.delay_button = QPushButton("Edit Delay")
        self.delay_button.setObjectName("secondary_button")

        self.move_up_button = QPushButton("Move Up")
        self.move_up_button.setObjectName("secondary_button")

        self.move_down_button = QPushButton("Move Down")
        self.move_down_button.setObjectName("secondary_button")

        self.remove_action_button = QPushButton("Remove")
        self.remove_action_button.setObjectName("danger_button")

        timeline_tools.addWidget(self.delay_button)
        timeline_tools.addWidget(self.move_up_button)
        timeline_tools.addWidget(self.move_down_button)
        timeline_tools.addWidget(self.remove_action_button)

        timeline_layout.addLayout(timeline_tools)

        # Macro library panel
        library_panel = QFrame()
        library_panel.setObjectName("macro_panel")
        library_panel.setMinimumWidth(215)
        library_panel.setMaximumWidth(330)

        library_layout = QVBoxLayout(library_panel)
        library_layout.setContentsMargins(15, 14, 15, 14)
        library_layout.setSpacing(10)

        library_header = QHBoxLayout()

        library_title = QLabel("Macro Library")
        library_title.setObjectName("macro_panel_title")

        library_header.addWidget(library_title)
        library_header.addStretch()

        library_layout.addLayout(library_header)

        self.library_list = QListWidget()
        self.library_list.setObjectName("macro_library")

        library_layout.addWidget(self.library_list, 1)

        self.save_macro_button = QPushButton("Save Current Macro")
        self.save_macro_button.setObjectName("primary_button")

        self.load_macro_button = QPushButton("Load")
        self.load_macro_button.setObjectName("secondary_button")

        self.delete_macro_button = QPushButton("Delete")
        self.delete_macro_button.setObjectName("danger_button")

        library_layout.addWidget(self.save_macro_button)

        library_actions = QHBoxLayout()
        library_actions.setSpacing(7)

        library_actions.addWidget(self.load_macro_button)
        library_actions.addWidget(self.delete_macro_button)

        library_layout.addLayout(library_actions)

        splitter.addWidget(timeline_panel)
        splitter.addWidget(library_panel)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([800, 270])

        root.addWidget(splitter, 1)

    # ======================================
    # SIGNALS
    # ======================================

    def _connect_signals(self):
        self.record_button.clicked.connect(
            self.start_recording
        )

        self.record_pause_button.clicked.connect(
            self.toggle_recording_pause
        )

        self.record_stop_button.clicked.connect(
            self.stop_recording
        )

        self.play_button.clicked.connect(
            self.start_playback
        )

        self.play_pause_button.clicked.connect(
            self.toggle_playback_pause
        )

        self.play_stop_button.clicked.connect(
            self.stop_playback
        )

        self.save_macro_button.clicked.connect(
            self.save_macro
        )

        self.load_macro_button.clicked.connect(
            self.load_selected_macro
        )

        self.delete_macro_button.clicked.connect(
            self.delete_selected_macro
        )

        self.delay_button.clicked.connect(
            self.edit_selected_delay
        )

        self.move_up_button.clicked.connect(
            lambda: self.move_selected_action(-1)
        )

        self.move_down_button.clicked.connect(
            lambda: self.move_selected_action(1)
        )

        self.remove_action_button.clicked.connect(
            self.remove_selected_action
        )

        self.record_hotkey_button.clicked.connect(
            lambda: self.begin_hotkey_capture("record_toggle")
        )

        self.playback_hotkey_button.clicked.connect(
            lambda: self.begin_hotkey_capture("playback_toggle")
        )

        self.macro_engine.recording_state_changed.connect(
            self.update_recording_state
        )

        self.macro_engine.playback_state_changed.connect(
            self.update_playback_state
        )

        self.macro_engine.actions_changed.connect(
            self.refresh_timeline
        )

        self.macro_engine.hotkeys_changed.connect(
            self.refresh_hotkeys
        )

        self.macro_engine.hotkey_capture_started.connect(
            self.on_hotkey_capture_started
        )

        self.macro_engine.hotkey_capture_finished.connect(
            self.on_hotkey_capture_finished
        )

        self.macro_engine.hotkey_capture_rejected.connect(
            self.on_hotkey_capture_rejected
        )

        self.speed_spin.valueChanged.connect(
            self.update_hotkey_playback_options
        )

        self.repeat_spin.valueChanged.connect(
            self.update_hotkey_playback_options
        )

        self.library_list.itemDoubleClicked.connect(
            lambda _item: self.load_selected_macro()
        )

        self.timeline_list.itemDoubleClicked.connect(
            lambda _item: self.edit_selected_delay()
        )

        self.update_hotkey_playback_options()

    # ======================================
    # HOTKEYS
    # ======================================

    def begin_hotkey_capture(self, action_name):
        if self._capturing_hotkey is not None:
            self.macro_engine.cancel_hotkey_capture()

        self.macro_engine.begin_hotkey_capture(action_name)

    def on_hotkey_capture_started(self, action_name):
        self._capturing_hotkey = action_name

        if action_name == "record_toggle":
            self.record_hotkey_button.setText("Press a key...")
        else:
            self.playback_hotkey_button.setText("Press a key...")

    def on_hotkey_capture_finished(self, action_name, _descriptor):
        self._capturing_hotkey = None

        self.record_hotkey_button.setText("Listen for Input")
        self.playback_hotkey_button.setText("Listen for Input")

        self.refresh_hotkeys()

    def on_hotkey_capture_rejected(self, message):
        if self.macro_engine._hotkey_capture_action is None:
            self._capturing_hotkey = None
            self.record_hotkey_button.setText("Listen for Input")
            self.playback_hotkey_button.setText("Listen for Input")

        if message != "Hotkey assignment cancelled.":
            QMessageBox.warning(
                self,
                "Hotkey Not Assigned",
                message
            )

    def refresh_hotkeys(self, _hotkeys=None):
        hotkeys = self.macro_engine.get_hotkeys()

        record_text = self.macro_engine.describe_hotkey(
            hotkeys.get("record_toggle")
        )

        playback_text = self.macro_engine.describe_hotkey(
            hotkeys.get("playback_toggle")
        )

        self.record_hotkey_label.setText(
            f"Record / Stop: {record_text}"
        )

        self.playback_hotkey_label.setText(
            f"Playback: {playback_text}"
        )

    def update_hotkey_playback_options(self, *_args):
        self.macro_engine.set_hotkey_playback_options(
            speed=self.speed_spin.value(),
            repeat_count=self.repeat_spin.value()
        )

    # ======================================
    # RECORDING
    # ======================================

    def start_recording(self):
        if self.macro_engine.playback_state != "stopped":
            return

        if self.macro_engine.recording_state != "stopped":
            return

        self.speed_spin.clearFocus()
        self.repeat_spin.clearFocus()
        self.setFocus()

        if self.macro_engine.start_recording(clear=True):
            self.timeline_list.clear()

    def toggle_recording_pause(self):
        if self.macro_engine.recording_state == "recording":
            self.macro_engine.pause_recording()

        elif self.macro_engine.recording_state == "paused":
            self.macro_engine.resume_recording()

    def stop_recording(self):
        self.macro_engine.stop_recording()

    def update_recording_state(self, state):
        if state == "recording":
            self.recording_status.setText("Recording...")
            self.record_button.setEnabled(False)
            self.record_pause_button.setEnabled(True)
            self.record_pause_button.setText("Pause")
            self.record_stop_button.setEnabled(True)

        elif state == "paused":
            self.recording_status.setText("Recording paused")
            self.record_button.setEnabled(False)
            self.record_pause_button.setEnabled(True)
            self.record_pause_button.setText("Resume")
            self.record_stop_button.setEnabled(True)

        else:
            self.recording_status.setText("Ready to record")
            self.record_button.setEnabled(
                self.macro_engine.playback_state == "stopped"
            )
            self.record_pause_button.setEnabled(False)
            self.record_pause_button.setText("Pause")
            self.record_stop_button.setEnabled(False)

        self._update_general_controls()

    # ======================================
    # PLAYBACK
    # ======================================

    def start_playback(self):
        if self.macro_engine.recording_state != "stopped":
            return

        started = self.macro_engine.play(
            speed=self.speed_spin.value(),
            repeat_count=self.repeat_spin.value()
        )

        if not started:
            if not self.macro_engine.actions:
                QMessageBox.information(
                    self,
                    "No Actions",
                    "Record or load a macro before playing it."
                )

    def toggle_playback_pause(self):
        if self.macro_engine.playback_state == "playing":
            self.macro_engine.pause_playback()

        elif self.macro_engine.playback_state == "paused":
            self.macro_engine.resume_playback()

    def stop_playback(self):
        self.macro_engine.stop_playback()

    def update_playback_state(self, state):
        if state == "playing":
            self.playback_status.setText("Playing...")
            self.play_button.setEnabled(False)
            self.play_pause_button.setEnabled(True)
            self.play_pause_button.setText("Pause")
            self.play_stop_button.setEnabled(True)

        elif state == "paused":
            self.playback_status.setText("Playback paused")
            self.play_button.setEnabled(False)
            self.play_pause_button.setEnabled(True)
            self.play_pause_button.setText("Resume")
            self.play_stop_button.setEnabled(True)

        else:
            self.playback_status.setText("Ready to play")
            self.play_button.setEnabled(
                bool(self.macro_engine.actions)
            )
            self.play_pause_button.setEnabled(False)
            self.play_pause_button.setText("Pause")
            self.play_stop_button.setEnabled(False)

        self._update_general_controls()

    def _update_general_controls(self):
        idle = (
            self.macro_engine.recording_state == "stopped"
            and self.macro_engine.playback_state == "stopped"
        )

        self.record_button.setEnabled(idle)
        self.play_button.setEnabled(
            idle and bool(self.macro_engine.actions)
        )

        self.save_macro_button.setEnabled(
            idle and bool(self.macro_engine.actions)
        )

        self.load_macro_button.setEnabled(idle)
        self.delete_macro_button.setEnabled(idle)

        self.delay_button.setEnabled(
            idle and self.timeline_list.currentRow() >= 0
        )

        self.move_up_button.setEnabled(
            idle and self.timeline_list.currentRow() > 0
        )

        self.move_down_button.setEnabled(
            idle
            and 0 <= self.timeline_list.currentRow()
            < len(self.macro_engine.actions) - 1
        )

        self.remove_action_button.setEnabled(
            idle and self.timeline_list.currentRow() >= 0
        )

    # ======================================
    # TIMELINE
    # ======================================

    def refresh_timeline(self, actions=None):
        if actions is None:
            actions = self.macro_engine.actions

        selected_row = self.timeline_list.currentRow()

        self._updating_timeline = True
        self.timeline_list.clear()

        previous_time = 0.0

        for index, action in enumerate(actions):
            action_time = float(action.get("time", 0.0))
            delay = max(0.0, action_time - previous_time)

            label = self._describe_action(action)

            item = QListWidgetItem(
                f"{index + 1:03d}    {label}    ·    +{delay:.3f}s"
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                index
            )

            self.timeline_list.addItem(item)

            previous_time = action_time

        self._updating_timeline = False

        count = len(actions)
        self.action_count_label.setText(
            f"{count} action" if count == 1 else f"{count} actions"
        )

        if count:
            self.timeline_list.setCurrentRow(
                min(max(selected_row, 0), count - 1)
            )

        self._update_general_controls()

    @staticmethod
    def _describe_action(action):
        input_type = action.get("input_type")
        control = action.get("control", "")
        state = action.get("state", "")

        if input_type == "keyboard":
            return f"Keyboard  ·  {control}  ·  {state}"

        if input_type == "button":
            return f"Mouse  ·  {control} button  ·  {state}"

        if input_type == "mouse" and control == "MOVE":
            return (
                f"Mouse movement  ·  "
                f"X: {action.get('x')}  Y: {action.get('y')}"
            )

        if input_type == "mouse":
            return f"Mouse scroll  ·  {control}"

        return f"{input_type}  ·  {control}  ·  {state}"

    def edit_selected_delay(self):
        row = self.timeline_list.currentRow()

        if row < 0 or row >= len(self.macro_engine.actions):
            return

        actions = list(self.macro_engine.actions)

        previous_time = (
            float(actions[row - 1].get("time", 0.0))
            if row > 0 else 0.0
        )

        current_time = float(actions[row].get("time", 0.0))
        current_delay = max(0.0, current_time - previous_time)

        delay, accepted = QInputDialog.getDouble(
            self,
            "Edit Action Delay",
            "Delay before this action (seconds):",
            current_delay,
            0.0,
            86400.0,
            3
        )

        if not accepted:
            return

        offset = delay - current_delay

        for index in range(row, len(actions)):
            actions[index]["time"] = max(
                0.0,
                float(actions[index].get("time", 0.0)) + offset
            )

        self.macro_engine.replace_actions(actions)

    def move_selected_action(self, direction):
        row = self.timeline_list.currentRow()

        if row < 0:
            return

        target = row + direction

        actions = [
            dict(action)
            for action in self.macro_engine.actions
        ]

        if target < 0 or target >= len(actions):
            return

        delays = []
        previous_time = 0.0

        for action in actions:
            action_time = float(action.get("time", 0.0))
            delays.append(max(0.0, action_time - previous_time))
            previous_time = action_time

        actions[row], actions[target] = (
            actions[target],
            actions[row]
        )

        delays[row], delays[target] = (
            delays[target],
            delays[row]
        )

        current_time = 0.0

        for action, delay in zip(actions, delays):
            current_time += delay
            action["time"] = current_time

        if self.macro_engine.replace_actions(actions):
            self.timeline_list.setCurrentRow(target)

    def remove_selected_action(self):
        row = self.timeline_list.currentRow()

        if row < 0:
            return

        actions = list(self.macro_engine.actions)

        if row >= len(actions):
            return

        del actions[row]

        if self.macro_engine.replace_actions(actions):
            if actions:
                self.timeline_list.setCurrentRow(
                    min(row, len(actions) - 1)
                )

    # ======================================
    # MACRO LIBRARY
    # ======================================

    def refresh_library(self):
        selected_path = None

        current = self.library_list.currentItem()

        if current:
            selected_path = current.data(
                Qt.ItemDataRole.UserRole
            )

        self.library_list.clear()

        for path in self.macro_engine.list_macros():
            item = QListWidgetItem(path.stem)

            item.setData(
                Qt.ItemDataRole.UserRole,
                str(path)
            )

            self.library_list.addItem(item)

            if selected_path == str(path):
                self.library_list.setCurrentItem(item)

    def save_macro(self):
        if not self.macro_engine.actions:
            return

        name, accepted = QInputDialog.getText(
            self,
            "Save Macro",
            "Macro name:"
        )

        if not accepted:
            return

        if not name.strip():
            return

        try:
            path = self.macro_engine.save_macro(name)
            self.refresh_library()

            for index in range(self.library_list.count()):
                item = self.library_list.item(index)

                if item.data(Qt.ItemDataRole.UserRole) == str(path):
                    self.library_list.setCurrentItem(item)
                    break

        except Exception as error:
            logger.exception("Could not save macro.")

            QMessageBox.critical(
                self,
                "Save Failed",
                f"Could not save macro:\n{error}"
            )

    def load_selected_macro(self):
        item = self.library_list.currentItem()

        if item is None:
            return

        path = item.data(Qt.ItemDataRole.UserRole)

        result = QMessageBox.question(
            self,
            "Load Macro",
            "Loading this macro will replace the current timeline.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        try:
            self.macro_engine.load_macro(Path(path))

        except Exception as error:
            logger.exception("Could not load macro.")

            QMessageBox.critical(
                self,
                "Load Failed",
                f"Could not load macro:\n{error}"
            )

    def delete_selected_macro(self):
        item = self.library_list.currentItem()

        if item is None:
            return

        path = Path(
            item.data(Qt.ItemDataRole.UserRole)
        )

        result = QMessageBox.question(
            self,
            "Delete Macro",
            f"Are you sure you want to delete '{path.stem}'?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        try:
            path.unlink()
            self.refresh_library()

        except Exception as error:
            logger.exception("Could not delete macro.")

            QMessageBox.critical(
                self,
                "Delete Failed",
                f"Could not delete macro:\n{error}"
            )
