"""240 — put the provenance line on every out/NNN.txt.

New reports get it from report_tex.provenance_line() at write time. The 151
that already exist get it from GIT, which recorded when each was added and
what it was added on top of — a fact, not a reconstruction. `base` is the
PARENT of the commit that added the file, i.e. the tree the work started from,
which is the same thing provenance_line() names for a report being written now.

A file whose add-commit cannot be found is left alone and reported, rather
than stamped with a guess.

Run: python3 tools/stamp_reports.py [--check]
--check exits non-zero if any out/*.txt lacks a well-formed first line, which
is what CI wants.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
STAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z  base=[0-9a-f]{7,40}$")


def git(*a):
    return subprocess.run(("git",) + a, cwd=str(ROOT), capture_output=True,
                          text=True).stdout.strip()


def add_commit(rel):
    out = git("log", "--diff-filter=A", "--format=%H%x09%cI", "-1", "--", rel)
    if not out or "\t" not in out:
        return None, None
    h, when = out.split("\t", 1)
    return h, when


def to_utc(iso):
    import datetime
    return (datetime.datetime.fromisoformat(iso)
            .astimezone(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"))


def main():
    check = "--check" in sys.argv
    files = sorted(OUT.glob("*.txt"))
    stamped = already = skipped = bad = 0
    for f in files:
        rel = str(f.relative_to(ROOT))
        first = f.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
        if STAMP.match(first):
            already += 1
            continue
        if check:
            print("::error:: %s has no provenance line" % rel)
            bad += 1
            continue
        h, when = add_commit(rel)
        if not h:
            print("  SKIP  %s — no add-commit in history" % rel)
            skipped += 1
            continue
        parent = git("rev-parse", "--short=12", h + "^") or "root"
        line = "%s  base=%s" % (to_utc(when), parent)
        body = f.read_text(encoding="utf-8", errors="replace")
        f.write_text(line + "\n" + body, encoding="utf-8")
        stamped += 1
    if check:
        print("%d of %d out/*.txt carry a provenance line"
              % (already, len(files)))
        return 1 if bad else 0
    print("stamped %d, already had one %d, skipped %d, of %d"
          % (stamped, already, skipped, len(files)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
