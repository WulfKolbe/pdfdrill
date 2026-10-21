# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Pages as independent work units: chunk, run in parallel, assemble."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

from . import bboxlayout, continuation, mathpix, pageimage, refine as refining, warmup

READERS = {"bbox": bboxlayout.read_pages, "tsv": bboxlayout.read_pages_tsv,
           "text": warmup.read_pages, "glyphs": None}
GEOMETRY_READERS = ("bbox", "tsv", "glyphs")
#: the warm-up a refined reading starts from: its own glyphs (the lines,
#: blocks and words pdftotext gave, built from the content stream; better
#: on the corpus and the twins, bench/README.md "Without pdftotext"). A
#: reading without the refinement stays with pdftotext -tsv: fast.
DEFAULT_READER = "glyphs"


class RangeError(ValueError):
    pass


class OverwriteError(RuntimeError):
    pass


def _refuse_foreign(lines_json: Path, doc_id: str) -> None:
    """A lines.json from MathPix cost money and cannot be rebuilt for free."""
    if not lines_json.exists():
        return
    try:
        ours = mathpix.written_by_us(
            json.loads(lines_json.read_text("utf-8")), doc_id)
    except (OSError, ValueError):
        ours = False
    if not ours:
        raise OverwriteError(
            f"{lines_json} exists and was not written by pdf2mmd2; it is "
            f"left untouched. Choose another --out folder.")


def page_count(pdf: Path) -> int:
    proc = subprocess.run(["pdfinfo", str(pdf)], capture_output=True)
    m = re.search(rb"^Pages:\s+(\d+)", proc.stdout, re.M)
    if proc.returncode != 0 or not m:
        msg = proc.stderr.decode("utf-8", "replace").strip()
        raise warmup.WarmupError(f"pdfinfo failed on {Path(pdf).name}: {msg}")
    return int(m.group(1))


def chunks(first: int, last: int, jobs: int) -> list[tuple[int, int]]:
    n = last - first + 1
    k = max(1, min(jobs, n))
    size, extra = divmod(n, k)
    out, start = [], first
    for i in range(k):
        end = start + size + (1 if i < extra else 0) - 1
        out.append((start, end))
        start = end + 1
    return out


def _write_json(path: Path, obj, pretty_depth: int | None = None) -> None:
    tmp = path.with_name(path.name + ".tmp")
    text = (json.dumps(obj, ensure_ascii=False) if pretty_depth is None
            else mathpix.pretty(obj, pretty_depth))
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def run(pdf: Path, out_dir: Path, first: int | None = None,
        last: int | None = None, jobs: int | None = None,
        images: bool = False, reader: str | None = None,
        refine: bool = False, pretty: bool = False) -> dict:
    reader = reader or (DEFAULT_READER if refine else "tsv")
    if reader not in READERS:
        raise ValueError(f"unknown warm-up reader {reader!r}; "
                         f"choose from {sorted(READERS)}")
    if refine:
        if reader not in GEOMETRY_READERS:
            raise ValueError("the refinement pass needs a reading with "
                             "geometry (reader 'glyphs', 'tsv' or 'bbox')")
        refining.require_pdfminer()
    if reader == "glyphs":
        refining.require_pdfminer()
    read_pages = READERS[reader]
    pdf, out_dir = Path(pdf), Path(out_dir)
    total = page_count(pdf)
    first = 1 if first is None else first
    last = total if last is None else last
    if not 1 <= first <= last <= total:
        raise RangeError(f"pages {first}-{last} requested, but {pdf.name} "
                         f"has {total} page(s)")
    jobs = jobs or os.cpu_count() or 1
    doc_id = pdf.stem
    page_dir = out_dir / f"{doc_id}.lines"
    lines_json = out_dir / f"{doc_id}.lines.json"
    _refuse_foreign(lines_json, doc_id)
    page_dir.mkdir(parents=True, exist_ok=True)
    for stale in page_dir.glob("page-[0-9][0-9][0-9][0-9].json"):
        stale.unlink()

    def warm(span: tuple[int, int]) -> int:
        n = 0
        for pg in read_pages(pdf, span[0], span[1], doc_id):
            if not refine:      # the refinement marks after its modules
                continuation.mark(pg)
            _write_json(page_dir / f"page-{pg['page']:04d}.json", pg)
            n += len(pg["lines"])
        return n

    seconds = {"warmup": 0.0, "refine": 0.0, "images": 0.0, "assemble": 0.0}
    t = time.perf_counter()
    if read_pages is not None:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            n_lines = sum(pool.map(warm, chunks(first, last, jobs)))
    elif not refine:
        # the glyphs are read in processes: pdfminer holds the GIL
        spans = chunks(first, last, jobs)
        with ProcessPoolExecutor(max_workers=len(spans)) as pool:
            n_lines = sum(pool.map(
                refining.build_range, [str(pdf)] * len(spans),
                [str(page_dir)] * len(spans), [a for a, _ in spans],
                [b for _, b in spans]))
    else:
        n_lines = 0     # the refinement makes the pages
    seconds["warmup"] = time.perf_counter() - t

    refined = None
    if refine:
        # Processes, not threads: pdfminer is Python and holds the GIL.
        t = time.perf_counter()
        spans = chunks(first, last, jobs)
        with ProcessPoolExecutor(max_workers=len(spans)) as pool:
            per_page = [st for part in pool.map(
                refining.refine_range, [str(pdf)] * len(spans),
                [str(page_dir)] * len(spans), [a for a, _ in spans],
                [b for _, b in spans],
                [read_pages is None] * len(spans)) for st in part]
        seconds["refine"] = time.perf_counter() - t
        refined = {
            "pages": len(per_page),
            "glyphs": sum(st["glyphs"] for st in per_page),
            "rules": sum(st["rules"] for st in per_page),
            "unassigned": sum(st["unassigned"] for st in per_page),
            "agreement_min": min((st["agreement"] for st in per_page),
                                 default=1.0),
            "errors": [f"page {st['page']}: {st['error']}"
                       for st in per_page if st["error"]],
        }

    if images:
        t = time.perf_counter()
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            list(pool.map(
                lambda p: pageimage.render_page(
                    pdf, p,
                    out_dir / "pages" / f"{mathpix.image_id(doc_id, p)}.jpg"),
                range(first, last + 1)))
        seconds["images"] = time.perf_counter() - t

    t = time.perf_counter()
    pages = [json.loads((page_dir / f"page-{p:04d}.json").read_text("utf-8"))
             for p in range(first, last + 1)]
    if pretty:
        # after every pass, so the passes keep reading compact page files
        for pg in pages:
            _write_json(page_dir / f"page-{pg['page']:04d}.json", pg, 2)
    if read_pages is None and refine:
        n_lines = sum(len(pg["lines"]) for pg in pages)   # no warm-up ran
    _write_json(lines_json, {"pages": pages}, 4 if pretty else None)
    seconds["assemble"] = time.perf_counter() - t
    result = {"pages": len(pages), "lines": n_lines, "seconds": seconds,
              "lines_json": lines_json}
    if refined is not None:
        result["refine"] = refined
        result["refine_pages"] = per_page
    return result
