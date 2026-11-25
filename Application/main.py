
import sys
import logging
import ctypes
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import (
    QFontDatabase,
    QIcon,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import QApplication

from window import SynapseWindow

from core.version import APP_VERSION

from core.app_paths import (
    ensure_app_data_dirs,
    get_logs_dir,
)

from core.input_detection.pynput_provider import PynputInputProvider
from core.input_detection.input_manager import InputManager
from core.macro_engine import MacroEngine


def resource_path(relative_path):
    """Resolve bundled resources in development and packaged builds."""
    if getattr(sys, "frozen", False):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent

    return base_path / relative_path


def create_application_icon(image_path):
    """Create a centered, multi-resolution application icon."""

    source = QPixmap(str(image_path))

    if source.isNull():
        logging.warning("Could not load application icon: %s", image_path)
        return QIcon()

    icon = QIcon()

    for size in (16, 24, 32, 48, 64, 128, 256):
        canvas = QPixmap(size, size)
        canvas.fill(Qt.GlobalColor.transparent)

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        scaled = source.scaled(
            QSize(size, size),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        x = (size - scaled.width()) // 2
        y = (size - scaled.height()) // 2

        painter.drawPixmap(x, y, scaled)
        painter.end()

        icon.addPixmap(canvas)

    return icon


def configure_logging():
    """Configure Synapse's rotating application log file."""

    logs_directory = get_logs_dir()
    logs_directory.mkdir(parents=True, exist_ok=True)

    log_file = logs_directory / "synapse.log"

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )

    file_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler.setFormatter(formatter)

    logging.basicConfig(
        level=logging.INFO,
        handlers=[file_handler],
        force=True,
    )

    logging.info("Synapse logging configured.")
    logging.info("Log file: %s", log_file)


# Give Windows a distinct application identity.
if sys.platform == "win32":
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Synapse.Synapse"
        )
    except Exception:
        pass


app = QApplication(sys.argv)

# Synapse application identity.
app.setApplicationDisplayName("Synapse")
app.setApplicationVersion(APP_VERSION)
app.setOrganizationName("Synapse")
app.setApplicationName("Synapse")

# Initialize persistent user-data directories.
ensure_app_data_dirs()

# Initialize application logging.
configure_logging()

logging.info("Starting Synapse version %s.", APP_VERSION)

# Load the application icon.
icon_path = resource_path(Path("assets") / "synapse_logo.png")
app_icon = create_application_icon(icon_path)

if not app_icon.isNull():
    app.setWindowIcon(app_icon)

# Register bundled Open Sans fonts.
for font_file in (
    "OpenSans-Bold.ttf",
    "OpenSans-ExtraBold.ttf",
):
    font_path = resource_path(Path("assets") / "fonts" / font_file)

    if font_path.exists():
        font_id = QFontDatabase.addApplicationFont(str(font_path))

        if font_id == -1:
            logging.warning(
                "Could not load font: %s",
                font_file
            )
    else:
        logging.warning(
            "Font file not found: %s",
            font_path
        )

# Create the macro engine before the main window so the Macros
# page can receive it during construction.
macro_engine = MacroEngine()

window = SynapseWindow(macro_engine=macro_engine)

# Explicitly set the main window icon.
if not app_icon.isNull():
    window.setWindowIcon(app_icon)

# Redirect logging immediately when the Logs folder changes.
window.settings_page.logs_directory_changed.connect(
    lambda _directory: configure_logging()
)

# Load the main stylesheet.
style_path = resource_path(Path("styles") / "styles.qss")

try:
    with open(style_path, "r", encoding="utf-8") as file:
        app.setStyleSheet(file.read())

except Exception:
    logging.exception("Could not load application stylesheet.")

# Load the Macros page stylesheet.
macros_style_path = resource_path(
    Path("styles") / "macros.qss"
)

try:
    with open(
        macros_style_path,
        "r",
        encoding="utf-8"
    ) as file:
        app.setStyleSheet(
            app.styleSheet() + "\n" + file.read()
        )

except Exception:
    logging.exception("Could not load Macros stylesheet.")

# ======================================
# SHARED INPUT INFRASTRUCTURE
# ======================================

input_provider = PynputInputProvider()
input_manager = InputManager(input_provider)

window.input_manager = input_manager


def forward_workflow_input(event):
    window.workflow_manager.handle_input_event(event)


input_manager.on_input = forward_workflow_input
input_manager.on_raw_input = macro_engine.handle_raw_input

# Start input detection.
input_manager.start()

logging.info("Synapse started successfully.")


# ======================================
# APPLICATION SHUTDOWN
# ======================================

def shutdown_application():
    logging.info("Synapse is shutting down.")

    macro_engine.stop_all()
    input_manager.stop()


app.aboutToQuit.connect(shutdown_application)

# Only start minimized when launched through Windows startup.
startup_launch = "--startup" in sys.argv[1:]

if startup_launch:
    settings = QSettings("Synapse", "Synapse")

    start_minimized = settings.value(
        "general/start_minimized",
        False,
        type=bool
    )

    if start_minimized:
        window.showMinimized()
    else:
        window.show()
else:
    window.show()

sys.exit(app.exec())
