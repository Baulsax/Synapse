import re
import sys
from pathlib import Path


def load_app_version():
    """Load and validate the application's version."""

    if getattr(sys, "frozen", False):
        version_path = Path(sys._MEIPASS) / "version.txt"
    else:
        version_path = Path(__file__).resolve().parent.parent / "version.txt"

    try:
        version = version_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(
            f"Could not read application version file: {version_path}"
        ) from exc

    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise RuntimeError(
            f"Invalid application version '{version}'. "
            "Expected Major.Minor.Patch, for example 0.1.0."
        )

    return version


APP_VERSION = load_app_version()