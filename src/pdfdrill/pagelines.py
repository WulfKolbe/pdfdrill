"""896 — a reading delivered as one file per page.

`~/pdf2mmd2` reads a born-digital PDF and writes a MathPix-shaped reading, but
it writes it TWICE: once as the whole-document `<stem>.lines.json`, and once as
`<stem>.lines/page-NNNN.json`, one file per page, so that two readings of the
same page sit side by side in a file list. The per-page file is not a different
format — it is exactly one element of `pages[]`, verified key for key:

    page keys      identical (image_id, languages_detected, lines, page,
                              page_height, page_width)
    line keys      a SUBSET — 14 of MathPix's 22 on 1306.1660 page 3; the 8
                   absent ones are table structure and the parent/child links
                   (see `missing_fields` below, which names them for the
                   producer instead of guessing a value here)

So the right change is not a new command: it is for the ONE place that already
locates a document's reading to accept the second spelling. Everything
downstream — `model`, `inspect`, `md`, `eqreport` — then reads an ordinary
`lines.json` and is untouched.

WHAT THIS REFUSES TO DO:

  * It never replaces a `<stem>.lines.json` it did not write. pdf2mmd2 makes
    exactly the same refusal in the other direction ("replaced only if pdf2mmd2
    wrote it; any other one — a MathPix export, a pdfdrill reading — is left
    untouched"). A paid MathPix reading sitting beside a dropped-in page folder
    must survive, so a present reading simply wins and nothing is assembled.
  * It never fills a gap in the page numbering, and never trusts the number in
    a filename over the `page` field inside it. The label is not the key — a
    lesson this repo learned by diffing a document by `EQnnnn` and reporting
    25 of 37 rows changed when 30 of 36 were unchanged. Here the two are
    cross-checked and a disagreement is an error, because silently reordering
    a document's pages produces a reading that looks complete.
  * It never supplies a field the producer omitted. A missing field is reported
    BY NAME, with what reads it, so the correction happens in pdf2mmd2 where
    the information actually is. Inventing a `children_ids` here would make
    pdfdrill agree with itself about a structure nobody measured. The one thing
    it restates rather than invents is a `source` the pages already agree on,
    lifted to the top level so both readers of that key are right by
    construction (897).

`page-NNNN.mathpix.json` in the same folder is MathPix's own reading of that
page, written by pdf2mmd2's `mathpix-pages` script for side-by-side comparison.
It is a SECOND READER and is never folded in: one `lines.json` holding two
readers' lines would be a document no measurement could attribute.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

#: `page-0003.json` — and deliberately NOT `page-0003.mathpix.json`. A glob
#: cannot make that distinction; the anchored number can.
_PAGE_FILE = re.compile(r"^page-(\d+)\.json$")

#: the same, for the twin written by `pdf2mmd2-mathpix-pages`
_TWIN_FILE = re.compile(r"^page-(\d+)\.mathpix\.json$")


class PageLinesError(Exception):
    """The page folder cannot be read as one document."""


def lines_dir(pdf: Path) -> Path:
    """`<stem>.lines/` beside the PDF — the folder whose name is the reading's
    name with the page files in it."""
    name = pdf.name
    stem = name[:-4] if name.lower().endswith(".pdf") else name
    return pdf.parent / f"{stem}.lines"


def lines_json(pdf: Path) -> Path:
    """`<stem>.lines.json` — the same path `commands._lines_json_path` returns.
    Recomputed here rather than imported because `commands` imports half the
    package and this module is reached from the CLI's resolve step."""
    name = pdf.name
    stem = name[:-4] if name.lower().endswith(".pdf") else name
    return pdf.parent / f"{stem}.lines.json"


def page_files(d: Path) -> list[tuple[int, Path]]:
    """The `page-NNNN.json` files in `d`, as (number-from-the-filename, path),
    ordered by that number. The twins are excluded. [] if `d` is not a folder.

    Sorting is NUMERIC. `sorted(glob())` is lexicographic, which orders
    `page-10.json` before `page-9.json` — correct only while every number is
    zero-padded to the same width, which is a property of today's writer and
    not of the format.
    """
    try:
        if not d.is_dir():
            return []
        names = sorted(p.name for p in d.iterdir())
    except OSError:
        return []
    out: list[tuple[int, Path]] = []
    for n in names:
        m = _PAGE_FILE.match(n)
        if m:
            out.append((int(m.group(1)), d / n))
    out.sort(key=lambda t: t[0])
    return out


