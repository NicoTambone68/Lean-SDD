"""Real tools only: opt-in acceptance must fail when prerequisites are absent.

No fake compiler, version probe, package lock or npm executable can satisfy this
suite. Installation is an explicit test-setup operation in temporary projects.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from lean_sdd.installer import initialize
from lean_sdd.profiles import BUILTIN_PROFILES
from lean_sdd.validation import ValidationResult, prepare_validation
from lean_sdd.validation_runner import run_validation

pytestmark = pytest.mark.typescript_toolchain
FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY = BUILTIN_PROFILES


def command(argv: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, timeout=180, check=False
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed.stdout.strip()


@pytest.fixture(scope="module")
def installed_typescript(tmp_path_factory: pytest.TempPathFactory) -> Path:
    for tool in ("node", "npm", "uv"):
        assert shutil.which(tool), f"Required real tool missing: {tool}"
    root = tmp_path_factory.mktemp("real-typescript")
    assert command(["node", "--version"], root) == "v26.13.1"
    assert command(["npm", "--version"], root) == "11.20.0"
    source = FIXTURES / "typescript"
    assert (source / "package-lock.json").is_file(), (
        "Generate and review the npm lock with the pinned toolchain first; "
        "see tests/fixtures/typescript/README.md."
    )
    shutil.copytree(source, root, dirs_exist_ok=True)
    command(["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], root)
    manifest = json.loads((root / "package.json").read_text())
    for name, version in manifest["devDependencies"].items():
        installed = json.loads(
            (root / "node_modules" / name / "package.json").read_text()
        )
        assert installed["version"] == version
    return root


def copy_component(source: Path, target: Path) -> None:
    shutil.copytree(
        source,
        target,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            "node_modules", ".venv", "__pycache__", ".*cache", ".build"
        ),
    )
    if (source / "node_modules").is_dir():
        # Dependency sharing is acceptance setup, never a project source link.
        (target / "node_modules").symlink_to(
            source / "node_modules", target_is_directory=True
        )


def configuration(components: list[tuple[str, str, tuple[str, ...]]]) -> str:
    lines = ["schema_version = 1"]
    for identity, path, profiles in components:
        lines.extend(
            [
                f"[components.{identity}]",
                f"path = {json.dumps(path)}",
                f"profiles = {json.dumps(profiles)}",
            ]
        )
        for profile_id in profiles:
            profile = REGISTRY.get(profile_id)
            for requirement in profile.required_checks:
                category = requirement.category
                script = {
                    "types": "typecheck",
                    "format": "format:check",
                    "tests": "test",
                }.get(category, category)
                argv = requirement.argv or ("npm", "run", script)
                # All TypeScript builds precede Python's cross-language tests.
                order = "a" if profile_id == "typescript" else "b"
                lines.extend(
                    [
                        "[[checks]]",
                        f'name = "{order}-{identity}-{profile_id}-{category}"',
                        'scope = "component"',
                        f"component = {json.dumps(identity)}",
                        f"profile = {json.dumps(profile_id)}",
                        f"category = {json.dumps(category)}",
                        f"cwd = {json.dumps(path)}",
                        f"argv = {json.dumps(argv)}",
                        "required = true",
                        "timeout_seconds = 120",
                    ]
                )
    return "\n".join(lines) + "\n"


def execute(root: Path, peer: Path | None = None) -> ValidationResult:
    env = dict(os.environ)
    env["UV_PYTHON_DOWNLOADS"] = "never"
    env["UV_FROZEN"] = "true"
    if peer is not None:
        env["LEAN_SDD_TYPESCRIPT_PEER"] = str(peer)
    plan = prepare_validation(root, registry=REGISTRY, environment=env)
    assert not plan.problems, plan.problems
    return run_validation(plan)


@pytest.mark.parametrize("module_type", ["module", "commonjs"])
def test_single_component_real_checks(
    tmp_path: Path, installed_typescript: Path, module_type: str
) -> None:
    copy_component(installed_typescript, tmp_path)
    package_path = tmp_path / "package.json"
    package = json.loads(package_path.read_text())
    package["type"] = module_type
    package_path.write_text(json.dumps(package), encoding="utf-8")
    original = {
        name: (tmp_path / name).read_bytes()
        for name in (
            "package.json",
            "package-lock.json",
            "tsconfig.json",
            "src/index.ts",
        )
    }
    initialize(tmp_path, language="typescript", registry=REGISTRY)
    assert initialize(tmp_path, registry=REGISTRY).created == ()
    assert all(
        (tmp_path / name).read_bytes() == data for name, data in original.items()
    )
    result = execute(tmp_path)
    assert result.exit_code == 0, result
    assert (tmp_path / "src/.build/index.js").is_file()
    assert "export" in (tmp_path / "src/.build/index.d.ts").read_text(encoding="utf-8")
    assert {
        item.check.category for item in result.checks if item.status == "passed"
    } == {"types", "lint", "format", "tests", "build"}
    if module_type == "module":
        report = command(["lean-sdd", "validate", str(tmp_path)], tmp_path)
        assert "passed: typescript-build" in report
        assert "passed: typescript-tests" in report


@pytest.mark.parametrize("layout", ["two-typescript", "mixed", "both-profiles"])
def test_composed_application_real_checks(
    tmp_path: Path,
    installed_typescript: Path,
    layout: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    components: list[tuple[str, str, tuple[str, ...]]]
    if layout == "both-profiles":
        peer = tmp_path
        copy_component(installed_typescript, tmp_path)
        copy_component(FIXTURES / "typescript_python", tmp_path)
        components = [("app", ".", ("python", "typescript"))]
    else:
        peer = tmp_path / "src/worker"
        copy_component(installed_typescript, peer)
        second = tmp_path / "src/api"
        source = (
            installed_typescript
            if layout == "two-typescript"
            else FIXTURES / "typescript_python"
        )
        copy_component(source, second)
        profiles = ("typescript",) if layout == "two-typescript" else ("python",)
        components = [
            ("worker", "src/worker", ("typescript",)),
            ("api", "src/api", profiles),
        ]
    mapping = configuration(components)
    if layout == "mixed":
        mapping += """
