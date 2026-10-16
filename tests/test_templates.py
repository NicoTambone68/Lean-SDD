"""Validate installation records independently of the installed CLI release."""

import json

import pytest

from lean_sdd.templates import installation_state, parse_installation_state


def record(**changes: object) -> str:
    state: dict[str, object] = {
        "schema_version": 1,
        "template_version": "0.0.1",
        "files": {".agents/example.md": "a" * 64},
    }
    state.update(changes)
    return json.dumps(state)


def test_existing_schema_round_trips_without_migration() -> None:
    content = installation_state({"AGENTS.md": b"rules\n"})
    parsed = parse_installation_state(content.decode("utf-8"))
    serialized = json.loads(content)
    assert parsed.schema_version == serialized["schema_version"] == 1
    assert parsed.template_version == serialized["template_version"]
    assert parsed.files == serialized["files"]


def test_historical_version_and_hex_case_are_supported() -> None:
    parsed = parse_installation_state(
        record(files={".agents/example.md": "A" * 64}, extra="ignored")
    )
    assert parsed.template_version == "0.0.1"
    assert parsed.files == {".agents/example.md": "a" * 64}


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{", "not valid JSON"),
        ("[" * 2_000, "not valid JSON"),
        ("null", "must be a JSON object"),
        ("[]", "must be a JSON object"),
        (record(extra=float("nan")), "not valid JSON"),
        (record(extra=float("inf")), "not valid JSON"),
        ("{}", "schema_version must be an integer"),
        (record(schema_version=None), "schema_version must be an integer"),
        (record(schema_version=True), "schema_version must be an integer"),
        (record(schema_version="1"), "schema_version must be an integer"),
        (record(schema_version=1.0), "schema_version must be an integer"),
        (record(schema_version=2), "Unsupported.*schema_version: 2"),
        (record(template_version=None), "template_version must be nonempty text"),
        (record(template_version=1), "template_version must be nonempty text"),
        (record(template_version=""), "template_version must be nonempty text"),
        (record(template_version="  "), "template_version must be nonempty text"),
        ('{"schema_version": 1}', "template_version must be nonempty text"),
        ('{"schema_version": 1, "template_version": "old"}', "nonempty mapping"),
        (record(files=None), "nonempty mapping"),
        (record(files=[]), "nonempty mapping"),
        (record(files={}), "nonempty mapping"),
        (record(files={"AGENTS.md": None}), "Invalid SHA-256"),
        (record(files={"AGENTS.md": 123}), "Invalid SHA-256"),
        (record(files={"AGENTS.md": "a" * 63}), "Invalid SHA-256"),
        (record(files={"AGENTS.md": "a" * 65}), "Invalid SHA-256"),
        (record(files={"AGENTS.md": "g" * 64}), "Invalid SHA-256"),
        (record(files={"AGENTS.md": "a" * 64 + "\n"}), "Invalid SHA-256"),
        ('{"schema_version": 2, "schema_version": 1}', "Duplicate.*schema_version"),
        (
            '{"schema_version": 1, "template_version": "old", '
            '"files": {"AGENTS.md": "bad", "AGENTS.md": "' + "a" * 64 + '"}}',
            "Duplicate.*AGENTS.md",
        ),
    ],
)
def test_invalid_records_are_rejected(content: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_installation_state(content)


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        "..",
        "../outside",
        "folder/../../outside",
        "/absolute",
        "//server/share",
        "./AGENTS.md",
        "folder/./AGENTS.md",
        "folder/../AGENTS.md",
        "folder//AGENTS.md",
        "folder/",
        "C:/outside",
        "C:outside",
        "folder\\AGENTS.md",
        "AGENTS.md:stream",
        "NUL",
        "folder/CON.txt",
        "CON/folder.txt",
        "folder./AGENTS.md",
        "folder /AGENTS.md",
        "line\nbreak",
        "null\x00byte",
        "delete\x7fbyte",
        "invalid\ud800unicode",
    ],
)
def test_unsafe_or_non_normalized_paths_are_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="Unsafe installation record path"):
        parse_installation_state(record(files={name: "a" * 64}))
