"""Local diagnostics must be informative without running project code."""

import hashlib
import json
import os
import socket
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO, TextIO

import pytest

from lean_sdd.cli import main
from lean_sdd.configuration import InstallationIdentity
from lean_sdd.doctor import diagnose
from lean_sdd.installer import initialize
from lean_sdd.profiles import PYTHON, Profile, ProfileRegistry, RequiredCheck
from lean_sdd.templates import (
    STATE_PATH,
    ResolvedBundle,
    installation_state,
    package_version,
    profile_installation_state,
    template_files,
)


@pytest.fixture
def local_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep CLI status tests independent of host tools and credential settings."""
    monkeypatch.delenv("GITHUB_MCP_URL", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(
        "lean_sdd.doctor.shutil.which", lambda command: f"/tools/{command}"
    )

    def run(arguments: list[str], target: Path) -> subprocess.CompletedProcess[str]:
        if arguments[0] == "bash":
            return subprocess.CompletedProcess(arguments, 0, "5.0.0", "")
        assert arguments == ["git", "rev-parse", "--show-toplevel"]
        return subprocess.CompletedProcess(arguments, 1, "", "not a Git repository")

    monkeypatch.setattr("lean_sdd.doctor._run", run)


@pytest.fixture
def historical_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Install a real project with a simulated older bundle and version."""
    payload = template_files()
    payload.pop(".agents/.env.example")
    payload[".agents/README.md"] = b"Original setup instructions\n"
    payload[".agents/retired.md"] = b"Retired template\n"
    with monkeypatch.context() as older:
        older.setattr("lean_sdd.templates.package_version", lambda: "0.0.0")
        for name, content in payload.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        (tmp_path / STATE_PATH).write_bytes(installation_state(payload))
    return tmp_path


def test_doctor_reports_missing_installation(tmp_path: Path) -> None:
    checks = diagnose(tmp_path)
    assert any(c.status == "FAIL" and "record missing" in c.message for c in checks)


def test_doctor_detects_modifications_and_missing_files(tmp_path: Path) -> None:
    initialize(tmp_path)
    (tmp_path / "CONSTITUTION.md").write_text("Approved local amendment\n")
    (tmp_path / ".agents/lib/mcp.sh").unlink()
    checks = diagnose(tmp_path)
    assert any(c.status == "WARN" and "CONSTITUTION.md" in c.message for c in checks)
    assert any(c.status == "FAIL" and "mcp.sh" in c.message for c in checks)


def test_doctor_does_not_execute_project_or_load_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    initialize(tmp_path)
    marker = tmp_path / "must-not-exist"
    (tmp_path / ".agents/.env").write_text(f"touch '{marker}'\n")
    startup = tmp_path / "bash-startup"
    startup.write_text(f"touch '{marker}'\n")
    monkeypatch.setenv("BASH_ENV", str(startup))
    monkeypatch.setenv("ENV", str(startup))
    monkeypatch.setenv("GITHUB_TOKEN", "secret-value-must-not-be-printed")
    monkeypatch.setenv("GITHUB_MCP_URL", "https://secret@example.invalid/mcp")
    assert main(["doctor", str(tmp_path)]) == 1
    output = capsys.readouterr()
    assert "secret" not in output.out + output.err
    assert "not the supported official endpoint" in output.out
    assert not marker.exists()


def test_invalid_install_record_is_not_interpreted_as_paths(tmp_path: Path) -> None:
    initialize(tmp_path)
    (tmp_path / STATE_PATH).write_text('{"files": {"../../outside": "value"}}')
    checks = diagnose(tmp_path)
    assert checks[0].status == "FAIL"
    assert "Invalid installation record" in checks[0].message


