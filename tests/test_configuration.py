"""Observable schema, resolution, filesystem and non-execution contracts."""

import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Literal

import pytest

from lean_sdd.configuration import (
    MAX_CHECKS,
    MAX_COMPONENTS,
    MAX_CONFIGURATION_BYTES,
    ConfigurationError,
    InstallationIdentity,
    load_configuration,
    parse_configuration,
    resolve_configuration,
    validate_directories,
)
from lean_sdd.profiles import PYTHON, Profile, ProfileRegistry, RequiredCheck

COMMANDS = {
    "tests": ["uv", "run", "pytest"],
    "lint": ["uv", "run", "ruff", "check", "."],
    "format": ["uv", "run", "ruff", "format", "--check", "."],
    "types": ["uv", "run", "mypy", "."],
}


def check_text(
    name: str,
    category: str,
    argv: list[str],
    *,
    component: str | None = "root",
    profile: str = "python",
    cwd: str = ".",
    required: bool = True,
) -> str:
    """Build an explicit complete check, independently of production defaults."""
    lines = [
        "[[checks]]",
        f"name = {json.dumps(name)}",
        f'scope = "{"component" if component else "project"}"',
        f"category = {json.dumps(category)}",
        f"cwd = {json.dumps(cwd)}",
        f"argv = {json.dumps(argv)}",
        f"required = {str(required).lower()}",
        "timeout_seconds = 120",
    ]
    if component is not None:
        lines += [
            f"component = {json.dumps(component)}",
            f"profile = {json.dumps(profile)}",
        ]
    return "\n".join(lines) + "\n"


def configuration(
    components: tuple[tuple[str, str], ...] = (("root", "."),),
) -> str:
    text = "schema_version = 1\n"
    for name, path in components:
        text += (
            f'[components.{name}]\npath = {json.dumps(path)}\nprofiles = ["python"]\n'
        )
    for name, path in components:
        for category, argv in COMMANDS.items():
            text += check_text(
                f"{name}-{category}", category, argv, component=name, cwd=path
            )
    return text


def write_config(root: Path, text: str) -> None:
    (root / "lean-sdd.toml").write_text(text, encoding="utf-8")


def fixture_registry() -> ProfileRegistry:
    return ProfileRegistry(
        (PYTHON, Profile("fixture", "Inert fixture", (RequiredCheck("tests"),)))
    )


def mixed_configuration() -> str:
    return configuration().replace(
        'profiles = ["python"]', 'profiles = ["python", "fixture"]'
    ) + check_text("fixture-tests", "tests", ["inert-fixture"], profile="fixture")


def test_explicit_root_configuration_preserves_python_commands() -> None:
    parsed = parse_configuration(configuration())
    assert parsed.schema_version == 1
    assert parsed.components[0].path == PurePosixPath(".")
    assert parsed.profiles == ("python",)
    assert [check.name for check in parsed.checks] == sorted(
        check.name for check in parsed.checks
    )
    assert {c.category: list(c.argv) for c in parsed.checks} == COMMANDS
    assert all(c.required and c.timeout_seconds == 120 for c in parsed.checks)


def test_documented_examples_are_complete_valid_configurations() -> None:
    documentation = Path(__file__).resolve().parents[1] / "docs/configuration.md"
    examples = re.findall(
        r"```toml\n(.*?)```", documentation.read_text(encoding="utf-8"), re.DOTALL
    )
    assert len(examples) == 2
    parsed = [parse_configuration(text) for text in examples]
    assert len(parsed[0].components) == 1
    assert len(parsed[1].components) == 2
    assert any(c.scope == "project" and c.required for c in parsed[1].checks)


def test_two_python_components_do_not_require_distinct_languages(
    tmp_path: Path,
) -> None:
    text = configuration((("worker", "src/worker"), ("api", "src/api")))
    parsed = parse_configuration(text)
    assert tuple(c.id for c in parsed.components) == ("api", "worker")
    assert len(parsed.checks) == 8
    validate_directories(parsed, tmp_path)
    assert not (tmp_path / "src").exists()
    with pytest.raises(ConfigurationError, match="required directory is missing"):
        validate_directories(parsed, tmp_path, require_exists=True)
    (tmp_path / "src/api").mkdir(parents=True)
    (tmp_path / "src/worker").mkdir()
    validate_directories(parsed, tmp_path, require_exists=True)


