"""Exercise initialization against real temporary filesystems."""

import json
from pathlib import Path

import pytest

from lean_sdd.cli import main
from lean_sdd.installer import InstallError, initialize
from lean_sdd.templates import STATE_PATH, package_version, template_files


def test_install_is_complete_and_repeatable(tmp_path: Path) -> None:
    target = tmp_path / "project with spaces"
    first = initialize(target)
    payload = template_files()
    assert set(first.created) == {*payload, STATE_PATH}
    for name, content in payload.items():
        path = target / name
        assert path.read_bytes() == content
        if name.endswith(".sh"):
            assert path.stat().st_mode & 0o111
    state = json.loads((target / STATE_PATH).read_text())
    assert state["template_version"] == package_version()
    assert set(state["files"]) == set(payload)
    before = {name: (target / name).stat().st_mtime_ns for name in first.created}
    second = initialize(target)
    assert second.created == ()
    assert set(second.unchanged) == set(first.created)
    assert before == {
        name: (target / name).stat().st_mtime_ns for name in first.created
    }
    assert not (target / ".git").exists()
    assert not (target / "pyproject.toml").exists()
    assert not (target / ".agents/.env").exists()


def test_conflicts_are_detected_before_any_write(tmp_path: Path) -> None:
    original = tmp_path / "CODING_STANDARDS.md"
    original.write_text("Project-specific rules\n")
    with pytest.raises(InstallError, match="Conflicting files"):
        initialize(tmp_path)
    assert original.read_text() == "Project-specific rules\n"
    assert list(tmp_path.iterdir()) == [original]


def test_unrelated_files_and_secrets_are_preserved(tmp_path: Path) -> None:
    agents = tmp_path / ".agents"
    agents.mkdir()
    secret = agents / ".env"
    secret.write_text("PRIVATE_CONFIGURATION=keep-me\n")
    (tmp_path / "README.md").write_text("My application\n")
    initialize(tmp_path)
    assert secret.read_text() == "PRIVATE_CONFIGURATION=keep-me\n"
    assert (tmp_path / "README.md").read_text() == "My application\n"
    assert (agents / ".gitignore").is_file()


def test_dry_run_does_not_create_target(tmp_path: Path) -> None:
    target = tmp_path / "absent"
    result = initialize(target, dry_run=True)
    assert result.created
    assert not target.exists()


@pytest.mark.parametrize("relative", ["AGENTS.md", ".agents", ".agents/lib"])
def test_symlinks_cannot_redirect_installation(tmp_path: Path, relative: str) -> None:
    target = tmp_path / "target"
    target.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = target / relative
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(InstallError, match="[Ss]ymbolic|[Pp]arent"):
        initialize(target)
    assert not list(outside.iterdir())
    assert not (target / "CONSTITUTION.md").exists()


def test_file_as_parent_is_rejected_before_writes(tmp_path: Path) -> None:
    (tmp_path / ".agents").write_text("not a directory")
    with pytest.raises(InstallError, match="parent"):
        initialize(tmp_path)
    assert not (tmp_path / "AGENTS.md").exists()


def test_partial_write_failure_cleans_up_only_new_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "project"
    target.mkdir()
    unrelated = target / "notes.txt"
    unrelated.write_text("keep")
    original = Path.chmod

    def fail_on_script(self: Path, mode: int, *, follow_symlinks: bool = True) -> None:
        if self.suffix == ".sh":
            raise OSError("simulated filesystem failure")
        original(self, mode, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "chmod", fail_on_script)
    with pytest.raises(InstallError, match="simulated filesystem failure"):
        initialize(target)
    assert list(target.iterdir()) == [unrelated]
    assert unrelated.read_text() == "keep"


def test_existing_install_record_cannot_be_silently_upgraded(tmp_path: Path) -> None:
    initialize(tmp_path)
    record = tmp_path / STATE_PATH
    content = json.loads(record.read_text())
    content["template_version"] = "0.0.0"
    record.write_text(json.dumps(content))
    with pytest.raises(InstallError, match="lean-sdd-install.json"):
        initialize(tmp_path)
    assert json.loads(record.read_text())["template_version"] == "0.0.0"


def test_cli_exit_status_and_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "new"
    assert main(["init", str(target), "--dry-run"]) == 0
    assert "Would create" in capsys.readouterr().out
    assert not target.exists()
    target.mkdir()
    (target / "AGENTS.md").write_text("custom")
    assert main(["init", str(target)]) == 1
    assert "Conflicting files" in capsys.readouterr().err
