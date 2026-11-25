
import json
import logging
import threading
import uuid

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from pynput import keyboard

from core.workflow_engine import WorkflowEngine
from core.ui_runtime import WorkflowUIRuntime
from core.app_paths import (
    ensure_app_data_dirs,
    get_workflows_dir,
    get_workflow_triggers_file,
)


logger = logging.getLogger(__name__)


class _WorkflowManagerSignals(QObject):
    activity_event = Signal(object)
    status_changed = Signal()


class WorkflowManager:

    MAX_ACTIVITY_EVENTS = 100

    def __init__(self):
        ensure_app_data_dirs()

        self.workflows_folder = get_workflows_dir()
        self.triggers_file = get_workflow_triggers_file()

        self.engines = {}

        self.hotkey_bindings = {}
        self.input_bindings = {}

        self.activity_history = []
        self._activity_lock = threading.Lock()
        self.signals = _WorkflowManagerSignals()

        self.ui_runtime = WorkflowUIRuntime()

        self.ui_runtime.button_clicked.connect(
            self._handle_ui_button_clicked
        )

        self.ui_runtime.window_closed.connect(
            self._handle_ui_window_closed
        )

        self.listener = None
        self.is_listening = False

        self.load_bindings()
        self.refresh_input_bindings()

    # -------------------------
    # Storage paths
    # -------------------------

    def _sync_storage_paths(self):
        ensure_app_data_dirs()

        self.workflows_folder = get_workflows_dir()
        self.triggers_file = get_workflow_triggers_file()

    @staticmethod
    def _normalize_folder(folder=None):
        if folder is None:
            folder = get_workflows_dir()

        return Path(folder).expanduser().resolve()

    @classmethod
    def _engine_key(cls, workflow_name, folder=None):
        normalized_folder = cls._normalize_folder(folder)

        return (
            str(normalized_folder),
            workflow_name
        )

    def remove_engine(self, workflow_name, folder=None):
        key = self._engine_key(workflow_name, folder)
        engine = self.engines.pop(key, None)

        if engine is not None:
            engine.set_lifecycle_callback(None)
            self.signals.status_changed.emit()

        return engine

    # -------------------------
    # Workflow enabled state
    # -------------------------

    def is_workflow_enabled(self, workflow_name, folder=None):
        """
        Read the workflow's automatic-trigger enabled state.

        Workflows without an enabled property are treated as enabled
        for backwards compatibility.

        Invalid or unreadable workflow files fail closed so an
        automatic trigger cannot accidentally start them.
        """
        folder = self._normalize_folder(folder)

        workflow_path = (
            folder / f"{workflow_name}.json"
        )

        if not workflow_path.exists():
            return False

        try:
            with open(
                workflow_path,
                "r",
                encoding="utf-8"
            ) as file:
                workflow_data = json.load(file)

            if not isinstance(workflow_data, dict):
                return False

            enabled = workflow_data.get("enabled", True)

            if not isinstance(enabled, bool):
                logger.warning(
                    "Workflow %s has an invalid enabled value.",
                    workflow_name
                )
                return False

            return enabled

        except Exception:
            logger.exception(
                "Could not read enabled state for workflow %s",
                workflow_name
            )
            return False

    # -------------------------
    # Activity and status
    # -------------------------

    def _find_engine_key(self, engine):
        for key, candidate in self.engines.items():
            if candidate is engine:
                return key

        return None

    def _get_engine_name(self, engine):
        key = self._find_engine_key(engine)

        if key is not None:
            return key[1]

        return "Unknown workflow"

    def _on_engine_lifecycle(self, engine, event, message=None):
        workflow_name = self._get_engine_name(engine)

        event_titles = {
            "started": "Workflow started",
            "completed": "Workflow completed",
            "stopped": "Workflow stopped",
            "error": "Workflow error",
            "button_started": "UI button triggered",
            "button_completed": "UI button finished",
        }

        title = event_titles.get(
            event,
            "Workflow activity"
        )

        if event == "error" and message:
            description = str(message)
        elif event in ("button_started", "button_completed") and message:
            description = f"Button: {message}"
        else:
            description = workflow_name

        activity = {
            "workflow": workflow_name,
            "event": event,
            "title": title,
            "message": description,
            "timestamp": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
        }

        with self._activity_lock:
            self.activity_history.insert(0, activity)

            del self.activity_history[
                self.MAX_ACTIVITY_EVENTS:
            ]

        self.signals.activity_event.emit(activity)
        self.signals.status_changed.emit()

    def get_activity_history(self, limit=20):
        with self._activity_lock:
            if limit is None:
                return list(self.activity_history)

            return list(self.activity_history[:max(0, limit)])

    def clear_activity_history(self):
        with self._activity_lock:
            self.activity_history.clear()

        self.signals.status_changed.emit()

    def get_workflow_status(self, workflow_name, folder=None):
        key = self._engine_key(workflow_name, folder)
        engine = self.engines.get(key)

        if engine is None:
            return "Idle"

        if engine.is_active:
            return "Running"

        if engine.last_error:
            return "Error"

        return "Idle"

    def get_workflow_statuses(self, folder=None):
        normalized_folder = str(
            self._normalize_folder(folder)
        )

        statuses = {}

        for key, engine in list(self.engines.items()):
            if key[0] != normalized_folder:
                continue

            if engine.is_active:
                status = "Running"
            elif engine.last_error:
                status = "Error"
            else:
                status = "Idle"

            statuses[key[1]] = status

        return statuses

    # -------------------------
    # Workflow UI events
    # -------------------------

    def _find_engine_by_ui_id(self, workflow_id):
        for engine in self.engines.values():
            if engine.ui_workflow_id == workflow_id:
                return engine

        return None

    def _handle_ui_button_clicked(
        self,
        workflow_id,
        widget_id
    ):
        engine = self._find_engine_by_ui_id(workflow_id)

        if engine is None:
            return

        handler = getattr(
            engine,
            "handle_ui_button_click",
            None
        )

        if callable(handler):
            handler(widget_id)

    def _handle_ui_window_closed(self, workflow_id):
        engine = self._find_engine_by_ui_id(workflow_id)

        if engine is None:
            return

        handler = getattr(
            engine,
            "handle_ui_window_closed",
            None
        )

        if callable(handler):
            handler()
        else:
            self._stop_engine(engine)

        self.signals.status_changed.emit()

    # -------------------------
    # Engine lifecycle helpers
    # -------------------------

    @staticmethod
    def _stop_engine(engine):
        stop_handler = getattr(
            engine,
            "stop_all_executions",
            None
        )

        if callable(stop_handler):
            stop_handler()
        else:
            engine.stop()

    def close_all_windows(self):
        self.ui_runtime.close_all_windows()

    # -------------------------
    # Existing keyboard hotkeys
    # -------------------------

    def load_bindings(self):
        self._sync_storage_paths()

        if not self.triggers_file.exists():
            self.hotkey_bindings = {}
            return

        try:
            with open(
                self.triggers_file,
                "r",
                encoding="utf-8"
            ) as file:
                data = json.load(file)

            self.hotkey_bindings = (
                data if isinstance(data, dict) else {}
            )

        except Exception:
            logger.exception(
                "Could not load hotkey bindings."
            )

            self.hotkey_bindings = {}

    def save_bindings(self):
        try:
            self._sync_storage_paths()

            with open(
                self.triggers_file,
                "w",
                encoding="utf-8"
            ) as file:
                json.dump(
                    self.hotkey_bindings,
                    file,
                    indent=4
                )

        except Exception:
            logger.exception(
                "Could not save hotkey bindings."
            )

    def bind_hotkey(self, hotkey, workflow_name):
        self.hotkey_bindings[hotkey] = workflow_name
        self.save_bindings()

        if self.is_listening:
            self._restart_listener()

    def start_listener(self):
        if self.is_listening:
            return

        self.is_listening = True
        self._restart_listener()

    def stop_listener(self):
        self.is_listening = False

        if self.listener:
            self.listener.stop()
            self.listener = None

    def _restart_listener(self):
        if self.listener:
            self.listener.stop()
            self.listener = None

        if not self.hotkey_bindings:
            return

        hotkeys = {}

        for hotkey, workflow_name in self.hotkey_bindings.items():
            hotkeys[hotkey] = (
                lambda name=workflow_name:
                self.start_workflow(
                    name,
                    automatic=True
                )
            )

        self.listener = keyboard.GlobalHotKeys(hotkeys)
        self.listener.start()

    # -------------------------
    # Workflow rename
    # -------------------------

    def rename_workflow(
        self,
        old_name,
        new_name,
        folder=None
    ):
        if old_name == new_name:
            return

        folder = self._normalize_folder(folder)

        old_key = self._engine_key(old_name, folder)
        new_key = self._engine_key(new_name, folder)

        if old_key in self.engines:
            self.engines[new_key] = self.engines.pop(old_key)

        current_folder = self._normalize_folder(
            get_workflows_dir()
        )

        if folder == current_folder:
            changed = False

            for hotkey, workflow_name in list(
                self.hotkey_bindings.items()
            ):
                if workflow_name == old_name:
                    self.hotkey_bindings[hotkey] = new_name
                    changed = True

            if changed:
                self.save_bindings()

                if self.is_listening:
                    self._restart_listener()

            self.refresh_input_bindings()

        self.signals.status_changed.emit()

    # -------------------------
    # Input block helpers
    # -------------------------

    @staticmethod
    def _input_descriptor(block):
        if not block:
            return None

        fields = block.get("fields", {})
        extra_state = block.get("extraState", {})

        device = (
            extra_state.get("device")
            or fields.get("DEVICE")
        )

        control = (
            extra_state.get("control")
            or fields.get("CONTROL")
        )

        if not device or not control:
            return None

        if control in (
            "Click to add an input",
            "Click to capture"
        ):
            return None

        return device, control

    # -------------------------
    # Workflow input triggers
    # -------------------------

    def refresh_input_bindings(self):
        self._sync_storage_paths()
        self.input_bindings.clear()

        if not self.workflows_folder.exists():
            return

        active_folder = self._normalize_folder(
            self.workflows_folder
        )

        for workflow_path in active_folder.glob("*.json"):
            try:
                with open(
                    workflow_path,
                    "r",
                    encoding="utf-8"
                ) as file:
                    workflow_data = json.load(file)

                blocks = workflow_data.get(
                    "blocks", {}
                ).get("blocks", [])

                for block in blocks:
                    if block.get("type") != "automation_input_trigger":
                        continue

                    input_data = block.get(
                        "inputs", {}
                    ).get("INPUT", {})

                    input_block = (
                        input_data.get("block")
                        or input_data.get("shadow")
                    )

                    trigger = self._input_descriptor(
                        input_block
                    )

                    if not trigger:
                        continue

                    mode = block.get(
                        "fields", {}
                    ).get("MODE", "START")

                    binding = {
                        "workflow": workflow_path.stem,
                        "folder": str(active_folder),
                        "mode": mode
                    }

                    self.input_bindings.setdefault(
                        trigger, []
                    ).append(binding)

                logger.debug(
                    "Loaded input triggers for %s",
                    workflow_path.stem
                )

            except Exception:
                logger.exception(
                    "Could not read triggers from %s",
                    workflow_path.name
                )

    def handle_input_event(self, event):
        if event.state != "pressed":
            return

        # Continue forwarding events to engines so workflows that
        # are already running can still use their internal listeners.
        for engine in list(self.engines.values()):
            engine.handle_input_event(event)

        trigger = (
            event.device_name,
            event.control
        )

        bindings = self.input_bindings.get(
            trigger, []
        )

        for binding in bindings:
            workflow_name = binding["workflow"]
            folder = binding["folder"]
            mode = binding["mode"]

            # Disabled workflows must ignore every assigned
            # automatic trigger, including STOP and TOGGLE.
            if not self.is_workflow_enabled(
                workflow_name,
                folder
            ):
                continue

            engine = self.get_engine(
                workflow_name,
                folder
            )

            if mode == "STOP":
                self._stop_engine(engine)

            elif mode == "TOGGLE":
                if getattr(
                    engine,
                    "is_active",
                    engine.is_running
                ):
                    self._stop_engine(engine)
                else:
                    self.start_workflow(
                        workflow_name,
                        folder,
                        automatic=True
                    )

            else:
                self.start_workflow(
                    workflow_name,
                    folder,
                    automatic=True
                )

    # -------------------------
    # Workflow execution
    # -------------------------

    def start_workflow(
        self,
        workflow_name,
        folder=None,
        automatic=False
    ):
        self._sync_storage_paths()

        folder = self._normalize_folder(folder)

        workflow_path = (
            folder / f"{workflow_name}.json"
        )

        if not workflow_path.exists():
            logger.warning(
                "Workflow file not found: %s",
                workflow_path
            )
            return False

        # Automatic triggers respect the workflow's enabled state.
        # Manual Run actions remain available regardless of this flag.
        if automatic and not self.is_workflow_enabled(
            workflow_name,
            folder
        ):
            logger.debug(
                "Ignoring automatic trigger for disabled workflow %s",
                workflow_name
            )
            return False

        try:
            with open(
                workflow_path,
                "r",
                encoding="utf-8"
            ) as file:
                workflow_data = json.load(file)

            engine = self.get_engine(
                workflow_name,
                folder
            )

            return engine.start(workflow_data)

        except Exception:
            logger.exception(
                "Could not start workflow %s",
                workflow_name
            )
            return False

    def stop_workflow(self, workflow_name, folder=None):
        key = self._engine_key(workflow_name, folder)
        engine = self.engines.get(key)

        if engine:
            self._stop_engine(engine)
            self.signals.status_changed.emit()

    def stop_all(self):
        for engine in list(self.engines.values()):
            self._stop_engine(engine)

        self.signals.status_changed.emit()

    def get_engine(self, workflow_name, folder=None):
        key = self._engine_key(workflow_name, folder)

        if key not in self.engines:
            engine = WorkflowEngine()

            engine.ui_workflow_id = str(uuid.uuid4())
            engine.ui_runtime = self.ui_runtime

            engine.set_lifecycle_callback(
                self._on_engine_lifecycle
            )

            self.engines[key] = engine

        return self.engines[key]
