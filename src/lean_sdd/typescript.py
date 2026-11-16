"""Bounded, non-executing inspection of the Node/npm profile.

No tool, configuration module, package script, dependency, or environment file is
executed here. Declared compatibility is distinct from real toolchain acceptance.
"""

import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, NoReturn

from lean_sdd.configuration import Check, Component
from lean_sdd.paths import safe_relative_path

MAX_METADATA_BYTES = 1024 * 1024
MAX_LOCK_BYTES = 8 * MAX_METADATA_BYTES
NODE_ENGINE = ">=26.13.1 <27"
NPM_VERSION = "11.20.0"
SCRIPT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9:_.-]{0,127}")


@dataclass(frozen=True)
class Observation:
    """A safe metadata observation, never evidence that project commands passed."""

    status: Literal["PASS", "WARN", "FAIL"]
    message: str


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field.")
        result[key] = value
    return result


def _constant(value: str) -> NoReturn:
    raise ValueError("Non-finite JSON constant.")


def _jsonc(text: str) -> str:
    """Remove comments/trailing commas outside JSON strings, preserving newlines."""
    output = list(text)
    quoted = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            index += 1
            continue
        if char == '"':
            quoted = True
        elif text.startswith("//", index):
            end = text.find("\n", index + 2)
            end = len(text) if end < 0 else end
            output[index:end] = " " * (end - index)
            index = end
            continue
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise ValueError("Unterminated JSON comment.")
            end += 2
            for position in range(index, end):
                if output[position] not in "\r\n":
                    output[position] = " "
            index = end
            continue
        index += 1
    # Comments have been replaced by whitespace; only commas outside strings
    # immediately before an object/array terminator can be trailing commas.
    quoted = escaped = False
    for index, char in enumerate(output):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == ",":
            following = index + 1
            while following < len(output) and output[following].isspace():
                following += 1
            if following < len(output) and output[following] in "}]":
                output[index] = " "
    return "".join(output)


def _safe_path(path: Path, *, directory: bool = False) -> bool:
    """Reject unsafe ancestors and entries, distinguishing absence from failures."""
    for parent in reversed(path.parents):
        try:
            mode = parent.lstat().st_mode
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(mode):
            raise ValueError("Unsafe ancestor.")
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
        raise ValueError("Unsafe entry.")
    return True


def _read_object(
    path: Path, limit: int, *, comments: bool = False
) -> dict[str, object]:
    if not _safe_path(path):
        raise FileNotFoundError
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError("Metadata exceeds its byte limit.")
    text = content.decode("utf-8")
    value: object = json.loads(
        _jsonc(text) if comments else text,
        object_pairs_hook=_pairs,
        parse_constant=_constant,
    )
    if not isinstance(value, dict):
        raise ValueError("Metadata must be an object.")
    return value


def npm_script(argv: tuple[str, ...]) -> str | None:
    """Accept only the reviewed npm-run adapter, without optional/forwarded flags."""
    if (
        len(argv) == 3
        and argv[:2] == ("npm", "run")
        and SCRIPT_NAME.fullmatch(argv[2]) is not None
    ):
        return argv[2]
    return None


def _package_contract(package: dict[str, object], checks: tuple[Check, ...]) -> None:
    if "workspaces" in package:
        raise ValueError("npm workspaces require separate support.")
    if package.get("type") not in ("module", "commonjs"):
        raise ValueError("package.json must explicitly select module or commonjs.")
    manager = package.get("packageManager")
    if (
        not isinstance(manager, str)
        or re.fullmatch(
            rf"npm@{re.escape(NPM_VERSION)}(?:\+sha(?:224|256|384|512)\.[a-fA-F0-9]+)?",
            manager,
        )
        is None
    ):
        raise ValueError(f"packageManager must pin npm@{NPM_VERSION}.")
    engines = package.get("engines")
    if not isinstance(engines, dict) or engines.get("node") != NODE_ENGINE:
        raise ValueError(f"engines.node must declare {NODE_ENGINE}.")
    scripts = package.get("scripts")
    if not isinstance(scripts, dict):
        raise ValueError("package.json requires reviewed scripts.")
    for check in checks:
        name = npm_script(check.argv)
        if name is None:
            raise ValueError("Required checks must use npm run with a script name.")
        script = scripts.get(name)
        if not isinstance(script, str) or not script.strip() or "\0" in script:
            raise ValueError(
                f"Required script missing or invalid for check {check.name}."
            )


def _lock_contract(lock: dict[str, object], package: dict[str, object] | None) -> None:
    if type(lock.get("lockfileVersion")) is not int or lock["lockfileVersion"] != 3:
        raise ValueError("package-lock.json must use lockfileVersion 3.")
    packages = lock.get("packages")
    if not isinstance(packages, dict) or not isinstance(packages.get(""), dict):
        raise ValueError("package-lock.json requires its root package metadata.")
    if package is not None:
        for field in (
            "name",
            "version",
            "dependencies",
            "devDependencies",
            "optionalDependencies",
        ):
            if package.get(field) != packages[""].get(field):
                raise ValueError(
                    "Lock root metadata differs from package.json; review npm ci."
                )


