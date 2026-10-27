r"""Only a display equation ever got the author's reading, on one route.

THE OWNER'S NEXT STEP (drillgroup, 2026-10-27, after T-0080 items 1-2):
"Author LaTeX on every route" — with a MathPix (or any other) lines.json on
disk, `drill` must still give the author's LaTeX for INLINE formulas too.
The gate: 1702.06385 drilled once with a MathPix lines.json present and once
without; both give the author's reading on every maths object it can be
matched to, and KaTeX refusals are counted the same way.

THE TWO DEFECTS, MEASURED (2026-10-27, 1702.06385, the gate document):

  born-digital route   170 maths objects, 170 with the author's latex (100%)
  MathPix route        178 maths objects,  18 with the author's latex (10%)

Both numbers are correct and neither is a reading of the same thing. On the
born-digital route there are NO MathPix objects to overlay onto, so
`cmd_injectlatex` CREATES the author's display equations as the document's
equations — every maths object is the author's by construction, and the
document's 160 inline formulas are simply absent. On the MathPix route the
model has 18 Equation and 160 Formula objects; `cmd_injectlatex` reaches
`extract_display_equations` only, so the 160 inline formulas get nothing —
and `cmd_model`'s auto-merge is gated on `lines_source in ("pdfminer-chars",
"pdfplumber-chars")`, so on a MathPix document it never even runs.

So two things are missing, not one: an inline pass (this file's
`extract_inline_math` + `attach_author_inline`), and the route gate that kept
it from running at all.

WHY AN EXACT KEY AND NOT A SIMILARITY THRESHOLD. The display loop attaches at
`latex_similarity >= 0.55`, which is right for an equation: it is long, so a
score that high means the same mathematics. An inline formula is three
characters. Measured on 1702.06385 with that same threshold, the best match
for the model's `\mid` is the author's `\min` (0.75), for `X_{2}` it is `Y_2`
(0.67), for `\mathcal{G} \leftarrow` it is `\mathcal{M}_{X \rightarrow Y}`
(0.84). A wrong author reading is not a partial result — the inspector would
show the author writing something they did not write. So the inline pass
attaches on an EXACT key match and leaves the rest unmatched, which is a
number it can report.
"""
import json
import re
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands as C
from pdfdrill import latex_source as ls
from pdfdrill import latex_only as L
from pdfdrill.scoring import author_match_key, latex_similarity, normalize_latex


# --------------------------------------------------------------- the harvest

def test_inline_math_is_found_in_both_spellings():
    got = ls.extract_inline_math(r"Let $x$ be and \(y + 1\) too.")
    assert [it["latex"] for it in got] == ["x", "y + 1"]
    assert [it["delim"] for it in got] == ["$", "\\("]
    assert got[0]["pos"] < got[1]["pos"]


def test_display_maths_is_not_harvested_as_inline():
    r"""`extract_display_equations` already reads these. Harvesting them here
    too would give one equation two author readings — and the second one keyed
    as inline, so the inspector would show the same formula twice."""
    body = r"Before $$a = b$$ and \[c = d\] and \begin{equation}e = f\end{equation} after."
    assert ls.extract_inline_math(body) == []


def test_verbatim_is_not_maths():
    body = "text\n\\begin{verbatim}\nfor $i in x; do echo $i; done\n\\end{verbatim}\nmore"
    assert ls.extract_inline_math(body) == []
    body2 = "\\begin{lstlisting}\nprintf(\"%d\", $a$);\n\\end{lstlisting}"
    assert ls.extract_inline_math(body2) == []


def test_an_algorithm_block_carries_the_authors_inline_maths():
    r"""THE CASE THAT CHOSE THE BLANKING RULE. `build_source_model` splits prose
    with `_STRUCT_RE`, which blanks `algorithm`/`algorithmic`, `figure`,
    `table`, `itemize`, … — right for PROSE (those blocks are not paragraphs),
    wrong for MATHS (the `$...$` inside them is the author's, and MathPix reads
    every one of those pseudocode lines as a Formula).

    Measured on 1702.06385: harvesting with `_STRUCT_RE` matches 109 of the
    model's 160 Formula objects; harvesting with the narrow rule — only display
    maths and verbatim hide inline maths — matches 123. The 14 are the
    document's algorithm block.
    """
    body = (r"\begin{algorithm}" "\n"
            r"\STATE $T_i \leftarrow \textsc{TrivialTree}(a_i)$" "\n"
            r"\end{algorithm}")
    assert [it["latex"] for it in ls.extract_inline_math(body)] == \
        [r"T_i \leftarrow \textsc{TrivialTree}(a_i)"]


