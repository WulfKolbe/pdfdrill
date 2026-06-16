"""
citedrill — drill INTO a citation: find where the cited publication can be
downloaded, fetch it, and stamp the Reference with the drill STATUS.

Flow per Reference (driven by `commands.cmd_citedrill`):
  1. Ask Perplexity SONAR for ALL downloadable links for the publication
     (`perplexity_client.fetch_links`); merge the answer URLs + SONAR citations.
  2. `rank_links` — free routes FIRST (arXiv → its direct PDF URL, then bare
     `.pdf`, then DOI, then anything else).
  3. For each candidate in rank order: HEAD-`verify` it, then attempt to
     `download` the PDF into the sidecar (`cited/<citekey>.pdf`). Attempt ANY
     link; stop at the first that downloads.
  4. Write a per-reference **`cited/<citekey>.pdf.json`** recording the attempt
     (candidates + verify/fetch status + the working link), and stamp the
     Reference with `drill_status` / `pdf_url` / `pdf_path` / `pdf_json` /
     `download_links` — so a citation record carries a possible link to its PDF.

Pure helpers (extract/classify/rank/record/status/fields) are here + unit-tested;
the network parts go through `net`/`sources`/`perplexity_client` and degrade
gracefully (blocked network / no key → `drill_status="blocked"`).
"""
from __future__ import annotations

import re
from typing import Optional

from . import sources

_URL = re.compile(r"https?://[^\s<>()\[\]\"']+")
_TRAIL = ".,;:)]}>\"'"


def extract_links(answer: str, citations: Optional[list] = None) -> list[str]:
    """All http(s) URLs from the Perplexity answer text + its citation list,
    de-duplicated, discovery order preserved, trailing punctuation trimmed."""
    out: list[str] = []
    seen: set[str] = set()
    for src in (answer or "", *(citations or [])):
        for m in _URL.finditer(str(src)):
            u = m.group(0).rstrip(_TRAIL)
            if u and u not in seen:
                seen.add(u)
                out.append(u)
    return out


def classify_link(url: str) -> str:
    """arxiv | doi | pdf | other (the routing class for ranking)."""
    if sources.parse_arxiv_id(url):
        return "arxiv"
    host = sources.host_of(url).lower()
    if "doi.org" in host or re.search(r"/10\.\d{4,9}/", url):
        return "doi"
    if url.lower().split("?")[0].endswith(".pdf"):
        return "pdf"
    return "other"


_ORDER = {"arxiv": 0, "pdf": 1, "doi": 2, "other": 3}


def rank_links(urls: list[str]) -> list[dict]:
    """Order candidates free-route-first ([{url, kind}]). An arXiv abs/pdf URL is
    normalized to its DIRECT PDF URL (the one pdfdrill can actually fetch). Stable
    within a class (discovery order)."""
    ranked: list[dict] = []
    seen: set[str] = set()
    for i, u in enumerate(urls):
        kind = classify_link(u)
        url = u
        if kind == "arxiv":
            aid = sources.parse_arxiv_id(u)
            if aid:
                url = sources.arxiv_urls(aid).get("pdf", u)
        if url in seen:
            continue
        seen.add(url)
        ranked.append({"url": url, "kind": kind, "_i": i})
    ranked.sort(key=lambda r: (_ORDER.get(r["kind"], 9), r["_i"]))
    for r in ranked:
        r.pop("_i", None)
    return ranked


def build_record(citekey: str, title: str, year: str, candidates: list[dict],
                 pdf_url: Optional[str], pdf_path: Optional[str],
                 blocked: bool = False, error: str = "") -> dict:
    """The per-reference pdf.json record + its derived `drill_status`."""
    if blocked:
        status = "blocked"
    elif error:
        status = "error"
    elif pdf_path:
        status = "fetched"
    elif candidates:
        status = "links_only"
    else:
        status = "no_links"
    rec = {
        "citekey": citekey, "title": title, "year": year,
        "drill_status": status,
        "pdf_url": pdf_url, "pdf_path": pdf_path,
        "candidates": candidates,
    }
    if error:
        rec["error"] = error
    return rec


def reference_fields(record: dict, pdf_json: str) -> dict:
    """The fields stamped onto the Reference DocObject from a pdf.json record."""
    return {
        "drill_status": record.get("drill_status"),
        "pdf_url": record.get("pdf_url"),
        "pdf_path": record.get("pdf_path"),
        "pdf_json": pdf_json,
        "download_links": [c["url"] for c in record.get("candidates", []) if c.get("url")],
    }


# --------------------------------------------------------------------------- #
#  network: verify + fetch (graceful)
# --------------------------------------------------------------------------- #

def verify(url: str, timeout: float = 20.0) -> str:
    """HEAD the URL: 'pdf' (content-type pdf or .pdf), 'ok' (reachable), or
    'fail'. Never raises — a blocked/unreachable host returns 'fail'."""
    import urllib.request
    from .net import urlopen, NetworkBlocked
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urlopen(req, timeout=timeout, host=sources.host_of(url)) as r:
            ctype = (r.headers.get("Content-Type") or "").lower()
        if "pdf" in ctype or url.lower().split("?")[0].endswith(".pdf"):
            return "pdf"
        return "ok"
    except (NetworkBlocked, Exception):
        return "fail"


def fetch(url: str, dest) -> bool:
    """Download the URL to dest; True on success (non-empty file). Never raises."""
    from pathlib import Path
    try:
        sources.download(url, dest)
        p = Path(dest)
        return p.exists() and p.stat().st_size > 0
    except Exception:
        try:
            Path(dest).unlink(missing_ok=True)
        except Exception:
            pass
        return False
