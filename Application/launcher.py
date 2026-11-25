
import ctypes
import subprocess
import sys
from pathlib import Path


def show_error(message):
    ctypes.windll.user32.MessageBoxW(
        None,
        message,
        "Synapse",
        0x10
    )


def get_install_directory():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent.parent


def main():
    install_directory = get_install_directory()
    application_directory = install_directory / "Application"

    python_executable = (
        install_directory
        / ".venv"
        / "Scripts"
        / "pythonw.exe"
    )

    application_entry = application_directory / "main.py"

    if not python_executable.is_file():
        show_error(
            "Could not find Synapse's Python environment.\n\n"
            "Expected:\n"
            f"{python_executable}"
        )
        return

    if not application_entry.is_file():
        show_error(
            "Could not find Synapse's application entry point.\n\n"
            f"{application_entry}"
        )
        return

    try:
        subprocess.Popen(
            [
                str(python_executable),
                str(application_entry)
            ],
            cwd=str(application_directory),
            creationflags=subprocess.CREATE_NO_WINDOW,
            close_fds=True
        )

    except Exception as error:
        show_error(
            "Synapse could not be started.\n\n"
            f"{error}"
        )


if __name__ == "__main__":
    main()
