#!/usr/bin/env python3
"""corpus_pages — render a representative page sample across the WHOLE library.

The problem this exists for: the library had 1008 rendered pages spread over 35
of 3273 modelled documents. Page variety was fine; document variety was 35. Any
rate measured on that corpus — residual glyphs, math capture, region coverage —
describes the handful of documents that happened to be rendered in full, not the
library, and one 178-page thesis can carry the whole number on its own.

So this spends the rendering budget on BREADTH: a few pages from every document
instead of every page from a few. It is additive and resumable — it only adds
`p{N}.png` files that are missing, never rewrites or deletes, and a document
already rendered in full is skipped because its pages are a superset of any
sample.

    python3 tools/corpus_pages.py --stats            # what the corpus is now
    python3 tools/corpus_pages.py --dry-run          # what it would render
    python3 tools/corpus_pages.py --per-doc 3 --jobs 8

Pages land in `<doc>/inspect/pages/p{N}.png`, the naming `pdfdrill inspect`
already reads, so the sample doubles as inspector input rather than a private
pile of images.
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import json
import math
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

DEFAULT_LIBRARY = Path.home() / "pdfdrill-library"
MANIFEST_NAME = "corpus-pages.json"

_PAGE_RE = re.compile(r"^p(\d+)\.png$")
_NUM_PAGES_RE = re.compile(rb'"num_pages"\s*:\s*(\d+)')
_HEAD_BYTES = 65536


# ---------------------------------------------------------------------------
# Pure selection logic
# ---------------------------------------------------------------------------

def sample_pages(n_pages: int, k: int) -> list[int]:
    """`k` pages spread evenly through a document of `n_pages`.

    Sample i sits at the CENTRE of the i-th of k equal slices, which has two
    properties worth keeping: the pages are spread (never k consecutive
    front-matter pages) and page 1 falls out of the sample for any document
    long enough for a cover to be unrepresentative. Deterministic, so a
    measurement repeated next week reads the same pages.
    """
    if n_pages <= 0 or k <= 0:
        return []
    if n_pages <= k:
        return list(range(1, n_pages + 1))
    out = []
    for i in range(k):
        # floor(x + 0.5) — half-UP. Python's round() is half-to-even, which
        # would pull every .5 midpoint of an even-length slice down a page.
        p = math.floor((i + 0.5) * n_pages / k + 0.5)
        out.append(max(1, min(n_pages, p)))
    return sorted(set(out))


def existing_pages(pages_dir: Path) -> set[int]:
    """Page numbers already rendered, from the `p{N}.png` names only.

    `page-NNNN.png` is the SAME image hardlinked under the rasterizer's own
    naming — counting both is how the corpus got reported at twice its size.
    """
    try:
        names = os.listdir(pages_dir)
    except OSError:
        return set()
    out = set()
    for name in names:
        m = _PAGE_RE.match(name)
        if m:
            out.add(int(m.group(1)))
    return out


def missing_pages(wanted: list[int], have: set[int]) -> list[int]:
    return [p for p in wanted if p not in have]


def page_count_from_head(head: bytes) -> int | None:
    """`num_pages` out of a model's meta header, or None.

    Scoped to the meta block on purpose: a `num_pages` occurring inside some
    object's text further down the file is not the document's page count, and
    a wrong count samples pages that do not exist.
    """
    i = head.find(b'"meta"')
    if i < 0:
        return None
    ends = [x for x in (head.find(b'"streams"', i), head.find(b'"objects"', i)) if x >= 0]
    end = min(ends) if ends else len(head)
    m = _NUM_PAGES_RE.search(head, i, end)
    if not m:
        return None
    n = int(m.group(1))
    return n or None


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

@dataclass
class DocPlan:
    bibkey: str
    pdf: Path
    pages_dir: Path
    pages: list[int]            # the ones still to render
    page_count: int
    sample: list[int] = field(default_factory=list)   # the full intended sample


def _page_count(pdf: Path, model: Path) -> int | None:
    """Model header first (a 64 KB read), the PDF itself when it is silent."""
    try:
        with open(model, "rb") as fh:
            n = page_count_from_head(fh.read(_HEAD_BYTES))
    except OSError:
        n = None
    return n or _page_count_from_pdf(pdf)


def _page_count_from_pdf(pdf: Path) -> int | None:
    """Ask the PDF itself when the model header did not say. ~10 ms."""
    try:
        out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True,
                             text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"^Pages:\s+(\d+)", out, re.M)
    return int(m.group(1)) if m and int(m.group(1)) else None


def plan_library(root: Path, *, per_doc: int = 3, limit: int | None = None,
                 with_skipped: bool = False):
    """What still has to be rendered, document by document. Nothing is written."""
    plan: list[DocPlan] = []
    skipped: list[tuple[str, str]] = []
    for doc in sorted(p for p in Path(root).iterdir() if p.is_dir()):
        pdfs = sorted(doc.glob("*.pdf"))
        if not pdfs:
            skipped.append((doc.name, "no pdf"))
            continue
        model = doc / "model.docmodel.json"
        if not model.exists():
            skipped.append((doc.name, "no model"))
            continue
        n = _page_count(pdfs[0], model)
        if not n:
            skipped.append((doc.name, "unknown page count"))
            continue
        want = sample_pages(n, per_doc)
        pages_dir = doc / "inspect" / "pages"
        todo = missing_pages(want, existing_pages(pages_dir))
        if not todo:
            continue
        plan.append(DocPlan(bibkey=doc.name, pdf=pdfs[0], pages_dir=pages_dir,
                            pages=todo, page_count=n, sample=want))
        if limit is not None and len(plan) >= limit:
            break
    return (plan, skipped) if with_skipped else plan


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render(doc: DocPlan, *, dpi: int) -> dict:
    """Render one document's missing pages. Never raises — a bad PDF must not
    end a 3000-document run."""
    from pdfdrill import pdf_reading
    t0 = time.time()
    rec = {"bibkey": doc.bibkey, "page_count": doc.page_count,
           "sample": doc.sample, "rendered": [], "bytes": 0}
    try:
        doc.pages_dir.mkdir(parents=True, exist_ok=True)
        imgs = pdf_reading.rasterize(doc.pdf, doc.pages_dir, pages=doc.pages, dpi=dpi)
    except Exception as exc:                       # gs missing, broken PDF, OOM…
        rec["error"] = f"{type(exc).__name__}: {exc}"[:200]
        rec["seconds"] = round(time.time() - t0, 2)
        return rec
    for img in imgs:
        m = re.search(r"page-(\d+)\.png$", img.name)
        if not m:
            continue
        n = int(m.group(1))
        target = doc.pages_dir / f"p{n}.png"
        if not target.exists():
            try:
                os.link(img, target)               # hardlink: no second copy
            except OSError:
                import shutil
                shutil.copyfile(img, target)
        rec["rendered"].append(n)
        try:
            rec["bytes"] += img.stat().st_size
        except OSError:
            pass
    rec["rendered"].sort()
    if not rec["rendered"]:
        # Belt and braces: the rasterizer now raises on an empty render, but a
        # document counted "ok" with zero pages is the exact shape of failure
        # this corpus was built to stop mistaking for coverage.
        rec["error"] = "no pages produced"
    rec["seconds"] = round(time.time() - t0, 2)
    return rec


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def corpus_stats(root: Path) -> dict:
    """The corpus as it stands. `pages` counts IMAGES, not directory entries."""
    docs = with_pages = pages = 0
    per_doc: list[int] = []
    for doc in sorted(p for p in Path(root).iterdir() if p.is_dir()):
        if not (doc / "model.docmodel.json").exists():
            continue
        docs += 1
        have = existing_pages(doc / "inspect" / "pages")
        if have:
            with_pages += 1
            pages += len(have)
            per_doc.append(len(have))
    per_doc.sort()
    return {
        "documents": docs,
        "documents_with_pages": with_pages,
        "pages": pages,
        "median_pages_per_rendered_doc": per_doc[len(per_doc) // 2] if per_doc else 0,
        "max_pages_in_one_doc": per_doc[-1] if per_doc else 0,
    }


def _fmt_stats(st: dict) -> str:
    docs, wp = st["documents"], st["documents_with_pages"]
    share = (100.0 * wp / docs) if docs else 0.0
    return (f"{st['pages']} pages across {wp}/{docs} modelled documents "
            f"({share:.1f}% covered); median {st['median_pages_per_rendered_doc']} "
            f"pages/doc, largest {st['max_pages_in_one_doc']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    ap.add_argument("--per-doc", type=int, default=3, help="pages sampled per document")
    ap.add_argument("--dpi", type=int, default=400, help="render DPI (gs floor is 400)")
    ap.add_argument("--jobs", type=int, default=min(8, (os.cpu_count() or 4)))
    ap.add_argument("--limit", type=int, help="only the first N documents needing work")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stats", action="store_true", help="report the corpus and exit")
    ap.add_argument("--manifest", type=Path, help=f"default <library>/{MANIFEST_NAME}")
    args = ap.parse_args(argv)

    root = args.library
    if not root.is_dir():
        print(f"no such library: {root}", file=sys.stderr)
        return 2

    if args.stats:
        print(_fmt_stats(corpus_stats(root)))
        return 0

    plan, skipped = plan_library(root, per_doc=args.per_doc, limit=args.limit,
                                 with_skipped=True)
    n_pages = sum(len(p.pages) for p in plan)
    print(f"before: {_fmt_stats(corpus_stats(root))}")
    print(f"plan:   {len(plan)} documents, {n_pages} pages at {args.dpi} DPI")
    if skipped:
        reasons: dict[str, int] = {}
        for _name, why in skipped:
            reasons[why] = reasons.get(why, 0) + 1
        print("skip:   " + ", ".join(f"{v} {k}" for k, v in sorted(reasons.items())))
    if args.dry_run:
        for p in plan[:10]:
            print(f"  {p.bibkey[:60]:<60} {p.page_count:>5}p -> {p.pages}")
        if len(plan) > 10:
            print(f"  … {len(plan) - 10} more")
        return 0
    if not plan:
        return 0

    t0 = time.time()
    results: list[dict] = []
    done = 0
    with futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        futs = {ex.submit(render, p, dpi=args.dpi): p for p in plan}
        for fut in futures.as_completed(futs):
            results.append(fut.result())
            done += 1
            if done % 100 == 0 or done == len(plan):
                ok = sum(1 for r in results if not r.get("error"))
                pg = sum(len(r["rendered"]) for r in results)
                print(f"  {done}/{len(plan)} docs · {pg} pages · {ok} ok · "
                      f"{time.time() - t0:.0f}s", flush=True)

    errs = [r for r in results if r.get("error")]
    manifest = {
        "generated_by": "tools/corpus_pages.py",
        "dpi": args.dpi,
        "per_doc": args.per_doc,
        "seconds": round(time.time() - t0, 1),
        "documents": sorted(results, key=lambda r: r["bibkey"]),
        "stats": corpus_stats(root),
    }
    mpath = args.manifest or (root / MANIFEST_NAME)
    with open(mpath, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)

    mb = sum(r["bytes"] for r in results) / 1048576
    print(f"after:  {_fmt_stats(manifest['stats'])}")
    print(f"wrote {mb:.0f} MB in {manifest['seconds']:.0f}s · manifest {mpath}")
    if errs:
        print(f"{len(errs)} document(s) failed:")
        for r in errs[:10]:
            print(f"  {r['bibkey'][:60]:<60} {r['error']}")
        if len(errs) > 10:
            print(f"  … {len(errs) - 10} more (see the manifest)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
