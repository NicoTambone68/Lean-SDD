"""TypeScript metadata, ownership and validation failure contracts."""

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from lean_sdd.configuration import (
    ConfigurationError,
    default_configuration_bytes,
    parse_configuration,
)
from lean_sdd.doctor import diagnose
from lean_sdd.installer import initialize
from lean_sdd.profiles import BUILTIN_PROFILES, TYPESCRIPT, ProfileRegistry
from lean_sdd.templates import STATE_PATH, resolve_bundle
from lean_sdd.typescript import MAX_METADATA_BYTES, inspect_typescript
from lean_sdd.validation import check_execution_boundaries, prepare_validation
from lean_sdd.validation_runner import run_validation

REGISTRY = BUILTIN_PROFILES


def metadata(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    package = {
        "name": "candidate",
        "version": "1.0.0",
        "type": "module",
        "packageManager": "npm@11.20.0",
        "engines": {"node": ">=26.13.1 <27"},
        "scripts": {
            name: "inert unit-test metadata"
            for name in ("typecheck", "lint", "format:check", "test", "build")
        },
    }
    lock = {
        "lockfileVersion": 3,
        "packages": {"": {"name": "candidate", "version": "1.0.0"}},
    }
    config = {
        "compilerOptions": {
            "strict": True,
            "noEmitOnError": True,
            "declaration": True,
            "module": "NodeNext",
            "moduleResolution": "NodeNext",
            "target": "ES2023",
            "rootDir": "src",
            "outDir": "src/.build",
        }
    }
    for name, content in (
        ("package.json", package),
        ("package-lock.json", lock),
        ("tsconfig.json", config),
    ):
        (root / name).write_text(json.dumps(content), encoding="utf-8")


def observations(root: Path) -> str:
    config = parse_configuration(
        default_configuration_bytes("typescript", registry=REGISTRY).decode(),
        registry=REGISTRY,
    )
    return "\n".join(
        f"{item.status}: {item.message}"
        for item in inspect_typescript(root, config.components[0], config.checks)
    )


def snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def test_builtin_typescript_obligations_cannot_be_replaced() -> None:
    assert tuple(profile.id for profile in BUILTIN_PROFILES.profiles) == (
        "python",
        "typescript",
    )
    assert BUILTIN_PROFILES.get("typescript") is TYPESCRIPT
    with pytest.raises(ValueError, match="cannot replace"):
        ProfileRegistry((replace(TYPESCRIPT, tools=()),))


@pytest.mark.parametrize("profiles", [("typescript",), ("python", "typescript")])
def test_typescript_bundle_composes_without_overriding_python(
    profiles: tuple[str, ...],
) -> None:
    bundle = resolve_bundle(profiles, registry=REGISTRY)
    assert bundle.profiles == profiles
    assert (
        b"TypeScript Coding Standards"
        in bundle.payload[".agents/standards/typescript.md"]
    )
    assert b"Node/npm contract" in bundle.payload[".agents/docs/typescript.md"]
    python = resolve_bundle()
    for path in ("AGENTS.md", "CONSTITUTION.md", ".agents/lib/github-pr.sh"):
        assert bundle.payload[path] == python.payload[path]
    if "python" in profiles:
        assert (
            bundle.payload[".agents/standards/python.md"]
            == python.payload[".agents/standards/python.md"]
        )


def test_initialization_and_repeat_preserve_application_metadata(
    tmp_path: Path,
) -> None:
    metadata(tmp_path)
    before = snapshot(tmp_path)
    planned = initialize(
        tmp_path, language="typescript", registry=REGISTRY, dry_run=True
    )
    assert planned.profiles == ("typescript",)
    assert snapshot(tmp_path) == before
    result = initialize(tmp_path, language="typescript", registry=REGISTRY)
    assert result.profiles == ("typescript",)
    assert all(snapshot(tmp_path)[key] == value for key, value in before.items())
    all_files = snapshot(tmp_path)
    assert initialize(tmp_path, registry=REGISTRY).created == ()
    assert snapshot(tmp_path) == all_files
    assert "FAIL" not in observations(tmp_path)
    with pytest.raises(ConfigurationError, match="switch"):
        initialize(tmp_path, language="python", registry=REGISTRY)
    state = json.loads((tmp_path / STATE_PATH).read_text())
    assert not set(before).intersection(state["files"])


@pytest.mark.parametrize("category", ["types", "lint", "format", "tests", "build"])
@pytest.mark.parametrize(
    "mutation", ["optional", "wrong-manager", "flags", "wrong-cwd", "missing"]
)
def test_required_categories_and_npm_adapter_cannot_be_weakened(
    category: str, mutation: str
) -> None:
    text = default_configuration_bytes("typescript", registry=REGISTRY).decode()
    blocks = text.split("[[checks]]")
    for index, block in enumerate(blocks):
        if f'category = "{category}"' not in block:
            continue
        if mutation == "optional":
            blocks[index] = block.replace("required = true", "required = false")
        elif mutation == "wrong-manager":
            blocks[index] = block.replace('"npm"', '"pnpm"')
        elif mutation == "flags":
            blocks[index] = block.replace('"run",', '"run", "--if-present",')
        elif mutation == "wrong-cwd":
            blocks[index] = block.replace('cwd = "."', 'cwd = "src"')
        else:
            del blocks[index]
        break
    with pytest.raises(ConfigurationError):
        parse_configuration("[[checks]]".join(blocks), registry=REGISTRY)


@pytest.mark.parametrize("name", ["package.json", "package-lock.json", "tsconfig.json"])
@pytest.mark.parametrize(
    "content", [b"", b"[]", b"{", b"\xff", b'{"x":1,"x":2}', b'{"x":NaN}']
)
def test_malformed_metadata_fails_without_echoing_values(
    tmp_path: Path, name: str, content: bytes
) -> None:
    metadata(tmp_path)
    (tmp_path / name).write_bytes(content)
    assert f"FAIL: Cannot read valid bounded {name}" in observations(tmp_path)


@pytest.mark.parametrize("name", ["package.json", "package-lock.json", "tsconfig.json"])
def test_missing_is_advisory_but_blocks_all_validation(
    tmp_path: Path, name: str
) -> None:
    metadata(tmp_path)
    initialize(tmp_path, language="typescript", registry=REGISTRY)
    (tmp_path / name).unlink()
    assert f"WARN: Missing {name}" in observations(tmp_path)
    result = run_validation(prepare_validation(tmp_path, registry=REGISTRY))
    assert result.exit_code == 1
    assert all(
        check.status in {"not-run", "missing-executable"} for check in result.checks
    )
    assert any(f"Missing {name}" in problem for problem in result.problems)


@pytest.mark.parametrize("name", ["package.json", "package-lock.json", "tsconfig.json"])
def test_links_are_rejected_without_following(tmp_path: Path, name: str) -> None:
    metadata(tmp_path)
    (tmp_path / name).unlink()
    (tmp_path / name).symlink_to(tmp_path / "secret")
    (tmp_path / "secret").write_text("private-value", encoding="utf-8")
    result = observations(tmp_path)
    assert "FAIL" in result
    assert "private-value" not in result


@pytest.mark.parametrize(
    ("file", "field", "value", "message"),
    [
        ("package.json", "workspaces", [], "workspaces"),
        ("package.json", "type", "browser", "module or commonjs"),
        ("package.json", "packageManager", "pnpm@10", "npm@11.20.0"),
        ("package.json", "engines", {"node": "*"}, "engines.node"),
        ("package.json", "scripts", {}, "script missing"),
        ("package-lock.json", "lockfileVersion", True, "lockfileVersion"),
        ("package-lock.json", "packages", {}, "root package"),
        ("tsconfig.json", "extends", "private-config", "inheritance"),
        ("tsconfig.json", "references", [], "references"),
    ],
)
def test_incompatible_metadata_is_explicit(
    tmp_path: Path, file: str, field: str, value: object, message: str
) -> None:
    metadata(tmp_path)
    path = tmp_path / file
    document = json.loads(path.read_text())
    document[field] = value
    path.write_text(json.dumps(document), encoding="utf-8")
    result = observations(tmp_path)
    assert "FAIL" in result and message in result
    assert "private-config" not in result


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("strict", False),
        ("strictNullChecks", False),
        ("noEmitOnError", False),
        ("declaration", False),
        ("noEmit", True),
        ("noCheck", True),
        ("strictNullChecks", "false"),
        ("module", "ESNext"),
        ("moduleResolution", "Bundler"),
        ("target", "ESNext"),
        ("rootDir", "."),
        ("outDir", "dist"),
        ("outDir", "../outside"),
        ("outFile", "src/output.js"),
        ("declarationDir", "src/types"),
    ],
)
def test_compiler_contract_cannot_relax_strictness_or_source_boundary(
    tmp_path: Path, field: str, value: object
) -> None:
    metadata(tmp_path)
    path = tmp_path / "tsconfig.json"
    document = json.loads(path.read_text())
    document["compilerOptions"][field] = value
    path.write_text(json.dumps(document), encoding="utf-8")
    assert "FAIL" in observations(tmp_path)