def test_an_escaped_dollar_is_not_a_delimiter():
    assert ls.extract_inline_math(r"costs \$5 and \$7 each") == []


def test_a_caption_carries_inline_maths():
    body = r"\begin{figure}\caption{The map $f: A \to B$.}\end{figure}"
    assert [it["latex"] for it in ls.extract_inline_math(body)] == [r"f: A \to B"]


# ------------------------------------------------------------------ the key

#: Each stated equivalence, with the two spellings the corpus actually carries.
#: Every one of these was a MISS before the key existed, and the model's form
#: on the left is MathPix's reading of the author's form on the right.
SAME_MATHS = [
    ("ldots",     r"j \in\{1, \ldots, l\}",            r"j \in \{ 1, \dots, l \}"),
    ("operatorname/textsc",
                  r"T_{i} \leftarrow \operatorname{TrivialTree}\left(a_{i}\right)",
                  r"T_i \leftarrow \textsc{TrivialTree}(a_i)"),
    ("operatorname/textit", r"\operatorname{type}(a)", r"\textit{type}(a)"),
    ("operatorname/mathit", r"\operatorname{res}(a)",  r"\mathit{res}(a)"),
    ("prime",     r"L\left(T_{i}^{\prime}\right)",     r"L(T'_i)"),
    ("left/right", r"\left(M_{X}, M_{Y}\right)",       r"(M_X, M_Y)"),
]


@pytest.mark.parametrize("name,model,author", SAME_MATHS,
                         ids=[r[0] for r in SAME_MATHS])
def test_the_same_maths_in_two_spellings_shares_one_key(name, model, author):
    assert author_match_key(model) == author_match_key(author), \
        f"{name}: {author_match_key(model)!r} != {author_match_key(author)!r}"


#: Pairs a 0.55 similarity threshold calls the same formula and that are NOT
#: the same mathematics. Every one is from 1702.06385, with its measured score.
NOT_THE_SAME = [
    (r"\mid", r"\min", 0.75),
    (r"l \in", r"\min", 0.75),
    (r"X_{2}", r"Y_2", 0.67),
    (r"\mathcal{G} \leftarrow", r"\mathcal{M}_{X \rightarrow Y}", 0.84),
    (r"M_{X \rightarrow Y}=", r"{X \rightarrow Y}", 0.82),
    (r"\mathrm{Crack}_{\delta}", r"\delta", 0.67),
]


@pytest.mark.parametrize("model,author,sim", NOT_THE_SAME,
                         ids=[r[0] for r in NOT_THE_SAME])
def test_a_short_formula_is_not_matched_by_similarity(model, author, sim):
    """The score is high and the mathematics is different. The threshold that
    is right for a display equation attaches the WRONG author reading here."""
    assert latex_similarity(model, author) >= 0.55
    assert author_match_key(model) != author_match_key(author)


def test_the_key_never_empties_a_formula():
    for s in (r"x", r"\alpha", r"\square", r"P(X)"):
        assert author_match_key(s), s


def test_the_key_is_stable():
    k = author_match_key(r"\operatorname{res}\left(a_{i}\right)")
    assert author_match_key(k) == k


def test_the_shared_normalizer_is_not_changed():
    r"""`normalize_latex` is `compare`'s and `scoring`'s own comparison, and
    every agreement number this repo quotes came from it. Extending ITS
    `_MATHRM` list would match these pairs too, and would move every one of
    those numbers. The key is a second function for that reason."""
    assert normalize_latex(r"\textit{type}(a)") != normalize_latex(r"\operatorname{type}(a)")


# ------------------------------------------------------------- the attach

_SOURCE = r"""
\documentclass{article}
\newcommand{\dom}{\ensuremath{\mathbb{D}}}
\begin{document}
Let $x^2 + 1$ and $\dom(a)$ and $x^2 + 1$ again, with $\textsc{Crack}(D)$.
\begin{equation}
L(D, M) = L(M)
\end{equation}
\end{document}
"""


