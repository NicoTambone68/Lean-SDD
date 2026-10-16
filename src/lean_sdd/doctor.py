"""Local diagnostics only: do not load credentials or invoke project scripts."""

import hashlib
import os
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from lean_sdd.installer import InstallError, check_path
from lean_sdd.templates import (
    STATE_PATH,
    InstallationRecord,
    package_version,
    parse_installation_state,
    template_files,
    template_manifest,
)


@dataclass(frozen=True)
class Check:
    """A local observation; warnings are not claims of workflow readiness."""

    status: Literal["PASS", "WARN", "FAIL"]
    message: str


def _run(arguments: list[str], target: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    # Noninteractive Bash can otherwise execute arbitrary startup commands.
    environment.pop("BASH_ENV", None)
    environment.pop("ENV", None)
    return subprocess.run(
        arguments,
        cwd=target,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def _installation_checks(target: Path) -> list[Check]:
    state_path = target / STATE_PATH
    try:
        check_path(state_path)
        if not state_path.is_file():
            return [Check("FAIL", "Installation record missing; run lean-sdd init.")]
        with state_path.open("rb") as stream:
            content = stream.read(1_000_001)
        if len(content) > 1_000_000:
            return [Check("FAIL", "Installation record is too large.")]
        record = parse_installation_state(content.decode("utf-8"))
    except InstallError:
        return [Check("FAIL", "Unsafe installation record path.")]
    except UnicodeError:
        return [Check("FAIL", "Installation record is not valid UTF-8 JSON.")]
    except ValueError as error:
        return [Check("FAIL", f"Invalid installation record: {error}")]
    except OSError:
        return [Check("FAIL", "Cannot read installation record; check file access.")]
    checks = _compatibility_checks(
        record, template_manifest(template_files()), package_version()
    )
    return checks + _installed_file_checks(target, record)


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
            check_path(path)
            if not path.is_file():
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


def diagnose(target: Path) -> list[Check]:
    """Check installed files, prerequisites, and configuration without networking."""
    target = target.expanduser().absolute()
    check_path(target, directory=True)
    if not target.is_dir():
        raise InstallError("Doctor requires an existing project directory.")
    checks = _installation_checks(target)
    commands = ("bash", "git", "curl", "jq", "awk", "grep", "mktemp", "uv")
    for command in commands:
        checks.append(
            Check("PASS", f"{command} is available.")
            if shutil.which(command)
            else Check("FAIL", f"Required command missing: {command}")
        )
    if shutil.which("bash"):
        bash = _run(
            ["bash", "--noprofile", "--norc", "-c", 'printf "%s" "$BASH_VERSION"'],
            target,
        )
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
        git = _run(["git", "rev-parse", "--show-toplevel"], target)
        if git.returncode or Path(git.stdout.strip()).resolve() != target.resolve():
            checks.append(Check("WARN", "Target is not a Git worktree root."))
        else:
            checks.append(Check("PASS", "Target is a Git worktree root."))
    project = target / "pyproject.toml"
    check_path(project)
    if project.is_file():
        try:
            with project.open("rb") as stream:
                config = tomllib.load(stream)
            checks.append(
                Check("PASS", "Python project metadata is present.")
                if isinstance(config.get("project"), dict)
                else Check("WARN", "pyproject.toml has no [project] metadata.")
            )
        except tomllib.TOMLDecodeError:
            checks.append(Check("FAIL", "pyproject.toml is invalid TOML."))
    else:
        checks.append(
            Check("WARN", "No pyproject.toml; prepare the Python project separately.")
        )
    lock = target / "uv.lock"
    check_path(lock)
    checks.append(
        Check("PASS", "uv.lock is present; freshness not checked.")
        if lock.is_file()
        else Check(
            "WARN", "No uv.lock; lock the project dependencies before validation."
        )
    )
    return checks
