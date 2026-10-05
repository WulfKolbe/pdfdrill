"""879 Phase 0 — the conformance harness, before any feature it measures.

pdf2mmd is to become a complete MathPix replacement with a fully compatible
`lines.json`. Nothing could say how far from that it was, so "full compatible"
was an opinion — and an opinion about a vocabulary of eighteen-plus line types
is not something anyone can act on or finish.

These tests pin the three properties that make the harness worth trusting:
it compares the right thing, it does not touch what it measures, and it does
not pretend MathPix is truth.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfdrill import mathpix_conformance as MC                 # noqa: E402


def _doc(types_and_fields):
    """A lines.json-shaped document: [(type, {field: value}), ...]."""
    return {"pages": [{"lines": [dict(t | {"type": ty})
                                 for ty, t in types_and_fields]}]}


# --------------------------------------------------------------------------
# What it measures.
# --------------------------------------------------------------------------

def test_a_type_the_reference_emits_and_we_do_not_is_missing():
    ref = _doc([("text", {}), ("simple_cell", {}), ("simple_cell", {})])
    ours = _doc([("text", {})])
    r = MC.compare(ref, ours)
    assert r["missing_types"] == {"simple_cell": 2}
    assert r["types_covered"] == 1 and r["types_in_reference"] == 2


def test_a_type_only_we_emit_is_additive_not_a_failure():
    """A MathPix consumer ignores an unknown type. Our `column` and `code` are
    information MathPix does not carry; they are not non-compliance."""
    ref = _doc([("text", {})])
    ours = _doc([("text", {}), ("code", {})])
    r = MC.compare(ref, ours)
    assert r["missing_types"] == {}
    assert r["extra_types"] == {"code": 1}


def test_missing_fields_are_reported_separately_from_types():
    """The four `cell_*` fields ARE the table geometry. Emitting a
    `simple_cell` without them would score as covered and carry nothing."""
    ref = _doc([("simple_cell", {"cell_row": 0, "cell_column": 1})])
    ours = _doc([("simple_cell", {})])
    r = MC.compare(ref, ours)
    assert r["missing_types"] == {}, "the type IS emitted"
    assert set(r["missing_fields"]) == {"cell_row", "cell_column"}


def test_it_counts_distributions_and_says_so():
    """NOT a 1:1 alignment. The readers segment differently — 1,068 lines
    against 993 on the same 26 pages — so an alignment needs a region-overlap
    threshold and every number would carry it. "This type appears 55 times and
    zero times" needs no threshold."""
    ref = _doc([("text", {})] * 50)
    ours = _doc([("text", {})] * 3)
    r = MC.compare(ref, ours)
    assert r["missing_types"] == {}, "same vocabulary, different segmentation"
    out = MC.render(r, "x")
    assert "DISTRIBUTIONS, not an alignment" in out
    assert "never whether a given line is right" in out


def test_the_headline_is_types_covered_over_types_in_the_reference():
    ref = _doc([("text", {}), ("math", {}), ("table", {}), ("chart", {})])
    ours = _doc([("text", {}), ("math", {})])
    r = MC.compare(ref, ours)
    assert (r["types_covered"], r["types_in_reference"]) == (2, 4)
    assert "2 of 4 MathPix line types emitted" in MC.render(r, "x")


# --------------------------------------------------------------------------
# Which reading counts as the reference.
# --------------------------------------------------------------------------

def test_the_backup_is_the_reference_when_one_exists(tmp_path):
    """845 parks a displaced MathPix reading at `.lines.mathpix.bak.json`."""
    pdf = tmp_path / "d.pdf"; pdf.write_bytes(b"%PDF-1.7\n")
    (tmp_path / "d.lines.mathpix.bak.json").write_text('{"pages":[]}')
    (tmp_path / "d.lines.json").write_text('{"pages":[],"source":"pdfminer-docmodel"}')
    assert MC.reference_for(pdf).name == "d.lines.mathpix.bak.json"


def test_our_own_reading_is_never_used_as_the_reference(tmp_path):
    """Measuring ourselves against ourselves would report perfect conformance
    and mean nothing. `source` identifies our reader since 846."""
    pdf = tmp_path / "d.pdf"; pdf.write_bytes(b"%PDF-1.7\n")
    (tmp_path / "d.lines.json").write_text(
        '{"pages":[],"source":"pdfminer-docmodel"}')
    assert MC.reference_for(pdf) is None


def test_a_pre_846_reading_of_OURS_is_recognised_without_a_source_key(tmp_path):
    """The ambiguous case, and it is real: sigma26-075's live lines.json has NO
    `source`, because our reader wrote it before 846 added the key. The line
    FIELDS settle it — `deferred_glyphs` is a concept MathPix does not have."""
    pdf = tmp_path / "d.pdf"; pdf.write_bytes(b"%PDF-1.7\n")
    (tmp_path / "d.lines.json").write_text(json.dumps(
        {"pages": [{"lines": [{"type": "text", "deferred_glyphs": []}]}]}))
    assert MC.reference_for(pdf) is None, (
        "a reading of ours without a source key must not become the reference")


