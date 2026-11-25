
import json
import logging

from pathlib import Path

from PySide6.QtCore import QObject, Slot, Property, Signal

from core.workflow_engine import WorkflowEngine
from core.app_paths import get_workflows_dir


logger = logging.getLogger(__name__)


class WorkflowBridge(QObject):

    workflow_loaded = Signal(str)
    workflow_changed = Signal()
    workflow_saved = Signal()
    workflow_name_changed = Signal(str)
    workflow_renamed = Signal(str, str)

    input_captured = Signal(str, str, str)

    selected_block_changed = Signal(str)
    property_change_requested = Signal(str, str, str)

    def __init__(self, workflow_name, engine=None, input_manager=None):
        super().__init__()

        self._workflow_name = workflow_name
        self.is_dirty = False

        self.engine = engine or WorkflowEngine()
        self.input_manager = input_manager

        self._workflows_folder = Path(get_workflows_dir()).resolve()

    @property
    def workflows_folder(self):
        return self._workflows_folder

    @Property(str, notify=workflow_name_changed)
    def workflow_name(self):
        return self._workflow_name

    # ======================================
    # WORKFLOW SETTINGS STORAGE
    # ======================================

    def _settings_path(self, workflow_name=None):
        name = workflow_name or self._workflow_name

        return (
            self.workflows_folder
            / ".synapse_settings"
            / f"{name}.json"
        )

    def _load_workflow_settings(self, workflow_name=None):
        path = self._settings_path(workflow_name)

        if not path.exists():
            return {}

        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, dict):
                return {}

            settings = {}

            for setting_id, value in data.items():
                if not isinstance(setting_id, str):
                    continue

                try:
                    settings[setting_id] = float(value)
                except (TypeError, ValueError, OverflowError):
                    continue

            return settings

        except Exception:
            logger.exception(
                "Could not load settings for workflow %s",
                workflow_name or self._workflow_name
            )
            return {}

    # ======================================
    # JSON STORAGE
    # ======================================

    @staticmethod
    def _write_json_atomic(path, data):
        """
        Write workflow data through a temporary file so an interrupted
        save cannot leave the workflow JSON partially written.
        """
        path = Path(path)
        path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        temporary_path = path.with_suffix(
            path.suffix + ".tmp"
        )

        try:
            with open(
                temporary_path,
                "w",
                encoding="utf-8"
            ) as file:
                json.dump(
                    data,
                    file,
                    indent=4,
                    ensure_ascii=False
                )

            temporary_path.replace(path)

        except Exception:
            try:
                if temporary_path.exists():
                    temporary_path.unlink()
            except Exception:
                logger.exception(
                    "Could not remove temporary workflow file %s",
                    temporary_path
                )

            raise

    # ======================================
    # NAME VALIDATION
    # ======================================

    @staticmethod
    def is_valid_workflow_name(name):
        name = name.strip()

        if not name:
            return False

        invalid_characters = '<>:"/\\|?*'

        if any(char in name for char in invalid_characters):
            return False

        if name.endswith(".") or name.endswith(" "):
            return False

        reserved_names = {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }

        if name.upper() in reserved_names:
            return False

        return True

    # ======================================
    # RENAME
    # ======================================

    @Slot(str, result=bool)
    def rename_workflow(self, new_name):
        new_name = new_name.strip()

        if not self.is_valid_workflow_name(new_name):
            return False

        old_name = self._workflow_name

        if new_name == old_name:
            return True

        self.workflows_folder.mkdir(
            parents=True,
            exist_ok=True
        )

        old_path = self.workflows_folder / f"{old_name}.json"
        new_path = self.workflows_folder / f"{new_name}.json"

        if new_path.exists():
            return False

        try:
            if not old_path.exists():
                return False

            old_path.rename(new_path)

            old_settings_path = self._settings_path(old_name)
            new_settings_path = self._settings_path(new_name)

            if old_settings_path.exists():
                new_settings_path.parent.mkdir(
                    parents=True,
                    exist_ok=True
                )

                if new_settings_path.exists():
                    logger.warning(
                        "Settings file already exists for renamed workflow %s.",
                        new_name
                    )
                else:
                    old_settings_path.rename(new_settings_path)

        except Exception:
            logger.exception(
                "Could not rename workflow %s to %s",
                old_name,
                new_name
            )
            return False

        self._workflow_name = new_name

        self.workflow_name_changed.emit(new_name)
        self.workflow_renamed.emit(old_name, new_name)

        return True

    # ======================================
    # BLOCK SELECTION / PROPERTIES
    # ======================================

    @Slot(str)
    def report_selected_block(self, block_json):
        try:
            block_data = json.loads(block_json)

            if not isinstance(block_data, dict):
                block_data = {}

            self.selected_block_changed.emit(
                json.dumps(block_data)
            )

        except (TypeError, ValueError):
            logger.warning(
                "Received invalid selected-block data."
            )

            self.selected_block_changed.emit("{}")

    @Slot()
    def clear_selected_block(self):
        self.selected_block_changed.emit("{}")

    @Slot(str, str, str)
    def set_block_property(self, block_id, property_name, value):
        if not block_id or not property_name:
            return

        self.property_change_requested.emit(
            block_id,
            property_name,
            value
        )

    # ======================================
    # SAVE / LOAD
    # ======================================

    @Slot(str, str)
    def receive_workflow(self, workflow_json, workflow_name):
        self.workflows_folder.mkdir(
            parents=True,
            exist_ok=True
        )

        save_path = (
            self.workflows_folder
            / f"{self._workflow_name}.json"
        )

        try:
            workflow_data = json.loads(workflow_json)

            if not isinstance(workflow_data, dict):
                raise ValueError(
                    "Workflow data must be a JSON object."
                )

            # Read the existing workflow before saving so local
            # metadata, including the enabled state, is retained.
            existing_data = {}

            if save_path.exists():
                try:
                    with open(
                        save_path,
                        "r",
                        encoding="utf-8"
                    ) as file:
                        loaded_data = json.load(file)

                    if isinstance(loaded_data, dict):
                        existing_data = loaded_data

                except Exception:
                    logger.exception(
                        "Could not read existing metadata for workflow %s",
                        self._workflow_name
                    )
                    return

            # Blockly may only send workspace data. Preserve every
            # existing top-level property it did not send.
            for key, value in existing_data.items():
                if key not in workflow_data:
                    workflow_data[key] = value

            self._write_json_atomic(
                save_path,
                workflow_data
            )

        except Exception:
            logger.exception(
                "Could not save workflow %s",
                self._workflow_name
            )
            return

        self.is_dirty = False
        self.workflow_saved.emit()

    @Slot()
    def load_workflow(self):
        save_path = (
            self.workflows_folder
            / f"{self._workflow_name}.json"
        )

        if not save_path.exists():
            self.workflow_loaded.emit(
                json.dumps({
                    "blocks": {
                        "languageVersion": 0,
                        "blocks": []
                    }
                })
            )
            return

        try:
            with open(save_path, "r", encoding="utf-8") as file:
                workflow_data = json.load(file)

            if not isinstance(workflow_data, dict):
                raise ValueError(
                    "Workflow data must be a JSON object."
                )

        except Exception:
            logger.exception(
                "Could not load workflow %s",
                self._workflow_name
            )
            return

        self.is_dirty = False
        self.workflow_saved.emit()
        self.workflow_loaded.emit(json.dumps(workflow_data))

    @Slot()
    def mark_workflow_changed(self):
        self.is_dirty = True
        self.workflow_changed.emit()

    @Slot()
    def mark_workflow_saved(self):
        self.is_dirty = False
        self.workflow_saved.emit()

    # ======================================
    # EXECUTION
    # ======================================

    @Slot(str)
    def start_workflow(self, workflow_json):
        try:
            workflow_data = json.loads(workflow_json)
            settings = self._load_workflow_settings()

            self.engine.start(
                workflow_data,
                settings=settings
            )

        except Exception:
            logger.exception(
                "Could not start workflow from editor."
            )

    @Slot()
    def stop_workflow(self):
        self.engine.stop()

    # ======================================
    # INPUT CAPTURE
    # ======================================

    @Slot(str)
    def request_input_capture(self, block_id):
        if not self.input_manager:
            logger.warning(
                "Input detection is not available."
            )
            return

        def captured(event):
            self.input_captured.emit(
                block_id,
                event.device_name,
                event.control
            )

        self.input_manager.capture_next_input(captured)