def twin_files(d: Path) -> list[tuple[int, Path]]:
    """The `page-NNNN.mathpix.json` twins — counted and named in the report so
    their presence is visible, never read into the assembled document."""
    try:
        if not d.is_dir():
            return []
        names = sorted(p.name for p in d.iterdir())
    except OSError:
        return []
    out = [(int(m.group(1)), d / n) for n in names
           if (m := _TWIN_FILE.match(n))]
    out.sort(key=lambda t: t[0])
    return out


def read_pages(files: list[tuple[int, Path]]) -> list[dict]:
    """Read each page file as one `pages[]` element, in the given order.

    Each file's own `page` field is checked against the number in its filename.
    They are two independent statements of the same fact and the format gives us
    both; when they disagree, one of them is wrong and we cannot tell which, so
    neither is used.
    """
    pages: list[dict] = []
    for num, path in files:
        try:
            pg = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise PageLinesError(f"{path.name}: {e}") from e
        if not isinstance(pg, dict):
            raise PageLinesError(
                f"{path.name}: a page file holds ONE pages[] element (an "
                f"object), not {type(pg).__name__}")
        said = pg.get("page")
        if said is not None and said != num:
            raise PageLinesError(
                f"{path.name} says page {said!r}. The filename and the `page` "
                f"field disagree, so the page order cannot be established "
                f"from either — fix the producer rather than picking one")
        if said is None:
            pg = dict(pg, page=num)       # the only value ever supplied, and
            # only because the ordering already proved it
        pages.append(pg)
    return pages


def gaps(files: list[tuple[int, Path]]) -> list[int]:
    """Page numbers absent from `first..last`. Reported, never filled: a
    document with page 7 missing is a reading to repair, not to renumber."""
    if not files:
        return []
    nums = {n for n, _ in files}
    return [n for n in range(min(nums), max(nums) + 1) if n not in nums]


