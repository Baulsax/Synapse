
import os
from pathlib import Path

from PySide6.QtCore import QSettings


APP_NAME = "Synapse"


def _get_app_data_directory():
    """Get Synapse's persistent user-data directory."""
    local_app_data = os.environ.get("LOCALAPPDATA")

    if local_app_data:
        return Path(local_app_data) / APP_NAME

    return Path.home() / "AppData" / "Local" / APP_NAME


APP_DATA_DIR = _get_app_data_directory()

# Default locations.
DEFAULT_WORKFLOWS_DIR = APP_DATA_DIR / "workflows"
DEFAULT_LOGS_DIR = APP_DATA_DIR / "logs"
DEFAULT_TEMPLATES_DIR = APP_DATA_DIR / "templates"

# Internal configuration remains in the default data directory.
CONFIG_DIR = APP_DATA_DIR / "settings"


def _get_settings():
    return QSettings("Synapse", "Synapse")


def get_workflows_dir():
    settings = _get_settings()
    configured_path = settings.value(
        "storage/workflows_directory",
        "",
        type=str
    )

    if configured_path:
        return Path(configured_path).expanduser()

    return DEFAULT_WORKFLOWS_DIR


def get_logs_dir():
    settings = _get_settings()
    configured_path = settings.value(
        "storage/logs_directory",
        "",
        type=str
    )

    if configured_path:
        return Path(configured_path).expanduser()

    return DEFAULT_LOGS_DIR


def get_templates_dir():
    settings = _get_settings()
    configured_path = settings.value(
        "storage/templates_directory",
        "",
        type=str
    )

    if configured_path:
        return Path(configured_path).expanduser()

    return DEFAULT_TEMPLATES_DIR


def set_workflows_dir(directory):
    path = Path(directory).expanduser().resolve()

    if not path.exists() or not path.is_dir():
        raise ValueError("The selected workflows folder does not exist.")

    settings = _get_settings()
    settings.setValue("storage/workflows_directory", str(path))
    settings.sync()

    if settings.status() != QSettings.Status.NoError:
        raise OSError("Could not save the workflows folder setting.")


def set_logs_dir(directory):
    path = Path(directory).expanduser().resolve()

    if not path.exists() or not path.is_dir():
        raise ValueError("The selected logs folder does not exist.")

    settings = _get_settings()
    settings.setValue("storage/logs_directory", str(path))
    settings.sync()

    if settings.status() != QSettings.Status.NoError:
        raise OSError("Could not save the logs folder setting.")


def set_templates_dir(directory):
    path = Path(directory).expanduser().resolve()

    if not path.exists() or not path.is_dir():
        raise ValueError("The selected templates folder does not exist.")

    settings = _get_settings()
    settings.setValue("storage/templates_directory", str(path))
    settings.sync()

    if settings.status() != QSettings.Status.NoError:
        raise OSError("Could not save the templates folder setting.")


# Compatibility constants for modules importing these paths directly.
# These represent the default paths; configurable paths should use
# the corresponding get_*_dir() functions.
WORKFLOWS_DIR = DEFAULT_WORKFLOWS_DIR
LOGS_DIR = DEFAULT_LOGS_DIR
TEMPLATES_DIR = DEFAULT_TEMPLATES_DIR

WORKFLOW_ORDER_FILE = APP_DATA_DIR / "workflow_order.json"
WORKFLOW_TRIGGERS_FILE = APP_DATA_DIR / "workflow_triggers.json"


def get_workflow_order_file():
    return get_workflows_dir().parent / "workflow_order.json"


def get_workflow_triggers_file():
    return get_workflows_dir().parent / "workflow_triggers.json"


def ensure_app_data_dirs():
    """Create Synapse's default and configured user-data directories."""
    for directory in (
        APP_DATA_DIR,
        DEFAULT_WORKFLOWS_DIR,
        DEFAULT_LOGS_DIR,
        DEFAULT_TEMPLATES_DIR,
        CONFIG_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    get_workflows_dir().mkdir(parents=True, exist_ok=True)
    get_logs_dir().mkdir(parents=True, exist_ok=True)
    get_templates_dir().mkdir(parents=True, exist_ok=True)
