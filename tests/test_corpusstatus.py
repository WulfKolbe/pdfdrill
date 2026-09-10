"""653 — `pdfdrill corpusstatus` writes one index.html across the WHOLE
library: one row per document, read-only, never building a model, never
taking a per-document lock.

Reuses 652's own read-only gatherer (`_status_conserve_ledger`) rather than
inventing a second one — the failure this repo keeps rediscovering when two
implementations of "the same number" drift apart (out/652.txt, out/653.txt).
Every test below stubs `cmd_model` to raise if called, the same posture
`test_status_html.py` already checks for `status --html`.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject, Realization
from pdfdrill import commands as C


# --------------------------------------------------------------- fixtures

def _base_reachable(doc: Document):
    mp = doc.ensure_stream("mathpix_lines")
    head = mp.append(text="1 Intro", _page=1, _line_index=0,
                     type="section_header")
    body = mp.append(text="Hello there.", _page=1, _line_index=1, type="text")
    sec = DocObject(type="Section", props={
        "caption": "Intro", "level": 1, "flow_index": 0, "page": 1})
    sec.add_realization(Realization(stream="mathpix_lines", start=head,
                                    end=head, role="surface"))
    doc.add(sec)
    par = DocObject(type="Paragraph", props={
        "text": "Hello there.", "page": 1, "flow_index": 1})
    par.add_realization(Realization(stream="mathpix_lines", start=body,
                                    end=body, role="surface"))
    doc.add_child(sec, par)


def _by_design_doc(bibkey: str) -> Document:
    """Reachable Section+Paragraph + one BY_DESIGN Page — no violation, no
    unclaimed/doubly-claimed anchor: must read 'conserved' (656's point)."""
    doc = Document()
    doc.meta["bibkey"] = bibkey
    _base_reachable(doc)
    doc.add(DocObject(type="Page", props={"page_number": 1}))
    return doc


def _violation_doc(bibkey: str) -> Document:
    """One genuine VIOLATION (Citation, 656's ninth type), NO baseline row,
    and NO anchor defect (the Citation carries no realization at all, so it
    affects no anchor's claim count). Must read 'NOT conserved' from
    `_status_verdict` — but this is the fix-round-1 (finding 2) 'unaudited'
    shape specifically: zero unclaimed, zero doubly-claimed, the ONLY thing
    wrong is a violation type with no baseline row. `corpusstatus` must
    color this differently from a real anchor defect (below)."""
    doc = Document()
    doc.meta["bibkey"] = bibkey
    _base_reachable(doc)
    doc.add(DocObject(type="Citation", props={"citekey": "X1", "flow_index": 2}))
    return doc


def _unclaimed_anchor_doc(bibkey: str) -> Document:
    """Reachable Section+Paragraph, PLUS one extra `mathpix_lines` anchor
    that NO object claims — a genuine, baseline-INDEPENDENT anchor defect
    (646/652's own `unclaimed` count). No violation type at all here: this
    document is NOT conserved purely because of the orphan anchor, and must
    read as a real defect ('bad') even though it also has no baseline row —
    fix round 1 (finding 1/2)'s whole point: a real anchor defect is not the
    same fact as 'nobody has audited this bibkey yet'."""
    doc = Document()
    doc.meta["bibkey"] = bibkey
    _base_reachable(doc)
    mp = doc.ensure_stream("mathpix_lines")
    mp.append(text="Orphan line nobody claims.", _page=1, _line_index=2,
             type="text")
    return doc


def _make_doc(library: Path, name: str, doc: "Document | None" = None,
             bibsource_refs: "int | None" = None,
             status_page: bool = False) -> Path:
    """A self-contained `<library>/<name>/<name>.pdf` with a real Sidecar,
    and, if `doc` is given, a real model.docmodel.json on disk. `status_page`
    writes a stub `<name>.status.html` beside it, as if
    `pdfdrill status --html` had already run."""
    folder = library / name
    folder.mkdir(parents=True, exist_ok=True)
    pdf = folder / f"{name}.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    sc = C.Sidecar(pdf)
    sc.add_fact("SIZE_KNOWN")
    if doc is not None:
        sc.add_fact(C.MODEL_BUILT)
        (folder / "model.docmodel.json").write_text(
            json.dumps(doc.to_dict()), encoding="utf-8")
    if bibsource_refs is not None:
        sc.add_fact(C.BIBSOURCE_BUILT)
        sc.set_evidence("bibsource_references", bibsource_refs)
    if status_page:
        (folder / f"{name}.status.html").write_text(
            "<title>stub</title>", encoding="utf-8")
    sc.save()
    return pdf


def _never_build(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("corpusstatus must never call cmd_model")
    monkeypatch.setattr(C, "cmd_model", _boom)


# ---------------------------------------------------------- the basic shape

def test_two_document_library_two_rows_right_verdicts_relative_links(
        tmp_path, monkeypatch):
    _never_build(monkeypatch)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline", lambda: {})

    _make_doc(tmp_path, "docA", _by_design_doc("docA"), bibsource_refs=7,
             status_page=True)
    _make_doc(tmp_path, "docB", None)          # no model at all

    out = C.cmd_corpusstatus(library=str(tmp_path))
    assert "2 document(s)" in out

    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    rows = re.findall(r"<tr>.*?</tr>", index, re.S)
    # header row + two data rows
    assert len(rows) == 3

    # docA: model built, gold bib (7), conserved
    a_row = next(r for r in rows if "docA" in r)
    assert ">yes<" in a_row or "yes (" in a_row
    assert "yes (7)" in a_row
    assert 'class="ok"' in a_row and ">conserved<" in a_row
    # link is RELATIVE (no absolute tmp_path prefix, no leading slash)
    m = re.search(r'href="([^"]+)"', a_row)
    assert m, "docA's row has no status-page link"
    href = m.group(1)
    assert not href.startswith("/") and str(tmp_path) not in href
    assert href == "docA/docA.status.html"

    # docB: no model, conservation unavailable, no status link
    b_row = next(r for r in rows if "docB" in r)
    assert ">no<" in b_row
    assert "unavailable" in b_row
    assert "not generated" in b_row


def test_real_anchor_defect_is_named_not_conserved_in_the_report(
        tmp_path, monkeypatch):
    """Fix round 1 (finding 1): a real unclaimed/doubly-claimed anchor is a
    genuine defect and belongs in the 'NOT conserved' bucket, whether or not
    the bibkey has a baseline row."""
    _never_build(monkeypatch)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline", lambda: {})

    _make_doc(tmp_path, "badkey", _unclaimed_anchor_doc("badkey"))
    out = C.cmd_corpusstatus(library=str(tmp_path))
    assert "NOT conserved: 1 (real anchor defect" in out
    assert "unaudited: 0" in out
    assert "badkey" in out.split("NOT conserved:")[-1].split("unaudited")[0]


def test_unaudited_violation_only_document_is_not_the_same_bucket(
        tmp_path, monkeypatch):
    """Fix round 1 (finding 2): a document whose ONLY problem is an
    unbaselined violation type (zero unclaimed, zero doubly-claimed) is
    'unaudited', not 'NOT conserved' — a different, less alarming fact, and
    must render in its own colour/class on the page."""
    _never_build(monkeypatch)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline", lambda: {})

    _make_doc(tmp_path, "greykey", _violation_doc("greykey"))
    out = C.cmd_corpusstatus(library=str(tmp_path))
    assert "NOT conserved: 0 (real anchor defect" in out
    assert "unaudited: 1" in out
    assert "greykey" in out.split("unaudited:")[-1]

    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    row = next(r for r in re.findall(r"<tr>.*?</tr>", index, re.S)
              if "greykey" in r)
    assert 'class="unaudited"' in row
    assert 'class="bad"' not in row
    assert "no baseline row recorded yet" in row


def test_a_real_anchor_defect_and_an_unaudited_document_get_different_states(
        tmp_path, monkeypatch):
    """Both shapes in one library, so the split itself is exercised, not
    just each shape alone."""
    _never_build(monkeypatch)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline", lambda: {})

    _make_doc(tmp_path, "badkey", _unclaimed_anchor_doc("badkey"))
    _make_doc(tmp_path, "greykey", _violation_doc("greykey"))
    _make_doc(tmp_path, "okkey", _by_design_doc("okkey"))

    result = C.corpus_status_rows(tmp_path)
    states = {r["bibkey"]: C._corpus_row_state(r) for r in result["rows"]}
    assert states == {"badkey": "bad", "greykey": "unaudited", "okkey": "ok"}


# --------------------------------------------------------------- --only-published

def test_only_published_reads_documents_json_and_is_cheap(tmp_path, monkeypatch):
    _never_build(monkeypatch)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline", lambda: {})

    pdf_a = _make_doc(tmp_path, "docA", _by_design_doc("docA"))
    _make_doc(tmp_path, "docB", _by_design_doc("docB"))   # NOT published

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "documents.json").write_text(
        json.dumps({"docA": str(pdf_a)}), encoding="utf-8")

    result = C.corpus_status_rows(tmp_path, only_published=True)
    assert result["only_published"] is True
    assert len(result["rows"]) == 1
    assert result["rows"][0]["bibkey"] == "docA"


def test_only_published_missing_set_reports_error_not_crash(tmp_path):
    result = C.corpus_status_rows(tmp_path, only_published=True)
    assert result["rows"] == []
    assert "error" in result


def test_only_published_reports_skipped_entries_not_silently(
        tmp_path, monkeypatch):
    """Fix round 1 (finding 10): a `documents.json` entry with no path, or
    whose path no longer resolves to a file, must be COUNTED and REPORTED,
    not silently dropped from the row count with no trace."""
    _never_build(monkeypatch)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline", lambda: {})

    pdf_a = _make_doc(tmp_path, "docA", _by_design_doc("docA"))
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "documents.json").write_text(json.dumps({
        "docA": str(pdf_a),
        "gone": str(tmp_path / "gone" / "gone.pdf"),   # never created
        "nullkey": None,
    }), encoding="utf-8")

    result = C.corpus_status_rows(tmp_path, only_published=True)
    assert len(result["rows"]) == 1
    assert result["skipped"] == 2

    out = C.cmd_corpusstatus(library=str(tmp_path), only_published=True)
    assert "skipped from the published set (2)" in out


