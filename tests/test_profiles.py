"""Verify profile composition, preserved policy, and resource failure boundaries."""

import json
import subprocess
from dataclasses import replace
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

import pytest

from lean_sdd.profiles import PYTHON, Profile, ProfileRegistry, RequiredCheck, Resource
from lean_sdd.templates import (
    CORE_SKILLS,
    MAX_RESOURCE_BYTES,
    compose_bundle,
    package_version,
    resolve_bundle,
    template_files,
    template_manifest,
)


def read_resources(root: Traversable) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for entry in root.iterdir():
        if entry.is_dir():
            result.update(
                {
                    f"{entry.name}/{name}": data
                    for name, data in read_resources(entry).items()
                }
            )
        else:
            result[entry.name] = entry.read_bytes()
    return result


@pytest.fixture
def common() -> dict[str, bytes]:
    common = read_resources(files("lean_sdd_templates").joinpath("common"))
    common[".agents/README.md"] = resolve_bundle().payload[".agents/README.md"]
    return common


@pytest.fixture
def python_files() -> dict[str, bytes]:
    return {PYTHON.standards_path: resolve_bundle().payload[PYTHON.standards_path]}


@pytest.fixture
def resource_tree(tmp_path: Path) -> Path:
    root = tmp_path / "resources"
    for name, content in read_resources(files("lean_sdd_templates")).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return root


def fixture_profile(name: str = "fixture", *, skill: str | None = None) -> Profile:
    resources: tuple[Resource, ...] = (
        Resource("standards.md", f".agents/standards/{name}.md"),
    )
    if skill is not None:
        resources += (Resource("SKILL.md", f".agents/skills/{skill}/SKILL.md"),)
    return Profile(
        name,
        "Inert fixture",
        (RequiredCheck("tests"),),
        tools=("fixture-tool",),
        resources=resources,
        skills=() if skill is None else (skill,),
    )


def contribution(profile: Profile) -> dict[str, bytes]:
    return {
        resource.destination: b"# Inert fixture\n" for resource in profile.resources
    }


def test_historical_manifest_preserves_rules_and_scripts() -> None:
    baseline = Path(__file__).parent / "fixtures/legacy-template-manifest.json"
    historical = json.loads(baseline.read_text(encoding="utf-8"))
    current = template_manifest(template_files())
    # #9 changed workflow documents in 0.2.0; #10 explicitly amended the
    # constitution in 0.2.1. Keep the historical fixture intact and pin the
    # approved amendment separately to protect every other original asset byte.
    revised = {
        "CONSTITUTION.md",
        "AGENTS.md",
        ".agents/README.md",
        ".agents/github-mcp-contract.md",
        ".agents/github-issue-contract.md",
        ".agents/github-workflow-acceptance.md",
        ".agents/skills/finalize-implementation/references/phase-contracts.md",
        ".agents/skills/create-issue/SKILL.md",
        ".agents/skills/get-issue/SKILL.md",
        ".agents/skills/update-issue/SKILL.md",
    }
    assert {name for name in historical if historical[name] != current[name]} == revised
    assert set(current) - set(historical) == {
        f".agents/docs/{name}.md"
        for name in ("configuration", "profiles", "diagnostics", "validation")
    }
    assert current["CONSTITUTION.md"] == (
        "3a4775e0f56bfdee914924e4d5470f697f19904857b659c5c3a7f4c8cc96578a"
    )
    assert package_version() not in {"0.1.0", "0.2.0"}


