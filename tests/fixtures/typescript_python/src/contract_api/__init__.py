"""Versioned Python side of the local TypeScript message acceptance fixture."""


def request(value: int) -> dict[str, int]:
    """Construct a versioned safe-integer request."""
    if type(value) is not int or not -(2**53 - 1) <= value < 2**53 - 1:
        raise ValueError("Expected an incrementable safe integer.")
    return {"version": 1, "value": value}


def response(value: object) -> int:
    """Validate the Node response at the Python runtime boundary."""
    if (
        not isinstance(value, dict)
        or type(value.get("version")) is not int
        or value["version"] != 1
        or type(value.get("result")) is not int
        or not -(2**53 - 1) <= value["result"] <= 2**53 - 1
    ):
        raise ValueError("Invalid response.")
    result: int = value["result"]
    return result
