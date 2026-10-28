"""ENGINEERING 2d rule 5, the half that was missing: the CONSUMER must refuse too.

Closing the `""` entry in `_TYPED_GEOMETRY_SOURCES` put the refusal in the
planner's prerequisite gate — `pdfdrill steps inspect` names the paid step, as
it should. The coordinator's audit of 6c8e3891 found that the consuming command
walked straight past it: on a reading whose producer cannot be named,
`pdfdrill model` exited 0 and built the whole model from it, and `pdfdrill
inspect` then rendered it.

Reproduced here before the fix, on the library's `1707.00189` reading with its
page frame turned to floats: `_lines_source` '' and typed-geometry False, yet
`model` exit 0, 317 objects — and its own report said "1 equations carry a
MathPix CDN image", a CDN crop claimed from a reading whose regions are in PDF
points. That is the wrong-frame hazard the gate exists to prevent, arriving
through the gate's own blind side.

So the rule is one rule in two places: the planner says the prerequisite is
unsatisfied, and `model` refuses to build. The refusal names the file, says
which piece of evidence is missing, and names the readers that would supply it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pdfdrill import commands as C


def _reading(source: "str | None", *, image_id="8a29fc03-28d7-4c95-8397-e96f4ec2224d-1",
             width=2125, height=2750, kinds=("page_info", "math")) -> dict:
    pg = {"image_id": image_id, "page": 1, "page_width": width,
          "page_height": height,
          "lines": [{"id": "l%d" % i, "type": k, "text": "x^2",
                     "region": {"top_left_x": 10, "top_left_y": 20,
                                "width": 300, "height": 18}}
                    for i, k in enumerate(kinds)]}
    doc: dict = {"pages": [pg]}
    if source is not None:
        doc = {"source": source, "pages": [pg]}
    return doc


def _doc(tmp_path, reading: "dict | None", stem="1707.00189") -> Path:
    d = tmp_path / stem
    d.mkdir()
    pdf = d / f"{stem}.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    if reading is not None:
        (d / f"{stem}.lines.json").write_text(json.dumps(reading),
                                              encoding="utf-8")
    return pdf


# --- the refusal itself ----------------------------------------------------

def test_a_point_frame_reading_is_refused_and_the_reason_is_the_frame(tmp_path):
    """The plant the coordinator's audit used: no `source`, ids that are
    neither a UUID nor the document's stem, and a FLOAT page size."""
    pdf = _doc(tmp_path, _reading(None, image_id="scan-0001",
                                  width=612.0, height=792.0))
    lp = C._lines_json_path(pdf)
    assert C._lines_source(lp) == "", "precondition: nothing identifies it"
    msg = C._refuse_unidentified_lines(pdf, lp)
    assert msg is not None
    assert "1707.00189.lines.json" in msg, "the refusal must name the file"
    assert "points" in msg, "and say which evidence is missing"


def test_an_untyped_reading_is_refused_for_its_line_types(tmp_path):
    pdf = _doc(tmp_path, _reading(None, image_id="scan-0001", kinds=("text",)))
    msg = C._refuse_unidentified_lines(pdf, C._lines_json_path(pdf))
    assert msg is not None
    assert "typed" in msg


def test_an_empty_reading_is_refused_without_raising(tmp_path):
    pdf = _doc(tmp_path, None)
    C._lines_json_path(pdf).write_text("", encoding="utf-8")
    msg = C._refuse_unidentified_lines(pdf, C._lines_json_path(pdf))
    assert msg is not None
    assert "0 bytes" in msg or "nothing" in msg


# --- and what must NOT be refused -----------------------------------------

def test_a_mathpix_reading_is_not_refused(tmp_path):
    pdf = _doc(tmp_path, _reading(None))          # UUID ids, integer frame
    assert C._lines_source(C._lines_json_path(pdf)) == "mathpix"
    assert C._refuse_unidentified_lines(pdf, C._lines_json_path(pdf)) is None


