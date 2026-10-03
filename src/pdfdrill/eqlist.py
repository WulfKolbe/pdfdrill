"""865 — AN EQUATION LIST: rows drawn ACROSS documents, not from one.

Every reporting layer in this package takes a document as its subject. It
holds that document's lock, writes fixed names beside its PDF, and says
"recognised / projected / deferred" about it. That is the right shape for
reading one paper and the wrong shape for two jobs now in front of us:

  * a corpus-wide equation list — `document, equation no, page rectangle or
    crop link, LaTeX` — for the BINARY-GENERATED PDFs here, which no
    per-document artefact can express because the subject spans 20+ folders;
  * InftyDB v1/v2, arriving as certified (image, LaTeX) pairs with NO PDF at
    all. It is not a corpus of documents we hold. It is rows.

So the subject becomes the LIST, and this module is what a list is.

WHAT A ROW IS IDENTIFIED BY, which took two wrong answers to settle.

`equations.json` carries `identifier` ("EQ0001") and `ident`
(`sha(bibkey|page|region|latex)`). I proposed `ident` as the key because I
measured it unique — 34,317 of 34,317 rows across the 20 documents that have
the file, zero collisions. It is unique, and it is still the wrong key, for a
reason uniqueness cannot show: it mixes LATEX INTO THE KEY. Re-read a slot,
get different LaTeX, and `ident` changes — so the row does not read as "same
slot, new content", it reads as a NEW ROW, with the old one vanished and any
measurement against it orphaned against an id that exists nowhere. The
artefact says nothing happened. An identity that changes when the content
changes cannot detect a content change.

inkdrill's split, which is what this module emits, separates the three jobs:

    identity    (bibkey, page, region)   unique BY CONSTRUCTION — two rows
                                         cannot occupy one rectangle. Measured:
                                         34,317 distinct of 34,317.
    label       EQnnnn                   human-facing; renumbers freely
    stability   latex_sha16              same identity + different hash
                                         = the slot was re-read, the mark
                                         is stale. NOT a key: 18,945 of
                                         32,449 rows (58.4%) share their
                                         LaTeX with another row in their OWN
                                         document — `V` occurs 166 times in
                                         sigma26-086. Over half the inline
                                         maths in a maths journal is a single
                                         letter.

`ident` is still carried, as provenance for the file it came from, and never
as the key.

SELECTION IS NOT CALIBRATION SCOPE. The one constraint that changed this
design. inkdrill votes the scale PER DOCUMENT, on up to 400 of that
document's rows, and calibrates its flag thresholds from the confidently
placed ones: sigma26-078 calibrated on n_ref 78; sigma26-080 REFUSED with 7.
A self-contained list of 20 rows per document would hand it ~5 reference rows
and every document would refuse. So each listed document is named here with
its resolvable paths and their hashes, and the measuring side calibrates on
the document's full set OF THE LISTED KIND while marking only the listed rows.
Anyone later "optimising" this file by dropping `documents` breaks the
instrument, not the file size.

THE KIND IS PART OF THAT SCOPE, which the first subset got wrong. "The
document's full row set" is right for an unfiltered list and wrong for a
kind-filtered one: sigma26-080 holds 1,976 inline rows and 74 display, so
calibrating a DISPLAY list on all 2,050 draws its reference rows from the
inline single letters — 409 of 415 sampled rows failed the margin test and the
document refused. The refusal was never about the document; it was about which
rows it was asked to reason from, and on the 74 display rows the margin
problem largely disappears. So `rows_of_kind_in_document` is emitted beside
`rows_in_document`, and a refusal at 74 now means "too few display equations
in this document" — information — rather than "the sample was the wrong kind".

THE FRAME IS DECLARED, NEVER INFERRED. Regions are in `PX_PER_PT = 250/72`,
y DOWN from the page's top-left — written down in `docmodel_six.py` and
`mathpix_merge.py`. It must not be derived from the data: the widest row in
these 20 documents reaches only the text margin (540pt of a 612pt page), so
the largest observed x understates the page width by 12% and a frame inferred
from it puts 2,958 rows (8.6%) "off the bottom of the page" that are in fact
all inside it. That was a real wrong answer, found only by reading the source.
Nor does this file convert the frame for anyone: mapping 250 dpi regions onto
another raster is per page and per axis (MathPix pixels are the CropBox,
`inspect/pages` the MediaBox — 654 found 4 of 21 documents with a CropBox
inset, and one global ratio lands a crop five text lines wrong). The list
states its frame. The consumer maps it.

NO HOST IS BAKED INTO A ROW. `crop_url_template` sits once at the top level
and rows carry only `crop.id` and the query. 862 is why: 2,783
`http://localhost:8000/cropped/...` links went into 20 `.tex` files, each one
unfetchable by LaTeX on any machine without that server, and nothing in the
output said so.

AND THE LIST READS. It never rewrites a `lines.json`. Every inkdrill mark set
hashes one through `measured_against`, so re-emitting a reading invalidates
the measurement even when the new reading means the same thing (863).
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

SCHEMA = "pdfdrill.eqlist/1"

#: The declared frame. `docmodel_six.PX_PER_PT` / `mathpix_merge.PX_PER_PT`.
PX_PER_PT = 250.0 / 72.0

FRAME = {
    "px_per_pt": PX_PER_PT,
    "dpi": 250,
    "y": "down",
    "origin": "page top-left",
    "note": "Declared, not inferred — the widest row reaches only the text "
            "margin, so the largest observed x understates the page width. "
            "Mapping these regions onto another raster is the consumer's, "
            "per page and per axis (CropBox vs MediaBox); this file does not "
            "convert them.",
}

#: Producers that are a BINARY GENERATING a PDF from a source document, as
#: against a scanner's wrapper. Measured over 3,024 sidecars: pdfTeX ~560
#: across 12 versions, dvips+Ghostscript 108, LuaTeX 31, XeTeX, Distiller
#: ~110, Adobe PDF Library ~80. Deliberately NOT "has a text layer" (2,869
#: documents, which includes re-wrapped scans carrying an OCR layer: pikepdf
#: 103, CVISION 26). A scan with an OCR layer is a scan.
_BINARY_PRODUCERS = re.compile(
    # `pdflatex` and `pdfetex` are spelled out because `pdftex` does not match
    # either of them — 19 documents say "PDFLaTeX" and 7 say "pdfeTeX-1.21a",
    # and all 26 were being classified as "not a generator" by a pattern
    # written for the name they do not use. `skia` is Chrome's print-to-PDF.
    r"pdftex|pdflatex|pdfetex|luatex|xetex|dvips|dvipdfm|tectonic|skia"
    r"|acrobat distiller|adobe pdf library|ghostscript"
    r"|microsoft.*(word|print)|libreoffice|openoffice|quartz|cairo"
    r"|itext|reportlab|pdf-lib|weasyprint|prince|wkhtmltopdf",
    re.I)

#: These produce a PDF too, but from PAGE IMAGES. The text in them, when
#: there is any, is OCR. They are excluded even though they match nothing
#: above, because the distinction the list rests on is glyph-level text.
_SCANNER_PRODUCERS = re.compile(
    r"cvision|abbyy|finereader|scantailor|img2pdf|paperport|epson|canon"
    r"|hp scan|xerox|kofax|readiris|omnipage|tesseract"
    # Found by reading the 606 "not recognised" producers rather than assuming
    # the list was complete: Acrobat's "Image Conversion Plug-in" (22 across
    # four versions) wraps page IMAGES, as do tiff2pdf (11), ImageMagick (8)
    # and calibre (7). They match nothing in the generator pattern either, so
    # without naming them here they would be excluded for the vague reason
    # instead of the true one — and this list is checked FIRST, so a document
    # that says both is a scan.
    r"|image conversion|tiff2pdf|imagemagick|calibre",
    re.I)


def binary_generated(producer: str | None, creator: str | None = None) -> tuple:
    """(is_binary, why) for a producer/creator pair.

    A PRODUCER-STRING test, and it is worth saying plainly that that is all it
    is: the string is self-reported metadata and a PDF can lie or carry none
    (138 of 3,024 sidecars have no producer at all). It is evidence, not
    proof, which is why `why` comes back with the answer and lands in the
    list — a reader who disagrees with a classification can see what it was
    made from instead of re-deriving it.
    """
    blob = " ".join(x for x in (producer or "", creator or "") if x)
    if not blob.strip():
        return False, "no producer recorded"
    if _SCANNER_PRODUCERS.search(blob):
        m = _SCANNER_PRODUCERS.search(blob)
        return False, f"scanner/OCR producer: {m.group(0)}"
    m = _BINARY_PRODUCERS.search(blob)
    if m:
        return True, f"producer: {m.group(0)}"
    return False, f"producer not recognised as a generator: {blob[:60]}"


#: A READING THAT LOST ITS SUBJECT. inkdrill found these in the ink — a
#: cobordism or a surface standing where a symbol would be, which is ordinary
#: in topology — and the reader drops the figure and emits the tokens around
#: it. `Q = .` compiles and asserts that Q equals nothing; `K_{n} = \times I,`
#: does not parse as maths at all. Both pass a structural check that only
#: counts delimiters, and both claim CONFIDENCE 1.0, because confidence is the
#: fraction of SPANS projected and a figure was never a span. A measure defined
#: over spans cannot see something that never became one.
#:
#: A LEADING RELATION IS NOT ONE OF THESE. A continuation line of an aligned
#: display legitimately starts with `=` — sigma26-076 EQ2371/2/3 are three
#: consecutive lines of one block — and a first pass that flagged them counted
#: 29 where the real number is 14.
_LOST_OPERAND = [
    (re.compile(r"(?:^|[^\\=<>])=\s*[.,;]?\s*$"), "nothing after ="),
    (re.compile(r"=\s*\\(?:times|otimes|cdot|circ|oplus)\b"),
     "= then a binary operator"),
    (re.compile(r"=\s*,"), "= then a comma"),
]


def lost_operand(latex: str | None) -> str | None:
    """Why this reading looks like it lost an operand, or None.

    A LOWER BOUND, and the list says so: a figure dropped from between two
    symbols that still leaves a syntactically plausible string is invisible
    here, exactly as it is invisible to an ink gap when the figure sits tight
    against the body. Two instruments, two blind spots, neither complete.
    """
    lx = (latex or "").strip()
    if not lx:
        return None
    for rx, why in _LOST_OPERAND:
        if rx.search(lx):
            return why
    return None


def latex_sha16(latex: str | None) -> str | None:
    """The STABILITY field: 16 hex of sha256 over the LaTeX.

    A change detector, never a key — 58.4% of rows share their LaTeX with
    another row in the same document.
    """
    if not latex:
        return None
    return hashlib.sha256(latex.encode("utf-8")).hexdigest()[:16]


def _sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def crop_id(bibkey: str, page: int) -> str:
    """The one crop id, `<bibkey>-<page:02d>` — `project_mmd.crop_id`'s scheme,
    restated here so the list does not import a reader to name a crop."""
    return f"{bibkey}-{page:02d}"


def _crop(bibkey: str, page: int, region: dict) -> dict:
    """The crop LINK, as id + query. No host: see the module docstring."""
    return {
        "id": crop_id(bibkey, page),
        "page": page,
        "query": (f"height={region['height']}&width={region['width']}"
                  f"&top_left_y={region['top_left_y']}"
                  f"&top_left_x={region['top_left_x']}"),
    }


def _row(bibkey: str, eq: dict, no: int) -> dict:
    """One list row, from one `equations.json` entry."""
    region = eq.get("region") or {}
    latex = eq.get("latex")
    return {
        "lane": "pdf",
        "document": bibkey,
        "no": no,
        # IDENTITY — unique by construction, survives a re-read.
        "identity": {"document": bibkey, "page": eq.get("page"),
                     "region": region},
        # LABEL — renumbers freely.
        "label": eq.get("identifier") or "",
        # THE AUTHOR'S equation number, when the document set one — `(1.1)`.
        # This is what "equation no" means to a reader of the paper; `label`
        # is an ordinal this pipeline invented and renumbers at will. It is
        # absent for an unnumbered display and for every inline fragment, and
        # absent is not "0": a row with no number is not row number nothing.
        "number": eq.get("number") or None,
        "number_region": eq.get("number_region"),
        # STABILITY — same identity + different hash == stale mark.
        "latex_sha16": latex_sha16(latex),
        "latex": latex,
        # Not a confidence and not a score: the NAME of the shape that makes
        # this reading suspect, or absent. A consumer can act on "nothing
        # after =" ; it cannot act on 0.97.
        "lost_operand": lost_operand(latex),
        "kind": eq.get("kind"),
        "confidence": eq.get("confidence"),
        "structural_ok": eq.get("structural_ok"),
        "spans": eq.get("spans"),
        "projected": eq.get("projected"),
        "deferred": eq.get("deferred") or [],
        "crop": _crop(bibkey, eq.get("page") or 0, region) if region else None,
        # The InftyDB lane's field, first-class from the start rather than
        # retrofitted: an (image, LaTeX) row has no page and no rectangle, and
        # a schema that forces the two lanes into one field is wrong in
        # whichever direction it chooses.
        "image": None,
        # Provenance only. NOT the key — it mixes latex into the hash.
        "ident": eq.get("ident"),
    }


def _document_entry(folder: Path, bibkey: str, n_rows: int, n_listed: int,
                    producer: str | None, creator: str | None,
                    pages: int | None, why: str, *,
                    kind: str | None = None, n_of_kind: int | None = None) -> dict:
    """What the measuring side needs to CALIBRATE on the full document while
    marking only the listed rows. Paths and their hashes, so a consumer can
    verify what it was handed instead of trusting it."""
    def ref(name: str) -> dict | None:
        p = folder / name
        if not p.exists():
            return None
        return {"path": str(p), "sha256": _sha256(p), "bytes": p.stat().st_size}

    return {
        "document": bibkey,
        "folder": str(folder),
        "producer": producer,
        "creator": creator,
        "pages": pages,
        "binary_generated_because": why,
        "rows_in_document": n_rows,
        # THE POPULATION TO CALIBRATE ON, which is not `rows_in_document` for
        # a kind-filtered list. inkdrill measured why: sigma26-080 has 1,976
        # inline rows and 74 display, so calibrating a DISPLAY list on the
        # document's whole set draws its reference rows from the inline
        # fragments — 409 of 415 sampled rows failed the margin test and the
        # document refused. The refusal was never about the document; it was
        # about which rows it was asked to reason from. On the 74 display rows
        # the margin problem largely disappears. So a refusal at 74 means
        # "too few display equations in this document", which is information,
        # instead of "the sample was the wrong kind", which is noise.
        "kind": kind or "any",
        "rows_of_kind_in_document": n_rows if n_of_kind is None else n_of_kind,
        "rows_listed": n_listed,
        # Named for calibration. Dropping these does not shrink the file, it
        # breaks the instrument: ~5 reference rows per document and every
        # document refuses (sigma26-080 refused with 7).
        "inputs": {
            "pdf": ref(f"{bibkey}.pdf"),
            "equations_json": ref(f"{bibkey}.equations.json"),
            "lines_json": ref(f"{bibkey}.lines.json"),
            "evidence_formula_tex": ref("evidence-formula.tex"),
        },
    }


def _sidecar_meta(folder: Path, bibkey: str) -> dict:
    for name in (f"{bibkey}.drill.json", f"{bibkey}.pdf.drill.json"):
        p = folder / name
        if p.exists():
            try:
                return (json.load(open(p, encoding="utf-8"))
                        .get("evidence") or {})
            except Exception:                                # noqa: BLE001
                return {}
    return {}


def candidates(library: Path) -> tuple:
    """(listable, skipped) over a library root.

    Listable = a folder with an `equations.json` whose producer says a binary
    generated the PDF. `skipped` is a {reason: [document]} map, because a
    document absent from a list for a knowable reason is not the same as a
    document that was never considered — the distinction that had `code`
    called "dropped entirely" when 97.5% of it was already recovered.
    """
    listable, skipped = [], {}

    def skip(why: str, name: str) -> None:
        skipped.setdefault(why, []).append(name)

    for folder in sorted(p for p in library.iterdir() if p.is_dir()):
        bibkey = folder.name
        eqs = folder / f"{bibkey}.equations.json"
        if not eqs.exists():
            skip("no equations.json (run `pdfdrill equations`)", bibkey)
            continue
        meta = _sidecar_meta(folder, bibkey)
        ok, why = binary_generated(meta.get("producer"), meta.get("creator"))
        if not ok:
            skip(why.split(":")[0] if ":" in why else why, bibkey)
            continue
        listable.append((folder, bibkey, meta, why))
    return listable, skipped


def build(library: Path, *, name: str = "eqlist", kind: str | None = None,
          per_document: int | None = None, documents: int | None = None,
          only: list | None = None, seed: int = 11) -> dict:
    """Build a list from a library root.

    `kind` filters display/inline; `per_document` and `documents` bound the
    subset. A bounded list says so in `selection`, so nobody reads a 200-row
    subset as a measurement of the corpus — 593's lesson, where a bounded
    build shipped fewer rows than its own manifest named.
    """
    listable, skipped = candidates(library)
    if only:
        want = set(only)
        listable = [t for t in listable if t[1] in want]
    rng = random.Random(seed)
    if documents is not None and len(listable) > documents:
        listable = sorted(rng.sample(listable, documents), key=lambda t: t[1])

    rows, docs = [], []
    counts = {"rows": 0, "display": 0, "inline": 0, "with_latex": 0,
              "structural_ok": 0, "with_region": 0, "lost_operand": 0}
    dropped = {}

    for folder, bibkey, meta, why in listable:
        try:
            data = json.load(open(folder / f"{bibkey}.equations.json",
                                  encoding="utf-8"))
        except Exception as e:                               # noqa: BLE001
            skipped.setdefault(f"unreadable equations.json: {e}", []).append(bibkey)
            continue
        eqs = data.get("equations") or []
        pool = [e for e in eqs if kind is None or e.get("kind") == kind]
        if kind is not None:
            n = len(eqs) - len(pool)
            if n:
                dropped[f"kind != {kind}"] = dropped.get(f"kind != {kind}", 0) + n
        chosen = pool
        if per_document is not None and len(pool) > per_document:
            # Evenly spaced through the document rather than the first N: the
            # first N rows of a paper are its abstract and introduction, and a
            # subset drawn from one region of one layout is not a subset.
            step = len(pool) / float(per_document)
            chosen = [pool[int(i * step)] for i in range(per_document)]
            dropped["beyond --per-document"] = (
                dropped.get("beyond --per-document", 0) + len(pool) - len(chosen))
        for i, eq in enumerate(chosen, 1):
            r = _row(bibkey, eq, i)
            rows.append(r)
            counts["rows"] += 1
            counts[r["kind"]] = counts.get(r["kind"], 0) + 1
            if r["latex"]:
                counts["with_latex"] += 1
            if r["structural_ok"]:
                counts["structural_ok"] += 1
            if r["crop"]:
                counts["with_region"] += 1
            if r["lost_operand"]:
                counts["lost_operand"] += 1
        docs.append(_document_entry(folder, bibkey, len(eqs), len(chosen),
                                    meta.get("producer"), meta.get("creator"),
                                    meta.get("pages"), why,
                                    kind=kind, n_of_kind=len(pool)))

    return {
        "schema": SCHEMA,
        "name": name,
        "frame": FRAME,
        "crop_url_template": "{base}/cropped/{id}.jpg?{query}",
        "selection": {
            "library": str(library),
            "kind": kind or "any",
            "per_document": per_document,
            "documents_requested": documents,
            "documents_listed": len(docs),
            "seed": seed,
            "bounded": bool(per_document or documents),
            "note": "SELECTION IS NOT CALIBRATION SCOPE — each document in "
                    "`documents` carries its full row count and its inputs so "
                    "the measuring side calibrates on the whole document and "
                    "marks only the listed rows.",
        },
        "identity": {
            "key": ["document", "page", "region"],
            "label": "label (EQnnnn) — renumbers on a re-read, never a key",
            "stability": "latex_sha16 — same key + different hash = stale",
            "not_a_key": "ident (sha of bibkey|page|region|latex) mixes the "
                         "content into the hash, so a re-read looks like a new "
                         "row rather than a changed one. Carried as provenance.",
        },
        "counts": counts,
        "not_listed": {"documents": {k: len(v) for k, v in sorted(skipped.items())},
                       "rows": dropped},
        "skipped_documents": {k: sorted(v) for k, v in sorted(skipped.items())},
        "documents": docs,
        "rows": rows,
    }


def validate(data: dict) -> list:
    """Problems with a list, as prose lines. Empty means it holds.

    This is the half the user asked for FIRST — "to check the correct list
    properties start with a subset". A list nobody can check is a list nobody
    should measure against.
    """
    out = []
    if data.get("schema") != SCHEMA:
        out.append(f"schema is {data.get('schema')!r}, expected {SCHEMA!r}")
    rows = data.get("rows") or []
    counts = data.get("counts") or {}
    if counts.get("rows") != len(rows):
        out.append(f"counts.rows {counts.get('rows')} != {len(rows)} actual rows")

    seen, dup = {}, 0
    no_region = no_latex = 0
    for r in rows:
        ident = r.get("identity") or {}
        reg = ident.get("region") or {}
        if not reg:
            no_region += 1
        else:
            k = (ident.get("document"), ident.get("page"),
                 reg.get("top_left_x"), reg.get("top_left_y"),
                 reg.get("width"), reg.get("height"))
            if k in seen:
                dup += 1
            seen[k] = 1
            if reg.get("width", 0) <= 0 or reg.get("height", 0) <= 0:
                out.append(f"{ident.get('document')} {r.get('label')}: "
                           f"zero-area region {reg}")
        if not (r.get("latex") or "").strip():
            no_latex += 1
        elif not r.get("latex_sha16"):
            out.append(f"{ident.get('document')} {r.get('label')}: LaTeX but "
                       f"no latex_sha16 — the stability field is the only way "
                       f"a stale mark is detectable")
    if dup:
        out.append(f"{dup} row(s) share an identity (document, page, region) — "
                   f"the key is not a key on this list")
    if no_region and data.get("rows") and any(
            r.get("lane") == "pdf" for r in rows):
        out.append(f"{no_region} pdf-lane row(s) carry no region, so nothing "
                   f"can be placed or cropped for them")

    # The documents a row names must be present, or the measuring side cannot
    # calibrate and the lane silently degrades into refusals.
    named = {d.get("document") for d in (data.get("documents") or [])}
    orphan = sorted({r.get("document") for r in rows} - named)
    if orphan:
        out.append(f"{len(orphan)} document(s) have rows but no entry in "
                   f"`documents`, so their full row set is unreachable for "
                   f"calibration: {', '.join(orphan[:5])}")
    for d in (data.get("documents") or []):
        ins = d.get("inputs") or {}
        for want in ("pdf", "equations_json"):
            if not ins.get(want):
                out.append(f"{d.get('document')}: no {want} — a dependency "
                           f"that is not in the file is not a dependency")
        if d.get("rows_listed", 0) > d.get("rows_in_document", 0):
            out.append(f"{d.get('document')}: lists {d['rows_listed']} rows of "
                       f"{d['rows_in_document']} in the document")
        k = d.get("rows_of_kind_in_document")
        if k is not None:
            if k > d.get("rows_in_document", 0):
                out.append(f"{d.get('document')}: calibration population {k} "
                           f"exceeds the document's {d.get('rows_in_document')} "
                           f"rows")
            if d.get("rows_listed", 0) > k:
                out.append(f"{d.get('document')}: lists {d['rows_listed']} rows "
                           f"but names only {k} to calibrate on — the listed "
                           f"rows must be inside the calibration population")
    return out


def verify_inputs(data: dict) -> list:
    """Re-hash every named input and report what moved.

    `proofs.verify`'s rule, applied to a list: a missing or changed input
    fails, rather than being read as agreement. A list whose documents have
    been rebuilt underneath it is not a list of those documents.
    """
    out = []
    for d in data.get("documents") or []:
        for name, ref in (d.get("inputs") or {}).items():
            if not ref:
                continue
            p = Path(ref["path"])
            if not p.exists():
                out.append(f"{d['document']}: {name} is gone — {p}")
                continue
            now = _sha256(p)
            if now != ref.get("sha256"):
                out.append(f"{d['document']}: {name} CHANGED since the list "
                           f"was built ({ref.get('sha256', '')[:12]} -> "
                           f"{(now or '')[:12]})")
    return out


def load(path: Path) -> dict:
    return json.load(open(path, encoding="utf-8"))
