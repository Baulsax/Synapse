
import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

from pathlib import Path, PurePosixPath


APP_NAME = "Synapse"
APP_EXE = "Synapse.exe"
HELPER_EXE = "SynapseUpdater.exe"

STAGING_FOLDER = "update-staging"

WAIT_TIMEOUT_SECONDS = 600
RETRY_DELAY_SECONDS = 0.5
FILE_RETRY_COUNT = 20

RESERVED_UPDATE_FILES = {
    "update-manifest.json",
    "update-manifest.json.tmp",
}

# The helper must never replace or delete itself.
# Synapse.exe is deliberately NOT protected: it can be replaced
# after the Synapse process has exited.
PROTECTED_FILES = {
    HELPER_EXE.casefold(),
    *RESERVED_UPDATE_FILES,
}

VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")

WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def get_staging_directory():
    local_app_data = os.environ.get("LOCALAPPDATA")

    if local_app_data:
        base = Path(local_app_data)
    else:
        base = Path.home() / "AppData" / "Local"

    return base / APP_NAME / STAGING_FOLDER


def show_message(title, message, error=False):
    flags = 0x10 if error else 0x40

    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            str(message),
            str(title),
            flags,
        )
    except Exception:
        pass


def safe_relative_path(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Invalid file path.")

    normalized = value.replace("\\", "/")

    if normalized.startswith("/") or ":" in normalized:
        raise ValueError(
            "Absolute or drive-qualified paths are not permitted."
        )

    parts = normalized.split("/")

    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("Unsafe relative path.")

    for part in parts:
        if part.endswith((" ", ".")):
            raise ValueError(
                f"Invalid Windows filename component: {part}"
            )

        if any(ord(character) < 32 for character in part):
            raise ValueError(
                "Control characters are not permitted in paths."
            )

        if any(character in '<>:"|?*' for character in part):
            raise ValueError(
                f"Invalid Windows filename component: {part}"
            )

        device_name = part.split(".")[0].upper()

        if device_name in WINDOWS_RESERVED_NAMES:
            raise ValueError(
                f"Reserved Windows filename: {part}"
            )

    relative = PurePosixPath(normalized)

    if relative.is_absolute():
        raise ValueError("Absolute paths are not permitted.")

    return relative


def resolve_inside(root, relative):
    root = Path(root).resolve()
    relative = safe_relative_path(relative)

    destination = root.joinpath(*relative.parts)

    # Reject symbolic links in any existing component.
    current = root

    for part in relative.parts:
        current = current / part

        if current.is_symlink():
            raise ValueError(
                f"Symbolic links are not permitted: {current}"
            )

    resolved_parent = destination.parent.resolve()

    try:
        resolved_parent.relative_to(root)
    except ValueError:
        raise ValueError(
            "Update path escapes its permitted directory."
        )

    return destination


def calculate_sha256(path):
    digest = hashlib.sha256()

    with open(path, "rb") as file:
        while True:
            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def wait_for_process(pid):
    if not isinstance(pid, int) or pid <= 0:
        raise ValueError("Invalid process ID.")

    kernel32 = ctypes.WinDLL(
        "kernel32",
        use_last_error=True,
    )

    synchronize = 0x00100000

    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint32,
    ]

    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.WaitForSingleObject.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]

    kernel32.CloseHandle.argtypes = [
        ctypes.c_void_p,
    ]

    handle = kernel32.OpenProcess(
        synchronize,
        False,
        pid,
    )

    if not handle:
        error = ctypes.get_last_error()

        # ERROR_INVALID_PARAMETER means the process no longer exists.
        if error == 87:
            return

        raise ctypes.WinError(error)

    try:
        result = kernel32.WaitForSingleObject(
            handle,
            int(WAIT_TIMEOUT_SECONDS * 1000),
        )

        if result == 0x00000102:
            raise TimeoutError(
                "Synapse did not close within the allowed time."
            )

        if result != 0:
            raise ctypes.WinError(
                ctypes.get_last_error()
            )

    finally:
        kernel32.CloseHandle(handle)