def test_missing_prerequisites_fail_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize(tmp_path)
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("GITHUB_MCP_URL", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    checks = diagnose(tmp_path)
    assert any(
        c.status == "FAIL" and "command missing: bash" in c.message for c in checks
    )
    assert any(c.status == "WARN" and "GITHUB_TOKEN" in c.message for c in checks)


def test_project_toml_errors_are_reported(tmp_path: Path) -> None:
    initialize(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[broken")
    assert any(c.status == "FAIL" and "TOML" in c.message for c in diagnose(tmp_path))


@pytest.mark.usefixtures("local_tools")
def test_fresh_installation_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    initialize(tmp_path)
    assert main(["doctor", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "PASS: Installation record matches current release" in output
    assert "All recorded templates match their original content" in output
    assert "Locally modified" not in output


@pytest.mark.usefixtures("local_tools")
def test_version_difference_with_identical_templates_is_compatible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with monkeypatch.context() as older:
        older.setattr("lean_sdd.templates.package_version", lambda: "0.0.0")
        initialize(tmp_path)
    assert main(["doctor", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "WARN: Recorded template version '0.0.0'" in output
    assert f"current CLI version {package_version()!r}" in output
    assert "Template contents are compatible; no upgrade required" in output
    assert "Locally modified" not in output


@pytest.mark.usefixtures("local_tools")
def test_old_installation_is_validated_against_its_original_bundle(
    historical_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["doctor", str(historical_project)]) == 0
    output = capsys.readouterr().out
    assert "WARN: Installation was created with another template release" in output
    assert "Upgrade advisory" in output
    assert "Templates added in current release: '.agents/.env.example'" in output
    assert "Templates removed in current release: '.agents/retired.md'" in output
    assert "Template reference hashes changed: '.agents/README.md'" in output
    assert (
        "PASS: Installed template matches recorded hash: '.agents/retired.md'" in output
    )
    assert "All recorded templates match their original content" in output
    assert "Locally modified" not in output
    assert not (historical_project / ".agents/.env.example").exists()


@pytest.mark.usefixtures("local_tools")
def test_modification_to_current_content_still_differs_from_original(
    historical_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    name = ".agents/README.md"
    (historical_project / name).write_bytes(template_files()[name])
    assert main(["doctor", str(historical_project)]) == 0
    output = capsys.readouterr().out
    assert f"WARN: Locally modified template: {name!r}" in output
    assert "All recorded templates match" not in output


@pytest.mark.usefixtures("local_tools")
def test_missing_retired_template_remains_a_failure(
    historical_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (historical_project / ".agents/retired.md").unlink()
    assert main(["doctor", str(historical_project)]) == 1
    assert (
        "FAIL: Missing installed template: '.agents/retired.md'"
        in capsys.readouterr().out
    )


@pytest.mark.usefixtures("local_tools")
def test_previous_release_preserves_customized_retired_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    initialize(tmp_path)
    name = ".agents/retired.md"
    record = tmp_path / STATE_PATH
    state = json.loads(record.read_text(encoding="utf-8"))
    state["template_version"] = "0.3.0"
    state["files"][name] = hashlib.sha256(b"Original instructions\n").hexdigest()
    record.write_text(json.dumps(state), encoding="utf-8")
    (tmp_path / name).write_bytes(b"Local instructions\n")
    before = installation_snapshot(tmp_path)

    assert main(["doctor", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert f"WARN: Templates removed in current release: {name!r}" in output
    assert f"WARN: Locally modified template: {name!r}" in output
    assert main(["init", str(tmp_path)]) == 1
    assert "no migration" in capsys.readouterr().err
    assert installation_snapshot(tmp_path) == before


@pytest.mark.parametrize("difference", ["added", "removed", "changed"])
@pytest.mark.usefixtures("local_tools")
def test_current_version_with_conflicting_manifest_fails(
    tmp_path: Path, difference: str, capsys: pytest.CaptureFixture[str]
) -> None:
    initialize(tmp_path)
    path = tmp_path / STATE_PATH
    state = json.loads(path.read_text(encoding="utf-8"))
    if difference == "added":
        state["files"]["unexpected.md"] = "0" * 64
        expected = "Templates removed in current release: 'unexpected.md'"
    elif difference == "removed":
        del state["files"]["AGENTS.md"]
        expected = "Templates added in current release: 'AGENTS.md'"
    else:
        state["files"]["AGENTS.md"] = "0" * 64
        expected = "Template reference hashes changed: 'AGENTS.md'"
    path.write_text(json.dumps(state), encoding="utf-8")
    assert main(["doctor", str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert "FAIL: Installation record contradicts" in output
    assert f"FAIL: {expected}" in output


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"{", "not valid JSON"),
        (b"\xff", "not valid UTF-8 JSON"),
        (b"x" * 1_000_001, "too large"),
        (b'{"schema_version": 3}', "Unsupported installation record schema_version: 3"),
        (
            json.dumps(
                {
                    "schema_version": 1,
                    "template_version": "old",
                    "files": {"../outside": "a" * 64},
                }
            ).encode("utf-8"),
            "Unsafe installation record path",
        ),
    ],
    ids=[
        "invalid-json",
        "invalid-encoding",
        "oversized",
        "unsupported-schema",
        "unsafe-path",
    ],
)
def test_record_failures_have_specific_diagnostics(
    tmp_path: Path, content: bytes, message: str
) -> None:
    initialize(tmp_path)
    (tmp_path / STATE_PATH).write_bytes(content)
    checks = diagnose(tmp_path)
    assert checks[0].status == "FAIL"
    assert message in checks[0].message
    assert not any("Installed template matches" in check.message for check in checks)


@pytest.mark.parametrize("name", ["AGENTS.md", ".agents/lib", STATE_PATH, ".agents"])
def test_symlinks_in_recorded_paths_fail(tmp_path: Path, name: str) -> None:
    target = tmp_path / "project"
    initialize(target)
    path = target / name
    outside = tmp_path / "outside"
    path.rename(outside)
    path.symlink_to(outside, target_is_directory=outside.is_dir())
    checks = diagnose(target)
    assert any(c.status == "FAIL" and "Unsafe" in c.message for c in checks)


@pytest.mark.parametrize("kind", ["directory", "broken_link", "fifo"])
def test_non_regular_installed_files_fail(tmp_path: Path, kind: str) -> None:
    initialize(tmp_path)
    path = tmp_path / "AGENTS.md"
    path.unlink()
    if kind == "directory":
        path.mkdir()
    elif kind == "broken_link":
        path.symlink_to(tmp_path / "absent")
    else:
        os.mkfifo(path)
    assert any(
        c.status == "FAIL" and "Unsafe installed path: 'AGENTS.md'" in c.message
        for c in diagnose(tmp_path)
    )


@pytest.mark.usefixtures("local_tools")
def test_repeated_diagnostics_preserve_files_and_timestamps(
    historical_project: Path,
) -> None:
    target = historical_project
    (target / "CONSTITUTION.md").write_text("Local amendment\n", encoding="utf-8")
    (target / ".agents/.env").write_text("PRIVATE=untouched\n", encoding="utf-8")

    def snapshot() -> dict[str, tuple[bytes | None, int, int, int]]:
        result = {}
        for path in [target, *target.rglob("*")]:
            content = path.read_bytes() if path.is_file() else None
            stat = path.stat()
            result[str(path.relative_to(target))] = (
                content,
                stat.st_mtime_ns,
                stat.st_ctime_ns,
                stat.st_mode,
            )
        return result

    before = snapshot()
    first = diagnose(target)
    assert not any(check.status == "FAIL" for check in first)
    assert diagnose(target) == first
    assert snapshot() == before


def test_invalid_doctor_invocation_still_exits_two() -> None:
    with pytest.raises(SystemExit) as error:
        main(["doctor", "--unsupported-option"])
    assert error.value.code == 2


# Configuration fixtures contain executable-looking commands as inert data.
def component_configuration(
    components: tuple[tuple[str, str, tuple[str, ...]], ...],
) -> str:
    text = "schema_version = 1\n"
    for name, path, profiles in components:
        text += (
            f"[components.{name}]\npath = {json.dumps(path)}\n"
            f"profiles = {json.dumps(profiles)}\n"
        )
    for name, path, profiles in components:
        for profile in profiles:
            commands = (
                [(r.category, r.argv) for r in PYTHON.required_checks]
                if profile == "python"
                else [("tests", ("fixture-command-must-not-run",))]
            )
            for category, argv in commands:
                text += (
                    f'\n[[checks]]\nname = "{name}-{profile}-{category}"\n'
                    f'scope = "component"\ncomponent = "{name}"\n'
                    f'profile = "{profile}"\n'
                    f'category = "{category}"\ncwd = {json.dumps(path)}\n'
                    f"argv = {json.dumps(argv)}\n"
                    "required = true\ntimeout_seconds = 300\n"
                )
    return text


def two_python_components(root: Path) -> None:
    (root / "lean-sdd.toml").write_text(
        component_configuration(
            (
                ("api", "src/api", ("python",)),
                ("worker", "src/worker", ("python",)),
            )
        ),
        encoding="utf-8",
    )
    initialize(root)
    for name in ("api", "worker"):
        (root / "src" / name).mkdir(parents=True)


def application_checks(root: Path) -> list[tuple[str, str]]:
    return [
        (c.status, c.message)
        for c in diagnose(root)
        if c.message.startswith("Component ")
    ]


@pytest.mark.usefixtures("local_tools")
def test_python_diagnostics_use_each_component_not_the_repository_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    two_python_components(tmp_path)
    (tmp_path / "pyproject.toml").write_text("invalid root TOML", encoding="utf-8")
    (tmp_path / "uv.lock").symlink_to(tmp_path / "absent")
    api = tmp_path / "src/api"
    (api / "pyproject.toml").write_text('[project]\nname = "api"\n', encoding="utf-8")
    (api / "uv.lock").write_text(
        "lock contents are not executed or freshness-checked", encoding="utf-8"
    )
    assert main(["doctor", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert (
        "Component api (src/api), profile python: Python project metadata is present"
        in output
    )
    assert "Component api (src/api), profile python: uv.lock is present" in output
    assert (
        "WARN: Component worker (src/worker), profile python: No pyproject.toml"
        in output
    )
    assert "WARN: Component worker (src/worker), profile python: No uv.lock" in output
    assert "invalid TOML" not in output
    assert "Unsafe uv.lock" not in output
    assert "Component root" not in output


@pytest.mark.usefixtures("local_tools")
def test_legacy_implicit_and_explicit_root_mappings_are_distinguished(
    historical_project: Path,
) -> None:
    implicit = diagnose(historical_project)
    assert any("Mapping origin: installed-legacy" in c.message for c in implicit)
    assert any(
        "Component root (.), profile python: No pyproject.toml" in c.message
        for c in implicit
    )
    (historical_project / "lean-sdd.toml").write_text(
        component_configuration((("app", ".", ("python",)),)),
        encoding="utf-8",
    )
    explicit = diagnose(historical_project)
    assert any("Mapping origin: explicit" in c.message for c in explicit)
    assert any(
        "Component app (.), profile python: No pyproject.toml" in c.message
        for c in explicit
    )
    assert not any(c.status == "FAIL" for c in explicit)


@pytest.mark.parametrize(
    ("content", "status", "message"),
    [
        (b"[project]\nname='api'", "PASS", "metadata is present"),
        (b"[tool.example]\nvalue=1", "WARN", "no [project] metadata"),
        (b"project = false", "FAIL", "[project] must be a table"),
        (b"[broken", "FAIL", "invalid TOML"),
        (b"\xff", "FAIL", "not valid UTF-8"),
        (b"x" * (1024 * 1024 + 1), "FAIL", "exceeds the 1 MiB limit"),
        (b"value = " + b"[" * 2000 + b"]" * 2000, "FAIL", "invalid TOML"),
    ],
)
@pytest.mark.usefixtures("local_tools")
def test_python_metadata_failures_are_local_and_bounded(
    tmp_path: Path,
    content: bytes,
    status: str,
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    two_python_components(tmp_path)
    (tmp_path / "src/api/pyproject.toml").write_bytes(content)
    assert main(["doctor", str(tmp_path)]) == (1 if status == "FAIL" else 0)
    output = capsys.readouterr().out
    assert f"{status}: Component api (src/api), profile python:" in output
    assert message in output
    assert "Component worker (src/worker), profile python: No pyproject.toml" in output
    assert "Component api (src/api), profile python: No uv.lock" in output


@pytest.mark.parametrize("name", ["pyproject.toml", "uv.lock"])
@pytest.mark.parametrize("kind", ["symlink", "directory", "fifo"])
@pytest.mark.usefixtures("local_tools")
def test_component_metadata_rejects_unsafe_files_without_following_them(
    tmp_path: Path, name: str, kind: str
) -> None:
    two_python_components(tmp_path)
    path = tmp_path / "src/api" / name
    if kind == "symlink":
        path.symlink_to(tmp_path / "missing")
    elif kind == "directory":
        path.mkdir()
    else:
        os.mkfifo(path)
    checks = application_checks(tmp_path)
    assert (
        "FAIL",
        f"Component api (src/api), profile python: Unsafe {name} path; "
        "use a regular file.",
    ) in checks
    assert any("Component worker" in message for _, message in checks)


@pytest.mark.parametrize("kind", ["missing", "file", "symlink"])
@pytest.mark.usefixtures("local_tools")
def test_invalid_component_directories_fail_mapping_not_record_integrity(
    tmp_path: Path, kind: str
) -> None:
    two_python_components(tmp_path)
    path = tmp_path / "src/api"
    path.rmdir()
    if kind == "file":
        path.write_text("not a directory", encoding="utf-8")
    elif kind == "symlink":
        path.symlink_to(tmp_path / "src/worker", target_is_directory=True)
    checks = diagnose(tmp_path)
    assert any(
        c.status == "FAIL" and "Installed configuration: component api" in c.message
        for c in checks
    )
    assert any(
        c.status == "PASS" and "All recorded templates match" in c.message
        for c in checks
    )
    assert any("Component profile diagnostics unavailable" in c.message for c in checks)
    assert not any("Python project metadata" in c.message for c in checks)


@pytest.mark.parametrize("mode", ["malformed", "unsupported", "missing"])
@pytest.mark.usefixtures("local_tools")
def test_bad_mapping_does_not_fall_back_to_python(
    tmp_path: Path, mode: str, capsys: pytest.CaptureFixture[str]
) -> None:
    initialize(tmp_path)
    config = tmp_path / "lean-sdd.toml"
    if mode == "missing":
        config.unlink()
    elif mode == "malformed":
        config.write_text("[broken", encoding="utf-8")
    else:
        config.write_text(
            component_configuration((("app", ".", ("unsupported",)),)), encoding="utf-8"
        )
    assert main(["doctor", str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert "Installation record is valid (schema 2)" in output
    assert "FAIL: Installed configuration:" in output
    assert "Component profile diagnostics unavailable" in output
    assert "No pyproject.toml" not in output


@pytest.mark.parametrize("owned", [False, True])
@pytest.mark.usefixtures("local_tools")
def test_mapping_edits_are_separate_from_original_assets(
    tmp_path: Path, owned: bool
) -> None:
    config = tmp_path / "lean-sdd.toml"
    if not owned:
        config.write_text(
            component_configuration((("initial", ".", ("python",)),)), encoding="utf-8"
        )
    initialize(tmp_path)
    record = (tmp_path / STATE_PATH).read_bytes()
    config.write_text(
        component_configuration(
            (("api", "src/api", ("python",)), ("worker", "src/worker", ("python",)))
        ),
        encoding="utf-8",
    )
    for name in ("api", "worker"):
        (tmp_path / "src" / name).mkdir(parents=True)
    checks = diagnose(tmp_path)
    assert not any(c.status == "FAIL" for c in checks)
    assert any("matches current release" in c.message for c in checks)
    assert (
        any("Locally modified template: 'lean-sdd.toml'" in c.message for c in checks)
        == owned
    )
    assert any("Component api (src/api), profile python" in c.message for c in checks)
    assert any(
        "Component worker (src/worker), profile python" in c.message for c in checks
    )
    assert (tmp_path / STATE_PATH).read_bytes() == record


def inert_bundle(
    selected: Iterable[str], *, registry: ProfileRegistry
) -> ResolvedBundle:
    """Local resource stand-in with a distinct asset for each requested profile."""
    profiles = tuple(sorted(selected))
    payload = {"common.md": b"common fixture asset"}
    for profile in profiles:
        registry.get(profile)
        payload[f"{profile}.md"] = profile.encode("utf-8")
    return ResolvedBundle(package_version(), profiles, payload)


@pytest.fixture
def inert_registry(monkeypatch: pytest.MonkeyPatch) -> ProfileRegistry:
    registry = ProfileRegistry(
        (PYTHON, Profile("fixture", "Inert fixture", (RequiredCheck("tests"),)))
    )
    monkeypatch.setattr("lean_sdd.doctor.resolve_bundle", inert_bundle)
    return registry


def install_inert(
    root: Path, profiles: tuple[str, ...], registry: ProfileRegistry
) -> None:
    bundle = inert_bundle(profiles, registry=registry)
    for name, content in bundle.payload.items():
        (root / name).write_bytes(content)
    (root / STATE_PATH).parent.mkdir()
    (root / STATE_PATH).write_bytes(
        profile_installation_state(
            bundle.payload,
            template_version=bundle.template_version,
            identity=InstallationIdentity(bundle.profiles, "configured"),
        )
    )
    (root / "lean-sdd.toml").write_text(
        component_configuration((("app", ".", profiles),)), encoding="utf-8"
    )


@pytest.mark.parametrize("profiles", [("fixture",), ("fixture", "python")])
@pytest.mark.usefixtures("local_tools")
def test_static_dispatch_does_not_assign_python_to_other_profiles(
    tmp_path: Path, inert_registry: ProfileRegistry, profiles: tuple[str, ...]
) -> None:
    install_inert(tmp_path, profiles, inert_registry)
    checks = diagnose(tmp_path, registry=inert_registry)
    assert not any(c.status == "FAIL" for c in checks)
    assert any("matches current release" in c.message for c in checks)
    assert any(
        "Component app (.), profile fixture: Application diagnostics unavailable"
        in c.message
        for c in checks
    )
    assert any("No pyproject.toml" in c.message for c in checks) == (
        "python" in profiles
    )
    assert any("No uv.lock" in c.message for c in checks) == ("python" in profiles)
    assert any(c.message == "uv is available." for c in checks)


@pytest.mark.usefixtures("local_tools")
def test_shared_uv_remains_required_for_inert_non_python_profile(
    tmp_path: Path, inert_registry: ProfileRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_inert(tmp_path, ("fixture",), inert_registry)
    monkeypatch.setattr(
        "lean_sdd.doctor.shutil.which",
        lambda command: None if command == "uv" else f"/tools/{command}",
    )
    checks = diagnose(tmp_path, registry=inert_registry)
    assert any(
        c.status == "FAIL" and c.message == "Required command missing: uv"
        for c in checks
    )
    assert not any("pyproject.toml" in c.message for c in checks)


@pytest.mark.usefixtures("local_tools")
def test_mapping_subset_does_not_change_release_profile_combination(
    tmp_path: Path, inert_registry: ProfileRegistry
) -> None:
    install_inert(tmp_path, ("fixture", "python"), inert_registry)
    record = (tmp_path / STATE_PATH).read_bytes()
    (tmp_path / "lean-sdd.toml").write_text(
        component_configuration((("app", ".", ("fixture",)),)), encoding="utf-8"
    )
    checks = diagnose(tmp_path, registry=inert_registry)
    assert not any(c.status == "FAIL" for c in checks)
    assert any("matches current release" in c.message for c in checks)
    assert not any("pyproject.toml" in c.message for c in checks)
    assert (tmp_path / STATE_PATH).read_bytes() == record


@pytest.mark.usefixtures("local_tools")
def test_known_but_uninstalled_mapping_profile_is_a_failure(
    tmp_path: Path, inert_registry: ProfileRegistry
) -> None:
    install_inert(tmp_path, ("fixture",), inert_registry)
    (tmp_path / "lean-sdd.toml").write_text(
        component_configuration((("app", ".", ("python",)),)), encoding="utf-8"
    )
    checks = diagnose(tmp_path, registry=inert_registry)
    assert any(
        c.status == "FAIL" and "profiles that are not installed" in c.message
        for c in checks
    )
    assert any("matches current release" in c.message for c in checks)
    assert not any("No pyproject.toml" in c.message for c in checks)


@pytest.mark.usefixtures("local_tools")
def test_unavailable_historical_profile_still_reports_modified_and_missing_assets(
    tmp_path: Path,
) -> None:
    (tmp_path / "original.md").write_bytes(b"original")
    payload = {"original.md": b"original", "missing.md": b"missing"}
    (tmp_path / STATE_PATH).parent.mkdir()
    (tmp_path / STATE_PATH).write_bytes(
        profile_installation_state(
            payload,
            template_version="0.0.0",
            identity=InstallationIdentity(("retired",), "configured"),
        )
    )
    (tmp_path / "original.md").write_bytes(b"customized")
    checks = diagnose(tmp_path)
    assert any(
        c.status == "PASS" and "Installation record is valid" in c.message
        for c in checks
    )
    assert any(
        c.status == "WARN" and "Locally modified template: 'original.md'" in c.message
        for c in checks
    )
    assert any(
        c.status == "FAIL" and "Missing installed template: 'missing.md'" in c.message
        for c in checks
    )
    assert any(
        c.status == "FAIL"
        and "bundle unavailable: Unsupported profile: retired" in c.message
        for c in checks
    )
    assert any("Component profile diagnostics unavailable" in c.message for c in checks)
    assert not any(
        "Invalid installation record" in c.message or "pyproject.toml" in c.message
        for c in checks
    )


def installation_snapshot(root: Path) -> dict[str, tuple[bytes | None, int, int, int]]:
    result = {}
    for path in (root, *root.rglob("*")):
        metadata = path.stat()
        result[str(path.relative_to(root))] = (
            path.read_bytes() if path.is_file() else None,
            metadata.st_mode,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )
    return result


def test_diagnostics_never_load_secrets_execute_project_code_or_contact_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    two_python_components(tmp_path)
    marker = tmp_path / "must-not-exist"
    script = f"from pathlib import Path; Path({str(marker)!r}).touch()"
    (tmp_path / "src/api/project_hook.py").write_text(script, encoding="utf-8")
    (tmp_path / "src/api/pyproject.toml").write_text(
        '[project]\nname="api"\n[build-system]\nrequires=[]\n'
        'build-backend="project_hook"\nbackend-path=["."]\n',
        encoding="utf-8",
    )
    (tmp_path / ".agents/.env").write_text(
        f"touch '{marker}'\nSECRET=do-not-read-me\n", encoding="utf-8"
    )
    config = tmp_path / "lean-sdd.toml"
    with config.open("a", encoding="utf-8") as stream:
        stream.write(
            '\n[[checks]]\nname="sentinel"\nscope="project"\n'
            'category="side-effects"\ncwd="."\nrequired=false\ntimeout_seconds=1\n'
            + "argv="
            + json.dumps(["python", "-c", script])
            + "\n"
        )
    startup = tmp_path / "startup.sh"
    startup.write_text(f"touch '{marker}'", encoding="utf-8")
    monkeypatch.setenv("BASH_ENV", str(startup))
    monkeypatch.setenv("ENV", str(startup))
    monkeypatch.setenv("BASH_FUNC_printf%%", f"() {{ touch '{marker}'; }}")
    monkeypatch.setenv("GIT_TRACE", str(marker))
    monkeypatch.setenv("GIT_TRACE2_EVENT", str(marker))
    monkeypatch.setenv("GITHUB_TOKEN", "secret-value-must-not-be-printed")
    before = installation_snapshot(tmp_path)
    original_open = Path.open
    original_run = subprocess.run
    calls: list[tuple[str, ...]] = []

    def read_only(
        self: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> BinaryIO | TextIO:
        assert self.name != ".env", "Doctor loaded a secret file"
        assert mode in ("r", "rb"), "Doctor opened a file for writing"
        if mode == "rb":
            return original_open(self, "rb", buffering=buffering)
        return original_open(
            self,
            "r",
            buffering=buffering,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )

    def observed_run(
        arguments: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert cwd == tmp_path
        assert capture_output and text and timeout == 10 and not check
        assert not any(k.startswith(("GIT_", "BASH_FUNC_")) for k in env)
        assert "BASH_ENV" not in env and "ENV" not in env
        executable = Path(arguments[0])
        assert executable.is_absolute() and not executable.is_relative_to(tmp_path)
        if executable.name == "bash":
            assert arguments[1:] == [
                "--noprofile",
                "--norc",
                "-p",
                "-c",
                'printf "%s" "$BASH_VERSION"',
            ]
        else:
            assert executable.name == "git"
            assert arguments[1:] == ["rev-parse", "--show-toplevel"]
        calls.append(tuple(arguments))
        return original_run(
            arguments,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def no_network(*args: object, **kwargs: object) -> None:
        pytest.fail("Doctor attempted network access")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", read_only)
        patch.setattr(subprocess, "run", observed_run)
        patch.setattr(socket, "create_connection", no_network)
        patch.setattr(socket.socket, "connect", no_network)
        checks = diagnose(tmp_path)
    assert not any(c.status == "FAIL" for c in checks)
    assert calls  # Executes only the fixed real system observations above.
    assert not marker.exists()
    assert not any(
        "secret-value" in c.message or "do-not-read-me" in c.message for c in checks
    )
    assert installation_snapshot(tmp_path) == before


@pytest.mark.parametrize("relative_path", [False, True])
def test_shared_observations_refuse_executables_inside_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative_path: bool
) -> None:
    initialize(tmp_path)
    binary = tmp_path / "bin"
    binary.mkdir()
    marker = tmp_path / "executed"
    for name in ("bash", "git"):
        path = binary / name
        path.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
        path.chmod(0o755)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "PATH",
        ("bin" if relative_path else str(binary))
        + os.pathsep
        + os.environ.get("PATH", ""),
    )
    checks = diagnose(tmp_path)
    assert any(
        c.status == "FAIL" and "Cannot inspect Bash version" in c.message
        for c in checks
    )
    assert any(
        c.status == "FAIL" and "Cannot inspect Git worktree" in c.message
        for c in checks
    )
    assert not marker.exists()


@pytest.mark.parametrize("failure", ["timeout", "unreadable"])
@pytest.mark.usefixtures("local_tools")
def test_shared_observation_errors_preserve_independent_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    initialize(tmp_path)

    def fail(arguments: list[str], target: Path) -> subprocess.CompletedProcess[str]:
        if failure == "timeout":
            raise subprocess.TimeoutExpired(arguments, 10, output="secret-output")
        raise PermissionError("secret-error")

    monkeypatch.setattr("lean_sdd.doctor._run", fail)
    checks = diagnose(tmp_path)
    assert sum(c.status == "FAIL" for c in checks) == 2
    assert any("All recorded templates match" in c.message for c in checks)
    assert any("No pyproject.toml" in c.message for c in checks)
    assert not any("secret" in c.message for c in checks)


@pytest.mark.usefixtures("local_tools")
def test_unreadable_metadata_reports_component_without_losing_other_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    two_python_components(tmp_path)
    metadata = tmp_path / "src/api/pyproject.toml"
    metadata.write_text("[project]", encoding="utf-8")
    original = Path.open

    def fail_metadata(
        self: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> BinaryIO | TextIO:
        if self == metadata:
            raise PermissionError("private filesystem detail")
        if mode == "rb":
            return original(self, "rb", buffering=buffering)
        assert mode == "r"
        return original(
            self,
            "r",
            buffering=buffering,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )

    monkeypatch.setattr(Path, "open", fail_metadata)
    checks = diagnose(tmp_path)
    assert any(
        c.status == "FAIL"
        and "Component api (src/api), profile python: Cannot read pyproject.toml"
        in c.message
        for c in checks
    )
    assert any(
        "Component worker (src/worker), profile python: No pyproject.toml" in c.message
        for c in checks
    )
    assert not any("private filesystem" in c.message for c in checks)


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("pyproject.toml", "Cannot read pyproject.toml"),
        ("uv.lock", "Cannot inspect uv.lock"),
        (STATE_PATH, "Cannot read installation record"),
        ("AGENTS.md", "Cannot read installed template: 'AGENTS.md'"),
    ],
)
@pytest.mark.usefixtures("local_tools")
def test_inaccessible_file_metadata_is_not_reported_as_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, message: str
) -> None:
    initialize(tmp_path)
    path = tmp_path / name
    if not path.exists():
        path.write_text("", encoding="utf-8")
    original = Path.lstat

    def inaccessible(self: Path) -> os.stat_result:
        if self == path:
            raise PermissionError("private access details")
        return original(self)

    monkeypatch.setattr(Path, "lstat", inaccessible)
    checks = diagnose(tmp_path)
    assert any(c.status == "FAIL" and message in c.message for c in checks)
    assert not any("private access details" in c.message for c in checks)
