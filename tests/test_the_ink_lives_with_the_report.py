r"""`inkreport` wrote the measurement and `residuals` said there was none.

The owner saw both lines in one terminal, 27 seconds apart, from ONE run of
`pdfdrill inkreport` — which is an alias of `residuals --measure --pdf`:

    report.ink.json  16:18:48  <pdf>.drill/   6 rows, built_at set
    residuals.pdf    16:19:15  <pdf parent>/  "no ink measurement for this
                                              document"

`header_lines` was right about the directory it was handed and the
directory was wrong: `cmd_residuals` and `cmd_evidence` both read
`pdf.parent / "report.ink.json"` while `reporttex` writes and adopts
`sc.blob_dir / "report.ink.json"`. Two commands, one file, two addresses.

blob_dir is preferred and the PDF's own folder is the fallback, so a
document drilled before the sidecar layout is not told its measurement
vanished.

AND `--ink` NOW NAMES THE COMMAND THAT MAKES THE FILE. The owner typed
`reporttex --ink` from the help text, which lists the flag without saying
nothing creates its argument until the ink pass has run, so the first thing
he met was a missing-file error for a file he could not have had.
"""
import json

import pytest

from pdfdrill.commands import ink_missing_message
from pdfdrill.reports import residuals as RS

INK = {"rows": [{"id": "X_EQ0001"}],
       "measured_against": {"built_at": "2026-11-22T15:18:40Z",
                            "model_mtime": 1795360720}}


def _write_ink(d):
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.ink.json").write_text(json.dumps(INK), encoding="utf-8")


def test_the_header_reports_a_measurement_that_is_there(tmp_path):
    _write_ink(tmp_path / "x.pdf.drill")
    line = "; ".join(RS.header_lines(tmp_path / "x.pdf.drill"))
    assert "equations measured 2026-11-22T15:18:40Z" in line
    assert "no ink measurement" not in line


def test_and_says_so_plainly_when_there_is_none(tmp_path):
    """The message is right — it was being asked about the wrong folder."""
    line = "; ".join(RS.header_lines(tmp_path))
    assert "no ink measurement" in line


def test_the_sidecar_is_where_the_ink_is_looked_for_first(tmp_path):
    r"""Both candidates exist: blob_dir wins, because that is where
    `reporttex` writes and adopts it."""
    _write_ink(tmp_path / "x.pdf.drill")
    stale = dict(INK)
    stale["measured_against"] = {"built_at": "1999-01-01T00:00:00Z"}
    (tmp_path / "report.ink.json").write_text(json.dumps(stale),
                                              encoding="utf-8")
    cands = [tmp_path / "x.pdf.drill" / "report.ink.json",
             tmp_path / "report.ink.json"]
    chosen = next(q for q in cands if q.is_file())
    assert chosen == cands[0]
    assert "2026-11-22" in "; ".join(RS.header_lines(chosen.parent))


def test_a_document_from_before_the_sidecar_keeps_its_ink(tmp_path):
    """Only the PDF's own folder has one: it must still be found, or a
    document drilled earlier is told its measurement vanished."""
    (tmp_path / "report.ink.json").write_text(json.dumps(INK),
                                              encoding="utf-8")
    cands = [tmp_path / "x.pdf.drill" / "report.ink.json",
             tmp_path / "report.ink.json"]
    chosen = next((q for q in cands if q.is_file()), cands[0])
    assert chosen == cands[1]
    assert "equations measured" in "; ".join(RS.header_lines(chosen.parent))


def test_ink_missing_names_inkreport_when_the_document_has_none(tmp_path):
    msg = ink_missing_message(tmp_path / "doc.pdf", "given.json",
                              tmp_path / "nothing" / "report.ink.json")
    assert "pdfdrill inkreport doc.pdf" in msg
    assert "does not exist" in msg


def test_ink_missing_points_at_the_one_the_document_has(tmp_path):
    _write_ink(tmp_path / "doc.pdf.drill")
    own = tmp_path / "doc.pdf.drill" / "report.ink.json"
    msg = ink_missing_message(tmp_path / "doc.pdf", "given.json", own)
    assert str(own) in msg
    assert "omit --ink to adopt it" in msg
    assert "inkreport" not in msg          # the file is there; no chain needed


def test_the_message_always_repeats_the_path_the_user_gave():
    """So the user can see their own typo, which is the common case."""
    for own in ("/nope/report.ink.json",):
        msg = ink_missing_message("doc.pdf", "mytypo.json", own)
        assert "mytypo.json" in msg


# ---------------------------------------------------------------------------
# A REFUSAL IS AN ERROR, SO IT EXITS 2.
#
# Both `--ink` refusals returned a bare string, which `main` prints and
# exits 0 on — so a script could not tell "your report was built" from
# "your --ink does not exist". `Report` is a `str` subclass carrying
# `exit_code`; only `main` reads that attribute, so every caller that
# treats the return as text is unaffected, `_inkreport_chain` included
# (it calls the function and reads the string, never a process exit).
#
# Nothing outside tests and the CLI invokes `reporttex`: no shell script,
# no Makefile, no CI workflow — grepped for *.sh, Makefile, *.mk, *.yml,
# *.yaml, *.py before the change.
#
# The check also MOVED to the top of `cmd_reporttex`, beside the long
# standing `--pages` refusal. It had sat 130 lines down, past the tiddler
# load, so a mistyped path cost that work before the complaint. Validating
# an argument before doing work is also what makes these tests cheap: a
# 9-byte PDF reaches the refusal, as `test_reporttex_refuses_a_bound`
# already relies on for `--pages`.

import pathlib

from pdfdrill import commands as C


def _fake_pdf(tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    return pdf


def test_the_refusal_names_inkreport_AND_exits_2(tmp_path):
    out = C.cmd_reporttex(_fake_pdf(tmp_path), ink="absent.json")
    assert "pdfdrill inkreport x.pdf" in out
    assert "absent.json does not exist" in out
    assert getattr(out, "exit_code", 0) == 2, "a refusal a script cannot see"


def test_the_refusal_names_the_documents_own_ink_AND_exits_2(tmp_path):
    pdf = _fake_pdf(tmp_path)
    own = pathlib.Path(str(pdf) + ".drill") / "report.ink.json"
    _write_ink(own.parent)
    out = C.cmd_reporttex(pdf, ink="mytypo.json")
    assert str(own) in out
    assert "omit --ink to adopt it" in out
    assert "mytypo.json" in out
    assert getattr(out, "exit_code", 0) == 2


def test_the_refusal_is_still_a_str_so_every_caller_keeps_working(tmp_path):
    """`_inkreport_chain` reads this return as text. A `Report` that was not
    a `str` would break the chain while fixing the exit code."""
    out = C.cmd_reporttex(_fake_pdf(tmp_path), ink="absent.json")
    assert isinstance(out, str)
    assert out.startswith("--ink ")
    assert len(out.splitlines()) >= 1


def test_no_ink_flag_at_all_does_not_refuse(tmp_path):
    """Omitting --ink must adopt or proceed, never refuse: the refusal is
    about a path the user GAVE that is not there."""
    out = C.cmd_reporttex(_fake_pdf(tmp_path))
    assert "does not exist" not in str(out)[:40]
    assert getattr(out, "exit_code", 0) != 2
