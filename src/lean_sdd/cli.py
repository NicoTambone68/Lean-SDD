"""Command-line interface for installation and local readiness diagnostics."""

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from lean_sdd.doctor import diagnose
from lean_sdd.installer import InstallError, initialize
from lean_sdd.profiles import BUILTIN_PROFILES
from lean_sdd.templates import package_version


def main(argv: Sequence[str] | None = None) -> int:
    """Return 0 on success, 1 on operational failure, or argparse's usage exit 2."""
    parser = argparse.ArgumentParser(
        prog="lean-sdd", description="Install the Lean-SDD GitHub workflow."
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {package_version()}"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser(
        "init", help="Install workflow files without overwriting conflicts."
    )
    init.add_argument("directory", nargs="?", type=Path, default=Path("."))
    init.add_argument(
        "--dry-run", action="store_true", help="Check and list changes without writing."
    )
    init.add_argument("--language", help="Select a supported single root profile.")
    commands.add_parser("languages", help="List supported bundled language profiles.")
    doctor = commands.add_parser(
        "doctor", help="Check local setup without network access."
    )
    doctor.add_argument("directory", nargs="?", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    try:
        if args.command == "languages":
            for profile in BUILTIN_PROFILES.profiles:
                print(f"{profile.id}: {profile.display_name}")
            return 0
        if args.command == "init":
            result = initialize(
                args.directory, dry_run=args.dry_run, language=args.language
            )
            print(f"Profiles: {', '.join(result.profiles)}")
            for component in result.configuration.components:
                print(
                    f"Component {component.id}: {component.path} "
                    f"[{', '.join(component.profiles)}]"
                )
            for name in result.preserved:
                print(f"Preserved existing configuration: {name}")
            for name in result.created:
                print(f"{'Would create' if args.dry_run else 'Created'} {name}")
            print(f"{len(result.unchanged)} identical files left unchanged.")
            if not args.dry_run:
                print(
                    "Workflow installed. Read .agents/README.md "
                    "and run lean-sdd doctor."
                )
                print(
                    "Application scaffolding and GitHub live acceptance "
                    "remain separate steps."
                )
            return 0
        checks = diagnose(args.directory)
        for check in checks:
            print(f"{check.status}: {check.message}")
        print(
            "Local checks only: no network access, "
            "credential verification, or project tests."
        )
        print(
            "Follow .agents/README.md for repository selection "
            "and live MCP verification."
        )
        return 1 if any(check.status == "FAIL" for check in checks) else 0
    except (InstallError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
