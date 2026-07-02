"""
PDF-reading primitives — parity with the Claude.ai `pdf-reading` skill, but
**file-based**: every result lands in the sidecar (page images, extracted
attachments/images, form-field + table JSON), not in an LLM context window.

The skill's tools, each wrapped here so a `pdfdrill` command can drive it and
return prose pointing at the written files:

  * rasterize a page → PNG          (`pdftoppm`)            — visual inspection
  * list / extract attachments      (`pdfdetach` + pypdf)   — embedded files
  * read interactive form fields    (pypdf)                 — AcroForm values
  * extract embedded raster images  (`pdfimages`)           — image bytes to disk
  * extract tables                  (pdfplumber)            — keyless, offline

All wrappers degrade gracefully (a clear message, no raise) when their tool/lib
is missing. Pure helpers (page-spec parsing, pdfdetach/pdfimages output parsing)
are unit-tested without touching a real PDF.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def parse_pages(spec: Optional[str], total: Optional[int] = None) -> Optional[list[int]]:
    """Parse a page spec into a sorted unique page list (1-based). `None`/"all"
    → None (meaning *all pages*). Accepts "N", "N-M", and comma lists
    ("1,3,5-8"). Clamps to `total` when given."""
    if spec is None or spec.strip().lower() in ("", "all"):
        return None
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out.update(range(min(a, b), max(a, b) + 1))
        elif part.isdigit():
            out.add(int(part))
    pages = sorted(p for p in out if p >= 1 and (total is None or p <= total))
    return pages or None


def parse_pdfdetach_list(text: str) -> list[dict[str, Any]]:
    """Parse `pdfdetach -list` output → [{index, name}]. The first line is
    "N embedded files"; each subsequent line is "<i>: <filename>"."""
    out = []
    for row in text.splitlines():
        m = re.match(r"\s*(\d+):\s*(.+?)\s*$", row)
        if m:
            out.append({"index": int(m.group(1)), "name": m.group(2)})
    return out


def filter_real_images(files: list[Path], min_bytes: int = 1024) -> tuple[list[Path], int]:
    """Drop tiny/empty extracted images (the skill's gotcha: masks / transparency
    / decorative layers). Returns (kept, n_dropped)."""
    kept = [f for f in files if f.stat().st_size >= min_bytes]
    return kept, len(files) - len(kept)


# ---------------------------------------------------------------------------
# 1. Rasterize pages (pdftoppm)  → PNG files for visual inspection
# ---------------------------------------------------------------------------

# Ghostscript is the ONLY rasterizer (no pdftoppm/fitz fallback): the downstream
# layers (OCR, vision, GNN layout, image-locate, …) all need consistent high-res
# input, and measured OCR/vision fidelity is far higher at gs-400 (94.9%, best
# 98.3%) than poppler/fitz (fitz-300 82.0%, fitz-180 73.8%) — only gs reads
# umlauts ("Geschäftsführer") correctly. Every raster task renders at >= 400 DPI.
RASTER_MIN_DPI = 400


def gs_binary() -> Optional[str]:
    """The Ghostscript executable, or None."""
    return (shutil.which("gs") or shutil.which("gswin64c")
            or shutil.which("gswin32c"))


def _require_gs() -> str:
    gs = gs_binary()
    if not gs:
        raise RuntimeError(
            "Ghostscript (gs) is required for rasterization — pdfdrill renders all "
            "page images with gs at >=400 DPI. Install it: `sudo apt-get install "
            "ghostscript` (or run `bash bootstrap.sh`).")
    return gs


def _gs_base(gs: str, dpi: int, ext: str) -> list[str]:
    device = "jpeg" if ext == "jpg" else "png16m"
    base = [gs, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", f"-sDEVICE={device}",
            f"-r{max(int(dpi), RASTER_MIN_DPI)}"]
    return base + (["-dJPEGQ=95"] if ext == "jpg" else [])


def rasterize(pdf: Path, out_dir: Path, *, pages: Optional[list[int]] = None,
              dpi: int = RASTER_MIN_DPI, fmt: str = "png") -> list[Path]:
    """Render pages to images via Ghostscript at >= 400 DPI (gs is the only
    rasterizer — see RASTER_MIN_DPI). `pages=None` → all pages. Files are named
    page-<N>.<ext> (N = actual page number) so callers can parse the page.
    Returns the written image paths (sorted). `dpi` is floored to 400; raises if
    gs is absent."""
    out_dir.mkdir(parents=True, exist_ok=True)
    gs = _require_gs()
    ext = "jpg" if fmt in ("jpg", "jpeg") else "png"
    pad = 4                                              # page-0001.png (sorts + parses)
    base = _gs_base(gs, dpi, ext)
    if pages:
        for p in pages:                                 # one call per page → exact name
            out = out_dir / f"page-{p:0{pad}d}.{ext}"
            subprocess.run(base + [f"-dFirstPage={p}", f"-dLastPage={p}",
                                   f"-sOutputFile={out}", str(pdf)],
                           check=True, capture_output=True, timeout=900)
    else:                                               # all pages: %d = 1..N = page no
        subprocess.run(base + [f"-sOutputFile={out_dir}/page-%0{pad}d.{ext}",
                               str(pdf)],
                       check=True, capture_output=True, timeout=1800)
    return sorted(out_dir.glob(f"page-*.{ext}"))


def render_page(pdf: Path, page: int, out_png: Path, *,
                dpi: int = RASTER_MIN_DPI) -> Path:
    """Render ONE page to an exact PNG path via Ghostscript (>= 400 DPI). For
    callers that need a specific filename (image-locate, snip/vision crops)."""
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    gs = _require_gs()
    subprocess.run(_gs_base(gs, dpi, "png") + [f"-dFirstPage={page}",
                   f"-dLastPage={page}", f"-sOutputFile={out_png}", str(pdf)],
                   check=True, capture_output=True, timeout=300)
    return out_png


# ---------------------------------------------------------------------------
# 2. Attachments (pdfdetach + pypdf)
# ---------------------------------------------------------------------------

def list_attachments(pdf: Path) -> tuple[list[dict[str, Any]], str]:
    """List embedded files. Prefer `pdfdetach -list`; fall back to pypdf's
    document-level attachments. Returns (items, source_used)."""
    if shutil.which("pdfdetach"):
        res = subprocess.run(["pdfdetach", "-list", str(pdf)],
                             capture_output=True, text=True, timeout=60)
        items = parse_pdfdetach_list(res.stdout)
        if items or "0 embedded files" in res.stdout:
            return items, "pdfdetach"
    # pypdf fallback (document-level EmbeddedFiles name tree)
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf))
        names = list(getattr(reader, "attachments", {}) or {})
        return [{"index": i + 1, "name": n} for i, n in enumerate(names)], "pypdf"
    except Exception:
        return [], "none"


def extract_attachments(pdf: Path, out_dir: Path) -> list[Path]:
    """Save all embedded files to `out_dir` via `pdfdetach -saveall`."""
    if shutil.which("pdfdetach") is None:
        raise RuntimeError("pdfdetach (poppler-utils) not on PATH.")
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["pdfdetach", "-saveall", "-o", str(out_dir), str(pdf)],
                   check=True, capture_output=True, timeout=120)
    return sorted(p for p in out_dir.iterdir() if p.is_file())


# ---------------------------------------------------------------------------
# 3. Form fields (pypdf)
# ---------------------------------------------------------------------------

_FT_LABEL = {"/Tx": "text", "/Btn": "button/checkbox", "/Ch": "choice/dropdown",
             "/Sig": "signature"}


def read_form_fields(pdf: Path) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Read interactive AcroForm fields via pypdf. Returns (fields, error). Each
    field: {name, value, type, options}. Empty list + None error = no form."""
    try:
        from pypdf import PdfReader
    except Exception:
        return [], "pypdf not installed (`pip install pypdf`)."
    try:
        reader = PdfReader(str(pdf))
        raw = reader.get_fields()
    except Exception as e:
        return [], f"could not read form: {e}"
    if not raw:
        return [], None
    out = []
    for name, fld in raw.items():
        ft = fld.get("/FT") if hasattr(fld, "get") else None
        val = fld.get("/V") if hasattr(fld, "get") else None
        states = fld.get("/_States_") if hasattr(fld, "get") else None
        out.append({"name": str(name),
                    "value": "" if val is None else str(val),
                    "type": _FT_LABEL.get(str(ft), str(ft) if ft else "unknown"),
                    "options": [str(s) for s in states] if states else []})
    return out, None


