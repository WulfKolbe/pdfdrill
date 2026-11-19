r"""One writer per record: the Footnote claims the lines it took its text from.

lib:d68e0271bd4d p170. A `footnote` record carries the block's REGION -- 207 px
tall, text empty -- and hangs the footnote's words off itself as CHILD records.
`FootnoteProcessor` read those children for its `content` but realized only the
parent, so `ParagraphProcessor` made Paragraphs out of them. The words then
existed twice in one model, under two objects, and the Footnote's block box lay
over the Paragraph holding its own text: 13 of that page's 15 overlap findings,
every one at share_of_smaller 1.00.

THE FIXTURE IS CUT FROM THE REAL READING, not written by hand. Three hand-made
fixtures passed vacuously in one day on this codebase -- glyphs whose baseline
defaulted to 0 so a distance test never ran, four lines where the edge finder
needs three at one x before it finds an edge at all, and a `props["region"]`
that no real object carries. Each time the unit tests were green and the page
was untouched. `tests/fixtures/d68e-p170-footnotes.lines.json` is that page's
three footnote records and their 14 children, copied out of the reading.

NOT FIXED YET, AND THE FIRST TWO ARE XFAIL. The cure is NOT to have the
Footnote claim those records: `heading_cleanup.extract_footnote_paragraphs`
already adopts the Paragraph into the existing Footnote (637), and a claiming
rule stops the Paragraph being built so the adoption has nothing to adopt --
11 tests in test_footnote_dedup.py say so, measured. The adoption is not
failing either: called again it returns 0 and raises nothing. It adopted 35 of
this book's 132 Footnotes and ABSTAINED on 97, because `footnote_extent` holds
that "where there is no extent nothing is adopted". Those 97 abstentions are
this defect, and the work is extent location on a Gemma4-shaped reading.

WHAT IS ASSERTED, in the order it went wrong:
  * the footnote's words appear ONCE in the model, on the Footnote;
  * no Paragraph is built from a record the Footnote claimed;
  * the Footnote realizes the region record AND the records its words came
    from, so its box is the block the page shows and nothing is unclaimed.
"""
import json
import sys

import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.base_module import ModuleConfig  # noqa: E402
from docmodel.core import Document  # noqa: E402
from docmodel.modules.footnote import FootnoteProcessor  # noqa: E402
from docmodel.modules.page import ingest_lines_json  # noqa: E402
from docmodel.modules.paragraph import ParagraphProcessor  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "d68e-p170-footnotes.lines.json"


def _built():
    doc = Document()
    ingest_lines_json(doc, json.loads(FIXTURE.read_text("utf-8")))
    FootnoteProcessor(ModuleConfig(title="FootnoteProcessor",
                                   classname="FootnoteProcessor",
                                   proc_order=2), "T").process_document(doc)
    ParagraphProcessor(ModuleConfig(title="ParagraphProcessor",
                                    classname="ParagraphProcessor",
                                    proc_order=13), "T").process_document(doc)
    return doc


@pytest.mark.xfail(strict=True, reason=(
    "footnote_extent abstains on this shape: 35 of 132 adopted on "
    "lib:d68e0271bd4d. See this file's docstring before 'fixing' it by "
    "claiming the records -- that breaks 637's adoption."))
def test_the_footnote_text_is_in_the_model_once():
    doc = _built()
    needle = "The structural and formal justif"
    fns = [o for o in doc.objects_of_type("Footnote")
           if needle in (o.props.get("content") or "")]
    paras = [o for o in doc.objects_of_type("Paragraph")
             if needle in (o.props.get("text") or "")]
    assert fns, "the Footnote must carry the words"
    assert not paras, "and no Paragraph may carry them as well"


@pytest.mark.xfail(strict=True, reason=(
    "same: the Footnote realizes only the region record until the extent "
    "rule reaches this reading's shape"))
def test_the_footnote_realizes_the_records_its_words_came_from():
    doc = _built()
    st = doc.stream("mathpix_lines")
    idx = {a: i for i, a in enumerate(st.anchors)}
    fn = next(o for o in doc.objects_of_type("Footnote")
              if "The structural and formal justif" in (o.props.get("content") or ""))
    claimed = set()
    for r in fn.realizations:
        if r.stream != "mathpix_lines":
            continue
        s, e = idx.get(r.start), idx.get(r.end)
        if s is not None and e is not None:
            claimed.update(st.anchors[s:e + 1])
    texts = "".join((st.payload.get(a) or {}).get("text") or "" for a in claimed)
    assert len(claimed) > 1, "the region record alone is not enough"
    assert "The structural and formal justif" in texts, \
        "the records it realizes must include the one holding its words"


def test_no_record_is_claimed_by_two_objects():
    """The ledger's `claimed more than once`, asserted on the page that had it:
    2 -> 0 over the whole book."""
    doc = _built()
    st = doc.stream("mathpix_lines")
    idx = {a: i for i, a in enumerate(st.anchors)}
    seen: dict = {}
    for o in doc.objects.values():
        if o.type == "Page":
            continue
        for r in o.realizations:
            if r.stream != "mathpix_lines" or r.role != "surface":
                continue
            if r.props and ("offset" in r.props or "length" in r.props):
                continue
            s, e = idx.get(r.start), idx.get(r.end)
            if s is None or e is None:
                continue
            for a in st.anchors[s:e + 1]:
                seen.setdefault(a, []).append(o.type)
    twice = {a: k for a, k in seen.items() if len(k) > 1}
    assert not twice, "records claimed twice: %s" % list(twice.values())[:3]
