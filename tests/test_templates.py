"""Tests for Lean-SDD template utilities."""

from importlib.metadata import version

from lean_sdd.templates import package_version


def test_package_version() -> None:
    """Verify that the CLI uses the correct distribution metadata."""
    assert package_version() == version("lean-sdd")
