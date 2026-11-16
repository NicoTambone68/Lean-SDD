"""Shared lexical path validation for records, configuration and resources."""

import re
from pathlib import PurePosixPath


def safe_relative_path(name: str) -> bool:
    """Accept normalized portable relative paths for files or directories."""
    path = PurePosixPath(name)
    return (
        bool(path.parts)
        and not path.is_absolute()
        and path.as_posix() == name
        and ".." not in path.parts
        and not any(character in name for character in "\\:")
        and not any(ord(character) < 32 or ord(character) == 127 for character in name)
        and not any(0xD800 <= ord(character) <= 0xDFFF for character in name)
        # Windows device names are unsafe even when inspecting a record on POSIX.
        and not any(
            re.fullmatch(
                r"CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|(?:COM|LPT)[1-9¹²³]",
                part.partition(".")[0].rstrip(" ").upper(),
            )
            for part in path.parts
        )
        and all(not part.endswith((".", " ")) for part in path.parts)
    )
