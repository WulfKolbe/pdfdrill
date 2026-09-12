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

677 — TWO DEFECTS THAT MADE THIS TOOL WRONG IN BOTH DIRECTIONS AT ONCE, in
the tool `docs/HANDOVER.md` tells a reader to run before believing anything
else. Both are rule 22: a correct answer to a question that had stopped
being the right one.

**It resolved the library folder as `<library>/<site slug>`.** Task 462
renamed nine documents' bibkeys WITHOUT renaming their folders — the site
slug `voloshin-hypergraph` against the folder `Introduction to Graph and
Hypergraph Theory (Vitaly I. Voloshin) (Z-Library)` — so for every
Z-Library book the path did not exist, the document was reported "NO LOCAL
BUILD", and a verdict was printed anyway. Eight of twenty documents, every
one a book, had never been checked. This is the SAME defect class as the
2026-09-11 marks run, which resolved inkdrill's key by site slug and
silently found nothing for the same eight.

The fix uses the authority that already exists rather than a table:
`<bibkey>.tiddlers.json` is written beside every document and the bibkey IS
the site slug (`report_tex.resolve_bibkey`: the model's `meta.bibkey` is
what `renamefolder` retargets and what every identifier is built from).
`resolve_folders` reads it from a directory listing — no model load, no
hardcoded alias map, and a slug it cannot resolve is NAMED rather than
counted as an absent build.

**It compared the site against a file the publish does not use.** 634's
`published/` Ghostscript /ebook derivative existed because the originals
totalled 947 MB. 655's size budget made the originals fit, the publish went
back to copying them, and the derivatives were left on disk — stale. This
tool still preferred `published/<f>` whenever it existed, so it compared
the site against a file nothing had published in weeks and reported twelve
up-to-date documents as STALE. Measured 2026-09-12 on voloshin-hypergraph:
all five site files are byte-identical to the ORIGINALS and differ from all
five derivatives.

