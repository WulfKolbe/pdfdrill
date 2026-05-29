"""pdfinfo-derived layers: PdfInfo struct, BibTeX, URLs, named destinations.

Wraps four pdfinfo invocations and parses their output into structured layers:

  pdfinfo -isodates          → pdfinfo struct (title, author, dates, pages, ...)
  pdfinfo -custom -isodates  → richer metadata (DOI, arXivID, License, ...)
  pdfinfo -url               → URL annotations per page
  pdfinfo -dests             → named destinations (theorems, equations, sections)

Each call is independent and idempotent. The sidecar stores raw parsed
results so re-parsing or re-formatting later is cheap.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# PdfInfo struct (matches the D-style struct in the spec)
# ---------------------------------------------------------------------------

def _empty_pdfinfo() -> dict[str, Any]:
    """Default PdfInfo struct with all fields present."""
    return {
        "title": "",
        "author": "",
        "producer": "",
        "creator": "",
        "creation_date": None,
        "mod_date": None,
        "custom_metadata": False,
        "metadata_stream": False,
        "tagged": False,
        "user_properties": False,
        "suspects": False,
        "form": "",
        "javascript": False,
        "pages": 0,
        "encrypted": False,
        "page_size": "",
        "page_rot": 0.0,
        "size_in_bytes": 0,
        "linearized": False,
        "optimized": False,
        "pdf_version": "",
    }


# Map pdfinfo output keys to PdfInfo struct field names.
_FIELD_MAP = {
    "Title": ("title", str),
    "Author": ("author", str),
    "Producer": ("producer", str),
    "Creator": ("creator", str),
    "CreationDate": ("creation_date", str),
    "ModDate": ("mod_date", str),
    "Custom Metadata": ("custom_metadata", "yesno"),
    "Metadata Stream": ("metadata_stream", "yesno"),
    "Tagged": ("tagged", "yesno"),
    "UserProperties": ("user_properties", "yesno"),
    "Suspects": ("suspects", "yesno"),
    "Form": ("form", str),
    "JavaScript": ("javascript", "yesno"),
    "Pages": ("pages", int),
    "Encrypted": ("encrypted", "yesno"),
    "Page size": ("page_size", str),
    "Page rot": ("page_rot", float),
    "File size": ("size_in_bytes", "bytes"),
    "Linearized": ("linearized", "yesno"),
    "Optimized": ("optimized", "yesno"),
    "PDF version": ("pdf_version", str),
}


def _coerce(value: str, kind: Any) -> Any:
    s = value.strip()
    if kind == "yesno":
        return s.lower() in ("yes", "true", "1")
    if kind == "bytes":
        m = re.match(r"(\d+)", s)
        return int(m.group(1)) if m else 0
    if kind is int:
        m = re.match(r"-?\d+", s)
        return int(m.group()) if m else 0
    if kind is float:
        m = re.match(r"-?\d+(?:\.\d+)?", s)
        return float(m.group()) if m else 0.0
    return s


def _parse_pdfinfo_kv(stdout: str) -> dict[str, str]:
    """Parse `Key: value` lines from pdfinfo output."""
    out: dict[str, str] = {}
    for line in stdout.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


# ---------------------------------------------------------------------------
# Subprocess wrappers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], timeout: int = 30) -> str:
    """Run a subprocess command and return stdout (empty on failure)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except (subprocess.SubprocessError, OSError):
        return ""


def fetch_pdfinfo_struct(pdf: Path) -> dict[str, Any]:
    """Build the full PdfInfo struct from two pdfinfo calls.

    Uses `-isodates` for stable date parsing and `-custom` to pick up
    extra fields like DOI/arXivID that some producers expose.
    """
    info = _empty_pdfinfo()
    info["size_in_bytes"] = pdf.stat().st_size

    base = _parse_pdfinfo_kv(_run(["pdfinfo", "-isodates", str(pdf)]))
    custom = _parse_pdfinfo_kv(_run(["pdfinfo", "-custom", "-isodates", str(pdf)]))

    merged: dict[str, str] = {}
    merged.update(custom)
    merged.update(base)

    for key, raw in merged.items():
        if key in _FIELD_MAP:
            field, kind = _FIELD_MAP[key]
            info[field] = _coerce(raw, kind)

    info["custom_fields"] = {
        k: v for k, v in custom.items() if k not in _FIELD_MAP
    }
    return info


# ---------------------------------------------------------------------------
# BibTeX record derivation
# ---------------------------------------------------------------------------

_ARXIV_RE = re.compile(r"arxiv\.org/abs/([\w.\-]+)", re.I)
_DOI_RE = re.compile(r"(?:doi\.org/|^doi:?\s*)(10\.\d{4,9}/[^\s]+)", re.I)


