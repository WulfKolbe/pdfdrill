"""
Markdown ingestion — the yt2tw route (and any LLM-summary Markdown).

A Perplexity/LLM summary arrives as Markdown: `#` title, `##`/`###` sections,
prose with inline \\(...\\) math and **LaTeX `\\cite{key}` commands**, display
math `\\[...\\]`/`$$...$$`, bullet lists, a numbered **References** section,
and a fenced ```bibtex appendix carrying the gold BibTeX entries (sometimes
with `% Inferred: ...` honesty comments).

`build_markdown_model(text, bibkey)` turns that into a docmodel `Document` —
the `latexbook` pattern (source-only: no PDF, no MathPix, no OCR):

  * `#` H1            -> doc.meta["title"]
  * `## X` / `### X`  -> Section objects (level 2/3); "Table of Contents" and
                         the References/BibTeX appendix headings are NOT
                         content sections
  * `## Abstract`     -> ONE Abstract object (its paragraphs joined)
  * prose blocks      -> Paragraph (parent_section = enclosing section)
  * `\\[...\\]`/`$$`  -> Equation (props["latex"])
  * `- ` bullets      -> ListItem
  * ```bibtex fence   -> gold Reference objects (citekey/author/year/title/
                         entry_type + verbatim `bibtex`) — authoritative when
                         present; else the numbered References list is parsed
                         heuristically (year + text)
  * `\\cite{a,b}`     -> one Citation per key, linked to its Reference via
                         Alignment(kind="cites") — the bibsource idiom

Every object carries a Realization into the `markdown_source` stream (one
anchor per block), so downstream passes address blocks the same way they
address MathPix lines. The slide-extractor PDFs from the same yt2tw run go
through the ordinary PDF route; a shared --bibkey family combines them.
"""
from __future__ import annotations

import re
from typing import Any, Optional

_H = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_NUMBERED = re.compile(r"^\s*(\d{1,3})[.)]\s+(.*)$")
_FENCE = re.compile(r"^\s*(```|~~~)\s*(\w*)\s*$")
_CITE = re.compile(r"\\cite[tp]?\{([^}]*)\}")
_DISPLAY_OPEN = re.compile(r"^\s*(\\\[|\$\$)\s*$")
_DISPLAY_CLOSE = re.compile(r"^\s*(\\\]|\$\$)\s*,?\s*$")
_YEAR = re.compile(r"\((\d{4})\)")
_BIB_ENTRY = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,")

# headings that are apparatus, not content sections
_SKIP_HEADINGS = re.compile(
    r"(?i)^(table of contents|contents|inhaltsverzeichnis|bibtex( entries)?)$")
_REF_HEADINGS = re.compile(r"(?i)^(references|bibliography|literatur(verzeichnis)?)$")
_ABSTRACT_HEADINGS = re.compile(r"(?i)^(abstract|zusammenfassung|summary)$")