The fix does not swap one silent preference for the other. Both candidates
are hashed, the status SAYS WHICH ONE MATCHED, and a derivative that
differs from its original is reported as a stale leftover in its own right
— so this can never again be quietly measuring the wrong file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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
    there is nothing on disk here to check the site against.

    status is one of:
      "same"          — the site matches a local candidate; the detail says
                        WHICH ("original" or "published/ derivative"), because
                        a check that does not know which file it matched
                        cannot tell a correct publish from a coincidence.
      "stale"         — both sides have it and the site matches NEITHER
                        candidate; the detail carries all three hashes.
      "not_published" — the site lacks a file this build has.

    A `published/` derivative that differs from its original is additionally
    reported as ("<fname> (published/ leftover)", "stale_derivative", …) —
    677: those derivatives are from 634's /ebook era, the publish stopped
    using them once 655's budget made the originals fit, and leaving them to
    rot is what made this tool compare the wrong file for weeks.

    Pure — no network, no git — so it can be unit tested directly.
    """
    # 677 fix round 2 — COMPARE WHAT THE SITE ACTUALLY CARRIES, not only the
    # five names `gate.PUBLISHED_FILES` lists. The site carries twelve kinds
    # per document (the four evidence PDFs, residuals.pdf, report.pdf,
    # formula-report.html, inspect.html, tables.html, <slug>.md,
    # report.build.json, report.ink.json); this compared five, so seven were
    # never checked. HANDOVER-RULES rule 22 already named that tuple as a
    # blind spot — "is this the complete list of files this document actually
    # publishes now" — and it paid out twice in one day: a stale
    # `formula-report.html` (a copy of `evidence-formula.html`, which
    # `evidence --pdf` does not rebuild at all) would have shipped beside four
    # corrected PDFs, unnoticed.
    #
    # The union, not a longer tuple: every name in `filenames` that exists
    # locally, PLUS every file the site already has for this document. A file
    # on the site that nobody put in a list is exactly the case that needs an
    # answer, and now it gets one.
    names = list(filenames)
    try:
        names += sorted(f.name for f in remote_dir.iterdir() if f.is_file())
    except OSError:
        pass
    seen = set()
    filenames = [n for n in names if not (n in seen or seen.add(n))]

    results = []
    for fname in filenames:
        original = sha(local_dir / fname)
        derived = sha(local_dir / "published" / fname)
        if original is None and derived is None:
            continue
        remote = sha(remote_dir / fname)
        if remote is None:
            results.append((fname, "not_published", ""))
        elif remote == original:
            results.append((fname, "same", "original"))
        elif remote == derived:
            results.append((fname, "same", "published/ derivative"))
        else:
            results.append((fname, "stale",
                            "site %s, original %s, derivative %s"
                            % (remote[:12], (original or "-")[:12],
                               (derived or "-")[:12])))
        if original and derived and original != derived:
            results.append(("%s (published/ leftover)" % fname,
                            "stale_derivative",
                            "derivative %s differs from original %s"
                            % (derived[:12], original[:12])))
    return results


def resolve_folders(library: pathlib.Path, slugs) -> tuple[dict, list]:
    """({site slug: library folder}, [slugs that resolved to nothing]).

    The library folder is NOT the site slug for any Z-Library book (462
    renamed bibkeys without renaming folders). `<bibkey>.tiddlers.json` sits
    beside every document and its stem IS the slug, so one directory listing
    per folder resolves the mapping with no model load and no alias table.
    A folder named for the slug is still accepted, so an arXiv id with no
    tiddlers file built yet resolves as it always did.
    """
    by_slug = {}
    try:
        folders = [d for d in library.iterdir() if d.is_dir()]
    except OSError:
        folders = []
    for d in folders:
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for n in names:
            if n.endswith(".tiddlers.json"):
                by_slug.setdefault(n[:-len(".tiddlers.json")], d)
    out, unresolved = {}, []
    for slug in slugs:
        if slug in by_slug:
            out[slug] = by_slug[slug]
        elif (library / slug).is_dir():
            out[slug] = library / slug
        else:
            unresolved.append(slug)
    return out, unresolved


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
        unresolved = []
    else:
        # 677 — resolve the library FOLDER, which is not the site slug for any
        # Z-Library book. A slug that resolves to nothing is named, not
        # silently reported as an absent build.
        slugs = sorted(d.name for d in reports.iterdir() if d.is_dir())
        docs, unresolved = resolve_folders(args.docs, slugs)

    same = diff = missing_local = missing_site = 0
    leftovers = 0
    lines = []
    for slug in unresolved:
        missing_local += 1
        lines.append(("UNRESOLVED", slug,
                      "no <slug>.tiddlers.json and no %s/ in the library"
                      % slug))
    for key in sorted(docs):
        local_present = [f for f in gate.PUBLISHED_FILES
                         if sha(docs[key] / f) is not None]
        if not local_present:
            missing_local += 1; lines.append(("NO LOCAL BUILD", key, "")); continue
        results = compare_document(docs[key], reports / key)
        # a stale `published/` leftover is a hygiene finding, not a publish
        # failure: it does not mean the site is wrong.
        stale_deriv = [r for r in results if r[1] == "stale_derivative"]
        leftovers += len(stale_deriv)
        bad = [r for r in results if r[1] not in ("same", "stale_derivative")]
        for fname, _status, detail in stale_deriv:
            lines.append(("LEFTOVER", "%s/%s" % (key, fname), detail))
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
    print("publishcheck — %d documents" % (len(docs) + len(unresolved)))
    print("  published and identical : %d" % same)
    print("  published but STALE     : %d" % diff)
    print("  not published           : %d" % missing_site)
    print("  no local build          : %d" % missing_local)
    if leftovers:
        print("  stale published/ files  : %d (not a publish failure; "
              "delete them — 677)" % leftovers)
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