def test_json_comments_trailing_commas_and_strings_are_not_evaluated(
    tmp_path: Path,
) -> None:
    metadata(tmp_path)
    path = tmp_path / "tsconfig.json"
    text = path.read_text().replace(
        '"compilerOptions":', '/* declaration */ "compilerOptions":'
    )
    text = text[:-1] + ', "note": "https://example.test/\\"/*literal*/,}",}'
    path.write_text("// comment\n" + text, encoding="utf-8")
    assert "FAIL" not in observations(tmp_path)
    path.write_text(text + " /*unterminated", encoding="utf-8")
    assert "FAIL" in observations(tmp_path)


def test_large_metadata_and_lock_drift_fail(tmp_path: Path) -> None:
    metadata(tmp_path)
    lock_path = tmp_path / "package-lock.json"
    lock = json.loads(lock_path.read_text())
    lock["packages"][""]["version"] = "2.0.0"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    assert "Lock root metadata differs" in observations(tmp_path)
    (tmp_path / "package.json").write_bytes(b" " * (MAX_METADATA_BYTES + 1))
    assert "Cannot read valid bounded package.json" in observations(tmp_path)


@pytest.mark.parametrize(
    "name", ["yarn.lock", "pnpm-lock.yaml", "bun.lock", "npm-shrinkwrap.json"]
)
def test_other_package_managers_are_preserved_and_diagnosed(
    tmp_path: Path, name: str
) -> None:
    metadata(tmp_path)
    (tmp_path / name).write_text("preserve", encoding="utf-8")
    before = snapshot(tmp_path)
    assert f"Conflicting {name}" in observations(tmp_path)
    assert snapshot(tmp_path) == before


def test_doctor_never_launches_node_npm_or_project_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata(tmp_path)
    initialize(tmp_path, language="typescript", registry=REGISTRY)
    (tmp_path / ".env").write_text("DO_NOT_LOAD=private-marker", encoding="utf-8")
    before = snapshot(tmp_path)

    def guard(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert Path(args[0]).name in {"bash", "git"}
        return subprocess.CompletedProcess(
            args, 0, "5\n" if Path(args[0]).name == "bash" else str(tmp_path) + "\n", ""
        )

    monkeypatch.setattr(subprocess, "run", guard)
    result = diagnose(tmp_path, registry=REGISTRY)
    messages = "\n".join(item.message for item in result)
    assert "profile typescript" in messages
    assert "private-marker" not in messages
    assert "Python project" not in messages
    assert snapshot(tmp_path) == before


def test_prelaunch_rechecks_changed_metadata(tmp_path: Path) -> None:
    metadata(tmp_path)
    initialize(tmp_path, language="typescript", registry=REGISTRY)
    plan = prepare_validation(tmp_path, registry=REGISTRY)
    (tmp_path / "package.json").write_text("broken", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="TypeScript"):
        check_execution_boundaries(plan)
