"""652 — `pdfdrill status --html` writes the state page instead of printing
it, folding in 646's conservation check, 634's claim ledger, and 656's
by-design/violation split for the verdict line, plus 655's evidence-size
note and 651's hand-work-merge record when either exists.

THE 656 CORRECTION THIS TASK IS BUILT AROUND: `conserve()`'s raw
`unreachable` count is ~100% BY_DESIGN/OUT_OF_SCOPE noise on every real
document (out/656.txt) — a page that printed it verbatim would call every
healthy document broken. A first draft summed
`classify_unreachable(...)["violations"]` for the verdict; that was
discarded because it has no baseline to compare against, so a document's
pre-existing, already-known violations would flip it to FAIL forever. The
shipped verdict instead uses `docops.conserve.gate()`'s `new_types` /
`increased` partition against the recorded baseline (`_status_verdict`,
`commands.py`) — only a violation type with no baseline row, or one whose
count rose above its baseline, counts against the verdict; matched,
decreased, by-design, and out-of-scope never do. Rule 11 (masked
success/failure): every check below is exercised on both a real PASS and a
real FAIL of the same verdict line, never one alone.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from docmodel.core import Document, DocObject, Realization
from pdfdrill import commands as C
from pdfdrill import doclock as L


# --------------------------------------------------------------- fixtures

def _base_reachable(doc: Document) -> DocObject:
    mp = doc.ensure_stream("mathpix_lines")
    head = mp.append(text="1 Intro", _page=1, _line_index=0,
                     type="section_header")
    body = mp.append(text="Hello [X1].", _page=1, _line_index=1, type="text")
    sec = DocObject(type="Section", props={
        "caption": "Intro", "level": 1, "flow_index": 0, "page": 1})
    sec.add_realization(Realization(stream="mathpix_lines", start=head,
                                    end=head, role="surface"))
    doc.add(sec)
    par = DocObject(type="Paragraph", props={
        "text": "Hello [X1].", "page": 1, "flow_index": 1})
    par.add_realization(Realization(stream="mathpix_lines", start=body,
                                    end=body, role="surface"))
    doc.add_child(sec, par)
    return sec, body


def _doc_with_one_violation(bibkey="V1") -> Document:
    """One reachable Section+Paragraph, one genuine VIOLATION (Citation has
    no BY_DESIGN/OUT_OF_SCOPE route — 656's ninth violation type)."""
    doc = Document()
    doc.meta["bibkey"] = bibkey
    sec, body = _base_reachable(doc)
    cit = DocObject(type="Citation", props={"citekey": "X1", "flow_index": 2})
    cit.add_realization(Realization(stream="mathpix_lines", start=body,
                                    end=body, role="surface",
                                    props={"offset": 6, "length": 2}))
    doc.add(cit)
    return doc


def _doc_by_design_only(bibkey="D1") -> Document:
    """One reachable Section+Paragraph, one BY_DESIGN Page — no violation,
    no unclaimed/doubly-claimed anchor. Must read 'conserved'."""
    doc = Document()
    doc.meta["bibkey"] = bibkey
    _base_reachable(doc)
    doc.add(DocObject(type="Page", props={"page_number": 1}))
    return doc


def _wire(tmp_path, name, doc=None):
    """A real Sidecar for a fresh PDF, with SIZE_KNOWN set (so `status`
    doesn't early-return) and, if `doc` is given, a model written to disk."""
    pdf = tmp_path / f"{name}.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    sc = C.Sidecar(pdf)
    sc.add_fact("SIZE_KNOWN")
    sc.save()
    if doc is not None:
        sc.blob_dir.mkdir(parents=True, exist_ok=True)
        (sc.blob_dir / "model.docmodel.json").write_text(
            json.dumps(doc.to_dict()), encoding="utf-8")
    return pdf, sc


def _verdict(html_text: str) -> str:
    m = re.search(r'<p class="verdict[^>]*>(.*?)</p>', html_text, re.S)
    assert m, "no verdict line found in the page"
    return m.group(1)


# ------------------------------------------------------------- the verdict

def test_a_genuine_violation_with_no_baseline_is_not_conserved(tmp_path, monkeypatch):
    pdf, sc = _wire(tmp_path, "V1", _doc_with_one_violation("V1"))
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline", lambda: {})
    C.cmd_status(pdf, html=True)
    text = (sc.blob_dir / "V1.status.html").read_text(encoding="utf-8")
    assert _verdict(text) == ("NOT conserved: 0 unclaimed, 0 doubly-claimed, "
                              "1 unreachable object(s) beyond what is "
                              "already recorded")


def test_by_design_unreachable_alone_reads_conserved(tmp_path, monkeypatch):
    """656's whole point: a Page (always 100% unreachable by construction)
    must never turn this verdict red."""
    pdf, sc = _wire(tmp_path, "D1", _doc_by_design_only("D1"))
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    C.cmd_status(pdf, html=True)
    text = (sc.blob_dir / "D1.status.html").read_text(encoding="utf-8")
    assert _verdict(text) == "conserved"
    # the by-design gap is still shown, just not counted against the verdict
    assert "unreachable BY DESIGN" in text and "Page=1" in text


def test_baseline_row_surfaces_the_gate_report(tmp_path, monkeypatch):
    doc = _doc_with_one_violation("V1")
    pdf, sc = _wire(tmp_path, "V1", doc)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline",
                        lambda: {"V1": {"Citation": 1}})
    C.cmd_status(pdf, html=True)
    text = (sc.blob_dir / "V1.status.html").read_text(encoding="utf-8")
    assert _verdict(text) == "conserved"        # matches baseline exactly
    assert "at baseline: Citation=1" in text
    assert "no baseline row" not in text