def test_multiple_profiles_have_separate_obligations() -> None:
    parsed = parse_configuration(mixed_configuration(), registry=fixture_registry())
    assert parsed.profiles == ("fixture", "python")
    assert len([c for c in parsed.checks if c.category == "tests"]) == 2
    with pytest.raises(ConfigurationError, match="exactly one required"):
        parse_configuration(
            mixed_configuration().replace("required = true", "required = false"),
            registry=fixture_registry(),
        )


def test_inert_component_and_project_checks_are_supported() -> None:
    text = (
        "schema_version = 1\n[components.worker]\n"
        'path = "src/worker"\nprofiles = ["fixture"]\n'
    )
    text += check_text(
        "unit",
        "tests",
        ["inert"],
        component="worker",
        profile="fixture",
        cwd="src/worker/tests",
    )
    text += check_text(
        "integration", "integration", ["inert"], component=None, cwd="tests/integration"
    )
    parsed = parse_configuration(text, registry=fixture_registry())
    assert parsed.checks[0].scope == "project"
    assert parsed.checks[0].component is None
    assert parsed.checks[1].cwd == PurePosixPath("src/worker/tests")


@pytest.mark.parametrize("replacement", ["true", "1.0", '"1"', "0", "2"])
def test_schema_version_is_strict(replacement: str) -> None:
    with pytest.raises(ConfigurationError, match="schema_version"):
        parse_configuration(
            configuration().replace(
                "schema_version = 1", f"schema_version = {replacement}"
            )
        )


@pytest.mark.parametrize(
    "text",
    [
        "",
        "garbage",
        "schema_version = 1",
        "schema_version = 1\ncomponents = []\nchecks = []",
    ],
)
def test_incomplete_configuration_is_an_error(text: str) -> None:
    with pytest.raises(ConfigurationError):
        parse_configuration(text)


@pytest.mark.parametrize(
    "old,new",
    [
        ('path = "."', 'path = "."\nextra = "secret-value"'),
        ("schema_version = 1", 'schema_version = 1\nextra = "secret-value"'),
        ('name = "root-tests"', 'name = "root-tests"\nextra = "secret-value"'),
        ("required = true\n", ""),
        ("timeout_seconds = 120\n", ""),
        ('argv = ["uv", "run", "pytest"]\n', ""),
        ('profiles = ["python"]', "profiles = []"),
        ('profiles = ["python"]', 'profiles = "python"'),
        ('profiles = ["python"]', "profiles = [true]"),
        ('profiles = ["python"]', 'profiles = ["python", "python"]'),
        ('profiles = ["python"]', 'profiles = ["unsupported"]'),
        ("components.root", 'components."bad name"'),
        ('name = "root-tests"', 'name = "Root.Tests"'),
        ('component = "root"', 'component = "missing"'),
        ('profile = "python"', 'profile = "fixture"'),
        ('scope = "component"', 'scope = "unknown"'),
        ('scope = "component"', 'scope = "project"'),
        ('category = "tests"', 'category = ""'),
        ("required = true", 'required = "true"'),
        ("required = true", "required = 1"),
    ],
)
def test_invalid_fields_and_assignments(old: str, new: str) -> None:
    with pytest.raises(ConfigurationError) as caught:
        parse_configuration(configuration().replace(old, new, 1))
    assert "secret-value" not in str(caught.value)


@pytest.mark.parametrize(
    "suffix",
    [
        '\n[components.root]\npath = "."\nprofiles = ["python"]\n',
        '\n[[checks]]\nname = "x"\nname = "y"\n',
    ],
)
def test_duplicate_toml_declarations_are_rejected(suffix: str) -> None:
    with pytest.raises(ConfigurationError, match="duplicate declarations"):
        parse_configuration(configuration() + suffix)


def test_duplicate_check_names_are_rejected() -> None:
    with pytest.raises(ConfigurationError, match="duplicate check names"):
        parse_configuration(
            configuration().replace('name = "root-lint"', 'name = "root-tests"')
        )


@pytest.mark.parametrize(
    "timeout", ["true", "false", '"120"', "0", "-1", "nan", "inf", "-inf", "1e999"]
)
def test_timeout_must_be_finite_positive_number(timeout: str) -> None:
    with pytest.raises(ConfigurationError, match="timeout_seconds"):
        parse_configuration(
            configuration().replace(
                "timeout_seconds = 120", f"timeout_seconds = {timeout}"
            )
        )


