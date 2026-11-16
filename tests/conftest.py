"""Keep real external-tool acceptance explicit and separate from unit tests."""

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
