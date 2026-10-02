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
import json
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


# ---------------------------------------------------------------- 845

def test_a_forced_glyph_read_backs_up_a_mathpix_reading(tmp_path, monkeypatch):
    """845 — THE ONE ARTEFACT THAT CANNOT BE REBUILT FOR FREE.

    `glyphlines` refuses to replace a MathPix lines.json — and `--force` walks
    past the refusal, which `model --reader glyphs` does on every call because
    naming a reader IS the instruction to re-read (837). So a paid layer was one
    flag away from being overwritten by a free reading, silently. inkdrill hit it
    regenerating 20 documents: sigma26-075 was the only one with a MathPix
    reading and it went.

    `cmd_ocr` already solved this — "the named command executes, the paid layer
    stays recoverable as <name>.mathpix.bak.json" — so this uses that name
    rather than inventing a second one.
    """
    d = tmp_path / "paper"
    d.mkdir()
    pdf = d / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")
    lines = d / "paper.lines.json"
    # MathPix output is identified by the ABSENCE of a `source` key (the
    # keyless routes stamp one) plus MathPix-only line types.
    mathpix = {"pages": [{"page": 1, "lines": [
        {"type": "math", "text": r"\\[ x^2 \\]"},
        {"type": "equation_number", "text": "(1)"}]}]}
    lines.write_text(json.dumps(mathpix), encoding="utf-8")

    assert C._is_mathpix_lines(lines), "fixture must look like MathPix output"

    # the glyph read itself is irrelevant here; only the backup is under test
    monkeypatch.setattr(
        "pdfreader.docmodel_six.build", lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError("stop after the backup")))

    out = C.cmd_glyphlines(pdf, force=True)
    bak = d / "paper.lines.mathpix.bak.json"
    assert bak.is_file(), out
    saved = json.loads(bak.read_text())
    assert saved["pages"][0]["lines"][0]["type"] == "math"
    assert "source" not in saved, "the backup must be the MathPix file verbatim"


def test_the_backup_is_never_overwritten_by_a_second_run(tmp_path, monkeypatch):
    """A second forced read must not replace the backup with the FREE reading
    it made on the first — that would lose the paid layer one run later."""
    d = tmp_path / "paper"
    d.mkdir()
    (d / "paper.pdf").write_bytes(b"%PDF-1.7\n%%EOF\n")
    bak = d / "paper.lines.mathpix.bak.json"
    bak.write_text('{"pages": [{"page": 1, "lines": ['
                   '{"type": "math", "text": "THE PAID ONE"}]}]}',
                   encoding="utf-8")
    (d / "paper.lines.json").write_text(
        '{"pages": [{"page": 1, "lines": ['
        '{"type": "math", "text": "a later reading"}]}]}', encoding="utf-8")
    monkeypatch.setattr(
        "pdfreader.docmodel_six.build", lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError("stop")))
    before = bak.read_bytes()
    C.cmd_glyphlines(d / "paper.pdf", force=True)
    assert bak.read_bytes() == before


# ---------------------------------------------------------------- 854

def test_our_own_output_is_never_promoted_to_a_document(tmp_path):
    r"""854 — `_has_a_second_document` asks whether the SIBLINGS are artefacts.
    Nothing asked whether the SUBJECT is.

    So writing `evidence-formula.pdf` into a folder that also holds the document
    promoted the artefact into `evidence-formula/evidence-formula.pdf` with an
    empty sidecar — and the next build wrote a fresh flat one beside it, leaving
    the first orphaned where a reader was still looking at it.

    Measured in the library: 2,667 nested artefact folders, nine in 0902.0431
    alone (`report/` 32 MB, `B/` 38.8 MB), every sidecar carrying `facts: []`
    because nothing ever drilled them. Those date from 09-17 and predate this
    function, so it was not the cause — but it reproduced on the first try, so it
    was the next one.
    """
    from pdfdrill.doclock import ensure_doc_folder
    d = tmp_path / "0902.0431"
    d.mkdir()
    for n in ("0902.0431.pdf", "evidence-formula.pdf", "evidence-equation.pdf",
              "report.pdf", "residuals.pdf", "B.pdf", "formula-report.pdf",
              "compare.pdf"):
        (d / n).write_bytes(PDF)
    for n in ("evidence-formula.pdf", "evidence-equation.pdf", "report.pdf",
              "residuals.pdf", "B.pdf", "formula-report.pdf", "compare.pdf"):
        got = ensure_doc_folder(d / n)
        assert Path(got) == d / n, f"{n} was promoted"
        assert not (d / Path(n).stem).is_dir(), f"{n} got its own folder"


def test_a_real_second_document_is_still_promoted(tmp_path):
    """The behaviour 830 exists for must survive: two real documents in one
    directory DO collide, because every build writes the same fixed names."""
    from pdfdrill.doclock import ensure_doc_folder
    d = tmp_path / "downloads"
    d.mkdir()
    (d / "paper_one.pdf").write_bytes(PDF)
    (d / "paper_two.pdf").write_bytes(PDF)
    ensure_doc_folder(d / "paper_one.pdf")
    assert (d / "paper_one").is_dir()
    assert (d / "paper_one" / "paper_one.pdf").is_file()


def test_a_split_evidence_part_is_also_our_output(tmp_path):
    """856 — `evidence-[a-z]+` admitted `evidence-formula` and nothing else, so a
    split part `evidence-formula-01.pdf` read as a second DOCUMENT and 854 would
    have promoted it into its own folder: the defect 854 had just closed,
    reintroduced by a new file name. Caught before any part was built, because
    inkdrill asked for the naming convention before building against it."""
    from pdfdrill.doclock import ensure_doc_folder
    d = tmp_path / "cardona"
    d.mkdir()
    names = ["cardona.pdf", "evidence-formula-01.pdf", "evidence-formula-02.pdf",
             "evidence-formula-1.pdf", "evidence-formula-part1.pdf",
             "evidence-equation-02.pdf"]
    for n in names:
        (d / n).write_bytes(PDF)
    for n in names[1:]:
        assert Path(ensure_doc_folder(d / n)) == d / n, n
        assert not (d / Path(n).stem).is_dir(), n


def test_a_real_document_whose_name_merely_starts_with_evidence_is_not_exempt():
    """The guard must not become a prefix match: `evidence.pdf` on its own is
    not one of our artefacts."""
    from pdfdrill.doclock import _GENERATED_PDF
    assert not _GENERATED_PDF.match("evidence.pdf")
    assert not _GENERATED_PDF.match("arXiv-0902.0431v1.pdf")
    assert _GENERATED_PDF.match("evidence-formula-01.pdf")
