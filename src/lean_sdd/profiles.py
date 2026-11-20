"""Static, inert language contracts; importing a profile never runs its tools."""

import re
from dataclasses import dataclass

from lean_sdd.paths import safe_relative_path


@dataclass(frozen=True)
class Resource:
    """A packaged path relative to profiles/<id>/ and its installation destination."""

    source: str
    destination: str


def valid_identifier(value: str) -> bool:
    """Accept a portable lowercase identifier of at most 64 characters."""
    return re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value) is not None


@dataclass(frozen=True)
class RequiredCheck:
    """A mandatory category, optionally pinned to exact argv at the component root.

    None permits the reviewed configuration to supply concrete arguments and a
    directory inside the component. This is data, not an executable adapter.
    """

    category: str
    argv: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Profile:
    """Release-owned identity and validation obligations for a language."""

    id: str
    display_name: str
    required_checks: tuple[RequiredCheck, ...]
    tools: tuple[str, ...] = ()
    diagnostic: str | None = None
    resources: tuple[Resource, ...] = ()
    skills: tuple[str, ...] = ()

    @property
    def standards_path(self) -> str:
        """Return the canonical destination for this profile's standards."""
        return f".agents/standards/{self.id}.md"


PYTHON = Profile(
    "python",
    "Python",
    (
        RequiredCheck("tests", ("uv", "run", "pytest")),
        RequiredCheck("lint", ("uv", "run", "ruff", "check", ".")),
        RequiredCheck("format", ("uv", "run", "ruff", "format", "--check", ".")),
        RequiredCheck("types", ("uv", "run", "mypy", ".")),
    ),
    tools=("python", "uv", "pytest", "ruff", "mypy"),
    diagnostic="python",
    resources=(Resource("standards.md", ".agents/standards/python.md"),),
)


TYPESCRIPT_DEFAULT_SCRIPTS = (
    ("types", "typecheck"),
    ("lint", "lint"),
    ("format", "format:check"),
    ("tests", "test"),
    ("build", "build"),
)

TYPESCRIPT = Profile(
    "typescript",
    "TypeScript",
    tuple(
        RequiredCheck(category)
        for category in ("types", "lint", "format", "tests", "build")
    ),
    tools=("node", "npm"),
    diagnostic="typescript",
    resources=(
        Resource("standards.md", ".agents/standards/typescript.md"),
        Resource("guide.md", ".agents/docs/typescript.md"),
    ),
)


@dataclass(frozen=True)
class ProfileRegistry:
    """Explicit in-process catalog, with no filesystem or plugin discovery.

    Additional entries support inert fixtures and future bundled profiles. The
    built-in Python and TypeScript obligations cannot be replaced.
    """

    profiles: tuple[Profile, ...] = (PYTHON, TYPESCRIPT)

    def __post_init__(self) -> None:
        if not isinstance(self.profiles, tuple) or not self.profiles:
            raise ValueError("Profile registry must be a nonempty tuple.")
        ids: set[str] = set()
        for profile in self.profiles:
            if (
                not isinstance(profile, Profile)
                or not isinstance(profile.id, str)
                or not valid_identifier(profile.id)
                or profile.id in ids
            ):
                raise ValueError("Invalid or duplicate profile identity.")
            ids.add(profile.id)
            if (
                not isinstance(profile.display_name, str)
                or not profile.display_name.strip()
                or not isinstance(profile.required_checks, tuple)
                or not profile.required_checks
            ):
                raise ValueError("Profile name and mandatory checks must be nonempty.")
            categories: set[str] = set()
            for check in profile.required_checks:
                if (
                    not isinstance(check, RequiredCheck)
                    or not isinstance(check.category, str)
                    or not valid_identifier(check.category)
                    or check.category in categories
                ):
                    raise ValueError("Invalid or duplicate mandatory category.")
                categories.add(check.category)
                if check.argv is not None and (
                    not isinstance(check.argv, tuple)
                    or not check.argv
                    or any(
                        not isinstance(arg, str) or "\0" in arg for arg in check.argv
                    )
                    or not check.argv[0].strip()
                ):
                    raise ValueError("Invalid mandatory command argument tuple.")
            if profile.id == "python" and profile != PYTHON:
                raise ValueError("The Python profile cannot replace mandatory checks.")
            if profile.id == "typescript" and profile != TYPESCRIPT:
                raise ValueError(
                    "The TypeScript profile cannot replace mandatory checks."
                )
            _resource_metadata(profile)

    def get(self, profile_id: str) -> Profile:
        """Return the named profile or reject an unsupported selection."""
        for profile in self.profiles:
            if profile.id == profile_id:
                return profile
        # Only validated identifiers may appear in diagnostics, never raw TOML.
        if not valid_identifier(profile_id):
            raise ValueError("Invalid profile identifier.")
        raise ValueError(f"Unsupported profile: {profile_id}.")


def _resource_metadata(profile: Profile) -> None:
    for values in (profile.tools, profile.skills):
        if (
            not isinstance(values, tuple)
            or any(not isinstance(v, str) or not valid_identifier(v) for v in values)
            or len(set(values)) != len(values)
        ):
            raise ValueError("Tools and skills must be unique identifier tuples.")
    # Keys identify known future dispatch, never an import path or callable.
    if profile.diagnostic not in (None, "python", "typescript"):
        raise ValueError("Unknown built-in diagnostic selection.")
    if profile.diagnostic == "python" and profile.id != "python":
        raise ValueError("Python diagnostics belong only to the Python profile.")
    if profile.diagnostic == "typescript" and profile.id != "typescript":
        raise ValueError(
            "TypeScript diagnostics belong only to the TypeScript profile."
        )
    if not isinstance(profile.resources, tuple):
        raise ValueError("Profile resources must be an explicit tuple.")
    destinations: set[str] = set()
    for resource in profile.resources:
        if (
            not isinstance(resource, Resource)
            or not isinstance(resource.source, str)
            or not isinstance(resource.destination, str)
            or not safe_relative_path(resource.source)
            or not safe_relative_path(resource.destination)
        ):
            raise ValueError("Unsafe profile resource mapping.")
        if resource.destination.casefold() in destinations:
            raise ValueError("Duplicate profile resource destination.")
        destinations.add(resource.destination.casefold())
    # Contract-only fixtures from configuration parsing need no packaged assets.
    # A composable profile, however, must declare its canonical standards file.
    if profile.resources and profile.standards_path not in {
        r.destination for r in profile.resources
    }:
        raise ValueError("Profile resources must include its standards file.")
    if profile.skills and not profile.resources:
        raise ValueError("Declared skills require profile resources.")


BUILTIN_PROFILES = ProfileRegistry()
