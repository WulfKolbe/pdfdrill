"""T-0153 — `md` alone produced 2,963 words and the verdict said "no reading".

Found by the coordinator on ada1b845 (env -i, sandbox, PDFDRILL_JUDGE set, a
fresh folder) and reproduced here:

    $ pdfdrill md 1805.01788-p0003.pdf                              exit=5
    Extracted 2963 words of Markdown across 3 pages. Detected 75 inline and
    1 display math expressions, 17 references. Stored as layer `md`.
    pdfdrill verdict: NOT REACHED - text: no reading; ink: not judged

`assess` takes `has_text` from `MODEL_BUILT` and the model's object counts
alone. `md` writes an `md` layer and no model, so a run that read the whole
document reported that it had read nothing — on the first command a user is
likely to type. That is the false-report class T-0153 exists for, and it
compounds: `has_text` False also skips the judge, so the line said "ink: not
judged" WITH a judge configured.

`_with_verdict` already hands `assess` the md blob — it was used only to count
U+FFFD. So the evidence was in the function the whole time.

AND THE JUDGE STILL CANNOT RUN AFTER `md` ALONE, which is worth saying rather
than papering over. The judge compares a PER-LINE GEOMETRY reading against the
page's ink, i.e. a lines.json; `md` produces none (measured: after `md` in a
fresh folder the blob dir holds chars.json and ir.json and no lines.json).
Only `glyphlines`/`drill` leave one. So the honest line distinguishes two
states that used to read identically:

    no judge configured        "ink: not judged"
    judge, nothing to judge    "ink: not judged (no lines.json ...)"
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfdrill import verdict                                # noqa: E402
from pdfdrill.sidecar import Sidecar                        # noqa: E402

WORDS = ("# A Section\n\nRankings of people and items are at the heart of "
         "selection-making, match-making and recommender systems.\n")


def _doc(tmp_path, *, md: "str | None" = None, model: bool = False):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.7 not-a-real-pdf\n%%EOF\n")
    sc = Sidecar(pdf)
    sc.set_evidence("pages", 3)
    sc.set_evidence("text_layer", True)
    sc.set_evidence("needs_ocr", False)
    sc.add_fact("SIZE_KNOWN")
    if model:
        sc.add_fact("MODEL_BUILT")
        sc.set_evidence("model_object_counts", {"Paragraph": 12})
    sc.save()
    files = []
    if md is not None:
        sc.blob_dir.mkdir(parents=True, exist_ok=True)
        p = sc.blob_dir / "doc.md"
        p.write_text(md, encoding="utf-8")
        files.append(p)
    return pdf, Sidecar(pdf), files


def test_an_md_layer_with_words_is_a_reading(tmp_path):
    """THE RED. 2,963 words reported, "text: no reading" in the same output."""
    pdf, sc, files = _doc(tmp_path, md=WORDS)
    v = verdict.assess(pdf, sc, files)
    assert v.state != verdict.NOT_REACHED, (
        f"a projection with words in it still reads as no reading: {v.line()}")
    assert "text: no reading" not in v.line()
    assert v.exit_code != 5


def test_the_verdicts_own_stamp_does_not_count_as_text(tmp_path):
    """`stamp()` writes the verdict INTO the projection, so on the second run
    the file begins with it. A reading must not be inferred from the sentence
    that says there is no reading."""
    pdf, sc, files = _doc(
        tmp_path, md="> " + verdict.MARK + " NOT REACHED — text: no reading\n\n")
    v = verdict.assess(pdf, sc, files)
    assert v.state == verdict.NOT_REACHED, (
        f"the verdict read its own stamp as the document's text: {v.line()}")


def test_an_empty_projection_is_still_no_reading(tmp_path):
    for i, body in enumerate(("", "\n\n   \n", "#\n\n|  |  |\n")):
        d = tmp_path / f"d{i}"
        d.mkdir()
        pdf, sc, files = _doc(d, md=body)
        v = verdict.assess(pdf, sc, files)
        assert v.state == verdict.NOT_REACHED, (body, v.line())


def test_a_model_still_decides_when_there_is_one(tmp_path):
    pdf, sc, files = _doc(tmp_path, model=True)
    assert verdict.assess(pdf, sc, files).state != verdict.NOT_REACHED


def test_the_geometry_lane_is_still_not_a_reading(tmp_path):
    """docs/LANES.md lane 5 draws boxes and reads no character. Its veto must
    survive this change, whatever a projection built from it contains."""
    pdf, sc, files = _doc(tmp_path, md=WORDS, model=True)
    sc.set_evidence("model_source", verdict.GEOMETRY_ONLY_SOURCES[0])
    sc.save()
    v = verdict.assess(pdf, Sidecar(pdf), files)
    assert v.state == verdict.NOT_REACHED, v.line()


# ------------------------------------------- the judge has nothing to judge
def test_a_configured_judge_with_no_lines_json_says_which(tmp_path,
                                                           monkeypatch):
    """Two states used to read identically. After `md` alone there is no
    lines.json, so the ink CANNOT be judged -- and a user who has just set
    PDFDRILL_JUDGE needs to be told that, not left to wonder."""
    from pdfdrill import pagejudge
    exe = tmp_path / "inkcmp-judge"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)
    monkeypatch.setenv("PDFDRILL_JUDGE", str(exe))
    pdf, sc, files = _doc(tmp_path, md=WORDS)
    v = verdict.assess(pdf, sc, files)
    line = v.line()
    assert "not judged" in line
    assert "lines.json" in line, (
        "the line does not say WHY it could not judge, so a configured judge "
        f"looks the same as none: {line}")
    assert "glyphlines" in line or "drill" in line, (
        f"...and does not say how to get one: {line}")


def test_no_judge_configured_still_says_just_not_judged(tmp_path, monkeypatch):
    monkeypatch.delenv("PDFDRILL_JUDGE", raising=False)
    from pdfdrill import pagejudge
    monkeypatch.setattr(pagejudge._cfg, "get", lambda *a, **k: None)
    pdf, sc, files = _doc(tmp_path, md=WORDS)
    line = verdict.assess(pdf, sc, files).line()
    assert "ink: not judged" in line
    assert "lines.json" not in line, (
        f"a user with no judge does not need the lines.json advice: {line}")


# --------------------------------------------- which page the verdict judges
def test_the_faulted_line_says_it_stopped_at_the_first_fault():
    """The coordinator's question: which page is judged, and why. One fault
    settles the document, so the walk stops there -- and the line has to say
    that, or "judged 1 of 3" reads as a sample someone chose."""
    from pdfdrill import pagejudge
    ink = pagejudge.Ink(pages_judged=1, pages=3, faults=11, page=1,
                        detail="1 wrong, 5 unread, 5 invented")
    line = ink.line()
    assert "1 of 3" in line
    assert "stopped" in line.lower() or "first" in line.lower(), (
        f"the line does not say why only one page was judged: {line}")


def test_a_clean_document_is_judged_in_full():
    from pdfdrill import pagejudge
    ink = pagejudge.Ink(pages_judged=3, pages=3, faults=0, page=0, detail="")
    assert "3 page(s)" in ink.line() and "stopped" not in ink.line().lower()
