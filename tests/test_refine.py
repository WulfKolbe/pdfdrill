"""170–174 — the refine loop, offline.

Nothing here touches the network, inkdrill or xelatex: the stages that need
them take their inputs as arguments so the decision logic can be tested on its
own. What is tested is what decides — the gate, the four validators, and the
promise that recording a proposal does not overwrite the original.
"""
import json

import pytest

from pdfdrill import refine as rf


# ---------------------------------------------------------------- stages ---

def test_stage_list_defaults_to_all_in_canonical_order():
    assert rf.parse_stages(None) == list(rf.STAGES)
    assert rf.parse_stages("") == list(rf.STAGES)


def test_stage_subset_is_reordered_canonically():
    # given out of order, the pipeline order is restored
    assert rf.parse_stages("propose,select") == ["select", "propose"]


def test_unknown_stage_is_refused_not_ignored():
    """A typo must not run zero stages and report success."""
    with pytest.raises(ValueError) as e:
        rf.parse_stages("select,propse")
    assert "propse" in str(e.value)


# ------------------------------------------------------------- ink metric ---

def test_ink_distance_is_l1_over_both_terms():
    assert rf.ink_distance({"components": 156, "holes": 36},
                           {"components": 80, "holes": 12}) == 76 + 24


def test_ink_distance_is_zero_for_identical_signatures():
    s = {"components": 12, "holes": 3}
    assert rf.ink_distance(s, dict(s)) == 0


def test_ink_distance_is_symmetric():
    a, b = {"components": 5, "holes": 1}, {"components": 9, "holes": 4}
    assert rf.ink_distance(a, b) == rf.ink_distance(b, a)


def test_missing_terms_read_as_zero_not_crash():
    assert rf.ink_distance({}, {"components": 3, "holes": 2}) == 5


# ------------------------------------------------------------ reply clean ---

@pytest.mark.parametrize("raw,want", [
    ("```latex\n$$ x^2 $$\n```", "x^2"),
    ("\\[ a+b \\]", "a+b"),
    ("$ \\frac{1}{2} $", "\\frac{1}{2}"),
    ("  x  ", "x"),
    ("", ""),
])
def test_clean_reply_strips_fences_and_delimiters(raw, want):
    assert rf._clean_reply(raw) == want


# -------------------------------------------------------------- selection ---

class _Obj:
    def __init__(self, oid, typ, props):
        self.id, self.type, self.props = oid, typ, props
        self.realizations = []

    def add_realization(self, r):
        self.realizations.append(r)


class _Doc:
    def __init__(self, objs):
        self.objects = {o.id: o for o in objs}
        self.streams = {}

    def ensure_stream(self, name):
        from docmodel.core import Stream
        return self.streams.setdefault(name, Stream(name=name))


def _doc():
    return _Doc([
        _Obj("a", "Equation", {"confidence": 0.02, "latex": "x"}),
        _Obj("b", "Formula", {"confidence": 0.4, "latex": "y"}),
        _Obj("c", "Equation", {"confidence": 0.9, "latex": "z"}),
        _Obj("d", "Equation", {"latex": "w"}),              # unscored
        _Obj("e", "Paragraph", {"confidence": 0.01}),       # not maths
    ])


def test_candidates_are_low_confidence_maths_worst_first():
    got = [o.id for o in rf.candidates(_doc(), max_conf=0.5)]
    assert got == ["a", "b"]


def test_unscored_row_is_not_a_candidate():
    """`None <= 0.5` is a TypeError, and an unscored row is not a doubted one."""
    assert "d" not in [o.id for o in rf.candidates(_doc(), max_conf=0.5)]


def test_limit_takes_the_worst_rows():
    assert [o.id for o in rf.candidates(_doc(), max_conf=0.5, limit=1)] == ["a"]


def test_bool_confidence_is_not_a_number():
    d = _Doc([_Obj("x", "Equation", {"confidence": True, "latex": "q"})])
    assert rf.candidates(d, max_conf=0.5) == []


# -------------------------------------------------------------- validate ---

def test_validate_rejects_empty_proposal():
    ok, reason, _ = rf.validate_one("", original="x")
    assert (ok, reason) == (False, rf.R_EMPTY)


def test_validate_rejects_an_unchanged_proposal():
    ok, reason, _ = rf.validate_one("x^2", original="x^2")
    assert (ok, reason) == (False, rf.R_NOCHANGE)


def test_validate_rejects_ragged_numeric_table():
    bad = r"\begin{array}{ll} = 1\ 0\ 1\ 0 \\ = 1\ 0\ 1 \end{array}"
    ok, reason, detail = rf.validate_one(bad, original="other")
    assert (ok, reason) == (False, rf.R_WIDTH)
    assert detail


def test_validate_rejects_unbalanced_environment():
    ok, reason, _ = rf.validate_one(r"\begin{aligned} x \end{aligned}\end{array}",
                                    original="other")
    assert (ok, reason) == (False, rf.R_ENV)


