"""Verify actual wheels and source archives, including isolated tool installation."""

import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

from lean_sdd.templates import STATE_PATH, package_version, template_files

ROOT = Path(__file__).resolve().parents[1]


def run(
    arguments: list[str], cwd: Path, env: dict[str, str]
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
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def test_bundled_links_resolve_and_scripts_parse(tmp_path: Path) -> None:
    payload = template_files()
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
    assert len([name for name in payload if name.endswith("/SKILL.md")]) == 6


def test_wheel_and_sdist_install_without_checkout(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("VIRTUAL_ENV", None)
    env.pop("GITHUB_TOKEN", None)
    env["GITHUB_MCP_URL"] = "https://api.githubcopilot.com/mcp/"
    env["UV_PYTHON_DOWNLOADS"] = "never"
    env["UV_TOOL_DIR"] = str(tmp_path / "tools")
    env["UV_TOOL_BIN_DIR"] = str(tmp_path / "bin")
    output = tmp_path / "dist"
    run(
        ["uv", "build", "--no-sources", "--offline", "--out-dir", str(output)],
        ROOT,
        env,
    )
    wheel = next(output.glob("*.whl"))
    archive = next(output.glob("*.tar.gz"))
    payload = template_files()
    with zipfile.ZipFile(wheel) as bundle:
        names = bundle.namelist()
        installed = {
            name.removeprefix("lean_sdd_templates/")
            for name in names
            if name.startswith("lean_sdd_templates/")
        }
        assert installed == set(payload)
        assert not any(
            name.endswith("/.env") or "__pycache__" in name for name in names
        )
        for name, content in payload.items():
            assert bundle.read(f"lean_sdd_templates/{name}") == content
    with tarfile.open(archive) as bundle:
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
        for name, content in payload.items():
            assert bundle.read(f"lean_sdd_templates/{name}") == content
    run(
        ["uv", "tool", "install", "--offline", "--python", sys.executable, str(wheel)],
        tmp_path,
        env,
    )
    executable = tmp_path / "bin" / ("lean-sdd.exe" if os.name == "nt" else "lean-sdd")
    assert (
        f"lean-sdd {package_version()}"
        in run([str(executable), "--version"], tmp_path, env).stdout
    )
    target = tmp_path / "fresh project"
    run([str(executable), "init", str(target)], tmp_path, env)
    assert (target / STATE_PATH).is_file()
    for name, content in payload.items():
        assert (target / name).read_bytes() == content
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