def test_no_baseline_row_is_noted_but_does_not_fail_the_page(tmp_path, monkeypatch):
    pdf, sc = _wire(tmp_path, "V1", _doc_with_one_violation("V1"))
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline", lambda: {})
    C.cmd_status(pdf, html=True)
    text = (sc.blob_dir / "V1.status.html").read_text(encoding="utf-8")
    assert "no baseline row for this bibkey" in text
    # the page's own verdict is independent of the ratchet's zero tolerance
    assert "NOT conserved" in _verdict(text)


def test_decreased_only_reads_conserved_with_a_reconciling_sentence(
        tmp_path, monkeypatch):
    """652 review, finding 5 — a gate delta that is ONLY a `decreased` (a
    fixed violation the checked-in baseline hasn't caught up to yet) must
    still read 'conserved' at the top (by design: a decrease is not counted
    against the per-document verdict) while `gate_report` below prints a
    literal FAIL for the SAME document — the baseline itself is stale. Both
    are correct; without a reconciling sentence they read as a
    contradiction to anyone who hasn't read the design rationale."""
    doc = _doc_with_one_violation("V1")          # exactly one Citation now
    pdf, sc = _wire(tmp_path, "V1", doc)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    # baseline recorded 2; only 1 remains -> `decreased`, nothing `new`/`increased`
    monkeypatch.setattr(conserve_mod, "load_baseline",
                        lambda: {"V1": {"Citation": 2}})
    C.cmd_status(pdf, html=True)
    text = (sc.blob_dir / "V1.status.html").read_text(encoding="utf-8")
    assert _verdict(text) == "conserved"
    assert "DROPPED" in text and "FAIL" in text          # the gate block
    # the reconciling sentence must be present, and must sit in the same
    # "Conservation & ledger" section as the gate block it explains
    assert "not the document" in text
    assert "baseline needs lowering" in text


def test_increased_alone_gets_no_reconciling_sentence(tmp_path, monkeypatch):
    """The sentence added for finding 5 must not fire on an ordinary FAIL —
    only on the specific 'verdict says conserved, gate block says FAIL'
    shape decreased-only produces."""
    pdf, sc = _wire(tmp_path, "V1", _doc_with_one_violation("V1"))
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline",
                        lambda: {"V1": {"Citation": 0}})
    C.cmd_status(pdf, html=True)
    text = (sc.blob_dir / "V1.status.html").read_text(encoding="utf-8")
    assert "NOT conserved" in _verdict(text)
    assert "not the document" not in text


# --------------------------------------------------- one bibkey source

def test_html_filename_and_embedded_verdict_use_the_same_bibkey(
        tmp_path, monkeypatch):
    """652 review, finding 4 — `_write_status_html` used to name the file
    from `resolve_bibkey` (sidecar/filename-stem) while the embedded
    `gate_report` text was keyed on the model's OWN recorded bibkey
    (`res["bibkey"]`). Force them apart (a sidecar bibkey that disagrees
    with the model's) and confirm the file is now named, and the gate
    report text keyed, on the SAME (model-derived) bibkey."""
    doc = _doc_with_one_violation("MODEL_KEY")
    pdf, sc = _wire(tmp_path, "SIDECAR_KEY", doc)
    sc.set_evidence("bibkey", "SIDECAR_KEY")      # diverges from doc.meta
    sc.save()
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline",
                        lambda: {"MODEL_KEY": {"Citation": 1}})
    C.cmd_status(pdf, html=True)
    out = sc.blob_dir / "MODEL_KEY.status.html"
    assert out.exists(), (
        "the page must be named from the model's own bibkey, not the "
        "sidecar's, once a model is available")
    text = out.read_text(encoding="utf-8")
    assert "conserve --gate MODEL_KEY:" in text
    assert not (sc.blob_dir / "SIDECAR_KEY.status.html").exists()


