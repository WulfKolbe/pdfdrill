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


def test_the_gaps_are_named_as_gaps_not_buried():
    """Three IGNORED entries are content being dropped, and the contract says
    so rather than letting 'ignored' read as 'fine'."""
    g = tc.gaps()
    assert set(g) == {"code", "molecule", "table_split_cell"}
    assert g["code"] > 40000, "code is the largest unread type in the corpus"


def test_the_inventory_records_how_it_was_taken():
    prov = json.loads(tc.INVENTORY.read_text(encoding="utf-8"))["_provenance"]
    for k in ("scanned", "line_objects", "method", "producer", "taken"):
        assert prov.get(k), f"inventory provenance missing {k}"
    assert "MathPix only" in prov["producer"], \
        "the inventory must say whose output it is — out/249"


def test_list_item_is_claimed_now():
    """out/248. It was the violation this contract would have caught."""
    assert "list_item" in tc.CLAIMED and "list_items" in tc.CLAIMED["list_item"]
