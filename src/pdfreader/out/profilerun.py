#!/usr/bin/env python3
"""profilerun — the page profile over a folder of PDFs, for TRIAGE.

781o — the answer to "what is in this corpus?" when counting cannot give
one. The IUST fuzzing corpus is 6,141 PDFs of which most are a single page
of deliberate nonsense and a few are 132-page manuals; an average over
that population describes nothing that exists in it.

What this prints instead is, per document, WHICH PAGES CARRY WHAT -- and
the one number that matters for cost:

    pages a paid pass would bill   vs   pages that carry anything

    python3 profilerun.py ~/some/folder
    python3 profilerun.py ~/some/folder --json out.json --limit 200
"""
import argparse
import glob
import json
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _TO
from pathlib import Path

CODE = Path(os.environ.get("PDF2MMD_CODE", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(CODE))

#: A hostile PDF is the point of a fuzzing corpus, so a reader that dies
#: on one must not take the run with it. Every failure is a RESULT.
TIMEOUT = 180


def one(path: str) -> dict:
    row = {"file": os.path.basename(path)}
    try:
        import docmodel_six as dm
        import pageprofile as pr
        pages = dm.build(path)
        row["pages"] = len(pages)
        where = pr.document_profile(pages)
        row["props"] = {k: len(v) for k, v in where.items()}
        row["carrying"] = len({n for ps in where.values() for n in ps})
        row["ok"] = True
    except Exception as exc:                                # noqa: BLE001
        row["ok"] = False
        row["error"] = type(exc).__name__ + ": " + str(exc)[:120]
        row["where"] = traceback.format_exc().strip().split("\n")[-2][:120]
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--json", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=4)
    A = ap.parse_args()
    files = sorted(glob.glob(os.path.join(A.folder, "**", "*.pdf"), recursive=True))
    if A.limit:
        files = files[:A.limit]
    if not files:
        print("no PDFs under %s" % A.folder)
        return
    res = []
    with ThreadPoolExecutor(max_workers=A.jobs) as ex:
        futs = {ex.submit(one, f): f for f in files}
        for i, fu in enumerate(futs, 1):
            try:
                res.append(fu.result(timeout=TIMEOUT))
            except _TO:
                res.append({"file": os.path.basename(futs[fu]), "ok": False,
                            "error": "timeout after %ds" % TIMEOUT})
            if i % 200 == 0:
                print("  %d/%d" % (i, len(files)), file=sys.stderr, flush=True)
    if A.json:
        Path(A.json).write_text(json.dumps(res, indent=1))

    ok = [r for r in res if r.get("ok")]
    bad = [r for r in res if not r.get("ok")]
    print("documents            %d" % len(res))
    print("  read               %d" % len(ok))
    print("  FAILED             %d" % len(bad))
    import collections
    if bad:
        c = collections.Counter(r.get("error", "?").split(":")[0] for r in bad)
        for k, v in c.most_common(8):
            print("     %-34s %d" % (k, v))
    if not ok:
        return
    pages = sum(r["pages"] for r in ok)
    carry = sum(r["carrying"] for r in ok)
    print("\npages                %d" % pages)
    print("  carrying anything  %d  (%.0f%%)" % (carry, 100 * carry / max(pages, 1)))
    print("  a paid pass bills  %d" % pages)
    prop = collections.Counter()
    docs = collections.Counter()
    for r in ok:
        for k, n in r["props"].items():
            prop[k] += n
            docs[k] += 1
    print("\nPROPERTY           pages   documents")
    for k, v in prop.most_common():
        print("  %-16s %6d   %6d" % (k, v, docs[k]))


if __name__ == "__main__":
    main()