# ------------------------------------------------------- stale / absent model

def test_stale_model_shows_stale_and_no_numbers_and_never_rebuilds(tmp_path, monkeypatch):
    pdf, sc = _wire(tmp_path, "S1", _doc_by_design_only("S1"))
    # No MODEL_BUILT fact recorded -> `_stale_or_absent` reports stale by its
    # own real logic (not monkeypatched here) — the model on disk is ignored.
    def _must_not_rebuild(*a, **k):
        raise AssertionError("a read must never chain into a build (634)")
    monkeypatch.setattr(C, "cmd_model", _must_not_rebuild)
    C.cmd_status(pdf, html=True)
    text = (sc.blob_dir / "S1.status.html").read_text(encoding="utf-8")
    assert "unavailable" in text
    assert "STALE" in text
    assert "conserved" not in _verdict(text).lower() or "unavailable" in _verdict(text)
    assert "NOT conserved" not in text
    assert "634 claim ledger" not in text


def test_absent_model_shows_a_reason(tmp_path):
    pdf, sc = _wire(tmp_path, "A1", doc=None)     # no model.docmodel.json at all
    C.cmd_status(pdf, html=True)
    text = (sc.blob_dir / "A1.status.html").read_text(encoding="utf-8")
    assert "no model on disk yet" in text
    assert "NOT conserved" not in text and "\"verdict ok\"" not in text


# --------------------------------------------------------------- artefacts

def test_artifact_links_resolve_relative_to_the_folder(tmp_path, monkeypatch):
    pdf, sc = _wire(tmp_path, "R1", _doc_by_design_only("R1"))
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    (sc.blob_dir / "R1.md").write_text("hello", encoding="utf-8")
    (sc.blob_dir / "svg").mkdir(exist_ok=True)
    (sc.blob_dir / "svg" / "f1.svg").write_text("<svg/>", encoding="utf-8")
    C.cmd_status(pdf, html=True)
    out_path = sc.blob_dir / "R1.status.html"
    text = out_path.read_text(encoding="utf-8")
    hrefs = re.findall(r'href="([^"]+)"', text)
    assert hrefs, "no artefact links found on the page"
    for href in hrefs:
        target = (out_path.parent / href).resolve()
        assert target.is_file(), f"dead link on the page: {href}"
    assert any(h.endswith("R1.md") for h in hrefs)
    assert any(h.endswith("svg/f1.svg") or h.endswith("svg\\f1.svg") for h in hrefs)


def test_status_html_is_itself_listed_as_an_artifact(tmp_path, monkeypatch):
    """`pdfdrill artifacts` (drillui's Outputs panel) globs `.html` in the
    blob dir, so writing the page is enough to register it — no separate
    manifest entry needed."""
    pdf, sc = _wire(tmp_path, "L1", _doc_by_design_only("L1"))
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    C.cmd_status(pdf, html=True)
    arts = C._list_artifacts(sc)
    assert any(p.name == "L1.status.html" for p in arts)
    listing = C.cmd_artifacts(pdf)
    assert "L1.status.html" in listing


# ------------------------------------------------------------- 655 / 651 extras

def test_over_budget_evidence_pdf_is_flagged(monkeypatch):
    from pdfdrill.reports import budget as budget_mod
    monkeypatch.setattr(budget_mod, "check_artifact",
                        lambda p, mb: (25_000_000, True))
    fake = Path("/nonexistent/evidence-formula.pdf")
    notes = C._status_budget_notes([fake])
    assert notes and notes[0]["over"] is True
    assert notes[0]["name"] == "evidence-formula.pdf"


def test_under_budget_evidence_pdf_is_not_flagged_as_over(monkeypatch):
    from pdfdrill.reports import budget as budget_mod
    monkeypatch.setattr(budget_mod, "check_artifact",
                        lambda p, mb: (1_000_000, False))
    fake = Path("/nonexistent/evidence-formula.pdf")
    notes = C._status_budget_notes([fake])
    assert notes and notes[0]["over"] is False