# --------------------------------------------------------------- scale guards

def test_size_guard_skips_an_oversized_model_without_loading_it(
        tmp_path, monkeypatch):
    _never_build(monkeypatch)

    def _boom(*a, **k):
        raise AssertionError("the oversized model must never be loaded")
    monkeypatch.setattr(C, "_status_conserve_ledger", _boom)
    monkeypatch.setattr(C, "_CORPUS_MODEL_SIZE_GUARD", 10)   # 10 bytes

    _make_doc(tmp_path, "huge", _by_design_doc("huge"))      # model > 10 bytes
    out = C.cmd_corpusstatus(library=str(tmp_path))
    assert "1 document(s)" in out

    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "size guard" in index
    assert "conservation unavailable: 1" in out


def test_cwd_is_restored_after_each_document(tmp_path, monkeypatch):
    """The CWD trap (module note in commands.py): corpusstatus chdirs into
    each document's own folder to check/read its model (652's proof is
    content-hash, recorded relative to the build's own cwd), and must always
    restore the process cwd afterward — even across many documents."""
    import os
    _never_build(monkeypatch)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline", lambda: {})

    _make_doc(tmp_path, "docA", _by_design_doc("docA"))
    _make_doc(tmp_path, "docB", _by_design_doc("docB"))

    prior = os.getcwd()
    C.cmd_corpusstatus(library=str(tmp_path))
    assert os.getcwd() == prior


