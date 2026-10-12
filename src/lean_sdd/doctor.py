"""Local diagnostics only: do not load credentials or invoke project scripts."""

import json
import os
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from lean_sdd.installer import InstallError, check_path
from lean_sdd.templates import STATE_PATH, installation_state, template_files


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
    payload = template_files()
    expected = json.loads(installation_state(payload))
    state_path = target / STATE_PATH
    check_path(state_path)
    if not state_path.is_file():
        return [Check("FAIL", "Installation record missing; run lean-sdd init.")]
    if state_path.stat().st_size > 1_000_000:
        return [Check("FAIL", "Installation record is too large.")]
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        return [Check("FAIL", "Installation record is not valid JSON.")]
    if state != expected:
        return [
            Check(
                "FAIL",
                "Installation record differs from this installer release. "
                "Use the matching installer or review the record; no upgrade was made.",
            )
        ]
    checks = [Check("PASS", "Installation version and template record match.")]
    for name, content in payload.items():
        path = target / name
        try:
            check_path(path)
        except InstallError:
            checks.append(Check("FAIL", f"Unsafe installed path: {name}"))
            continue
        if not path.is_file():
            checks.append(Check("FAIL", f"Missing installed file: {name}"))
        elif path.stat().st_size != len(content) or path.read_bytes() != content:
            checks.append(Check("WARN", f"Locally modified template: {name}"))
    if len(checks) == 1:
        checks.append(Check("PASS", "All installed templates match this release."))
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
