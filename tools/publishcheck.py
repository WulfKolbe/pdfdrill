#!/usr/bin/env python3
"""621 — did the site actually get the new reports?

A check that answers ONE question with evidence: is what is published the
same artefact as what is on disk here, per document. It compares the sha256
of each library report.pdf against the one on the live site, so "we published
overnight" becomes a fact rather than a belief.

    python3 tools/publishcheck.py                 # clone and compare
    python3 tools/publishcheck.py --site DIR      # compare against a clone

Exit status is 0 only when every document matches. Anything else is a
non-zero exit and a named list, so it can be run from cron or a hook.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

SITE_URL = "https://github.com/PDFDRILL/PDFDRILL.github.io.git"


def sha(p: pathlib.Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", type=pathlib.Path,
                    help="an existing clone; otherwise one is made")
    ap.add_argument("--docs", type=pathlib.Path,
                    default=pathlib.Path.home() / "pdfdrill-library",
                    help="the library root")
    ap.add_argument("--list", type=pathlib.Path,
                    help="JSON {key: pdf path} naming the documents to check")
    args = ap.parse_args()

    tmp = None
    site = args.site
    if site is None:
        tmp = tempfile.mkdtemp(prefix="publishcheck-")
        site = pathlib.Path(tmp) / "site"
        r = subprocess.run(["git", "clone", "-q", "--depth", "1",
                            SITE_URL, str(site)])
        if r.returncode:
            print("CANNOT CHECK: the site would not clone (rc=%d)" % r.returncode)
            return 2
    reports = site / "reports"
    if not reports.is_dir():
        print("CANNOT CHECK: %s has no reports/ directory" % site)
        return 2

    if args.list and args.list.is_file():
        docs = {k: pathlib.Path(v).parent
                for k, v in json.loads(args.list.read_text()).items() if v}
    else:
        docs = {d.name: d for d in reports.iterdir() if d.is_dir()}
        docs = {k: (args.docs / k) for k in docs}

    same = diff = missing_local = missing_site = 0
    lines = []
    for key in sorted(docs):
        local = sha(docs[key] / "report.pdf")
        remote = sha(reports / key / "report.pdf")
        if remote is None:
            missing_site += 1; lines.append(("NOT PUBLISHED", key, "")); continue
        if local is None:
            missing_local += 1; lines.append(("NO LOCAL BUILD", key, "")); continue
        if local == remote:
            same += 1
        else:
            diff += 1
            lines.append(("STALE ON SITE", key,
                          "site %s, local %s" % (remote[:12], local[:12])))
    print("publishcheck — %d documents" % len(docs))
    print("  published and identical : %d" % same)
    print("  published but STALE     : %d" % diff)
    print("  not published           : %d" % missing_site)
    print("  no local build          : %d" % missing_local)
    for state, key, why in lines:
        print("  %-15s %-40s %s" % (state, key[:40], why))
    ok = (diff == 0 and missing_site == 0 and missing_local == 0)
    print()
    print("RESULT: %s" % ("every document on the site is the build on disk"
                          if ok else "THE SITE IS NOT UP TO DATE"))
    if tmp:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
