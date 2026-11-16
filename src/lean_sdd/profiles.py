"""Static, inert language contracts; importing a profile never runs its tools."""

import re
from dataclasses import dataclass


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


PYTHON = Profile(
    "python",
    "Python",
    (
        RequiredCheck("tests", ("uv", "run", "pytest")),
        RequiredCheck("lint", ("uv", "run", "ruff", "check", ".")),
        RequiredCheck("format", ("uv", "run", "ruff", "format", "--check", ".")),
        RequiredCheck("types", ("uv", "run", "mypy", ".")),
    ),
)


@dataclass(frozen=True)
class ProfileRegistry:
    """Explicit in-process catalog, with no filesystem or plugin discovery.

    Additional entries support inert fixtures and future bundled profiles. The
    production default contains only Python, whose obligations cannot be replaced.
    """

    profiles: tuple[Profile, ...] = (PYTHON,)

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

    def get(self, profile_id: str) -> Profile:
        """Return the named profile or reject an unsupported selection."""
        for profile in self.profiles:
            if profile.id == profile_id:
                return profile
        # Only validated identifiers may appear in diagnostics, never raw TOML.
        if not valid_identifier(profile_id):
            raise ValueError("Invalid profile identifier.")
        raise ValueError(f"Unsupported profile: {profile_id}.")


BUILTIN_PROFILES = ProfileRegistry()
