r"""D2 — a compiled .bbl makes the shared .bib unnecessary, and reading it anyway
cost 476 seconds.

THE DEFECT (measured 2026-11-10 on arxiv.2209.02970)
----------------------------------------------------
    pdfdrill md <doc>          476.78 s
    pdfdrill model <doc>         0.16 s
    pdfdrill bibliography <doc>  0.15 s

`md` was the whole cost, and the whole of `md`'s cost was one file.
`build_bibliography_from_source` did this:

    if res["bbl"]: ingest_bbl(...)                     # main.bbl -- the CITED set
    if res["bib"]: load_bibtex_file(... read_text() ...)   # <- not elif

`main.tex` declares `\bibliography{anthology,custom}`, so `res["bib"][0]` is
`anthology.bib`: **the entire ACL Anthology, 41.9 MB**, read into memory and
parsed in full — after `main.bbl` had already supplied all 46 references.
`restrict=` limits which entries are CREATED; it cannot stop the file being
read and parsed. The owner's verdict on the document was exact: "There is
nothing in this document that take more than 1 sec!" The 42 MB was shipped
beside the document, not in it.

The function's own docstring states the rule it broke: "the CITED subset of a
possibly-larger shared .bib -- **a compiled .bbl is already the cited set**".

WHY NOT A BARE `elif`
---------------------
A `.bbl` is the cited set by construction, but a stale or truncated one need not
cover every `\cite` in the document. So the condition is the MEASURED one: read
the `.bib` only while some cited key still has no filled Reference. That keeps
the 42 MB unread in the common case and still repairs a partial `.bbl` — and it
is a question about the document, not about which files happen to exist.
"""
import tempfile
from pathlib import Path

from docmodel.core import Document, DocObject, Realization

from pdfdrill import bibliography as B


def _doc_citing(*citekeys: str) -> Document:
    doc = Document()
    st = doc.ensure_stream("source_cites")
    for key in citekeys:
        a = st.append(citekey=key)
        c = DocObject(type="Citation", props={"citekey": key})
        c.add_realization(Realization(stream="source_cites", start=a, end=a,
                                      role="surface"))
        doc.add(c)
    return doc


def _bbl(*citekeys: str) -> str:
    items = "".join(
        f"\\bibitem{{{k}}} J. Smith. A paper about {k}. Venue, 2020.\n"
        for k in citekeys)
    return "\\begin{thebibliography}{1}\n" + items + "\\end{thebibliography}\n"


def _source(d: Path, bbl_keys, bib_keys, bib_name="anthology") -> None:
    """A source dir shaped like the measured one: a `\\bibliography{}` naming a
    big shared database, a compiled .bbl beside it."""
    (d / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n"
        + "".join(f"Text \\cite{{{k}}}.\n" for k in bbl_keys or bib_keys)
        + f"\\bibliography{{{bib_name},custom}}\n\\end{{document}}\n",
        encoding="utf-8")
    if bbl_keys:
        (d / "main.bbl").write_text(_bbl(*bbl_keys), encoding="utf-8")
    (d / f"{bib_name}.bib").write_text(
        "".join(f"@article{{{k}, title={{T {k}}}, author={{A}}, year={{2020}} }}\n"
                for k in bib_keys), encoding="utf-8")


class _Counter:
    """Records every call to `load_bibtex_file` AND the bytes handed to it, so
    the test can assert the 42 MB was never read rather than merely that no
    extra Reference appeared."""

    def __init__(self, real):
        self.real, self.calls, self.bytes = real, 0, 0

    def __call__(self, doc, text, *a, **k):
        self.calls += 1
        self.bytes += len(text)
        return self.real(doc, text, *a, **k)


def test_a_complete_bbl_leaves_the_shared_bib_unread(monkeypatch):
    """The measured case: every cited key is in the .bbl, so the shared database
    must not be opened. This is the 476.78 s."""
    counter = _Counter(B.load_bibtex_file)
    monkeypatch.setattr(B, "load_bibtex_file", counter)
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        # the .bib carries the cited keys AND a thousand others, as a shared
        # database does; reading it is what must not happen.
        _source(d, bbl_keys=("smith20", "jones21"),
                bib_keys=("smith20", "jones21", *(f"other{i}" for i in range(500))))
        doc = _doc_citing("smith20", "jones21")
        B.build_bibliography_from_source(doc, str(d))

        refs = {r.props["citekey"] for r in doc.objects.values()
                if r.type == "Reference"}
        assert {"smith20", "jones21"} <= refs, "the .bbl must still supply them"
        assert counter.calls == 0, (
            f"the shared .bib was read ({counter.bytes} chars) although the "
            f".bbl already covered every cited key")


def test_a_partial_bbl_still_falls_through_to_the_bib(monkeypatch):
    """The repair case that forbids a bare `elif`: a .bbl that does not cover
    every \\cite must not leave those references unfilled."""
    counter = _Counter(B.load_bibtex_file)
    monkeypatch.setattr(B, "load_bibtex_file", counter)
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        _source(d, bbl_keys=("smith20",), bib_keys=("smith20", "jones21"))
        doc = _doc_citing("smith20", "jones21")
        B.build_bibliography_from_source(doc, str(d))

        refs = {r.props["citekey"] for r in doc.objects.values()
                if r.type == "Reference" and not r.props.get("stub")}
        assert "jones21" in refs, "the .bib must fill what the .bbl missed"
        assert counter.calls == 1, "and it is read exactly once"


def test_no_bbl_at_all_reads_the_bib_as_before(monkeypatch):
    """A document with no compiled .bbl is unchanged by this fix."""
    counter = _Counter(B.load_bibtex_file)
    monkeypatch.setattr(B, "load_bibtex_file", counter)
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        _source(d, bbl_keys=(), bib_keys=("smith20",))
        doc = _doc_citing("smith20")
        B.build_bibliography_from_source(doc, str(d))
        assert counter.calls == 1
        refs = {r.props["citekey"] for r in doc.objects.values()
                if r.type == "Reference"}
        assert "smith20" in refs


def test_the_decision_is_about_the_document_not_the_file_size(monkeypatch):
    """Deliberately NOT a size threshold. A 42 MB database that is genuinely
    needed is read; a 2 KB one that is not needed is skipped. The question is
    whether a cited key is still unfilled."""
    counter = _Counter(B.load_bibtex_file)
    monkeypatch.setattr(B, "load_bibtex_file", counter)
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        _source(d, bbl_keys=("smith20",), bib_keys=("smith20",))
        doc = _doc_citing("smith20")
        B.build_bibliography_from_source(doc, str(d))
        assert counter.calls == 0            # tiny .bib, still not needed