def _tsconfig_contract(
    config: dict[str, object], root: Path, component: Component
) -> None:
    if "extends" in config or "references" in config:
        raise ValueError("tsconfig inheritance/references require separate support.")
    options = config.get("compilerOptions")
    if not isinstance(options, dict):
        raise ValueError("tsconfig requires explicit compilerOptions.")
    if any(
        options.get(name) is not True
        for name in ("strict", "noEmitOnError", "declaration")
    ):
        raise ValueError("strict, noEmitOnError and declaration must be true.")
    if any(
        name in options and options[name] is not True
        for name in (
            "noImplicitAny",
            "noImplicitThis",
            "strictNullChecks",
            "strictFunctionTypes",
            "strictBindCallApply",
            "strictPropertyInitialization",
            "strictBuiltinIteratorReturn",
            "alwaysStrict",
            "useUnknownInCatchVariables",
        )
    ):
        raise ValueError("Individual strict compiler checks cannot be disabled.")
    if options.get("module") not in ("NodeNext", "nodenext") or options.get(
        "moduleResolution"
    ) not in ("NodeNext", "nodenext"):
        raise ValueError("module and moduleResolution must be NodeNext.")
    if options.get("target") not in ("ES2023", "es2023"):
        raise ValueError("target must explicitly select ES2023.")
    if (
        options.get("noCheck") is True
        or options.get("noEmit") is True
        or "outFile" in options
        or "declarationDir" in options
    ):
        raise ValueError(
            "Use outDir for emitted builds; output overrides are unsupported."
        )
    for field in ("rootDir", "outDir"):
        value = options.get(field)
        if not isinstance(value, str) or (
            value != "." and not safe_relative_path(value)
        ):
            raise ValueError(
                "rootDir/outDir must be normalized component-relative paths."
            )
        destination = component.path / PurePosixPath(value)
        if not destination.is_relative_to(PurePosixPath("src")):
            raise ValueError(
                "Source and generated output must stay under repository src/."
            )
        _safe_path(root / destination, directory=True)


def inspect_typescript(
    root: Path, component: Component, checks: tuple[Check, ...]
) -> tuple[Observation, ...]:
    """Inspect known metadata without executing or rewriting any project file.

    Missing setup is advisory here but blocks validation. Malformed, oversized,
    inaccessible or unsafe input fails without printing raw values or exceptions.
    Symlinks are refused; this is not protection against concurrent hostile edits.
    """
    directory = root / component.path
    results: list[Observation] = []
    metadata: dict[str, dict[str, object]] = {}
    for name, limit in (
        ("package.json", MAX_METADATA_BYTES),
        ("package-lock.json", MAX_LOCK_BYTES),
        ("tsconfig.json", MAX_METADATA_BYTES),
    ):
        try:
            metadata[name] = _read_object(
                directory / name, limit, comments=name == "tsconfig.json"
            )
        except FileNotFoundError:
            results.append(
                Observation(
                    "WARN",
                    f"Missing {name}; prepare the TypeScript project separately.",
                )
            )
        except (OSError, ValueError, RecursionError):
            results.append(
                Observation(
                    "FAIL",
                    f"Cannot read valid bounded {name}; "
                    "check syntax, size, access and safe paths.",
                )
            )
    required = tuple(
        check
        for check in checks
        if check.component == component.id
        and check.profile == "typescript"
        and check.required
        and check.category in {"types", "lint", "format", "tests", "build"}
    )
    for name, metadata_value in metadata.items():
        try:
            if name == "package.json":
                _package_contract(metadata_value, required)
            elif name == "package-lock.json":
                _lock_contract(metadata_value, metadata.get("package.json"))
            else:
                _tsconfig_contract(metadata_value, root, component)
        except OSError:
            results.append(
                Observation("FAIL", "Cannot inspect TypeScript source/output paths.")
            )
        except ValueError as error:
            results.append(Observation("FAIL", str(error)))
        else:
            results.append(
                Observation(
                    "PASS",
                    f"{name} declarations satisfy the profile; "
                    "commands and installed tool versions not verified.",
                )
            )
    for name in (
        "yarn.lock",
        "pnpm-lock.yaml",
        "bun.lock",
        "bun.lockb",
        "npm-shrinkwrap.json",
    ):
        try:
            if _safe_path(directory / name):
                results.append(
                    Observation(
                        "FAIL",
                        f"Conflicting {name}; "
                        "preserve and review the project's package manager.",
                    )
                )
        except (OSError, ValueError):
            results.append(Observation("FAIL", f"Unsafe or inaccessible {name}."))
    return tuple(results)