# --------------------------------------------------------------- bib parsing
def split_bibtex_entries(bibsrc: str) -> list[tuple[str, str, str]]:
    """-> [(entry_type, citekey, verbatim_entry)] — brace-balanced split."""
    out = []
    matches = list(_BIB_ENTRY.finditer(bibsrc))
    for k, m in enumerate(matches):
        start = m.start()
        depth = 0
        end = 0
        for i in range(start, len(bibsrc)):
            ch = bibsrc[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if not end:
            # TRUNCATED entry (LLM output cut off mid-entry): salvage up to the
            # next entry / end of source so its parsed fields survive.
            end = matches[k + 1].start() if k + 1 < len(matches) else len(bibsrc)
        out.append((m.group(1).lower(), m.group(2), bibsrc[start:end].rstrip()))
    return out


def _bib_fields(entry: str) -> dict[str, str]:
    """Field values from one entry; `%` comment lines stripped for parsing
    (the verbatim entry keeps them)."""
    from .perplexity_client import parse_bibtex_fields
    clean = "\n".join(l for l in entry.splitlines()
                      if not l.lstrip().startswith("%"))
    return parse_bibtex_fields(clean)


# ----------------------------------------------------------------- the parse
def parse_markdown(text: str) -> dict[str, Any]:
    """Pure structural parse -> {title, blocks, bibtex_entries, references}.

    blocks: ordered [{kind: heading|paragraph|equation|listitem|reference,
                      text/latex/level/..., cites: [keys]}]
    """
    lines = text.splitlines()
    title = ""
    blocks: list[dict[str, Any]] = []
    bib_entries: list[tuple[str, str, str]] = []
    references: list[dict[str, Any]] = []

    mode = "body"          # body | toc | refs | abstract
    fence_lang: Optional[str] = None
    fence_buf: list[str] = []
    para: list[str] = []
    math_buf: Optional[list[str]] = None

    def flush_para():
        nonlocal para
        t = " ".join(s.strip() for s in para if s.strip())
        para = []
        if not t:
            return
        kind = "abstract" if mode == "abstract" else "paragraph"
        blocks.append({"kind": kind, "text": t, "cites": _CITE.findall(t)})

    for raw in lines + [""]:
        line = raw.rstrip("\n")

        # fenced code blocks (the bibtex appendix lives here)
        fm = _FENCE.match(line)
        if fence_lang is not None:
            if fm:
                src = "\n".join(fence_buf)
                if fence_lang.lower() == "bibtex" or _BIB_ENTRY.search(src):
                    bib_entries.extend(split_bibtex_entries(src))
                else:
                    blocks.append({"kind": "paragraph", "text": src,
                                   "code": True, "cites": []})
                fence_lang, fence_buf = None, []
            else:
                fence_buf.append(line)
            continue
        if fm:
            flush_para()
            fence_lang = fm.group(2) or ""
            continue

        # display math
        if math_buf is not None:
            if _DISPLAY_CLOSE.match(line):
                blocks.append({"kind": "equation",
                               "latex": "\n".join(math_buf).strip().rstrip(","),
                               "cites": []})
                math_buf = None
            else:
                math_buf.append(line)
            continue
        if _DISPLAY_OPEN.match(line):
            flush_para()
            math_buf = []
            continue

        hm = _H.match(line)
        if hm:
            flush_para()
            level, caption = len(hm.group(1)), hm.group(2).strip()
            if level == 1 and not title:
                title = caption
                mode = "body"
                continue
            if _SKIP_HEADINGS.match(caption):
                mode = "toc"
                continue
            if _REF_HEADINGS.match(caption):
                mode = "refs"
                continue
            if _ABSTRACT_HEADINGS.match(caption):
                mode = "abstract"
                continue
            mode = "body"
            blocks.append({"kind": "heading", "level": level,
                           "caption": caption, "cites": []})
            continue

        if mode == "toc":
            continue                       # TOC entries are navigation, not content

        if mode == "refs":
            nm = _NUMBERED.match(line)
            if nm:
                t = nm.group(2).strip()
                ym = _YEAR.search(t)
                references.append({"number": int(nm.group(1)), "text": t,
                                   "year": ym.group(1) if ym else ""})
            continue

        nm = _BULLET.match(line)
        if nm:
            flush_para()
            t = nm.group(1).strip()
            blocks.append({"kind": "listitem", "text": t,
                           "cites": _CITE.findall(t)})
            continue

        if not line.strip():
            flush_para()
            continue
        para.append(line)

    flush_para()
    if fence_lang is not None and fence_buf:
        # unclosed fence at EOF (truncated LLM output): treat as closed
        src = "\n".join(fence_buf)
        if fence_lang.lower() == "bibtex" or _BIB_ENTRY.search(src):
            bib_entries.extend(split_bibtex_entries(src))
        else:
            blocks.append({"kind": "paragraph", "text": src,
                           "code": True, "cites": []})
    return {"title": title, "blocks": blocks,
            "bibtex_entries": bib_entries, "references": references}


# ---------------------------------------------------------------- the build
def build_markdown_model(text: str, bibkey: str = "DOC",
                         source_path: str = "") -> "object":
    """Markdown text -> docmodel Document (source-only; latexbook pattern)."""
    from docmodel.core import Document, DocObject, Stream, Realization, Range, Alignment

    parsed = parse_markdown(text)
    doc = Document()
    doc.meta["bibkey"] = bibkey
    doc.meta["title"] = parsed["title"] or bibkey
    doc.meta["source_format"] = "markdown"
    if source_path:
        doc.meta["source_path"] = source_path

    stream = Stream("markdown_source")
    doc.streams["markdown_source"] = stream

    def anchored(obj: DocObject, payload: dict) -> DocObject:
        a = stream.append(**payload)
        obj.add_realization(Realization(stream="markdown_source",
                                        start=a, end=a, role="surface"))
        doc.add(obj)
        return obj

    # --- references: gold BibTeX appendix beats the numbered list ----------
    refs_by_key: dict[str, DocObject] = {}
    if parsed["bibtex_entries"]:
        for etype, key, verbatim in parsed["bibtex_entries"]:
            fields = _bib_fields(verbatim)
            r = anchored(DocObject(type="Reference", props={
                "citekey": key, "entry_type": etype,
                "author": fields.get("author", ""),
                "year": fields.get("year", ""),
                "title": fields.get("title", ""),
                "bibtex": verbatim, "bibkey": bibkey,
                "added_by": "markdown_bibtex",
            }), {"kind": "reference", "citekey": key})
            refs_by_key[key] = r
    else:
        for ref in parsed["references"]:
            anchored(DocObject(type="Reference", props={
                "number": ref["number"], "year": ref["year"],
                "raw_text": ref["text"], "bibkey": bibkey,
                "added_by": "markdown_reflist",
            }), {"kind": "reference", "number": ref["number"]})

    # --- content flow -------------------------------------------------------
    fi = 0
    current_section: Optional[DocObject] = None
    abstract_parts: list[str] = []
    counts = {"sections": 0, "paragraphs": 0, "equations": 0,
              "listitems": 0, "citations": 0}

    def cite_objects(keys: list[str], block_anchor_payload: dict):
        nonlocal fi
        for spec in keys:
            for key in (k.strip() for k in spec.split(",")):
                if not key:
                    continue
                fi += 1
                c = anchored(DocObject(type="Citation", props={
                    "citekey": key, "flow_index": fi, "bibkey": bibkey,
                    "added_by": "markdown",
                }), dict(block_anchor_payload, kind="citation", citekey=key))
                counts["citations"] += 1
                r = refs_by_key.get(key)
                if r is not None:
                    ls = Range("markdown_source", c.realizations[0].start,
                               c.realizations[0].end)
                    rs = Range("markdown_source", r.realizations[0].start,
                               r.realizations[0].end)
                    doc.add_alignment(Alignment(
                        kind="cites", left=ls, right=rs,
                        props={"citekey": key, "citation_id": c.id,
                               "reference_id": r.id}))

    for b in parsed["blocks"]:
        fi += 1
        if b["kind"] == "heading":
            current_section = anchored(DocObject(type="Section", props={
                "caption": b["caption"], "level": b["level"],
                "flow_index": fi, "bibkey": bibkey,
            }), {"kind": "heading", "caption": b["caption"]})
            counts["sections"] += 1
        elif b["kind"] == "abstract":
            abstract_parts.append(b["text"])
            cite_objects(b["cites"], {"kind": "abstract"})
        elif b["kind"] == "equation":
            anchored(DocObject(type="Equation", props={
                "latex": b["latex"], "flow_index": fi, "bibkey": bibkey,
            }), {"kind": "equation", "latex": b["latex"]})
            counts["equations"] += 1
        elif b["kind"] == "listitem":
            anchored(DocObject(type="ListItem", props={
                "content": b["text"], "flow_index": fi, "bibkey": bibkey,
                "parent_section": current_section.id if current_section else None,
            }), {"kind": "listitem", "text": b["text"]})
            counts["listitems"] += 1
            cite_objects(b["cites"], {"kind": "listitem"})
        else:  # paragraph
            anchored(DocObject(type="Paragraph", props={
                "text": b["text"], "flow_index": fi, "bibkey": bibkey,
                "parent_section": current_section.id if current_section else None,
            }), {"kind": "paragraph", "text": b["text"]})
            counts["paragraphs"] += 1
            cite_objects(b["cites"], {"kind": "paragraph"})

    if abstract_parts:
        anchored(DocObject(type="Abstract", props={
            "text": "\n\n".join(abstract_parts), "bibkey": bibkey,
        }), {"kind": "abstract"})

    counts["references"] = len(doc.objects_of_type("Reference"))
    doc.meta["source_counts"] = counts
    return doc
