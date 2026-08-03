"""`inspect` must demand a model that HAS geometry, not merely a model file.

Every `done_when` spec so far is a presence test — the artifact exists. Presence
is not adequacy: a model built by a lane that produces no object regions is a
perfectly good file that `inspect` can draw nothing from, and the state machine
called that state satisfied. It is the same mistake as gating a route on the
existence of the file that route produces.

So: a `model:geometry` detector that asks whether objects actually carry
rectangles, and `geometry` as a real prerequisite of `inspect` — a command whose
job is to attach the geometry it is named for, upgrading a region-less model in
place instead of leaving the view empty.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmodel.core import Document, DocObject
from pdfdrill import planner
from pdfdrill.commands import upgrade_object_regions, merge_page_geometry


class _SC:
    def has(self, _f):
        return False


def _write_model(tmp_path, with_region: bool) -> Path:
    doc = Document()
    props = {"text": "We propose a method that learns a metric"}
    if with_region:
        props["region"] = {"top_left_x": 1, "top_left_y": 2,
                           "width": 3, "height": 4}
    doc.add(DocObject(type="Paragraph", props=props))
    p = tmp_path / "model.docmodel.json"
    p.write_text(json.dumps(doc.to_dict()))
    return p


def test_model_geometry_detector_distinguishes_presence_from_adequacy(tmp_path):
    pdf = tmp_path / "d.pdf"
    bare = _write_model(tmp_path / "a", True) if False else None
    (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
    no_geo = _write_model(tmp_path / "a", with_region=False)
    with_geo = _write_model(tmp_path / "b", with_region=True)

    assert planner.detect("model", _SC(), pdf, no_geo) is True    # file exists
    assert planner.detect("model:geometry", _SC(), pdf, no_geo) is False
    assert planner.detect("model:geometry", _SC(), pdf, with_geo) is True
    assert planner.detect("model:geometry", _SC(), pdf,
                          tmp_path / "missing.json") is False


def test_inspect_declares_geometry_as_a_prerequisite():
    man = planner.load_manifest()
    requires, done = planner.load_graph(man)
    assert "geometry" in requires.get("inspect", []), \
        "inspect draws boxes; it must demand the geometry that makes them"
    assert done.get("geometry") == "model:geometry", \
        "geometry is done when the model actually carries regions"


def test_plan_inserts_geometry_when_the_model_has_none():
    requires, _ = planner.load_graph(planner.load_manifest())
    steps = planner.plan("inspect", requires, satisfied={"model"})
    assert steps[-1] == "inspect"
    assert "geometry" in steps[:-1], steps


def _lines(tmp_path):
    data = {"pages": [{"page": 1, "page_width": 612, "page_height": 792, "lines": [
        {"text": "We propose a method that learns a metric", "type": "text",
         "region": {"top_left_x": 72, "top_left_y": 120,
                    "width": 420, "height": 12}}]}]}
    p = tmp_path / "d.lines.json"
    p.write_text(json.dumps(data))
    return p


def test_upgrade_attaches_regions_to_a_regionless_model(tmp_path):
    doc = Document()
    doc.add(DocObject(type="Paragraph", props={
        "text": "We propose a method that learns a metric"}))
    n = upgrade_object_regions(doc, _lines(tmp_path))
    para = next(o for o in doc.objects.values() if o.type == "Paragraph")
    assert n == 1 and para.props["region"]["top_left_x"] == 72


def test_upgrade_is_idempotent_and_adds_no_duplicate_pages(tmp_path):
    """Re-running must not accumulate Page objects — the merge adds one per page."""
    doc = Document()
    doc.add(DocObject(type="Paragraph", props={
        "text": "We propose a method that learns a metric"}))
    lines = _lines(tmp_path)
    merge_page_geometry(doc, lines)
    pages_after_first = sum(1 for o in doc.objects.values() if o.type == "Page")
    upgrade_object_regions(doc, lines)
    upgrade_object_regions(doc, lines)
    assert sum(1 for o in doc.objects.values() if o.type == "Page") == pages_after_first


def test_upgrade_fills_a_region_on_an_object_that_already_has_a_page(tmp_path):
    """THE upgrade case: an earlier merge set `page` but stored no rectangle.

    merge_page_geometry skips anything already carrying a `page`, which is right
    when the job is placing objects and wrong when the job is adding the boxes —
    every already-placed object was skipped and the upgrade added nothing.
    """
    doc = Document()
    doc.add(DocObject(type="Paragraph", props={
        "text": "We propose a method that learns a metric", "page": 1}))
    n = upgrade_object_regions(doc, _lines(tmp_path))
    para = next(o for o in doc.objects.values() if o.type == "Paragraph")
    assert n == 1, "an object with a page but no region must still get one"
    assert para.props["region"]["top_left_x"] == 72


def test_ensure_is_silent_about_its_prerequisites(capsys):
    """One request, one answer. Each prerequisite printing its own report turns
    `inspect` into four paragraphs of machinery before the line that matters."""
    calls = []

    def handler(argv):
        calls.append(argv)
        return "Built unified model: 270 objects … Next: pdfdrill compare"

    ran = planner.ensure("inspect", Path("nope.pdf"),
                         {"model": handler, "geometry": handler}, "nope.pdf")
    assert capsys.readouterr().out == "", "prerequisites must not narrate"
    assert ran == [] or calls, "steps still run, they just stay quiet"
