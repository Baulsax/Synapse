
import hashlib
import json
import os
import re
import shutil
import urllib.request
import zipfile

from pathlib import Path, PurePosixPath

from PySide6.QtCore import QObject, QThread, Signal


GITHUB_API_URL = (
    "https://api.github.com/repos/"
    "Baulsax/Synapse/releases/latest"
)

APP_NAME = "Synapse"
STAGING_DIR_NAME = "update-staging"

REQUEST_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 60

MAX_METADATA_SIZE = 5 * 1024 * 1024
MAX_ARCHIVE_SIZE = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_FILES = 10000
MAX_COMPRESSION_RATIO = 1000

VERSION_PATTERN = re.compile(
    r"^\d+\.\d+\.\d+$"
)

SHA256_PATTERN = re.compile(
    r"^[0-9a-fA-F]{64}$"
)


def get_update_staging_directory():
    local_app_data = os.environ.get("LOCALAPPDATA")

    if local_app_data:
        base = Path(local_app_data)
    else:
        base = Path.home() / "AppData" / "Local"

    return base / APP_NAME / STAGING_DIR_NAME


def parse_version(version):
    """Parse a strict Major.Minor.Patch version."""

    if not isinstance(version, str):
        raise ValueError("Invalid version format.")

    match = VERSION_PATTERN.fullmatch(
        version.strip()
    )

    if not match:
        raise ValueError(
            f"Invalid version number: {version}"
        )

    return tuple(
        int(part)
        for part in match.groups()
    )


def is_newer_version(latest, current):
    return parse_version(latest) > parse_version(current)


def calculate_sha256(path):
    digest = hashlib.sha256()

    with open(path, "rb") as file:
        while True:
            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def safe_relative_path(value):
    """
    Reject paths that could escape the application directory.
    """

    if not isinstance(value, str) or not value:
        raise ValueError("Invalid update file path.")

    normalized = value.replace("\\", "/")

    if normalized.startswith("/"):
        raise ValueError(
            "Absolute update paths are not allowed."
        )

    if ":" in normalized:
        raise ValueError(
            "Drive-qualified paths are not allowed."
        )

    parts = normalized.split("/")

    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(
            "Unsafe update file path."
        )

    path = PurePosixPath(normalized)

    if path.is_absolute():
        raise ValueError(
            "Absolute update paths are not allowed."
        )

    return path


def open_url(url, timeout=REQUEST_TIMEOUT, accept=None):
    if not isinstance(url, str):
        raise ValueError("Invalid URL.")

    if not url.startswith("https://"):
        raise ValueError(
            "Update URLs must use HTTPS."
        )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Synapse-Updater",
            "Accept": accept or "application/octet-stream",
        },
    )

    return urllib.request.urlopen(
        request,
        timeout=timeout,
    )


def validate_sha256(value, description):
    if (
        not isinstance(value, str)
        or not SHA256_PATTERN.fullmatch(value)
    ):
        raise ValueError(
            f"Invalid SHA-256 checksum for {description}."
        )

    return value.lower()


def validate_file_list(files, description):
    if not isinstance(files, list):
        raise ValueError(
            f"Invalid {description} list."
        )

    normalized = []

    for filename in files:
        relative = safe_relative_path(filename)
        normalized.append(relative.as_posix())

    if len(set(normalized)) != len(normalized):
        raise ValueError(
            f"Duplicate entries in {description} list."
        )

    return normalized


def validate_manifest(manifest, version):
    if not isinstance(manifest, dict):
        raise ValueError(
            "Update manifest is invalid."
        )

    if manifest.get("version") != version:
        raise ValueError(
            "Update manifest version mismatch."
        )

    files = manifest.get("files")

    if not isinstance(files, dict):
        raise ValueError(
            "Update manifest has an invalid file list."
        )

    normalized_files = {}

    for filename, entry in files.items():
        relative = safe_relative_path(filename)
        normalized = relative.as_posix()

        if normalized in normalized_files:
            raise ValueError(
                "Update manifest contains duplicate file paths."
            )

        if not isinstance(entry, dict):
            raise ValueError(
                f"Invalid manifest entry: {filename}"
            )

        size = entry.get("size")

        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or size > MAX_ARCHIVE_SIZE
        ):
            raise ValueError(
                f"Invalid file size in manifest: {filename}"
            )

        digest = validate_sha256(
            entry.get("sha256"),
            filename,
        )

        normalized_files[normalized] = {
            "size": size,
            "sha256": digest,
        }

    return normalized_files