def test_cwd_restored_even_when_the_gatherer_raises(tmp_path, monkeypatch):
    """The chdir/finally in `_corpus_status_row` restores the cwd even when
    the gatherer raises — and, since fix round 1 (finding 3), the raise no
    longer propagates out of `cmd_corpusstatus` at all: it is caught one
    level up, in `_corpus_row_or_error`, and turned into an 'errored' row."""
    import os
    _never_build(monkeypatch)

    def _boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    monkeypatch.setattr(C, "_status_conserve_ledger", _boom)

    _make_doc(tmp_path, "docA", _by_design_doc("docA"))
    prior = os.getcwd()
    out = C.cmd_corpusstatus(library=str(tmp_path))       # must NOT raise
    assert os.getcwd() == prior
    assert "could not be read at all (1" in out
    assert "docA" in out.split("could not be read at all")[-1]


# --------------------------------------------------------------- exception isolation

def test_one_malformed_model_does_not_abort_the_whole_walk(tmp_path, monkeypatch):
    """Fix round 1 (finding 3): a REAL corrupt model.docmodel.json (not a
    monkeypatched stub) among several documents must not void every row
    already computed for the others — `index.html` must still be written,
    with 3 rows: the two good ones plus one 'errored' row for the broken
    one."""
    _never_build(monkeypatch)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline", lambda: {})

    _make_doc(tmp_path, "goodA", _by_design_doc("goodA"))
    _make_doc(tmp_path, "goodB", _unclaimed_anchor_doc("goodB"))
    _make_doc(tmp_path, "brokenC", _by_design_doc("brokenC"))
    # overwrite with genuinely invalid JSON AFTER _make_doc wrote a real one,
    # so MODEL_BUILT + the fact/evidence sidecar state is otherwise normal —
    # only the model FILE itself is corrupt, the shape a real bad build or a
    # truncated write would leave.
    (tmp_path / "brokenC" / "model.docmodel.json").write_text(
        "{not valid json at all", encoding="utf-8")

    out = C.cmd_corpusstatus(library=str(tmp_path))
    assert "3 document(s)" in out
    assert "could not be read at all (1" in out
    assert "brokenC" in out.split("could not be read at all")[-1]

    index_path = tmp_path / "index.html"
    assert index_path.is_file() and index_path.stat().st_size > 0
    index = index_path.read_text(encoding="utf-8")
    rows = re.findall(r"<tr>.*?</tr>", index, re.S)
    assert len(rows) == 4                                  # header + 3

    result = C.corpus_status_rows(tmp_path)
    by_key = {r["bibkey"]: r for r in result["rows"]}
    assert by_key["goodA"].get("errored") is not True
    assert by_key["goodB"].get("errored") is not True
    assert by_key["brokenC"]["errored"] is True
    assert C._corpus_row_state(by_key["brokenC"]) == "errored"
    assert by_key["brokenC"]["conserve"]["available"] is False
    assert "could not read this document" in by_key["brokenC"]["conserve"]["reason"]


