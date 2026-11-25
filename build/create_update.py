
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
import zipfile

from pathlib import Path, PurePosixPath


# ==========================================
# CONFIGURATION
# ==========================================

REPOSITORY = "Baulsax/Synapse"

PROJECT_ROOT = Path(__file__).resolve().parent.parent

VERSION_FILE = (
    PROJECT_ROOT
    / "Application"
    / "version.txt"
)

APPLICATION_BUILD = (
    PROJECT_ROOT
    / "build"
    / "dist"
    / "Synapse"
)

OUTPUT_DIRECTORY = (
    PROJECT_ROOT
    / "build"
    / "release-output"
)

GITHUB_API = (
    f"https://api.github.com/repos/{REPOSITORY}"
)

MANIFEST_NAME = "manifest.json"
METADATA_NAME = "update.json"

HELPER_EXE = "SynapseUpdater.exe"

MAX_METADATA_SIZE = 10 * 1024 * 1024

WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


# ==========================================
# VERSION
# ==========================================

def parse_version(value):
    match = re.fullmatch(
        r"(\d+)\.(\d+)\.(\d+)",
        value.strip(),
    )

    if not match:
        raise ValueError(
            "Version must use Major.Minor.Patch format, "
            "for example 0.1.1."
        )

    return tuple(
        int(part)
        for part in match.groups()
    )


def load_version():
    if not VERSION_FILE.is_file():
        raise FileNotFoundError(
            "Could not find the application version file:\n"
            f"{VERSION_FILE}"
        )

    version = VERSION_FILE.read_text(
        encoding="utf-8"
    ).strip()

    parse_version(version)

    return version


# ==========================================
# PATH VALIDATION
# ==========================================

def safe_relative_path(value):
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"Invalid application path: {value}"
        )

    normalized = value.replace("\\", "/")

    parts = normalized.split("/")

    if (
        normalized.startswith("/")
        or ":" in normalized
        or any(
            part in ("", ".", "..")
            for part in parts
        )
    ):
        raise ValueError(
            f"Unsafe application path: {value}"
        )

    for part in parts:
        if part.endswith((" ", ".")):
            raise ValueError(
                f"Invalid Windows filename component: {part}"
            )

        if any(ord(character) < 32 for character in part):
            raise ValueError(
                f"Control character in filename: {part}"
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
        raise ValueError(
            f"Absolute paths are not permitted: {value}"
        )

    return relative


def validate_path_collisions(files):
    seen = {}

    for filename in files:
        relative = safe_relative_path(filename)
        normalized = relative.as_posix().casefold()

        if normalized in seen:
            raise ValueError(
                "Windows-incompatible filename collision: "
                f"{seen[normalized]} and {filename}"
            )

        seen[normalized] = filename


# ==========================================
# HASHING
# ==========================================

def calculate_sha256(path):
    digest = hashlib.sha256()

    with open(path, "rb") as file:
        while True:
            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def calculate_file_manifest(directory):
    files = {}

    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(
                f"Symbolic links are not permitted in the build: {path}"
            )

        if not path.is_file():
            continue

        relative = path.relative_to(
            directory
        ).as_posix()

        safe_relative_path(relative)

        # The updater helper is a stable bootstrap component.
        # It is installed and replaced by the full installer only.
        if relative.casefold() == HELPER_EXE.casefold():
            continue

        files[relative] = {
            "size": path.stat().st_size,
            "sha256": calculate_sha256(path),
        }

    if not files:
        raise RuntimeError(
            "The application build directory is empty."
        )

    validate_path_collisions(files)

    return {
        "files": files,
    }


# ==========================================
# GITHUB REQUESTS
# ==========================================

def github_request(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Synapse-Release-Builder",
            "Accept": "application/vnd.github+json",
        },
    )

    return urllib.request.urlopen(
        request,
        timeout=30,
    )


def read_json_url(url):
    with github_request(url) as response:
        data = response.read(
            MAX_METADATA_SIZE + 1
        )

    if len(data) > MAX_METADATA_SIZE:
        raise RuntimeError(
            "GitHub metadata is unexpectedly large."
        )

    return json.loads(
        data.decode("utf-8")
    )


def get_previous_manifest():
    url = f"{GITHUB_API}/releases/latest"

    try:
        release = read_json_url(url)

    except urllib.error.HTTPError as error:
        if error.code == 404:
            print(
                "No previous GitHub release found. "
                "This will be a full update package."
            )
            return None

        raise

    assets = release.get("assets", [])

    manifest_asset = next(
        (
            asset
            for asset in assets
            if asset.get("name") == MANIFEST_NAME
        ),
        None,
    )

    if manifest_asset is None:
        raise RuntimeError(
            "The latest GitHub release does not contain "
            "manifest.json. Cannot safely calculate a "
            "differential update."
        )

    manifest_url = manifest_asset.get(
        "browser_download_url"
    )

    if not manifest_url:
        raise RuntimeError(
            "Previous manifest has no download URL."
        )

    manifest = read_json_url(
        manifest_url
    )

    if not isinstance(manifest, dict):
        raise RuntimeError(
            "Previous release manifest is invalid."
        )

    if not isinstance(manifest.get("files"), dict):
        raise RuntimeError(
            "Previous release manifest has an invalid file list."
        )

    if manifest.get("version"):
        parse_version(manifest["version"])

    validate_path_collisions(
        manifest["files"]
    )

    return manifest