def missing_fields(pages: list[dict]) -> dict[str, str]:
    """The fields pdfdrill READS that no line in this reading carries, each
    with what reads it — the statement the producer needs.

    The list is not hand-written: it is `docmodel.type_contract.CLAIMED_FIELDS`,
    the contract that already names every MathPix field a module consumes and
    is held to the corpus by `tests/test_type_contract.py`. A field that is
    merely carried and never read (`parent_id`, `line`, `is_printed`,
    `selected_labels`…) is in IGNORED_FIELDS and is correctly absent from this
    report — asking a producer for a value nothing reads is noise.
    """
    try:
        from docmodel.type_contract import CLAIMED_FIELDS
    except ImportError:                       # docmodel not importable here
        return {}
    seen: set[str] = set()
    for pg in pages:
        for ln in (pg.get("lines") or []):
            if isinstance(ln, dict):
                seen |= set(ln)
    return {f: why for f, why in CLAIMED_FIELDS.items() if f not in seen}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assemble(pdf: Path, force: bool = False) -> "dict | None":
    """Build `<stem>.lines.json` from `<stem>.lines/page-NNNN.json`.

    Returns a report dict, or None when there is nothing to do — no page folder,
    no page files in it, or a reading already on disk that we did not write.
    Returning None is the common case and costs two `stat` calls.

    The report's `wrote` is False for a no-op and True when the file was
    written; `why` says which.
    """
    d = lines_dir(pdf)
    files = page_files(d)
    if not files:
        return None
    target = lines_json(pdf)
    rep: dict = {
        "dir": str(d), "pages": len(files), "twins": len(twin_files(d)),
        "lines_json": str(target), "wrote": False, "why": "",
        "gaps": gaps(files), "missing_fields": {},
    }

    # A reading already there wins unless it is one of ours. pdf2mmd2 writes
    # BOTH spellings, so this is the normal case for its own output folders and
    # must not provoke a rewrite; and in a library folder the file may be a paid
    # MathPix conversion, which must not be touched at all.
    prior = _recorded(pdf)
    if target.exists() and not force:
        if prior and prior.get("sha256") == _sha256(
                target.read_text(encoding="utf-8", errors="replace")):
            newest = max(p.stat().st_mtime for _, p in files)
            if target.stat().st_mtime >= newest:
                rep["why"] = "the assembled lines.json is current"
                return rep
        else:
            rep["why"] = ("a lines.json we did not write is already there — "
                          "left untouched")
            return rep

    pages = read_pages(files)
    rep["missing_fields"] = missing_fields(pages)
    # The assembled document carries exactly what the page files carry, with one
    # exception: a `source` the pages AGREE on is restated at the top.
    #
    # 897 — this module shipped without that, because the planner's prerequisite
    # was answered by the ABSENCE of a `source` key and declaring one would have
    # made `inspect --ensure` name a paid step. That gate now asks the question
    # it meant to ask (`_is_typed_geometry_lines`), so a reading may say who
    # produced it. A page file is per page by construction, so a producer adding
    # `source` adds it per page and nothing would appear at the top; lifting it
    # makes `docmodel.declared_source` and the head-read in
    # `commands._lines_json_source` right by construction rather than by key
    # ordering — the same argument `pdfreader/docmodel_six.py` makes for stating
    # it in both places. Only a unanimous answer is lifted: pages that disagree
    # have no single producer.
    #
    # Until the producer declares one, nothing is invented here. A model built
    # from an undeclared reading reports `meta.source = "mathpix"`, because
    # `docmodel/main.py` defaults to that; the real reader is in the sidecar
    # under `lines_from_pages`, where no gate reads it. Naming a producer this
    # module merely inferred would be a guess recorded as provenance.
    doc: dict = {"pages": pages}
    _said = {pg.get("source") for pg in pages} - {None, ""}
    if len(_said) == 1:
        doc = {"source": _said.pop(), "pages": pages}
    rep["source"] = doc.get("source", "")
    text = json.dumps(doc, ensure_ascii=False)
    _atomic_write(target, text)
    rep["wrote"] = True
    rep["why"] = "assembled from %d page file(s)" % len(files)
    rep["sha256"] = _sha256(text)
    rep["lines"] = sum(len(pg.get("lines") or []) for pg in pages)
    _record(pdf, rep)
    return rep


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _record(pdf: Path, rep: dict) -> None:
    """Remember that WE wrote this lines.json, in the sidecar — pdfdrill's own
    state area. Deliberately not in the file: see the comment in `assemble`."""
    try:
        from .sidecar import Sidecar
        sc = Sidecar(pdf)
        sc.set_evidence("lines_from_pages", {
            "dir": rep["dir"], "pages": rep["pages"], "lines": rep.get("lines"),
            "sha256": rep.get("sha256"), "twins": rep["twins"],
            "missing_fields": sorted(rep["missing_fields"]),
        })
        sc.save()
    except Exception:                         # noqa: BLE001
        pass                                  # provenance never fails a command


def _recorded(pdf: Path) -> "dict | None":
    try:
        from .sidecar import Sidecar
        got = Sidecar(pdf).get_evidence("lines_from_pages")
        return got if isinstance(got, dict) else None
    except Exception:                         # noqa: BLE001
        return None


def report_text(rep: dict) -> str:
    """The statement a person reads — and, when a field is missing, the
    statement pdf2mmd2's CLI needs in order to fix it on its own side."""
    out = [f"{rep['pages']} page file(s) -> {Path(rep['lines_json']).name}"
           f" ({rep['why']})"]
    if rep.get("source"):
        out.append(f"  declares source={rep['source']!r}")
    if rep.get("twins"):
        out.append(f"  {rep['twins']} MathPix twin(s) in the folder — a second "
                   f"reader, not folded in")
    if rep.get("gaps"):
        out.append(f"  PAGES MISSING from the folder: "
                   f"{', '.join(str(g) for g in rep['gaps'])}")
    miss = rep.get("missing_fields") or {}
    if miss:
        out.append(f"  {len(miss)} field(s) pdfdrill READS are on no line of "
                   f"this reading — for the producer to emit:")
        for f, why in sorted(miss.items()):
            out.append(f"    {f}: read by {why}")
    return "\n".join(out)
