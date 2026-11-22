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

REQUIRE = '''
import sys, json
sys.path.insert(0, %r)
from pdfreader import docmodel_six as dm
pages = dm.build(%r%s)
want = %r
ok = 0
if want == "rotated":
    ok = int(any(getattr(ln, "rotated", False) for p in pages for ln in p.lines))
elif want == "frac2x":
    rs = [r for p in pages for ln in p.lines for r in (ln.rules or [])
          if r.role == "fraction"]
    for i, A in enumerate(rs):
        for Bx in rs[i+1:]:
            if not (A.rect[2] < Bx.rect[0] or Bx.rect[2] < A.rect[0]):
                ok = 1
print(json.dumps(ok))
'''

READ = '''
import sys, json
sys.path.insert(0, %r)
from pdfreader import docmodel_six as dm
d = dm.to_lines_json(dm.build(%r%s), doc_id=%r)
out = []
for p in d["pages"]:
    for l in p["lines"]:
        out.append([p.get("page"), l.get("type"), l.get("text") or ""])
print(json.dumps(out))
'''


def describe(rev: str, dest: str) -> str:
    """What was ACTUALLY compared, in one line, for the result's header.

    A result that does not say what it compared can be read as answering a
    question it never asked. This task produced three such results before the
    tool existed, and one after: a hand-rolled comparison picked up an export
    directory left by an earlier run, so it compared a revision three commits
    old and showed those commits' changes as if they were the one under test.
    The header is how a reader catches that at a glance.
    """
    if rev.upper() == "WORKTREE":
        head = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        diff = subprocess.run(["git", "-C", ROOT, "diff", "HEAD"],
                              capture_output=True, text=True).stdout
        import hashlib
        h = hashlib.sha256(diff.encode()).hexdigest()[:12] if diff.strip() else "clean"
        n = len([l for l in diff.splitlines() if l.startswith("+++ ")])
        return "WORKTREE  on %s  +%d file(s) changed  diff %s" % (head, n, h)
    out = subprocess.run(
        ["git", "-C", ROOT, "show", "-s", "--format=%h  %ad  %s", "--date=short", rev],
        capture_output=True, text=True)
    return out.stdout.strip() or rev


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


def _env():
    return {"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin",
            "HOME": os.path.expanduser("~")}


def read(src: str, pdf: str, key: str, timeout: int, page=None):
    sel = "" if page is None else ", pages=[%d]" % (page - 1)
    try:
        r = subprocess.run([sys.executable, "-c", READ % (src, pdf, sel, key)],
                           capture_output=True, text=True, env=_env(),
                           timeout=timeout)
        return json.loads(r.stdout)
    except Exception:
        return None


def qualifies(src: str, pdf: str, want: str, timeout: int, page=None) -> bool:
    """Does this page carry the SHAPE the change acts on?

    A held-out sample drawn without this says nothing: 20 random pages once
    produced 0 movers, which rules out a misfire and measures no reach.
    """
    sel = "" if page is None else ", pages=[%d]" % (page - 1)
    try:
        r = subprocess.run([sys.executable, "-c", REQUIRE % (src, pdf, sel, want)],
                           capture_output=True, text=True, env=_env(),
                           timeout=timeout)
        return bool(json.loads(r.stdout))
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rev_a")
    ap.add_argument("rev_b")
    ap.add_argument("--board", action="store_true",
                    help="every board page under ~/drillgroup/work/board60")
    ap.add_argument("--pdf", action="append", default=[],
                    help="a PDF to read (repeatable)")
    ap.add_argument("--pages-from", default=None,
                    help="a file of `<pdf>\\t<page>` lines: a held-out sample, "
                         "each document read at its own page, under ONE pair "
                         "of exports")
    ap.add_argument("--full", action="store_true",
                    help="print every differing line, not the first few")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--page", type=int, default=None,
                    help="read only this 1-based page of each PDF")
    ap.add_argument("--require", default=None,
                    help="skip a page unless this expression is true of the "
                         "B-side reading: `frac2x` = two fraction rules "
                         "overlapping in x, `rotated` = any rotated line")
    a = ap.parse_args()

    jobs = [(os.path.splitext(os.path.basename(p))[0], os.path.abspath(p), a.page)
            for p in a.pdf]
    if a.pages_from:
        for ln in open(a.pages_from, encoding="utf-8"):
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            path, _, pg = ln.partition("\t")
            jobs.append((os.path.splitext(os.path.basename(path))[0],
                         path, int(pg) if pg.strip() else None))
    if a.board:
        for d in sorted(os.listdir(BOARD)) if os.path.isdir(BOARD) else []:
            pdf = os.path.join(BOARD, d, d + ".pdf")
            if os.path.exists(pdf):
                jobs.append((d, pdf, a.page))
    if not jobs:
        sys.exit("nothing to read: pass --pdf or --board")

    # A FRESH FOLDER PER RUN. The exports are never reused and never found
    # by a later process: a stale `a/` left by an earlier run is exactly how
    # a comparison in this task came to read a revision three commits old.
    import datetime
    run = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-") + str(os.getpid())
    base = os.path.join(WORK, run)
    if os.path.exists(base):
        sys.exit("refusing to reuse %s" % base)
    os.makedirs(base)
    src_a = export(a.rev_a, os.path.join(base, "a"))
    src_b = export(a.rev_b, os.path.join(base, "b"))
    print("=" * 72)
    print("A  %s" % describe(a.rev_a, src_a))
    print("B  %s" % describe(a.rev_b, src_b))
    print("   exports: %s" % base)
    print("=" * 72)
    print()

    same = empty = failed = 0
    changed = []
    ra_all, rb_all = {}, {}
    skipped_shape = 0
    for key, pdf, page in jobs:
        if a.require and not qualifies(src_b, pdf, a.require, a.timeout, page):
            skipped_shape += 1
            continue
        ra = read(src_a, pdf, key, a.timeout, page)
        rb = read(src_b, pdf, key, a.timeout, page)
        if ra is None or rb is None:
            failed += 1
            print("FAILED  %s" % key)
            continue
        if not ra and not rb:
            empty += 1
            continue
        ra_all[key], rb_all[key] = ra, rb
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

    print("identical %d   empty-both %d   changed %d   failed %d%s"
          % (same, empty, len(changed), failed,
             ("   skipped (no %s) %d" % (a.require, skipped_shape))
             if a.require else ""))
    for key, na, nb, retyped, gone, new in changed:
        print()
        print("%s   lines %d -> %d   retyped %d, text -%d +%d"
              % (key, na, nb, len(retyped), len(gone), len(new)))
        # NOTHING LOST is the gate for a prerequisite change: the characters
        # may be redistributed between lines, but none may disappear.
        import re as _re
        def _bare(rows):
            t = "".join(x[2] for x in rows)
            t = _re.sub(r"\\[a-zA-Z]+\s?", "", t)
            t = _re.sub(r"[\$\{\}_^\\\[\]]", "", t)
            return len(_re.sub(r"\s", "", t))
        print("    characters with LaTeX stripped: %d -> %d  (%+d)"
              % (_bare(ra_all[key]), _bare(rb_all[key]),
                 _bare(rb_all[key]) - _bare(ra_all[key])))
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
