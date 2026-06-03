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
    root = out_dir / "page"
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(ppi), str(pdf), str(root)],
        check=True, capture_output=True, timeout=900,
    )
    header = "\t".join(["level", "page_num", "block_num", "par_num", "line_num",
                        "word_num", "left", "top", "width", "height", "conf", "text"])
    rows: list[str] = [header]
    for png in sorted(out_dir.glob("page-*.png")):
        digits = "".join(c for c in png.stem if c.isdigit())
        page_num = int(digits) if digits else 0
        res = subprocess.run(
            ["tesseract", str(png), "-", "-l", lang, "--psm", "1", "tsv"],
            capture_output=True, text=True, timeout=300,
        )
        rows.extend(_patch_page_column(res.stdout, page_num))
    return "\n".join(rows) + "\n"


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

    if model is not None:
        # Full element set (addresses + BOM lines) with projection embeddings.
        tiddlers = tsv_gcn.emit_tiddlers(str(tsv_path), model, bibkey, source)
    else:
        # Heuristic-only: emit the reconciled addresses as tiddlers.
        serials: dict[str, int] = {}
        tiddlers = []
        for e in reconciled:
            code = tsv_gcn.TYPE_CODE.get(e["kind"], "LO")
            serials[code] = serials.get(code, 0) + 1
            tiddlers.append(tsv_gcn.element_to_tiddler(e, bibkey, serials[code], source))

    return {"available": True, "message": "", "tiddlers": tiddlers,
            "elements": reconciled, "tsv_path": str(tsv_path),
            "source": source, "model": model}