def test_a_genuine_mathpix_reading_without_a_source_key_is_accepted(tmp_path):
    pdf = tmp_path / "d.pdf"; pdf.write_bytes(b"%PDF-1.7\n")
    (tmp_path / "d.lines.json").write_text(json.dumps(
        {"pages": [{"lines": [{"type": "text", "cnt": [], "confidence": 1}]}]}))
    assert MC.reference_for(pdf).name == "d.lines.json"


# --------------------------------------------------------------------------
# What it must not do.
# --------------------------------------------------------------------------

def test_the_harness_writes_nothing():
    """A conformance check that modified the artefact it checks would be the
    worst kind of instrument. Our reading is built in memory, every run."""
    import inspect
    from pdfdrill import commands
    src = inspect.getsource(commands.cmd_conformance)
    for forbidden in ("_atomic_write", "open(", ".write_text(", ".write_bytes("):
        assert forbidden not in src.replace("json.load(open(", ""), forbidden
    assert "_dm.build(" in src, "our side must be built, not read from disk"


def test_the_reference_is_not_called_truth():
    """MathPix is the richest available reading and the compatibility TARGET.
    A type we do not emit is a gap in compatibility; it is not evidence that
    our reading is wrong, and the module must not say it is."""
    doc = Path(MC.__file__).read_text(encoding="utf-8")
    assert "MATHPIX IS NOT TRUTH" in doc
    assert "never says it is" in doc


# --------------------------------------------------------------------------
# Coverage per shared type. "Emitted" and "covered" are different claims.
# --------------------------------------------------------------------------

def test_a_type_can_be_emitted_and_barely_covered():
    """THE REASON THIS COLUMN EXISTS, and it found two cases in its first run.
    Emitting `equation_number` moved the headline from 8 of 18 to 9 of 18
    while finding 13 of the reference's 40 — a tick in the type column that
    would have read as finished. The same run then showed `page_info` at 20 of
    52, a type counted as covered since the beginning."""
    ref = _doc([("equation_number", {})] * 40 + [("text", {})] * 10)
    ours = _doc([("equation_number", {})] * 13 + [("text", {})] * 10)
    r = MC.compare(ref, ours)
    assert r["missing_types"] == {}, "the type IS emitted"
    assert r["coverage"]["equation_number"] == {
        "reference": 40, "ours": 13, "ratio": 0.325}
    assert "equation_number" in r["thin_types"]
    assert "text" not in r["thin_types"], "a fully covered type is not thin"
    out = MC.render(r, "x")
    assert "THINLY COVERED" in out and "13 of 40" in out


def test_a_type_we_over_emit_is_not_thin():
    """Finding MORE than the reference is not under-coverage. It may be a
    defect in either reader, and this module does not adjudicate that."""
    ref = _doc([("text", {})] * 5)
    ours = _doc([("text", {})] * 50)
    r = MC.compare(ref, ours)
    assert r["thin_types"] == {}
    assert r["coverage"]["text"]["ratio"] == 10.0


# --------------------------------------------------------------------------
# Phase 1 — equation_number, split out in the EXPORT.
# --------------------------------------------------------------------------

def test_equation_number_is_split_in_the_export_not_the_model():
    r"""879 Phase 1. `LINE_TYPES` declared `equation_number` and
    `classify_lines` assigned it ZERO times, because `absorb_equation_numbers`
    joins the number to its display before classification sees it.

    That absorption stays — 739 measured what happens without it: two numbered
    displays fused into one `aligned`, and the numbers surviving as loose prose
    that `to_markdown` dropped and `to_latex` printed twice. So the model keeps
    the number absorbed and the EXPORT splits it out, which is the rule
    `_mp_type` already states for `math`/`equation`."""
    from pdfreader import docmodel_six as dm
    import inspect
    src = inspect.getsource(dm._split_equation_numbers)
    # it runs on the EXPORT, after the containers and the run-in split
    assert "_split_equation_numbers(out, pages, k)" in inspect.getsource(
        dm.to_lines_json)
    # and it re-identifies the glyphs rather than re-measuring them
    assert "equation_number(ln" in src
    assert "column_of(p, ln)" in src


def test_a_line_that_is_only_a_number_is_not_split():
    """Splitting it would leave an empty host line where the equation was."""
    from pdfreader import docmodel_six as dm
    import inspect
    src = inspect.getsource(dm._split_equation_numbers)
    assert "if not body:" in src
    assert "already its own line" in src