def validate_metadata(metadata, version):
    if not isinstance(metadata, dict):
        raise ValueError(
            "Update metadata is invalid."
        )

    if metadata.get("version") != version:
        raise ValueError(
            "Release version does not match its metadata."
        )

    required_fields = (
        "manifest_asset",
        "package_asset",
        "package_size",
        "package_sha256",
        "changed_files",
        "deleted_files",
    )

    for field in required_fields:
        if field not in metadata:
            raise ValueError(
                f"Update metadata is missing {field}."
            )

    for field in ("manifest_asset", "package_asset"):
        value = metadata[field]

        if (
            not isinstance(value, str)
            or not value
            or "/" in value
            or "\\" in value
        ):
            raise ValueError(
                f"Invalid release asset name: {field}"
            )

    package_size = metadata["package_size"]

    if (
        not isinstance(package_size, int)
        or isinstance(package_size, bool)
        or package_size < 0
        or package_size > MAX_ARCHIVE_SIZE
    ):
        raise ValueError(
            "Invalid update package size."
        )

    metadata["package_sha256"] = validate_sha256(
        metadata["package_sha256"],
        "update package",
    )

    metadata["changed_files"] = validate_file_list(
        metadata["changed_files"],
        "changed-files",
    )

    metadata["deleted_files"] = validate_file_list(
        metadata["deleted_files"],
        "deleted-files",
    )

    changed = set(metadata["changed_files"])
    deleted = set(metadata["deleted_files"])

    if changed & deleted:
        raise ValueError(
            "A file cannot be both changed and deleted."
        )

    return metadata


