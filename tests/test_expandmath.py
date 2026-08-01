"""
`pdfdrill expandmath` — persist the fully macro-expanded LaTeX in the docmodel.

The model already carries `latex_original` (author source) on every math object.
What it lacked is a durable FULLY-expanded `latex`: a macro the build could not
reach survived, and the pass that fixes it lived only inside the `sre`
projection — recomputed per call, never stored.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from pdfdrill import latex_source as ls
from pdfdrill import commands as C


def _doc(*pairs):
    d = Document(); d.meta["bibkey"] = "K"
    for i, (latex, orig) in enumerate(pairs):
        props = {"latex": latex, "flow_index": i + 1}
        if orig is not None:
            props["latex_original"] = orig
        d.add(DocObject(type="Formula", props=props))
    return d


def _run(tmp_path, monkeypatch, doc, macros, **kw):
    pdf = tmp_path / "K.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
    mp = tmp_path / "m.json"; mp.write_text("{}")
    saved = {}
    monkeypatch.setattr(C, "load_model", lambda p: doc)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    monkeypatch.setattr(C, "_model_path", lambda sc: mp)
    monkeypatch.setattr(C, "_document_macros", lambda d, p=None: macros)
    monkeypatch.setattr(C, "save_model", lambda path, d: saved.setdefault("doc", d))
    msg = C.cmd_expandmath(pdf, **kw)
    return msg, saved.get("doc")


def _math(doc):
    return [o for o in doc.objects.values() if o.type == "Formula"]


def test_persists_expansion_the_build_missed(tmp_path, monkeypatch):
    """The rewrite path: a macro still in `latex` gets expanded and STORED."""
    macros = ls.collect_macros(r"\newcommand{\dom}{\mathbb{D}}", ".")
    doc = _doc((r"x \in \dom", r"x \in \dom"))
    msg, out = _run(tmp_path, monkeypatch, doc, macros)
    o = _math(out)[0]
    assert o.props["latex"] == r"x \in \mathbb{D}"        # expanded + stored
    assert o.props["latex_original"] == r"x \in \dom"     # author form intact
    assert o.props["latex_expanded_by"] == "pdfdrill.expandmath"
    assert "1 rewritten" in msg


def test_never_clobbers_an_existing_latex_original(tmp_path, monkeypatch):
    macros = ls.collect_macros(r"\newcommand{\dom}{\mathbb{D}}", ".")
    doc = _doc((r"x \in \dom", r"AUTHOR-FORM"))
    _, out = _run(tmp_path, monkeypatch, doc, macros)
    assert _math(out)[0].props["latex_original"] == "AUTHOR-FORM"


def test_backfills_latex_original_when_absent(tmp_path, monkeypatch):
    macros = ls.collect_macros(r"\newcommand{\dom}{\mathbb{D}}", ".")
    doc = _doc((r"x \in \dom", None))             # no latex_original yet
    _, out = _run(tmp_path, monkeypatch, doc, macros)
    o = _math(out)[0]
    assert o.props["latex_original"] == r"x \in \dom"     # the pre-expansion form
    assert o.props["latex"] == r"x \in \mathbb{D}"


def test_is_idempotent(tmp_path, monkeypatch):
    macros = ls.collect_macros(r"\newcommand{\dom}{\mathbb{D}}", ".")
    doc = _doc((r"x \in \dom", r"x \in \dom"))
    _run(tmp_path, monkeypatch, doc, macros)
    before = _math(doc)[0].props["latex"]
    msg2, out2 = _run(tmp_path, monkeypatch, doc, macros)
    assert _math(out2)[0].props["latex"] == before
    assert "0 rewritten" in msg2


def test_records_unresolved_macros_on_the_object(tmp_path, monkeypatch):
    """`\\res(a)` — braced-arg macro called with parens; expansion cannot match,
    so the survivor is recorded IN THE MODEL, not just in a projection."""
    macros = ls.collect_macros(r"\newcommand{\res}[1]{\mathrm{res}(#1)}", ".")
    doc = _doc((r"\res(a) = b", r"\res(a) = b"))
    msg, out = _run(tmp_path, monkeypatch, doc, macros)
    assert _math(out)[0].props["macros_unresolved"] == ["\\res"]
    assert "still carry a document macro" in msg


def test_no_macro_table_is_reported_not_silently_skipped(tmp_path, monkeypatch):
    doc = _doc((r"\res(a)", r"\res(a)"))
    msg, out = _run(tmp_path, monkeypatch, doc, None)
    assert "No LaTeX macro table" in msg and "injectlatex" in msg
    assert out is None                            # nothing saved
