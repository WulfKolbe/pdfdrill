"""
semantic/units.py — the seed unit lexicon (L6 quantity sublayer, S1.1).
Pure stdlib: symbol → (canonical, dimension, factor) tables + parse/convert/
dimension. `convert` returns None on a dimension mismatch — grounded absence,
never a guess.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic import units as U


def test_parse_known_units():
    for sym, dim in [("%", "ratio"), ("‰", "ratio"),
                     ("USD", "currency"), ("$", "currency"), ("EUR", "currency"),
                     ("€", "currency"), ("ct", "currency"), ("Cent", "currency"),
                     ("s", "time"), ("min", "time"), ("h", "time"), ("ms", "time"),
                     ("B", "data"), ("KB", "data"), ("MB", "data"), ("GB", "data")]:
        u = U.parse_unit(sym)
        assert u is not None, f"parse_unit({sym!r}) -> None"
        assert U.dimension(u) == dim, f"{sym}: {U.dimension(u)} != {dim}"
    assert U.parse_unit("xyzzy") is None


def test_currency_conversion_dollar_to_cent():
    # $2 → 200 ct
    assert U.convert(2, "$", "ct") == 200.0
    assert U.convert(200, "ct", "USD") == 2.0


def test_ratio_units():
    # % is a dimensionless ratio; canonical form is the plain fraction
    assert U.dimension(U.parse_unit("%")) == "ratio"
    assert U.convert(82, "%", "") == 0.82         # "" = the canonical bare ratio
    assert U.convert(5, "‰", "%") == 0.5


def test_convert_dimension_mismatch_is_none():
    # money → time is meaningless: grounded absence, never a guess
    assert U.convert(2, "USD", "min") is None
    assert U.convert(1, "GB", "%") is None


def test_time_and_data_conversions():
    assert U.convert(2, "min", "s") == 120.0
    assert U.convert(1500, "ms", "s") == 1.5
    assert U.convert(1, "GB", "MB") == 1000.0


def test_count_nouns():
    for n in ["facts", "triples", "statements", "entities", "tokens", "pairs",
              "relations", "subjects", "objects", "annotations", "pages",
              "parameters"]:
        assert n in U.COUNT_NOUNS, f"{n} missing from COUNT_NOUNS"
    assert "bananas" not in U.COUNT_NOUNS


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
