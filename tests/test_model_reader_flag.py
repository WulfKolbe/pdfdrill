r"""
836 — phase 4 of the pdf2mmd integration: TWO READERS, ONE COMMAND.

The reason the glyph reader was absorbed (834) rather than left beside us is
that a reader reached by a different program is measured by a different
command, and two measurements taken by two commands are not comparable. The
user's own words: "we will only work on pdfdrill to test new feature on our
pdfreader and Mathpix with the same commands."

So `model --reader glyphs|mathpix` names the reading, and the two rules that
make the naming mean something:

  * A PAID READER IS NAMED, NEVER RUN. `--reader mathpix` with no conversion
    on disk refuses and prints the command that would buy one. This is
    `planner.network_commands`' rule, stated at a second place because this
    one can reach `cmd_mathpix` directly.
  * NAMING A READER SUPPRESSES THE SOURCE LANE. On an arXiv paper the
    author's LaTeX is the richest input and `prefers_merged_route` takes it —
    so `--reader glyphs` without `no_source` would build from the e-print and
    report it under the glyph reader's name. The comparison would be
    source-against-source and would look fine.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest                                                  # noqa: E402

from pdfdrill import commands as C                             # noqa: E402

PDF = b"%PDF-1.7 not-a-real-pdf\n%%EOF\n"


@pytest.fixture
def doc(tmp_path):
    d = tmp_path / "paper"
    d.mkdir()
    p = d / "paper.pdf"
    p.write_bytes(PDF)
    return p


def test_an_unknown_reader_is_refused_by_name(doc):
    out = C.cmd_model(doc, reader="tesseract")
    assert "takes `glyphs` or `mathpix`" in out
    assert "tesseract" in out


def test_mathpix_without_a_conversion_is_refused_not_bought(doc):
    """The refusal names the exact command that would satisfy it — the
    `--ensure` contract for a paid layer, which never runs unasked."""
    out = C.cmd_model(doc, reader="mathpix")
    assert "never run for you" in out
    assert "pdfdrill mathpix paper" in out


def test_naming_a_reader_suppresses_the_author_source_lane(monkeypatch, doc):
    """THE RULE A SILENT WRONG MEASUREMENT WOULD HAVE BROKEN. `--reader` must
    reach the build with `no_source` true, or an arXiv paper is read from its
    e-print and reported under the reader's name — and it would look fine.

    Observed where it bites: `cmd_model` consults `prefers_merged_route` only
    when `no_source` is false, so a reader that is named must never reach it.
    """
    monkeypatch.setattr(C, "cmd_glyphlines", lambda p, force=False: "ok")

    def _never(*a, **kw):                                      # pragma: no cover
        raise AssertionError(
            "the author-source lane was consulted for a NAMED reader: the "
            "model would be built from the e-print and reported as the "
            "reader's own reading")

    monkeypatch.setattr(C, "prefers_merged_route", _never)
    # The build itself needs a real PDF; stop at the first thing after the
    # gate and assert only on what the gate decided.
    monkeypatch.setattr(C, "model_rebuild_blocked",
                        lambda *a, **kw: "STOPPED-BY-TEST")
    out = C.cmd_model(doc, reader="glyphs", force=True)
    assert out == "STOPPED-BY-TEST", out


def test_naming_a_reader_implies_a_re_read(monkeypatch, doc):
    """Without `force`, a lines.json already on disk is kept — so `--reader
    glyphs` would build from whatever was there and call it the glyph
    reader's reading.

    Observed through the one branch `force` alone controls this early:
    `if blocked and force: return blocked`.
    """
    monkeypatch.setattr(C, "cmd_glyphlines", lambda p, force=False: "ok")
    monkeypatch.setattr(C, "prefers_merged_route", lambda *a, **kw: False)
    monkeypatch.setattr(C, "model_rebuild_blocked", lambda *a, **kw: "BLOCKED")

    # `force` defaults to False and NOTHING else sets it on this path, so
    # reaching this return at all is the observation.
    assert C.cmd_model(doc, reader="glyphs") == "BLOCKED"
    # NO CONTROL LEG HERE, deliberately. `cmd_model(doc)` with no lines.json
    # auto-chains `cmd_mathpix`, and writing that control UPLOADED THIS FAKE
    # PDF TO THE PAID API from a unit test (measured, 2026-09-30). A test must
    # not be able to spend money; the positive above is sufficient.


def test_a_reader_that_cannot_read_stops_before_the_build(monkeypatch, doc):
    """A glyph read that found no text layer must not fall through into a
    build that would then quietly use whatever lines.json was already there."""
    monkeypatch.setattr(
        C, "cmd_glyphlines",
        lambda p, force=False: "glyphlines: paper.pdf yielded 0 line(s) — "
                               "no text layer to read.")

    def _stop(*a, **kw):                                       # pragma: no cover
        raise AssertionError("the build must not be reached")

    monkeypatch.setattr(C, "Sidecar", _stop)
    out = C.cmd_model(doc, reader="glyphs")
    assert "no text layer" in out


def test_the_flag_is_in_the_manifest():
    """A capability not in `commands.yaml` is invisible to `steps`,
    `--ensure` and the SKILL — audit A4."""
    import yaml
    y = yaml.safe_load(
        (Path(__file__).resolve().parents[1]
         / ".claude/skills/pdfdrill/commands.yaml").read_text(encoding="utf-8"))
    entry = [c for c in y["commands"] if c["name"] == "model"][0]
    flags = {f["flag"] for f in entry.get("flags", [])}
    assert "--reader" in flags, flags
