#!/usr/bin/env python3
"""621 — did the site actually get the new reports?

A check that answers ONE question with evidence: is what is published the
same artefact as what is on disk here, per document. It used to compare only
`report.pdf`; the redrawn surface (gate.py, spec 2026-09-06) publishes FIVE
files per document — the four evidence PDFs and residuals.pdf — so this now
hashes every one of `gate.PUBLISHED_FILES` that exists locally and compares
each against the site.

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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
from pdfdrill.reports import gate  # noqa: E402 — path set up above

SITE_URL = "https://github.com/PDFDRILL/PDFDRILL.github.io.git"


def sha(p: pathlib.Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def compare_document(local_dir: pathlib.Path, remote_dir: pathlib.Path,
                     filenames=gate.PUBLISHED_FILES) -> list[tuple[str, str, str]]:
    """(filename, status, detail) for every FILE PRESENT LOCALLY.

    A file absent locally is not this document's build and is not compared —
    there is nothing on disk here to check the site against. status is one of
    "same", "stale" (both sides have it, bytes differ) or "not_published"
    (the site lacks a file this build has). Pure — no network, no git — so it
    can be unit tested directly.
    """
    results = []
    for fname in filenames:
        # 634 — the site carries a Ghostscript /ebook DERIVATIVE of each file
        # (the originals total 947 MB across 20 documents, six formula files
        # between 66 and 94 MB; GitHub Pages caps a site near 1 GB). The
        # derivative lives beside the original under <doc>/published/ and IS
        # the build the site must match; the original is compared only when
        # no derivative exists.
        derived = local_dir / "published" / fname
        local = sha(derived) if derived.is_file() else sha(local_dir / fname)
        if local is None:
            continue
        remote = sha(remote_dir / fname)
        if remote is None:
            results.append((fname, "not_published", ""))
        elif local == remote:
            results.append((fname, "same", ""))
        else:
            results.append((fname, "stale",
                           "site %s, local %s" % (remote[:12], local[:12])))
    return results


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
        local_present = [f for f in gate.PUBLISHED_FILES
                         if sha(docs[key] / f) is not None]
        if not local_present:
            missing_local += 1; lines.append(("NO LOCAL BUILD", key, "")); continue
        results = compare_document(docs[key], reports / key)
        bad = [r for r in results if r[1] != "same"]
        if not bad:
            same += 1
            continue
        if any(status == "not_published" for _, status, _ in bad):
            missing_site += 1
        else:
            diff += 1
        for fname, status, detail in bad:
            label = "NOT PUBLISHED" if status == "not_published" else "STALE ON SITE"
            lines.append((label, "%s/%s" % (key, fname), detail))
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
