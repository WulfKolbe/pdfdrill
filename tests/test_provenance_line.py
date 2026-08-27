"""240 — every report says when it was written and against which tree.

A report arriving after a newer one is otherwise indistinguishable from a
current one, and that happened twice in one session: a five-day-old
report.compare.tsv read as fresh off a listing that printed HH:MM with no date,
and a published 0902.0431 whose artefacts were two days apart from the library
copy they were compared against.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from pdfdrill import report_tex as rt

ROOT = Path(__file__).resolve().parent.parent
STAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z  base=[0-9a-f]{7,40}$")


def test_the_line_is_utc_and_names_a_commit():
    assert STAMP.match(rt.provenance_line()), rt.provenance_line()


def test_it_carries_no_branch():
    """Git records no such thing — `--abbrev-ref HEAD` is the branch NOW, not
    the branch a commit was made on. On a retrofitted report that would be an
    unverifiable claim dressed as provenance, and the hash locates the tree by
    itself."""
    assert "branch=" not in rt.provenance_line()


def test_every_out_report_begins_with_it():
    """All of them, not just the ones written after the rule. A rule with 151
    exceptions is not a rule."""
    bad = [str(f.relative_to(ROOT)) for f in sorted((ROOT / "out").glob("*.txt"))
           if not STAMP.match(
               f.read_text(encoding="utf-8", errors="replace").split("\n")[0])]
    assert not bad, "reports with no provenance line: %s" % bad[:8]


def test_no_report_carries_two_stamps():
    """The retrofit prepended instead of replacing once, because its
    "already stamped?" test used a double-escaped pattern that matched
    nothing — so it reported 151 stamped while leaving 151 duplicated."""
    dup = []
    for f in sorted((ROOT / "out").glob("*.txt")):
        lines = f.read_text(encoding="utf-8", errors="replace").split("\n")
        if len(lines) > 1 and STAMP.match(lines[0]) and \
                re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z  base=", lines[1]):
            dup.append(str(f.relative_to(ROOT)))
    assert not dup, "reports with a duplicated stamp: %s" % dup[:8]


def test_the_stamper_agrees_that_they_are_all_stamped():
    r = subprocess.run([sys.executable, "tools/stamp_reports.py", "--check"],
                       cwd=str(ROOT), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_cli_reports_lead_with_it(tmp_path):
    """publishready and handover cross session boundaries — they are read by
    the pages CLI, which is where a superseded report does its damage."""
    from tests.test_publish_ready import _doc, SPREAD
    from pdfdrill.commands import cmd_publishready, cmd_handover
    pdf = _doc(tmp_path, ink=SPREAD)
    assert STAMP.match(cmd_publishready(pdf).split("\n")[0])
    assert STAMP.match(cmd_handover(tmp_path).split("\n")[0])
    assert STAMP.match(json.loads(cmd_publishready(pdf, as_json=True))["provenance"])
    assert STAMP.match(json.loads(cmd_handover(tmp_path, as_json=True))["provenance"])


def test_the_build_stamp_names_the_tree_that_built_it(tmp_path):
    p = tmp_path / "report.pdf"
    p.write_bytes(b"%PDF-1.4\n")
    s = rt.build_stamp(p)
    assert re.match(r"^[0-9a-f]{7,40}$|^unknown$", s["commit"])
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", s["built_at"])
