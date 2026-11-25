
import logging
import threading
import time

from pynput.keyboard import Controller as KeyboardController
from pynput.mouse import Controller as MouseController, Button

from .control_flow import (
    ControlFlowMixin,
    _BreakLoop,
    _ContinueLoop,
    _ReturnFunction,
)
from .values import ValuesMixin
from .inputs import InputsMixin
from .ui import UIMixin


logger = logging.getLogger(__name__)


class WorkflowEngine(
    ControlFlowMixin,
    ValuesMixin,
    InputsMixin,
    UIMixin
):

    MIN_CONTINUOUS_LOOP_INTERVAL = 0.001
    MAX_FUNCTION_CALL_DEPTH = 100

    # For longer waits, leave this much time for the precision phase.
    # This accommodates the typical Windows scheduler wake-up delay.
    PRECISE_WAIT_WINDOW = 0.020

    TEXT_CHARACTER_DELAY = 0.01
    TEXT_SHIFTED_CHARACTER_DELAY = 0.025

    SHIFTED_TEXT_CHARACTERS = set(
        '!@#$%^&*()_+{}|:"<>?~'
    )

    FUNCTION_DEFINITION_TYPES = {
        "procedures_defnoreturn",
        "procedures_defreturn"
    }

    FUNCTION_CALL_TYPES = {
        "procedures_callnoreturn",
        "procedures_callreturn"
    }

    FUNCTION_ARGUMENT_TYPES = {
        "argument_reporter_string_number",
        "argument_reporter_boolean"
    }

    def __init__(self):
        self.mouse = MouseController()
        self.keyboard = KeyboardController()

        self.is_running = False
        self.stop_event = threading.Event()
        self.execution_thread = None

        self._state_lock = threading.Lock()
        self._stop_inputs = set()
        self._held_keys = set()

        self._variables = {}
        self._variable_names = {}

        self._functions = {}

        # Lifecycle tracking.
        self.last_error = None
        self.lifecycle_callback = None

        # UI runtime
        self.ui_workflow_id = None
        self.ui_runtime = None
        self._workflow_data = None
        self._ui_windows_active = False
        self._ui_window_ids = set()
        self._ui_window_lock = threading.Lock()

        # Button event execution tracking
        self.allow_multiple_ui_executions = False
        self._button_execution_lock = threading.Lock()
        self._button_executions = {}

        # Shared state lock.
        self._execution_lock = threading.RLock()

        # Each execution thread has its own stop event,
        # loop depth, function scopes, and loop-variable scopes.
        self._execution_context = threading.local()

    # ======================================
    # LIFECYCLE NOTIFICATIONS
    # ======================================

    def set_lifecycle_callback(self, callback):
        self.lifecycle_callback = callback

    def _notify_lifecycle(self, event, message=None):
        callback = self.lifecycle_callback

        if not callback:
            return

        try:
            callback(self, event, message)
        except Exception:
            logger.exception(
                "Workflow lifecycle callback failed."
            )

    # ======================================
    # EXECUTION STATUS
    # ======================================

    @property
    def is_active(self):
        if self.is_running:
            return True

        with self._ui_window_lock:
            if self._ui_windows_active:
                return True

        with self._button_execution_lock:
            for executions in self._button_executions.values():
                for execution in executions:
                    if execution["thread"].is_alive():
                        return True

        return False

    # ======================================
    # WORKFLOW CONTROL
    # ======================================

    def start(self, workflow_data, settings=None):
        """
        Start a workflow.

        The settings argument is retained temporarily for compatibility
        with older WorkflowManager calls. Workflow Setting blocks now
        read their values directly from their serialized VALUE fields.
        """
        self._cancel_button_executions()

        with self._button_execution_lock:
            previous_threads = [
                execution["thread"]
                for executions in self._button_executions.values()
                for execution in executions
            ]

        for thread in previous_threads:
            if thread is not threading.current_thread():
                thread.join(timeout=1.0)

        with self._state_lock:
            if self.is_running:
                logger.warning(
                    "Workflow start rejected: already running."
                )
                return False

            if self._has_active_button_executions():
                logger.warning(
                    "Workflow start rejected: previous button "
                    "executions are still stopping."
                )
                return False

            self.stop_event.clear()
            self._stop_inputs = self._collect_stop_inputs(workflow_data)

            with self._execution_lock:
                self._held_keys.clear()
                self._workflow_data = workflow_data

                self._initialize_variables(workflow_data)
                self._initialize_functions(workflow_data)

            with self._ui_window_lock:
                self._ui_windows_active = bool(
                    self.ui_runtime
                    and self.ui_runtime.windows.get(
                        self.ui_workflow_id,
                        {}
                    )
                )

            self.last_error = None
            self.is_running = True

            self.execution_thread = threading.Thread(
                target=self._execute,
                args=(workflow_data,),
                daemon=True
            )

            self._notify_lifecycle("started")
            self.execution_thread.start()

        return True

    def stop(self):
        self.stop_event.set()
        self._cancel_button_executions()
        self._close_all_ui_windows()

    def stop_all_executions(self):
        self.stop()

    def _close_all_ui_windows(self):
        with self._ui_window_lock:
            self._ui_windows_active = False

            window_ids = set(self._ui_window_ids)
            self._ui_window_ids.clear()

        if not self.ui_runtime or not self.ui_workflow_id:
            return

        existing_windows = self.ui_runtime.windows.get(
            self.ui_workflow_id,
            {}
        )

        window_ids.update(existing_windows.keys())

        for window_id in window_ids:
            self.ui_runtime.submit(
                self.ui_workflow_id,
                "close_window",
                {
                    "window_id": str(window_id)
                }
            )

    def _cancel_button_executions(self):
        with self._button_execution_lock:
            for executions in self._button_executions.values():
                for execution in executions:
                    execution["stop_event"].set()

    def _has_active_button_executions(self):
        with self._button_execution_lock:
            return any(
                execution["thread"].is_alive()
                for executions in self._button_executions.values()
                for execution in executions
            )

    def handle_input_event(self, event):
        if not self.is_running or event.state != "pressed":
            return

        trigger = (event.device_name, event.control)

        if trigger in self._stop_inputs:
            logger.info(
                "Workflow stop input detected: %s %s",
                event.device_name,
                event.control
            )
            self.stop()

    # ======================================
    # PRECISE TIMING
    # ======================================

    @classmethod
    def _wait_precisely(cls, stop_event, duration_seconds):
        """
        Wait for the requested duration with better precision than
        time.sleep() provides on Windows.

        Short waits use a performance-counter spin phase because
        Windows thread sleeps can overshoot by several milliseconds.

        Longer waits use the stop event for most of the duration,
        then finish with a short precision phase.

        The stop event is checked throughout both phases.
        """
        if duration_seconds <= 0:
            return

        deadline = time.perf_counter() + duration_seconds

        remaining = deadline - time.perf_counter()

        if remaining > cls.PRECISE_WAIT_WINDOW:
            stop_event.wait(
                remaining - cls.PRECISE_WAIT_WINDOW
            )

        while not stop_event.is_set():
            remaining = deadline - time.perf_counter()

            if remaining <= 0:
                break

    # ======================================
    # EXECUTION
    # ======================================

    def _execute(self, workflow_data):
        previous = self._set_execution_context(self.stop_event)
        execution_error = None

        try:
            top_blocks = (
                workflow_data.get("blocks", {}).get("blocks", [])
            )

            if not top_blocks:
                return

            entry_block = None

            for block in top_blocks:
                block_type = block.get("type")

                if block_type in self.FUNCTION_DEFINITION_TYPES:
                    continue

                if block_type == "automation_input_trigger":
                    mode = block.get("fields", {}).get("MODE", "START")

                    if mode == "STOP":
                        continue

                    next_data = block.get("next", {}).get("block")

                    if next_data:
                        entry_block = next_data
                        break

                    continue

                if block_type == "automation_ui_button_clicked":
                    continue

                entry_block = block
                break

            if entry_block:
                self._execute_chain(entry_block)

        except Exception as exc:
            execution_error = exc
            self.last_error = str(exc) or type(exc).__name__

            logger.exception("Workflow execution failed.")

            self._notify_lifecycle(
                "error",
                self.last_error
            )

        finally:
            try:
                self._release_all_keys()
            except Exception:
                logger.exception(
                    "Failed to release held inputs after workflow execution."
                )

            with self._state_lock:
                self.is_running = False
                self._stop_inputs.clear()

            self._restore_execution_context(previous)

            if execution_error is None:
                if self.stop_event.is_set():
                    self._notify_lifecycle("stopped")
                else:
                    self._notify_lifecycle("completed")

    def _execute_chain(self, first_block):
        current_block = first_block
        stop_event = self._current_stop_event()

        while current_block and not stop_event.is_set():
            block_type = current_block.get("type")

            if block_type == "automation_repeat_until_stopped":
                self._execute_repeat_until_stopped(current_block)

            elif block_type == "controls_if":
                self._execute_if(current_block)

            elif block_type in (
                "controls_repeat_ext",
                "controls_repeat"
            ):
                self._execute_repeat(current_block)

            elif block_type == "controls_whileUntil":
                self._execute_while_until(current_block)

            elif block_type == "controls_for":
                self._execute_for(current_block)

            elif block_type == "controls_forEach":
                self._execute_for_each(current_block)

            elif block_type == "controls_flow_statements":
                flow = current_block.get(
                    "fields", {}
                ).get("FLOW", "BREAK")

                if self._current_loop_depth() <= 0:
                    logger.warning(
                        "%s encountered outside a loop.",
                        flow.title()
                    )
                elif flow == "CONTINUE":
                    raise _ContinueLoop()
                else:
                    raise _BreakLoop()

            elif block_type == "automation_break_loop":
                if self._current_loop_depth() > 0:
                    raise _BreakLoop()

                logger.warning(
                    "Break Loop encountered outside a loop."
                )

            elif block_type == "procedures_ifreturn":
                condition = self._evaluate_value(
                    self._get_input_block(current_block, "CONDITION")
                )

                if condition:
                    raise _ReturnFunction(
                        self._evaluate_value(
                            self._get_input_block(current_block, "VALUE")
                        )
                    )

            elif block_type in self.FUNCTION_DEFINITION_TYPES:
                pass

            else:
                self._execute_block(current_block)

            if stop_event.is_set():
                break

            current_block = current_block.get(
                "next", {}
            ).get("block")

    # ======================================
    # BLOCK EXECUTION
    # ======================================

    def _execute_block(self, block):
        stop_event = self._current_stop_event()

        if stop_event.is_set():
            return

        block_type = block.get("type")
        fields = block.get("fields", {})

        # ------------------------------
        # Functions
        # ------------------------------

        if block_type in self.FUNCTION_CALL_TYPES:
            self._execute_function_call(block)

        # ------------------------------
        # Variables
        # ------------------------------

        elif block_type == "variables_set":
            variable_field = fields.get("VAR")
            variable_key = self._get_variable_key(variable_field)

            if variable_key is None:
                logger.warning(
                    "Set Variable block has no valid variable."
                )
                return

            value = self._evaluate_value(
                self._get_input_block(block, "VALUE")
            )

            if not self._set_scoped_variable(variable_field, value):
                with self._execution_lock:
                    self._variables[variable_key] = value

        elif block_type == "math_change":
            variable_field = fields.get("VAR")
            variable_key = self._get_variable_key(variable_field)

            if variable_key is None:
                logger.warning(
                    "Change Variable block has no valid variable."
                )
                return

            delta = self._safe_number(
                self._evaluate_value(
                    self._get_input_block(block, "DELTA")
                )
            )

            found, current_value = self._get_scoped_variable(
                variable_field
            )

            if found:
                self._set_scoped_variable(
                    variable_field,
                    self._safe_number(current_value) + delta
                )
            else:
                with self._execution_lock:
                    current_value = self._safe_number(
                        self._variables.get(variable_key, 0)
                    )
                    self._variables[variable_key] = current_value + delta

        # ------------------------------
        # Timing
        # ------------------------------

        elif block_type == "automation_wait":
            duration_block = self._get_input_block(
                block,
                "DURATION"
            )

            if duration_block:
                duration_value = self._evaluate_value(
                    duration_block
                )
            else:
                # Backward compatibility with older saved Wait blocks.
                duration_value = fields.get("DURATION", 1000)

            duration_ms = self._safe_number(
                duration_value,
                0
            )

            if self._current_minimum_wait_loop_depth() > 0:
                duration_ms = max(1, duration_ms)

            self._wait_precisely(
                stop_event,
                duration_ms / 1000
            )

        # ------------------------------
        # UI
        # ------------------------------

        elif block_type == "automation_ui_create_window":
            self.create_ui_window(
                window_id=fields.get("WINDOW_ID", ""),
                title=fields.get("TITLE", "Workflow Window"),
                width=fields.get("WIDTH", 400),
                height=fields.get("HEIGHT", 300)
            )

        elif block_type == "automation_ui_create_label":
            layout = fields.get("LAYOUT", "AUTO")
            geometry = (
                self._get_ui_geometry(fields)
                if layout == "CUSTOM"
                else None
            )

            self.create_ui_label(
                window_id=fields.get("WINDOW_ID", ""),
                widget_id=fields.get("WIDGET_ID", ""),
                text=self._evaluate_value(
                    self._get_input_block(block, "TEXT")
                ),
                geometry=geometry
            )

        elif block_type == "automation_ui_create_button":
            layout = fields.get("LAYOUT", "AUTO")
            geometry = (
                self._get_ui_geometry(fields)
                if layout == "CUSTOM"
                else None
            )

            self.create_ui_button(
                window_id=fields.get("WINDOW_ID", ""),
                widget_id=fields.get("WIDGET_ID", ""),
                text=self._evaluate_value(
                    self._get_input_block(block, "TEXT")
                ),
                geometry=geometry
            )

        elif block_type == "automation_ui_set_text":
            self.set_ui_text(
                widget_id=fields.get("WIDGET_ID", ""),
                text=self._evaluate_value(
                    self._get_input_block(block, "TEXT")
                )
            )

        elif block_type == "automation_ui_close_window":
            self.close_ui_window(
                window_id=fields.get("WINDOW_ID", "")
            )

        # ------------------------------
        # Mouse
        # ------------------------------

        elif block_type == "automation_left_click":
            self._mouse_click(Button.left)

        elif block_type == "automation_mouse_click":
            button_name = fields.get("BUTTON", "LEFT")

            buttons = {
                "LEFT": Button.left,
                "RIGHT": Button.right,
                "MIDDLE": Button.middle,
                "X1": Button.x1,
                "X2": Button.x2
            }

            button = buttons.get(button_name)

            if button is None:
                logger.warning(
                    "Unsupported mouse button: %s",
                    button_name
                )
            else:
                self._mouse_click(button)

        elif block_type == "automation_mouse_move":
            x = self._safe_number(fields.get("X", 0))
            y = self._safe_number(fields.get("Y", 0))

            if not stop_event.is_set():
                self.mouse.position = (int(x), int(y))

        elif block_type == "automation_mouse_scroll":
            amount = self._safe_number(
                fields.get("AMOUNT", 1)
            )

            if not stop_event.is_set():
                self.mouse.scroll(0, int(amount))

        # ------------------------------
        # Keyboard
        # ------------------------------

        elif block_type == "automation_key_press":
            key = self._resolve_key(fields.get("KEY"))

            if key is not None:
                self._press_key(key)

        elif block_type == "automation_key_down":
            key = self._resolve_key(fields.get("KEY"))

            if key is not None:
                self._key_down(key)

        elif block_type == "automation_key_up":
            key = self._resolve_key(fields.get("KEY"))

            if key is not None:
                self._key_up(key)

        elif block_type == "automation_type_text":
            self._type_text(str(fields.get("TEXT", "")))