def test_fractional_timeout_is_preserved() -> None:
    parsed = parse_configuration(
        configuration().replace("timeout_seconds = 120", "timeout_seconds = 0.25")
    )
    assert all(c.timeout_seconds == 0.25 for c in parsed.checks)


@pytest.mark.parametrize(
    "argv",
    ["[]", '[""]', '["  "]', '["uv", true]', '"uv run pytest"', '["uv", "\\u0000"]'],
)
def test_invalid_argv(argv: str) -> None:
    with pytest.raises(ConfigurationError):
        parse_configuration(configuration().replace('["uv", "run", "pytest"]', argv))


def test_optional_arguments_preserve_shell_metacharacters_as_data() -> None:
    arguments = ["unused", "", "$(touch secret)", "; echo never", "a b", "line\nbreak"]
    text = configuration() + check_text("optional", "extra", arguments, required=False)
    parsed = parse_configuration(text)
    optional = next(c for c in parsed.checks if c.name == "optional")
    assert optional.argv == tuple(arguments)
    assert not optional.required


@pytest.mark.parametrize("category", list(COMMANDS))
def test_required_categories_cannot_be_removed(category: str) -> None:
    text = configuration().replace(
        check_text(f"root-{category}", category, COMMANDS[category]), ""
    )
    with pytest.raises(ConfigurationError, match="exactly one required"):
        parse_configuration(text)


@pytest.mark.parametrize("mutation", ["optional", "argv", "cwd", "duplicate"])
def test_required_checks_cannot_be_downgraded_or_replaced(mutation: str) -> None:
    text = configuration()
    if mutation == "optional":
        text = text.replace("required = true", "required = false", 1)
    elif mutation == "argv":
        text = text.replace('["uv", "run", "pytest"]', '["echo", "passed"]')
    elif mutation == "cwd":
        text = text.replace('cwd = "."', 'cwd = "src"', 1)
    else:
        text += check_text("duplicate-tests", "tests", COMMANDS["tests"])
    with pytest.raises(ConfigurationError, match="mandatory"):
        parse_configuration(text)


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/src/api",
        "../src/api",
        "src/../api",
        "src/./api",
        "src//api",
        "src/api/",
        "apps/api",
        "C:/src/api",
        "src\\api",
        "src/CON",
        "src/api.",
        "src/api ",
        "src/\napi",
    ],
)
def test_unsafe_component_paths(path: str) -> None:
    with pytest.raises(ConfigurationError):
        parse_configuration(configuration((("api", path),)))


@pytest.mark.parametrize(
    "paths",
    [
        (("a", "."), ("b", "src/b")),
        (("a", "src/a"), ("b", "src/a")),
        (("a", "src/a"), ("b", "src/a/child")),
        (("a", "src/a/child"), ("b", "src/a")),
        (("a", "src/API"), ("b", "src/api")),
    ],
)
def test_overlapping_component_paths(paths: tuple[tuple[str, str], ...]) -> None:
    with pytest.raises(ConfigurationError, match="overlapping"):
        parse_configuration(configuration(paths))


@pytest.mark.parametrize("cwd", ["..", "/tmp", "src/../tests", "src/sibling", "."])
def test_component_check_cannot_escape_component(cwd: str) -> None:
    text = configuration((("api", "src/api"),)) + check_text(
        "extra", "extra", ["unused"], component="api", cwd=cwd
    )
    with pytest.raises(ConfigurationError):
        parse_configuration(text)


@pytest.mark.parametrize("cwd", ["../outside", "/outside", "tests/../src"])
def test_project_check_cannot_escape_repository(cwd: str) -> None:
    with pytest.raises(ConfigurationError):
        parse_configuration(
            configuration()
            + check_text(
                "integration", "integration", ["unused"], component=None, cwd=cwd
            )
        )


@pytest.mark.parametrize("kind", ["file", "link", "broken-link"])
def test_component_path_types_are_checked_even_during_planning(
    tmp_path: Path, kind: str
) -> None:
    (tmp_path / "src").mkdir()
    path = tmp_path / "src/api"
    if kind == "file":
        path.write_text("not a directory", encoding="utf-8")
    else:
        destination = tmp_path / "destination"
        if kind == "link":
            destination.mkdir()
        path.symlink_to(destination, target_is_directory=True)
    parsed = parse_configuration(configuration((("api", "src/api"),)))
    with pytest.raises(ConfigurationError, match="symlink or non-directory"):
        validate_directories(parsed, tmp_path)


