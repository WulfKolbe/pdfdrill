r"""`doc.objects.pop(id)` removes the object and leaves every pointer to it.

Eleven sites call it (`grep -rn 'objects\.pop(' src/`): the footnote
extraction dropping a Paragraph it emptied, `clean_heading_residuals`, the
bibliography and image passes, the citation stub, and five in commands.py.
Each one removes the entry from `doc.objects` and nothing else, so the
Section that listed the object keeps listing it and the flow chain keeps
pointing at it.

MEASURED ON THE TEN-DOCUMENT GEMMA4 SET (2957de8, yolo, models built at
1175259b), before changing anything -- and the two counts are equal on every
document, which is what says they have one cause:

    document            objects   dangling children   dangling prev/next_in_flow
    lib:d68e0271bd4d     14408          155                   155 / 155
    1805.01788             341            6                     6 /   6
    lib:008d43e5db48      3680            3                     3 /   3
    2312.11532             531            3                     3 /   3
    0864                   412            2                     2 /   2
    lib:c9daf79960c3      7890            1                     1 /   1
    BH3, US6100897A, lib:5a5c76391c9c, lib:9027b2a8b957: none

170 in all, every one of them listed by a Section. `parent` and
`props["parent_section"]` are clean at zero, because the structure pass
(procOrder 999) only fills live objects and the pops run after it -- which
also says WHEN the damage happens, not just that it does.

WHAT IT COSTS. A tree walker that descends by `children` hits an id that is
not in `doc.objects`: `test_a_listed_child_knows_its_parent` already skips
those ("dangling ids are a separate defect" -- this is that defect), the
TiddlyWiki projector's `_section_body` has to tolerate them, and a reader
that trusts the flow chain walks off the end of the document. None of it
raises; it all just silently drops content or stops early, which is the
failure class this repository keeps paying for.

THE RULE: removing an object removes every reference to it. The parent stops
listing it, its own children are reparented to its parent rather than
orphaned, and the flow chain closes over the gap so prev and next point at
each other instead of at a hole.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject  # noqa: E402


def _doc():
    """A Section with three children in a flow chain, the middle one doomed."""
    d = Document()
    d.meta["bibkey"] = "K"
    sec = d.add(DocObject(type="Section", props={"caption": "R", "level": 1,
                                                 "flow_index": 1}))
    a = d.add(DocObject(type="Paragraph", props={"text": "first",
                                                 "flow_index": 2}))
    b = d.add(DocObject(type="Paragraph", props={"text": "doomed",
                                                 "flow_index": 3}))
    c = d.add(DocObject(type="Paragraph", props={"text": "last",
                                                 "flow_index": 4}))
    for o in (a, b, c):
        sec.children.append(o.id)
        o.parent = sec.id
        o.props["parent_section"] = sec.id
    a.props["next_in_flow"] = b.id
    b.props["prev_in_flow"] = a.id
    b.props["next_in_flow"] = c.id
    c.props["prev_in_flow"] = b.id
    # and the doomed one has a child of its own
    kid = d.add(DocObject(type="Formula", props={"latex": "x", "flow_index": 5}))
    b.children.append(kid.id)
    kid.parent = b.id
    return d, sec, a, b, c, kid


def _dangling(doc):
    ids = set(doc.objects)
    out = {"children": [], "parent": [], "parent_section": [], "flow": []}
    for o in doc.objects.values():
        for ch in (o.children or []):
            if ch not in ids:
                out["children"].append((o.id, ch))
        if o.parent is not None and o.parent not in ids:
            out["parent"].append((o.id, o.parent))
        ps = o.props.get("parent_section")
        if ps and ps not in ids:
            out["parent_section"].append((o.id, ps))
        for k in ("prev_in_flow", "next_in_flow"):
            v = o.props.get(k)
            if v and v not in ids:
                out["flow"].append((o.id, k, v))
    return out


def test_the_bare_pop_is_what_leaves_the_references():
    """The defect itself, so the fix below is measured against it rather than
    against an assumption."""
    d, sec, _a, b, _c, _kid = _doc()
    d.objects.pop(b.id, None)
    bad = _dangling(d)
    assert bad["children"], "expected the Section to keep listing it"
    assert bad["flow"], "expected the flow chain to keep pointing at it"
    assert bad["parent"], "expected its own child to keep pointing at it"


def test_removing_an_object_leaves_no_reference_behind():
    d, sec, _a, b, _c, _kid = _doc()
    d.remove(b.id)
    assert b.id not in d.objects
    bad = _dangling(d)
    assert bad == {"children": [], "parent": [], "parent_section": [],
                   "flow": []}, repr(bad)


def test_the_parent_stops_listing_it():
    d, sec, a, b, c, _kid = _doc()
    d.remove(b.id)
    assert b.id not in sec.children
    assert a.id in sec.children and c.id in sec.children


def test_the_flow_chain_closes_over_the_gap():
    """A reader walking the chain must reach `c` from `a`, not a hole."""
    d, _sec, a, b, c, _kid = _doc()
    d.remove(b.id)
    assert a.props["next_in_flow"] == c.id
    assert c.props["prev_in_flow"] == a.id


def test_its_own_children_are_reparented_not_orphaned():
    """The Formula inside the removed Paragraph belongs to the Section now.
    Dropping it to `parent=None` would hide it from every tree walk, and
    deleting it would lose content the removal never meant to touch."""
    d, sec, _a, b, _c, kid = _doc()
    d.remove(b.id)
    assert kid.id in d.objects, "the child itself is not removed"
    assert kid.parent == sec.id
    assert kid.id in sec.children


def test_removing_an_absent_id_is_not_an_error():
    """Every call site today is `pop(oid, None)`, so the replacement must be
    just as forgiving or the passes start raising on a double removal."""
    d, _sec, _a, b, _c, _kid = _doc()
    d.remove(b.id)
    d.remove(b.id)
    d.remove("obj_never_existed")


def test_a_root_level_object_removes_cleanly():
    """No parent, no flow neighbours, children reparented to nothing."""
    d = Document()
    o = d.add(DocObject(type="Paragraph", props={"text": "alone"}))
    kid = d.add(DocObject(type="Formula", props={"latex": "x"}))
    o.children.append(kid.id)
    kid.parent = o.id
    d.remove(o.id)
    assert kid.id in d.objects and kid.parent is None
    assert _dangling(d) == {"children": [], "parent": [],
                            "parent_section": [], "flow": []}
