"""
831 — a document's README: what it is, where it came from, what was done to it.

A drilled folder holds up to forty files and says nothing about itself. Which
route produced the model, whether a paid MathPix conversion is in there, what
has been run and what has deliberately not — all of it is recorded, in the
sidecar, and readable only by someone who knows the sidecar's shape.

The two things it exists to say:

  * WHAT WAS PAID FOR. A folder holding a MathPix conversion is worth more than
    the PDF it came from and cannot be rebuilt for free. Nothing in the folder
    said so.
  * WHAT HAS NOT BEEN RUN. A property that is not established is ABSENT, not
    false — the distinction that had `code` called "dropped entirely" when
    97.5% of it was already recovered.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.readme import collect, render, _q, _seq            # noqa: E402

yaml = pytest.importorskip("yaml")

PDF = b"%PDF-1.7 not-a-real-pdf\n%%EOF\n"


def _doc(tmp_path, transitions=(), evidence=None, facts=()):
    """A self-contained doc folder with a hand-written sidecar."""
    d = tmp_path / "paper"
    d.mkdir()
    (d / "paper.pdf").write_bytes(PDF)
    (d / "paper.drill.json").write_text(json.dumps({
        "pdf": str(d / "paper.pdf"),
        "pdfdrill_version": "0.4.0",
        "facts": list(facts),
        "evidence": evidence or {},
        "transitions": list(transitions),
    }), encoding="utf-8")
    return d / "paper.pdf"


def front_matter(text: str) -> dict:
    return yaml.safe_load(text.split("---", 2)[1])


def test_the_front_matter_is_valid_yaml(tmp_path):
    pdf = _doc(tmp_path, evidence={"bibkey": "k", "pages": 3},
               facts=["SIZE_KNOWN"])
    fm = front_matter(render(collect(pdf)))
    assert fm["bibkey"] == "k"
    assert fm["document"]["pages"] == 3
    assert fm["facts"] == ["SIZE_KNOWN"]


def test_a_paid_step_is_named(tmp_path):
    """The reason the file exists: this folder cannot be rebuilt for free."""
    pdf = _doc(tmp_path, transitions=[
        {"ts": "2026-01-01T00:00:00Z", "node": "size", "detail": "3 pages"},
        {"ts": "2026-01-01T00:01:00Z", "node": "mathpix", "detail": "uploaded"},
    ])
    d = collect(pdf)
    assert d["paid"] == ["mathpix"]
    out = render(d)
    assert "cannot be rebuilt for free" in out
    assert "- `mathpix`" in out
    assert front_matter(out)["paid_steps"] == ["mathpix"]


def test_an_offline_only_document_says_so(tmp_path):
    pdf = _doc(tmp_path, transitions=[
        {"ts": "2026-01-01T00:00:00Z", "node": "size", "detail": "3 pages"},
        {"ts": "2026-01-01T00:02:00Z", "node": "model", "detail": "12 objects"},
    ])
    out = render(collect(pdf))
    assert "Nothing. Every artefact here was produced offline" in out
    assert front_matter(out)["paid_steps"] == []


def test_every_step_appears_in_order(tmp_path):
    steps = [
        {"ts": "2026-01-01T00:00:00Z", "node": "size", "detail": "3 pages"},
        {"ts": "2026-01-01T00:01:00Z", "node": "model", "detail": "12 objects"},
        {"ts": "2026-01-01T00:02:00Z", "node": "tiddlers", "detail": "9 tiddlers"},
    ]
    out = render(collect(_doc(tmp_path, transitions=steps)))
    at = [out.index("`%s`" % s["node"]) for s in steps]
    assert at == sorted(at), "the process table must read in the order it happened"
    assert "12 objects" in out and "9 tiddlers" in out


def test_what_has_not_been_run_is_named(tmp_path):
    """Absent is not false. Listing only what happened turns 'never attempted'
    into 'nothing there'."""
    out = render(collect(_doc(tmp_path, transitions=[
        {"ts": "2026-01-01T00:00:00Z", "node": "size", "detail": "3 pages"}])))
    assert "## Not run" in out
    assert "have **not been attempted**" in out
    assert "`model`" in out.split("## Not run", 1)[1]


def test_a_pipe_in_a_detail_does_not_break_the_table(tmp_path):
    out = render(collect(_doc(tmp_path, transitions=[
        {"ts": "t", "node": "size", "detail": "a | b | c"}])))
    row = [l for l in out.splitlines() if l.startswith("| t |")][0]
    # the pipes INSIDE the cell are escaped, so the row still has four cells
    assert row.replace("\\|", "").count("|") == 5, row
    assert "\\|" in row


def test_authors_is_a_list_not_a_python_repr():
    """The model stores authors as a list; stringifying it wrote
    `authors: "['A']"` — valid YAML for a STRING that looks like a list."""
    assert yaml.safe_load(_seq("authors", ["A B"]))["authors"] == ["A B"]
    assert _seq("authors", None) == "authors: []"
    assert yaml.safe_load(_seq("authors", None))["authors"] == []


def test_a_title_with_a_colon_survives():
    """`Ologs: a categorical framework` is the real case — an unquoted colon
    makes the whole document unparseable."""
    assert yaml.safe_load("t: " + _q("Ologs: a framework"))["t"] == "Ologs: a framework"
    assert yaml.safe_load("t: " + _q("1102.1889"))["t"] == "1102.1889"


def test_it_says_it_is_generated(tmp_path):
    out = render(collect(_doc(tmp_path)))
    assert "do not hand-edit" in out


def test_a_bare_folder_still_produces_a_readme(tmp_path):
    """No sidecar at all: the file must still say what little is true rather
    than fail."""
    d = tmp_path / "x"
    d.mkdir()
    (d / "x.pdf").write_bytes(PDF)
    out = render(collect(d / "x.pdf"))
    assert "# x" in out
    assert "nothing recorded" in out