def load_json(path):
    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def validate_version(version):
    if (
        not isinstance(version, str)
        or not VERSION_PATTERN.fullmatch(version)
    ):
        raise ValueError("Invalid update version.")

    return version


def validate_manifest(manifest, plan):
    if not isinstance(manifest, dict):
        raise ValueError("Invalid update manifest.")

    if not isinstance(plan, dict):
        raise ValueError("Invalid update plan.")

    manifest_version = validate_version(
        manifest.get("version")
    )

    plan_version = validate_version(
        plan.get("version")
    )

    if manifest_version != plan_version:
        raise ValueError("Manifest version mismatch.")

    files = manifest.get("files")

    if not isinstance(files, dict):
        raise ValueError("Manifest file list is invalid.")

    changed_files = plan.get("changed_files")
    deleted_files = plan.get("deleted_files")

    if not isinstance(changed_files, list):
        raise ValueError("Invalid changed-files list.")

    if not isinstance(deleted_files, list):
        raise ValueError("Invalid deleted-files list.")

    # Validate the manifest and reject Windows case-insensitive
    # collisions before touching the installation.
    normalized_manifest = {}

    for filename, entry in files.items():
        relative = safe_relative_path(filename)
        normalized = relative.as_posix().casefold()

        if normalized in normalized_manifest:
            raise ValueError(
                "The manifest contains case-insensitive path collisions: "
                f"{normalized_manifest[normalized]} and {filename}"
            )

        normalized_manifest[normalized] = filename

        if normalized in PROTECTED_FILES:
            raise ValueError(
                f"The manifest contains a protected filename: {filename}"
            )

        if not isinstance(entry, dict):
            raise ValueError(
                f"Invalid manifest entry: {filename}"
            )

        size = entry.get("size")
        digest = entry.get("sha256")

        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
        ):
            raise ValueError(
                f"Invalid file size: {filename}"
            )

        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(
                character not in "0123456789abcdefABCDEF"
                for character in digest
            )
        ):
            raise ValueError(
                f"Invalid SHA-256: {filename}"
            )

    # Validate changed and deleted lists.
    changed_normalized = {}
    deleted_normalized = {}

    for filename in changed_files:
        relative = safe_relative_path(filename)
        normalized = relative.as_posix().casefold()

        if normalized in PROTECTED_FILES:
            raise ValueError(
                f"Update attempted to modify a protected file: {filename}"
            )

        if normalized in changed_normalized:
            raise ValueError(
                f"Duplicate changed file path: {filename}"
            )

        changed_normalized[normalized] = filename

        # Require exact spelling to match the manifest.
        if normalized not in normalized_manifest:
            raise ValueError(
                f"Missing manifest entry: {filename}"
            )

        if normalized_manifest[normalized] != filename:
            raise ValueError(
                f"Changed-file path casing does not match manifest: {filename}"
            )

    for filename in deleted_files:
        relative = safe_relative_path(filename)
        normalized = relative.as_posix().casefold()

        if normalized in PROTECTED_FILES:
            raise ValueError(
                f"Update attempted to delete a protected file: {filename}"
            )

        if normalized in deleted_normalized:
            raise ValueError(
                f"Duplicate deleted file path: {filename}"
            )

        deleted_normalized[normalized] = filename

        if normalized in normalized_manifest:
            raise ValueError(
                f"Deleted file is still present in manifest: {filename}"
            )

    if set(changed_normalized) & set(deleted_normalized):
        raise ValueError(
            "A file cannot be both changed and deleted."
        )

    return files


def verify_payload(staging, manifest, plan):
    payload = staging / "payload"
    files = manifest["files"]

    for filename in plan["changed_files"]:
        source = resolve_inside(
            payload,
            filename,
        )

        if not source.is_file():
            raise FileNotFoundError(
                f"Missing staged file: {filename}"
            )

        entry = files[filename]

        if source.stat().st_size != entry["size"]:
            raise ValueError(
                f"Staged file size mismatch: {filename}"
            )

        if calculate_sha256(source) != entry["sha256"]:
            raise ValueError(
                f"Staged file checksum mismatch: {filename}"
            )


