r"""The reading states where a paragraph begins, and the build must not
overrule it with geometry.

A reading carries TWO facts about a line's attachment, and they can disagree:

  * `text_display` beginning "\n\n" -- the reader saying THIS LINE BEGINS A
    BLOCK. `docmodel.text_utils.join_stated` already names it: "a leading
    '\n\n' is it saying the line begins a block".
  * `subtype` in `STATED_JOIN` (`continues_line_space`, `..._no_hyphen`,
    `..._no_space`, `..._newline`) -- the reader saying THIS LINE CONTINUES
    THE ONE BEFORE IT.

0864 p2, column 2, is the shape where they disagree and the disagreement
costs. `g4_p2_l61` is "Definition 1. Let \(A\) and \(B\) be maps defined on a
common domain" -- a numbered environment, plainly a new paragraph, marked
"\n\n" by the reader -- and it ALSO carries `subtype='continues_line_space'`.
It stands at x = 1094 where the column's body edge is 1095, so there is no
indent for `_is_first_line` to see, and it follows `l60` immediately, so
there is no vertical gap either. Nothing in the geometry can stop the
paragraph, and the build ran straight on: ONE Paragraph held `l58`-`l73`,
MathPix's four units (the prose at l58, Definition 1 at l61, the prose at
l67, Proposition 1 at l71) plus the first line of a list.

MEASURED, on the ten-document Gemma4 inspect set (2957de8, yolo), counting
lines the reading marks as beginning a block that the build placed MID
paragraph:

    lib:c9daf79960c3 471   lib:d68e0271bd4d 467   lib:008d43e5db48 424
    BH3 284   2312.11532 62   1805.01788 30   0864 8   US6100897A 6
    lib:5a5c76391c9c 5

and of c9's 471, 407 are lines that mark a block AND state a continuation --
the contradictory cell, not the clean one. The subtype looks mechanical
(c9 stamps `continues_line_space` on 5243 of its 7545 prose lines); the
block marker looks meant. So the marker wins, and that is the whole rule.

WHAT THIS IS NOT. It does not strip the "\n\n" from anyone's text. That was
tried and cost 8 of texbook Appendix G's 34 numbered rules their line in the
projection, which is why `join_stated` leaves a line that states no join to
the caller verbatim. The marker is read here as a BOUNDARY and the text is
untouched.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.base_module import ModuleConfig  # noqa: E402
from docmodel.core import Document  # noqa: E402
from docmodel.modules.page import ingest_lines_json  # noqa: E402
from docmodel.modules.paragraph import ParagraphProcessor  # noqa: E402
from docmodel.text_utils import STATED_JOIN  # noqa: E402

#: 0864 p2 WHOLE, all 108 records out of the real reading. A column-2 slice
#: was tried first and it lied: with column 1 removed, `1117`/`1129` (list
#: items and three indented starts) became recurring edges of column 2, so
#: `_column_states_an_indent` answered True where the real page answers
#: False, and the slice disagreed with the document it was cut from. The
#: page's statistics are a property of the page.
FIXTURE = Path(__file__).parent / "fixtures" / "0864-p2.lines.json"


def _built():
    doc = Document()
    doc.meta["bibkey"] = "T"
    ingest_lines_json(doc, json.loads(FIXTURE.read_text("utf-8")))
    ParagraphProcessor(ModuleConfig(title="ParagraphProcessor",
                                    classname="ParagraphProcessor",
                                    proc_order=13), "T").process_document(doc)
    return doc


def _paragraph_lines(doc):
    """[(Paragraph id, [line id, ...])] in reading order."""
    st = doc.stream("mathpix_lines")
    idx = {a: i for i, a in enumerate(st.anchors)}
    out = []
    for o in doc.objects.values():
        if o.type != "Paragraph":
            continue
        ids = []
        for r in o.realizations:
            if r.stream != "mathpix_lines" or r.role != "surface" \
                    or r.start is None:
                continue
            s = idx.get(r.start)
            e = idx.get(r.end if r.end is not None else r.start)
            if s is None or e is None:
                continue
            for j in range(s, e + 1):
                ids.append(st.payload[st.anchors[j]].get("id"))
        if ids:
            out.append((o.id, ids))
    out.sort(key=lambda t: t[1][0])
    return out


def _marked(doc):
    st = doc.stream("mathpix_lines")
    return {st.payload[a].get("id") for a in st.anchors
            if (st.payload[a].get("text_display") or "").startswith("\n\n")}


def test_the_fixture_really_carries_the_contradiction():
    """Guard against a fixture that passes vacuously: `l61` must actually
    mark a block AND state a continuation, or this file proves nothing."""
    doc = _built()
    st = doc.stream("mathpix_lines")
    pay = next(st.payload[a] for a in st.anchors
               if st.payload[a].get("id") == "g4_p2_l61")
    assert (pay.get("text_display") or "").startswith("\n\n")
    assert pay.get("subtype") in STATED_JOIN
    assert "Definition 1." in (pay.get("text") or "")


def test_a_marked_line_is_never_mid_paragraph():
    """THE INVARIANT. A line the reading marks as beginning a block is the
    FIRST line of its Paragraph or no Paragraph's line at all."""
    doc = _built()
    marked = _marked(doc)
    bad = []
    for pid, ids in _paragraph_lines(doc):
        for k, lid in enumerate(ids):
            if k and lid in marked:
                bad.append((pid, ids[0], lid))
    assert not bad, "marked line placed mid-paragraph: %r" % (bad,)


