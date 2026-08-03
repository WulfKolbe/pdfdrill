"""Every prerequisite needs a detector, and it must test the RIGHT store.

Two rules, learned one failure at a time:

1. A prerequisite with NO `done_when` is never in the satisfied set, so the
   planner inserts it on every single `--ensure`. `route` requires `size` and
   `publish` requires `tiddlers`; both re-ran unconditionally, and `tiddlers`
   regenerates the whole array.

2. The detector must read the store the work actually LANDS in:
     sidecar evidence  -> a fact is right (`size` writes only to the sidecar)
     model content     -> read the model; a rebuild discards it while the fact
                          survives (this is what left 60 citations pointing at
                          stubs)
     an artifact file  -> the file, AND not older than the model it came from,
                          or a rebuild leaves a stale array looking current
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmodel.core import Document, DocObject
from pdfdrill import planner


class _SC:
    def __init__(self, facts=(), blob=None):
        self._f = set(facts)
        self.blob_dir = blob

    def has(self, f):
        return f in self._f


def test_every_prerequisite_declares_a_detector():
    man = planner.load_manifest()
    requires, done = planner.load_graph(man)
    prereqs = {d for deps in requires.values() for d in deps}
    missing = sorted(p for p in prereqs if p not in done)
    assert not missing, f"prerequisite(s) with no done_when, so always re-run: {missing}"


def test_no_model_content_detector_is_a_bare_fact():
    """bibsource/bibliography build References INTO the model."""
    _, done = planner.load_graph(planner.load_manifest())
    for cmd in ("bibliography", "bibsource"):
        assert done.get(cmd) == "model:citations_resolved", (cmd, done.get(cmd))


def test_size_may_stay_a_fact():
    """`size` writes only sidecar evidence, which a model rebuild cannot discard,
    so a fact is the correct store to ask."""
    _, done = planner.load_graph(planner.load_manifest())
    assert done.get("size") == "fact:SIZE_KNOWN"


def _model(tmp_path) -> Path:
    doc = Document()
    doc.add(DocObject(type="Paragraph", props={"text": "x"}))
    p = tmp_path / "model.docmodel.json"
    p.write_text(json.dumps(doc.to_dict()))
    return p


def test_tiddlers_artifact_detector(tmp_path):
    model = _model(tmp_path)
    blob = tmp_path / "blob"
    blob.mkdir()
    sc = _SC(blob=blob)
    pdf = tmp_path / "d.pdf"

    assert planner.detect("artifact:tiddlers", sc, pdf, model) is False

    art = blob / "k.tiddlers.json"
    art.write_text("[]")
    assert planner.detect("artifact:tiddlers", sc, pdf, model) is True

    # a model rebuilt AFTER the array leaves it stale, not done
    time.sleep(0.01)
    model.write_text(model.read_text())
    assert planner.detect("artifact:tiddlers", sc, pdf, model) is False


def test_one_fresh_artifact_does_not_mask_a_stale_sibling(tmp_path):
    """A document has SEVERAL tiddler arrays — the main one and `*.spoken.*`.

    `_tiddlers_current` took the MAX mtime across them, so regenerating one made
    the whole set look current while a sibling stayed stale. Observed on
    2209.00445v3: the main array was rebuilt with the corrected citation titles
    while `2209.00445v3.spoken.tiddlers.json` sat four days old with the old
    ones — and importing both into one wiki mixes the two naming schemes.

    Checking "an artifact is fresh" instead of "every artifact is fresh" is the
    same presence-vs-adequacy mistake one level down.
    """
    model = _model(tmp_path)
    blob = tmp_path / "blob2"
    blob.mkdir()
    sc = _SC(blob=blob)
    pdf = tmp_path / "d.pdf"

    stale = blob / "k.spoken.tiddlers.json"
    stale.write_text("[]")
    os.utime(stale, (1, 1))                       # far older than the model
    fresh = blob / "k.tiddlers.json"
    fresh.write_text("[]")

    assert planner.detect("artifact:tiddlers", sc, pdf, model) is False, \
        "a stale sibling must keep the set from counting as done"

    os.utime(stale, None)                         # bring it up to date
    assert planner.detect("artifact:tiddlers", sc, pdf, model) is True


def test_stale_sibling_arrays_are_named(tmp_path):
    """A stale array must be REPORTED, not merely counted as not-done.

    223 documents carry a `*.spoken.tiddlers.json` that no command in the repo
    produces — an unmaintained leftover. It holds the old citation titles, and
    importing it beside the current array puts two naming schemes in one wiki:
    the titles come from one file, the markers from the other, and the links
    break in a way that looks like the current export is wrong.
    """
    from pdfdrill.commands import stale_tiddler_siblings

    blob = tmp_path / "b"
    blob.mkdir()
    model = _model(tmp_path)
    cur = blob / "k.tiddlers.json"
    cur.write_text("[]")
    old = blob / "k.spoken.tiddlers.json"
    old.write_text("[]")
    os.utime(old, (1, 1))

    stale = stale_tiddler_siblings(blob, model, cur)
    assert [p.name for p in stale] == ["k.spoken.tiddlers.json"]
    # the file just written is never reported against itself
    assert cur not in stale
