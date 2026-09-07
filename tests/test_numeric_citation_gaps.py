"""640 — the numeric citations the citation stage misses (Steerable).

Steerable emits `\\cite` for most of its 29 numbered references and still
prints 12 literal `[n]`/`[n, locant]` brackets in the body. Measured (not
guessed): every one of the 12 has ZERO Citation object over it, and they fall
into three classes, each a reason `detect_numeric_citations` never looked at
the line at all or its own regex refused the shape:

  LOCANT      `[1, Ch. III]`, `[21, Ch. II.5]` — the bracket has more than a
              digit-list inside it. `_NUMCITE` required the WHOLE bracket to
              be `\\d[\\d,\\s\\-–]*`; a trailing ", Ch. III" broke the match
              and the detector never fired on the line at all, even though it
              IS a `text`-type paragraph line.
  TABLE CELL  `Forster et al. [10]` inside a MathPix `simple_cell`/
              `complex_cell` line. `detect_numeric_citations` only scanned
              `type in ("text", "title")`; a cell is neither, so the line
              was never looked at.
  DIAGRAM     `checkerboard illusion [29]` inside a MathPix `diagram` line's
   CAPTION    own `\\caption{…}` text. Same cause as the table: `type ==
              "diagram"` was excluded from the scan. (The identical caption
              text usually ALSO exists as a duplicate `text`-type paragraph,
              which IS scanned and IS cited — which is why the reader sees
              the citation resolved once and literal once, on the same
              document.)

`_numlist_spans` already gives a locant-tail bracket's LEADING number its own
span (645/642) — it never had a reason to *see* the locant text, since the
outer regex was rejecting the whole bracket before `_numlist_spans` ever ran.
So the LOCANT fix is entirely in `_NUMCITE`; nothing downstream changes.

TABLE CELL is deliberately measured but NOT surfaced in the `.tex`: a `Table`
with no `latex_code` renders its `raw_text` inside `\\begin{verbatim}…
\\end{verbatim}`, where LaTeX does not interpret `\\cite{…}` — substituting
there would print the literal command text. The Citation object is still
created (this file's test), so the model is correct and a future table
projector can use it; `citations.py` counts it under
`citations_outside_running_text` rather than claiming a substitution that
never reaches the reader. See `tests/test_cite_projection.py` for the
DIAGRAM class reaching the `.tex`.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject, Realization
from docops.base import OperatorConfig
from docops.projectors.tiddlywiki import TiddlyWikiProjector
from pdfdrill.bibliography import detect_numeric_citations, link_citations


def _doc_with_refs(nums: list[int]) -> Document:
    doc = Document(meta={"bibkey": "D"})
    mp = doc.ensure_stream("mathpix_lines")
    for n in nums:
        ra = mp.append(type="text", text=f"Author {n}. Title. 20{10 + n}.",
                       _page=99)
        r = DocObject(type="Reference",
                      props={"citekey": f"Ref{n}", "number": n})
        r.add_realization(Realization(stream="mathpix_lines", start=ra,
                                      end=ra, role="surface"))
        doc.add(r)
    return doc


def _line(doc: Document, typ: str, text: str):
    mp = doc.streams["mathpix_lines"]
    return mp.append(type=typ, text=text, text_display=text, _page=1)


# --------------------------------------------------------- 1. LOCANT class

def test_locant_bracket_gets_a_citation_for_the_leading_number():
    doc = _doc_with_refs([1, 7, 19])
    anchor = _line(doc, "text",
                    "can be found, e.g., in [1, Ch. III.1] and elsewhere.")
    n = detect_numeric_citations(doc, max_num=19)
    assert n == 1, "exactly one citation: the leading '1', not a second one"
    cits = list(doc.objects_of_type("Citation"))
    assert len(cits) == 1
    c = cits[0]
    assert c.props["number"] == 1
    r = c.realizations[0]
    assert r.start is anchor
    off, ln = r.props["offset"], r.props["length"]
    text = "can be found, e.g., in [1, Ch. III.1] and elsewhere."
    assert text[off:off + ln] == "1", (off, ln, text[off:off + ln])


def test_locant_bracket_end_to_end_keeps_bracket_and_locant_text():
    """The bracket is not swallowed (content beyond the citation's own span
    remains inside it) and the locant text is untouched, verbatim."""
    from docops.base import OperatorConfig
    from docops.projectors.latex import LaTeXProjector

    doc = _doc_with_refs([1])
    line = "The original meaning can be found in [21, Ch. II.5]: see below."
    body_anchor = _line(doc, "text", line)
    ref = doc.objects_of_type("Reference")[0]
    ref.props["number"] = 21
    ref.props["citekey"] = "Grlebeck2007"

    sec = DocObject(type="Section", props={"caption": "S", "level": 1,
                                            "flow_index": 0, "page": 1})
    sec.add_realization(Realization(stream="mathpix_lines", start=body_anchor,
                                    end=body_anchor, role="surface"))
    doc.add(sec)
    par = DocObject(type="Paragraph", props={"text": line, "page": 1,
                                              "flow_index": 1})
    par.add_realization(Realization(stream="mathpix_lines", start=body_anchor,
                                    end=body_anchor, role="surface"))
    doc.add_child(sec, par)

    n = detect_numeric_citations(doc, max_num=21)
    assert n == 1
    link_citations(doc)

    tex = LaTeXProjector(
        OperatorConfig(op="projector", classname="LaTeXProjector")).project(doc)
    body = tex[tex.index("\\begin{document}"):]
    assert "[\\cite{Grlebeck2007}, Ch. II.5]" in body, body
    assert "[21, Ch. II.5]" not in body, body


# ------------------------------------------------------- 2. TABLE CELL class

def test_table_cell_line_gets_a_numeric_citation():
    doc = _doc_with_refs([6, 10])
    for typ in ("simple_cell", "complex_cell"):
        _line(doc, typ, f"Forster et al. [10]" if typ == "simple_cell"
                        else "Tensor products of Hilbert transforms [6]")
    n = detect_numeric_citations(doc, max_num=10)
    assert n == 2, "both cell lines are now scanned"
    nums = sorted(c.props["number"] for c in doc.objects_of_type("Citation"))
    assert nums == [6, 10]


def test_a_plain_prose_line_is_unaffected_by_the_cell_type_addition():
    """The extension adds types; it must not change what a `text`/`title`
    line already did."""
    doc = _doc_with_refs([3])
    _line(doc, "text", "as shown in [3] before.")
    n = detect_numeric_citations(doc, max_num=3)
    assert n == 1


# ------------------------------------------------------ 3. DIAGRAM class

def test_diagram_caption_line_gets_a_numeric_citation():
    doc = _doc_with_refs([28, 29])
    _line(doc, "diagram",
          "\\begin{figure}\n\\includegraphics{x}\n"
          "\\caption{Fig. 11. (a) Adelson's checkerboard illusion [29]: "
          "the shadow (compare also [28]).}\n\\end{figure}")
    n = detect_numeric_citations(doc, max_num=29)
    assert n == 2
    nums = sorted(c.props["number"] for c in doc.objects_of_type("Citation"))
    assert nums == [28, 29]


# ----------------------- FIX ROUND 1: the locant tail was too permissive

def test_a_matrix_is_never_mistaken_for_a_locant():
    """`_NUMCITE`'s tail was `[^\\]\\d]` — a NON-digit first character after
    the comma — and `\\s*` can match zero characters, so the SPACE after the
    comma satisfied it and `[^\\]]*` then swallowed the rest, digits,
    semicolons and all: `[1, 2; 3, 4]` (a matrix) matched WHOLE and minted
    four bogus Citations, on exactly the table-cell lines this task added
    scanning to. A locant tail must START with a recognisable locant WORD."""
    doc = _doc_with_refs([1, 2, 3, 4])
    _line(doc, "text", "the matrix [1, 2; 3, 4] has four entries.")
    n = detect_numeric_citations(doc, max_num=4)
    assert n == 0, "a matrix is not a citation list"
    assert list(doc.objects_of_type("Citation")) == []


def test_a_plain_two_item_bracket_is_still_the_existing_numeric_list_rule():
    """`[0, 1]` is unaffected by the locant change either way — it has no
    comma-then-word tail, so it never reaches the new branch at all and is
    governed entirely by the PRE-EXISTING per-number range filter
    (`1 <= x <= max_num`, `_numlist_spans`): `0` is never accepted (the
    hardcoded lower bound, "filters intervals like [0,1]" per the
    docstring), regardless of whether a Reference happens to be numbered 0;
    `1` is accepted when it is in range. Same as `test_numeric_citation_
    detection_and_linking`'s `[0,9]` case in test_bibliography.py, one
    number valid instead of zero."""
    doc = _doc_with_refs([1])
    _line(doc, "text", "the interval [0, 1] appears here.")
    n = detect_numeric_citations(doc, max_num=1)
    assert n == 1, "1 is in range; 0 never is, regardless of any Reference"
    nums = [c.props["number"] for c in doc.objects_of_type("Citation")]
    assert nums == [1]


def test_a_locant_bracket_still_resolves_with_the_word_gated_tail():
    doc = _doc_with_refs([24])
    line = "can be found in [24, Ch. III.1] and elsewhere."
    _line(doc, "text", line)
    n = detect_numeric_citations(doc, max_num=24)
    assert n == 1
    c = next(iter(doc.objects_of_type("Citation")))
    assert c.props["number"] == 24
    r = c.realizations[0]
    off, ln = r.props["offset"], r.props["length"]
    assert line[off:off + ln] == "24"


# --------- FIX ROUND 1, finding 3: TiddlyWiki gets the same ownership gate

def test_a_table_cell_citation_is_never_spliced_into_a_paragraph():
    """Coordinator review, finding 3. `_build_inline_subs` took every
    Citation with no owning-type check, and `_transclude_paragraph` walks
    `stream.slice_anchors(surface.start, surface.end)` — a POSITIONAL range,
    not a set of lines the Paragraph actually claims. A Paragraph whose
    realization happens to SPAN a `simple_cell` anchor in between (the 646
    doubly-claimed-anchor shape) would splice the cell's own citation into
    the Paragraph's tiddler text. Reproduced directly: a Paragraph realized
    from line 1 THROUGH line 3, with a `simple_cell` line 2 in between
    carrying a Citation."""
    doc = Document(meta={"bibkey": "D"})
    mp = doc.ensure_stream("mathpix_lines")
    l1 = mp.append(type="text", text="Intro text.", text_display="Intro text.",
                   _page=1)
    l2 = mp.append(type="simple_cell", text="Forster et al. [10]",
                   text_display="Forster et al. [10]", _page=1)
    l3 = mp.append(type="text", text="More text.", text_display="More text.",
                   _page=1)

    par = DocObject(type="Paragraph", props={
        "text": "Intro text. Forster et al. [10] More text.",
        "page": 1, "flow_index": 0})
    par.add_realization(Realization(stream="mathpix_lines", start=l1, end=l3,
                                    role="surface"))
    doc.add(par)

    cit = DocObject(type="Citation", props={"citekey": "Forster2008", "page": 1})
    off = "Forster et al. [".__len__()
    cit.add_realization(Realization(
        stream="mathpix_lines", start=l2, end=l2, role="surface",
        props={"offset": off, "length": 2}))
    doc.add(cit)

    ref = DocObject(type="Reference", props={"citekey": "Forster2008",
                                             "bibkey": "D"})
    ref.add_realization(Realization(stream="mathpix_lines", start=l2, end=l2,
                                    role="surface", props={"offset": off,
                                                           "length": 2}))
    doc.add(ref)

    proj = TiddlyWikiProjector(
        OperatorConfig(op="projector", classname="TiddlyWikiProjector"))
    tiddlers = json.loads(proj.project(doc))
    para_tiddler = next(t for t in tiddlers if t.get("title") == "D_PARA_0001")
    assert "||CIT}}" not in para_tiddler["text"], para_tiddler["text"]
    assert "[10]" in para_tiddler["text"], para_tiddler["text"]
    assert proj.counters.get("citations_outside_running_text") == 1, proj.counters


if __name__ == "__main__":
    import inspect as _inspect
    mod = _inspect.getmodule(test_locant_bracket_gets_a_citation_for_the_leading_number)
    for name, fn in list(vars(mod).items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("\nAll tests passed.")