def test_the_marker_beats_a_stated_continuation():
    """The named case: Definition 1 starts its own Paragraph even though the
    same record says it continues the line before it."""
    doc = _built()
    starts = {ids[0] for _pid, ids in _paragraph_lines(doc)}
    assert "g4_p2_l61" in starts, "Definition 1 did not start a paragraph"
    assert "g4_p2_l71" in starts, "Proposition 1 did not start a paragraph"
    assert "g4_p2_l67" in starts


def test_a_stated_continuation_alone_still_continues():
    """The rule must not shatter prose. `l62`-`l66` state a continuation and
    mark no block, so they stay with Definition 1."""
    doc = _built()
    by_first = {ids[0]: ids for _pid, ids in _paragraph_lines(doc)}
    assert by_first.get("g4_p2_l61") == [
        "g4_p2_l61", "g4_p2_l62", "g4_p2_l63", "g4_p2_l64", "g4_p2_l65",
        "g4_p2_l66"]


def test_the_marker_is_a_boundary_and_not_an_edit():
    r"""The "\n\n" is read as a boundary; nobody's text is rewritten to get
    it. The paragraph's own text still begins with its first word."""
    doc = _built()
    para = next(o for o in doc.objects.values()
                if o.type == "Paragraph"
                and (o.props.get("text") or "").startswith("Definition 1."))
    assert "\\(A\\)" in para.props["text"]
    assert "\n\n" not in para.props["text"]


#: ------------------------------------------------------------------
#: AND WHERE THE PAGE ITSELF STATES THE CONVENTION, THE PAGE WINS.
#:
#: The marker alone was measured on all ten documents of the Gemma4 inspect
#: set (2957de8, yolo), `pagecheck --model --mathpix`, against a baseline
#: built at e653b8db. It is a large win on six and a clear LOSS on one:
#:
#:     document             merged        split        matched
#:     lib:c9daf79960c3   502 ->  79   268 -> 340   1064 -> 1415
#:     BH3                202 ->  24    90 -> 155    203 ->  316
#:     lib:d68e0271bd4d   327 -> 119   280 -> 332   1146 -> 1293
#:     1805.01788          46 ->  20    30 ->  36     50 ->   70
#:     2312.11532          28 ->  12    11 ->  18     74 ->   83
#:     lib:008d43e5db48   155 -> 141   207 -> 483   1429 -> 1167
#:
#: 008d is a German prose book whose paragraphs ARE indented, and whose
#: reader marks SENTENCE starts as well as paragraph starts. 271 MathPix
#: units went from matched to split there, every one of them broken by a mark
#: INSIDE the unit. p117 is the shape: the real paragraphs begin at x = 517,
#: one em right of the column's body edge of 464, and `l10` -- "Man erhält
#: dann das Areal, das für die Verarbeitung von Be..." -- is marked while
#: standing at x = 465, ON the body edge. The page says continuation by not
#: indenting it.
#:
#: The exception is the one LaTeX itself creates: an environment's first line
#: is set FLUSH LEFT, so "Theorem 0.0.1 (...)", "Definition 1." and
#: "Remark 1.1.2." stand at the body edge and are genuine starts. Of the
#: markers the plain rule newly splits, cross-tabbed:
#:
#:     document           states_indent/env   states_indent/no env   no convention
#:     lib:008d43e5db48           0                   181                 243
#:     lib:c9daf79960c3          65                    83                 323
#:     0864                       0                     0                   8
#:
#: 008d's harmful class is ALL of the 181, and 0864 loses nothing. So the
#: marker is overruled only where the column states an indent convention AND
#: the line does not open a numbered environment.

FIXTURE_INDENTED = (Path(__file__).parent / "fixtures"
                    / "008d-p117-indented-prose.lines.json")


def _built_indented():
    doc = Document()
    doc.meta["bibkey"] = "T"
    ingest_lines_json(doc, json.loads(FIXTURE_INDENTED.read_text("utf-8")))
    ParagraphProcessor(ModuleConfig(title="ParagraphProcessor",
                                    classname="ParagraphProcessor",
                                    proc_order=13), "T").process_document(doc)
    return doc