class UpdateWorker(QThread):

    update_available = Signal(dict)
    up_to_date = Signal(str)

    download_progress = Signal(int, int)
    download_finished = Signal(str)

    failed = Signal(str)

    def __init__(
        self,
        operation,
        current_version,
        install_directory=None,
        parent=None,
    ):
        super().__init__(parent)

        self.operation = operation
        self.current_version = current_version

        self.install_directory = (
            Path(install_directory).resolve()
            if install_directory
            else None
        )

        self.release_data = None

    def run(self):
        try:
            if self.operation == "check":
                self._check_for_updates()

            elif self.operation == "download":
                self._download_update()

            else:
                raise ValueError(
                    "Unknown updater operation."
                )

        except Exception as error:
            self.failed.emit(str(error))

    def _read_json_url(self, url):
        with open_url(
            url,
            accept="application/vnd.github+json",
        ) as response:

            raw = response.read(
                MAX_METADATA_SIZE + 1
            )

        if len(raw) > MAX_METADATA_SIZE:
            raise ValueError(
                "Update metadata is unexpectedly large."
            )

        try:
            return json.loads(
                raw.decode("utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError(
                "The update server returned invalid JSON."
            )

    @staticmethod
    def _find_release_asset(release, filename):
        assets = release.get("assets", [])

        if not isinstance(assets, list):
            raise ValueError(
                "GitHub returned an invalid release asset list."
            )

        for asset in assets:
            if (
                isinstance(asset, dict)
                and asset.get("name") == filename
            ):
                url = asset.get("browser_download_url")

                if not isinstance(url, str) or not url.startswith("https://"):
                    raise ValueError(
                        f"Invalid download URL for {filename}."
                    )

                return asset

        raise ValueError(
            f"Release is missing {filename}."
        )

    def _check_for_updates(self):
        release = self._read_json_url(
            GITHUB_API_URL
        )

        if not isinstance(release, dict):
            raise ValueError(
                "GitHub returned invalid release information."
            )

        if release.get("draft") or release.get("prerelease"):
            raise ValueError(
                "The latest GitHub release is not a stable release."
            )

        tag_name = release.get("tag_name", "")

        if not isinstance(tag_name, str):
            raise ValueError(
                "GitHub returned an invalid release version."
            )

        latest_version = (
            tag_name[1:]
            if tag_name.startswith("v")
            else tag_name
        )

        parse_version(latest_version)
        parse_version(self.current_version)

        if not is_newer_version(
            latest_version,
            self.current_version,
        ):
            self.release_data = None

            self.up_to_date.emit(
                self.current_version
            )
            return

        metadata_asset = self._find_release_asset(
            release,
            "update.json",
        )

        metadata = self._read_json_url(
            metadata_asset["browser_download_url"]
        )

        metadata = validate_metadata(
            metadata,
            latest_version,
        )

        manifest_asset = self._find_release_asset(
            release,
            metadata["manifest_asset"],
        )

        package_asset = self._find_release_asset(
            release,
            metadata["package_asset"],
        )

        metadata["manifest_url"] = (
            manifest_asset["browser_download_url"]
        )

        metadata["package_url"] = (
            package_asset["browser_download_url"]
        )

        metadata["release_url"] = release.get(
            "html_url",
            "",
        )

        metadata["release_notes"] = release.get(
            "body",
            "",
        )

        metadata["release_date"] = release.get(
            "published_at",
            "",
        )

        metadata["current_version"] = (
            self.current_version
        )

        self.release_data = metadata

        self.update_available.emit(metadata)

    def _download_to_file(
        self,
        url,
        destination,
        expected_size=None,
        maximum_size=MAX_ARCHIVE_SIZE,
    ):
        destination = Path(destination)

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError(
                "Invalid update download URL."
            )

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Synapse-Updater",
                "Accept": "application/octet-stream",
            },
        )

        downloaded = 0

        with urllib.request.urlopen(
            request,
            timeout=DOWNLOAD_TIMEOUT,
        ) as response:

            response_size = response.headers.get(
                "Content-Length"
            )

            if response_size:
                try:
                    response_size = int(response_size)
                except ValueError:
                    raise ValueError(
                        "The server returned an invalid download size."
                    )

                if response_size < 0 or response_size > maximum_size:
                    raise ValueError(
                        "Download exceeds the allowed size."
                    )

                if (
                    expected_size is not None
                    and response_size != expected_size
                ):
                    raise ValueError(
                        "Download size does not match release metadata."
                    )

            else:
                response_size = 0

            with open(destination, "wb") as output:
                while True:
                    chunk = response.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    downloaded += len(chunk)

                    if downloaded > maximum_size:
                        raise ValueError(
                            "Download exceeds the allowed size."
                        )

                    output.write(chunk)

                    self.download_progress.emit(
                        downloaded,
                        expected_size or response_size,
                    )

        if (
            expected_size is not None
            and downloaded != expected_size
        ):
            raise ValueError(
                "Downloaded file size is incorrect."
            )

        return downloaded

    def _validate_archive(self, archive, changed_files):
        entries = {}
        total_uncompressed = 0

        for entry in archive.infolist():
            if entry.is_dir():
                continue

            if len(entries) >= MAX_ARCHIVE_FILES:
                raise ValueError(
                    "Update archive contains too many files."
                )

            relative = safe_relative_path(
                entry.filename
            )

            normalized = relative.as_posix()

            if normalized in entries:
                raise ValueError(
                    "Update archive contains duplicate paths."
                )

            # Reject symbolic links and other non-regular entries.
            unix_mode = (entry.external_attr >> 16) & 0xFFFF
            file_type = unix_mode & 0o170000

            if file_type not in (0, 0o100000):
                raise ValueError(
                    f"Unsupported file type in update archive: {normalized}"
                )

            if entry.flag_bits & 0x1:
                raise ValueError(
                    "Encrypted update archives are not supported."
                )

            if entry.file_size < 0 or entry.file_size > MAX_ARCHIVE_SIZE:
                raise ValueError(
                    "An update archive file exceeds the allowed size."
                )

            if entry.compress_size > 0:
                ratio = entry.file_size / entry.compress_size

                if ratio > MAX_COMPRESSION_RATIO:
                    raise ValueError(
                        "Update archive has an unsafe compression ratio."
                    )

            total_uncompressed += entry.file_size

            if total_uncompressed > MAX_ARCHIVE_SIZE:
                raise ValueError(
                    "Update archive expands beyond the allowed size."
                )

            entries[normalized] = entry

        expected = set(changed_files)

        if set(entries) != expected:
            raise ValueError(
                "Update archive contents do not match release metadata."
            )

        return entries

    def _extract_and_verify(
        self,
        archive_path,
        payload_directory,
        manifest_files,
        changed_files,
    ):
        payload_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        with zipfile.ZipFile(
            archive_path,
            "r",
        ) as archive:

            entries = self._validate_archive(
                archive,
                changed_files,
            )

            for filename in changed_files:
                relative = safe_relative_path(
                    filename
                )

                entry = entries[filename]

                if filename not in manifest_files:
                    raise ValueError(
                        f"Updated file is missing from manifest: {filename}"
                    )

                expected = manifest_files[filename]

                if entry.file_size != expected["size"]:
                    raise ValueError(
                        f"Archive file size does not match manifest: {filename}"
                    )

                destination = (
                    payload_directory
                    / Path(*relative.parts)
                )

                destination.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                digest = hashlib.sha256()
                extracted_size = 0

                with archive.open(entry, "r") as source:
                    with open(destination, "wb") as output:
                        while True:
                            chunk = source.read(
                                1024 * 1024
                            )

                            if not chunk:
                                break

                            extracted_size += len(chunk)

                            if extracted_size > expected["size"]:
                                raise ValueError(
                                    f"Extracted file exceeds expected size: {filename}"
                                )

                            digest.update(chunk)
                            output.write(chunk)

                if extracted_size != expected["size"]:
                    raise ValueError(
                        f"File size verification failed: {filename}"
                    )

                if digest.hexdigest() != expected["sha256"]:
                    raise ValueError(
                        f"File checksum verification failed: {filename}"
                    )

    def _download_update(self):
        staging = get_update_staging_directory()

        try:
            if not self.release_data:
                self._check_for_updates()

                if not self.release_data:
                    raise ValueError(
                        "There is no update available to download."
                    )

            metadata = self.release_data

            # Remove only the updater's own staging directory.
            if staging.exists():
                shutil.rmtree(staging)

            staging.mkdir(
                parents=True,
                exist_ok=True,
            )

            archive_path = staging / "update.zip"
            manifest_path = staging / "update-manifest.json"

            self._download_to_file(
                metadata["package_url"],
                archive_path,
                expected_size=metadata["package_size"],
                maximum_size=MAX_ARCHIVE_SIZE,
            )

            actual_hash = calculate_sha256(
                archive_path
            )

            if actual_hash != metadata["package_sha256"]:
                raise ValueError(
                    "Update package verification failed."
                )

            manifest = self._read_json_url(
                metadata["manifest_url"]
            )

            manifest_files = validate_manifest(
                manifest,
                metadata["version"],
            )

            changed_files = metadata["changed_files"]
            deleted_files = metadata["deleted_files"]

            # The manifest must describe the exact new file set.
            if set(changed_files) - set(manifest_files):
                raise ValueError(
                    "The update contains files missing from its manifest."
                )

            # Verify that the update plan does not list any path as both
            # changed and deleted.
            if set(changed_files) & set(deleted_files):
                raise ValueError(
                    "The update contains conflicting file operations."
                )

            payload_directory = staging / "payload"

            self._extract_and_verify(
                archive_path,
                payload_directory,
                manifest_files,
                changed_files,
            )

            with open(
                manifest_path,
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    manifest,
                    file,
                    indent=2,
                )

            plan = {
                "version": metadata["version"],
                "changed_files": changed_files,
                "deleted_files": deleted_files,
                "package_sha256": metadata["package_sha256"],
            }

            with open(
                staging / "plan.json",
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    plan,
                    file,
                    indent=2,
                )

            archive_path.unlink()

            self.download_finished.emit(
                str(staging)
            )

        except Exception:
            # Do not leave a partial update that could be mistaken
            # for a completed download.
            if staging.exists():
                try:
                    shutil.rmtree(staging)
                except OSError:
                    pass

            raise


