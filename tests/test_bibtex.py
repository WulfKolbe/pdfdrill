"""
`pdfdrill bibtex` augmentation: an arXiv input must NOT yield @misc{unknown2023}.
The embedded PDF metadata is usually empty, so bibtex augments from the FREE
arXiv abs-page metadata (title/authors) and warns when still a placeholder.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import sources
from pdfdrill.commands import (_augment_bibtex, _is_placeholder_bib, _arxiv_year)
from pdfdrill.sidecar import Sidecar


def test_is_placeholder_bib():
    assert _is_placeholder_bib({"title": "", "author": "", "citekey": "unknown2023"})
    assert _is_placeholder_bib(None)
    assert not _is_placeholder_bib({"title": "Real Title", "author": "", "citekey": "x2023"})
    assert not _is_placeholder_bib({"title": "", "author": "A B", "citekey": "b2023"})


def test_arxiv_year():
    assert _arxiv_year("2305.04710v1") == "2023"
    assert _arxiv_year("2104.13478") == "2021"
    assert _arxiv_year("math/0309136") == "2003"
    assert _arxiv_year("") == ""


def test_augment_from_arxiv_metadata(monkeypatch):
    monkeypatch.setattr(sources, "fetch_arxiv_metadata", lambda aid: {
        "title": "ElasticHash: Semantic Image Similarity Search",
        "authors": ["Nikolaus Korfhage", "Markus Mühling", "Bernd Freisleben"],
        "primary_category": "cs.CV", "arxiv_id": aid,
    })
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "2305.04710v1.pdf"; pdf.write_bytes(b"%PDF-1.4")
        sc = Sidecar(pdf)
        sc.set_evidence("source_arxiv_id", "2305.04710v1")
        bib = {"title": "", "author": "", "year": "", "citekey": "unknown2023",
               "entry_type": "misc", "pages": 10, "url": ""}
        note = _augment_bibtex(bib, pdf, sc)
        assert note == ""                                  # no warning — it's real now
        assert bib["title"].startswith("ElasticHash")
        assert bib["author"] == "Nikolaus Korfhage and Markus Mühling and Bernd Freisleben"
        assert bib["entry_type"] == "misc"                 # canonical arXiv @misc form
        assert bib["year"] == "2023"
        assert bib["citekey"] == "korfhage2023"            # NOT unknown2023
        assert bib["arxiv_id"] == "2305.04710v1"
        assert bib["eprint"] == "2305.04710v1"             # eprint/archivePrefix present
        assert bib["archive_prefix"] == "arXiv"


def test_placeholder_warns_when_no_source(monkeypatch):
    # not arXiv, no model, empty metadata → stays a placeholder + warns
    def _no_arxiv(s):  # bare_arxiv_id / parse_arxiv_id both miss a plain stem
        return None
    monkeypatch.setattr(sources, "bare_arxiv_id", _no_arxiv)
    monkeypatch.setattr(sources, "parse_arxiv_id", _no_arxiv)
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "scan_001.pdf"; pdf.write_bytes(b"%PDF-1.4")
        sc = Sidecar(pdf)
        bib = {"title": "", "author": "", "year": "2023", "citekey": "unknown2023",
               "entry_type": "misc", "pages": 3, "url": ""}
        note = _augment_bibtex(bib, pdf, sc)
        assert "PLACEHOLDER" in note and "abstract" in note
        assert _is_placeholder_bib(bib)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))


# ------------------------------------------- the drilled front matter as record
class _SCFM:
    """Stands for pdfdrill.sidecar.Sidecar — see tests/test_stub_fidelity.py."""

    def __init__(self, ev=None, blob_dir=None):
        self.evidence = dict(ev or {})
        self.blob_dir = blob_dir

    def set_evidence(self, k, v):
        self.evidence[k] = v

    def get_evidence(self, k, default=None):
        return self.evidence.get(k, default)


def test_a_scanned_books_own_title_page_becomes_the_record(monkeypatch, tmp_path):
    """`bibtex` on a 174-page scanned book returned `@misc{unknown, pages=174}`
    while the model held the title and authors from the book's title page and
    the sidecar held the ISBN that `identifiers` had already validated."""
    from pdfdrill import commands

    class _G:
        meta = {"title": "Strukturen der physikalischen Welt und ihrer "
                         "nichtmateriellen Seite",
                "authors": "Walter Dröscher / Burkhard Heim"}

    mp = tmp_path / "model.docmodel.json"
    mp.write_text("{}")
    monkeypatch.setattr(commands, "_model_path", lambda sc: mp)
    from pdfdrill import model_io
    monkeypatch.setattr(model_io, "load_docgraph", lambda p: _G())

    sc = _SCFM({"identifiers": {"ids": [{"type": "ISBN", "value": "385382059X", "confidence": 0.97}]}})
    bib = {"entry_type": "misc", "pages": "174"}
    note = commands._augment_bibtex(bib, tmp_path / "WDorg4.pdf", sc)

    assert bib["title"].startswith("Strukturen der physikalischen Welt")
    assert bib["author"] == "Walter Dröscher and Burkhard Heim"
    assert bib["isbn"] == "385382059X"
    assert bib["entry_type"] == "book"          # an ISBN means a book
    assert bib["citekey"] != "unknown"
    assert "PLACEHOLDER" not in note


def test_an_isbn_alone_does_not_invent_an_author(monkeypatch, tmp_path):
    """Half a record is not a record: without a title or author it must still
    say PLACEHOLDER rather than look finished."""
    from pdfdrill import commands

    monkeypatch.setattr(commands, "_model_path", lambda sc: tmp_path / "none.json")
    sc = _SCFM({"identifiers": {"ids": [{"type": "ISBN", "value": "385382059X", "confidence": 0.97}]}})
    bib = {"entry_type": "misc", "pages": "174"}
    note = commands._augment_bibtex(bib, tmp_path / "x.pdf", sc)
    assert bib.get("author", "") == ""
    assert "isbn" not in bib             # nothing to attach it to
    assert bib["entry_type"] == "misc"   # ... so it is not promoted to a book
    assert "PLACEHOLDER" in note


def test_an_arxiv_record_is_not_turned_into_a_book(monkeypatch, tmp_path):
    """The arXiv path owns entry_type; a stray ISBN must not override it."""
    from pdfdrill import commands

    monkeypatch.setattr(commands, "_model_path", lambda sc: tmp_path / "none.json")
    sc = _SCFM({"source_arxiv_id": "2312.11532",
                "arxiv_title": "Topic-VQ-VAE", "arxiv_authors": ["Y. Yoo"],
                "identifiers": {"ids": [{"type": "ISBN", "value": "385382059X", "confidence": 0.97}]}})
    bib = {"entry_type": "misc"}
    commands._augment_bibtex(bib, tmp_path / "2312.11532.pdf", sc)
    assert bib["entry_type"] == "misc"


def test_the_front_matter_is_read_from_lines_json_without_a_rebuild(monkeypatch, tmp_path):
    """The title/author capture happens at model-build time, so every document
    already drilled would need `model --force` to benefit — which drops the
    bibliography and the bibfetch enrichment with it (on WDorg4: 21 references
    and a paid API pass). The lines.json is the immutable source and is right
    there, so read the front matter from it when the model meta lacks it.
    """
    import json
    from pdfdrill import commands

    pdf = tmp_path / "WDorg4.pdf"
    (tmp_path / "WDorg4.lines.json").write_text(json.dumps({"pages": [
        {"page": 1, "lines": [{"type": "text", "text": "half title"}]},
        {"page": 3, "lines": [
            {"type": "authors", "text": "Walter Dröscher / Burkhard Heim"},
            {"type": "title", "text": ""},
            {"type": "text", "text": "Strukturen"},
            {"type": "text", "text": "der physikalischen Welt"},
            {"type": "page_info", "text": "RESCH VERLAG INNSBRUCK 1996"}]},
    ]}), encoding="utf-8")

    class _G:
        meta = {}                                # an OLD model: no title, no authors

    mp = tmp_path / "model.docmodel.json"
    mp.write_text("{}")
    monkeypatch.setattr(commands, "_model_path", lambda sc: mp)
    from pdfdrill import model_io
    monkeypatch.setattr(model_io, "load_docgraph", lambda p: _G())

    bib = {"entry_type": "misc", "pages": "174"}
    note = commands._augment_bibtex(bib, pdf, _SCFM())
    assert bib["title"] == "Strukturen der physikalischen Welt"
    assert bib["author"] == "Walter Dröscher and Burkhard Heim"
    assert "PLACEHOLDER" not in note


def test_the_isbn_reader_matches_what_cmd_identifiers_writes():
    """Pins the field NAME to its producer. The first version of
    `_isbn_from_sidecar` read `kind`; cmd_identifiers writes `type`, so it
    matched nothing on every real sidecar while its test — which invented the
    same wrong key — passed."""
    import inspect
    from pdfdrill import commands

    src = inspect.getsource(commands.cmd_identifiers)
    assert '{"type": f.type, "value": f.value' in src, \
        "cmd_identifiers no longer writes `type` — update _isbn_from_sidecar"
    sc = _SCFM({"identifiers": {"ids": [
        {"type": "ISBN", "value": "385382059X", "confidence": 0.97}]}})
    assert commands._isbn_from_sidecar(sc) == "385382059X"


def test_force_re_derives_a_cached_record(monkeypatch, tmp_path):
    """The cache is keyed on "is it a placeholder", so a record that gained a
    title but is still missing the ISBN never refreshes — and there was no way
    to ask. Observed live: the second `bibtex` run served a stale record while
    the augmentation had already been fixed.

    Uses a real Sidecar on a real PDF rather than a fake: cmd_bibtex chains
    pdfinfo, and a stub grown to match would be one more thing to keep in sync.
    """
    import shutil
    import pytest as _pytest
    from pdfdrill import commands

    if not shutil.which("pdfinfo"):
        _pytest.skip("poppler not installed")
    pypdf = _pytest.importorskip("pypdf")
    w = pypdf.PdfWriter()
    w.add_blank_page(width=200, height=200)
    pdf = tmp_path / "cached.pdf"
    with open(pdf, "wb") as fh:
        w.write(fh)

    calls = []

    def fake_augment(bib, _pdf, _sc):
        calls.append(1)
        bib["title"] = "A Real Title"
        bib["author"] = "Some Author"
        bib["citekey"] = "author"
        return ""

    monkeypatch.setattr(commands, "_augment_bibtex", fake_augment)

    commands.cmd_bibtex(pdf)
    assert calls == [1]                      # first run derives
    commands.cmd_bibtex(pdf)
    assert calls == [1]                      # second serves the cache
    commands.cmd_bibtex(pdf, force=True)
    assert calls == [1, 1]                   # ... unless asked


def test_the_isbn_is_actually_rendered():
    """`_augment_bibtex` set bib["isbn"] and the entry became @book, but the
    renderer's field list had no isbn — so the ISBN was silently dropped and
    the printed record looked identical apart from the type."""
    from pdfdrill.pdfinfo_layers import bibtex_to_string

    out = bibtex_to_string({"entry_type": "book", "citekey": "drscher1996",
                            "title": "Strukturen der physikalischen Welt",
                            "author": "Walter Dröscher and Burkhard Heim",
                            "year": "1996", "isbn": "385382059X"})
    assert "isbn" in out and "385382059X" in out
    assert out.startswith("@book{drscher1996,")


def test_a_citekey_keeps_a_transliterated_umlaut():
    """`Dröscher` collapsed to `drscher` — the ö was dropped rather than
    transliterated, giving a key that matches nothing a reader would type."""
    from pdfdrill.pdfinfo_layers import _make_citekey

    assert _make_citekey("Walter Dröscher and Burkhard Heim", "1996", "") == "droescher1996"
    assert _make_citekey("Émile Borel", "1921", "") == "borel1921"
    assert _make_citekey("Kingma and Welling", "2013", "") == "kingma2013"


def test_the_publisher_and_place_reach_the_record(monkeypatch, tmp_path):
    import json
    from pdfdrill import commands

    pdf = tmp_path / "WDorg4.pdf"
    (tmp_path / "WDorg4.lines.json").write_text(json.dumps({"pages": [
        {"page": 3, "lines": [
            {"type": "authors", "text": "Walter Dröscher / Burkhard Heim"},
            {"type": "title", "text": ""},
            {"type": "text", "text": "Strukturen der physikalischen Welt"}]},
        {"page": 4, "lines": [
            {"type": "text", "text": "© 1996 by Andreas Resch Verlag, Innsbruck"}]},
    ]}), encoding="utf-8")

    class _G:
        meta = {}

    mp = tmp_path / "model.docmodel.json"
    mp.write_text("{}")
    monkeypatch.setattr(commands, "_model_path", lambda sc: mp)
    from pdfdrill import model_io
    monkeypatch.setattr(model_io, "load_docgraph", lambda p: _G())

    bib = {"entry_type": "misc"}
    commands._augment_bibtex(bib, pdf, _SCFM())
    assert bib["publisher"] == "Andreas Resch Verlag"
    assert bib["address"] == "Innsbruck"
    assert bib["year"] == "1996"


def test_an_arxiv_paper_gets_no_publisher_from_a_stray_imprint(monkeypatch, tmp_path):
    """The arXiv path clears `publisher` on purpose — a preprint has none, and
    the PDF Producer is a tool. Front-matter filling must not undo that."""
    import json
    from pdfdrill import commands

    pdf = tmp_path / "2312.11532.pdf"
    (tmp_path / "2312.11532.lines.json").write_text(json.dumps({"pages": [
        {"page": 1, "lines": [
            {"type": "text", "text": "© 2024 by Some Conference, New York"}]},
    ]}), encoding="utf-8")
    monkeypatch.setattr(commands, "_model_path", lambda sc: tmp_path / "none.json")

    # arxiv gave a title but no authors, so the front-matter block DOES run —
    # otherwise the guard is never reached and the test proves nothing.
    bib = {"entry_type": "misc"}
    commands._augment_bibtex(bib, pdf, _SCFM(
        {"source_arxiv_id": "2312.11532", "arxiv_title": "T",
         "arxiv_authors": []}))
    assert bib["publisher"] == ""
    assert "address" not in bib