def test_python_rules_and_common_workflow_are_preserved() -> None:
    legacy = template_files()
    bundle = resolve_bundle()
    assert bundle.template_version == package_version()
    assert bundle.profiles == ("python",)
    assert PYTHON.tools == ("python", "uv", "pytest", "ruff", "mypy")
    assert PYTHON.diagnostic == "python"
    expected = legacy["CODING_STANDARDS.md"]
    expected = expected.replace(b"](CONSTITUTION.md)", b"](../../CONSTITUTION.md)")
    expected = expected.replace(b"](AGENTS.md)", b"](../../AGENTS.md)")
    assert bundle.payload[".agents/standards/python.md"] == expected
    for name, content in legacy.items():
        if name != "CODING_STANDARDS.md":
            assert bundle.payload[name] == content, name
    shared = bundle.payload["CODING_STANDARDS.md"].decode("utf-8")
    assert "[.agents/standards/python.md](.agents/standards/python.md)" in shared
    assert "every installed language standard relevant to the change" in shared
    assert "cannot replace shared" in shared
    assert "{{profile_standards}}" not in shared
    assert list(bundle.payload) == sorted(bundle.payload)


def test_multiple_profile_order_is_deterministic(
    common: dict[str, bytes], python_files: dict[str, bytes]
) -> None:
    fixture = fixture_profile()
    registry = ProfileRegistry((fixture, PYTHON))
    first = compose_bundle(
        common,
        {"python": python_files, "fixture": contribution(fixture)},
        template_version="1.2.3",
        registry=registry,
    )
    second = compose_bundle(
        dict(reversed(list(common.items()))),
        {"fixture": contribution(fixture), "python": python_files},
        template_version="1.2.3",
        registry=registry,
    )
    assert first.profiles == ("fixture", "python")
    assert dict(first.payload) == dict(second.payload)
    assert template_manifest(first.payload) == template_manifest(second.payload)
    assert first.payload[PYTHON.standards_path] == python_files[PYTHON.standards_path]


def test_resolve_deduplicates_selected_profiles() -> None:
    assert resolve_bundle(["python", "python"]) == resolve_bundle(["python"])


def test_declared_skill_addition_is_composed(
    common: dict[str, bytes], python_files: dict[str, bytes]
) -> None:
    fixture = fixture_profile(skill="fixture-check")
    bundle = compose_bundle(
        common,
        {"python": python_files, "fixture": contribution(fixture)},
        template_version="1",
        registry=ProfileRegistry((PYTHON, fixture)),
    )
    actual = {p.split("/")[2] for p in bundle.payload if p.endswith("/SKILL.md")}
    assert actual == CORE_SKILLS | {"fixture-check"}


def test_fixture_only_bundle_does_not_reference_unselected_python(
    common: dict[str, bytes],
) -> None:
    fixture = fixture_profile()
    bundle = compose_bundle(
        common,
        {"fixture": contribution(fixture)},
        template_version="1",
        registry=ProfileRegistry((fixture,)),
    )
    assert PYTHON.standards_path not in bundle.payload
    assert b".agents/standards/python.md" not in bundle.payload["CODING_STANDARDS.md"]
    # A test-only registry cannot advertise its fixture as production support.
    assert fixture.id not in {p.id for p in ProfileRegistry().profiles}


def test_declared_skill_requires_nonempty_instructions(
    common: dict[str, bytes],
) -> None:
    fixture = fixture_profile(skill="fixture-check")
    contents = contribution(fixture)
    contents[".agents/skills/fixture-check/SKILL.md"] = b"\n"
    with pytest.raises(ValueError, match="skill instructions must be nonempty"):
        compose_bundle(
            common,
            {"fixture": contents},
            template_version="1",
            registry=ProfileRegistry((fixture,)),
        )


@pytest.mark.parametrize("selected", [[], ["unknown"], ["../python"]])
def test_invalid_or_unsupported_selection(selected: list[str]) -> None:
    with pytest.raises(ValueError):
        resolve_bundle(selected)


@pytest.mark.parametrize(
    "removed",
    [
        "AGENTS.md",
        "CONSTITUTION.md",
        "CODING_STANDARDS.md",
        ".agents/skills/get-issue/SKILL.md",
        ".agents/skills/get-issue/scripts/get-issue.sh",
        ".agents/lib/mcp.sh",
    ],
)
def test_missing_common_resources_fail(
    common: dict[str, bytes], python_files: dict[str, bytes], removed: str
) -> None:
    del common[removed]
    with pytest.raises(ValueError, match="required common"):
        compose_bundle(common, {"python": python_files}, template_version="1")


