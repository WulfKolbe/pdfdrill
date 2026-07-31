"""
`pdfdrill docs` — the compact session listing, and TITLED abstracts.

A multi-document session is unusable when every line is a bibkey or a filename
stem: `1012.3259` says nothing about what the paper is. `docs` gives one line
per document (title + bibkey), and `abstract` labels each abstract with its
title instead of returning an anonymous pile of text.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands as C


def _store(tmp_path, sources):
    p = tmp_path / "session.docpack"
    p.write_text(json.dumps({"is_combined": True, "objects": [],
                             "meta": {"sources": sources}}), encoding="utf-8")
    return p


def test_docs_lists_title_per_document(tmp_path):
    store = _store(tmp_path, [
        {"bibkey": "2002.08155", "path": "/nope/a.pdf", "title": "CodeBERT: A Model"},
        {"bibkey": "2105.00377", "path": "/nope/b.pdf", "title": "MathBERT: Another"},
    ])
    out = C.cmd_docs(store)
    assert "2 document(s) in this session" in out
    assert "CodeBERT: A Model" in out and "MathBERT: Another" in out
    assert "2002.08155" in out and "2105.00377" in out
    # one line per document — compact by construction
    body = [l for l in out.splitlines() if l.startswith("  2")]
    assert len(body) == 2


def test_docs_titles_only_is_the_shortest_form(tmp_path):
    store = _store(tmp_path, [
        {"bibkey": "k1", "path": "/nope/a.pdf", "title": "First Paper"},
        {"bibkey": "k2", "path": "/nope/b.pdf", "title": "Second Paper"},
    ])
    assert C.cmd_docs(store, titles_only=True) == "First Paper\nSecond Paper"


def test_docs_flags_untitled_docs_and_says_how_to_fix(tmp_path):
    """A document showing its id must explain WHY and what to run."""
    store = _store(tmp_path, [{"bibkey": "1012.3259", "path": "/nope/x.pdf",
                               "title": ""}])
    out = C.cmd_docs(store)
    assert "1012.3259" in out
    assert "no title was captured" in out and "abstract" in out


def test_docs_empty_store(tmp_path):
    assert "No documents" in C.cmd_docs(_store(tmp_path, []))


def test_abstract_fans_out_over_a_session_with_titles(tmp_path, monkeypatch):
    """Each abstract must carry its own title — an unlabelled pile is unusable."""
    store = _store(tmp_path, [
        {"bibkey": "k1", "path": str(tmp_path / "a.pdf"), "title": "First Paper"},
        {"bibkey": "k2", "path": str(tmp_path / "b.pdf"), "title": "Second Paper"},
    ])
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4\n")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(C, "_abstract_body", lambda p: f"body of {Path(p).stem}")
    monkeypatch.setattr(C, "doc_title",
                        lambda p, sc=None: {"a": "First Paper",
                                            "b": "Second Paper"}[Path(p).stem])
    monkeypatch.setattr(C, "resolve_bibkey", lambda p, b, sc: Path(p).stem)
    out = C.cmd_abstract(store)
    assert "Abstracts for 2 document(s)" in out
    assert "## First Paper" in out and "## Second Paper" in out
    assert "body of a" in out and "body of b" in out
    # the title comes BEFORE its abstract body
    assert out.index("## First Paper") < out.index("body of a")


def test_single_document_abstract_is_titled(tmp_path, monkeypatch):
    pdf = tmp_path / "solo.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(C, "_abstract_body", lambda p: "the abstract text")
    monkeypatch.setattr(C, "doc_title", lambda p, sc=None: "A Real Title")
    monkeypatch.setattr(C, "resolve_bibkey", lambda p, b, sc: "solo")
    out = C.cmd_abstract(pdf)
    assert out.startswith("## A Real Title\n[solo]\n")
    assert "the abstract text" in out
