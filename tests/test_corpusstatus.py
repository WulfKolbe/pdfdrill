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

import pytest

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
    """One genuine VIOLATION (Citation, 656's ninth type, no baseline row):
    must read 'NOT conserved'."""
    doc = Document()
    doc.meta["bibkey"] = bibkey
    _base_reachable(doc)
    doc.add(DocObject(type="Citation", props={"citekey": "X1", "flow_index": 2}))
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


def test_not_conserved_documents_are_named_in_the_report(tmp_path, monkeypatch):
    _never_build(monkeypatch)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    import docops.conserve as conserve_mod
    monkeypatch.setattr(conserve_mod, "load_baseline", lambda: {})

    _make_doc(tmp_path, "badkey", _violation_doc("badkey"))
    out = C.cmd_corpusstatus(library=str(tmp_path))
    assert "NOT conserved: 1" in out
    assert "badkey" in out.split("NOT conserved:")[-1]


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
    import os
    _never_build(monkeypatch)

    def _boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    monkeypatch.setattr(C, "_status_conserve_ledger", _boom)

    _make_doc(tmp_path, "docA", _by_design_doc("docA"))
    prior = os.getcwd()
    with pytest.raises(RuntimeError):
        C.cmd_corpusstatus(library=str(tmp_path))
    assert os.getcwd() == prior


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
