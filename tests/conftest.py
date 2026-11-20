"""Keep real external-tool acceptance explicit and separate from unit tests."""

from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, TextIO

import pytest

# These project tests run only inside the explicit cross-language harness.
collect_ignore = ["fixtures/typescript_python"]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-typescript",
        action="store_true",
        help="Run real TypeScript acceptance, including npm ci in temporary projects",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--run-typescript"):
        return
    for item in items:
        if "typescript_toolchain" in item.keywords:
            item.add_marker(
                pytest.mark.skip(
                    reason="Real toolchain acceptance needs --run-typescript"
                )
            )


@pytest.fixture
def deny_file_read(monkeypatch: pytest.MonkeyPatch) -> Callable[[Path], None]:
    """Simulate a read denial at open even when tests run as a privileged user."""

    def deny(unreadable: Path) -> None:
        original = Path.open

        def fail_metadata(
            self: Path,
            mode: str = "r",
            buffering: int = -1,
            encoding: str | None = None,
            errors: str | None = None,
            newline: str | None = None,
        ) -> BinaryIO | TextIO:
            if self == unreadable:
                raise PermissionError("private filesystem detail")
            if mode == "rb":
                return original(self, "rb", buffering=buffering)
            assert mode == "r"
            return original(
                self,
                "r",
                buffering=buffering,
                encoding=encoding,
                errors=errors,
                newline=newline,
            )

        monkeypatch.setattr(Path, "open", fail_metadata)

    return deny
