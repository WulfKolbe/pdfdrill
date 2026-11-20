r"""A layout heuristic may not cut inside a block the reading bracketed.

lib:d68e0271bd4d, read by Gemma4. A `footnote` record carries the block's
region and hangs the footnote's words off itself as CHILD `text` records. The
`\footnotetext{...}` wrapper is NOT in one record: the opening
`\footnotetext{` sits in the FIRST child's `text_display` and the closing `}`
in the LAST child's. So the span is balanced only across the whole block.

`ParagraphProcessor` does not know the block exists. Its own rules -- the
page's indent (`_is_first_line`), a vertical jump, a caption opener -- cut
between two children, and then NO single Paragraph holds a balanced span.
`heading_cleanup.extract_footnote_paragraphs` scans for `\footnotetext{`,
calls `_balanced`, gets -1, and abstains on the whole group: no body is
lifted and no Footnote is adopted, so the footnote's words stay in the model
twice, once on the Footnote and once on the Paragraph.

MEASURED ACROSS THE TEN-DOCUMENT GEMMA4 SET (g4-526c2e9), BEFORE CHANGING
ANYTHING -- and the correlation is exact, not approximate:

    document            blocks   split   no Paragraph   adopted  unbalanced
    lib:d68e... yolo       156      76             80        79          76
    lib:d68e... inklines   157      78             79        78          78
    0864                     2       1              1         1           1
    lib:c9daf79960c3         1       1              0         0           1
    1805.01788               6       0              6         5           0
    2312.11532               3       0              3         3           0
    lib:008d43e5db48         3       0              3         3           0

"no Paragraph" is the SUCCESS column: the cleanup lifted the body and dropped
the emptied Paragraph, so nothing covers those children any more. Every SPLIT
block leaves exactly one unbalanced span and is abstained on. "one Paragraph"
was ZERO on all twenty arms -- the block either survives whole and is consumed,
or it is cut and lost. On lib:d68e that is 76 abstentions, and 49 footnote
bodies whose words sit in the model twice.

THE RULE: the children of one `footnote` record are one group. The reading
states it (`children_ids`), so a layout rule that would break between two of
them does not fire. This is NOT a claiming rule -- the Paragraph is still
built, which is what 637's adoption needs (11 tests in test_footnote_dedup.py
measure that) -- it is only kept whole.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.base_module import ModuleConfig  # noqa: E402
from docmodel.core import Document  # noqa: E402
from docmodel.modules.footnote import FootnoteProcessor  # noqa: E402
from docmodel.modules.page import ingest_lines_json  # noqa: E402
from docmodel.modules.paragraph import ParagraphProcessor  # noqa: E402
from pdfdrill.heading_cleanup import (_FOOTNOTETEXT,  # noqa: E402
                                      _balanced,
                                      extract_footnote_paragraphs)

#: p18's LAST 13 records, cut out of the real reading: eight prose lines (so
#: the page's own body edge of 170.5 px is a measured fact and not an
#: invention), the `footnote` record, its three children and the copyright
#: line. A fixture of the footnote records ALONE passes vacuously -- with no
#: prose the page has no body edge, so `_is_first_line` can never fire and
#: the block is never cut. Nine records is already too few; thirteen is the
#: smallest set that still reproduces.
FIXTURE = Path(__file__).parent / "fixtures" / "d68e-p18-footnote-block.lines.json"


def _built():
    """The fixture through the two modules that disagree about the block."""
    doc = Document()
    doc.meta["bibkey"] = "T"
    ingest_lines_json(doc, json.loads(FIXTURE.read_text("utf-8")))
    FootnoteProcessor(ModuleConfig(title="FootnoteProcessor",
                                   classname="FootnoteProcessor",
                                   proc_order=2), "T").process_document(doc)
    ParagraphProcessor(ModuleConfig(title="ParagraphProcessor",
                                    classname="ParagraphProcessor",
                                    proc_order=13), "T").process_document(doc)
    return doc


def _paragraphs_over_each_block(doc):
    """{footnote line id: {Paragraph ids covering its children}}."""
    st = doc.stream("mathpix_lines")
    idx = {a: i for i, a in enumerate(st.anchors)}
    by_id = {}
    for a in st.anchors:
        lid = st.payload[a].get("id")
        if lid and lid not in by_id:
            by_id[lid] = a
    owner = {}
    for o in doc.objects.values():
        if o.type != "Paragraph":
            continue
        for r in o.realizations:
            if r.stream != "mathpix_lines" or r.role != "surface" \
                    or r.start is None:
                continue
            s = idx.get(r.start)
            e = idx.get(r.end if r.end is not None else r.start)
            if s is None or e is None:
                continue
            for j in range(s, e + 1):
                owner[st.anchors[j]] = o.id
    out = {}
    for a in st.anchors:
        pay = st.payload[a]
        if pay.get("type") != "footnote":
            continue
        kids = [by_id[c] for c in (pay.get("children_ids") or []) if c in by_id]
        if not kids:
            continue
        ids = {owner.get(k) for k in kids}
        ids.discard(None)
        out[pay.get("id")] = ids
    return out


def test_the_children_of_one_footnote_record_make_one_paragraph():
    """THE INVARIANT. The block must be covered by at most ONE Paragraph.
    Two means the span is cut and every body of that block is lost to the
    cleanup. Here `_is_first_line` cuts it: the children stand at x = 171,
    185 and 208 while the page's body edge is 170.5 with an em of 31, so the
    third child reads as an indent 37 px deep and starts a paragraph."""
    over = _paragraphs_over_each_block(_built())
    assert over, "the fixture must have footnote blocks with children"
    cut = {k: sorted(v) for k, v in over.items() if len(v) > 1}
    assert not cut, "footnote block cut across several Paragraphs: %r" % (cut,)


def test_the_wrapper_left_in_a_paragraph_closes():
    r"""A `\footnotetext{` with no closing brace in the same Paragraph is the
    shape `extract_footnote_paragraphs` cannot read: `_balanced` answers -1
    and the whole group is abstained on."""
    doc = _built()
    bad = []
    for o in doc.objects.values():
        if o.type != "Paragraph":
            continue
        text = o.props.get("text") or ""
        for m in _FOOTNOTETEXT.finditer(text):
            if _balanced(text, m.end() - 1) < 0:
                bad.append(text[:60])
    assert not bad, "unbalanced \\footnotetext span in a Paragraph: %r" % (bad,)


def test_the_cleanup_adopts_every_body_instead_of_abstaining():
    """The consequence, end to end: with the block whole, 637's adoption
    reaches each body and no footnote's words are left in two objects."""
    doc = _built()
    extract_footnote_paragraphs(doc)
    assert int(doc.meta.get("footnote_adopted") or 0) > 0, \
        "nothing adopted — the cleanup abstained"
    assert int(doc.meta.get("footnote_span_not_located") or 0) == 0
    needle = "What you see is what you get"
    fns = [o for o in doc.objects.values() if o.type == "Footnote"
           and needle in (o.props.get("content") or "")]
    paras = [o for o in doc.objects.values() if o.type == "Paragraph"
             and needle in (o.props.get("text") or "")]
    assert len(fns) == 1, "the words must sit on exactly one Footnote"
    assert not paras, "and on no Paragraph as well"
