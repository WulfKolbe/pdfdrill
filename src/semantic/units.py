"""
Unit lexicon — the seed unit/dimension tables for the quantity sublayer
(L6, S1.1). Pure stdlib, deliberately small: the units the reference corpus
(2303.11082-class papers + commercial documents) actually uses. This is the
first implemented step of L8's "unit/quantity ontologies for numeric facts";
external ontology grounding (QUDT etc. via OP.GROUND) remains open.

Model: every unit maps to (canonical_symbol, dimension, factor) where
`value_in_canonical = value * factor`. Canonical units per dimension:
    ratio     ""    (the bare fraction: 82% → 0.82)
    currency  "ct"  (integer-friendly cents; $2 → 200 ct)
    time      "s"
    data      "B"
`convert(value, a, b)` returns None when the dimensions differ — grounded
absence, never a guess (the same honesty rule the extractors follow).

`COUNT_NOUNS` names the discrete count-nouns a bare integer can quantify
("5,550,689 facts") so the quantity extractor can type `count` records.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Unit:
    symbol: str          # as parsed
    canonical: str       # the dimension's canonical symbol
    dim: str             # dimension name
    factor: float        # value_in_canonical = value * factor


# symbol -> (canonical, dimension, to_canonical_factor)
UNITS: dict[str, tuple[str, str, float]] = {
    # dimensionless ratios (canonical: the bare fraction, symbol "")
    "":      ("", "ratio", 1.0),
    "%":     ("", "ratio", 0.01),
    "‰":     ("", "ratio", 0.001),
    # currency (canonical: cents — integer-friendly)
    "ct":    ("ct", "currency", 1.0),
    "Cent":  ("ct", "currency", 1.0),
    "cent":  ("ct", "currency", 1.0),
    "USD":   ("ct", "currency", 100.0),
    "$":     ("ct", "currency", 100.0),
    "EUR":   ("ct", "currency", 100.0),
    "€":     ("ct", "currency", 100.0),
    # time (canonical: seconds)
    "s":     ("s", "time", 1.0),
    "ms":    ("s", "time", 0.001),
    "min":   ("s", "time", 60.0),
    "h":     ("s", "time", 3600.0),
    # data (canonical: bytes; decimal SI multiples)
    "B":     ("B", "data", 1.0),
    "KB":    ("B", "data", 1e3),
    "MB":    ("B", "data", 1e6),
    "GB":    ("B", "data", 1e9),
}

# Discrete things a bare integer counts ("5,550,689 facts", "29 pages").
COUNT_NOUNS: frozenset[str] = frozenset({
    "facts", "triples", "statements", "entities", "tokens", "pairs",
    "relations", "subjects", "objects", "annotations", "pages", "parameters",
})


def parse_unit(s: str) -> Optional[Unit]:
    """The Unit behind a symbol, or None if unknown. Exact-symbol lookup
    (a fuzzy layer can sit on top later; the lexicon stays strict)."""
    if s is None:
        return None
    entry = UNITS.get(s.strip())
    if entry is None:
        return None
    canonical, dim, factor = entry
    return Unit(symbol=s.strip(), canonical=canonical, dim=dim, factor=factor)


def dimension(u: "Unit | str | None") -> Optional[str]:
    """The dimension of a Unit or a raw symbol; None when unknown."""
    if u is None:
        return None
    if isinstance(u, Unit):
        return u.dim
    parsed = parse_unit(u)
    return parsed.dim if parsed else None


def convert(value: float, from_u: str, to_u: str) -> Optional[float]:
    """Convert `value` between two unit symbols. None on an unknown unit or a
    dimension mismatch (money → time is meaningless) — never a guess."""
    a, b = parse_unit(from_u), parse_unit(to_u)
    if a is None or b is None or a.dim != b.dim:
        return None
    # round off binary-representation noise (0.8200000000000001 → 0.82); the
    # factors are exact decimals, so 12 significant-decimal digits are safe.
    return round(value * a.factor / b.factor, 12)