def test_validate_rejects_cjk():
    ok, reason, _ = rf.validate_one(r"x + \text{孔}", original="other")
    assert (ok, reason) == (False, rf.R_CJK)


def test_validate_passes_clean_value_without_compiling():
    """work=None skips the compile, so the three cheap checks stand alone."""
    ok, reason, _ = rf.validate_one("x^{2}+y^{2}", original="x", work=None)
    assert ok and reason == ""


def test_structural_checks_run_before_the_compile():
    """A malformed table compiles fine — it must never reach xelatex."""
    bad = r"\begin{array}{ll} = 1\ 0\ 1\ 0 \\ = 1\ 0\ 1 \end{array}"
    # work is a path that does not exist; if compile ran first this would not
    # be the width reason.
    ok, reason, _ = rf.validate_one(bad, original="o", work="/nonexistent/xx")
    assert reason == rf.R_WIDTH


# ---------------------------------------------------------------- record ---

def test_record_keeps_the_original_and_signs_the_change():
    doc = _doc()
    # 230: `verified_by` is now REQUIRED. It used to be a literal "ink" written
    # into the realization whatever had accepted the row, so this proposal —
    # which never said what verified it — was recorded as ink-verified anyway.
    # The accept stage sets it; a proposal reaching record_one without it is a
    # record whose provenance would be guessed, and record_one now refuses.
    prop = {"id": "a", "proposed": "x^{2}", "ink_before": 91, "ink_after": 40,
            "ink_delta": -51, "basis": "inferred", "author": "minimax-m3",
            "verified_by": rf.VERIFIED_INK}
    assert rf.record_one(doc, "a", prop) is True
    obj = doc.objects["a"]

    # the original is untouched
    assert obj.props["latex"] == "x"
    # the refinement is addressable under its own name
    assert obj.props[rf.REFINED_FIELD] == "x^{2}"

    r = obj.realizations[-1]
    assert r.provenance == "change"
    assert r.props["verified_by"] == "ink"
    assert (r.props["ink_before"], r.props["ink_after"]) == (91, 40)
    assert r.props[rf.REFINED_FIELD] == "x^{2}"
    # the realization carries the value under the FIELD NAME so modeldiff can
    # find the evidence path behind the changed prop
    assert r.props[rf.REFINED_FIELD] == obj.props[rf.REFINED_FIELD]


def test_record_is_a_no_op_for_an_unknown_object():
    assert rf.record_one(_doc(), "nope", {"proposed": "x"}) is False


# ----------------------------------------------------------- changes.json ---

def test_changes_round_trip(tmp_path):
    p = rf.changes_path(tmp_path)
    rf.save_changes(p, {"proposals": [{"id": "a", "status": "proposed"}]})
    assert rf.load_changes(p)["proposals"][0]["id"] == "a"


def test_absent_changes_file_reads_as_empty(tmp_path):
    assert rf.load_changes(tmp_path / "nope.json") == {"proposals": []}


def test_corrupt_changes_file_does_not_crash(tmp_path):
    p = tmp_path / "changes.json"
    p.write_text("{not json", encoding="utf-8")
    assert rf.load_changes(p) == {"proposals": []}


def test_save_is_atomic_leaving_no_tmp(tmp_path):
    p = rf.changes_path(tmp_path)
    rf.save_changes(p, {"proposals": []})
    assert not list(tmp_path.glob("*.tmp"))


# ---------------------------------------------------------------- png dpi ---

def test_has_phys_false_for_absent_file(tmp_path):
    assert rf._has_phys(tmp_path / "nope.png") is False


# ------------------------------------------------- blank-reference guard ---

def test_blank_scan_is_not_a_measurable_reference():
    """The failure shape of every crop bug is 'no ink', not 'wrong ink'."""
    assert rf.measurable({"components": 0, "holes": 0}) is False
    assert rf.measurable({}) is False
    assert rf.measurable({"components": 1, "holes": 0}) is True


def test_blank_reference_would_have_rewarded_deleting_content():
    """Documents the inversion the guard exists to prevent: against a blank
    scan, the emptiest proposal scores best."""
    blank = {"components": 0, "holes": 0}
    before = rf.ink_distance(blank, {"components": 40, "holes": 5})
    after = rf.ink_distance(blank, {"components": 12, "holes": 1})
    assert after < before          # i.e. it would have been ACCEPTED
    assert not rf.measurable(blank)   # ... which is why it never gets measured


def test_blank_against_blank_is_not_a_perfect_match():
    """distance 0 here would read as 'render already matches the scan' and the
    ink gate would SKIP the row as needing no work."""
    blank = {"components": 0, "holes": 0}
    assert rf.ink_distance(blank, blank) == 0
    assert not rf.measurable(blank)


# ------------------------------------------------ per-page scale guard ---

def _lines(tmp_path, pages):
    import json as _j
    p = tmp_path / "d.lines.json"
    p.write_text(_j.dumps({"pages": pages}), encoding="utf-8")
    return tmp_path


