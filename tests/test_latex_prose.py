"""
LaTeX-source builder (option b): prose Paragraphs + inline Formula objects, with
BOTH forms in parallel — `latex` (macro-EXPANDED, what TiddlyWiki KaTeX renders)
and `latex_original` (the author's un-expanded macro source). Inline math is
transcluded into the paragraph via {{<bibkey>_FO…||FO}} (resolves cleanly).
"""
import sys
import json
import tempfile
import collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import latex_source as ls
from docops.projectors.tiddlywiki import TiddlyWikiProjector, tiddler_integrity
from docops.base import OperatorConfig

_TEX = r"""
\documentclass{article}
\newcommand{\foo}{\mathbf{f}}
\begin{document}
\section{Intro}
This is prose with inline \(\foo\) math and a dollar $E=mc^2$ here.

A second paragraph with no math at all.
\begin{equation} a = b \end{equation}
\end{document}
"""


def _build():
    d = tempfile.mkdtemp()
    p = Path(d) / "x.tex"
    p.write_text(_TEX)
    return ls.build_source_model(str(p), bibkey="paper2024")


def test_prose_and_inline_formula_objects():
    doc = _build()
    c = collections.Counter(o.type for o in doc.objects.values())
    assert c["Section"] >= 1
    assert c["Paragraph"] == 2
    assert c["Formula"] == 2          # \(\foo\) and $E=mc^2$
    assert c["Equation"] == 1         # the display equation

    formulas = [o for o in doc.objects.values() if o.type == "Formula"]
    assert all(o.props.get("display") is False for o in formulas)
    # the macro one keeps BOTH forms in parallel
    foo = next(o for o in formulas if o.props["latex_original"] == r"\foo")
    assert foo.props["latex"] == r"\mathbf{f}"        # EXPANDED → KaTeX/latex field
    assert foo.props["latex_original"] == r"\foo"      # UN-expanded → latex_original


def test_inline_transclusion_resolves():
    doc = _build()
    t = json.loads(TiddlyWikiProjector(OperatorConfig(
        op="projector", classname="TiddlyWikiProjector", params={})).project(doc))
    integ = tiddler_integrity(t)
    assert integ["dangling"] == [] and integ["orphan_synthetic"] == []
    markers = sum(p["text"].count("||FO}}") for p in t
                  if (p.get("tags") or "").startswith("paragraph"))
    assert markers == 2               # both inline formulas transcluded
    # the FO tiddler renders the EXPANDED latex and keeps the original
    fo = [x for x in t if (x.get("tags") or "").startswith("formula")]
    assert any(x.get("latex") == r"\mathbf{f}" and x.get("latex_original") == r"\foo"
               for x in fo)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
