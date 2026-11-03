"""Token tables for the native fuzzy-name coverage score.

A table holds every distinct title token once, each title's token positions and the Unicode code
points of each token, so the native matcher reads the same word boundaries the Python regular
expression produces without retokenizing the catalogue per query. One table belongs to one title
order: a projection builds one per display language for its course rows, and a caller without a
projection builds one for the rows it supplies.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

import numpy

_WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class LookupTokenTable:
    """One title order's vocabulary, token positions and token code points."""

    vocabulary_codepoints: numpy.ndarray
    vocabulary_offsets: numpy.ndarray
    token_offsets: numpy.ndarray
    token_indices: numpy.ndarray


def title_tokens(name: str | None) -> tuple[str, ...]:
    """Return one name's word tokens in order, or none for an absent name."""
    return () if name is None else tuple(_WORD.findall(name))


def build_token_table(names: Sequence[str | None]) -> LookupTokenTable:
    """Build one token table in the supplied title order."""
    titles = tuple(title_tokens(name) for name in names)
    vocabulary = tuple(sorted({token for tokens in titles for token in tokens}))
    positions = {token: index for index, token in enumerate(vocabulary)}
    token_indices: list[int] = []
    token_offsets = [0]
    for tokens in titles:
        token_indices.extend(positions[token] for token in tokens)
        token_offsets.append(len(token_indices))
    codepoints: list[int] = []
    vocabulary_offsets = [0]
    for token in vocabulary:
        codepoints.extend(ord(character) for character in token)
        vocabulary_offsets.append(len(codepoints))
    return LookupTokenTable(
        vocabulary_codepoints=numpy.asarray(codepoints, dtype=numpy.int32),
        vocabulary_offsets=numpy.asarray(vocabulary_offsets, dtype=numpy.int32),
        token_offsets=numpy.asarray(token_offsets, dtype=numpy.int32),
        token_indices=numpy.asarray(token_indices, dtype=numpy.int32),
    )