# ==========================================
# VERSION COMPARISON
# ==========================================

def compare_manifests(previous, current):
    current_files = current["files"]

    if previous is None:
        return (
            sorted(current_files.keys()),
            [],
        )

    previous_files = previous.get(
        "files",
        {},
    )

    # Ignore the helper if an older release accidentally
    # included it in its manifest. It must never be removed
    # or replaced by the differential updater.
    previous_files = {
        filename: info
        for filename, info in previous_files.items()
        if filename.casefold() != HELPER_EXE.casefold()
    }

    changed = []
    deleted = []

    for filename, current_info in current_files.items():
        previous_info = previous_files.get(
            filename
        )

        if previous_info != current_info:
            changed.append(filename)

    for filename in previous_files:
        if filename not in current_files:
            deleted.append(filename)

    return (
        sorted(changed),
        sorted(deleted),
    )


# ==========================================
# UPDATE PACKAGE
# ==========================================

def create_update_archive(
    application_directory,
    output_path,
    changed_files,
):
    with zipfile.ZipFile(
        output_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:

        for filename in changed_files:
            relative = safe_relative_path(
                filename
            )

            if relative.as_posix().casefold() == HELPER_EXE.casefold():
                raise ValueError(
                    "The updater helper cannot be included in a "
                    "differential update package."
                )

            source = application_directory.joinpath(
                *relative.parts
            )

            if source.is_symlink():
                raise ValueError(
                    f"Symbolic links are not permitted: {filename}"
                )

            if not source.is_file():
                raise FileNotFoundError(
                    f"Missing application file: {filename}"
                )

            archive.write(
                source,
                arcname=relative.as_posix(),
            )


# ==========================================
# RELEASE METADATA
# ==========================================

def create_release_metadata(
    version,
    package_path,
    changed_files,
    deleted_files,
):
    return {
        "version": version,
        "manifest_asset": MANIFEST_NAME,
        "package_asset": package_path.name,
        "package_size": package_path.stat().st_size,
        "package_sha256": calculate_sha256(
            package_path
        ),
        "changed_files": changed_files,
        "deleted_files": deleted_files,
    }


# ==========================================
# MAIN
# ==========================================

def main():
    version = load_version()
    version_tuple = parse_version(version)

    if not APPLICATION_BUILD.is_dir():
        raise FileNotFoundError(
            "Built Synapse application was not found:\n"
            f"{APPLICATION_BUILD}\n\n"
            "Build the application before creating a release."
        )

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()
    print("==========================================")
    print(" SYNAPSE RELEASE PACKAGER")
    print("==========================================")
    print()

    print(f"Version: {version}")
    print(f"Version source: {VERSION_FILE}")
    print(f"Application: {APPLICATION_BUILD}")
    print()

    # Read the previous release.
    previous = get_previous_manifest()

    if previous is not None:
        previous_version = previous.get("version")

        if previous_version:
            if version_tuple <= parse_version(previous_version):
                raise ValueError(
                    "The new version must be greater than "
                    f"the previous release ({previous_version})."
                )

    # Generate current manifest.
    print("Generating application manifest...")

    manifest = calculate_file_manifest(
        APPLICATION_BUILD
    )

    manifest["version"] = version

    changed_files, deleted_files = compare_manifests(
        previous,
        manifest,
    )

    # Final safety checks before creating any package.
    protected_name = HELPER_EXE.casefold()

    for filename in changed_files + deleted_files:
        if filename.casefold() == protected_name:
            raise RuntimeError(
                "The updater helper cannot be changed or deleted "
                "by a differential update."
            )

    print(
        f"Changed or new files: {len(changed_files)}"
    )

    print(
        f"Removed files: {len(deleted_files)}"
    )

    if not changed_files:
        print(
            "No application files changed. "
            "The package will contain an empty update archive."
        )

    # Create archive.
    package_name = (
        f"Synapse-Update-{version}.zip"
    )

    package_path = (
        OUTPUT_DIRECTORY
        / package_name
    )

    print()
    print("Creating update archive...")

    create_update_archive(
        APPLICATION_BUILD,
        package_path,
        changed_files,
    )

    # Save manifest.
    manifest_path = (
        OUTPUT_DIRECTORY
        / MANIFEST_NAME
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

    # Save update metadata.
    metadata = create_release_metadata(
        version,
        package_path,
        changed_files,
        deleted_files,
    )

    metadata_path = (
        OUTPUT_DIRECTORY
        / METADATA_NAME
    )

    with open(
        metadata_path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            metadata,
            file,
            indent=2,
        )

    print()
    print("==========================================")
    print(" RELEASE PACKAGE CREATED")
    print("==========================================")
    print()

    print(f"Version: {version}")
    print(
        f"Package size: "
        f"{package_path.stat().st_size / (1024 * 1024):.2f} MB"
    )

    print()
    print("Release files:")

    print(f"  {package_path}")
    print(f"  {manifest_path}")
    print(f"  {metadata_path}")

    print()
    print(
        "Upload all three files to a GitHub Release "
        f"tagged v{version}."
    )

    print(
        "Do not rename the assets. The updater expects "
        "these exact filenames."
    )

    print()
    print(
        "Reminder: SynapseUpdater.exe is intentionally excluded "
        "from differential updates. Use the full installer to "
        "replace the updater helper."
    )
    print()


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        print()
        print("RELEASE PACKAGING FAILED")
        print(str(error))
        print()

        sys.exit(1)
