r"""A correction made in TiddlyWiki must reach the docmodel.

OWNER, 2026-11-12: "To change formulas and correct errors I would always prefer
Tiddlywiki. Therefore we need an importer that is able to update existing
docmodel data by Tiddlywiki."

WHAT WAS WRONG. `pdfdrill tiddlers --update` already reads an edited
tiddlers.json, matches BY TITLE, restores hand edits and refuses stale ones
with reasons — and writes the result to `<bibkey>.update.json`, where it stops.
The docmodel never learns, so `md`, `latex`, `inspect` and every other
projection keep showing the uncorrected value. And `KEEP_LIST` guards `text`,
`caption` and `trailing_punct` but NOT `latex`, so a formula corrected in the
wiki was overwritten by the projector's own value before any question of
reaching the model.

THE RULE: A FIELD IS IMPORTED ONLY WHERE THE CORRESPONDENCE CAN BE PROVED.
The importer re-projects the model, and a tiddler field may be written back to
a prop only when the FRESH projection reproduces that prop's current value
verbatim. Then the edit has exactly one place to land and we can say which.

MEASURED on BH2 (6,450 titles) — what that rule admits:

    Formula    tiddler[latex]   == props[latex]     4870
    Equation   tiddler[latex]   == props[latex]      342
    ListItem   tiddler[text]    == props[content]    120
    Sidenote   tiddler[text]    == props[content]     11
    Section    tiddler[caption] == props[caption]      8
    Footnote   tiddler[text]    == props[content]      6

and what it refuses: 651 of 656 Paragraph `text` fields, because the projector
REBUILDS a paragraph's text from the model's own realization in the reading
stream rather than reading `props['text']`. On BH2 that is visible as the
tiddler holding GERMAN while `props['text']` holds the English translation.
There is no prop for such an edit to land in, so it is refused and said, never
guessed at.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject            # noqa: E402
from docops import tiddler_import                        # noqa: E402


def _doc():
    d = Document()
    d.meta["bibkey"] = "demo"
    d.meta["num_pages"] = 1
    d.meta["pages"] = [{"page": 1, "page_width": 1000, "page_height": 1400}]
    d.add(DocObject(type="Formula", id="f1", props={
        "flow_index": 1, "page": 1, "display": True,
        "latex": r"\alpha + \beta",
        # the producer's verbatim record, which must never be written
        "latex_raw": r"\alpha + \beta",
        "latex_original": r"\alpha + \beta"}))
    d.add(DocObject(type="Section", id="s1", props={
        "flow_index": 2, "page": 1, "level": 1, "caption": "Einleitung"}))
    d.add(DocObject(type="ListItem", id="li1", props={
        "flow_index": 3, "page": 1, "content": "erster Punkt"}))
    return d


def _edited(doc, title_substr, field, value):
    """The tiddler file as a wiki hand-edit leaves it: the fresh projection
    with ONE field changed."""
    fresh = tiddler_import.fresh_tiddlers(doc, "demo")
    out = []
    for t in fresh:
        t = dict(t)
        if title_substr in t["title"] and field in t:
            t[field] = value
        out.append(t)
    return out


# ── the provable cases ─────────────────────────────────────────────────────

def test_a_formula_corrected_in_the_wiki_reaches_the_model():
    """The case the owner named."""
    doc = _doc()
    edits = _edited(doc, "_FO", "latex", r"\alpha - \beta")
    plan = tiddler_import.plan(doc, "demo", edits)
    assert len(plan["changes"]) == 1, plan
    c = plan["changes"][0]
    assert (c["obj_id"], c["field"], c["prop"]) == ("f1", "latex", "latex")
    assert c["new"] == r"\alpha - \beta"
    assert tiddler_import.apply(doc, plan["changes"]) == 1
    assert doc.objects["f1"].props["latex"] == r"\alpha - \beta"


def test_the_producers_verbatim_record_is_never_written():
    """`latex_raw` / `latex_original` / `latex_author` are what the reader
    produced. A correction is a new value for `latex`, not a rewriting of the
    evidence it was derived from."""
    doc = _doc()
    edits = _edited(doc, "_FO", "latex", r"\alpha - \beta")
    tiddler_import.apply(doc, tiddler_import.plan(doc, "demo", edits)["changes"])
    p = doc.objects["f1"].props
    assert p["latex_raw"] == r"\alpha + \beta"
    assert p["latex_original"] == r"\alpha + \beta"


def test_a_section_heading_reaches_its_caption():
    doc = _doc()
    edits = _edited(doc, "_H", "caption", "Einführung")
    plan = tiddler_import.plan(doc, "demo", edits)
    assert [(c["obj_id"], c["prop"]) for c in plan["changes"]] == [("s1", "caption")]


def test_a_list_items_text_reaches_its_content_prop():
    """The tiddler field is `text`; the prop is `content`. The correspondence
    is PROVED from the projection, not read off a hand-written table that
    could drift from it."""
    doc = _doc()
    edits = _edited(doc, "_LI", "text", "erster korrigierter Punkt")
    plan = tiddler_import.plan(doc, "demo", edits)
    assert [(c["obj_id"], c["field"], c["prop"]) for c in plan["changes"]] \
        == [("li1", "text", "content")]


# ── what it refuses, and whether it says why ───────────────────────────────

def test_an_unchanged_file_changes_nothing():
    doc = _doc()
    plan = tiddler_import.plan(doc, "demo", tiddler_import.fresh_tiddlers(doc, "demo"))
    assert plan["changes"] == []


def test_a_field_with_no_matching_prop_is_refused_with_a_reason():
    """A Formula tiddler's `text` is the `<$latex>` WIDGET, built by the
    template — it reproduces no prop, so an edit there has nowhere to land."""
    doc = _doc()
    edits = _edited(doc, "_FO", "text", "<$latex text={{!!latex}} />EDITED")
    plan = tiddler_import.plan(doc, "demo", edits)
    assert plan["changes"] == []
    assert plan["refused"], plan
    r = plan["refused"][0]
    assert r["field"] == "text"
    assert "reproduce" in r["reason"].lower() or "no prop" in r["reason"].lower(), r


def test_a_title_the_model_does_not_have_is_reported_not_created():
    """An importer that created objects could not be trusted with a file a
    person edited by hand."""
    doc = _doc()
    edits = tiddler_import.fresh_tiddlers(doc, "demo") + [
        {"title": "demo_FO9999", "latex": "x", "text": "x"}]
    before = len(doc.objects)
    plan = tiddler_import.plan(doc, "demo", edits)
    tiddler_import.apply(doc, plan["changes"])
    assert len(doc.objects) == before, "the importer created an object"
    assert "demo_FO9999" in plan["unmatched"], plan["unmatched"]


def test_nothing_is_written_by_planning():
    """`plan` is a read. The command's default is a dry run, and that is only
    true if planning cannot touch the document."""
    doc = _doc()
    before = {i: dict(o.props) for i, o in doc.objects.items()}
    tiddler_import.plan(doc, "demo", _edited(doc, "_FO", "latex", "CHANGED"))
    assert {i: dict(o.props) for i, o in doc.objects.items()} == before


def test_a_blank_value_is_refused():
    """Emptying a field in the wiki is far more likely a slip than an
    instruction to delete the document's mathematics."""
    doc = _doc()
    plan = tiddler_import.plan(doc, "demo", _edited(doc, "_FO", "latex", "   "))
    assert plan["changes"] == []
    assert any("empty" in r["reason"].lower() for r in plan["refused"]), plan


