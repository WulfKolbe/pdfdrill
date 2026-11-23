"""T-0153 #2 — when the ink judge has run, its numbers decide the verdict.

`REACHED` means "nothing known missing". On a page the judge has just faulted
that is false, so once the judge has spoken the verdict is its answer, not the
model's object counts (coordinator, T-0153 #2).

THREE STATES, and the third is the one that keeps the promise honest:

  judged, nothing faulted   -> REACHED,  exit 0
  judged, something faulted -> DEGRADED, exit 4, the counts in the line
  not judged                -> exactly as before, "ink: not judged"

WHERE THE JUDGE COMES FROM. `PDFDRILL_JUDGE` first, then the config key
`judge`, then nothing. No path is baked into this repository: inkdrill is not
a dependency of pdfdrill and a fresh clone must build and test without it.
An entry that does not resolve to an executable file is the same as no entry.

WHY THIS DOES NOT REPORT A RESIDUAL. The residual is the BOARD's statistic and
it is computed in drillgroup `scripts/board_run.py`:

    orig = page_chars or (glyphs + unpaired_A);   den = orig + rules_a
    residual = (glyph + (orig - glyphs) + unpaired_B
                + rules_missing + rules_invented) / den

Four separate owner decisions live in that denominator -- rule ink on both
sides of the division, an unmeasurable glyph staying in the denominator, the
page's own glyph count rather than the reading's, and NOT RUN for a status
that is not OK. A second implementation here would be a second source of truth
that can silently disagree with the board, which is the defect class this
project keeps finding.

And it is not needed. The verdict asks whether ANYTHING faulted, and
`residual > 0` holds exactly when that NUMERATOR is non-zero -- a plain sum of
raw judge counts, with no denominator in it. So the verdict quotes the judge's
own counts and leaves the ratio to the board.

ONE PAGE IS ENOUGH TO FAULT A DOCUMENT, so the pages are judged in order and
the walk STOPS at the first page that faults: the verdict is already DEGRADED
and no later page can change it. The line says how many pages were judged, so
a run that stopped early is not mistaken for a clean sweep.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfdrill import pagejudge, verdict                     # noqa: E402


# --------------------------------------------------------------- the path
def test_no_entry_means_no_judge(tmp_path, monkeypatch):
    monkeypatch.delenv("PDFDRILL_JUDGE", raising=False)
    monkeypatch.setattr(pagejudge._cfg, "get", lambda *a, **k: None)
    assert pagejudge.judge_path() is None


def test_the_env_wins(tmp_path, monkeypatch):
    exe = tmp_path / "inkcmp-judge"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)
    other = tmp_path / "from-config"
    other.write_text("#!/bin/sh\nexit 0\n")
    other.chmod(0o755)
    monkeypatch.setenv("PDFDRILL_JUDGE", str(exe))
    monkeypatch.setattr(pagejudge._cfg, "get", lambda *a, **k: str(other))
    assert pagejudge.judge_path() == exe


def test_the_config_key_is_the_fallback(tmp_path, monkeypatch):
    exe = tmp_path / "inkcmp-judge"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)
    monkeypatch.delenv("PDFDRILL_JUDGE", raising=False)
    monkeypatch.setattr(pagejudge._cfg, "get",
                        lambda k, d=None: str(exe) if k == "judge" else d)
    assert pagejudge.judge_path() == exe


@pytest.mark.parametrize("what", ["missing", "not-executable", "a-directory"])
def test_an_entry_that_is_not_an_executable_is_no_entry(tmp_path, monkeypatch,
                                                        what):
    if what == "missing":
        p = tmp_path / "nope"
    elif what == "not-executable":
        p = tmp_path / "plain"
        p.write_text("#!/bin/sh\n")
    else:
        p = tmp_path / "dir"
        p.mkdir()
    monkeypatch.setenv("PDFDRILL_JUDGE", str(p))
    monkeypatch.setattr(pagejudge._cfg, "get", lambda *a, **k: None)
    assert pagejudge.judge_path() is None, f"{what} was accepted as the judge"


def test_no_judge_path_is_written_into_this_repository():
    """inkdrill is not a dependency. A default path here would make the suite
    pass on the author's machine and nowhere else."""
    import subprocess
    out = subprocess.run(
        ["grep", "-rn", "inkcmp-judge", "--include=*.py", "--include=*.yaml",
         "--include=*.toml", str(ROOT / "src"), str(ROOT / "pyproject.toml")],
        capture_output=True, text=True).stdout
    # THE FIRST VERSION OF THIS TEST MATCHED ITS OWN CHECKOUT. grep -n prints
    # `path:lineno:content`, and the condition tested the WHOLE line for
    # "home" -- which is in `/home/<user>/...`, the path of this very
    # repository. It failed on a correct file and would fail on any machine
    # whose clone lives under /home. Only the CONTENT may be inspected.
    bad = []
    for l in out.splitlines():
        content = l.split(":", 2)[-1]
        if "inkcmp-judge" not in content:
            continue
        if any(h in content for h in ("/home/", "/Users/", "drillgroup",
                                      "/usr/local/bin", "~/")):
            bad.append(l)
    assert not bad, "a concrete judge path is baked into src:\n" + "\n".join(bad)


