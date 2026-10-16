"""Read the explicitly bundled, versioned workflow resources."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import version
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import PurePosixPath
from typing import NoReturn

STATE_PATH = ".agents/lean-sdd-install.json"


@dataclass(frozen=True)
class InstallationRecord:
    """Validated original manifest, independent of the current CLI release."""

    schema_version: int
    template_version: str
    files: dict[str, str]


def _safe_template_path(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        bool(path.parts)
        and not path.is_absolute()
        and path.as_posix() == name
        and ".." not in path.parts
        and not any(character in name for character in "\\:")
        and not any(ord(character) < 32 or ord(character) == 127 for character in name)
        and not any(0xD800 <= ord(character) <= 0xDFFF for character in name)
        # Windows device names are unsafe even when inspecting a record on POSIX.
        and not any(
            re.fullmatch(
                r"CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|(?:COM|LPT)[1-9¹²³]",
                part.partition(".")[0].rstrip(" ").upper(),
            )
            for part in path.parts
        )
        and all(not part.endswith((".", " ")) for part in path.parts)
    )


def _record_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate installation record field: {key!r}.")
        result[key] = value
    return result


def _invalid_json_constant(value: str) -> NoReturn:
    raise ValueError(f"Installation record is not valid JSON: {value}.")


def parse_installation_state(content: str) -> InstallationRecord:
    """Validate schema v1 JSON without accessing recorded paths or releases.

    Raises:
        ValueError: The record is malformed, unsupported, or contains unsafe paths.

    Additional fields are ignored. Hex digests are normalized to lowercase;
    the serialized record is never changed. Filesystem safety is checked by
    the caller before reading each installed file.
    """
    try:
        state: object = json.loads(
            content,
            object_pairs_hook=_record_object,
            parse_constant=_invalid_json_constant,
        )
    except (json.JSONDecodeError, RecursionError) as error:
        raise ValueError("Installation record is not valid JSON.") from error
    if not isinstance(state, dict):
        raise ValueError("Installation record must be a JSON object.")
    schema = state.get("schema_version")
    if type(schema) is not int:
        raise ValueError("Installation record schema_version must be an integer.")
    if schema != 1:
        raise ValueError(f"Unsupported installation record schema_version: {schema}.")
    template_version = state.get("template_version")
    if not isinstance(template_version, str) or not template_version.strip():
        raise ValueError("Installation record template_version must be nonempty text.")
    manifest = state.get("files")
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError("Installation record files must be a nonempty mapping.")
    validated: dict[str, str] = {}
    for name, digest in manifest.items():
        if not _safe_template_path(name):
            raise ValueError(f"Unsafe installation record path: {name!r}.")
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None
        ):
            raise ValueError(f"Invalid SHA-256 digest for recorded template: {name!r}.")
        validated[name] = digest.lower()
    return InstallationRecord(schema, template_version, validated)


def template_manifest(payload: Mapping[str, bytes]) -> dict[str, str]:
    """Return the SHA-256 manifest for a template bundle, sorted by path."""
    return {
        name: hashlib.sha256(content).hexdigest()
        for name, content in sorted(payload.items())
    }


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
        if not _safe_template_path(name):
            raise ValueError("Installed template bundle contains an unsafe path.")
    return payload


def installation_state(payload: dict[str, bytes]) -> bytes:
    """Describe the original installed templates, without machine-local values."""
    state = {
        "schema_version": 1,
        "template_version": package_version(),
        "files": template_manifest(payload),
    }
    return (json.dumps(state, indent=2, sort_keys=True) + "\n").encode("utf-8")
