"""242 — every report opens and closes with a timestamp, in both zones.

    2026-08-27T08:56:07Z  /  2026-08-27 10:56:07 +02:00 (Europe/Berlin)  commit ccc61c5 +dirty
       ... the report ...
    2026-08-27T09:14:22Z  /  2026-08-27 11:14:22 +02:00 (Europe/Berlin)  end

The pair gives the duration, which the harness otherwise shows only as a
"Worked for 6m 55s" note that does not survive being pasted. A report arriving
after a newer one is otherwise indistinguishable from a current one, and that
happened twice in one session.
"""
import datetime
import json
import re
import subprocess
import sys

import pytest
from pathlib import Path
from zoneinfo import ZoneInfo

from pdfdrill import report_tex as rt

ROOT = Path(__file__).resolve().parent.parent
BOTH = (r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z  /  "
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{2}:\d{2} \(Europe/Berlin\)")
OPEN = re.compile(r"^%s  commit [0-9a-f]{7,40}( \+dirty)?$" % BOTH)
CLOSE = re.compile(r"^(%s  end|%s)$" % (BOTH, re.escape(rt.NO_END)))


def test_both_lines_carry_both_zones():
    assert OPEN.match(rt.provenance_open()), rt.provenance_open()
    assert CLOSE.match(rt.provenance_close()), rt.provenance_close()


def test_the_two_halves_are_the_same_instant():
    line = rt.provenance_open()
    u, loc = line.split("  /  ")
    u = datetime.datetime.strptime(u, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc)
    body = loc.split(" (Europe/Berlin)")[0]
    local = datetime.datetime.strptime(body, "%Y-%m-%d %H:%M:%S %z")
    assert u == local, (u, local)


@pytest.mark.parametrize("iso,off", [
    ("2026-01-15T12:00:00+00:00", "+01:00"),      # winter
    ("2026-07-15T12:00:00+00:00", "+02:00"),      # summer
    ("2026-03-29T00:30:00+00:00", "+01:00"),      # before the March change
    ("2026-03-29T01:30:00+00:00", "+02:00"),      # after it
    ("2026-10-25T00:30:00+00:00", "+02:00"),      # before the October change
    ("2026-10-25T01:30:00+00:00", "+01:00"),      # after it
])
def test_the_offset_follows_daylight_saving(iso, off):
    """Hard-coding +02:00 is wrong on one side of every March and October."""
    when = datetime.datetime.fromisoformat(iso)
    assert off in rt.provenance_open(when), rt.provenance_open(when)


def test_octobers_repeated_hour_is_disambiguated_by_the_utc_half():
    """02:30 Berlin happens twice on the October change day. The local half
    alone cannot say which; the UTC half can, which is why both are shown."""
    a = rt.provenance_open(datetime.datetime.fromisoformat("2026-10-25T00:30:00+00:00"))
    b = rt.provenance_open(datetime.datetime.fromisoformat("2026-10-25T01:30:00+00:00"))
    assert "02:30:00 +02:00" in a and "02:30:00 +01:00" in b
    assert a.split("  /  ")[0] != b.split("  /  ")[0]


def test_the_zone_is_named_not_inherited():
    """ZoneInfo('Europe/Berlin'), not the machine's zone: a report is about
    Berlin whatever the machine is set to."""
    src = __import__("inspect").getsource(rt._both)
    assert "ZoneInfo(BERLIN)" in src and rt.BERLIN == "Europe/Berlin"


def test_dirty_is_flagged():
    src = __import__("inspect").getsource(rt.provenance_open)
    assert "porcelain" in src and "+dirty" in src


def test_it_carries_no_branch():
    """Git records no such thing — --abbrev-ref HEAD is the branch NOW, not the
    branch a commit was made on."""
    assert "branch" not in rt.provenance_open()


def test_every_out_report_opens_and_closes():
    files = sorted((ROOT / "out").glob("*.txt"))
    bad = []
    for f in files:
        lines = [l for l in f.read_text(encoding="utf-8",
                                        errors="replace").split("\n")]
        last = next((l for l in reversed(lines) if l.strip()), "")
        if not (OPEN.match(lines[0]) and CLOSE.match(last)):
            bad.append(f.name)
    assert not bad, "reports missing a provenance line: %s" % bad[:8]


def test_a_retrofit_does_not_invent_an_end_time():
    """The finish time was never recorded for reports written before 242, and
    supplying one would be the retrofit lying about its own provenance — the
    thing the retrofit rule warns against."""
    assert "not recorded" in rt.NO_END
    olds = [f for f in sorted((ROOT / "out").glob("*.txt"))
            if f.read_text(encoding="utf-8", errors="replace")
            .rstrip().endswith(rt.NO_END)]
    assert olds, "expected retrofitted reports to say so"


def test_the_stamper_agrees():
    r = subprocess.run([sys.executable, "tools/stamp_reports.py", "--check"],
                       cwd=str(ROOT), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_cli_reports_open_and_close(tmp_path):
    from tests.test_publish_ready import _doc, SPREAD
    from pdfdrill.commands import cmd_publishready, cmd_handover
    pdf = _doc(tmp_path, ink=SPREAD)
    for text in (cmd_publishready(pdf), cmd_handover(tmp_path)):
        lines = text.split("\n")
        assert OPEN.match(lines[0]), lines[0]
        assert CLOSE.match(lines[-1]), lines[-1]
    for blob in (cmd_publishready(pdf, as_json=True),
                 cmd_handover(tmp_path, as_json=True)):
        j = json.loads(blob)
        assert OPEN.match(j["started"]) and CLOSE.match(j["finished"])