# ------------------------------------------------------------ the parsing
JUDGE1_CLEAN = (
    "# page 1: family cm, 67 lines, A chars 2526, snippet pages 67\n"
    "JUDGE1 a_glyphs 2526 a_unpaired 0 accents_on_ink 0 b_unpaired 0 "
    "flagged 0 glyph 0 glyphs 2526 rules_a 4 rules_invented 0 "
    "rules_missing 0 style 0 unpaired_A 0 unpaired_B 0\n"
    "STATUS OK\n")
JUDGE1_FAULTED = (
    "# page 1: family cm, 67 lines, A chars 2526, snippet pages 67\n"
    "JUDGE1 a_glyphs 2526 a_unpaired 5 accents_on_ink 0 b_unpaired 3 "
    "flagged 7 glyph 7 glyphs 2500 rules_a 4 rules_invented 1 "
    "rules_missing 2 style 11 unpaired_A 5 unpaired_B 3\n"
    "STATUS OK\n")
JUDGE1_NOT_OK = (
    "JUDGE1 a_glyphs 0 glyphs 0 glyph 0 rules_a 0\n"
    "STATUS FONT_UNMAPPED\n")


def test_a_clean_page_has_no_findings():
    d = pagejudge.parse(JUDGE1_CLEAN)
    assert d["status"] == "OK"
    assert d["page_chars"] == 2526
    assert pagejudge.faults(d) == 0


def test_every_part_of_the_boards_numerator_counts_as_a_fault():
    """glyph + (page_chars - glyphs) + unpaired_B + rules_missing
    + rules_invented -- the board's numerator, nothing else."""
    d = pagejudge.parse(JUDGE1_FAULTED)
    assert d["status"] == "OK"
    # 7 wrong + (2526-2500 unread) + 3 invented glyph + 2 missing rule
    # + 1 invented rule
    assert pagejudge.faults(d) == 7 + 26 + 3 + 2 + 1


def test_style_findings_are_not_faults():
    """The board leaves style out of the residual, so the verdict leaves it
    out too -- `style 11` in the faulted sample is not in the sum above."""
    d = pagejudge.parse(JUDGE1_FAULTED)
    assert d["style"] == 11
    assert pagejudge.faults(d) == 39


def test_a_status_that_is_not_OK_is_not_a_judgement():
    d = pagejudge.parse(JUDGE1_NOT_OK)
    assert d["status"] == "FONT_UNMAPPED"
    assert pagejudge.faults(d) is None, (
        "a page the judge could not measure must not read as 0 faults -- that "
        "is the difference between 'clean' and 'not measured'")


def test_output_with_no_JUDGE1_line_is_not_a_judgement():
    assert pagejudge.parse("boom\nTraceback...\n").get("status") == ""
    assert pagejudge.faults(pagejudge.parse("boom\n")) is None


# ------------------------------------------------------------ the verdict
def _v(ink):
    return verdict.decide(has_text=True, maths_unread=False, ink=ink)


def test_a_clean_judgement_is_REACHED():
    v = _v(pagejudge.Ink(pages_judged=3, pages=3, faults=0, page=0, detail=""))
    assert v.state == verdict.REACHED and v.exit_code == 0
    assert "not judged" not in v.line()
    assert "3 page(s)" in v.line()


def test_a_faulted_judgement_is_DEGRADED_whatever_the_model_holds():
    v = _v(pagejudge.Ink(pages_judged=1, pages=3, faults=39, page=1,
                        detail="7 wrong, 26 unread, 3 invented, 2/1 rule"))
    assert v.state == verdict.DEGRADED and v.exit_code == 4
    assert "39 finding(s)" in v.line() and "page 1" in v.line()
    assert "7 wrong" in v.line()


