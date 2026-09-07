"""647 — `expandmath` and `formulas` crashed on EVERY document, and the suite
could not see it.

    Error [TypeError]: _texsrc_dir() takes 1 positional argument but 2 were given

`src/pdfdrill/commands.py` defined `_texsrc_dir` TWICE at module level: once at
line ~6743 as `_texsrc_dir(doc, pdf)` (the Document form, used by
`_document_macros` / `_document_macro_names`, which `cmd_expandmath` and
`cmd_formulas` both call) and again ~1400 lines later as `_texsrc_dir(sc)` (the
Sidecar form, used by `cmd_texfigures`). Python keeps the LAST definition, so
the second silently replaced the first for the whole module and every caller of
the two-argument form died.

`tests/test_expandmath.py` monkeypatches `_document_macros`, so the real call
was never made in the suite. Two tests here, at two levels:

  * the CAUSE — no module in `src/` may bind the same top-level name twice;
  * the SYMPTOM — the real `_document_macros(doc, pdf)` / `_document_macro_names(doc, pdf)`
    are called with two arguments against a real cached e-print directory.
"""
from __future__ import annotations

import ast
import collections
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from docmodel.core import Document, DocObject          # noqa: E402
from pdfdrill import commands as C                     # noqa: E402


# ---------------------------------------------------------------------------
# the cause
# ---------------------------------------------------------------------------

def test_no_module_defines_the_same_top_level_name_twice():
    """A redefinition is invisible in a 10,000-line module — and it does not
    fail at import, only at the first call with the wrong signature."""
    dupes = []
    for f in sorted((REPO / "src").rglob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        seen: dict[str, list[int]] = collections.defaultdict(list)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                seen[node.name].append(node.lineno)
        for name, lines in seen.items():
            if len(lines) > 1:
                dupes.append(f"{f.relative_to(REPO)}: {name} at lines {lines}")
    assert not dupes, (
        "a later definition silently shadows the earlier one:\n  "
        + "\n  ".join(dupes))


# ---------------------------------------------------------------------------
# the symptom — the two-argument form, really called
# ---------------------------------------------------------------------------

def _doc_with_source(tmp_path: Path) -> tuple[Document, Path]:
    src = tmp_path / "texsrc"
    src.mkdir()
    (src / "main.tex").write_text(
        r"\newcommand{\dom}{\mathbb{D}}" "\n" r"\begin{document}x\end{document}",
        encoding="utf-8")
    doc = Document()
    doc.meta["bibkey"] = "K"
    doc.meta["latex_source_dir"] = str(src)
    doc.add(DocObject(type="Formula", props={"latex": r"x \in \dom", "flow_index": 1}))
    pdf = tmp_path / "K.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    return doc, pdf


def test_document_macros_takes_doc_and_pdf(tmp_path):
    doc, pdf = _doc_with_source(tmp_path)
    table = C._document_macros(doc, pdf)          # TypeError before 647
    assert table is not None, "the cached e-print was not found"
    assert "dom" in table or r"\dom" in table, table


def test_document_macro_names_takes_doc_and_pdf(tmp_path):
    doc, pdf = _doc_with_source(tmp_path)
    names = C._document_macro_names(doc, pdf)     # TypeError before 647
    assert names, "no macro names read back from the cached e-print"


def test_texsrc_dir_resolves_from_the_document(tmp_path):
    doc, pdf = _doc_with_source(tmp_path)
    d = C._texsrc_dir(doc, pdf)                   # TypeError before 647
    assert d is not None and d.name == "texsrc"


def test_author_texsrc_dir_still_takes_a_sidecar(tmp_path):
    """The other function is still there, under its own name, unchanged."""
    from pdfdrill.sidecar import Sidecar
    doc, pdf = _doc_with_source(tmp_path)
    sc = Sidecar(pdf)
    (sc.blob_dir / "texsrc").mkdir(parents=True, exist_ok=True)
    assert C._author_texsrc_dir(sc) == sc.blob_dir / "texsrc"


# ---------------------------------------------------------------------------
# the two commands that crashed, end to end (no _document_macros patch)
# ---------------------------------------------------------------------------

def test_expandmath_reaches_the_macro_table_without_a_typeerror(tmp_path, monkeypatch):
    doc, pdf = _doc_with_source(tmp_path)
    mp = tmp_path / "m.json"
    mp.write_text("{}")
    monkeypatch.setattr(C, "load_model", lambda p: doc)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    monkeypatch.setattr(C, "_model_path", lambda sc: mp)
    monkeypatch.setattr(C, "save_model", lambda path, d: None)
    msg = C.cmd_expandmath(pdf)
    assert "TypeError" not in msg
    assert "No LaTeX source cached" not in msg, msg
    o = next(o for o in doc.objects.values() if o.type == "Formula")
    assert o.props["latex"] == r"x \in \mathbb{D}"
