"""Profile selection, original-record ownership and transactional initialization."""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import BinaryIO, Literal, TextIO

import pytest

from lean_sdd.cli import main
from lean_sdd.configuration import (
    CONFIGURATION_NAME,
    ConfigurationError,
    InstallationIdentity,
    default_configuration_bytes,
    parse_configuration,
)
from lean_sdd.doctor import diagnose
from lean_sdd.installer import InstallError, initialize
from lean_sdd.templates import (
    STATE_PATH,
    installation_state,
    package_version,
    parse_installation_state,
    profile_installation_state,
    resolve_bundle,
    template_files,
    template_manifest,
)


def snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def install_legacy(root: Path) -> None:
    payload = template_files()
    for name, content in payload.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    # Unusual JSON formatting and digest case are valid historical bytes.
    state = json.loads(installation_state(payload))
    state["files"] = {name: digest.upper() for name, digest in state["files"].items()}
    state["historical_extension"] = "preserve"
    (root / STATE_PATH).write_text(json.dumps(state, indent=4), encoding="utf-8")


def two_components() -> str:
    documentation = (Path(__file__).parents[1] / "docs/configuration.md").read_text(
        encoding="utf-8"
    )
    return list(re.finditer(r"```toml\n(.*?)```", documentation, re.DOTALL))[1].group(1)


