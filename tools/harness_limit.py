#!/usr/bin/env python3
"""032 — one bound, one announcement, for every multi-document harness.

A harness that iterates documents must be TOLD how many to take, and must say
what it is about to do before it does it. Six harnesses in tools/ could each
process the whole corpus from a bare invocation (out/031.txt); two of them
advertised a `--limit` whose default disabled it, which is worse than none —
it reads like a bound and is not one.

`--limit` is therefore REQUIRED, with 0 meaning "all" so the unbounded run is
still reachable but must be ASKED FOR. And `announce()` prints the planned
document and page count before the first document is touched, so the operator
sees the size of the thing they started while it is still cheap to stop.

Every tools/ script is run as a script, so its own directory is sys.path[0]
and `from harness_limit import ...` resolves without any path handling.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def add_limit(ap, what: str = "documents") -> None:
    """Register the REQUIRED --limit N. 0 = all, asked for explicitly."""
    ap.add_argument("--limit", type=int, required=True, metavar="N",
                    help=f"how many {what} to process; 0 = all of them "
                         f"(required — an unbounded run must be asked for)")


def apply_limit(items, limit: int):
    """The first `limit` items, or all of them when limit is 0."""
    return list(items) if not limit else list(items)[:max(0, limit)]


def _pages_of(doc) -> int | None:
    """Page count from the cheapest source that knows it: the sidecar, then
    the lines.json, then pdfinfo. None when nothing local can say."""
    p = Path(doc)
    stem = p.name[:-4] if p.name.lower().endswith(".pdf") else p.name
    base = p if p.is_dir() else p.parent
    for cand in (base / f"{stem}.drill.json", base / f"{p.stem}.drill.json"):
        try:
            ev = json.loads(cand.read_text(errors="replace")).get("evidence", {})
            if isinstance(ev.get("pages"), int):
                return ev["pages"]
        except Exception:
            pass
    for cand in (base / f"{stem}.lines.json", base / f"{p.stem}.lines.json"):
        try:
            return len(json.loads(cand.read_text(errors="replace"))["pages"])
        except Exception:
            pass
    if p.is_file() and p.suffix.lower() == ".pdf":
        try:
            out = subprocess.run(["pdfinfo", str(p)], capture_output=True,
                                 text=True, timeout=30).stdout
            for line in out.splitlines():
                if line.startswith("Pages:"):
                    return int(line.split()[1])
        except Exception:
            pass
    return None


def announce(harness: str, docs, *, count_pages: bool = True,
             stream=None) -> tuple[int, int, int]:
    """Print the plan BEFORE the work starts. Returns (docs, pages, unknown).

    Page counts come from local metadata only — a document that has not been
    fetched yet reports UNKNOWN rather than a guessed number, because a plan
    that invents its own size is worse than one that admits what it cannot
    see."""
    # resolved at CALL time: a `stream=sys.stderr` default binds the original
    # stream at import and ignores any later redirection — invisible in
    # production, and it made the announcement untestable
    stream = sys.stderr if stream is None else stream
    docs = list(docs)
    pages = unknown = 0
    if count_pages:
        for d in docs:
            n = _pages_of(d)
            if n is None:
                unknown += 1
            else:
                pages += n
    line = f"[{harness}] planned: {len(docs)} document(s)"
    if count_pages:
        line += f", {pages} page(s)"
        if unknown:
            line += f" (+{unknown} document(s) whose page count is not "
            line += "knowable locally yet)"
    print(line, file=stream, flush=True)
    return len(docs), pages, unknown
