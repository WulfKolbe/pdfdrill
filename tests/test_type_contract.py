"""250 — every corpus type is named by a module or ignored with a reason.

ONE DIRECTION. The reverse was dropped: out/249 established that "equation",
"figure" and "caption" occur zero times in 4.0M MathPix line objects and are
all live — emitted by the visionocr route or asserted by tests. A literal
absent from today's corpus is not a defect.
"""
import json
import re
from pathlib import Path

import pytest

from docmodel import type_contract as tc

ROOT = Path(__file__).resolve().parent.parent
MODULES = ROOT / "src" / "docmodel" / "modules"


def test_no_corpus_type_is_unaccounted_for():
    """The check that has teeth. A type MathPix emits and no module names
    produces nothing, breaks nothing and logs nothing — that is how list_item
    went unread in 882 documents."""
    assert tc.violations() == [], (
        "corpus types named by neither CLAIMED nor IGNORED: %s" % tc.violations())


def test_claimed_and_ignored_do_not_overlap():
    assert not (set(tc.CLAIMED) & set(tc.IGNORED))


def test_every_claimed_type_appears_in_the_module_that_claims_it():
    """Keeps the map honest: a CLAIMED entry naming a module that does not
    mention the type is a comment, not a contract."""
    sources = {p.stem: p.read_text(encoding="utf-8") for p in MODULES.glob("*.py")}
    bad = []
    for t, where in tc.CLAIMED.items():
        mods = [m.strip().split(" ")[0] for m in where.split(",")]
        if not any(f'"{t}"' in sources.get(m, "") for m in mods):
            bad.append((t, where))
    assert not bad, "CLAIMED entries no module actually mentions: %s" % bad


def test_every_ignored_type_carries_a_real_reason():
    """A type moved into IGNORED to silence the check, with a reason that does
    not survive being read aloud, defeats the check."""
    for t, why in tc.IGNORED.items():
        assert len(why) > 40, f"{t}: reason too thin to be a reason"
        assert re.match(r"^(GAP|container only|sub-element|non-content):", why), \
            f"{t}: reason must state its KIND first — {why[:40]!r}"


def test_no_type_gap_is_open():
    """259 closed all three. The check that matters is not which gaps exist but
    that a GAP entry is never left standing as if 'ignored' meant 'fine' — so
    this asserts the set is empty, and the next reopened gap has to justify
    itself here rather than appearing silently."""
    assert tc.gaps() == {}, (
        "a type GAP is open again: %s" % sorted(tc.gaps()))


def test_the_types_259_closed_are_claimed_by_name():
    for t in ("code", "molecule", "table_split_cell"):
        assert t in tc.CLAIMED, f"{t} was closed in 259 and must stay claimed"
        assert t not in tc.IGNORED


def test_the_inventory_records_how_it_was_taken():
    prov = json.loads(tc.INVENTORY.read_text(encoding="utf-8"))["_provenance"]
    for k in ("scanned", "line_objects", "method", "producer", "taken"):
        assert prov.get(k), f"inventory provenance missing {k}"
    assert "MathPix only" in prov["producer"], \
        "the inventory must say whose output it is — out/249"


def test_list_item_is_claimed_now():
    """out/248. It was the violation this contract would have caught."""
    assert "list_item" in tc.CLAIMED and "list_items" in tc.CLAIMED["list_item"]


# ---- 255: the same contract for FIELDS -----------------------------------

def test_every_corpus_field_is_named():
    from docmodel.type_contract import field_violations
    assert field_violations() == [], (
        "a field MathPix emits that no module reads and no reason names: "
        "silent loss, exactly like an unnamed type")


def test_claimed_and_ignored_fields_are_disjoint():
    from docmodel.type_contract import CLAIMED_FIELDS, IGNORED_FIELDS
    assert not (set(CLAIMED_FIELDS) & set(IGNORED_FIELDS))


def test_every_ignored_field_reason_is_categorised():
    from docmodel.type_contract import IGNORED_FIELDS
    prefixes = ("GAP:", "redundant", "non-content:", "opaque:", "carried,",
                "NOT A MATHPIX FIELD")
    for field, why in IGNORED_FIELDS.items():
        assert why.startswith(prefixes), f"{field}: uncategorised reason"
        assert len(why) > 40, f"{field}: a reason too short to have been read"


def test_the_subtype_field_moved_from_unread_to_claimed():
    # 256 — it was the largest unread field at 1,239,021 lines.
    from docmodel.type_contract import CLAIMED_FIELDS, IGNORED_FIELDS
    assert "subtype" in CLAIMED_FIELDS
    assert "subtype" not in IGNORED_FIELDS


def test_the_two_pdfdrill_written_fields_are_marked_as_such():
    # They are not MathPix gaps — we wrote them. Same writer, same 52,668 lines.
    from docmodel.type_contract import IGNORED_FIELDS, corpus_fields
    counts = corpus_fields()
    assert counts["out_of_column"] == counts["margin_role"]
    for f in ("out_of_column", "margin_role"):
        assert IGNORED_FIELDS[f].startswith("NOT A MATHPIX FIELD")


def test_no_field_gap_is_open():
    # 259 closed both: `cnt` now tightens skewed crops, `font_size` now sets
    # header levels. Same standard as the type gaps above.
    from docmodel.type_contract import field_gaps, CLAIMED_FIELDS
    assert field_gaps() == {}, "a field GAP is open again: %s" % sorted(field_gaps())
    for f in ("cnt", "font_size"):
        assert f in CLAIMED_FIELDS


def test_field_inventory_records_that_it_is_not_mathpix_only():
    import json
    from docmodel.type_contract import FIELD_INVENTORY
    prov = json.loads(FIELD_INVENTORY.read_text(encoding="utf-8"))["_provenance"]
    assert "pdfdrill writes back" in prov["producer"] or \
           "pdfdrill" in prov["producer"]
    assert prov["line_objects"] > 3_900_000