def test_render_phase_isolates_a_single_row_failure(tmp_path, monkeypatch):
    """Fix round 2 — a row that raises while being RENDERED (not gathered)
    is the SAME catastrophic shape finding 3 fixed for the gather phase,
    one phase later: `_render_corpus_index_html`'s
    `"".join(_corpus_row_html(r) for r in rows)` had no isolation at all,
    so one bad row would void the HTML for every other row already
    gathered. Every other row must still appear on the page, and the
    failed one gets a VISIBLE marker rather than vanishing."""
    _never_build(monkeypatch)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline", lambda: {})

    _make_doc(tmp_path, "goodA", _by_design_doc("goodA"))
    _make_doc(tmp_path, "goodB", _unclaimed_anchor_doc("goodB"))
    _make_doc(tmp_path, "renderboom", _by_design_doc("renderboom"))

    real_render = C._corpus_row_html

    def _boom(r):
        if r["bibkey"] == "renderboom":
            raise RuntimeError("render boom")
        return real_render(r)
    monkeypatch.setattr(C, "_corpus_row_html", _boom)

    out = C.cmd_corpusstatus(library=str(tmp_path))
    assert "3 document(s)" in out

    index_path = tmp_path / "index.html"
    assert index_path.is_file() and index_path.stat().st_size > 0
    index = index_path.read_text(encoding="utf-8")

    # every row is on the page — nothing vanished because one raised
    assert "goodA" in index
    assert "goodB" in index
    assert "renderboom" in index
    assert "could not be rendered on this page" in index
    assert "render boom" in index

    rows = re.findall(r"<tr>.*?</tr>", index, re.S)
    assert len(rows) == 4                                  # header + 3
    boom_row = next(r for r in rows if "renderboom" in r)
    good_a_row = next(r for r in rows if "goodA" in r)
    # the broken row still carries 8 real <td> cells, one per column header
    # — a colspan cell would leave `a.children[idx]` undefined for later
    # columns and break the inline JS sorter on THIS row's account.
    assert boom_row.count("<td") == 8 == good_a_row.count("<td")


def test_page_summary_gives_errored_its_own_number(tmp_path, monkeypatch):
    """Minor finding: the summary paragraph used to fold `errored` into
    `unavailable`, so the headline sentence carried no separate count for
    it even though the per-row text and the CLI prose both did."""
    _never_build(monkeypatch)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline", lambda: {})

    _make_doc(tmp_path, "goodA", _by_design_doc("goodA"))
    _make_doc(tmp_path, "nomodel", None)
    _make_doc(tmp_path, "brokenC", _by_design_doc("brokenC"))
    (tmp_path / "brokenC" / "model.docmodel.json").write_text(
        "{not valid json at all", encoding="utf-8")

    C.cmd_corpusstatus(library=str(tmp_path))
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    flat = " ".join(index.split())
    assert "1 conservation unavailable" in flat
    assert "1 could not be read at all (errored" in flat