def test_root_ancestors_and_check_directories_reject_links(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "link"
    link.symlink_to(actual, target_is_directory=True)
    parsed = parse_configuration(configuration())
    with pytest.raises(ConfigurationError, match="symlink"):
        validate_directories(parsed, link / "child")
    text = configuration() + check_text("extra", "extra", ["unused"], cwd="link/child")
    with pytest.raises(ConfigurationError, match="symlink"):
        validate_directories(parse_configuration(text), tmp_path)


def test_missing_project_check_directory_blocks_execution(tmp_path: Path) -> None:
    parsed = parse_configuration(
        configuration()
        + check_text(
            "integration",
            "integration",
            ["unused"],
            component=None,
            cwd="tests/integration",
        )
    )
    validate_directories(parsed, tmp_path)
    with pytest.raises(
        ConfigurationError, match="check integration: required directory is missing"
    ):
        validate_directories(parsed, tmp_path, require_exists=True)


def test_absent_configuration_is_distinct_from_empty(tmp_path: Path) -> None:
    assert load_configuration(tmp_path) is None
    write_config(tmp_path, "")
    with pytest.raises(ConfigurationError):
        load_configuration(tmp_path)


@pytest.mark.parametrize(
    "kind", ["directory", "symlink", "fifo", "invalid-utf8", "oversized"]
)
def test_loader_rejects_unsafe_or_invalid_files(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "lean-sdd.toml"
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        path.symlink_to(tmp_path / "missing")
    elif kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("FIFO files are unavailable on this platform")
        os.mkfifo(path)
    elif kind == "invalid-utf8":
        path.write_bytes(b"\xff")
    else:
        path.write_bytes(b" " * (MAX_CONFIGURATION_BYTES + 1))
    with pytest.raises(ConfigurationError):
        load_configuration(tmp_path)


def test_parser_limits_encoded_size_and_nesting() -> None:
    with pytest.raises(ConfigurationError, match="1 MiB"):
        parse_configuration("#" + "é" * (MAX_CONFIGURATION_BYTES // 2))
    with pytest.raises(ConfigurationError):
        parse_configuration("value = " + "[" * 2000 + "]" * 2000)


def test_large_integer_errors_stay_at_configuration_boundary() -> None:
    with pytest.raises(ConfigurationError):
        parse_configuration(
            configuration().replace(
                "timeout_seconds = 120", "timeout_seconds = " + "9" * 5000, 1
            )
        )


def test_component_and_check_count_limits() -> None:
    text = configuration(
        tuple((f"component{i}", f"src/c{i}") for i in range(MAX_COMPONENTS + 1))
    )
    with pytest.raises(ConfigurationError, match="components: expected"):
        parse_configuration(text)
    text = configuration() + "".join(
        check_text(f"extra{i}", "extra", ["unused"]) for i in range(MAX_CHECKS)
    )
    with pytest.raises(ConfigurationError, match="checks: expected"):
        parse_configuration(text)


def test_legacy_and_fresh_default_share_required_commands(tmp_path: Path) -> None:
    fresh = resolve_configuration(tmp_path)
    legacy = resolve_configuration(
        tmp_path, installed=InstallationIdentity(("python",), "legacy-python")
    )
    selected = resolve_configuration(tmp_path, language="python")
    assert fresh.origin == "fresh-default"
    assert legacy.origin == "installed-legacy"
    assert selected.origin == "language"
    assert fresh.configuration == legacy.configuration == selected.configuration
    assert {c.category: list(c.argv) for c in fresh.configuration.checks} == COMMANDS
    assert all(c.timeout_seconds == 300 for c in fresh.configuration.checks)


def test_configuration_overrides_default_but_not_installed_identity(
    tmp_path: Path,
) -> None:
    write_config(
        tmp_path, configuration((("api", "src/api"), ("worker", "src/worker")))
    )
    result = resolve_configuration(
        tmp_path, installed=InstallationIdentity(("python",), "legacy-python")
    )
    assert result.origin == "explicit"
    assert len(result.configuration.components) == 2
    with pytest.raises(ConfigurationError, match="conflicts"):
        resolve_configuration(tmp_path, language="python")


def test_compatible_language_and_explicit_root_selection(tmp_path: Path) -> None:
    write_config(tmp_path, configuration())
    result = resolve_configuration(
        tmp_path,
        language="python",
        installed=InstallationIdentity(("python",), "configured"),
    )
    assert result.origin == "explicit"


def test_configured_installation_never_guesses_missing_mapping(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="requires lean-sdd.toml"):
        resolve_configuration(
            tmp_path,
            installed=InstallationIdentity(("python",), "configured"),
            language="python",
        )


@pytest.mark.parametrize("text", ["", "broken", "schema_version = true"])
def test_malformed_configuration_never_falls_back(tmp_path: Path, text: str) -> None:
    write_config(tmp_path, text)
    with pytest.raises(ConfigurationError):
        resolve_configuration(
            tmp_path, installed=InstallationIdentity(("python",), "legacy-python")
        )


def test_unavailable_historical_profile_is_not_replaced(tmp_path: Path) -> None:
    identity = InstallationIdentity(("historical",), "configured")
    write_config(tmp_path, configuration())
    with pytest.raises(ConfigurationError, match="Unsupported profile: historical"):
        resolve_configuration(tmp_path, installed=identity)


def test_mapping_can_use_subset_of_installed_profiles(tmp_path: Path) -> None:
    write_config(tmp_path, configuration())
    identity = InstallationIdentity(("fixture", "python"), "configured")
    resolved = resolve_configuration(
        tmp_path, installed=identity, registry=fixture_registry()
    )
    assert resolved.configuration.profiles == ("python",)
    assert identity.profiles == ("fixture", "python")
    with pytest.raises(ConfigurationError, match="switch installed profiles"):
        resolve_configuration(
            tmp_path, installed=identity, registry=fixture_registry(), language="python"
        )


def test_uninstalled_profile_selection_is_rejected(tmp_path: Path) -> None:
    write_config(tmp_path, mixed_configuration())
    with pytest.raises(ConfigurationError, match="not installed"):
        resolve_configuration(
            tmp_path,
            installed=InstallationIdentity(("python",), "configured"),
            registry=fixture_registry(),
        )


@pytest.mark.parametrize(
    "profiles,mode",
    [
        ((), "configured"),
        (("python", "python"), "configured"),
        (("python", "fixture"), "configured"),
        (("bad/id",), "configured"),
        (("typescript",), "legacy-python"),
    ],
)
def test_installed_identity_rejects_invalid_state(
    profiles: tuple[str, ...], mode: Literal["configured", "legacy-python"]
) -> None:
    with pytest.raises(ConfigurationError):
        InstallationIdentity(profiles, mode)


def test_typescript_resolves_its_own_required_default_plan(tmp_path: Path) -> None:
    assert tuple(p.id for p in ProfileRegistry().profiles) == ("python", "typescript")
    resolved = resolve_configuration(tmp_path, language="typescript")
    assert resolved.configuration.profiles == ("typescript",)
    assert len(resolved.configuration.checks) == 5
    assert all(c.argv[:2] == ("npm", "run") for c in resolved.configuration.checks)


def test_fixture_profile_requires_explicit_commands_without_python_fallback(
    tmp_path: Path,
) -> None:
    with pytest.raises(ConfigurationError, match="requires explicit"):
        resolve_configuration(tmp_path, language="fixture", registry=fixture_registry())


def test_registry_rejects_duplicate_and_weakened_profiles() -> None:
    with pytest.raises(ValueError, match="duplicate profile"):
        ProfileRegistry((PYTHON, PYTHON))
    with pytest.raises(ValueError, match="cannot replace"):
        ProfileRegistry(
            (
                Profile(
                    "python", "Python", (RequiredCheck("tests", ("echo", "passed")),)
                ),
            )
        )
    with pytest.raises(ValueError, match="duplicate mandatory"):
        ProfileRegistry(
            (
                Profile(
                    "fixture",
                    "Fixture",
                    (RequiredCheck("tests"), RequiredCheck("tests")),
                ),
            )
        )


def test_resolution_neither_executes_nor_modifies_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Configuration inspection must not execute commands")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    write_config(
        tmp_path,
        configuration()
        + check_text(
            "untrusted", "extra", ["sh", "-c", "touch never-created"], required=False
        ),
    )
    secret = tmp_path / ".env"
    secret.write_text("NOT_LOADED=secret\n", encoding="utf-8")
    before = {
        p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()
    }
    result = resolve_configuration(tmp_path)
    validate_directories(result.configuration, tmp_path, require_exists=True)
    after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()}
    assert before == after
    assert "NOT_LOADED" not in os.environ
