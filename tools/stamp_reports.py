"""242 — put the two provenance lines on every out/NNN.txt.

    2026-08-27T08:56:07Z  /  2026-08-27 10:56:07 +02:00 (Europe/Berlin)  commit ccc61c5 +dirty
       ... the report ...
    2026-08-27T09:14:22Z  /  2026-08-27 11:14:22 +02:00 (Europe/Berlin)  end

First line: when the report started, and the tree it was written on. Last line:
when it finished. Together they give the duration, which the harness otherwise
shows only as a "Worked for 6m 55s" note that does not survive being pasted.

RETROFIT. Git recorded ONE instant per report — the commit that added it — with
the offset it was committed at. That instant is converted to Berlin AT THAT
INSTANT, so a January report reads +01:00 and an August one +02:00; using
today's offset would make the retrofit lie about its own provenance.

The finish time was NEVER RECORDED for those reports, so the closing line says
so rather than supplying one. A rule with 153 fabricated end times is worse
than a rule that admits what it does not know.

Run: python3 tools/stamp_reports.py [--check]
"""
import datetime
import re
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from pdfdrill.report_tex import NO_END, provenance_open, provenance_close  # noqa

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
BOTH = (r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z  /  "
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{2}:\d{2} \(Europe/Berlin\)")
OPEN = re.compile(r"^%s  commit [0-9a-f]{7,40}( \+dirty)?$" % BOTH)
CLOSE = re.compile(r"^(%s  end|%s)$" % (BOTH, re.escape(NO_END)))
ANYSTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")


def git(*a):
    return subprocess.run(("git",) + a, cwd=str(ROOT), capture_output=True,
                          text=True).stdout.strip()


def add_commit(rel):
    out = git("log", "--diff-filter=A", "--format=%H%x09%cI", "-1", "--", rel)
    if not out or "\t" not in out:
        return None, None
    h, when = out.split("\t", 1)
    return h, datetime.datetime.fromisoformat(when)


def strip_old(lines):
    """Drop any pre-existing stamp lines, in either old format, top and tail."""
    while lines and ANYSTAMP.match(lines[0]):
        del lines[0]
    while lines and (not lines[-1].strip() or ANYSTAMP.match(lines[-1])
                     or lines[-1] == NO_END):
        del lines[-1]
    return lines


def main():
    check = "--check" in sys.argv
    files = sorted(OUT.glob("*.txt"))
    ok = bad = done = skipped = 0
    for f in files:
        lines = f.read_text(encoding="utf-8", errors="replace").split("\n")
        if OPEN.match(lines[0] if lines else "") and \
                CLOSE.match(next((l for l in reversed(lines) if l.strip()), "")):
            ok += 1
            continue
        if check:
            print("::error:: %s lacks the two provenance lines" % f.name)
            bad += 1
            continue
        h, when = add_commit(str(f.relative_to(ROOT)))
        if not h:
            print("  SKIP  %s — no add-commit in history" % f.name)
            skipped += 1
            continue
        body = strip_old(lines)
        head = "%s  commit %s" % (
            _both_static(when), git("rev-parse", "--short", h))
        f.write_text("\n".join([head] + body + ["", NO_END]) + "\n",
                     encoding="utf-8")
        done += 1
    if check:
        print("%d of %d out/*.txt carry both provenance lines" % (ok, len(files)))
        return 1 if bad else 0
    print("stamped %d, already correct %d, skipped %d, of %d"
          % (done, ok, skipped, len(files)))
    return 0


def _both_static(when):
    u = when.astimezone(datetime.timezone.utc)
    loc = u.astimezone(ZoneInfo("Europe/Berlin"))
    off = loc.strftime("%z")
    return "%s  /  %s %s:%s (Europe/Berlin)" % (
        u.strftime("%Y-%m-%dT%H:%M:%SZ"),
        loc.strftime("%Y-%m-%d %H:%M:%S"), off[:3], off[3:])


if __name__ == "__main__":
    raise SystemExit(main())
