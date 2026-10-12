"""Execute documented uv invocations with dummy credentials and inert skill probes."""

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from lean_sdd.installer import initialize
from lean_sdd.templates import template_files

# These are explicit caller inputs, not values selected from dotenv configuration.
ARGUMENTS = {
    "OWNER": "selected-owner",
    "REPO": "selected-repo",
    "ISSUE_NUMBER": "17",
    "WORKING_BRANCH": "dev",
    "QUERY": "repo:selected-owner/selected-repo",
    "TITLE": "Preserve literal $(touch argument-command-ran)",
    "BODY": "A multiline plan\nwith quotes: 'single' and \"double\".",
    "COMMENT": "Checkpoint\nwith literal $variables and `backticks`.",
}

INVOCATIONS = [
    ("list-repositories", "list-repositories", ["QUERY"]),
    ("create-issue", "create-issue", ["OWNER", "REPO", "TITLE", "BODY"]),
    ("get-issue", "get-issue", ["OWNER", "REPO", "ISSUE_NUMBER"]),
    (
        "git-change-workflow",
        "prepare-change-branch",
        ["OWNER", "REPO", "ISSUE_NUMBER", "WORKING_BRANCH"],
    ),
    ("update-issue", "comment-issue", ["OWNER", "REPO", "ISSUE_NUMBER", "COMMENT"]),
    ("update-issue", "close-issue", ["OWNER", "REPO", "ISSUE_NUMBER"]),
    ("finalize-implementation", "publish-implementation", ["PUBLICATION_INPUT"]),
    ("finalize-implementation", "merge-implementation", ["RETAINED_STATE"]),
]


def invocation(skill: str, script: str) -> str:
    """Use the actual first invocation example for this entry point."""
    document = template_files()[f".agents/skills/{skill}/SKILL.md"].decode()
    entrypoint = f".agents/skills/{skill}/scripts/{script}.sh"
    for match in re.finditer(r"```bash\n(.*?)\n```", document, re.DOTALL):
        block = match.group(1)
        if f"bash {entrypoint}" in block:
            return block
    raise AssertionError(f"No documented invocation for {entrypoint}")


def prepare(
    tmp_path: Path, skill: str, script: str
) -> tuple[Path, dict[str, str], Path]:
    """Install templates and replace just the invoked skill with an inert probe."""
    target = tmp_path / "project with spaces"
    initialize(target)
    # --no-project must prevent this invalid application metadata from being read.
    (target / "pyproject.toml").write_text("[invalid TOML", encoding="utf-8")
    dotenv = target / ".agents/.env"
    dotenv.write_text(
        "export GITHUB_TOKEN='dummy-file-token'\n"
        "GITHUB_MCP_URL=https://api.githubcopilot.com/mcp/\n"
        "OWNER=dotenv-must-not-select-the-owner\n"
        "REPO=dotenv-must-not-select-the-repository\n"
        "WORKING_BRANCH=dotenv-must-not-select-the-base\n"
        "LITERAL_VALUE='$(touch dotenv-command-ran)'\n",
        encoding="utf-8",
    )
    trace = tmp_path / "probe.json"
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import json, os, pathlib, sys\n"
        "result = {\n"
        "    'arguments': sys.argv[1:],\n"
        "    'token_matches': os.environ.get('GITHUB_TOKEN') == "
        "os.environ['EXPECTED_DUMMY_TOKEN'],\n"
        "    'endpoint_matches': os.environ.get('GITHUB_MCP_URL') == "
        "'https://api.githubcopilot.com/mcp/',\n"
        "    'dotenv_is_data': os.environ.get('LITERAL_VALUE') == "
        "'$(touch dotenv-command-ran)',\n"
        "}\n"
        "pathlib.Path(os.environ['PROBE_TRACE']).write_text(json.dumps(result))\n",
        encoding="utf-8",
    )
    entrypoint = target / f".agents/skills/{skill}/scripts/{script}.sh"
    entrypoint.write_text(
        f'exec {shlex.quote(sys.executable)} {shlex.quote(str(probe))} "$@"\n',
        encoding="utf-8",
    )
    # Do not pass real credentials or shell startup settings into test processes.
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "TMPDIR", "TEMP", "SYSTEMROOT", "UV_CACHE_DIR"}
    }
    environment.update(ARGUMENTS)
    environment.update(
        {
            "UV_OFFLINE": "1",
            "UV_PYTHON_DOWNLOADS": "never",
            "UV_PYTHON": sys.executable,
            "PROBE_TRACE": str(trace),
            "EXPECTED_DUMMY_TOKEN": "dummy-file-token",
            "PUBLICATION_INPUT": str(tmp_path / "publication input.json"),
            "RETAINED_STATE": str(tmp_path / "retained state.json"),
            "FINALIZATION_RESULT": str(tmp_path / "finalization result.json"),
        }
    )
    return target, environment, trace


@pytest.mark.parametrize(("skill", "script", "arguments"), INVOCATIONS)
def test_documented_invocations_load_env_and_preserve_arguments(
    tmp_path: Path, skill: str, script: str, arguments: list[str]
) -> None:
    target, environment, trace = prepare(tmp_path, skill, script)
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-c", invocation(skill, script)],
        cwd=target,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    observed = json.loads(trace.read_text())
    assert observed == {
        "arguments": [environment[name] for name in arguments],
        "token_matches": True,
        "endpoint_matches": True,
        "dotenv_is_data": True,
    }
    assert "dummy-file-token" not in result.stdout + result.stderr
    assert not (target / "dotenv-command-ran").exists()
    assert not (target / "argument-command-ran").exists()
    assert not (target / ".venv").exists()
    assert not (target / "uv.lock").exists()


def test_inherited_credentials_take_precedence(tmp_path: Path) -> None:
    target, environment, trace = prepare(tmp_path, "get-issue", "get-issue")
    environment["GITHUB_TOKEN"] = "dummy-inherited-token"
    environment["EXPECTED_DUMMY_TOKEN"] = "dummy-inherited-token"
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-c", invocation("get-issue", "get-issue")],
        cwd=target,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(trace.read_text())["token_matches"]
    assert "dummy-inherited-token" not in result.stdout + result.stderr


def test_missing_env_file_stops_before_skill_execution(tmp_path: Path) -> None:
    target, environment, trace = prepare(tmp_path, "get-issue", "get-issue")
    (target / ".agents/.env").unlink()
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-c", invocation("get-issue", "get-issue")],
        cwd=target,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode != 0
    assert not trace.exists()
