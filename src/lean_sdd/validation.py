"""Plan explicit reviewed validation; imports and planning never execute commands."""

import os
import shutil
import signal
import stat
import sys
import threading
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from lean_sdd.configuration import (
    Check,
    Configuration,
    ConfigurationError,
    resolve_configuration,
    validate_directories,
)
from lean_sdd.installer import InstallError, check_path
from lean_sdd.profiles import BUILTIN_PROFILES, Profile, ProfileRegistry
from lean_sdd.templates import STATE_PATH, parse_installation_state
from lean_sdd.typescript import inspect_typescript

MAX_METADATA_BYTES = 1024 * 1024
Status = Literal[
    "passed",
    "failed",
    "missing-executable",
    "timed-out",
    "cancelled",
    "not-run",
    "error",
]


@dataclass(frozen=True)
class PlannedCheck:
    """One validated command with its absolute working directory and executable."""

    check: Check = field(repr=False)
    directory: Path
    executable: str | None


@dataclass(frozen=True)
class ValidationPlan:
    """Immutable execution snapshot returned by prepare_validation.

    Environment values are retained for execution only and must never be logged.
    Problems block all execution, including otherwise runnable optional checks.
    """

    root: Path
    configuration: Configuration = field(repr=False)
    checks: tuple[PlannedCheck, ...]
    environment: Mapping[str, str] = field(repr=False)
    problems: tuple[str, ...]
    standards_profiles: tuple[Profile, ...] = ()


@dataclass(frozen=True)
class CheckResult:
    """A command outcome; returncode is absent without a naturally observed exit."""

    check: Check = field(repr=False)
    status: Status
    returncode: int | None = None
    detail: str = ""


@dataclass(frozen=True)
class ValidationResult:
    """Required success, infrastructure failure and interruption remain distinct."""

    checks: tuple[CheckResult, ...]
    problems: tuple[str, ...] = ()
    cancellation_signal: int | None = None

    @property
    def exit_code(self) -> int:
        """Return 0/1, or 128 plus the signal that cancelled this invocation."""
        if self.cancellation_signal is not None:
            return 128 + self.cancellation_signal
        return int(
            bool(self.problems)
            or any(
                result.check.required and result.status != "passed"
                for result in self.checks
            )
        )


def _regular_file(path: Path, label: str) -> None:
    try:
        check_path(path)
        if not stat.S_ISREG(path.lstat().st_mode):
            raise InstallError("Not a regular file.")
    except (OSError, InstallError) as error:
        raise ConfigurationError(
            f"{label}: required regular file is missing, unsafe or inaccessible."
        ) from error


def _python_preconditions(config: Configuration, root: Path) -> None:
    for component in config.components:
        if "python" not in component.profiles:
            continue
        context = f"Component {component.id} ({component.path}), Python"
        project = root / component.path / "pyproject.toml"
        _regular_file(project, f"{context} pyproject.toml")
        try:
            with project.open("rb") as stream:
                content = stream.read(MAX_METADATA_BYTES + 1)
            if len(content) > MAX_METADATA_BYTES:
                raise ConfigurationError(f"{context}: pyproject.toml exceeds 1 MiB.")
            metadata = tomllib.loads(content.decode("utf-8"))
        except (OSError, ValueError, RecursionError) as error:
            raise ConfigurationError(
                f"{context}: cannot read valid bounded UTF-8 pyproject.toml."
            ) from error
        if not isinstance(metadata.get("project"), dict):
            raise ConfigurationError(
                f"{context}: pyproject.toml requires a [project] table."
            )
        _regular_file(root / component.path / "uv.lock", f"{context} uv.lock")


def _check_profile_standards(root: Path, profiles: tuple[Profile, ...]) -> None:
    for profile in profiles:
        path = root / profile.standards_path
        label = f"Profile {profile.id} standards {profile.standards_path}"
        _regular_file(path, label)
        try:
            with path.open("rb", buffering=0) as stream:
                stream.read(1)
        except OSError as error:
            raise ConfigurationError(f"{label}: cannot read installed file.") from error


def _typescript_preconditions(config: Configuration, root: Path) -> None:
    for component in config.components:
        if "typescript" not in component.profiles:
            continue
        for observation in inspect_typescript(root, component, config.checks):
            if observation.status != "PASS":
                raise ConfigurationError(
                    f"Component {component.id} ({component.path}), "
                    f"TypeScript: {observation.message}"
                )