def test_that_fixture_really_states_an_indent_convention():
    """Not vacuous: the column must own two recurring edges with a decided
    body edge, or the filter under test is never exercised."""
    from docmodel.modules.paragraph import _PROSE_TYPES, _is_first_line
    from docmodel.page_edges import _body_edges
    doc = _built_indented()
    edges = _body_edges(doc.stream("mathpix_lines"), _PROSE_TYPES)
    assert edges[117][0] == [464.0, 512.0]
    assert edges[117][3] == {464.0: 17, 512.0: 3}
    assert _is_first_line(517, 117, edges) is True     # the real starts
    assert _is_first_line(465, 117, edges) is False    # the marked line


def test_a_mark_at_the_body_edge_of_an_indented_column_is_not_a_start():
    """`l10` is marked and stands on the body edge, so the page's own
    convention overrules the mark and the paragraph runs on."""
    doc = _built_indented()
    by_first = {ids[0]: ids for _pid, ids in _paragraph_lines(doc)}
    assert "g4_p117_l10" not in by_first, \
        "a sentence start at the body edge began a paragraph"
    assert by_first.get("g4_p117_l3") == [
        "g4_p117_l%d" % k for k in range(3, 13)]


def test_the_indent_itself_still_starts_a_paragraph():
    """The filter must not disable the page's own evidence: x = 517 is an
    indent of one em and still begins a paragraph."""
    doc = _built_indented()
    starts = {ids[0] for _pid, ids in _paragraph_lines(doc)}
    assert "g4_p117_l3" in starts and "g4_p117_l13" in starts


#: ------------------------------------------------------------------
#: AND A SENTENCE DOES NOT BEGIN WITH A LOWERCASE LETTER.
#:
#: Four geometric discriminators were measured and three of them died: "the
#: previous line ends mid-sentence" (lib:008d43e5db48 31 %, lib:c9daf79960c3
#: 32 %, indistinguishable, and lib:d68e0271bd4d is 47 % and improves), "the
#: column states no indent convention" on its own (removes ~40 % of the good
#: markers and ~40 % of the bad), and "the DOCUMENT states an indent
#: convention" (d68e states it on 59.6 % of its pages and improves; 008d on
#: 47.3 % and regresses). None of them separates the document the marker
#: hurts from the ones it helps.
#:
#: Listing the paragraph starts the rule ADDS does separate them, with no
#: hypothesis needed:
#:
#:     added start                 lib:008d43e5db48   lib:c9daf79960c3
#:     begins LOWERCASE                     116                 17
#:     numbered environment label             0                215
#:     begins with a capital                 81                 88
#:     other (list and enum markers)         28                 74
#:     a page number or stray token          15                  1
#:
#: and the lowercase ones are continuations on BOTH documents, so refusing
#: them is not a trade: 008d's are "können Sie es. Warum würden Sie sich
#: sonst..." and "sen wiederum waren 32 selektiv für..." (a hyphenation
#: fragment), c9's are "thereby reduce to the case where \(R\) is a (reduced)
#: local..." and "complete the proof by establishing the following...".
#:
#: German makes this stronger rather than weaker: it capitalises its nouns,
#: so a lowercase first letter cannot be a sentence's first word there
#: either. Refusing the marker is CONSERVATIVE -- it falls back to what the
#: build did before, so the indent rule and the blank-band rule can still
#: start a paragraph on that line if the page says so.

FIXTURE_LOWER = (Path(__file__).parent / "fixtures"
                 / "008d-p65-lowercase-continuation.lines.json")


def _built_lower():
    doc = Document()
    doc.meta["bibkey"] = "T"
    ingest_lines_json(doc, json.loads(FIXTURE_LOWER.read_text("utf-8")))
    ParagraphProcessor(ModuleConfig(title="ParagraphProcessor",
                                    classname="ParagraphProcessor",
                                    proc_order=13), "T").process_document(doc)
    return doc


def test_that_fixture_isolates_the_lowercase_rule():
    """Not vacuous, and not testing the OTHER filter by accident: the column
    owns a single edge, so `_column_states_an_indent` is False and only the
    lowercase refusal can decide `l10`."""
    from docmodel.modules.paragraph import (_PROSE_TYPES,
                                            _column_states_an_indent)
    from docmodel.page_edges import _body_edges
    doc = _built_lower()
    st = doc.stream("mathpix_lines")
    edges = _body_edges(st, _PROSE_TYPES)
    assert edges[65][0] == [464.0]
    pay = next(st.payload[a] for a in st.anchors
               if st.payload[a].get("id") == "g4_p65_l10")
    assert (pay.get("text_display") or "").startswith("\n\n")
    assert _column_states_an_indent(465, 65, edges) is False
    assert (pay.get("text") or "").startswith("können")


def test_a_marked_line_beginning_lowercase_is_a_continuation():
    doc = _built_lower()
    by_first = {ids[0]: ids for _pid, ids in _paragraph_lines(doc)}
    assert "g4_p65_l10" not in by_first, \
        "a lowercase line began a paragraph"
    assert by_first.get("g4_p65_l1") == [
        "g4_p65_l%d" % k for k in range(1, 13)]