def test_a_declared_keyless_reader_is_not_refused(tmp_path):
    """`pdfminer-chars` fails the GEOMETRY gate (its regions are points) and
    must still be a legal input to `model` — it is the merged route, and the
    author's LaTeX supplies the mathematics. The refusal is about readings that
    name nobody, not about readings whose geometry this one gate declines."""
    pdf = _doc(tmp_path, _reading("pdfminer-chars", width=612.0, height=792.0))
    lp = C._lines_json_path(pdf)
    assert C._is_typed_geometry_lines(lp) is False
    assert C._refuse_unidentified_lines(pdf, lp) is None


def test_no_reading_at_all_is_not_refused(tmp_path):
    """`model` builds from the PDF itself or the author's LaTeX when there is no
    lines.json. This gate must not stand in that lane's way."""
    pdf = _doc(tmp_path, None)
    assert not C._lines_json_path(pdf).exists()
    assert C._refuse_unidentified_lines(pdf, C._lines_json_path(pdf)) is None


# --- through the command, and through the command line --------------------

def test_cmd_model_refuses_with_a_non_zero_status(tmp_path):
    from pdfdrill.cli import EXIT_LANE_NOT_RUN
    pdf = _doc(tmp_path, _reading(None, image_id="scan-0001",
                                 width=612.0, height=792.0))
    out = C.cmd_model(pdf)
    assert getattr(out, "exit_code", 0) == EXIT_LANE_NOT_RUN, out
    assert "1707.00189.lines.json" in out
    assert not (pdf.parent / "model.docmodel.json").exists(), \
        "a refusal that still wrote a model is not a refusal"


def _console_script() -> "Path | None":
    """The `pdfdrill` that belongs to the interpreter running this suite.

    Deliberately NOT `shutil.which("pdfdrill")`. Run from a worktree, that
    resolves to the script installed from the MAIN checkout
    (`~/.local/bin/pdfdrill`, whose shebang is the system python), so the test
    measures another branch's code while every path in its output names this
    one. The first version of this test did exactly that: it reported the
    defect as still present after the fix, because the fix was not in the tree
    it ran. A script next to `sys.executable` is this interpreter's own.
    """
    # NOT `.resolve()`: a venv's `bin/python3` is a symlink to the system
    # interpreter, so resolving it lands in `/usr/bin`, where there is no
    # `pdfdrill`, and the test SKIPS although the script is right there. A skip
    # is a NOT RUN, which is not a pass.
    for cand in (Path(sys.prefix) / "bin" / "pdfdrill",
                 Path(sys.executable).parent / "pdfdrill"):
        if cand.exists():
            return cand
    return None


def test_the_refusal_reaches_the_command_line(tmp_path):
    """Through the installed console script, which is what a person types. The
    audit that found this defect ran `pdfdrill model X.pdf --no-source` and got
    exit 0 and a full model."""
    script = _console_script()
    if script is None:
        pytest.skip("NOT RUN: no `pdfdrill` console script beside %s"
                    % sys.executable)
    exe = str(script)
    shebang = script.read_text(encoding="utf-8",
                               errors="replace").splitlines()[0]
    assert str(sys.prefix) in shebang or sys.executable in shebang, (
        "the script must run THIS interpreter, or the test measures another "
        "tree: %s" % shebang)
    pdf = _doc(tmp_path, _reading(None, image_id="scan-0001",
                                 width=612.0, height=792.0))
    env = {"HOME": os.environ.get("HOME", ""), "PATH": os.environ["PATH"],
           "PDFDRILL_SANDBOX": "1", "PDFDRILL_NO_PREFLIGHT": "1",
           "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([exe, "model", pdf.name, "--no-source"],
                       cwd=str(pdf.parent), env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode != 0, r.stdout[-2000:]
    assert "1707.00189.lines.json" in r.stdout + r.stderr
    assert not (pdf.parent / "model.docmodel.json").exists()