def derive_bibtex(info: dict[str, Any]) -> dict[str, Any]:
    """Derive a BibTeX record from a PdfInfo struct + custom fields.

    Fields are partial by design — pdfinfo often gives us pages and dates
    but not title/author. The caller can later augment from the abstract.
    """
    custom = info.get("custom_fields", {})

    title = info.get("title") or ""
    author = info.get("author") or ""

    year = ""
    cdate = info.get("creation_date") or ""
    m = re.match(r"(\d{4})", cdate)
    if m:
        year = m.group(1)

    doi = ""
    for src in (custom.get("DOI", ""), custom.get("doi", "")):
        m = _DOI_RE.search(src or "")
        if m:
            doi = m.group(1)
            break

    arxiv_id = ""
    for src in (custom.get("arXivID", ""), custom.get("arxivID", ""), custom.get("DOI", "")):
        m = _ARXIV_RE.search(src or "")
        if m:
            arxiv_id = m.group(1)
            break

    entry_type = "article" if (doi or arxiv_id) else "misc"

    citekey = _make_citekey(author, year, title)

    bib: dict[str, Any] = {
        "entry_type": entry_type,
        "citekey": citekey,
        "title": title,
        "author": author,
        "year": year,
        "pages": info.get("pages", 0),
        "doi": doi,
        "arxiv_id": arxiv_id,
        "url": custom.get("URL", "") or custom.get("arXivID", "") or "",
        "license": custom.get("License", ""),
        "publisher": info.get("producer", ""),
    }
    return bib


def _make_citekey(author: str, year: str, title: str) -> str:
    """Make a simple citekey: FirstAuthorLastNameYEAR."""
    first = ""
    if author:
        first_author = author.split(";")[0].split(",")[0].split(" and ")[0].strip()
        parts = first_author.split()
        if parts:
            first = re.sub(r"[^A-Za-z]", "", parts[-1]).lower()
    if not first and title:
        first = re.sub(r"[^A-Za-z]", "", title.split()[0]).lower() if title.split() else ""
    return f"{first or 'unknown'}{year or ''}"


def bibtex_to_string(bib: dict[str, Any]) -> str:
    """Render a BibTeX dict as a BibTeX entry string."""
    if not bib:
        return ""
    lines = [f"@{bib['entry_type']}{{{bib['citekey']},"]
    field_order = ("title", "author", "year", "pages", "doi", "arxiv_id", "url", "license", "publisher")
    for key in field_order:
        val = bib.get(key)
        if val:
            lines.append(f"  {key:9s} = {{{val}}},")
    if lines[-1].endswith(","):
        lines[-1] = lines[-1].rstrip(",")
    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# URLs layer
# ---------------------------------------------------------------------------

_URL_LINE_RE = re.compile(r"^\s*(\d+)\s+(\S+)\s+(\S.*)$")


def fetch_urls(pdf: Path) -> list[dict[str, Any]]:
    """Parse `pdfinfo -url` output into a list of URL records."""
    out = _run(["pdfinfo", "-url", str(pdf)])
    urls: list[dict[str, Any]] = []
    for line in out.splitlines():
        if line.startswith("Page") or not line.strip():
            continue
        m = _URL_LINE_RE.match(line)
        if not m:
            continue
        page, type_, url = m.groups()
        urls.append({
            "page": int(page),
            "type": type_,
            "url": url.strip(),
        })
    return urls


# ---------------------------------------------------------------------------
# Named destinations layer
# ---------------------------------------------------------------------------

_DEST_LINE_RE = re.compile(
    r"^\s*(\d+)\s+\[\s*\S+\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+\S+\s*\]\s+\"([^\"]+)\""
)


def fetch_dests(pdf: Path) -> list[dict[str, Any]]:
    """Parse `pdfinfo -dests` output into structured destination records.

    Output format:  `   1 [ XYZ   78  714 null      ] "Doc-Start"`
    """
    out = _run(["pdfinfo", "-dests", str(pdf)], timeout=60)
    dests: list[dict[str, Any]] = []
    for line in out.splitlines():
        m = _DEST_LINE_RE.match(line)
        if not m:
            continue
        page, x, y, name = m.groups()
        dests.append({
            "page": int(page),
            "x": float(x),
            "y": float(y),
            "name": name,
            "kind": _classify_dest(name),
        })
    return dests


def _classify_dest(name: str) -> str:
    """Bucket a destination name into a kind: theorem, equation, section, page, figure, ..."""
    low = name.lower()
    if low.startswith("theorem"):
        return "theorem"
    if low.startswith("lemma"):
        return "lemma"
    if low.startswith("proposition") or low.startswith("prop"):
        return "proposition"
    if low.startswith("corollary"):
        return "corollary"
    if low.startswith("definition") or low.startswith("def."):
        return "definition"
    if low.startswith("remark"):
        return "remark"
    if low.startswith("example"):
        return "example"
    if low.startswith("equation") or re.match(r"^eq\.|^equation\.", low):
        return "equation"
    if low.startswith("figure") or low.startswith("fig."):
        return "figure"
    if low.startswith("table") or low.startswith("tab."):
        return "table"
    if low.startswith("section"):
        return "section"
    if low.startswith("subsection") or low.startswith("subsubsection"):
        return "subsection"
    if low.startswith("page."):
        return "page_anchor"
    if low.startswith("ams") or low.startswith("toc"):
        return "metadata"
    if low in ("doc-start", "doc-end"):
        return "anchor"
    return "other"


def summarize_dests(dests: list[dict[str, Any]]) -> dict[str, int]:
    """Count destinations by kind."""
    counts: dict[str, int] = {}
    for d in dests:
        counts[d["kind"]] = counts.get(d["kind"], 0) + 1
    return counts