# ---------------------------------------------------------------------------
# 4. Extract embedded raster images (pdfimages)
# ---------------------------------------------------------------------------

def extract_images(pdf: Path, out_dir: Path, *, pages: Optional[list[int]] = None,
                   original_format: bool = False) -> list[Path]:
    """Extract embedded raster image bytes to files with pdfimages. `pages` may
    bound a contiguous range (min..max). NOTE: vector charts are page operators,
    not image objects — they won't appear (rasterize the page instead)."""
    if shutil.which("pdfimages") is None:
        raise RuntimeError("pdfimages (poppler-utils) not on PATH.")
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / "img"
    cmd = ["pdfimages", "-all" if original_format else "-png"]
    if pages:
        cmd += ["-f", str(min(pages)), "-l", str(max(pages))]
    cmd += [str(pdf), str(prefix)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    return sorted(p for p in out_dir.iterdir() if p.is_file() and p.name.startswith("img"))


# ---------------------------------------------------------------------------
# 5. Tables (pdfplumber)  — keyless, offline
# ---------------------------------------------------------------------------

def table_has_text(entry: dict[str, Any]) -> bool:
    """A grid with fewer than two filled cells is a FIGURE FRAME the lattice
    strategy mistook for a table (nested boxes in architecture diagrams,
    possibly carrying one stray label), not a table."""
    filled = sum(1 for c in entry.get("cells", [])
                 if (c.get("text") or "").strip())
    return filled >= 2


def plausible_text_table(entry: dict[str, Any]) -> bool:
    """Gate for the text-strategy fallback: it must LOOK like a table — at
    least 3x3 and mostly filled — so a prose page never becomes a 70x1
    'table' (the text strategy happily segments running text)."""
    n_rows, n_cols = entry.get("n_rows", 0), entry.get("n_cols", 0)
    if n_rows < 3 or n_cols < 3:
        return False
    cells = entry.get("cells", [])
    filled = sum(1 for c in cells if (c.get("text") or "").strip())
    return filled >= 0.4 * n_rows * n_cols


# pdfplumber may collapse spaces ("Table2. Detailed…"), so \s* not \s+;
# Tabelle covers German documents.
_TABLE_CAPTION = re.compile(r"(?i)\btab(?:le|elle)\s*\d+\s*[.:]")
_TEXT_STRATEGY = {"vertical_strategy": "text", "horizontal_strategy": "text"}


def extract_tables(pdf: Path, *, pages: Optional[list[int]] = None
                   ) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Extract tables with pdfplumber (`find_tables`, span-aware). Each table:
    {page, index, rows (naive matrix, compat), n_rows, n_cols, strategy,
     cells:[{row,col,row_span,col_span,text,region},…],   # value ONCE at its
     columns:[…], header_rows}                            # anchor + its range
    A merged header keeps its covered range instead of '' placeholders;
    `columns` are the flattened, linefeed-free header names per column.

    Two-strategy: the default LINES (lattice) pass first, dropping all-empty
    grids (figure-frame artifacts); on a page with a "Table N." caption but no
    usable lattice table (booktabs tables have no vertical rules), the TEXT
    strategy is tried, accepted only via `plausible_text_table`. Skips are
    reported in the second tuple element (informational, not an error)."""
    try:
        import pdfplumber
    except Exception:
        return [], "pdfplumber not installed (`pip install pdfplumber`)."
    from .table_structure import cells_from_plumber, column_headers, grid

    def _entry(tbl, pageno: int, strategy: str) -> dict[str, Any]:
        cells, n_rows, n_cols = cells_from_plumber(tbl)
        entry: dict[str, Any] = {
            "page": pageno, "index": 0,
            "rows": grid(cells, n_rows, n_cols),
            "n_rows": n_rows, "n_cols": n_cols, "strategy": strategy,
        }
        if cells:
            columns, header_rows = column_headers(cells, n_cols)
            entry.update(cells=cells, columns=columns, header_rows=header_rows)
        return entry

    out: list[dict[str, Any]] = []
    skipped_empty = 0
    try:
        with pdfplumber.open(str(pdf)) as doc:
            for pageno, page in enumerate(doc.pages, start=1):
                if pages and pageno not in pages:
                    continue
                page_tables = []
                for tbl in page.find_tables() or []:
                    e = _entry(tbl, pageno, "lines")
                    if table_has_text(e):
                        page_tables.append(e)
                    else:
                        skipped_empty += 1
                if not page_tables:
                    # booktabs-style tables have no vertical rules; only try
                    # the (noisy) text strategy where a caption says a table
                    # is actually on this page.
                    txt = page.extract_text() or ""
                    if _TABLE_CAPTION.search(txt):
                        for tbl in page.find_tables(_TEXT_STRATEGY) or []:
                            e = _entry(tbl, pageno, "text")
                            if plausible_text_table(e):
                                page_tables.append(e)
                for ti, e in enumerate(page_tables):
                    e["index"] = ti
                out.extend(page_tables)
    except Exception as e:
        return out, f"pdfplumber error: {e}"
    note = (f"skipped {skipped_empty} empty lattice grid(s) (figure-frame "
            f"artifacts)" if skipped_empty else None)
    return out, note


def tables_to_markdown(tables: list[dict[str, Any]]) -> str:
    """Render extracted tables as GitHub-flavoured markdown (one per table)."""
    blocks = []
    for t in tables:
        rows = t["rows"]
        if not rows:
            continue
        head = rows[0]
        md = ["| " + " | ".join(head) + " |",
              "| " + " | ".join("---" for _ in head) + " |"]
        for r in rows[1:]:
            r = r + [""] * (len(head) - len(r))
            md.append("| " + " | ".join(r[:len(head)]) + " |")
        blocks.append(f"**Table p{t['page']}.{t['index']}** "
                      f"({t['n_rows']}×{t['n_cols']}):\n" + "\n".join(md))
    return "\n\n".join(blocks)


_TABLES_HTML_CSS = """
body{font-family:sans-serif;margin:1.5em}
table{border-collapse:collapse;margin:1.5em 0}
caption{text-align:left;font-weight:bold;padding:.3em 0;white-space:pre-line}
td,th{border:1px solid #999;padding:.25em .5em;vertical-align:top}
th{background:#eef} .warn{color:#b00}
"""


def tables_to_html(tables: list[dict[str, Any]]) -> str:
    """The QA projection: one real <table> per extracted table, spans rendered
    natively via rowspan/colspan. Caption = page, dims, spanning-cell count +
    any structure warnings. Tables without `cells` (old shape) degrade to the
    naive grid."""
    import html as _h
    from .table_structure import to_html, check
    parts = ["<!doctype html><html><head><meta charset='utf-8'>"
             f"<style>{_TABLES_HTML_CSS}</style></head><body>",
             f"<h1>Tables ({len(tables)})</h1>"]
    for t in tables:
        cells = t.get("cells")
        if not cells:                                  # degrade: naive grid
            cells = [{"row": r, "col": c, "row_span": 1, "col_span": 1,
                      "text": v}
                     for r, row in enumerate(t.get("rows") or [])
                     for c, v in enumerate(row)]
        n_rows, n_cols = t.get("n_rows", 0), t.get("n_cols", 0)
        spanning = sum(1 for c in cells
                       if c["row_span"] > 1 or c["col_span"] > 1)
        warnings = check(cells, n_rows, n_cols)
        caption = (f"Table p. {t.get('page')}.{t.get('index')} — "
                   f"{n_rows}×{n_cols}, {spanning} spanning cell(s)")
        if warnings:
            caption += "\n⚠ " + "; ".join(warnings[:5])
        parts.append(to_html(cells, n_rows, n_cols, caption=caption,
                             columns=t.get("columns"),
                             header_rows=t.get("header_rows", 1)))
        if t.get("columns"):
            parts.append("<p><i>columns:</i> " + " | ".join(
                _h.escape(c) for c in t["columns"]) + "</p>")
    parts.append("</body></html>")
    return "\n".join(parts)