@pytest.mark.parametrize("language", [None, "python"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_default_and_explicit_python_report_same_mapping(
    tmp_path: Path, language: str | None, dry_run: bool
) -> None:
    target = tmp_path / "new"
    result = initialize(target, language=language, dry_run=dry_run)
    assert result.profiles == ("python",)
    assert [
        (c.id, str(c.path), c.profiles) for c in result.configuration.components
    ] == [("root", ".", ("python",))]
    assert CONFIGURATION_NAME in result.created
    assert ".agents/standards/python.md" in result.created
    if dry_run:
        assert not target.exists()
    else:
        state = parse_installation_state(
            (target / STATE_PATH).read_text(encoding="utf-8")
        )
        assert state.schema_version == 2
        assert state.identity == InstallationIdentity(("python",), "configured")
        assert state.files == template_manifest(
            {
                name: (target / name).read_bytes()
                for name in result.created
                if name != STATE_PATH
            }
        )
        assert (
            parse_configuration(
                (target / CONFIGURATION_NAME).read_text(encoding="utf-8")
            )
            == result.configuration
        )


def test_languages_and_cli_selection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["languages"]) == 0
    assert capsys.readouterr().out == "python: Python\ntypescript: TypeScript\n"
    target = tmp_path / "new"
    assert main(["init", str(target), "--language", "python", "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "Profiles: python" in output
    assert "Component root: . [python]" in output
    assert not target.exists()


@pytest.mark.parametrize("language", ["rust", "unknown", "Python"])
def test_unsupported_languages_do_not_default_or_write(
    tmp_path: Path, language: str, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "new"
    assert main(["init", str(target), "--language", language]) == 1
    assert "ERROR:" in capsys.readouterr().err
    assert not target.exists()


@pytest.mark.parametrize("multi", [False, True])
@pytest.mark.parametrize("dry_run", [False, True])
def test_explicit_configuration_is_preserved_and_never_claimed_as_installed(
    tmp_path: Path, multi: bool, dry_run: bool
) -> None:
    path = tmp_path / CONFIGURATION_NAME
    content = "# User formatting and comments survive.\r\n" + (
        two_components() if multi else default_configuration_bytes().decode("utf-8")
    )
    path.write_bytes(content.encode("utf-8"))
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    result = initialize(tmp_path, dry_run=dry_run)
    assert result.profiles == ("python",)
    assert len(result.configuration.components) == (2 if multi else 1)
    assert result.preserved == (CONFIGURATION_NAME,)
    assert CONFIGURATION_NAME not in result.created
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert not (tmp_path / "src").exists()
    if dry_run:
        assert list(tmp_path.iterdir()) == [path]
    else:
        record = parse_installation_state(
            (tmp_path / STATE_PATH).read_text(encoding="utf-8")
        )
        assert CONFIGURATION_NAME not in record.files
        before_all = snapshot(tmp_path)
        assert initialize(tmp_path).created == ()
        assert snapshot(tmp_path) == before_all


def test_two_component_mapping_conflicts_with_language_convenience(
    tmp_path: Path,
) -> None:
    (tmp_path / CONFIGURATION_NAME).write_text(two_components(), encoding="utf-8")
    before = snapshot(tmp_path)
    with pytest.raises(ConfigurationError, match="conflicts.*mapping"):
        initialize(tmp_path, language="python")
    assert snapshot(tmp_path) == before


def test_matching_single_component_option_preserves_user_mapping(
    tmp_path: Path,
) -> None:
    path = tmp_path / CONFIGURATION_NAME
    path.write_bytes(default_configuration_bytes().replace(b"root", b"app"))
    before = path.read_bytes()
    result = initialize(tmp_path, language="python")
    assert result.configuration.components[0].id == "app"
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "content", [b"", b"[broken", b"\xff", b"x" * (1024 * 1024 + 1)]
)
def test_bad_configuration_never_falls_back(tmp_path: Path, content: bytes) -> None:
    (tmp_path / CONFIGURATION_NAME).write_bytes(content)
    before = snapshot(tmp_path)
    with pytest.raises(ConfigurationError):
        initialize(tmp_path, language="python")
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("owned", [False, True])
def test_missing_configured_file_is_not_regenerated(
    tmp_path: Path, owned: bool
) -> None:
    if not owned:
        (tmp_path / CONFIGURATION_NAME).write_bytes(default_configuration_bytes())
    initialize(tmp_path)
    (tmp_path / CONFIGURATION_NAME).unlink()
    before = snapshot(tmp_path)
    with pytest.raises(ConfigurationError, match="requires lean-sdd.toml"):
        initialize(tmp_path, language="python")
    assert snapshot(tmp_path) == before
    assert any(
        c.status == "FAIL" and "requires lean-sdd.toml" in c.message
        for c in diagnose(tmp_path)
    )


@pytest.mark.parametrize("owned", [False, True])
def test_mapping_edits_do_not_rewrite_original_hashes_or_identity(
    tmp_path: Path, owned: bool
) -> None:
    config = tmp_path / CONFIGURATION_NAME
    if not owned:
        config.write_bytes(default_configuration_bytes())
    initialize(tmp_path)
    record = tmp_path / STATE_PATH
    original_record = record.read_bytes()
    config.write_text(two_components(), encoding="utf-8")
    before = snapshot(tmp_path)
    result = initialize(tmp_path)
    assert result.created == ()
    assert len(result.configuration.components) == 2
    assert snapshot(tmp_path) == before
    assert record.read_bytes() == original_record
    checks = diagnose(tmp_path)
    assert not any("contradicts" in c.message for c in checks)
    assert (
        any("Locally modified template: 'lean-sdd.toml'" in c.message for c in checks)
        == owned
    )


@pytest.mark.parametrize("explicit", [False, True])
def test_legacy_reinitialization_keeps_record_bytes_and_layout(
    tmp_path: Path, explicit: bool
) -> None:
    install_legacy(tmp_path)
    if explicit:
        (tmp_path / CONFIGURATION_NAME).write_bytes(default_configuration_bytes())
    before = snapshot(tmp_path)
    result = initialize(tmp_path, language="python")
    assert result.created == ()
    assert snapshot(tmp_path) == before
    assert not (tmp_path / ".agents/standards").exists()
    assert (tmp_path / CONFIGURATION_NAME).exists() == explicit
    assert (
        parse_installation_state(
            (tmp_path / STATE_PATH).read_text(encoding="utf-8")
        ).schema_version
        == 1
    )


@pytest.mark.parametrize("legacy", [False, True])
def test_missing_asset_is_repaired_without_record_rewrite(
    tmp_path: Path, legacy: bool
) -> None:
    if legacy:
        install_legacy(tmp_path)
    else:
        initialize(tmp_path)
    record = tmp_path / STATE_PATH
    before = (record.read_bytes(), record.stat().st_mtime_ns)
    asset = tmp_path / ".agents/lib/mcp.sh"
    original = asset.read_bytes()
    asset.unlink()
    result = initialize(tmp_path)
    assert result.created == (".agents/lib/mcp.sh",)
    assert asset.read_bytes() == original
    assert (record.read_bytes(), record.stat().st_mtime_ns) == before


def test_schema_two_legacy_mode_does_not_generate_config(tmp_path: Path) -> None:
    payload = dict(resolve_bundle().payload)
    for name, content in payload.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (tmp_path / STATE_PATH).write_bytes(
        profile_installation_state(
            payload,
            template_version=package_version(),
            identity=InstallationIdentity(("python",), "legacy-python"),
        )
    )
    before = snapshot(tmp_path)
    assert initialize(tmp_path).created == ()
    assert snapshot(tmp_path) == before
    assert not (tmp_path / CONFIGURATION_NAME).exists()


@pytest.mark.parametrize("profiles", [["retired"], ["python", "retired"]])
def test_unknown_installed_profiles_stay_valid_but_cannot_be_substituted(
    tmp_path: Path, profiles: list[str]
) -> None:
    initialize(tmp_path)
    path = tmp_path / STATE_PATH
    state = json.loads(path.read_bytes())
    state["profiles"] = profiles
    path.write_text(json.dumps(state), encoding="utf-8")
    assert parse_installation_state(
        path.read_text(encoding="utf-8")
    ).identity.profiles == tuple(profiles)
    before = snapshot(tmp_path)
    with pytest.raises(ConfigurationError, match="Unsupported profile"):
        initialize(tmp_path)
    with pytest.raises(ConfigurationError, match="Unsupported profile"):
        initialize(tmp_path, language="python")
    checks = diagnose(tmp_path)
    assert any("bundle unavailable" in c.message for c in checks)
    assert any("All recorded templates match" in c.message for c in checks)
    assert not any("Invalid installation record" in c.message for c in checks)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("difference", ["release", "manifest", "asset"])
def test_repeat_conflicts_do_not_upgrade_or_restore_over_customizations(
    tmp_path: Path, legacy: bool, difference: str
) -> None:
    if legacy:
        install_legacy(tmp_path)
    else:
        initialize(tmp_path)
    path = tmp_path / STATE_PATH
    state = json.loads(path.read_bytes())
    if difference == "release":
        state["template_version"] = "0.0.0"
    elif difference == "manifest":
        state["files"]["AGENTS.md"] = "0" * 64
    else:
        (tmp_path / "AGENTS.md").write_text("Local rules", encoding="utf-8")
    path.write_text(json.dumps(state), encoding="utf-8")
    (tmp_path / ".agents/.env.example").unlink()
    before = snapshot(tmp_path)
    with pytest.raises(InstallError, match="Conflicting"):
        initialize(tmp_path)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "name", [CONFIGURATION_NAME, STATE_PATH, "src/api", ".agents/standards"]
)
def test_profile_paths_reject_symlinks_before_writes(tmp_path: Path, name: str) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / CONFIGURATION_NAME).write_text(two_components(), encoding="utf-8")
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    path.symlink_to(outside, target_is_directory=True)
    with pytest.raises(
        (InstallError, ConfigurationError), match="[Ss]ymbolic|[Ss]ymlink|Unsafe parent"
    ):
        initialize(root)
    assert not (root / "AGENTS.md").exists()
    assert not list(outside.iterdir())


def test_init_never_executes_configured_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "executed"
    text = default_configuration_bytes().decode("utf-8")
    text += (
        '\n[[checks]]\nname = "extra"\nscope = "project"\ncategory = "extra"\n'
        'cwd = "."\nrequired = false\ntimeout_seconds = 1\n'
    )
    text += "argv = " + json.dumps(
        [
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(marker)!r}).touch()",
        ]
    )
    (tmp_path / CONFIGURATION_NAME).write_text(text, encoding="utf-8")

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Initialization launched a process")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    initialize(tmp_path, dry_run=True)
    initialize(tmp_path)
    assert not marker.exists()


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_record_write_failure_rolls_back_generated_config_and_reports_leftovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cleanup_fails: bool
) -> None:
    target = tmp_path / "project"
    target.mkdir()
    (target / "notes.txt").write_text("keep", encoding="utf-8")
    original_open = Path.open
    original_unlink = Path.unlink

    def fail_record(
        self: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> BinaryIO | TextIO:
        # Metadata reads remain real; failure is scoped to the final record's
        # write, after exclusive creation and after configuration was installed.
        if mode == "r":
            return original_open(
                self,
                mode="r",
                buffering=buffering,
                encoding=encoding,
                errors=errors,
                newline=newline,
            )
        assert mode in ("rb", "xb")
        binary_mode: Literal["rb", "xb"] = "rb" if mode == "rb" else "xb"
        stream = original_open(self, mode=binary_mode, buffering=buffering)
        if str(self).endswith(STATE_PATH) and mode == "xb":
            assert (target / CONFIGURATION_NAME).is_file()
            write = stream.write

            def partial_write(content: bytes) -> int:
                write(content[:7])
                raise OSError("injected record write failure")

            monkeypatch.setattr(stream, "write", partial_write)
        return stream

    def fail_cleanup(self: Path, missing_ok: bool = False) -> None:
        if cleanup_fails and self.name == CONFIGURATION_NAME:
            raise OSError("injected cleanup failure")
        original_unlink(self, missing_ok=missing_ok)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", fail_record)
        patch.setattr(Path, "unlink", fail_cleanup)
        with pytest.raises(
            InstallError, match="injected record write failure"
        ) as error:
            initialize(target)
    if cleanup_fails:
        assert "Review leftover paths:" in str(error.value)
        assert CONFIGURATION_NAME in str(error.value)
        assert (target / CONFIGURATION_NAME).is_file()
    else:
        assert "Newly created files were removed" in str(error.value)
        assert {p.name for p in target.iterdir()} == {"notes.txt"}
    assert (target / "notes.txt").read_text(encoding="utf-8") == "keep"
    assert not (target / STATE_PATH).exists()


@pytest.mark.parametrize(
    "content", [b"{", b"\xff", b"x" * 1_000_001, b'{"schema_version": 3}']
)
def test_invalid_record_never_becomes_a_fresh_install(
    tmp_path: Path, content: bytes
) -> None:
    path = tmp_path / STATE_PATH
    path.parent.mkdir()
    path.write_bytes(content)
    before = snapshot(tmp_path)
    with pytest.raises(InstallError):
        initialize(tmp_path)
    assert snapshot(tmp_path) == before


def test_exclusive_creation_preserves_file_appearing_after_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lean_sdd import installer

    root = tmp_path / "project"
    root.mkdir()
    original = installer._make_directories
    config = root / CONFIGURATION_NAME

    def appear_before_open(path: Path, created: list[Path]) -> None:
        original(path, created)
        # The generated configuration is the first root-level write after the
        # composed payload. Simulate a competing file at this exact boundary.
        if path == root and (root / "CONSTITUTION.md").exists():
            config.write_bytes(b"owned by another writer")

    monkeypatch.setattr(installer, "_make_directories", appear_before_open)
    with pytest.raises(InstallError, match="Installation failed"):
        initialize(root)
    assert config.read_bytes() == b"owned by another writer"
    assert list(root.iterdir()) == [config]
