"""Integrated installed governance contracts with inert profile additions."""

import hashlib
import re
import subprocess
from importlib.resources import files
from pathlib import Path

import pytest

from lean_sdd.profiles import PYTHON, Profile, ProfileRegistry, RequiredCheck, Resource
from lean_sdd.templates import (
    CORE_SKILLS,
    _common_resources,
    compose_bundle,
    resolve_bundle,
    template_files,
)


@pytest.mark.parametrize("composed", [False, True])
def test_workflow_gates_and_execution_boundary(composed: bool) -> None:
    payload = resolve_bundle().payload if composed else template_files()
    workflow = payload["AGENTS.md"].decode("utf-8")
    # Pinned at the approved pre-integration workflow. Validation integration
    # must not alter the full implementation/publication/merge/failure contracts.
    intake = workflow[
        workflow.index("## 1. Create the issue") : workflow.index("## 3. Validate")
    ]
    completion = workflow[workflow.index("Fix implementation-related failures") :]
    assert hashlib.sha256(intake.encode()).hexdigest() == (
        "83aa3a013f8d43190da4453e7669e67167bdcbb2df874b22b3ece7c6ddfad3e9"
    )
    assert hashlib.sha256(completion.encode()).hexdigest() == (
        "4311774aee4b252c4f55bfff05c53d3edd3d33a4eb6d874d41add5eb03dee344"
    )
    assert "every\nprofile relevant to the change" in workflow
    assert "lean-sdd validate ." in workflow
    assert "full configured required suite across all components" in workflow
    assert "Review the current mapping, every command argument list" in workflow
    assert "Optional failures remain visible" in workflow
    assert "legacy Python\ninstallations" in workflow
    for command in (
        "uv run pytest",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run mypy .",
    ):
        assert command in workflow
    setup = payload[".agents/README.md"].decode("utf-8")
    assert "--no-project --env-file" in setup
    assert "Do not use the GitHub `.env` loader for application validation" in setup
    assert "Native Windows and macOS validation are unsupported" in setup
    assert "never updates project templates automatically" in setup
    assert "explicit authorization for a live run in a disposable project" in setup


@pytest.mark.parametrize("selected", [("fixture",), ("fixture", "python")])
def test_inert_profile_bundle_contract(
    tmp_path: Path, selected: tuple[str, ...]
) -> None:
    """Extra skills and fixture-only bundles keep every core contract/link/script."""
    fixture = Profile(
        "fixture",
        "Inert acceptance fixture",
        (RequiredCheck("tests"),),
        resources=(
            Resource("standards.md", ".agents/standards/fixture.md"),
            Resource("SKILL.md", ".agents/skills/fixture-check/SKILL.md"),
            Resource("check.sh", ".agents/skills/fixture-check/scripts/check.sh"),
        ),
        skills=("fixture-check",),
    )
    common = _common_resources(files("lean_sdd_templates"))
    python = {PYTHON.standards_path: resolve_bundle().payload[PYTHON.standards_path]}
    additions = {
        ".agents/standards/fixture.md": (
            b"# Inert rules\nRead [shared](../../CODING_STANDARDS.md).\n"
        ),
        ".agents/skills/fixture-check/SKILL.md": (
            b"# Inert skill\nRead [workflow](../../../AGENTS.md).\n"
        ),
        ".agents/skills/fixture-check/scripts/check.sh": (
            b"#!/usr/bin/env bash\nexit 0\n"
        ),
    }
    contributions = {"fixture": additions}
    if "python" in selected:
        contributions["python"] = python
    bundle = compose_bundle(
        common,
        contributions,
        template_version="fixture-only",
        registry=ProfileRegistry((PYTHON, fixture)),
    )
    assert bundle.profiles == selected
    assert {
        name.split("/")[2] for name in bundle.payload if name.endswith("/SKILL.md")
    } == CORE_SKILLS | {"fixture-check"}
    for name, content in common.items():
        if name != "CODING_STANDARDS.md":
            assert bundle.payload[name] == content
    # Composition checks every relative link. Parse every script without running
    # a skill, a check, credentials, or any live GitHub operation.
    for name, content in bundle.payload.items():
        if name.endswith(".sh"):
            script = tmp_path / "parse-only.sh"
            script.write_bytes(content)
            result = subprocess.run(
                ["bash", "-n", str(script)],
                capture_output=True,
                timeout=10,
                check=False,
            )
            assert result.returncode == 0, name
    references = re.findall(
        rb"\]\((\.agents/standards/[^)]+)\)", bundle.payload["CODING_STANDARDS.md"]
    )
    assert references == [
        f".agents/standards/{profile}.md".encode() for profile in selected
    ]
