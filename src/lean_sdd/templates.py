"""Read the explicitly bundled, versioned workflow resources."""

import hashlib
import json
import posixpath
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib.metadata import version
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import NoReturn

from lean_sdd.configuration import InstallationIdentity
from lean_sdd.paths import safe_relative_path as _safe_template_path
from lean_sdd.profiles import BUILTIN_PROFILES, ProfileRegistry

STATE_PATH = ".agents/lean-sdd-install.json"
CORE_SKILLS = frozenset(
    {
        "create-issue",
        "finalize-implementation",
        "get-issue",
        "git-change-workflow",
        "list-repositories",
        "update-issue",
    }
)
CORE_FILES = frozenset(
    {
        "AGENTS.md",
        "CONSTITUTION.md",
        "CODING_STANDARDS.md",
        ".agents/README.md",
        ".agents/.env.example",
        ".agents/.gitignore",
        ".agents/github-mcp-contract.md",
        ".agents/github-issue-contract.md",
        ".agents/github-workflow-acceptance.md",
    }
    | {f".agents/skills/{skill}/SKILL.md" for skill in CORE_SKILLS}
    | {
        f".agents/lib/{name}.sh"
        for name in (
            "github-identity",
            "github-issues",
            "github-mcp",
            "github-pr",
            "mcp",
        )
    }
    | {
        f".agents/skills/{skill}/scripts/{script}.sh"
        for skill, script in (
            ("create-issue", "create-issue"),
            ("get-issue", "get-issue"),
            ("git-change-workflow", "prepare-change-branch"),
            ("list-repositories", "list-repositories"),
            ("update-issue", "comment-issue"),
            ("update-issue", "close-issue"),
            ("finalize-implementation", "publish-implementation"),
            ("finalize-implementation", "merge-implementation"),
        )
    }
    | {".agents/skills/finalize-implementation/references/phase-contracts.md"}
)
MAX_RESOURCE_BYTES = 1024 * 1024
MAX_BUNDLE_BYTES = 8 * MAX_RESOURCE_BYTES
MAX_RESOURCE_FILES = 512
PROFILE_REFERENCES = b"{{profile_standards}}"


@dataclass(frozen=True)
class ResolvedBundle:
    """Release-versioned profile selection and immutable destination bytes."""

    template_version: str
    profiles: tuple[str, ...]
    payload: Mapping[str, bytes]