def test_the_line_says_it_stopped_early():
    """One faulted page settles the document, so the walk stops -- and the
    line must not let that read as a clean sweep of all three."""
    v = _v(pagejudge.Ink(pages_judged=1, pages=3, faults=39, page=1, detail="x"))
    assert "1 of 3" in v.line(), v.line()


def test_not_judged_is_unchanged():
    v = _v(None)
    assert "ink: not judged" in v.line()
    assert v.state == verdict.REACHED and v.exit_code == 0


def test_a_status_the_judge_could_not_measure_says_so_and_is_not_a_pass():
    v = _v(pagejudge.Ink(pages_judged=0, pages=3, faults=None, page=1,
                        detail="", status="FONT_UNMAPPED"))
    assert "not judged" in v.line() and "FONT_UNMAPPED" in v.line()
    assert v.state == verdict.REACHED, (
        "an unmeasurable page is not a fault; it is an absence of evidence, "
        "which is what the old line already said")


def test_the_judge_overrides_a_maths_warning_it_contradicts():
    """A judge that finds no missing ink has seen the mathematics on the page.
    `maths_unread` is a guess from fonts; the judge is a measurement."""
    v = verdict.decide(has_text=True, maths_unread=True,
                       ink=pagejudge.Ink(pages_judged=3, pages=3, faults=0,
                                        page=0, detail=""))
    assert v.state == verdict.REACHED, (
        "the font guess outvoted a clean measurement of the same page")


# ---------------------------------------------------------------- the route
# Found by the acceptance run, not by a test: with PDFDRILL_JUDGE set, BH1
# p113 -- a scan carrying an OCR underlay -- was judged on the GLYPH route and
# came back "1313 finding(s) ... 1308 wrong". `needs_ocr` is False for that
# document, because it DOES have a text layer; that is exactly what T-0153 #1
# is about. The glyph route compares glyph shapes against positions that are
# an OCR estimate, so its answer there is a broken measurement rather than a
# fault in the reading, and docs/LANES.md and the board both use `--route
# scan` on a scan.

def _sc_for(tmp_path, monkeypatch, *, text_layer, scanned, keys=frozenset()):
    from pdfdrill import ocr_router as R
    from pdfdrill.sidecar import Sidecar
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.7 not-a-real-pdf\n%%EOF\n")
    sc = Sidecar(pdf)
    sc.set_evidence("pages", 3)
    sc.set_evidence("text_layer", text_layer)
    sc.set_evidence("needs_ocr", not text_layer)
    sc.save()
    monkeypatch.setattr(R, "scanned_images_for", lambda *a, **k: scanned or None)
    monkeypatch.setattr(R, "arxiv_source_for", lambda *a, **k: False)
    monkeypatch.setattr(R, "keys_present", lambda: keys)
    monkeypatch.setattr(R, "ink_available", lambda: True)
    monkeypatch.setattr(R, "detector_available", lambda: True)
    return pdf, Sidecar(pdf)


def _route_used(pdf, sc, monkeypatch):
    seen = {}
    from pdfdrill import pagejudge
    monkeypatch.setattr(pagejudge, "judge_path", lambda: Path("/nonexistent"))
    monkeypatch.setattr(pagejudge, "judge_document",
                        lambda *a, **k: seen.setdefault("route", k.get("route")))
    verdict._ink_for(pdf, sc)
    return seen.get("route")


def test_a_scan_with_an_ocr_underlay_takes_the_scan_route(tmp_path,
                                                          monkeypatch):
    pdf, sc = _sc_for(tmp_path, monkeypatch, text_layer=True, scanned=True)
    assert _route_used(pdf, sc, monkeypatch) == "scan", (
        "`needs_ocr` is False for an underlay scan, so deriving the route "
        "from it put a scan on the glyph route -- 1313 findings on BH1 p113")


def test_a_born_digital_page_takes_the_glyph_route(tmp_path, monkeypatch):
    pdf, sc = _sc_for(tmp_path, monkeypatch, text_layer=True, scanned=False)
    assert _route_used(pdf, sc, monkeypatch) == "glyph"


def test_a_textless_scan_takes_the_scan_route(tmp_path, monkeypatch):
    pdf, sc = _sc_for(tmp_path, monkeypatch, text_layer=False, scanned=True)
    assert _route_used(pdf, sc, monkeypatch) == "scan"


