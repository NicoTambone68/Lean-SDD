"""Local diagnostics must be informative without running project code."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from lean_sdd.cli import main
from lean_sdd.doctor import diagnose
from lean_sdd.installer import initialize
from lean_sdd.templates import STATE_PATH, package_version, template_files


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
        older.setattr("lean_sdd.installer.template_files", lambda: payload)
        initialize(tmp_path)
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
        (b'{"schema_version": 2}', "Unsupported installation record schema_version: 2"),
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
