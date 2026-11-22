#!/usr/bin/env python3
r"""Compare two revisions' readings of the same pages. TWO EXPORTS, never a tree.

    python3 tools/revdiff.py HEAD WORKTREE  --board
    python3 tools/revdiff.py 701b62cc HEAD  --pdf a.pdf --pdf b.pdf
    python3 tools/revdiff.py HEAD WORKTREE  --board --full

WHY THIS EXISTS. Twice in T-0156 a before/after comparison read the WORKING
TREE for its "before" side while that tree was being edited:

  * a background comparison ran `git stash` on the tree it was reading, and
    an edit of mine landed against the stashed content;
  * a comparison whose `before` side was `src/` reported "30 of 30 pages
    byte-identical" because the change under test had been applied to `src`
    WHILE IT RAN. The real answer was a regression on one page, and it was
    found only when the comparison was re-run against a fixed export.

A comparison must read two FIXED trees. `git archive <rev> | tar -x` gives
one per revision under the project's own `work/run-files/`, with no
worktree, no stash and no checkout of the tree being edited (house rule
D-7). `WORKTREE` is accepted for the side under development and is copied,
not read in place, so an edit during the run cannot change the answer.

It diffs the lines.json each revision writes: per page, the line count, and
every line whose TEXT or TYPE differs, matched by text so that an inserted
line does not misalign the rest (a positional zip reported two spurious
"retyped" lines once).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "work", "run-files", "revdiff")
BOARD = os.path.expanduser("~/drillgroup/work/board60")

READ = '''
import sys, json
sys.path.insert(0, %r)
from pdfreader import docmodel_six as dm
d = dm.to_lines_json(dm.build(%r), doc_id=%r)
out = []
for p in d["pages"]:
    for l in p["lines"]:
        out.append([p.get("page"), l.get("type"), l.get("text") or ""])
print(json.dumps(out))
'''


def export(rev: str, dest: str) -> str:
    """One revision's `src/`, fixed on disk. `WORKTREE` is COPIED, not used."""
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest, exist_ok=True)
    if rev.upper() == "WORKTREE":
        shutil.copytree(os.path.join(ROOT, "src"), os.path.join(dest, "src"))
    else:
        tar = subprocess.run(["git", "-C", ROOT, "archive", rev],
                             capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", dest], input=tar, check=True)
    src = os.path.join(dest, "src")
    if not os.path.isdir(src):
        sys.exit("export of %s has no src/" % rev)
    return src


def read(src: str, pdf: str, key: str, timeout: int):
    env = {"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin",
           "HOME": os.path.expanduser("~")}
    try:
        r = subprocess.run([sys.executable, "-c", READ % (src, pdf, key)],
                           capture_output=True, text=True, env=env,
                           timeout=timeout)
        return json.loads(r.stdout)
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rev_a")
    ap.add_argument("rev_b")
    ap.add_argument("--board", action="store_true",
                    help="every board page under ~/drillgroup/work/board60")
    ap.add_argument("--pdf", action="append", default=[],
                    help="a PDF to read (repeatable)")
    ap.add_argument("--full", action="store_true",
                    help="print every differing line, not the first few")
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args()

    jobs = [(os.path.splitext(os.path.basename(p))[0], os.path.abspath(p))
            for p in a.pdf]
    if a.board:
        for d in sorted(os.listdir(BOARD)) if os.path.isdir(BOARD) else []:
            pdf = os.path.join(BOARD, d, d + ".pdf")
            if os.path.exists(pdf):
                jobs.append((d, pdf))
    if not jobs:
        sys.exit("nothing to read: pass --pdf or --board")

    os.makedirs(WORK, exist_ok=True)
    src_a = export(a.rev_a, os.path.join(WORK, "a"))
    src_b = export(a.rev_b, os.path.join(WORK, "b"))
    print("A = %-12s %s" % (a.rev_a, src_a))
    print("B = %-12s %s" % (a.rev_b, src_b))
    print()

    same = empty = failed = 0
    changed = []
    for key, pdf in jobs:
        ra, rb = read(src_a, pdf, key, a.timeout), read(src_b, pdf, key, a.timeout)
        if ra is None or rb is None:
            failed += 1
            print("FAILED  %s" % key)
            continue
        if not ra and not rb:
            empty += 1
            continue
        if ra == rb:
            same += 1
            continue
        # matched by TEXT, so an inserted line does not misalign the rest
        ta = {(p, t): ty for p, ty, t in ra}
        tb = {(p, t): ty for p, ty, t in rb}
        retyped = [(k, ta[k], tb[k]) for k in ta if k in tb and ta[k] != tb[k]]
        gone = [x for x in ra if (x[0], x[2]) not in tb]
        new = [x for x in rb if (x[0], x[2]) not in ta]
        changed.append((key, len(ra), len(rb), retyped, gone, new))

    print("identical %d   empty-both %d   changed %d   failed %d"
          % (same, empty, len(changed), failed))
    for key, na, nb, retyped, gone, new in changed:
        print()
        print("%s   lines %d -> %d   retyped %d, text -%d +%d"
              % (key, na, nb, len(retyped), len(gone), len(new)))
        lim = None if a.full else 4
        for (p, t), x, y in retyped[:lim]:
            print("    p%-3s %-9s -> %-9s %s" % (p, x, y, t[:72]))
        for p, ty, t in gone[:lim]:
            print("    - p%-3s %-9s %s" % (p, ty, t[:72].replace("\n", "|")))
        for p, ty, t in new[:lim]:
            print("    + p%-3s %-9s %s" % (p, ty, t[:72].replace("\n", "|")))
    return 1 if changed or failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
