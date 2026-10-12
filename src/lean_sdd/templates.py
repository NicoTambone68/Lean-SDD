"""Read the explicitly bundled, versioned workflow resources."""

import hashlib
import json
from importlib.metadata import version
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import PurePosixPath

STATE_PATH = ".agents/lean-sdd-install.json"


def package_version() -> str:
    """Return the version of the installed distribution."""
    return version("lean-sdd-cli")


def _read_tree(root: Traversable, prefix: str = "") -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for entry in sorted(root.iterdir(), key=lambda child: child.name):
        name = f"{prefix}{entry.name}"
        if entry.is_dir():
            result.update(_read_tree(entry, f"{name}/"))
        elif entry.is_file():
            result[name] = entry.read_bytes()
    return result


def template_files() -> dict[str, bytes]:
    """Read installed resources, including dotfiles, without locating a checkout."""
    payload = _read_tree(files("lean_sdd_templates"))
    required = {"AGENTS.md", "CONSTITUTION.md", "CODING_STANDARDS.md"}
    if not required.issubset(payload) or STATE_PATH in payload:
        raise ValueError("Installed template bundle is incomplete or invalid.")
    for name in payload:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError("Installed template bundle contains an unsafe path.")
    return payload


def installation_state(payload: dict[str, bytes]) -> bytes:
    """Describe the original installed templates, without machine-local values."""
    state = {
        "schema_version": 1,
        "template_version": package_version(),
        "files": {
            name: hashlib.sha256(content).hexdigest()
            for name, content in sorted(payload.items())
        },
    }
    return (json.dumps(state, indent=2, sort_keys=True) + "\n").encode("utf-8")