[[checks]]
name = "z-shared-contract"
scope = "project"
category = "integration"
cwd = "src/api"
argv = ["uv", "run", "pytest", "tests/test_contract.py"]
required = true
timeout_seconds = 120
"""
    (tmp_path / "lean-sdd.toml").write_text(mapping, encoding="utf-8")
    initialize(tmp_path, registry=REGISTRY)
    if layout == "mixed":
        monkeypatch.setenv("LEAN_SDD_TYPESCRIPT_PEER", str(peer))
        monkeypatch.setenv("UV_FROZEN", "true")
        monkeypatch.setenv("UV_PYTHON_DOWNLOADS", "never")
        argv = ["lean-sdd", "validate", "."]
        report = command(argv, tmp_path)
        assert report.count("passed:") == 10
        assert "passed: z-shared-contract" in report
        standard = REGISTRY.get("typescript").standards_path
        (tmp_path / standard).unlink()
        blocked = subprocess.run(
            argv, cwd=tmp_path, capture_output=True, text=True, timeout=30, check=False
        )
        assert blocked.returncode == 1 and blocked.stdout.count("not-run:") == 10
        assert f"Profile typescript standards {standard}" in blocked.stderr
        return
    result = execute(tmp_path, peer=peer)
    assert result.exit_code == 0, result
    assert all(item.status == "passed" for item in result.checks)
    expected = 10 if layout == "two-typescript" else 9
    assert len(result.checks) == expected


@pytest.mark.parametrize("category", ["types", "lint", "format", "tests", "build"])
def test_required_failure_is_visible(
    tmp_path: Path, installed_typescript: Path, category: str
) -> None:
    copy_component(installed_typescript, tmp_path)
    initialize(tmp_path, language="typescript", registry=REGISTRY)
    if category in {"types", "lint", "format"}:
        addition = {
            "types": "\nexport const invalid: string = 42;\n",
            "lint": "\nconst unused = 42;\n",
            "format": "\nexport const badlySpaced=42;\n",
        }[category]
        path = tmp_path / "src/index.ts"
        path.write_text(path.read_text() + addition, encoding="utf-8")
    elif category == "tests":
        path = tmp_path / "tests/contract.test.mjs"
        path.write_text(
            path.read_text() + '\nthrow new Error("intentional test failure");\n',
            encoding="utf-8",
        )
    else:
        path = tmp_path / "package.json"
        package = json.loads(path.read_text())
        package["scripts"]["build"] = "tsc --notACompilerOption"
        path.write_text(json.dumps(package), encoding="utf-8")
    result = execute(tmp_path)
    assert result.exit_code == 1
    assert any(
        item.check.category == category and item.status == "failed"
        for item in result.checks
    ), result
