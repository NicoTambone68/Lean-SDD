"""Conservative installation: preflight every file and never overwrite one."""

from dataclasses import dataclass
from pathlib import Path

from lean_sdd.templates import STATE_PATH, installation_state, template_files


class InstallError(Exception):
    """A target cannot be initialized without risking existing content."""


@dataclass(frozen=True)
class InstallResult:
    """Report the planned or completed changes relative to the target."""

    created: tuple[str, ...]
    unchanged: tuple[str, ...]


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


def initialize(target: Path, *, dry_run: bool = False) -> InstallResult:
    """Install missing files, failing before writes on any content conflict.

    Existing identical files are left untouched. On a write failure, remove
    only newly created files and empty directories from this invocation. The
    target must not be concurrently modified while initialization is running.
    """
    target = target.expanduser().absolute()
    check_path(target, directory=True)
    payload = template_files()
    payload[STATE_PATH] = installation_state(payload)
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
    return InstallResult(tuple(missing), tuple(unchanged))