class UpdateManager(QObject):

    update_available = Signal(dict)
    up_to_date = Signal(str)

    download_progress = Signal(int, int)
    download_finished = Signal(str)

    failed = Signal(str)

    def __init__(
        self,
        current_version,
        install_directory=None,
        parent=None,
    ):
        super().__init__(parent)

        parse_version(current_version)

        self.current_version = current_version

        self.install_directory = (
            Path(install_directory).resolve()
            if install_directory
            else None
        )

        self._worker = None
        self._release_data = None

    def _start_worker(self, operation):
        if (
            self._worker is not None
            and self._worker.isRunning()
        ):
            return False

        worker = UpdateWorker(
            operation,
            self.current_version,
            self.install_directory,
            self,
        )

        worker.update_available.connect(
            self._on_update_available
        )

        worker.up_to_date.connect(
            self._on_up_to_date
        )

        worker.download_progress.connect(
            self.download_progress.emit
        )

        worker.download_finished.connect(
            self.download_finished.emit
        )

        worker.failed.connect(
            self.failed.emit
        )

        self._worker = worker
        worker.start()

        return True

    def _on_update_available(self, metadata):
        self._release_data = metadata
        self.update_available.emit(metadata)

    def _on_up_to_date(self, version):
        self._release_data = None
        self.up_to_date.emit(version)

    def check_for_updates(self):
        return self._start_worker("check")

    def download_update(self):
        if not self._release_data:
            self.failed.emit(
                "Check for updates before downloading."
            )
            return False

        if (
            self._worker is not None
            and self._worker.isRunning()
        ):
            return False

        worker = UpdateWorker(
            "download",
            self.current_version,
            self.install_directory,
            self,
        )

        worker.release_data = self._release_data

        worker.download_progress.connect(
            self.download_progress.emit
        )

        worker.download_finished.connect(
            self.download_finished.emit
        )

        worker.failed.connect(
            self.failed.emit
        )

        self._worker = worker
        worker.start()

        return True
