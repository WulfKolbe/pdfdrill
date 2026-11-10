r"""A record in the reading that no module claims must not vanish.

OWNER, 2026-11-10: "the lines.json is the interface and the rest must be normal
pdfdrill function not any special cases … I need these view to optimize and
adjust the lowest levels of the blob search (now written in C). Any kind of
correction is unwanted."

WHAT WAS WRONG. `lines.json` is the documented interface, and the model built
from it kept only the 16 line types in `docmodel.line_types`. Every other record
was DROPPED — not reported, not counted, simply absent from the model and
therefore from `inspect`, `md`, `tiddlers` and every other projection.

MEASURED with a reading in GLYPHDRILL3's shape (8 records): the model came out
with 4 objects and the inspector drew 2 boxes.

    text      -> Paragraph   drawn
    diagram   -> Diagram     drawn
    page_info -> Page        frame only
    column    -> DROPPED
    gd3_block -> DROPPED
    gd3_white -> DROPPED
    gd3_word  -> DROPPED

A reader cannot adjust a layout stage whose output is invisible. And this is the
same class as the figure glyphs (D1, 2109f4a7): content present in the input,
absent from the result, with nothing saying so.

THE RULE: everything in the reading reaches the model. A module that recognises
a record claims it as it always did; a record nobody claims becomes an object
carrying ITS OWN TYPE and ITS OWN REGION, verbatim. No correction, no
normalisation, no renaming, no reordering, no dropping — the owner asked for the
rectangles as the reading states them, and a viewer that silently improves its
input is useless for adjusting the stage that produced it.

This is not a special case or a flag. `pdfdrill model` then `pdfdrill inspect`
is the normal path, and it now shows what the interface carries.
"""
from docmodel.base_module import ModuleConfig
from docmodel.core import Document

from docmodel.modules.unclaimed import UnclaimedLineProcessor


def _proc():
    return UnclaimedLineProcessor(
        ModuleConfig(title="U", classname="UnclaimedLineProcessor", proc_order=998),
        "T")


def _reading(records):
    """A Document with a mathpix_lines stream, as a lines.json ingest leaves it."""
    doc = Document()
    doc.meta["pages"] = [{"page": 1, "page_width": 3307, "page_height": 4677}]
    mp = doc.ensure_stream("mathpix_lines")
    for r in records:
        mp.append(**r)
    return doc


def _run(doc):
    _proc().process_document(doc)
    return [o for o in doc.objects.values()]


GD3 = [
    {"text": "page 1", "_page": 1, "type": "page_info",
     "region": {"top_left_x": 0, "top_left_y": 0, "width": 3307, "height": 4677}},
    {"text": "left column", "_page": 1, "type": "column",
     "region": {"top_left_x": 389, "top_left_y": 1667, "width": 1222, "height": 2667}},
    {"text": "block 1", "_page": 1, "type": "gd3_block",
     "region": {"top_left_x": 389, "top_left_y": 1667, "width": 1222, "height": 667}},
    {"text": "gutter", "_page": 1, "type": "gd3_white",
     "region": {"top_left_x": 1622, "top_left_y": 1667, "width": 61, "height": 2667}},
    {"text": "Fengshenbang", "_page": 1, "type": "gd3_word",
     "region": {"top_left_x": 389, "top_left_y": 400, "width": 500, "height": 83}},
]


def test_an_unclaimed_record_becomes_an_object():
    doc = _reading(GD3)
    objs = _run(doc)
    assert len(objs) == len(GD3), (
        f"{len(GD3)} records in the reading, {len(objs)} objects in the model")


def test_the_record_keeps_its_own_type_verbatim():
    """`gd3_block` stays `gd3_block`. The owner is adjusting the stage that
    emitted that name; renaming it to something this repo recognises would hide
    exactly the distinction they are looking at."""
    doc = _reading(GD3)
    kinds = {o.props.get("lines_type") for o in _run(doc)}
    assert kinds == {"page_info", "column", "gd3_block", "gd3_white", "gd3_word"}


def test_the_region_is_passed_through_unchanged():
    """NO CORRECTION. Not re-scaled, not clipped to the page, not rounded, not
    reordered. The owner said a rectangle in the wrong place is their stage's
    problem to fix — so the viewer must show the wrong place, exactly."""
    doc = _reading(GD3)
    by_type = {o.props.get("lines_type"): o for o in _run(doc)}
    assert by_type["gd3_white"].props["region"] == {
        "top_left_x": 1622, "top_left_y": 1667, "width": 61, "height": 2667}
    assert by_type["gd3_word"].props["region"] == {
        "top_left_x": 389, "top_left_y": 400, "width": 500, "height": 83}


def test_a_record_a_real_module_already_claimed_is_left_alone():
    """This runs last in the pipeline and must not duplicate what the recognised
    modules built: a `text` line that became a Paragraph stays one object."""
    from docmodel.core import DocObject, Realization
    doc = _reading([{"text": "body prose", "_page": 1, "type": "text",
                     "region": {"top_left_x": 10, "top_left_y": 20,
                                "width": 30, "height": 40}}])
    mp = doc.stream("mathpix_lines")
    a = mp.anchors[0]
    p = DocObject(type="Paragraph", props={"text": "body prose", "page": 1})
    p.add_realization(Realization(stream="mathpix_lines", start=a, end=a,
                                  role="surface"))
    doc.add(p)
    before = len(doc.objects)
    _proc().process_document(doc)
    assert len(doc.objects) == before, "an already-claimed line was duplicated"


def test_it_realizes_into_the_lines_stream_so_the_inspector_can_place_it():
    """`docinspect.object_geometry` takes a box from the mathpix_lines
    realizations, falling back to `props['region']`. Both are provided: the
    realization is what makes the record selectable in the ELEMENTS tree and
    keeps the claim ledger honest about who claimed it."""
    doc = _reading(GD3)
    for o in _run(doc):
        rz = [r for r in o.realizations if r.stream == "mathpix_lines"]
        assert rz, f"{o.props.get('lines_type')} has no lines realization"
        assert o.props.get("region"), "and no region fallback either"


def test_the_page_number_is_carried_so_the_box_lands_on_a_page():
    """A box with no page is filtered out of every page view — the model would
    hold a correct rectangle that nothing draws."""
    doc = _reading(GD3)
    assert all(o.props.get("page") == 1 for o in _run(doc))


def test_nothing_happens_without_a_reading():
    """A LaTeX-source model has no mathpix_lines stream at all."""
    doc = Document()
    _proc().process_document(doc)
    assert not doc.objects


def test_a_page_spanning_every_line_is_not_a_claim():
    """The bug the first version of this module had, pinned.

    `Page` realizes every line on its page (anchors 0..7 of 8 on the measured
    reading) and `Document` spans all of them, so counting a container's span
    as a claim marked the whole reading claimed and this module kept NOTHING —
    it loaded, ran, reported nothing and changed nothing. A container describes
    where content sits; it does not account for it.
    """
    from docmodel.core import DocObject, Realization
    doc = _reading(GD3)
    mp = doc.stream("mathpix_lines")
    page = DocObject(type="Page", props={"page_number": 1})
    page.add_realization(Realization(stream="mathpix_lines",
                                     start=mp.anchors[0], end=mp.anchors[-1],
                                     role="surface"))
    doc.add(page)
    kept = [o for o in _run(doc) if o.type == "ReadingRecord"]
    assert len(kept) == len(GD3), (
        f"a Page spanning the page hid {len(GD3) - len(kept)} record(s)")
