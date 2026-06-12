"""
Gap detection (src/semantic/gaps.py) — the cohomology-as-a-linter pass:
diagnostics for MISSING information, computed over the docmodel (+ graph).
Four rules: undefined acronym, undefined math symbol, unsupported novelty
claim, unmatched in-text citation. Diagnostics, never exceptions.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from semantic import gaps


def _base_doc():
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Section", id="s1", props={
        "caption": "Method", "flow_index": 1}))
    return doc


def test_undefined_acronym_gap():
    doc = _base_doc()
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "The HMM baseline beats the HMM variant.", "page": 3,
        "parent_section": "s1", "flow_index": 2}))
    out = gaps.detect_gaps(doc)
    g = [x for x in out if x["kind"] == "acronym_undefined"]
    assert len(g) == 1 and g[0]["name"] == "HMM"
    assert g[0]["locations"][0]["page"] == 3
    assert "expansion" in g[0]["detail"] or "defin" in g[0]["detail"]


def test_defined_acronym_is_not_a_gap():
    doc = _base_doc()
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "A Hidden Markov Model (HMM) is used. The HMM works.",
        "page": 1, "parent_section": "s1", "flow_index": 2}))
    assert not [x for x in gaps.detect_gaps(doc) if x["kind"] == "acronym_undefined"]


def test_undefined_symbol_gap():
    doc = _base_doc()
    doc.add(DocObject(type="Section", id="n", props={
        "caption": "Notation", "flow_index": 3}))
    doc.add(DocObject(type="ListItem", id="i1", props={
        "content": "psi — the wave function", "page": 2,
        "parent_section": "n", "flow_index": 4}))
    doc.add(DocObject(type="Equation", id="e1", props={
        "latex": "\\psi + \\phi^2", "page": 5, "flow_index": 5}))
    out = gaps.detect_gaps(doc)
    g = {x["name"]: x for x in out if x["kind"] == "symbol_undefined"}
    assert "phi" in g            # used in math, no notation entry
    assert "psi" not in g        # declared in the Notation section


def test_unsupported_claim_gap():
    doc = _base_doc()
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "We propose a novel method that outperforms all baselines.",
        "page": 1, "parent_section": "s1", "flow_index": 2}))
    doc.add(DocObject(type="Paragraph", id="p2", props={
        "text": "We propose a novel encoder, improving on prior work "
                "\\cite{kipf2017semi}.", "page": 2,
        "parent_section": "s1", "flow_index": 3}))
    out = [x for x in gaps.detect_gaps(doc) if x["kind"] == "claim_unsupported"]
    assert len(out) == 1 and out[0]["locations"][0]["page"] == 1


def test_unmatched_citation_gap():
    doc = _base_doc()
    doc.add(DocObject(type="Citation", id="c1", props={
        "citekey": "ghost2020", "page": 4, "flow_index": 2}))
    doc.add(DocObject(type="Citation", id="c2", props={
        "citekey": "real2021", "flow_index": 3}))
    doc.add(DocObject(type="Reference", id="r1", props={
        "citekey": "real2021", "year": "2021"}))
    # the authoritative marker: bibliography/bibsource set cited_reference_id —
    # such a citation is matched even when its OCR citekey looks alien ("Mir")
    doc.add(DocObject(type="Citation", id="c3", props={
        "citekey": "Mir", "cited_reference_id": "r1", "flow_index": 4}))
    out = {x["name"]: x for x in gaps.detect_gaps(doc)
           if x["kind"] == "citation_unmatched"}
    assert "ghost2020" in out and "real2021" not in out
    assert "Mir" not in out


def test_report_is_prose_and_sorted():
    doc = _base_doc()
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "Our novel approach is the best. The HMM and the HMM agree.",
        "page": 1, "parent_section": "s1", "flow_index": 2}))
    out = gaps.detect_gaps(doc)
    txt = gaps.report(out)
    assert "acronym" in txt and "HMM" in txt
    sev = [x["severity"] for x in out]
    assert sev == sorted(sev, reverse=True)      # most severe first


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
