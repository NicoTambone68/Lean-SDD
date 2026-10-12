"""Local diagnostics must be informative without running project code."""

from pathlib import Path

import pytest

from lean_sdd.cli import main
from lean_sdd.doctor import diagnose
from lean_sdd.installer import initialize
from lean_sdd.templates import STATE_PATH


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
    assert "record differs" in checks[0].message


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
