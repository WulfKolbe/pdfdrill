"""A report says only what happened (T-0153, idea 2).

Four reports were false on the board extract 1805.01788-p0003 after one
`pdfdrill drill` (pdfdrill 250aaccb, fresh shell, installed entry point):

1. `steps inspect` listed `glyphlines` as "already done" though `drill` never
   ran it: `model` leaves a `pdfminer-chars` lines.json beside the PDF and the
   detector asked only for a file of that name. After a real `glyphlines` it
   listed `mathpix` and `gemmaocr` as satisfied; neither ran.
2. `artifacts` listed `<bibkey>.md` and `<bibkey>.inspect.html` as present and,
   in the same output, `md` and `inspect` as "Not generated yet": the detector
   expanded `{bibkey}` to the drill FOLDER's name and looked beside the PDF.
3. `plan --goal md` said "already satisfied" although the reading had been
   replaced after the Markdown was written.
4. `glyphlines` exits 0 when its reader raised.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import planner


class _SC:
    def __init__(self, blob, facts=()):
        self.blob_dir = blob
        self._f = set(facts)

    def has(self, f):
        return f in self._f


def _doc(tmp_path, source):
    """A document in the `<name>.pdf.drill/` layout with one reading."""
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    blob = tmp_path / "x.pdf.drill"
    blob.mkdir()
    lines = tmp_path / "x.lines.json"
    lines.write_text(json.dumps({"source": source, "pages": []}))
    return pdf, blob, lines


def _done(cmd):
    return planner.load_graph(planner.load_manifest())[1][cmd]


# ---- 1 ------------------------------------------------------------------- #
def test_a_reading_from_another_reader_is_not_glyphlines_done(tmp_path):
    pdf, blob, _ = _doc(tmp_path, "pdfminer-chars")
    assert not planner.detect(_done("glyphlines"), _SC(blob), pdf,
                              blob / "model.docmodel.json")


def test_the_glyph_readers_own_reading_is_glyphlines_done(tmp_path):
    pdf, blob, _ = _doc(tmp_path, "pdfminer-docmodel")
    assert planner.detect(_done("glyphlines"), _SC(blob), pdf,
                          blob / "model.docmodel.json")


def test_steps_does_not_say_done_for_a_command_that_did_not_run(tmp_path):
    """`mathpix` and `gemmaocr` wait on a typed reading. When the glyph reader
    wrote it, the report names the glyph reader, and says of the other two
    that they were not run."""
    pdf, blob, _ = _doc(tmp_path, "pdfminer-docmodel")
    out = planner._met({"size", "glyphlines", "mathpix", "gemmaocr"}, pdf,
                       planner.load_manifest())
    assert "mathpix (not run: the reading on disk is `glyphlines`'s)" in out
    assert "gemmaocr (not run: the reading on disk is `glyphlines`'s)" in out
    assert "glyphlines (not run" not in out
    assert "already done" not in planner.describe("inspect", pdf)


# ---- 2 ------------------------------------------------------------------- #
def test_a_projection_in_the_drill_folder_is_found(tmp_path):
    pdf, blob, _ = _doc(tmp_path, "pdfminer-docmodel")
    (blob / "x.md").write_text("# x\n")
    assert planner.detect("file:{bibkey}.md", _SC(blob), pdf,
                          blob / "model.docmodel.json")


def test_an_empty_projection_is_still_not_generated(tmp_path):
    pdf, blob, _ = _doc(tmp_path, "pdfminer-docmodel")
    (blob / "x.md").write_text("")
    assert not planner.detect("file:{bibkey}.md", _SC(blob), pdf,
                              blob / "model.docmodel.json")


# ---- 3 ------------------------------------------------------------------- #
def test_markdown_older_than_the_reading_is_not_satisfied(tmp_path):
    from pdfdrill.commands import stale_projection_facts
    pdf, blob, lines = _doc(tmp_path, "pdfminer-docmodel")
    md = blob / "x.md"
    md.write_text("# x\n")
    old = time.time() - 100
    os.utime(md, (old, old))
    assert "MD_BUILT" in stale_projection_facts(pdf, blob, {"md": {"blob": "x.md"}})
    os.utime(md, None)
    os.utime(lines, (old, old))
    assert "MD_BUILT" not in stale_projection_facts(pdf, blob, {"md": {"blob": "x.md"}})


# ---- 4 ------------------------------------------------------------------- #
def test_glyphlines_exits_non_zero_when_the_reader_fails(tmp_path, monkeypatch):
    from pdfdrill import commands
    from pdfreader import docmodel_six

    def boom(_path):
        raise RuntimeError("stock pdfminer: no glyph origins")

    monkeypatch.setattr(docmodel_six, "build", boom)
    pdf = tmp_path / "y.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    out = commands.cmd_glyphlines(pdf)
    assert "could not read" in out
    assert getattr(out, "exit_code", 0) != 0