def test_a_source_twin_is_never_the_target():
    """On a translated model `props['text_source']` holds the original. An
    import must not write the pre-translation record either."""
    doc = _doc()
    doc.objects["li1"].props["content_source"] = "erster Punkt"
    edits = _edited(doc, "_LI", "text", "korrigiert")
    plan = tiddler_import.plan(doc, "demo", edits)
    for c in plan["changes"]:
        assert not c["prop"].endswith("_source"), c


def test_wiki_machinery_is_not_reported_as_missing_objects():
    r"""The projection carries 16 TEMPLATE tiddlers (`FO`, `CIT`, `PARA`, …)
    holding the widgets the object tiddlers transclude, plus the document's own
    root tiddler and a generated TOC. No object owns any of them, and none ever
    will. Listing them as "titles the model does not have" put 17 alarming rows
    in the report of a perfectly clean import on 1911.02782.

    The test is STRUCTURAL, not a tag match: the projection has the title and
    the title map gives it no object."""
    doc = _doc()
    edits = tiddler_import.fresh_tiddlers(doc, "demo")
    plan = tiddler_import.plan(doc, "demo", edits)
    assert plan["unmatched"] == [], plan["unmatched"]
    assert plan["furniture"] > 0, plan


def test_a_title_absent_from_the_projection_is_the_only_unmatched_kind():
    """A tiddler the wiki author created, or a title from an older build."""
    doc = _doc()
    edits = tiddler_import.fresh_tiddlers(doc, "demo") + [
        {"title": "demo_FO9999", "latex": "x"},
        {"title": "MyOwnNote", "text": "a note I wrote in the wiki"}]
    plan = tiddler_import.plan(doc, "demo", edits)
    assert sorted(plan["unmatched"]) == ["MyOwnNote", "demo_FO9999"]


# ── and the correction must survive the next command ───────────────────────

def test_every_changed_object_is_stamped_so_a_rebuild_refuses():
    r"""MEASURED on the first end-to-end round trip (1911.02782): the import
    wrote `{}^{1, 2}` into the model, and the next `pdfdrill latex --force` ran
    the lazy rebuild (`_stale_or_absent` -> `cmd_model`), regenerated every
    object id (obj_ca8c2d32ed23 -> obj_2ec8cf656c22) and put `^{1, 2}` back.

    An imported correction is not in lines.json and a rebuild cannot reproduce
    it, which is the definition of an enrichment. The stamp is what the rebuild
    guard sees."""
    from pdfdrill.commands import ENRICHMENT_MARKERS
    assert tiddler_import.EDIT_MARKER in ENRICHMENT_MARKERS, (
        "the marker is not in ENRICHMENT_MARKERS, so a rebuild will discard "
        "every imported correction without a word")
    doc = _doc()
    edits = _edited(doc, "_FO", "latex", r"\alpha - \beta")
    tiddler_import.apply(doc, tiddler_import.plan(doc, "demo", edits)["changes"])
    assert doc.objects["f1"].props[tiddler_import.EDIT_MARKER] == "latex"


def test_the_stamp_accumulates_the_fields_it_covers():
    doc = _doc()
    doc.objects["li1"].props[tiddler_import.EDIT_MARKER] = "caption"
    edits = _edited(doc, "_LI", "text", "korrigiert")
    tiddler_import.apply(doc, tiddler_import.plan(doc, "demo", edits)["changes"])
    assert doc.objects["li1"].props[tiddler_import.EDIT_MARKER] == "caption,content"


def test_an_unchanged_object_is_not_stamped():
    """The marker blocks rebuilds, so stamping an object nothing changed would
    freeze a document for no reason."""
    doc = _doc()
    tiddler_import.apply(doc, [])
    assert tiddler_import.EDIT_MARKER not in doc.objects["s1"].props