def test_a_keyed_machine_does_not_change_the_route(tmp_path, monkeypatch):
    """The lane differs (gemma rather than geometry) and the route must not."""
    pdf, sc = _sc_for(tmp_path, monkeypatch, text_layer=True, scanned=True,
                      keys=frozenset({"gemma"}))
    assert _route_used(pdf, sc, monkeypatch) == "scan"


def test_the_scan_route_is_reduced_to_a_sign_and_never_to_a_number():
    """A scan residual is not comparable with a glyph-route one (board_run
    `_scan1` keeps it in its own field), so this gate takes only its sign."""
    from pdfdrill import pagejudge
    d = pagejudge.parse("SCAN1 comps 120 holes 3 residual 0.0412\nSTATUS OK\n")
    assert d["route"] == "scan"
    assert pagejudge.faults(d) == 1
    clean = pagejudge.parse("SCAN1 comps 120 holes 0 residual 0.0\nSTATUS OK\n")
    assert pagejudge.faults(clean) == 0


def test_the_scan_route_does_not_borrow_the_word_finding():
    """It has no count of findings, only a residual the judge computed. The
    first version printed the SIGN as "1 finding(s)" on BH1 p113, whose scan
    residual is 0.5219 -- reading as exactly one finding."""
    from pdfdrill import pagejudge
    d = pagejudge.parse(
        "SCAN1 comps 1510 holes 286 invented 386 lines 44 lines_judged 44 "
        "missing 116 not_set 0 rendered 1856 unplaced 0 residual 0.521854\n"
        "STATUS OK\n")
    ink = pagejudge.Ink(1, 3, pagejudge.faults(d), 1, pagejudge.detail(d),
                        "OK", "scan")
    line = ink.line()
    assert "finding(s)" not in line, line
    assert "scan residual 0.5219" in line, line
    assert "116 missing" in line and "386 invented" in line, line
    assert "1 of 3" in line, line


def test_the_glyph_route_still_counts_findings():
    from pdfdrill import pagejudge
    d = pagejudge.parse(JUDGE1_FAULTED)
    ink = pagejudge.Ink(1, 3, pagejudge.faults(d), 1, pagejudge.detail(d))
    assert "39 finding(s)" in ink.line()
    assert "scan residual" not in ink.line()


def test_the_glyph_route_never_prints_a_residual():
    """board_run.py owns that formula; a second one here could disagree."""
    from pdfdrill import pagejudge
    d = pagejudge.parse(JUDGE1_FAULTED)
    assert "residual" not in pagejudge.detail(d)


# ------------------------------------------------------------- doctor says
# `doctor` reports tools, deps and keys. The ink judge is an OPTIONAL tool
# living outside this distribution, so an operator who set PDFDRILL_JUDGE had
# no way to confirm it took effect except by noticing a verdict line no longer
# said "ink: not judged".
#
# The third state is the one worth a test: a path that is SET BUT BROKEN must
# not look like an absent judge. (The first version of this reported
# "name 'os' is not defined" for two of the three states -- `os` is not
# imported at module level in commands.py and the broad `except` turned the
# NameError into a printed message, so the OK case still looked fine.)

def test_doctor_names_a_configured_judge(tmp_path, monkeypatch):
    from pdfdrill import commands
    exe = tmp_path / "inkcmp-judge"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)
    monkeypatch.setenv("PDFDRILL_JUDGE", str(exe))
    out = commands.cmd_doctor()
    assert "ink judge" in out
    assert str(exe) in out, out[out.find("ink judge"):][:200]
    assert "not defined" not in out


def test_doctor_says_a_broken_judge_path_is_ignored(tmp_path, monkeypatch):
    from pdfdrill import commands
    monkeypatch.setenv("PDFDRILL_JUDGE", str(tmp_path / "nope"))
    out = commands.cmd_doctor()
    seg = out[out.find("ink judge"):][:260]
    assert "is set but is not an executable file" in seg, seg
    assert "not defined" not in seg, seg


def test_doctor_says_how_to_turn_it_on_when_unset(monkeypatch):
    from pdfdrill import commands
    monkeypatch.delenv("PDFDRILL_JUDGE", raising=False)
    monkeypatch.setattr(verdict, "_ink_for", lambda *a, **k: None)
    out = commands.cmd_doctor()
    seg = out[out.find("ink judge"):][:300]
    assert "PDFDRILL_JUDGE" in seg and "not judged" in seg, seg
    assert "not defined" not in seg, seg