@dataclass(frozen=True)
class InstallationRecord:
    """Validated original manifest, independent of the current CLI release."""

    schema_version: int
    template_version: str
    files: dict[str, str]
    identity: InstallationIdentity = InstallationIdentity(("python",), "legacy-python")


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
    """Validate schema v1/v2 JSON without accessing recorded paths or releases.

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
    if schema not in (1, 2):
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
    identity = InstallationIdentity(("python",), "legacy-python")
    if schema == 2:
        profiles = state.get("profiles")
        mode = state.get("configuration_mode")
        if not isinstance(profiles, list):
            raise ValueError("Installation record profiles must be a nonempty array.")
        if mode not in ("legacy-python", "configured"):
            raise ValueError("Invalid installed configuration mode.")
        identity = InstallationIdentity(tuple(profiles), mode)
        if STATE_PATH in validated:
            raise ValueError("Installation record cannot hash itself.")
        if "lean-sdd.toml" in validated and mode != "configured":
            raise ValueError("Managed configuration requires configured mode.")
        folded = {name.casefold() for name in validated}
        if len(folded) != len(validated) or any(
            str(parent) in folded
            for name in folded
            for parent in PurePosixPath(name).parents
        ):
            raise ValueError("Installation record paths collide.")
    return InstallationRecord(schema, template_version, validated, identity)


def template_manifest(payload: Mapping[str, bytes]) -> dict[str, str]:
    """Return the SHA-256 manifest for a template bundle, sorted by path."""
    return {
        name: hashlib.sha256(content).hexdigest()
        for name, content in sorted(payload.items())
    }


def package_version() -> str:
    """Return the version of the installed distribution."""
    return version("lean-sdd-cli")


def _asset_path(name: str) -> bool:
    if not _safe_template_path(name) or name == STATE_PATH:
        return False
    return all(
        part not in {".git", ".venv", "__pycache__", ".env"}
        and not (part.startswith(".env.") and part != ".env.example")
        and not part.endswith((".pyc", ".pyo"))
        for part in PurePosixPath(name).parts
    )


def _read_tree(root: Traversable) -> dict[str, bytes]:
    """Read bounded explicit resource trees; never follow filesystem symlinks."""
    result: dict[str, bytes] = {}
    pending = [(root, "", 0)]
    total = 0
    visited = 0
    try:
        while pending:
            directory, prefix, depth = pending.pop()
            if depth > 32 or (isinstance(directory, Path) and directory.is_symlink()):
                raise ValueError("Unsafe or excessively nested resource directory.")
            if not directory.is_dir():
                raise ValueError("Required resource directory is missing.")
            for entry in directory.iterdir():
                visited += 1
                if visited > MAX_RESOURCE_FILES:
                    raise ValueError("Resource tree has too many entries.")
                name = f"{prefix}{entry.name}"
                if not _asset_path(name) or (
                    isinstance(entry, Path) and entry.is_symlink()
                ):
                    raise ValueError("Resource tree contains an unsafe path.")
                if entry.is_dir():
                    pending.append((entry, f"{name}/", depth + 1))
                elif entry.is_file():
                    with entry.open("rb") as stream:
                        content = stream.read(MAX_RESOURCE_BYTES + 1)
                    total += len(content)
                    if len(content) > MAX_RESOURCE_BYTES or total > MAX_BUNDLE_BYTES:
                        raise ValueError("Resource tree exceeds its byte limit.")
                    result[name] = content
                else:
                    raise ValueError("Resource tree contains a non-regular entry.")
    except OSError as error:
        raise ValueError("Cannot read packaged resource tree.") from error
    return dict(sorted(result.items()))


def _validate_payload(payload: Mapping[str, bytes]) -> None:
    if len(payload) > MAX_RESOURCE_FILES:
        raise ValueError("Bundle has too many files.")
    paths: set[str] = set()
    directories: set[str] = set()
    total = 0
    for name, content in sorted(payload.items()):
        if not _asset_path(name):
            raise ValueError("Bundle contains an unsafe destination.")
        if not isinstance(content, bytes) or len(content) > MAX_RESOURCE_BYTES:
            raise ValueError("Bundle files must be bounded bytes.")
        total += len(content)
        if total > MAX_BUNDLE_BYTES:
            raise ValueError("Bundle exceeds its byte limit.")
        folded = name.casefold()
        parents = {str(p) for p in PurePosixPath(folded).parents if str(p) != "."}
        if folded in paths or folded in directories or parents & paths:
            raise ValueError("Bundle has a path collision or file/directory conflict.")
        paths.add(folded)
        directories.update(parents)


def _validate_bundle(payload: Mapping[str, bytes], skills: frozenset[str]) -> None:
    _validate_payload(payload)
    if not CORE_FILES.issubset(payload) or any(
        not payload[p].strip() for p in CORE_FILES
    ):
        raise ValueError("Bundle is missing required common files.")
    actual = {
        p.split("/")[2]
        for p in payload
        if re.fullmatch(r"\.agents/skills/[^/]+/SKILL\.md", p)
    }
    if actual != skills:
        raise ValueError("Bundle must contain the core skills plus declared additions.")
    if any(not payload[f".agents/skills/{skill}/SKILL.md"].strip() for skill in skills):
        raise ValueError("Declared skill instructions must be nonempty.")
    for name, content in payload.items():
        if name.startswith(".agents/skills/") and name.split("/")[2] not in skills:
            raise ValueError("Bundle contains an undeclared skill resource.")
        if not name.endswith(".md"):
            continue
        try:
            document = content.decode("utf-8")
        except UnicodeError as error:
            raise ValueError("Bundle documentation must be UTF-8.") from error
        for link in re.findall(r"\]\(([^)]+)\)", document):
            if "://" in link or link.startswith("#"):
                continue
            target = posixpath.normpath(
                posixpath.join(posixpath.dirname(name), link.split("#")[0])
            )
            if target not in payload:
                raise ValueError(f"Unresolved documentation link in {name}.")


def compose_bundle(
    common: Mapping[str, bytes],
    contributions: Mapping[str, Mapping[str, bytes]],
    *,
    template_version: str,
    registry: ProfileRegistry = BUILTIN_PROFILES,
) -> ResolvedBundle:
    """Compose destination bytes without I/O, execution, or profile overrides.

    Contributions must exactly match each selected profile's resource metadata.
    All collisions (even identical content) fail. The only shared rendering is
    replacing one fixed standards-reference marker with selected profile links.
    Natural-language rule compatibility still requires author review.
    """
    if (
        not contributions
        or not isinstance(template_version, str)
        or not template_version.strip()
    ):
        raise ValueError("Bundle requires profiles and a nonempty release version.")
    _validate_bundle(common, CORE_SKILLS)
    selected = tuple(sorted(contributions))
    payload = dict(common)
    skills = set(CORE_SKILLS)
    for profile_id in selected:
        profile = registry.get(profile_id)
        contribution = contributions[profile_id]
        _validate_payload(contribution)
        expected = {resource.destination for resource in profile.resources}
        if (
            not expected
            or set(contribution) != expected
            or profile.standards_path not in expected
        ):
            raise ValueError(
                f"Profile {profile_id} has missing or undeclared resources."
            )
        if not contribution[profile.standards_path].strip():
            raise ValueError(f"Profile {profile_id} standards must be nonempty.")
        if skills.intersection(profile.skills):
            raise ValueError("Profile skills collide with common or selected skills.")
        declared = frozenset(profile.skills)
        actual = {
            p.split("/")[2]
            for p in contribution
            if re.fullmatch(r"\.agents/skills/[^/]+/SKILL\.md", p)
        }
        if actual != declared:
            raise ValueError("Profile skill declarations do not match their resources.")
        for destination, content in contribution.items():
            if destination in payload:
                raise ValueError(
                    "Profile resource collision; replacements are forbidden."
                )
            if destination.startswith(".agents/lib/"):
                raise ValueError("Profiles cannot contribute shared workflow helpers.")
            if (
                destination.startswith(".agents/skills/")
                and destination.split("/")[2] not in declared
            ):
                raise ValueError("Profile resource belongs to an undeclared skill.")
            payload[destination] = content
        skills.update(declared)
    shared = payload.get("CODING_STANDARDS.md", b"")
    if shared.count(PROFILE_REFERENCES) != 1:
        raise ValueError(
            "Shared standards require exactly one profile-reference marker."
        )
    links = "\n".join(
        f"- Read [{registry.get(p).standards_path}]({registry.get(p).standards_path})."
        for p in selected
    ).encode("utf-8")
    payload["CODING_STANDARDS.md"] = shared.replace(PROFILE_REFERENCES, links)
    _validate_bundle(payload, frozenset(skills))
    return ResolvedBundle(
        template_version, selected, MappingProxyType(dict(sorted(payload.items())))
    )


def _python_standards(content: bytes) -> bytes:
    """Relocate only the canonical root-document links; preserve every rule byte."""
    for filename in ("CONSTITUTION.md", "AGENTS.md"):
        old = f"]({filename})".encode()
        if content.count(old) != 1:
            raise ValueError("Python standards have unexpected root-document links.")
        content = content.replace(old, f"](../../{filename})".encode())
    return content


def resolve_bundle(
    selected_profiles: Iterable[str] = ("python",),
    *,
    registry: ProfileRegistry = BUILTIN_PROFILES,
    resource_root: Traversable | None = None,
) -> ResolvedBundle:
    """Read bundled resources and resolve a sorted profile union without writes.

    resource_root is an explicit local test/resource adapter, never a module name
    or project-configured plugin. Profiles are versioned with the CLI release.
    """
    if isinstance(selected_profiles, str):
        raise ValueError("Select profiles as a collection, not a string.")
    selected = tuple(sorted(set(selected_profiles)))
    if not selected:
        raise ValueError("At least one profile must be selected.")
    for profile_id in selected:
        registry.get(profile_id)
    root = resource_root if resource_root is not None else files("lean_sdd_templates")
    if isinstance(root, Path) and root.is_symlink():
        raise ValueError("Resource root must not be a symlink.")
    common = _read_tree(root.joinpath("common"))
    contributions: dict[str, dict[str, bytes]] = {}
    profile_root = root.joinpath("profiles")
    if isinstance(profile_root, Path) and profile_root.is_symlink():
        raise ValueError("Profile resource directory must not be a symlink.")
    for profile_id in selected:
        profile = registry.get(profile_id)
        resources = _read_tree(profile_root.joinpath(profile_id))
        if set(resources) != {r.source for r in profile.resources}:
            raise ValueError(
                f"Profile {profile_id} resource sources do not match metadata."
            )
        contribution = {r.destination: resources[r.source] for r in profile.resources}
        if profile_id == "python":
            contribution[profile.standards_path] = _python_standards(
                contribution[profile.standards_path]
            )
        contributions[profile_id] = contribution
    return compose_bundle(
        common, contributions, template_version=package_version(), registry=registry
    )


def template_files() -> dict[str, bytes]:
    """Return the unchanged legacy Python payload used by init and doctor.

    Both APIs reuse the same canonical common assets and Python standards source.
    This compatibility adapter selects the original root Python standards instead
    of rendering shared/profile standards. It does not change installation records.
    """
    root = files("lean_sdd_templates")
    payload = _read_tree(root.joinpath("common"))
    python = _read_tree(root.joinpath("profiles", "python"))
    if set(python) != {"standards.md"}:
        raise ValueError("Legacy Python standards source is missing or invalid.")
    payload["CODING_STANDARDS.md"] = python["standards.md"]
    _validate_bundle(payload, CORE_SKILLS)
    return dict(sorted(payload.items()))


def installation_state(payload: dict[str, bytes]) -> bytes:
    """Describe the original installed templates, without machine-local values."""
    state = {
        "schema_version": 1,
        "template_version": package_version(),
        "files": template_manifest(payload),
    }
    return (json.dumps(state, indent=2, sort_keys=True) + "\n").encode("utf-8")


def profile_installation_state(
    payload: Mapping[str, bytes],
    *,
    template_version: str,
    identity: InstallationIdentity,
) -> bytes:
    """Serialize original bytes and catalog-independent identity as schema 2."""
    state = {
        "schema_version": 2,
        "template_version": template_version,
        "profiles": identity.profiles,
        "configuration_mode": identity.configuration_mode,
        "files": template_manifest(payload),
    }
    content = json.dumps(state, indent=2, sort_keys=True) + "\n"
    parse_installation_state(content)
    return content.encode("utf-8")