def test_non_evidence_pdf_is_not_a_budget_note(monkeypatch):
    from pdfdrill.reports import budget as budget_mod
    monkeypatch.setattr(budget_mod, "check_artifact",
                        lambda p, mb: (1_000_000, False))
    fake = Path("/nonexistent/report.pdf")
    assert C._status_budget_notes([fake]) == []


def test_update_record_summary_appears_on_the_page(tmp_path, monkeypatch):
    pdf, sc = _wire(tmp_path, "U1", _doc_by_design_only("U1"))
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    (sc.blob_dir / "U1.update.json").write_text(json.dumps({
        "old_file": "/somewhere/U1.tiddlers.json",
        "restored": {"T1": ["text"], "T2": ["caption", "note"]},
        "unmatched": ["Old title"],
        "newly_orphaned": [],
    }), encoding="utf-8")
    C.cmd_status(pdf, html=True)
    text = (sc.blob_dir / "U1.status.html").read_text(encoding="utf-8")
    assert "Hand-work merge record" in text
    assert "3 field(s) restored across 2 title(s)" in text
    assert "1 old title(s) unmatched" in text


def test_no_update_record_means_no_section(tmp_path, monkeypatch):
    pdf, sc = _wire(tmp_path, "U2", _doc_by_design_only("U2"))
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    C.cmd_status(pdf, html=True)
    text = (sc.blob_dir / "U2.status.html").read_text(encoding="utf-8")
    assert "Hand-work merge record" not in text


# --------------------------------------------------- text status is unchanged

def test_text_status_unaffected_by_html_param(tmp_path):
    pdf, sc = _wire(tmp_path, "T1", doc=None)
    out = C.cmd_status(pdf)
    assert isinstance(out, str) and "For T1.pdf I have:" in out
    assert not (sc.blob_dir / "T1.status.html").exists()


def test_cmd_status_source_still_calls_the_shared_line_builders():
    """The dict the text printer and the HTML writer both consume is built
    from the SAME calls `status` always made — never a duplicate
    re-derivation (the brief's own instruction)."""
    import inspect
    src = inspect.getsource(C.cmd_status)
    assert "_model_status_lines" in src
    assert "_retracted_status_lines" in src


# ---------------------------------------------------------------- the lock

def test_write_status_html_is_not_cmd_prefixed():
    """The `@_writes` AST scan in test_doclock.py only walks top-level
    `cmd_*` defs; the write helper must stay outside that name so the TEXT
    branch of `cmd_status` (which never writes) is not forced to hold the
    document lock just because SOME branch of it writes."""
    assert not C._write_status_html.__name__.startswith("cmd_")


def test_html_write_refuses_when_another_process_holds_the_document(tmp_path):
    import subprocess
    import sys as _sys
    pdf, sc = _wire(tmp_path, "LK1", doc=None)
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "from pathlib import Path\n"
        "from pdfdrill import commands as C\n"
        "from pdfdrill import doclock as L\n"
        "try:\n"
        "    C.cmd_status(Path(%r), html=True)\n"
        "    print('TOOK')\n"
        "except L.DocumentBusy:\n"
        "    print('REFUSED')\n"
    ) % (str(Path(__file__).resolve().parent.parent / "src"), str(pdf))
    with L.hold(pdf, "other-process"):
        r = subprocess.run([_sys.executable, "-c", code],
                           capture_output=True, text=True, timeout=60)
    assert r.stdout.strip() == "REFUSED", r.stdout + r.stderr


def test_html_write_takes_and_releases_the_lock(tmp_path, monkeypatch):
    pdf, sc = _wire(tmp_path, "LK2", _doc_by_design_only("LK2"))
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    assert L.read_holder(pdf) is None
    C.cmd_status(pdf, html=True)
    assert L.read_holder(pdf) is None            # released after the write


# ------------------------------------------------------------------ CLI

def test_do_status_parses_html_flag(monkeypatch, tmp_path):
    from pdfdrill import cli, commands

    calls = []

    def fake_cmd_status(pdf, html=False):
        calls.append({"pdf": pdf, "html": html})
        return "ok"

    monkeypatch.setattr(commands, "cmd_status", fake_cmd_status)
    fake_pdf = tmp_path / "x.pdf"
    monkeypatch.setattr(cli, "_pdf", lambda args: fake_pdf)

    cli._do_status(["x.pdf"])
    cli._do_status(["x.pdf", "--html"])

    assert [c["html"] for c in calls] == [False, True]
    assert all(c["pdf"] == fake_pdf for c in calls)
