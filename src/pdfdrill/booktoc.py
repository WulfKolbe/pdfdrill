"""
Book TOC layer — a greppable table of contents with printed→PDF page alignment.

A book's printed TOC pairs each chapter/section with its PRINTED page number,
which is NOT the PDF (physical) page number: front matter (title, copyright,
the TOC itself, preface — often roman-numbered or unnumbered) shifts everything
by a constant. So "Chapter 3 … 45" means printed page 45, which might be PDF
page 57.

We recover that **front-matter offset** without guessing, by matching TOC
titles to the model's `Section` objects — those carry the REAL PDF page. The
offset is `median(section.pdf_page − toc.printed_page)` over the matched pairs;
it absorbs whatever front matter exists. A TOC entry that matches a section
resolves to that section's exact PDF page; an unmatched entry falls back to
`printed_page + offset`.

The output (`<bibkey>.toc.txt`) is one line per entry —
`<number>\t<title>\t printed <p> \t pdf <q>` — so an LLM can **grep a chapter
or section by name and read its PDF page directly**, then `pdfdrill page` /
`rasterize` that page. It is a cheap, standalone artifact (no full model load
needed to navigate the book).

Pure functions here; `commands.cmd_booktoc` wires them over the fast DocGraph
read path.
"""
from __future__ import annotations

import re
import statistics
from typing import Any

# A good TOC line: "1.1 Formal Concepts  ..... 11" or "Bibliography  133".
# title (>=2 non-dot chars) + optional dotted leader + trailing page number.
_ENTRY = re.compile(r"^\s*(.+?)\s*\.{0,}\s*(\d{1,4})\s*$")
# a leading section number lifted out of the title: "1.1 Formal Concepts".
_LEAD_NUM = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(.*)$")
_DOTS_ONLY = re.compile(r"^[.\s]*$")


def _norm(title: str) -> str:
    """Match key: drop a leading section number, lowercase, collapse spaces."""
    t = _LEAD_NUM.sub(r"\2", title.strip())
    return re.sub(r"\s+", " ", t).strip().lower()


def parse_toc_entries(raw_entries: list[str]) -> list[dict[str, Any]]:
    """Raw TOC strings → [{number, title, printed_page}], fragments dropped.

    MathPix often emits a TOC line three times ("X  ..... 5", "X", "..... 5");
    only the form carrying BOTH a real title and a trailing page survives."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for raw in raw_entries:
        if not raw or _DOTS_ONLY.match(raw):
            continue
        m = _ENTRY.match(raw)
        if not m:
            continue
        title, page = m.group(1).strip(" .\t"), int(m.group(2))
        if len(title) < 2 or _DOTS_ONLY.match(title):
            continue
        number = ""
        nm = _LEAD_NUM.match(title)
        if nm:
            number, title = nm.group(1), nm.group(2).strip()
        key = (title.lower(), page)
        if key in seen:
            continue
        seen.add(key)
        out.append({"number": number, "title": title, "printed_page": page})
    return out


def compute_offset(entries: list[dict], sections: list[dict]
                   ) -> tuple[int, float, list[tuple]]:
    """(offset, confidence, pairs). offset = median(pdf − printed) over TOC
    entries whose normalized title matches a Section caption; confidence =
    fraction of matched pairs agreeing with the chosen offset."""
    sec_page = {}
    for s in sections:
        cap = (s.get("caption") or "").strip()
        pg = s.get("page")
        if cap and pg is not None:
            sec_page.setdefault(_norm(cap), pg)
    pairs = []
    for e in entries:
        pg = sec_page.get(_norm(e["title"]))
        if pg is not None:
            pairs.append((e["printed_page"], pg))
    if not pairs:
        return 0, 0.0, []
    diffs = [pdf - pr for pr, pdf in pairs]
    offset = int(statistics.median(diffs))
    agree = sum(1 for d in diffs if d == offset)
    return offset, round(agree / len(diffs), 3), pairs


def align_toc(entries: list[dict], sections: list[dict]) -> list[dict[str, Any]]:
    """Attach `pdf_page` (+ `exact`) to each entry: the matched section's real
    page when available, else `printed_page + offset`."""
    offset, _conf, _ = compute_offset(entries, sections)
    sec_page = {}
    for s in sections:
        cap = (s.get("caption") or "").strip()
        if cap and s.get("page") is not None:
            sec_page.setdefault(_norm(cap), s["page"])
    out = []
    for e in entries:
        pg = sec_page.get(_norm(e["title"]))
        out.append({**e,
                    "pdf_page": pg if pg is not None else e["printed_page"] + offset,
                    "exact": pg is not None})
    return out


def render_toc(aligned: list[dict], offset: int, bibkey: str) -> str:
    """Greppable text: header + one line per entry (number, title, printed,
    pdf). `grep <chapter> <bibkey>.toc.txt` → the PDF page to open."""
    exact = sum(1 for a in aligned if a.get("exact"))
    lines = [f"# Table of contents — {bibkey}",
             f"# printed→PDF page offset {offset:+d} (front matter); "
             f"{exact}/{len(aligned)} entries page-exact, rest estimated.",
             "# columns: number  title  printed_page  pdf_page  [~ = estimated]",
             ""]
    for a in sorted(aligned, key=lambda x: x["pdf_page"]):
        num = a.get("number") or ""
        mark = "" if a.get("exact") else " ~"
        lines.append(f"{num:<8}{a['title']}\tprinted {a['printed_page']}\t"
                     f"pdf {a['pdf_page']}{mark}")
    return "\n".join(lines)
