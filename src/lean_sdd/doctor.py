"""Local diagnostics only: do not load credentials or invoke project scripts."""

import hashlib
import os
import shutil
import stat
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from lean_sdd.configuration import (
    CONFIGURATION_NAME,
    Component,
    ConfigurationError,
    resolve_configuration,
    validate_directories,
)
from lean_sdd.installer import InstallError, check_path
from lean_sdd.profiles import BUILTIN_PROFILES, ProfileRegistry
from lean_sdd.templates import (
    STATE_PATH,
    InstallationRecord,
    package_version,
    parse_installation_state,
    resolve_bundle,
    template_files,
    template_manifest,
)
from lean_sdd.typescript import inspect_typescript

MAX_METADATA_BYTES = 1024 * 1024


@dataclass(frozen=True)
class Check:
    """A local observation; warnings are not claims of workflow readiness."""

    status: Literal["PASS", "WARN", "FAIL"]
    message: str


def _run(arguments: list[str], target: Path) -> subprocess.CompletedProcess[str]:
    executable = shutil.which(arguments[0])
    if executable is None:
        raise OSError("Shared observation tool is unavailable.")
    program = Path(executable).resolve(strict=True)
    if program.is_relative_to(target.resolve()):
        raise OSError("Refusing a shared observation tool inside the project.")
    environment = os.environ.copy()
    # Noninteractive Bash can otherwise execute arbitrary startup commands.
    environment.pop("BASH_ENV", None)
    environment.pop("ENV", None)
    # Fixed observations must not inherit exported shell functions, Git tracing
    # destinations, or Git environment overrides that redirect the inspected root.
    for name in tuple(environment):
        if name.startswith(("BASH_FUNC_", "GIT_")):
            environment.pop(name)
    return subprocess.run(
        [str(program), *arguments[1:]],
        cwd=target,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def _regular_file_exists(path: Path) -> bool:
    """Distinguish absence from inaccessible metadata, rejecting links/special files."""
    check_path(path)
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(mode):
        raise InstallError("Expected a regular file.")
    return True


def _read_installation(target: Path) -> tuple[InstallationRecord | None, list[Check]]:
    state_path = target / STATE_PATH
    try:
        if not _regular_file_exists(state_path):
            return None, [
                Check("FAIL", "Installation record missing; run lean-sdd init.")
            ]
        with state_path.open("rb") as stream:
            content = stream.read(1_000_001)
        if len(content) > 1_000_000:
            return None, [Check("FAIL", "Installation record is too large.")]
        record = parse_installation_state(content.decode("utf-8"))
    except InstallError:
        return None, [Check("FAIL", "Unsafe installation record path.")]
    except UnicodeError:
        return None, [Check("FAIL", "Installation record is not valid UTF-8 JSON.")]
    except ValueError as error:
        return None, [Check("FAIL", f"Invalid installation record: {error}")]
    except OSError:
        return None, [
            Check("FAIL", "Cannot read installation record; check file access.")
        ]
    return record, [
        Check(
            "PASS",
            f"Installation record is valid (schema {record.schema_version}); "
            f"installed profiles: {', '.join(record.identity.profiles)}.",
        )
    ]


def _release_checks(
    record: InstallationRecord, registry: ProfileRegistry
) -> list[Check]:
    try:
        for profile in record.identity.profiles:
            registry.get(profile)
        payload = (
            template_files()
            if record.schema_version == 1
            else resolve_bundle(record.identity.profiles, registry=registry).payload
        )
        manifest = template_manifest(payload)
        if record.schema_version == 2 and CONFIGURATION_NAME in record.files:
            # Current configuration may have been customized. Its historical hash
            # is checked against disk below, not recomputed from current defaults.
            manifest[CONFIGURATION_NAME] = record.files[CONFIGURATION_NAME]
        checks = _compatibility_checks(record, manifest, package_version())
    except ValueError as error:
        checks = [Check("FAIL", f"Installed profile bundle unavailable: {error}")]
    return checks


def _component_checks(
    target: Path, record: InstallationRecord, registry: ProfileRegistry
) -> list[Check]:
    try:
        resolved = resolve_configuration(
            target, installed=record.identity, registry=registry
        )
        validate_directories(resolved.configuration, target, require_exists=True)
    except ConfigurationError as error:
        return [
            Check("FAIL", f"Installed configuration: {error}"),
            Check(
                "WARN",
                "Component profile diagnostics unavailable "
                "until configuration is valid.",
            ),
        ]
    checks = [
        Check(
            "PASS",
            "Installed profile configuration is valid; commands not executed. "
            f"Mapping origin: {resolved.origin}.",
        )
    ]
    for component in resolved.configuration.components:
        for profile_id in component.profiles:
            context = (
                f"Component {component.id} ({component.path}), profile {profile_id}"
            )
            if registry.get(profile_id).diagnostic == "python":
                observations = _python_checks(target, component)
            elif registry.get(profile_id).diagnostic == "typescript":
                observations = [
                    Check(item.status, item.message)
                    for item in inspect_typescript(
                        target, component, resolved.configuration.checks
                    )
                ]
            else:
                observations = [
                    Check(
                        "WARN",
                        "Application diagnostics unavailable for this profile; "
                        "readiness has not been established.",
                    )
                ]
            checks.extend(
                Check(check.status, f"{context}: {check.message}")
                for check in observations
            )
    return checks


def _compatibility_checks(
    record: InstallationRecord, current: dict[str, str], current_version: str
) -> list[Check]:
    versions = (
        f"Recorded template version {record.template_version!r}; "
        f"current CLI version {current_version!r}."
    )
    same_version = record.template_version == current_version
    if record.files == current:
        if same_version:
            return [
                Check(
                    "PASS", f"Installation record matches current release. {versions}"
                )
            ]
        return [
            Check(
                "WARN",
                f"{versions} Template contents are compatible; no upgrade required.",
            )
        ]
    status: Literal["FAIL", "WARN"] = "FAIL" if same_version else "WARN"
    message = (
        "Installation record contradicts the current release's template manifest."
        if same_version
        else "Installation was created with another template release. "
        "Upgrade advisory: review bundle differences; no templates were changed."
    )
    checks = [Check(status, f"{message} {versions}")]
    differences = (
        ("Templates added in current release", current.keys() - record.files.keys()),
        ("Templates removed in current release", record.files.keys() - current.keys()),
        (
            "Template reference hashes changed",
            {
                name
                for name in current.keys() & record.files.keys()
                if current[name] != record.files[name]
            },
        ),
    )
    for label, names in differences:
        if names:
            checks.append(
                Check(status, f"{label}: {', '.join(map(repr, sorted(names)))}")
            )
    return checks


def _installed_file_checks(target: Path, record: InstallationRecord) -> list[Check]:
    checks: list[Check] = []
    for name, expected_hash in sorted(record.files.items()):
        path = target / name
        try:
            if not _regular_file_exists(path):
                checks.append(Check("FAIL", f"Missing installed template: {name!r}"))
                continue
            with path.open("rb") as stream:
                actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        except InstallError:
            checks.append(Check("FAIL", f"Unsafe installed path: {name!r}"))
            continue
        except OSError:
            checks.append(
                Check(
                    "FAIL",
                    f"Cannot read installed template: {name!r}; check file access.",
                )
            )
            continue
        checks.append(
            Check("PASS", f"Installed template matches recorded hash: {name!r}")
            if actual_hash == expected_hash
            else Check("WARN", f"Locally modified template: {name!r}")
        )
    if all(check.status == "PASS" for check in checks):
        checks.append(
            Check("PASS", "All recorded templates match their original content.")
        )
    return checks


def _shared_checks(target: Path) -> list[Check]:
    """Observe workflow prerequisites independently of application profiles."""
    checks: list[Check] = []
    commands = ("bash", "git", "curl", "jq", "awk", "grep", "mktemp", "uv")
    for command in commands:
        checks.append(
            Check("PASS", f"{command} is available.")
            if shutil.which(command)
            else Check("FAIL", f"Required command missing: {command}")
        )
    if shutil.which("bash"):
        try:
            bash = _run(
                [
                    "bash",
                    "--noprofile",
                    "--norc",
                    "-p",
                    "-c",
                    'printf "%s" "$BASH_VERSION"',
                ],
                target,
            )
        except (OSError, UnicodeError, subprocess.TimeoutExpired):
            checks.append(
                Check(
                    "FAIL",
                    "Cannot inspect Bash version; use an accessible system Bash "
                    "outside the project (10-second timeout).",
                )
            )
        else:
            major = bash.stdout.partition(".")[0]
            checks.append(
                Check("PASS", "Bash 4 or newer is available.")
                if bash.returncode == 0 and major.isdigit() and int(major) >= 4
                else Check("FAIL", "Workflow scripts require Bash 4 or newer.")
            )
    endpoint = os.environ.get("GITHUB_MCP_URL", "")
    if not endpoint:
        checks.append(Check("WARN", "GITHUB_MCP_URL is not exported."))
    elif endpoint.rstrip("/") != "https://api.githubcopilot.com/mcp":
        checks.append(
            Check("FAIL", "GITHUB_MCP_URL is not the supported official endpoint.")
        )
    else:
        checks.append(Check("PASS", "Official GitHub MCP endpoint configured."))
    token = os.environ.get("GITHUB_TOKEN", "")
    checks.append(
        Check("PASS", "GITHUB_TOKEN is exported; validity and permissions not checked.")
        if token
        else Check("WARN", "GITHUB_TOKEN is not exported; .env files are not loaded.")
    )
    if shutil.which("git"):
        try:
            git = _run(["git", "rev-parse", "--show-toplevel"], target)
        except (OSError, UnicodeError, subprocess.TimeoutExpired):
            checks.append(
                Check(
                    "FAIL",
                    "Cannot inspect Git worktree; use an accessible system Git "
                    "outside the project (10-second timeout).",
                )
            )
        else:
            if git.returncode or Path(git.stdout.strip()).resolve() != target.resolve():
                checks.append(Check("WARN", "Target is not a Git worktree root."))
            else:
                checks.append(Check("PASS", "Target is a Git worktree root."))
    return checks


def _python_checks(target: Path, component: Component) -> list[Check]:
    """Inspect bounded Python metadata at a validated, existing component root."""
    root = target / component.path
    checks: list[Check] = []
    project = root / "pyproject.toml"
    try:
        if not _regular_file_exists(project):
            checks.append(
                Check(
                    "WARN", "No pyproject.toml; prepare the Python project separately."
                )
            )
        else:
            with project.open("rb") as stream:
                content = stream.read(MAX_METADATA_BYTES + 1)
            if len(content) > MAX_METADATA_BYTES:
                checks.append(Check("FAIL", "pyproject.toml exceeds the 1 MiB limit."))
            else:
                metadata = tomllib.loads(content.decode("utf-8"))
                if isinstance(metadata.get("project"), dict):
                    checks.append(Check("PASS", "Python project metadata is present."))
                elif "project" in metadata:
                    checks.append(
                        Check("FAIL", "pyproject.toml [project] must be a table.")
                    )
                else:
                    checks.append(
                        Check("WARN", "pyproject.toml has no [project] metadata.")
                    )
    except InstallError:
        checks.append(Check("FAIL", "Unsafe pyproject.toml path; use a regular file."))
    except UnicodeError:
        checks.append(Check("FAIL", "pyproject.toml is not valid UTF-8."))
    except (ValueError, RecursionError):
        checks.append(Check("FAIL", "pyproject.toml is invalid TOML."))
    except OSError:
        checks.append(Check("FAIL", "Cannot read pyproject.toml; check file access."))
    lock = root / "uv.lock"
    try:
        checks.append(
            Check("PASS", "uv.lock is present; freshness not checked.")
            if _regular_file_exists(lock)
            else Check(
                "WARN", "No uv.lock; lock the project dependencies before validation."
            )
        )
    except InstallError:
        checks.append(Check("FAIL", "Unsafe uv.lock path; use a regular file."))
    except OSError:
        checks.append(Check("FAIL", "Cannot inspect uv.lock; check file access."))
    return checks


def diagnose(
    target: Path, *, registry: ProfileRegistry = BUILTIN_PROFILES
) -> list[Check]:
    """Inspect installation, shared prerequisites, and selected components locally.

    The explicit in-process registry supports inert fixtures, not project plugins.
    No configuration commands execute, credentials load, or installation writes
    occur. Only fixed Bash-version and Git-root observations may run. The project
    and PATH must not be concurrently modified during inspection.
    """
    target = target.expanduser().absolute()
    check_path(target, directory=True)
    if not target.is_dir() or ".." in target.parts:
        raise InstallError(
            "Doctor requires an existing project directory without traversal."
        )
    record, checks = _read_installation(target)
    if record is not None:
        checks += _installed_file_checks(target, record)
        checks += _release_checks(record, registry)
        checks += _component_checks(target, record, registry)
    else:
        checks.append(
            Check(
                "WARN",
                "Profile selection and component diagnostics unavailable "
                "without a valid installation record.",
            )
        )
    checks += _shared_checks(target)
    return checks