def copy_with_retry(source, destination):
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = destination.with_name(
        destination.name + ".synapse-update.tmp"
    )

    last_error = None

    for _ in range(FILE_RETRY_COUNT):
        try:
            if temporary.exists():
                if temporary.is_dir():
                    raise ValueError(
                        f"Unexpected directory at temporary path: {temporary}"
                    )

                temporary.unlink()

            shutil.copy2(
                source,
                temporary,
            )

            os.replace(
                temporary,
                destination,
            )

            return

        except OSError as error:
            last_error = error
            time.sleep(RETRY_DELAY_SECONDS)

    try:
        if temporary.exists():
            temporary.unlink()
    except OSError:
        pass

    raise last_error


def remove_file_with_retry(path):
    if path.is_symlink():
        raise ValueError(
            f"Refusing to remove a symbolic link: {path}"
        )

    if not path.exists():
        return

    if not path.is_file():
        raise ValueError(
            f"Refusing to remove a directory as an update file: {path}"
        )

    last_error = None

    for _ in range(FILE_RETRY_COUNT):
        try:
            path.unlink()
            return

        except OSError as error:
            last_error = error
            time.sleep(RETRY_DELAY_SECONDS)

    raise last_error


def verify_installed_files(install_dir, manifest, plan):
    files = manifest["files"]

    for filename in plan["changed_files"]:
        destination = resolve_inside(
            install_dir,
            filename,
        )

        if not destination.is_file():
            raise FileNotFoundError(
                f"Installed file is missing: {filename}"
            )

        expected = files[filename]

        if destination.stat().st_size != expected["size"]:
            raise ValueError(
                f"Installed file size mismatch: {filename}"
            )

        if calculate_sha256(destination) != expected["sha256"]:
            raise ValueError(
                f"Installed file checksum mismatch: {filename}"
            )

    for filename in plan["deleted_files"]:
        destination = resolve_inside(
            install_dir,
            filename,
        )

        if destination.exists():
            raise ValueError(
                f"Deleted file still exists: {filename}"
            )


def write_installed_manifest(install_dir, manifest):
    destination = resolve_inside(
        install_dir,
        "update-manifest.json",
    )

    temporary = resolve_inside(
        install_dir,
        "update-manifest.json.tmp",
    )

    with open(
        temporary,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            manifest,
            file,
            indent=2,
        )

    os.replace(
        temporary,
        destination,
    )


def apply_update(install_dir, staging):
    install_dir = Path(install_dir).resolve()
    staging = Path(staging).resolve()

    expected_staging = get_staging_directory().resolve()

    if staging != expected_staging:
        raise ValueError(
            "The staged update is not in the expected Synapse data directory."
        )

    manifest_path = staging / "update-manifest.json"
    plan_path = staging / "plan.json"

    if not manifest_path.is_file():
        raise FileNotFoundError(
            "The staged update manifest is missing."
        )

    if not plan_path.is_file():
        raise FileNotFoundError(
            "The staged update plan is missing."
        )

    manifest = load_json(manifest_path)
    plan = load_json(plan_path)

    validate_manifest(
        manifest,
        plan,
    )

    verify_payload(
        staging,
        manifest,
        plan,
    )

    payload = staging / "payload"
    backup = staging / "rollback"

    backup.mkdir(
        parents=True,
        exist_ok=True,
    )

    affected_files = list(dict.fromkeys(
        plan["changed_files"]
        + plan["deleted_files"]
        + ["update-manifest.json"]
    ))

    backed_up = set()

    try:
        # Back up every existing file before modifying anything.
        for filename in affected_files:
            destination = resolve_inside(
                install_dir,
                filename,
            )

            if destination.exists():
                if not destination.is_file():
                    raise ValueError(
                        f"Expected a file, found a directory: {filename}"
                    )

                backup_path = resolve_inside(
                    backup,
                    filename,
                )

                backup_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                shutil.copy2(
                    destination,
                    backup_path,
                )

                backed_up.add(filename)

        # Install changed files, including Synapse.exe if needed.
        for filename in plan["changed_files"]:
            source = resolve_inside(
                payload,
                filename,
            )

            destination = resolve_inside(
                install_dir,
                filename,
            )

            copy_with_retry(
                source,
                destination,
            )

        # Remove files explicitly listed as obsolete.
        for filename in plan["deleted_files"]:
            destination = resolve_inside(
                install_dir,
                filename,
            )

            remove_file_with_retry(destination)

        # Verify all installed and deleted files.
        verify_installed_files(
            install_dir,
            manifest,
            plan,
        )

        # The manifest write is part of the transaction.
        write_installed_manifest(
            install_dir,
            manifest,
        )

    except Exception:
        # Restore every affected file that existed beforehand.
        for filename in reversed(affected_files):
            try:
                destination = resolve_inside(
                    install_dir,
                    filename,
                )

                backup_path = resolve_inside(
                    backup,
                    filename,
                )

                if filename in backed_up and backup_path.is_file():
                    copy_with_retry(
                        backup_path,
                        destination,
                    )
                else:
                    remove_file_with_retry(destination)

            except Exception as rollback_error:
                show_message(
                    "Synapse Update - Rollback Warning",
                    (
                        f"Could not restore {filename}:\n\n"
                        f"{rollback_error}"
                    ),
                    error=True,
                )

        temporary_manifest = install_dir / "update-manifest.json.tmp"

        try:
            remove_file_with_retry(temporary_manifest)
        except Exception:
            pass

        raise

    return plan["version"]