# --------------------------------------------------------------- artefacts / page

def test_artefacts_present_counted_against_the_five_published_files(
        tmp_path, monkeypatch):
    _never_build(monkeypatch)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline", lambda: {})
    from pdfdrill.reports.gate import PUBLISHED_FILES

    _make_doc(tmp_path, "docA", _by_design_doc("docA"))
    for f in PUBLISHED_FILES[:2]:
        (tmp_path / "docA" / f).write_bytes(b"%PDF-1.4\n")

    result = C.corpus_status_rows(tmp_path)
    row = result["rows"][0]
    assert row["artefacts"]["present"] == 2
    assert row["artefacts"]["total"] == len(PUBLISHED_FILES)


def test_index_page_is_sortable_inline_js_no_network(tmp_path, monkeypatch):
    _never_build(monkeypatch)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline", lambda: {})

    _make_doc(tmp_path, "docA", _by_design_doc("docA"))
    C.cmd_corpusstatus(library=str(tmp_path))
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "<script src=" not in index          # no CDN / network
    assert "http://" not in index and "https://" not in index
    assert "addEventListener" in index
    assert "<title>" in index


def test_no_such_library_directory_does_not_crash(tmp_path):
    missing = tmp_path / "nope"
    out = C.cmd_corpusstatus(library=str(missing))
    assert "No such library directory" in out


def test_surrogate_escaped_filename_does_not_crash_the_index_write(
        tmp_path, monkeypatch):
    """A live bug found running the real corpus (out/653.txt): a folder
    whose name is not valid UTF-8 (CP1252 bytes — `taskout._write`'s own
    docstring names 18 such folders in this library) decodes via
    surrogateescape to a lone surrogate. `write_text(encoding="utf-8")`
    cannot encode that back out and raised `UnicodeEncodeError` on the real
    library's first full-corpus run; the fix writes bytes with
    `errors="replace"` instead of failing the whole index."""
    import os
    _never_build(monkeypatch)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline", lambda: {})

    bad = b"weird\xd6doc"                       # invalid UTF-8 continuation
    folder = tmp_path.as_posix().encode("utf-8") + b"/" + bad
    os.mkdir(folder)
    pdf_bytes = folder + b"/" + bad + b".pdf"
    with open(pdf_bytes, "wb") as f:
        f.write(b"%PDF-1.4\n")

    pdf_path = Path(os.fsdecode(pdf_bytes))
    name = pdf_path.stem
    doc = _by_design_doc(name)
    sc = C.Sidecar(pdf_path)
    sc.add_fact("SIZE_KNOWN")
    sc.add_fact(C.MODEL_BUILT)
    Path(os.fsdecode(folder) + "/model.docmodel.json").write_text(
        json.dumps(doc.to_dict()), encoding="utf-8")
    sc.save()

    out = C.cmd_corpusstatus(library=str(tmp_path))
    assert "1 document(s)" in out
    index_path = tmp_path / "index.html"
    assert index_path.is_file() and index_path.stat().st_size > 0


# --------------------------------------------------- the write is not cmd_-prefixed

def test_write_helper_is_not_cmd_prefixed_so_no_lock_is_required():
    """Mirrors 652's own confirmation: the literal write lives in a helper
    whose name does not start with `cmd_`, so test_doclock.py's AST scan
    (which only walks top-level `cmd_*` defs) never requires this command to
    hold a per-document lock — correct, since index.html is not one
    document's file (brief item 2)."""
    assert not C._write_corpus_index_html.__name__.startswith("cmd_")


# ------------------------------------------------------------------ CLI wiring

def test_cli_do_corpusstatus_parses_library_and_only_published(monkeypatch):
    from pdfdrill import cli
    calls = []

    def _stub(library=None, only_published=False):
        calls.append((library, only_published))
        return "ok"

    monkeypatch.setattr("pdfdrill.commands.cmd_corpusstatus", _stub)
    assert cli._do_corpusstatus(["--library", "/some/dir", "--only-published"]) == "ok"
    assert calls[-1] == ("/some/dir", True)

    calls.clear()
    assert cli._do_corpusstatus([]) == "ok"
    assert calls[-1] == (None, False)