def check_execution_boundaries(plan: ValidationPlan) -> None:
    """Recheck platform, directories and selected profile metadata before launch."""
    if (
        sys.platform != "linux"
        or threading.current_thread() is not threading.main_thread()
    ):
        raise ConfigurationError(
            "Validation execution requires Linux and the main thread."
        )
    validate_directories(plan.configuration, plan.root, require_exists=True)
    _check_profile_standards(plan.root, plan.standards_profiles)
    _python_preconditions(plan.configuration, plan.root)
    _typescript_preconditions(plan.configuration, plan.root)


def _executable(
    command: str, directory: Path, environment: Mapping[str, str]
) -> str | None:
    # Resolve relative executable paths and PATH entries against the check cwd,
    # never against the directory from which the CLI happened to be invoked.
    if "/" in command:
        candidate = Path(command)
        return shutil.which(
            str(candidate if candidate.is_absolute() else directory / candidate)
        )
    search = os.pathsep.join(
        str(Path(entry) if Path(entry).is_absolute() else directory / entry)
        for entry in environment.get("PATH", os.defpath).split(os.pathsep)
    )
    return shutil.which(command, path=search)


def prepare_validation(
    target: Path,
    *,
    registry: ProfileRegistry = BUILTIN_PROFILES,
    environment: Mapping[str, str] | None = None,
) -> ValidationPlan:
    """Read and validate the complete plan without launching any process.

    Raises ConfigurationError when no trustworthy plan can be resolved. Once
    configuration is resolved, preparation problems are returned with every
    check so execution can report missing executables and not-run outcomes.
    Only Linux main-thread execution is supported. No installation is created,
    upgraded or hashed against the current release; reviewed local rules remain
    user-owned, and historical identity must still name available profiles.
    """
    root = target.expanduser().absolute()
    path = root / STATE_PATH
    _regular_file(path, "Installation record")
    try:
        with path.open("rb") as stream:
            content = stream.read(1_000_001)
        if len(content) > 1_000_000:
            raise ConfigurationError("Installation record exceeds its size limit.")
        installed = parse_installation_state(content.decode("utf-8"))
    except (OSError, ValueError) as error:
        raise ConfigurationError(
            "Cannot read a valid supported installation record."
        ) from error
    resolved = resolve_configuration(
        root, installed=installed.identity, registry=registry
    )
    env = dict(os.environ if environment is None else environment)
    if any("\0" in key or "=" in key or "\0" in value for key, value in env.items()):
        raise ConfigurationError("Execution environment contains an invalid entry.")
    checks = tuple(
        PlannedCheck(
            check, root / check.cwd, _executable(check.argv[0], root / check.cwd, env)
        )
        for check in resolved.configuration.checks
    )
    problems: list[str] = []
    standards_profiles = (
        tuple(registry.get(name) for name in resolved.configuration.profiles)
        if installed.schema_version == 2
        else ()
    )
    for profile in standards_profiles:
        if profile.standards_path not in installed.files:
            problems.append(
                f"Profile {profile.id} standards {profile.standards_path} "
                "missing from installation record."
            )
    if (
        sys.platform != "linux"
        or threading.current_thread() is not threading.main_thread()
    ):
        problems.append(
            "Validation execution requires Linux and the main thread; "
            "no checks were started."
        )
    try:
        validate_directories(resolved.configuration, root, require_exists=True)
        _check_profile_standards(root, standards_profiles)
        _python_preconditions(resolved.configuration, root)
        _typescript_preconditions(resolved.configuration, root)
    except ConfigurationError as error:
        problems.append(str(error))
    for item in checks:
        if item.executable is None and item.check.required:
            problems.append(
                f"Required executable unavailable for check {item.check.name}; "
                "inspect its argv and PATH."
            )
    return ValidationPlan(
        root,
        resolved.configuration,
        checks,
        MappingProxyType(env),
        tuple(problems),
        standards_profiles,
    )


def validate(target: Path) -> ValidationResult:
    """Explicit execution entry point, never called by init, doctor or imports."""
    # Keep process ownership and signal handling out of the planning module.
    from lean_sdd.validation_runner import run_validation

    try:
        plan = prepare_validation(target)
    except ConfigurationError as error:
        return ValidationResult((), (str(error),))
    except KeyboardInterrupt:
        return ValidationResult((), cancellation_signal=signal.SIGINT)
    return run_validation(plan)