@pytest.mark.parametrize(
    "target",
    ["AGENTS.md", "CONSTITUTION.md", "CODING_STANDARDS.md", ".agents/lib/mcp.sh"],
)
def test_even_identical_profile_overrides_are_rejected(
    common: dict[str, bytes], target: str
) -> None:
    fixture = fixture_profile()
    fixture = replace(
        fixture, resources=fixture.resources + (Resource("override.md", target),)
    )
    contents = contribution(fixture)
    contents[target] = common[target]
    with pytest.raises(ValueError, match="collision"):
        compose_bundle(
            common,
            {"fixture": contents},
            template_version="1",
            registry=ProfileRegistry((fixture,)),
        )


@pytest.mark.parametrize(
    "target",
    [
        "CODING_STANDARDS.md/child",
        "coding_standards.md",
        ".agents",
        ".agents/lib/extra.sh",
    ],
)
def test_directory_conflicts_aliases_and_shared_helpers_are_rejected(
    common: dict[str, bytes], target: str
) -> None:
    fixture = fixture_profile()
    fixture = replace(
        fixture, resources=fixture.resources + (Resource("extra.md", target),)
    )
    with pytest.raises(ValueError, match="collision|conflict|shared workflow"):
        compose_bundle(
            common,
            {"fixture": contribution(fixture)},
            template_version="1",
            registry=ProfileRegistry((fixture,)),
        )


def test_cross_profile_collisions_are_rejected(common: dict[str, bytes]) -> None:
    a = fixture_profile("alpha")
    b = fixture_profile("beta")
    shared = Resource("extra.md", ".agents/shared-extra.md")
    a, b = (
        replace(a, resources=a.resources + (shared,)),
        replace(b, resources=b.resources + (shared,)),
    )
    with pytest.raises(ValueError, match="collision"):
        compose_bundle(
            common,
            {"alpha": contribution(a), "beta": contribution(b)},
            template_version="1",
            registry=ProfileRegistry((a, b)),
        )


@pytest.mark.parametrize(
    "path",
    ["../bad", "/absolute", "C:/bad", "x\\y", "./bad", "x//y", "x/../y", "NUL", "bad."],
)
def test_unsafe_resource_metadata(path: str) -> None:
    for resource in (
        Resource(path, ".agents/standards/fixture.md"),
        Resource("standards.md", path),
    ):
        with pytest.raises(ValueError, match="Unsafe"):
            ProfileRegistry((replace(fixture_profile(), resources=(resource,)),))


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".agents/.env",
        ".agents/.env.local",
        ".git/config",
        "__pycache__/x.pyc",
        ".agents/lean-sdd-install.json",
    ],
)
def test_sensitive_destinations_are_rejected(
    common: dict[str, bytes], path: str
) -> None:
    fixture = fixture_profile()
    fixture = replace(
        fixture, resources=fixture.resources + (Resource("extra.txt", path),)
    )
    with pytest.raises(ValueError, match="unsafe destination"):
        compose_bundle(
            common,
            {"fixture": contribution(fixture)},
            template_version="1",
            registry=ProfileRegistry((fixture,)),
        )


@pytest.mark.parametrize(
    "mode", ["missing", "extra", "empty", "broken-link", "invalid-utf8"]
)
def test_invalid_profile_payload(
    common: dict[str, bytes], python_files: dict[str, bytes], mode: str
) -> None:
    if mode == "missing":
        python_files.clear()
    elif mode == "extra":
        python_files["extra.md"] = b"undeclared"
    elif mode == "empty":
        python_files[PYTHON.standards_path] = b"\n"
    elif mode == "broken-link":
        python_files[PYTHON.standards_path] += b"[missing](absent.md)\n"
    else:
        python_files[PYTHON.standards_path] = b"\xff"
    with pytest.raises(ValueError):
        compose_bundle(common, {"python": python_files}, template_version="1")


