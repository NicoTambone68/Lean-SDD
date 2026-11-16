"""Strict component configuration contracts, without command execution or writes.

The CLI does not consume these APIs yet. See docs/configuration.md for schema 1,
installation identity precedence, and the separate reviewed-execution boundary.
"""

import math
import stat
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from lean_sdd.profiles import (
    BUILTIN_PROFILES,
    PYTHON,
    ProfileRegistry,
    valid_identifier,
)
from lean_sdd.templates import _safe_template_path

CONFIGURATION_NAME = "lean-sdd.toml"
MAX_CONFIGURATION_BYTES = 1024 * 1024
MAX_COMPONENTS = 128
MAX_CHECKS = 1024
DEFAULT_TIMEOUT_SECONDS = 300.0


class ConfigurationError(ValueError):
    """Configuration is invalid or cannot be resolved without guessing."""


@dataclass(frozen=True)
class Component:
    """A component root and its explicitly selected profiles, sorted by ID."""

    id: str
    path: PurePosixPath
    profiles: tuple[str, ...]


@dataclass(frozen=True)
class Check:
    """Reviewed command data; constructing or resolving it grants no execution."""

    name: str
    scope: Literal["component", "project"]
    component: str | None
    profile: str | None
    category: str
    cwd: PurePosixPath
    argv: tuple[str, ...]
    required: bool
    timeout_seconds: float


@dataclass(frozen=True)
class Configuration:
    """Validated schema, with components/checks in deterministic name order."""

    schema_version: int
    components: tuple[Component, ...]
    checks: tuple[Check, ...]

    @property
    def profiles(self) -> tuple[str, ...]:
        """Return the sorted union selected by this mapping."""
        return tuple(sorted({p for c in self.components for p in c.profiles}))


@dataclass(frozen=True)
class InstallationIdentity:
    """Catalog-independent selection from a validated installation record.

    Version 1 maps to (('python',), 'legacy-python'). Version 2 stores these two
    fields alongside template_version and original hashes. It stores no current
    mapping or command copies. Record serialization remains a later increment.
    """

    profiles: tuple[str, ...]
    configuration_mode: Literal["legacy-python", "configured"]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.profiles, tuple)
            or not self.profiles
            or any(
                not isinstance(p, str) or not valid_identifier(p) for p in self.profiles
            )
            or tuple(sorted(set(self.profiles))) != self.profiles
        ):
            raise ConfigurationError("Installed profiles must be sorted unique IDs.")
        if self.configuration_mode not in ("legacy-python", "configured"):
            raise ConfigurationError("Invalid installed configuration mode.")
        if self.configuration_mode == "legacy-python" and self.profiles != ("python",):
            raise ConfigurationError("Legacy Python mode requires only Python.")


@dataclass(frozen=True)
class ResolvedConfiguration:
    """Selected mapping and provenance, without implying readiness or trust."""

    configuration: Configuration
    origin: Literal["explicit", "installed-legacy", "fresh-default", "language"]


