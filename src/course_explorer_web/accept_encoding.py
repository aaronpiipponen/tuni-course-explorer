"""The one Accept-Encoding parser of the served responses.

The catalogue body and the precompressed frontend assets both answer a coding only when the request
admits it with a positive weight. A malformed weight violates the header grammar, so that coding is
treated as not acceptable rather than guessed.
"""

from __future__ import annotations

import re

_WEIGHT = re.compile(r"^(?:0(?:\.\d{0,3})?|1(?:\.0{0,3})?)$")


def accepts_encoding(header: str, encoding: str) -> bool:
    """Return whether one Accept-Encoding header admits an encoding with a positive weight."""
    for item in header.split(","):
        token, _, parameters = item.strip().partition(";")
        if token.strip().lower() != encoding:
            continue
        weight = 1.0
        for parameter in parameters.split(";"):
            name, _, value = parameter.strip().partition("=")
            if name.strip().lower() == "q":
                candidate = value.strip()
                if _WEIGHT.fullmatch(candidate) is None:
                    return False
                weight = float(candidate)
        return weight > 0
    return False
