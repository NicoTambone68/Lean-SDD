"""Conservative installation: preflight every file and never overwrite one."""

from dataclasses import dataclass
from pathlib import Path

from lean_sdd.configuration import (
    CONFIGURATION_NAME,
    Configuration,
    InstallationIdentity,
    default_configuration_bytes,
    resolve_configuration,
)
from lean_sdd.profiles import BUILTIN_PROFILES, ProfileRegistry
from lean_sdd.templates import (
    STATE_PATH,
    InstallationRecord,
    package_version,
    parse_installation_state,
    profile_installation_state,
    resolve_bundle,
    template_files,
    template_manifest,
)


class InstallError(Exception):
    """A target cannot be initialized without risking existing content."""


@dataclass(frozen=True)
class InstallResult:
    """Report the planned or completed changes relative to the target."""

    created: tuple[str, ...]
    unchanged: tuple[str, ...]
    preserved: tuple[str, ...]
    profiles: tuple[str, ...]
    configuration: Configuration


def check_path(path: Path, *, directory: bool = False) -> None:
    """Reject symlinks and non-directory ancestors before accessing a target."""
    for parent in reversed(path.parents):
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise InstallError(f"Unsafe parent directory: {parent}")
    if path.is_symlink():
        raise InstallError(f"Refusing symbolic link: {path}")
    if path.exists() and (not path.is_dir() if directory else not path.is_file()):
        raise InstallError(f"Unexpected file type: {path}")


def _matches(path: Path, content: bytes) -> bool:
    return path.stat().st_size == len(content) and path.read_bytes() == content


def _make_directories(path: Path, created: list[Path]) -> None:
    missing = []
    while not path.exists():
        missing.append(path)
        path = path.parent
    for directory in reversed(missing):
        directory.mkdir()
        created.append(directory)


def _read_record(target: Path) -> tuple[InstallationRecord, bytes] | None:
    path = target / STATE_PATH
    check_path(path)
    if not path.exists():
        return None
    with path.open("rb") as stream:
        content = stream.read(1_000_001)
    if len(content) > 1_000_000:
        raise InstallError("Installation record is too large.")
    try:
        return parse_installation_state(content.decode("utf-8")), content
    except UnicodeError as error:
        raise InstallError("Installation record is not valid UTF-8 JSON.") from error
    except ValueError as error:
        raise InstallError(f"Invalid installation record: {error}") from error


def _existing_payload(
    record: InstallationRecord, registry: ProfileRegistry
) -> dict[str, bytes]:
    """Require the exact original release before repairing any missing asset."""
    payload = (
        template_files()
        if record.schema_version == 1
        else dict(resolve_bundle(record.identity.profiles, registry=registry).payload)
    )
    expected = template_manifest(payload)
    # Configuration is mutable project data. Its original hash remains evidence,
    # never a recipe for reconstructing or rewriting the user's current mapping.
    if record.schema_version == 2 and CONFIGURATION_NAME in record.files:
        expected[CONFIGURATION_NAME] = record.files[CONFIGURATION_NAME]
    if record.template_version != package_version() or record.files != expected:
        raise InstallError(
            f"Conflicting {STATE_PATH}; the installed release or manifest differs. "
            "Review differences in a separate empty directory; "
            "no migration is performed."
        )
    return payload


def initialize(
    target: Path,
    *,
    dry_run: bool = False,
    language: str | None = None,
    registry: ProfileRegistry = BUILTIN_PROFILES,
) -> InstallResult:
    """Resolve profiles and install missing files after complete read-only preflight.

    Fresh installs use composed assets and schema 2, generating a root Python
    configuration only when no user file exists. Existing records, configuration,
    and identical assets are never rewritten; schema 1 uses its legacy bundle.
    On failure remove only files/directories created by this invocation. The
    target must not be concurrently modified while initialization is running.
    """
    target = target.expanduser().absolute()
    check_path(target, directory=True)
    existing = _read_record(target)
    resolved = resolve_configuration(
        target,
        installed=existing[0].identity if existing else None,
        language=language,
        registry=registry,
    )
    preserved = (CONFIGURATION_NAME,) if resolved.origin == "explicit" else ()
    if existing:
        record, content = existing
        profiles = record.identity.profiles
        payload = _existing_payload(record, registry)
        payload[STATE_PATH] = content
    else:
        bundle = resolve_bundle(resolved.configuration.profiles, registry=registry)
        profiles = bundle.profiles
        payload = dict(bundle.payload)
        if not preserved:
            payload[CONFIGURATION_NAME] = default_configuration_bytes(
                profiles[0], registry=registry
            )
        payload[STATE_PATH] = profile_installation_state(
            payload,
            template_version=bundle.template_version,
            identity=InstallationIdentity(profiles, "configured"),
        )
    missing: list[str] = []
    unchanged: list[str] = []
    conflicts: list[str] = []
    for name, content in payload.items():
        destination = target / name
        check_path(destination)
        if destination.exists():
            if _matches(destination, content):
                unchanged.append(name)
            else:
                conflicts.append(name)
        else:
            missing.append(name)
    if conflicts:
        raise InstallError(
            "Conflicting files; nothing was written:\n  "
            + "\n  ".join(conflicts)
            + "\nReview differences using a separate empty directory. "
            "Existing rules and installation versions are never overwritten."
        )
    if not dry_run:
        written: list[Path] = []
        directories: list[Path] = []
        try:
            for name in missing:
                destination = target / name
                check_path(destination)
                _make_directories(destination.parent, directories)
                with destination.open("xb") as stream:
                    written.append(destination)
                    stream.write(payload[name])
                if destination.suffix == ".sh":
                    destination.chmod(0o755)
        except (OSError, InstallError) as error:
            cleanup_failures: list[str] = []
            for path in reversed(written):
                try:
                    path.unlink()
                except OSError:
                    cleanup_failures.append(str(path))
            for path in reversed(directories):
                try:
                    path.rmdir()
                except OSError:
                    cleanup_failures.append(str(path))
            detail = (
                " Review leftover paths: " + ", ".join(cleanup_failures)
                if cleanup_failures
                else " Newly created files were removed."
            )
            raise InstallError(f"Installation failed: {error}.{detail}") from error
    return InstallResult(
        tuple(missing), tuple(unchanged), preserved, profiles, resolved.configuration
    )
