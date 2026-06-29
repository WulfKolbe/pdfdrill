"""
Layout-element layer — glue between pdfdrill and the vendored `tsv_gcn` GNN.

`tsv_gcn` is a pure-NumPy geometric-attention GNN over Tesseract TSV word boxes
that isolates structured layout elements (postal **addresses**, **BOM line
items**) the same way the MathPix layer isolates equations as LaTeX: each found
element gets a content-addressed identity (blake3, or sha256 fallback) and is
emitted as a TiddlyWiki tiddler (`<bibkey>_<TYPE>_<serial>`) with data fields,
a normalised `geo-projection`, and a learned `projection` embedding.

This module is the thin, **additive** wiring: it renders the PDF pages, runs
tesseract over each page to a single combined TSV (page numbers patched to the
real page), and calls the two public `tsv_gcn` entry points —
`crosscheck(tsv_path, model_path)` and `emit_tiddlers(tsv_path, model_path,
bibkey, source)`. It never touches the docmodel/docops pipeline; the result is
written to the sidecar as a `layout` layer + a sibling tiddlers file by the
`pdfdrill elements` command.

It degrades gracefully on every missing piece: NumPy absent, OCR tools absent,
no trained `.npz` model AND no `extract_addresses` heuristic — each returns a
clear, actionable message instead of raising. The GNN path needs a model the
caller supplies via `--model` (train one with `python -m pdfdrill.tsv_gcn
train …`); the heuristic-only path needs the optional `extract_addresses`
module on PYTHONPATH.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional


def numpy_available() -> bool:
    return importlib.util.find_spec("numpy") is not None


def tools_available() -> tuple[bool, str]:
    """Return (ok, message). The element layer needs NumPy (the GNN) plus
    pdftoppm + tesseract (to produce the TSV word boxes)."""
    if not numpy_available():
        return False, ("the layout-element GNN needs NumPy. Install it with "
                       "`pip install 'pdfdrill[layout]'` (numpy + blake3).")
    missing = [t for t in ("pdftoppm", "tesseract") if shutil.which(t) is None]
    if missing:
        return False, (f"layout-element OCR needs {' and '.join(missing)} on "
                       f"PATH. Install poppler-utils and tesseract-ocr "
                       f"(plus a language pack, e.g. tesseract-ocr-deu).")
    return True, ""


# ---------------------------------------------------------------------------
# Combined per-page tesseract TSV (page_num patched to the real page)
# ---------------------------------------------------------------------------

def _patch_page_column(tsv: str, page_num: int) -> list[str]:
    """Rewrite the `page_num` column (index 1) of every tesseract TSV data row
    to `page_num`, dropping the header. tesseract reports page 1 for every
    single-image call, so per-page calls must be renumbered before they are
    concatenated (tsv_gcn keys words + page dims by that column)."""
    rows: list[str] = []
    for row in tsv.splitlines():
        f = row.split("\t")
        if not f or f[0] == "level" or len(f) < 12:
            continue
        f[1] = str(page_num)
        rows.append("\t".join(f))
    return rows


def build_combined_tsv(pdf: Path, out_dir: Path, *, ppi: int = 300,
                       lang: str = "deu+eng") -> str:
    """Render each page (pdftoppm) and OCR it (tesseract `tsv`), returning ONE
    combined TSV string whose `page_num` column carries the real page number.
    Reuses the same render+tesseract invocation as the `ocr` path; here we keep
    the raw TSV (the GNN consumes word geometry directly) rather than grouping
    it into lines."""
    out_dir.mkdir(parents=True, exist_ok=True)
    from . import pdf_reading                    # Ghostscript >= 400 DPI (only rasterizer)
    pngs = pdf_reading.rasterize(pdf, out_dir, dpi=ppi, fmt="png")
    header = "\t".join(["level", "page_num", "block_num", "par_num", "line_num",
                        "word_num", "left", "top", "width", "height", "conf", "text"])
    rows: list[str] = [header]
    for png in pngs:
        digits = "".join(c for c in png.stem if c.isdigit())
        page_num = int(digits) if digits else 0
        res = subprocess.run(
            ["tesseract", str(png), "-", "-l", lang, "--psm", "1", "tsv"],
            capture_output=True, text=True, timeout=300,
        )
        rows.extend(_patch_page_column(res.stdout, page_num))
    return "\n".join(rows) + "\n"


# ---------------------------------------------------------------------------
# Optional libpostal component parsing (graceful — None when absent)
# ---------------------------------------------------------------------------

def _preload_libpostal() -> bool:
    """Make `libpostal.so` loadable for the `postal` C-extension without root or
    LD_LIBRARY_PATH. A from-source `make install` puts the lib in /usr/local/lib,
    which is NOT in the default linker cache unless `ldconfig` was run — so
    `import postal._parser` fails with "libpostal.so.1: cannot open shared object
    file" even though everything is installed. We dlopen the lib RTLD_GLOBAL
    first; the subsequent extension import then finds the soname already
    resident. Returns True if a lib was loaded (or already is)."""
    import ctypes
    import glob
    dirs = ["/usr/local/lib", "/usr/lib", "/usr/lib/x86_64-linux-gnu",
            "/opt/homebrew/lib", "/usr/local/lib64", "/lib"]
    names = ["libpostal.so.1", "libpostal.so", "libpostal.1.dylib", "libpostal.dylib"]
    cands = [f"{d}/{n}" for d in dirs for n in names]
    cands += sorted(g for d in dirs for g in glob.glob(f"{d}/libpostal.so*"))
    for cand in cands:
        try:
            ctypes.CDLL(cand, mode=ctypes.RTLD_GLOBAL)
            return True
        except OSError:
            continue
    return False


def _libpostal_parser():
    """Return libpostal's `parse_address` or None. libpostal (pypostal `postal`)
    is a CRF address parser trained on ~1B OSM/OpenAddresses records; it *parses*
    a known address string into components but cannot *find* addresses on a page
    — which is why it runs AFTER the heuristic/GNN locates the block. We try the
    plain import; if the shared lib isn't on the loader path we ctypes-preload it
    and retry. Returns None only when libpostal is genuinely absent."""
    try:
        from postal.parser import parse_address  # type: ignore
        return parse_address
    except Exception:
        if _preload_libpostal():
            try:
                from postal.parser import parse_address  # type: ignore
                return parse_address
            except Exception:
                return None
        return None


def _enrich_with_libpostal(addresses: list[dict]) -> int:
    """Parse each heuristic address's raw block text into clean components
    (road/house_number/postcode/city/…) via libpostal, in place. Only fills
    addresses that lack components (so it never clobbers GNN per-word labels).
    Returns the count enriched; a no-op (0) when libpostal is unavailable."""
    parse_fn = _libpostal_parser()
    if parse_fn is None:
        return 0
    from .extract_addresses import parse_components
    n = 0
    for e in addresses:
        if e.get("kind") != "address" or e.get("components"):
            continue
        txt = e.get("text") or e.get("heuristic_text") or ""
        if not txt:
            continue
        comp = parse_components(parse_fn, txt)
        if comp:
            e["components"] = comp
            e["parsed_by"] = "libpostal"
            n += 1
    return n


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def find_elements(pdf: Path, *, model_path: Optional[Path], bibkey: str,
                  source: Optional[str], blob_dir: Path, ppi: int = 300,
                  lang: str = "deu+eng", force: bool = False) -> dict[str, Any]:
    """Render → combined TSV → tsv_gcn, returning a result dict:
        {available, message, tiddlers, elements, tsv_path, source, model}
    `available` is False (with a `message`) when a prerequisite is missing.
    `elements` is the reconciled-address provenance summary; `tiddlers` the full
    emitted tiddler array (address + BOM-line) when a model is supplied."""
    ok, msg = tools_available()
    if not ok:
        return {"available": False, "message": msg, "tiddlers": [],
                "elements": [], "tsv_path": None}

    from . import tsv_gcn  # lazy: importing pulls in NumPy

    source = source or pdf.name
    blob_dir.mkdir(parents=True, exist_ok=True)
    tsv_path = blob_dir / "elements.tsv"
    if force or not tsv_path.exists():
        tsv = build_combined_tsv(pdf, blob_dir / "elements_pages", ppi=ppi, lang=lang)
        tsv_path.write_text(tsv, encoding="utf-8")

    model = str(model_path) if model_path else None

    if model is None and not tsv_gcn._HAVE_EA:
        return {"available": False, "tsv_path": str(tsv_path),
                "tiddlers": [], "elements": [],
                "message": (
                    "no element source available: pass --model <model.npz> to "
                    "run the GNN (train one with `python -m pdfdrill.tsv_gcn "
                    "synth <dir> && python -m pdfdrill.tsv_gcn train <dir>/*.tsv "
                    "--labels-dir <dir> -o model.npz`), or put the "
                    "`extract_addresses` heuristic module on PYTHONPATH for the "
                    "address-only path. The combined page TSV was written to "
                    f"{tsv_path.name}.")}

    # Cross-check addresses (GNN ∩ heuristic) — works with a model, a heuristic,
    # or both; tags each address gnn+heuristic / gnn-only / heuristic-only.
    reconciled, _nodes = tsv_gcn.crosscheck(str(tsv_path), model)

    # Optional libpostal upgrade: parse heuristic address blocks into clean
    # components (road/house_number/postcode/city). Graceful no-op when absent.
    n_libpostal = _enrich_with_libpostal(reconciled)

    if model is not None:
        # Full element set (addresses + BOM lines) with projection embeddings.
        tiddlers = tsv_gcn.emit_tiddlers(str(tsv_path), model, bibkey, source)
    else:
        # Heuristic-only: emit the reconciled addresses as tiddlers (now carrying
        # libpostal components when available).
        serials: dict[str, int] = {}
        tiddlers = []
        for e in reconciled:
            code = tsv_gcn.TYPE_CODE.get(e["kind"], "LO")
            serials[code] = serials.get(code, 0) + 1
            tiddlers.append(tsv_gcn.element_to_tiddler(e, bibkey, serials[code], source))

    return {"available": True, "message": "", "tiddlers": tiddlers,
            "elements": reconciled, "tsv_path": str(tsv_path),
            "source": source, "model": model, "libpostal_enriched": n_libpostal}
