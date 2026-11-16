"""Real Node message interaction, enabled only inside the acceptance harness."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from contract_api import request, response


def test_message_contract() -> None:
    peer = Path(os.environ["LEAN_SDD_TYPESCRIPT_PEER"])
    completed = subprocess.run(
        ["node", str(peer / "tests/worker.mjs")],
        input=json.dumps(request(41)),
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    assert response(json.loads(completed.stdout)) == 42


def test_node_rejects_incompatible_message() -> None:
    peer = Path(os.environ["LEAN_SDD_TYPESCRIPT_PEER"])
    completed = subprocess.run(
        ["node", str(peer / "tests/worker.mjs")],
        input=json.dumps({"version": 2, "value": 41}),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode != 0
    assert "Invalid versioned request" in completed.stderr


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"version": 1, "result": "42"},
        {"version": True, "result": 42},
        {"version": 1, "result": 2**53},
    ],
)
def test_python_rejects_invalid_response(value: object) -> None:
    with pytest.raises(ValueError, match="Invalid response"):
        response(value)