def _table(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise ConfigurationError(f"{context}: expected a table.")
    return {k: v for k, v in value.items()}


def _fields(table: dict[str, object], expected: set[str], context: str) -> None:
    if set(table) != expected:
        # Do not print arbitrary keys/values from potentially sensitive input.
        raise ConfigurationError(f"{context}: missing or unknown fields.")


def _identifier(value: object, context: str) -> str:
    if not isinstance(value, str) or not valid_identifier(value):
        raise ConfigurationError(f"{context}: expected a lowercase identifier.")
    return value


def _profile_ids(
    value: object, registry: ProfileRegistry, context: str
) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigurationError(f"{context}: profiles must be a nonempty array.")
    result = tuple(_identifier(p, context) for p in value)
    if len(set(result)) != len(result):
        raise ConfigurationError(f"{context}: duplicate profiles.")
    for profile in result:
        _supported(registry, profile)
    return tuple(sorted(result))


def _supported(registry: ProfileRegistry, profile: str) -> None:
    try:
        registry.get(profile)
    except ValueError as error:
        raise ConfigurationError(str(error)) from error


def _path(value: object, context: str) -> PurePosixPath:
    if not isinstance(value, str) or (value != "." and not _safe_template_path(value)):
        raise ConfigurationError(
            f"{context}: expected a safe normalized relative path."
        )
    return PurePosixPath(value)


def _components(value: object, registry: ProfileRegistry) -> tuple[Component, ...]:
    table = _table(value, "components")
    if not 1 <= len(table) <= MAX_COMPONENTS:
        raise ConfigurationError(f"components: expected 1 to {MAX_COMPONENTS} entries.")
    result: list[Component] = []
    for name, raw in sorted(table.items()):
        component_id = _identifier(name, "component ID")
        context = f"component {component_id}"
        entry = _table(raw, context)
        _fields(entry, {"path", "profiles"}, context)
        path = _path(entry["path"], context)
        if path != PurePosixPath(".") and path.parts[0] != "src":
            raise ConfigurationError(f"{context}: component must be inside root src/.")
        for previous in result:
            # Case-fold for portable overlap detection even on a case-sensitive host.
            left, right = (
                PurePosixPath(str(path).casefold()),
                PurePosixPath(str(previous.path).casefold()),
            )
            if left.is_relative_to(right) or right.is_relative_to(left):
                raise ConfigurationError(f"{context}: overlapping component paths.")
        result.append(
            Component(
                component_id, path, _profile_ids(entry["profiles"], registry, context)
            )
        )
    return tuple(result)


def _check(value: object, components: dict[str, Component]) -> Check:
    entry = _table(value, "check")
    name = _identifier(entry.get("name"), "check name")
    context = f"check {name}"
    scope = entry.get("scope")
    common = {"name", "scope", "category", "cwd", "argv", "required", "timeout_seconds"}
    if scope == "component":
        _fields(entry, common | {"component", "profile"}, context)
        component = _identifier(entry["component"], context)
        profile = _identifier(entry["profile"], context)
        if component not in components or profile not in components[component].profiles:
            raise ConfigurationError(f"{context}: component/profile is not selected.")
    elif scope == "project":
        _fields(entry, common, context)
        component, profile = None, None
    else:
        raise ConfigurationError(f"{context}: scope must be component or project.")
    category = _identifier(entry["category"], context)
    cwd = _path(entry["cwd"], context)
    if component is not None and not cwd.is_relative_to(components[component].path):
        raise ConfigurationError(f"{context}: working directory escapes its component.")
    argv = entry["argv"]
    if (
        not isinstance(argv, list)
        or not argv
        or any(
            not isinstance(arg, str)
            or "\0" in arg
            or any(0xD800 <= ord(char) <= 0xDFFF for char in arg)
            for arg in argv
        )
        or not argv[0].strip()
    ):
        raise ConfigurationError(
            f"{context}: argv must contain a nonempty executable and text arguments."
        )
    required = entry["required"]
    if type(required) is not bool:
        raise ConfigurationError(f"{context}: required must be a boolean.")
    timeout = entry["timeout_seconds"]
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ConfigurationError(f"{context}: timeout_seconds must be a number.")
    try:
        seconds = float(timeout)
    except OverflowError as error:
        raise ConfigurationError(
            f"{context}: timeout_seconds is out of range."
        ) from error
    if not math.isfinite(seconds) or seconds <= 0:
        raise ConfigurationError(
            f"{context}: timeout_seconds must be finite and positive."
        )
    return Check(
        name, scope, component, profile, category, cwd, tuple(argv), required, seconds
    )


def _required_checks(config: Configuration, registry: ProfileRegistry) -> None:
    for component in config.components:
        for profile_id in component.profiles:
            for requirement in registry.get(profile_id).required_checks:
                matches = [
                    c
                    for c in config.checks
                    if c.component == component.id
                    and c.profile == profile_id
                    and c.category == requirement.category
                ]
                context = (
                    f"component {component.id}, profile {profile_id}, "
                    f"category {requirement.category}"
                )
                if len(matches) != 1 or not matches[0].required:
                    raise ConfigurationError(
                        f"{context}: exactly one required check is mandatory."
                    )
                if requirement.argv is not None and (
                    matches[0].argv != requirement.argv
                    or matches[0].cwd != component.path
                ):
                    raise ConfigurationError(
                        f"{context}: mandatory argv and component root "
                        "cannot be replaced."
                    )


def parse_configuration(
    content: str, *, registry: ProfileRegistry = BUILTIN_PROFILES
) -> Configuration:
    """Parse bounded TOML with strict fields, paths and mandatory checks.

    This pure function performs no filesystem access and never executes argv.
    Missing directories are addressed separately by validate_directories.
    Raises ConfigurationError without echoing configuration values on failure.
    """
    if len(content) > MAX_CONFIGURATION_BYTES:
        raise ConfigurationError("Configuration exceeds the 1 MiB limit.")
    try:
        encoded_size = len(content.encode("utf-8"))
    except UnicodeError as error:
        raise ConfigurationError("Configuration must be valid UTF-8.") from error
    if encoded_size > MAX_CONFIGURATION_BYTES:
        raise ConfigurationError("Configuration exceeds the 1 MiB limit.")
    try:
        raw: object = tomllib.loads(content)
    except (ValueError, RecursionError) as error:
        # tomllib may also surface the interpreter's integer-digit limit as
        # ValueError rather than TOMLDecodeError. Keep that parser boundary narrow.
        raise ConfigurationError(
            "Invalid TOML configuration; "
            "check syntax, encoding and duplicate declarations."
        ) from error
    entry = _table(raw, "configuration")
    _fields(entry, {"schema_version", "components", "checks"}, "configuration")
    if type(entry["schema_version"]) is not int or entry["schema_version"] != 1:
        raise ConfigurationError("configuration: schema_version must be integer 1.")
    components = _components(entry["components"], registry)
    checks = entry["checks"]
    if not isinstance(checks, list) or not 1 <= len(checks) <= MAX_CHECKS:
        raise ConfigurationError(f"checks: expected 1 to {MAX_CHECKS} entries.")
    by_id = {item.id: item for item in components}
    parsed = tuple(_check(c, by_id) for c in checks)
    if len({c.name for c in parsed}) != len(parsed):
        raise ConfigurationError("checks: duplicate check names.")
    result = Configuration(1, components, tuple(sorted(parsed, key=lambda c: c.name)))
    _required_checks(result, registry)
    return result


def _directory(path: Path, *, require_exists: bool, context: str) -> None:
    for candidate in (*reversed(path.parents), path):
        try:
            mode = candidate.lstat().st_mode
        except FileNotFoundError:
            if require_exists:
                raise ConfigurationError(
                    f"{context}: required directory is missing."
                ) from None
            continue
        except OSError as error:
            raise ConfigurationError(f"{context}: cannot inspect directory.") from error
        if not stat.S_ISDIR(mode):
            raise ConfigurationError(f"{context}: symlink or non-directory path.")


def _root(root: Path, *, require_exists: bool) -> Path:
    path = root.expanduser().absolute()
    if ".." in path.parts:
        raise ConfigurationError("Repository root must not contain traversal.")
    _directory(path, require_exists=require_exists, context="repository root")
    return path


def validate_directories(
    config: Configuration, root: Path, *, require_exists: bool = False
) -> None:
    """Inspect paths without writes; require existence immediately before execution.

    Accept only configurations returned by parse_configuration/resolve_configuration.
    Missing directories are permitted during planning, but existing symlinks and
    non-directories are always errors. This is not an application source scanner
    or protection against concurrent hostile filesystem mutation.
    """
    root = _root(root, require_exists=require_exists)
    paths = [(c.path, f"component {c.id}") for c in config.components]
    paths += [(c.cwd, f"check {c.name}") for c in config.checks]
    for path, context in paths:
        _directory(root / path, require_exists=require_exists, context=context)


def load_configuration(
    root: Path, *, registry: ProfileRegistry = BUILTIN_PROFILES
) -> Configuration | None:
    """Read at most 1 MiB of a regular UTF-8 TOML file; absence alone returns None.

    Reject links and special files before opening. The repository must not be
    concurrently modified during inspection. Never loads env files or commands.
    """
    root = _root(root, require_exists=False)
    path = root / CONFIGURATION_NAME
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ConfigurationError("Cannot inspect lean-sdd.toml.") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise ConfigurationError("lean-sdd.toml must be a regular file, not a symlink.")
    if metadata.st_size > MAX_CONFIGURATION_BYTES:
        raise ConfigurationError("Configuration exceeds the 1 MiB limit.")
    try:
        with path.open("rb") as stream:
            content = stream.read(MAX_CONFIGURATION_BYTES + 1)
        if len(content) > MAX_CONFIGURATION_BYTES:
            raise ConfigurationError("Configuration exceeds the 1 MiB limit.")
        text = content.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise ConfigurationError("Cannot read lean-sdd.toml as UTF-8.") from error
    config = parse_configuration(text, registry=registry)
    validate_directories(config, root)
    return config


def _legacy_python() -> Configuration:
    checks = tuple(
        Check(
            f"python-{r.category}",
            "component",
            "root",
            "python",
            r.category,
            PurePosixPath("."),
            r.argv,
            True,
            DEFAULT_TIMEOUT_SECONDS,
        )
        for r in PYTHON.required_checks
        if r.argv is not None
    )
    return Configuration(
        1,
        (Component("root", PurePosixPath("."), ("python",)),),
        tuple(sorted(checks, key=lambda c: c.name)),
    )


def resolve_configuration(
    root: Path,
    *,
    installed: InstallationIdentity | None = None,
    language: str | None = None,
    registry: ProfileRegistry = BUILTIN_PROFILES,
) -> ResolvedConfiguration:
    """Resolve explicit configuration, historical identity, then a fresh default.

    A language convenience selection must exactly match a sole selected profile
    in a component rooted at '.'. No supported profile replaces unavailable
    historical identity. This function never executes or writes configuration.
    """
    config = load_configuration(root, registry=registry)
    if language is not None:
        language = _identifier(language, "language")
        _supported(registry, language)
    if installed is not None:
        for profile in installed.profiles:
            _supported(registry, profile)
        if config is None and installed.configuration_mode == "configured":
            raise ConfigurationError(
                "Installed configuration requires lean-sdd.toml; "
                "no fallback is permitted."
            )
        if config is not None and not set(config.profiles).issubset(installed.profiles):
            raise ConfigurationError(
                "Configuration selects profiles that are not installed."
            )
        if language is not None and installed.profiles != (language,):
            raise ConfigurationError(
                "Language selection would switch installed profiles."
            )
    if config is not None:
        if language is not None and (
            len(config.components) != 1
            or config.components[0].path != PurePosixPath(".")
            or config.profiles != (language,)
        ):
            raise ConfigurationError(
                "Language conflicts with the explicit component mapping."
            )
        return ResolvedConfiguration(config, "explicit")
    if language not in (None, "python"):
        raise ConfigurationError(
            "This profile requires explicit component/check configuration."
        )
    _supported(registry, "python")
    origin: Literal["installed-legacy", "fresh-default", "language"] = (
        "installed-legacy"
        if installed is not None
        else "language"
        if language
        else "fresh-default"
    )
    config = _legacy_python()
    validate_directories(config, root)
    return ResolvedConfiguration(config, origin)