def is_administrator():
    try:
        return bool(
            ctypes.windll.shell32.IsUserAnAdmin()
        )
    except Exception:
        return False


def relaunch_as_administrator(args, install_dir):
    executable = Path(sys.executable).resolve()

    parameters = [
        "--pid",
        str(args.pid),
        "--install-dir",
        str(install_dir),
    ]

    if args.restart:
        parameters.append("--restart")

    command_line = subprocess.list2cmdline(parameters)

    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        str(executable),
        command_line,
        str(install_dir),
        1,
    )

    if result <= 32:
        if result == 5:
            raise PermissionError(
                "Administrator permission was denied."
            )

        raise OSError(
            f"Windows could not start the elevated updater (error {result})."
        )


def restart_application(install_dir):
    executable = install_dir / APP_EXE

    if not executable.is_file():
        raise FileNotFoundError(
            "Synapse.exe could not be found after updating."
        )

    subprocess.Popen(
        [str(executable)],
        cwd=str(install_dir),
        close_fds=True,
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--pid",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--install-dir",
        type=str,
        required=True,
    )

    parser.add_argument(
        "--restart",
        action="store_true",
    )

    args = parser.parse_args()

    if os.name != "nt":
        raise RuntimeError(
            "The Synapse updater helper currently supports Windows only."
        )

    if args.pid <= 0:
        raise ValueError("Invalid process ID.")

    install_dir = Path(
        args.install_dir
    ).resolve()

    # Only permit the expected Synapse installation directory.
    if install_dir.name.casefold() != APP_NAME.casefold():
        raise ValueError(
            "The supplied directory is not a Synapse installation directory."
        )

    if not install_dir.is_dir():
        raise FileNotFoundError(
            "The Synapse installation directory could not be found."
        )

    if not (install_dir / APP_EXE).is_file():
        raise FileNotFoundError(
            "Synapse.exe could not be found in the installation directory."
        )

    staging = get_staging_directory()

    if not staging.is_dir():
        raise FileNotFoundError(
            "No staged update was found."
        )

    # Request UAC elevation before attempting to modify Program Files.
    if not is_administrator():
        relaunch_as_administrator(
            args,
            install_dir,
        )
        return

    # Wait silently for Synapse to exit before touching installed files.
    wait_for_process(args.pid)

    version = apply_update(
        install_dir,
        staging,
    )

    # Remove only the dedicated updater staging directory.
    shutil.rmtree(staging)

    if args.restart:
        restart_application(install_dir)

    else:
        show_message(
            "Synapse Updated",
            f"Synapse was successfully updated to version {version}.",
        )


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        show_message(
            "Synapse Update Failed",
            str(error),
            error=True,
        )
        sys.exit(1)