def _mathpix_model():
    """A MathPix-shaped model: Formula objects with a `latex` prop and NO
    `latex_original` — which is the whole defect, written down as a fixture."""
    from docmodel.core import Document, DocObject
    doc = Document(meta={"bibkey": "GATE"})
    for i, lat in enumerate([
            r"x^{2}+1",                       # the author's, two occurrences
            r"x^{2}+1",
            r"\mathbb{D}(a)",                 # the author wrote it as a macro
            r"\operatorname{Crack}(D)",       # MathPix's font, the author's \textsc
            r"\mid",                          # a fragment: nothing to match
    ], 1):
        doc.add(DocObject(type="Formula",
                          props={"latex": lat, "display": False, "flow_index": i}))
    doc.add(DocObject(type="Equation", props={"latex": r"L(D, M) = L(M)",
                                              "flow_index": 9}))
    return doc


def _attach(doc, force=False):
    preamble, body = ls.split_preamble(_SOURCE)
    return C.attach_author_inline(doc, body, ls.extract_macros(preamble), force=force)


def _tex(obj):
    return [r for r in obj.realizations
            if r.provenance == "tex" and r.role == "latex_candidate"]


def test_a_matched_formula_carries_the_authors_own_source():
    doc = _mathpix_model()
    counts = _attach(doc)
    forms = [o for o in doc.objects.values() if o.type == "Formula"]
    hit = [o for o in forms if _tex(o)]
    assert counts["attached"] == len(hit) == 4, counts
    assert counts["formulas"] == 5
    by_latex = {o.props["latex"]: o for o in forms}
    r = _tex(by_latex[r"\mathbb{D}(a)"])[0]
    assert r.props["latex_original"] == r"\dom(a)"      # what the author typed
    assert r.props["latex"] == r"\mathbb{D}(a)"         # expanded AND resolved
    assert r.props["inline"] is True


def test_an_unmatched_formula_is_left_alone():
    """`\\mid` is MathPix's fragment of a formula it split. Nothing in the
    source is that formula, and inventing one is the defect this guards."""
    doc = _mathpix_model()
    _attach(doc)
    frag = next(o for o in doc.objects.values()
                if o.type == "Formula" and o.props["latex"] == r"\mid")
    assert _tex(frag) == []


def test_every_occurrence_of_one_formula_gets_the_reading():
    r"""MathPix emits one Formula per OCCURRENCE — the symbol `$x^2+1$` used
    twice is two objects. The attach is content-keyed for that reason: a
    one-to-one assignment (the display loop's shape) would leave the second
    occurrence of every repeated symbol unread."""
    doc = _mathpix_model()
    _attach(doc)
    same = [o for o in doc.objects.values()
            if o.type == "Formula" and o.props["latex"] == r"x^{2}+1"]
    assert len(same) == 2
    assert all(_tex(o) for o in same)


def test_the_authors_form_is_renderable():
    r"""T-0080's rules apply here too: the author wrote `\ensuremath{\mathbb{D}}`
    and KaTeX cannot render that. `expand_math`, not `expand_macros`."""
    doc = _mathpix_model()
    _attach(doc)
    for o in doc.objects.values():
        for r in _tex(o):
            assert L.names_left(r.props["latex"]) == [], r.props["latex"]


def test_a_display_equation_is_not_touched_by_the_inline_pass():
    """The display loop owns Equation objects. Two passes writing the same
    realization is how an object ends up with two author readings."""
    doc = _mathpix_model()
    _attach(doc)
    eq = next(o for o in doc.objects.values() if o.type == "Equation")
    assert _tex(eq) == []


def test_running_it_twice_attaches_once():
    doc = _mathpix_model()
    first = _attach(doc)
    second = _attach(doc)
    assert second["attached"] == 0, second
    assert second["already"] == first["attached"]
    for o in doc.objects.values():
        assert len(_tex(o)) <= 1


def test_force_replaces_the_reading():
    doc = _mathpix_model()
    _attach(doc)
    again = _attach(doc, force=True)
    assert again["attached"] == 4
    for o in doc.objects.values():
        assert len(_tex(o)) <= 1


# --------------------------------------------------------------- the route

def _mathpix_lines():
    return {"source": "mathpix", "total_pages": 1, "pages": [
        {"page_number": 1, "page_width": 612, "page_height": 792, "lines": [
            {"text": "Let $x^2$ hold.", "type": "text",
             "region": {"top_left_x": 10, "top_left_y": 10,
                        "width": 200, "height": 12}}]}]}


