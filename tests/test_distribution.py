"""Verify actual wheels and source archives, including isolated tool installation."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest

from lean_sdd.profiles import PYTHON, TYPESCRIPT, ProfileRegistry
from lean_sdd.templates import (
    CORE_SKILLS,
    STATE_PATH,
    package_version,
    resolve_bundle,
    template_files,
    template_manifest,
)

ROOT = Path(__file__).resolve().parents[1]


def run(
    arguments: list[str], cwd: Path, env: dict[str, str], *, expected: int = 0
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        arguments,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    return result


@pytest.mark.parametrize(
    "profiles", [(), ("python",), ("typescript",), ("python", "typescript")]
)
def test_bundled_links_resolve_and_scripts_parse(
    tmp_path: Path, profiles: tuple[str, ...]
) -> None:
    registry = ProfileRegistry((PYTHON, TYPESCRIPT))
    payload = (
        resolve_bundle(profiles, registry=registry).payload
        if profiles
        else template_files()
    )
    for name, content in payload.items():
        if name.endswith(".md"):
            for link in re.findall(r"\]\(([^)]+)\)", content.decode()):
                if "://" in link or link.startswith("#"):
                    continue
                path = (Path(name).parent / link.split("#")[0]).as_posix()
                assert os.path.normpath(path) in payload, (name, link)
        elif name.endswith(".sh"):
            script = tmp_path / "script.sh"
            script.write_bytes(content)
            result = subprocess.run(
                ["bash", "-n", str(script)],
                capture_output=True,
                timeout=10,
                check=False,
            )
            assert result.returncode == 0, name
    assert not any(name.endswith("/.env") for name in payload)
    readiness = payload[".agents/github-workflow-acceptance.md"].decode()
    assert "NicoTambone68" not in readiness
    assert "not been established" in readiness
    assert {
        name.split("/")[2] for name in payload if name.endswith("/SKILL.md")
    } == CORE_SKILLS


@pytest.mark.parametrize("artifact", ["wheel", "sdist-rebuilt-wheel"])
def test_wheel_and_sdist_install_without_checkout(
    tmp_path: Path, artifact: str
) -> None:
    env = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "TMPDIR", "TEMP", "SYSTEMROOT", "UV_CACHE_DIR"}
    }
    env.pop("PYTHONPATH", None)
    env.pop("VIRTUAL_ENV", None)
    env.pop("GITHUB_TOKEN", None)
    env["GITHUB_MCP_URL"] = "https://api.githubcopilot.com/mcp/"
    env["UV_PYTHON_DOWNLOADS"] = "never"
    env["UV_TOOL_DIR"] = str(tmp_path / "tools")
    env["UV_TOOL_BIN_DIR"] = str(tmp_path / "bin")
    output = tmp_path / "dist"
    # Build a clean allowed-source snapshot with deliberate untracked exclusions.
    # Never copy real environment files or private workflow evidence into tests.
    source = tmp_path / "source"
    source.mkdir()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    targets = project["tool"]["hatch"]["build"]["targets"]
    for name in targets["sdist"]["only-include"]:
        origin, destination = ROOT / name, source / name
        if origin.is_dir():
            shutil.copytree(
                origin,
                destination,
                ignore=shutil.ignore_patterns(
                    ".env*",
                    "__pycache__",
                    "*.pyc",
                    ".pytest_cache",
                    ".mypy_cache",
                    ".ruff_cache",
                    "node_modules",
                    ".build",
                ),
            )
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, destination)
    sentinel = b"-".join((b"EXCLUDED", b"LOCAL", b"ACCEPTANCE", b"SENTINEL"))
    excluded = (
        ".env",
        ".agents/.env",
        ".agents/live-evidence.json",
        ".agents/github-workflow-acceptance.md",
        "local-result.json",
        "src/lean_sdd/.env.local",
        "tests/.env.private",
        "src/lean_sdd/__pycache__/secret.pyc",
        "tests/.pytest_cache/local",
    )
    for name in excluded:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(sentinel)
    run(
        ["uv", "build", "--no-sources", "--offline", "--out-dir", str(output)],
        source,
        env,
    )
    wheel = next(output.glob("*.whl"))
    archive = next(output.glob("*.tar.gz"))
    payload = template_files()
    composed = resolve_bundle()
    typescript_registry = ProfileRegistry((PYTHON, TYPESCRIPT))
    typescript_bundle = resolve_bundle(
        ("python", "typescript"), registry=typescript_registry
    )
    mappings = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "tool"
    ]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    packaged = {
        destination.removeprefix("lean_sdd_templates/"): (ROOT / source).read_bytes()
        for source, destination in mappings.items()
    }
    assert len(packaged) == len(mappings)
    with zipfile.ZipFile(wheel) as bundle:
        names = bundle.namelist()
        assert all(sentinel not in bundle.read(name) for name in names)
        installed = {
            name.removeprefix("lean_sdd_templates/")
            for name in names
            if name.startswith("lean_sdd_templates/")
        }
        assert installed == set(packaged)
        assert not any(
            name.endswith("/.env") or "__pycache__" in name for name in names
        )
        for name, content in packaged.items():
            assert bundle.read(f"lean_sdd_templates/{name}") == content
        zipped = resolve_bundle(
            resource_root=zipfile.Path(bundle, "lean_sdd_templates/")
        )
        assert zipped == composed
        assert (
            resolve_bundle(
                ("python", "typescript"),
                registry=typescript_registry,
                resource_root=zipfile.Path(bundle, "lean_sdd_templates/"),
            )
            == typescript_bundle
        )
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            if member.isfile():
                stream = bundle.extractfile(member)
                assert stream is not None
                with stream:
                    assert sentinel not in stream.read(), member.name
        assert any(name.endswith("/.agents/.env.example") for name in bundle.getnames())
        assert not any(name.endswith("/.env") for name in bundle.getnames())
        assert not any(
            name.endswith("/.agents/github-workflow-acceptance.md")
            for name in bundle.getnames()
        )
    rebuilt = tmp_path / "rebuilt"
    run(
        [
            "uv",
            "build",
            "--wheel",
            "--offline",
            str(archive),
            "--out-dir",
            str(rebuilt),
        ],
        tmp_path,
        env,
    )
    with zipfile.ZipFile(next(rebuilt.glob("*.whl"))) as bundle:
        for name, content in packaged.items():
            assert bundle.read(f"lean_sdd_templates/{name}") == content
        assert (
            resolve_bundle(resource_root=zipfile.Path(bundle, "lean_sdd_templates/"))
            == composed
        )
        assert (
            resolve_bundle(
                ("python", "typescript"),
                registry=typescript_registry,
                resource_root=zipfile.Path(bundle, "lean_sdd_templates/"),
            )
            == typescript_bundle
        )
    selected_wheel = wheel if artifact == "wheel" else next(rebuilt.glob("*.whl"))
    run(
        [
            "uv",
            "tool",
            "install",
            "--offline",
            "--python",
            sys.executable,
            str(selected_wheel),
        ],
        tmp_path,
        env,
    )
    executable = tmp_path / "bin" / ("lean-sdd.exe" if os.name == "nt" else "lean-sdd")
    python = (
        tmp_path
        / "tools"
        / "lean-sdd-cli"
        / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    typescript_probe = run(
        [
            str(python),
            "-c",
            (
                "import json; "
                "from lean_sdd.profiles import PYTHON, TYPESCRIPT, ProfileRegistry; "
                "from lean_sdd.templates import resolve_bundle, template_manifest; "
                "bundle = resolve_bundle(('python','typescript'), "
                "registry=ProfileRegistry((PYTHON,TYPESCRIPT))); "
                "print(json.dumps(template_manifest(bundle.payload)))"
            ),
        ],
        tmp_path,
        env,
    )
    assert json.loads(typescript_probe.stdout) == template_manifest(
        typescript_bundle.payload
    )
    probe = run(
        [
            str(python),
            "-c",
            (
                "import json; "
                "from lean_sdd.templates import resolve_bundle, template_manifest; "
                "bundle = resolve_bundle(); "
                "print(json.dumps({'profiles':bundle.profiles, "
                "'manifest':template_manifest(bundle.payload)}))"
            ),
        ],
        tmp_path,
        env,
    )
    assert json.loads(probe.stdout) == {
        "profiles": ["python"],
        "manifest": template_manifest(composed.payload),
    }
    assert (
        f"lean-sdd {package_version()}"
        in run([str(executable), "--version"], tmp_path, env).stdout
    )
    dry_target = tmp_path / "dry project"
    dry = run([str(executable), "init", str(dry_target), "--dry-run"], tmp_path, env)
    assert "Profiles: python" in dry.stdout
    assert not dry_target.exists()
    unsupported = run(
        [str(executable), "init", str(dry_target), "--language", "rust"],
        tmp_path,
        env,
        expected=1,
    )
    assert "Unsupported profile" in unsupported.stderr
    assert not dry_target.exists()
    typescript_target = tmp_path / "typescript project"
    dry_typescript = run(
        [
            str(executable),
            "init",
            str(typescript_target),
            "--language",
            "typescript",
            "--dry-run",
        ],
        tmp_path,
        env,
    )
    assert "Profiles: typescript" in dry_typescript.stdout
    assert not typescript_target.exists()
    run(
        [str(executable), "init", str(typescript_target), "--language", "typescript"],
        tmp_path,
        env,
    )
    typescript_state = json.loads((typescript_target / STATE_PATH).read_text())
    assert typescript_state["profiles"] == ["typescript"]
    assert (typescript_target / ".agents/standards/typescript.md").is_file()
    assert not (typescript_target / ".agents/standards/python.md").exists()
    assert not (typescript_target / "package.json").exists()
    assert not (typescript_target / "src").exists()
    typescript_record = (typescript_target / STATE_PATH).read_bytes()
    run([str(executable), "init", str(typescript_target)], tmp_path, env)
    assert (typescript_target / STATE_PATH).read_bytes() == typescript_record
    missing_setup = run(
        [str(executable), "validate", str(typescript_target)], tmp_path, env, expected=1
    )
    assert "Missing package.json" in missing_setup.stderr
    target = tmp_path / "fresh project"
    run([str(executable), "init", str(target)], tmp_path, env)
    assert (target / STATE_PATH).is_file()
    for name, content in composed.payload.items():
        assert (target / name).read_bytes() == content
    state = json.loads((target / STATE_PATH).read_text(encoding="utf-8"))
    assert state["schema_version"] == 2
    assert state["profiles"] == ["python"]
    assert state["configuration_mode"] == "configured"
    assert (
        state["files"]["lean-sdd.toml"]
        == hashlib.sha256((target / "lean-sdd.toml").read_bytes()).hexdigest()
    )
    assert (
        run([str(executable), "languages"], tmp_path, env).stdout
        == "python: Python\ntypescript: TypeScript\n"
    )
    repeated = run(
        [str(executable), "init", str(target), "--language", "python"], tmp_path, env
    )
    assert "Profiles: python" in repeated.stdout
    assert "Created " not in repeated.stdout
    # Doctor stays local and its diagnostics remain usable in an isolated install.
    result = subprocess.run(
        [str(executable), "doctor", str(target)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Local checks only" in result.stdout
    assert "PASS: Installation record matches current release" in result.stdout
    assert not result.stderr
    assert "Component root (.), profile python: No pyproject.toml" in result.stdout

    if sys.platform == "linux":
        # The installed validator runs only an inert uv stand-in, never project
        # dependency installation or live services during the distribution test.
        blocked = run(
            [str(executable), "validate", str(target)], tmp_path, env, expected=1
        )
        assert blocked.stdout.count("not-run:") == 4
        (target / "pyproject.toml").write_text(
            '[project]\nname="smoke"\n', encoding="utf-8"
        )
        (target / "uv.lock").write_text("version=1\n", encoding="utf-8")
        validation_bin = tmp_path / "validation-bin"
        validation_bin.mkdir()
        validation_log = tmp_path / "validation-events.jsonl"
        uv_fixture = validation_bin / "uv"
        uv_fixture.write_text(
            f"#!{sys.executable}\nimport json,sys,os\n"
            f"with open({str(validation_log)!r},'a',encoding='utf-8') as f:\n"
            " f.write(json.dumps([os.getcwd(),sys.argv[1:]])+'\\n')\n"
            "sys.exit(7 if os.environ.get('FAIL_SHARED') "
            "and 'tests/integration' in sys.argv else 0)\n",
            encoding="utf-8",
        )
        uv_fixture.chmod(0o755)
        validation_env = dict(
            env, PATH=str(validation_bin) + os.pathsep + env.get("PATH", "")
        )
        validation_result = run(
            [str(executable), "validate", str(target)], tmp_path, validation_env
        )
        assert validation_result.stdout.count("passed:") == 4
        events = [
            json.loads(line)
            for line in validation_log.read_text(encoding="utf-8").splitlines()
        ]
        assert events == [
            [str(target), argv]
            for argv in (
                ["run", "ruff", "format", "--check", "."],
                ["run", "ruff", "check", "."],
                ["run", "pytest"],
                ["run", "mypy", "."],
            )
        ]

    # Profile diagnostics also work from an isolated wheel for edited mappings.
    examples = re.findall(
        r"```toml\n(.*?)```",
        (target / ".agents/docs/configuration.md").read_text(encoding="utf-8"),
        re.DOTALL,
    )
    (target / "lean-sdd.toml").write_text(examples[1], encoding="utf-8")
    for component in ("api", "worker"):
        (target / "src" / component).mkdir(parents=True)
    (target / "src/api/pyproject.toml").write_text(
        '[project]\nname="api"\n', encoding="utf-8"
    )
    (target / "src/api/uv.lock").write_text("", encoding="utf-8")
    (target / "pyproject.toml").write_text("[broken", encoding="utf-8")
    component_result = run([str(executable), "doctor", str(target)], tmp_path, env)
    assert (
        "Component api (src/api), profile python: Python project metadata is present"
        in component_result.stdout
    )
    assert (
        "Component worker (src/worker), profile python: No pyproject.toml"
        in component_result.stdout
    )
    assert "Locally modified template: 'lean-sdd.toml'" in component_result.stdout
    assert "Component root" not in component_result.stdout

    record_before = (target / STATE_PATH).read_bytes()
    if sys.platform == "linux":
        (target / "src/worker/pyproject.toml").write_text(
            '[project]\nname="worker"\n', encoding="utf-8"
        )
        (target / "src/worker/uv.lock").write_text("version=1\n", encoding="utf-8")
        validation_log.unlink()
        multi = run(
            [str(executable), "validate", str(target)], tmp_path, validation_env
        )
        assert multi.stdout.count("passed:") == 9
        events = [json.loads(line) for line in validation_log.read_text().splitlines()]
        assert [event[0] for event in events] == (
            [str(target / "src/api")] * 4
            + [str(target)]
            + [str(target / "src/worker")] * 4
        )
        assert events[4][1] == ["run", "pytest", "tests/integration"]
        failure = run(
            [str(executable), "validate", str(target)],
            tmp_path,
            dict(validation_env, FAIL_SHARED="1"),
            expected=1,
        )
        assert failure.stdout.count("failed:") == 1
        assert failure.stdout.count("passed:") == 8
        assert "shared-contracts" in failure.stdout
    run([str(executable), "init", str(target)], tmp_path, env)
    assert (target / STATE_PATH).read_bytes() == record_before
    # A pre-existing example mapping is user-owned, including formatting/mtime.
    user_target = tmp_path / "user-owned"
    user_target.mkdir()
    user_config = user_target / "lean-sdd.toml"
    user_config.write_text("# user-owned\n" + examples[0], encoding="utf-8")
    original_config = (user_config.read_bytes(), user_config.stat().st_mtime_ns)
    run([str(executable), "init", str(user_target)], tmp_path, env)
    assert (user_config.read_bytes(), user_config.stat().st_mtime_ns) == original_config
    user_record = json.loads((user_target / STATE_PATH).read_text())
    assert "lean-sdd.toml" not in user_record["files"]

    if sys.platform == "linux":
        (user_target / "pyproject.toml").write_text(
            '[project]\nname="documented-root"\n', encoding="utf-8"
        )
        (user_target / "uv.lock").write_text("version=1\n", encoding="utf-8")
        documented_root = run(
            [str(executable), "validate", str(user_target)], tmp_path, validation_env
        )
        assert documented_root.stdout.count("passed:") == 4
        assert (
            user_config.read_bytes(),
            user_config.stat().st_mtime_ns,
        ) == original_config

    # Profile catalog compatibility must not mask original integrity failures.
    unknown_record = json.loads(record_before)
    unknown_record["profiles"] = ["retired"]
    (target / STATE_PATH).write_text(json.dumps(unknown_record), encoding="utf-8")
    (target / "AGENTS.md").write_text("Local customization\n", encoding="utf-8")
    (target / ".agents/.env.example").unlink()
    unknown = run([str(executable), "doctor", str(target)], tmp_path, env, expected=1)
    assert "Locally modified template: 'AGENTS.md'" in unknown.stdout
    assert "Missing installed template: '.agents/.env.example'" in unknown.stdout
    assert "retired" in unknown.stdout
    if sys.platform == "linux":
        run(
            [str(executable), "validate", str(target)],
            tmp_path,
            validation_env,
            expected=1,
        )

    # A historical fixture requires no historical release or network access.
    older = tmp_path / "older project"
    old_payload = payload.copy()
    old_payload.pop(".agents/.env.example")
    old_payload[".agents/README.md"] = b"Historical instructions\n"
    old_payload[".agents/retired.md"] = b"Retired template\n"
    for name, content in old_payload.items():
        path = older / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (older / STATE_PATH).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "template_version": "0.0.0",
                "files": {
                    name: hashlib.sha256(content).hexdigest()
                    for name, content in old_payload.items()
                },
            }
        ),
        encoding="utf-8",
    )
    before = {
        name: (
            (older / name).read_bytes(),
            (older / name).stat().st_mtime_ns,
            (older / name).stat().st_ctime_ns,
        )
        for name in [*old_payload, STATE_PATH]
    }
    refused = run([str(executable), "init", str(older)], tmp_path, env, expected=1)
    assert "no migration" in refused.stderr
    for _ in range(2):
        result = run([str(executable), "doctor", str(older)], tmp_path, env)
        assert (
            "WARN: Installation was created with another template release"
            in result.stdout
        )
        assert "Recorded template version '0.0.0'" in result.stdout
        assert f"current CLI version {package_version()!r}" in result.stdout
        assert (
            "Templates added in current release: '.agents/.env.example'"
            in result.stdout
        )
        assert (
            "Templates removed in current release: '.agents/retired.md'"
            in result.stdout
        )
        assert "Template reference hashes changed: '.agents/README.md'" in result.stdout
        assert "All recorded templates match their original content" in result.stdout
        assert "Locally modified" not in result.stdout
        assert not result.stderr
    assert before == {
        name: (
            (older / name).read_bytes(),
            (older / name).stat().st_mtime_ns,
            (older / name).stat().st_ctime_ns,
        )
        for name in before
    }
    assert {
        path.relative_to(older).as_posix()
        for path in older.rglob("*")
        if path.is_file()
    } == set(before)
    (older / ".agents/README.md").write_bytes(payload[".agents/README.md"])
    result = run([str(executable), "doctor", str(older)], tmp_path, env)
    assert "WARN: Locally modified template: '.agents/README.md'" in result.stdout
