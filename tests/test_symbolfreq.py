"""277 — the frequency check, and the honest limit of it.

It catches all 11 of 2010.14265's turnstile substitutions — matching the arity
check of out/210 exactly — plus one arity structurally cannot see. Corpus-wide
it flags 37,505 occurrences that are mostly ordinary mathematics, which is why
it is a module and not a command.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.symbolfreq import (norm_shape, occurrences, flags, specific,
                                 relation_pairs, check)


def _lines(*texts):
    """Distinct text per line — occurrences() de-duplicates on text, so a
    fixture repeating one string collapses to a single occurrence."""
    return [{"type": "text", "text": t + (" %% %d" % i), "_page": i + 1}
            for i, t in enumerate(texts)]


def test_the_position_key_is_token_local_not_the_whole_fragment():
    """`X \\nVdash_{P} Y \\mid \\boldsymbol{S}` and `X \\Perp_{P} Y` are the same
    RELATIONAL position. A whole-fragment key made them different and matched
    only 5 of 11; a character window cut through `_{P}` and matched none."""
    a = r"X \Perp_{P} Y"
    b = r"X \nVdash_{P} Y \mid \boldsymbol{S}"
    ka = norm_shape(a, a.index("\\Perp"), a.index("\\Perp") + 5)
    kb = norm_shape(b, b.index("\\nVdash"), b.index("\\nVdash") + 7)
    assert ka == kb == "V§_{V}V"


def test_a_rare_spelling_against_a_dominant_sibling_is_flagged():
    rows = _lines(*([r"\(X \Perp_{P} Y\)"] * 8 + [r"\(X \nVdash_{P} Y\)"]))
    f = check(rows)
    assert [(r["rare"], r["rare_count"], r["common"]) for r in f] == \
        [("\\nVdash", 1, "\\Perp")]


def test_an_even_split_is_not_flagged():
    rows = _lines(*([r"\(X \Perp_{P} Y\)"] * 5 + [r"\(X \nVdash_{P} Y\)"] * 5))
    assert check(rows) == []


def test_a_negation_sharing_its_positives_position_is_never_a_substitution():
    rows = _lines(*([r"\(X \in \boldsymbol{Y}\)"] * 20 + [r"\(X \notin \boldsymbol{Y}\)"]))
    assert check(rows) == []


def test_styling_macros_are_excluded():
    rows = _lines(*([r"\(\boldsymbol{X}\)"] * 20 + [r"\(\mathbf{X}\)"]))
    assert check(rows) == []


def test_lines_repeated_under_several_types_are_counted_once():
    """MathPix repeats a string under `text` and `diagram`; counting both
    inflates every spelling by its container count."""
    t = r"\(X \Perp_{P} Y\)"
    dup = [{"type": "text", "text": t}, {"type": "diagram", "text": t},
           {"type": "list_item", "text": t}]
    assert len(occurrences(dup)) == 1


def test_the_tier_split_is_on_the_position_carrying_an_index():
    rows = _lines(*([r"\(X \Perp_{P} Y\)"] * 8 + [r"\(X \nVdash_{P} Y\)"]
                    + [r"\(A \cup B\)"] * 8 + [r"\(A \star B\)"]))
    f = check(rows)
    assert {r["tier"] for r in specific(f)} == {"specific"}
    assert all("_" in r["shape"] or "^" in r["shape"] for r in specific(f))
    assert any(r["tier"] == "generic" for r in f)


def test_relation_pairs_keeps_only_relation_against_relation():
    rows = _lines(*([r"\(X \Perp_{P} Y\)"] * 8 + [r"\(X \nVdash_{P} Y\)"]
                    + [r"\(Z_{\alpha} W\)"] * 8 + [r"\(Z_{\lambda} W\)"]))
    rp = relation_pairs(check(rows))
    assert [r["rare"] for r in rp] == ["\\nVdash"]