def test_the_author_overlay_runs_on_the_mathpix_route(monkeypatch):
    """The gate that made this a born-digital-only feature. `cmd_model` ran the
    overlay only for `pdfminer-chars`/`pdfplumber-chars`, so a document with a
    MathPix lines.json on disk got geometry and MathPix's reading and no author
    LaTeX at all."""
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        C._lines_json_path(pdf).write_text(json.dumps(_mathpix_lines()))
        called = []
        monkeypatch.setattr(C, "_arxiv_id_for", lambda p, sc=None: "1702.06385")
        monkeypatch.setattr(C, "cmd_injectlatex",
                            lambda p, *a, **k: called.append("injectlatex") or "ok")
        monkeypatch.setattr(C, "cmd_merge",
                            lambda p, *a, **k: called.append("merge") or "ok")
        C.cmd_model(pdf)
        assert "injectlatex" in called, called


def test_the_prose_merge_stays_on_the_born_digital_route(monkeypatch):
    r"""`cmd_merge` replaces the model's prose with the author's, because the
    born-digital char layer is garbled by two-column interleaving and the arXiv
    margin stamp. MathPix's prose is not garbled, and replacing it would throw
    away the reading the owner paid for. The author's MATHS is the thing that
    was missing — not their prose."""
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        C._lines_json_path(pdf).write_text(json.dumps(_mathpix_lines()))
        called = []
        monkeypatch.setattr(C, "_arxiv_id_for", lambda p, sc=None: "1702.06385")
        monkeypatch.setattr(C, "cmd_injectlatex",
                            lambda p, *a, **k: called.append("injectlatex") or "ok")
        monkeypatch.setattr(C, "cmd_merge",
                            lambda p, *a, **k: called.append("merge") or "ok")
        C.cmd_model(pdf)
        assert "merge" not in called, called


def test_no_source_still_means_no_author_source(monkeypatch):
    """`--no-source` exists so a READER can be measured with the author's
    source out of the way (`model_route_choice`). Running the overlay on every
    route must not put the author's equations and TikZ back into the one model
    that asked to be without them."""
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        C._lines_json_path(pdf).write_text(json.dumps(_mathpix_lines()))
        called = []
        monkeypatch.setattr(C, "_arxiv_id_for", lambda p, sc=None: "1702.06385")
        monkeypatch.setattr(C, "cmd_injectlatex",
                            lambda p, *a, **k: called.append("injectlatex") or "ok")
        C.cmd_model(pdf, no_source=True)
        assert called == [], called


def test_injectlatex_reports_the_inline_count():
    """A pass whose number is not reported is a pass nobody can audit: the
    report line and the sidecar both carry it."""
    import inspect
    src = inspect.getsource(C.cmd_injectlatex)
    assert "attach_author_inline" in src
    assert "latex_inline_attached" in src


def test_injectlatex_attaches_the_inline_reading_end_to_end():
    """The command, not the helper: a model on disk, the author's .tex beside
    the PDF, `pdfdrill injectlatex`'s own entry point. The report line carries
    the count, and the realization is in the saved model."""
    from pdfdrill.model_io import save_model
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        (Path(d) / "paper.tex").write_text(_SOURCE, encoding="utf-8")
        sc = C.Sidecar(pdf)
        sc.blob_dir.mkdir(parents=True, exist_ok=True)
        save_model(sc.blob_dir / "model.docmodel.json", _mathpix_model())
        sc.mark(C.MODEL_BUILT, produced_by="model")
        sc.save()
        out = C.cmd_injectlatex(pdf)
        assert "Inline: 4 of 5 Formula object(s)" in out, out
        doc = json.loads((sc.blob_dir / "model.docmodel.json").read_text())
        objs = doc["objects"]
        objs = objs if isinstance(objs, list) else list(objs.values())
        forms = [o for o in objs if o["type"] == "Formula"]
        got = [o for o in forms
               if any(r.get("provenance") == "tex"
                      and (r.get("props") or {}).get("inline")
                      for r in (o.get("realizations") or []))]
        assert len(forms) == 5 and len(got) == 4, (len(forms), len(got))
        assert C.Sidecar(pdf).get_evidence("latex_inline_attached") == 4


def test_the_inspector_shows_an_inline_author_reading():
    """END TO END, no browser: the realization the attach writes is the shape
    `docinspect._author_latex` reads, so the inspector's author pane and its
    KaTeX audit count inline formulas on the same footing as equations."""
    from pdfdrill import docinspect
    doc = _mathpix_model()
    _attach(doc)
    fo = next(o for o in doc.objects.values()
              if o.type == "Formula" and o.props["latex"] == r"\mathbb{D}(a)")
    got = docinspect._author_latex(json.loads(json.dumps(fo.to_dict())))
    assert got.get("latex_original") == r"\dom(a)"
    assert got.get("orig_from") == "tex"