@pytest.mark.parametrize(
    "mutation",
    [
        "extra-skill",
        "missing-skill",
        "core-skill",
        "diagnostic",
        "duplicate-mapping",
        "missing-standards",
    ],
)
def test_contradictory_profile_metadata(
    common: dict[str, bytes], mutation: str
) -> None:
    profile = fixture_profile()
    if mutation == "extra-skill":
        profile = replace(
            profile,
            resources=profile.resources
            + (Resource("SKILL.md", ".agents/skills/extra/SKILL.md"),),
        )
    elif mutation == "missing-skill":
        profile = replace(profile, skills=("extra",))
    elif mutation == "core-skill":
        profile = fixture_profile(skill="get-issue")
    elif mutation == "diagnostic":
        profile = replace(profile, diagnostic="untrusted.module:function")
    elif mutation == "duplicate-mapping":
        profile = replace(profile, resources=profile.resources + profile.resources)
    else:
        profile = replace(profile, resources=(Resource("other.md", "other.md"),))
    with pytest.raises(ValueError):
        registry = ProfileRegistry((profile,))
        compose_bundle(
            common,
            {"fixture": contribution(profile)},
            template_version="1",
            registry=registry,
        )


@pytest.mark.parametrize("count", [0, 2])
def test_shared_marker_must_be_unique(
    common: dict[str, bytes], python_files: dict[str, bytes], count: int
) -> None:
    common["CODING_STANDARDS.md"] = b"# Shared\n" + b"{{profile_standards}}" * count
    with pytest.raises(ValueError, match="exactly one"):
        compose_bundle(common, {"python": python_files}, template_version="1")


def test_resource_loading_with_multiple_profiles_and_no_execution(
    resource_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = fixture_profile(skill="fixture-check")
    root = resource_tree / "profiles/fixture"
    root.mkdir()
    (root / "standards.md").write_text("# Fixture\n", encoding="utf-8")
    (root / "SKILL.md").write_text("# Inert skill\n", encoding="utf-8")

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Resource resolution must not execute a command")

    before = {
        p: (p.read_bytes(), p.stat().st_mtime_ns)
        for p in resource_tree.rglob("*")
        if p.is_file()
    }
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    bundle = resolve_bundle(
        ["python", "fixture", "python"],
        registry=ProfileRegistry((PYTHON, fixture)),
        resource_root=resource_tree,
    )
    assert bundle.profiles == ("fixture", "python")
    assert ".agents/skills/fixture-check/SKILL.md" in bundle.payload
    assert before == {
        p: (p.read_bytes(), p.stat().st_mtime_ns)
        for p in resource_tree.rglob("*")
        if p.is_file()
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "undeclared",
        "symlink",
        "directory-link",
        "oversized",
        "bad-python-links",
        "bad-setup-links",
    ],
)
def test_resource_loader_failure_paths(resource_tree: Path, mutation: str) -> None:
    standards = resource_tree / "profiles/python/standards.md"
    if mutation == "missing":
        standards.unlink()
    elif mutation == "undeclared":
        (standards.parent / "extra.md").write_bytes(b"unknown")
    elif mutation == "symlink":
        standards.unlink()
        standards.symlink_to(resource_tree / "common/AGENTS.md")
    elif mutation == "directory-link":
        link = resource_tree / "common/linked"
        link.symlink_to(resource_tree / "profiles", target_is_directory=True)
    elif mutation == "oversized":
        standards.write_bytes(b"x" * (MAX_RESOURCE_BYTES + 1))
    elif mutation == "bad-setup-links":
        (resource_tree / "common/.agents/README.md").write_bytes(b"# Broken setup\n")
    else:
        standards.write_bytes(b"# Missing canonical links\n")
    with pytest.raises(ValueError):
        resolve_bundle(resource_root=resource_tree)


def test_setup_relocation_changes_only_declared_links() -> None:
    source = Path(__file__).parents[1] / ".agents/README.md"
    expected = source.read_bytes()
    for name in ("configuration", "profiles", "diagnostics", "validation"):
        expected = expected.replace(
            f"](../docs/{name}.md)".encode(), f"](docs/{name}.md)".encode()
        )
    assert resolve_bundle().payload[".agents/README.md"] == expected
