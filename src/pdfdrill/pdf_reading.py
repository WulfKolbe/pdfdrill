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

def rasterize(pdf: Path, out_dir: Path, *, pages: Optional[list[int]] = None,
              dpi: int = 150, fmt: str = "png") -> list[Path]:
    """Render pages to images with pdftoppm. `pages=None` → all pages. Returns
    the written image paths (sorted). pdftoppm zero-pads by total page count, so
    we glob rather than guess names."""
    if shutil.which("pdftoppm") is None:
        raise RuntimeError("pdftoppm (poppler-utils) not on PATH.")
    out_dir.mkdir(parents=True, exist_ok=True)
    flag = "-jpeg" if fmt in ("jpg", "jpeg") else "-png"
    ext = "jpg" if flag == "-jpeg" else "png"
    written: list[Path] = []
    ranges = [(p, p) for p in pages] if pages else [(None, None)]
    for first, last in ranges:
        root = out_dir / (f"page" if first is None else f"page")
        cmd = ["pdftoppm", flag, "-r", str(dpi)]
        if first is not None:
            cmd += ["-f", str(first), "-l", str(last)]
        cmd += [str(pdf), str(root)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=900)
    written = sorted(out_dir.glob(f"page-*.{ext}"))
    return written


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

def extract_tables(pdf: Path, *, pages: Optional[list[int]] = None
                   ) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Extract tables with pdfplumber. Returns (tables, error); each table:
    {page, index, rows:[[cell,…],…], n_rows, n_cols}."""
    try:
        import pdfplumber
    except Exception:
        return [], "pdfplumber not installed (`pip install pdfplumber`)."
    out: list[dict[str, Any]] = []
    try:
        with pdfplumber.open(str(pdf)) as doc:
            for pageno, page in enumerate(doc.pages, start=1):
                if pages and pageno not in pages:
                    continue
                for ti, tbl in enumerate(page.extract_tables() or []):
                    rows = [["" if c is None else str(c) for c in row] for row in tbl]
                    out.append({"page": pageno, "index": ti, "rows": rows,
                                "n_rows": len(rows),
                                "n_cols": max((len(r) for r in rows), default=0)})
    except Exception as e:
        return out, f"pdfplumber error: {e}"
    return out, None


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