def test_page_widths_are_read_per_page_not_once(tmp_path):
    """11 of 305 corpus documents carry more than one page_width. Applying
    page 1's width everywhere mis-scales the crop on the odd page — the same
    defect as not scaling at all, just rarer."""
    d = _lines(tmp_path, [{"page": 1, "page_width": 2066},
                          {"page": 2, "page_width": 2125}])
    w = rf.mathpix_page_widths(d)
    assert w == {1: 2066.0, 2: 2125.0}


def test_page_without_a_recorded_width_is_absent_not_defaulted(tmp_path):
    """Absent, so the caller refuses to crop rather than cropping wrongly."""
    d = _lines(tmp_path, [{"page": 1, "page_width": 2066}, {"page": 2}])
    assert 2 not in rf.mathpix_page_widths(d)


def test_no_lines_json_yields_no_widths(tmp_path):
    assert rf.mathpix_page_widths(tmp_path) == {}


def test_scan_crop_refuses_without_a_page_width(tmp_path):
    assert rf.scan_crop(tmp_path / "x.pdf", 1, {"top_left_x": 0, "top_left_y": 0,
                                                "width": 10, "height": 10},
                        tmp_path / "o.png", page_width=0) is None


# --------------------------------------------- cross-boundary schema ---

def _ink_json(glyphs):
    import json as _j
    return _j.dumps({"pages": [{"lines": glyphs}]})


def test_schema_change_in_inkdrill_output_is_refused(monkeypatch, tmp_path):
    """inkdrill belongs to another session. If it renames `holes`, the metric
    silently loses a term rather than failing — a confident wrong number."""
    import subprocess

    renamed = [{"type": "glyph", "ink": {"components": 1, "n_holes": 2}}] * 5

    def fake_run(*a, **k):
        return subprocess.CompletedProcess(a, 0, _ink_json(renamed), "")

    monkeypatch.setattr(rf, "inkdrill_root", lambda: tmp_path)
    monkeypatch.setattr(subprocess, "run", fake_run)
    png = tmp_path / "x.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(rf.InkUnavailable) as e:
        rf.ink_signature(png)
    assert "holes" in str(e.value)


def test_hole_free_page_is_not_mistaken_for_a_schema_change(monkeypatch, tmp_path):
    """A page whose glyphs genuinely have no holes carries "holes": 0. Key
    PRESENCE distinguishes that from a renamed field."""
    import subprocess

    holeless = [{"type": "glyph", "ink": {"components": 1, "holes": 0}}] * 5

    def fake_run(*a, **k):
        return subprocess.CompletedProcess(a, 0, _ink_json(holeless), "")

    monkeypatch.setattr(rf, "inkdrill_root", lambda: tmp_path)
    monkeypatch.setattr(subprocess, "run", fake_run)
    png = tmp_path / "x.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert rf.ink_signature(png) == {"components": 5, "holes": 0}


def test_page_with_no_glyphs_does_not_trip_the_schema_check(monkeypatch, tmp_path):
    """An empty page is a blank-reference problem, caught by measurable(),
    not a schema problem — the two must not be conflated."""
    import subprocess

    def fake_run(*a, **k):
        return subprocess.CompletedProcess(a, 0, _ink_json([]), "")

    monkeypatch.setattr(rf, "inkdrill_root", lambda: tmp_path)
    monkeypatch.setattr(subprocess, "run", fake_run)
    png = tmp_path / "x.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    sig = rf.ink_signature(png)
    assert sig == {"components": 0, "holes": 0}
    assert not rf.measurable(sig)


# ------------------------------------------------------- 216: variant C ---

def test_variant_C_prompt_shows_the_existing_reading():
    """out/113: from the image ALONE the median delta was +146; with the
    existing reading added it was -8. The prior is the whole difference."""
    p = rf.PROPOSE_PROMPT_C.format(conf="0.0020", latex="X")
    assert "THE OCR'S READING" in p
    assert "AGAINST THE IMAGE" in p


def test_the_crop_selects_the_variant_C_prompt(monkeypatch, tmp_path):
    seen = {}

    def fake(prompt, *, system, model, max_tokens, timeout, crop=None):
        seen["prompt"], seen["crop"] = prompt, crop
        return "x^2", "stop", ""

    monkeypatch.setattr(rf, "_novita_chat", fake)
    png = tmp_path / "c.png"; png.write_bytes(b"\x89PNG\r\n\x1a\n")
    rf.propose_one("X", 0.1, crop=str(png))
    assert "AGAINST THE IMAGE" in seen["prompt"] and seen["crop"]


def test_without_a_crop_it_is_NOT_variant_C(monkeypatch):
    """A run with no image is not one of the four variants out/113 measured,
    and must not be reported as C."""
    seen = {}

    def fake(prompt, *, system, model, max_tokens, timeout, crop=None):
        seen["prompt"], seen["crop"] = prompt, crop
        return "x^2", "stop", ""

    monkeypatch.setattr(rf, "_novita_chat", fake)
    rf.propose_one("X", 0.1)
    assert "AGAINST THE IMAGE" not in seen["prompt"] and seen["crop"] is None
