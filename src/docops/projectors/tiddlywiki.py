"""
TiddlyWikiProjector — emit a JSON array of TiddlyWiki tiddlers.

Goal: produce TiddlyWiki output where every non-textual element is replaced
by a templated transclusion. Even a single `$E$` becomes `{{<bibkey>_FO0817||FO}}`.

For inline elements we substitute by per-line offset+length stored on each
DocObject's surface Realization. For elements without explicit offsets
(footnote markers, inline picture URLs) we use regex passes on the rebuilt
paragraph text. Paragraph text is reconstructed from the immutable
mathpix_lines stream so the substitution offsets remain valid even if a
mutator (Dehyphenate, translation, etc.) has rewritten `Paragraph.text`.

Tiddler title scheme (bibkey="DOC"):
    DOC                     — root document tiddler
    DOC_H<n>                — Section
    DOC_PAGE_<NNN>          — Page
    DOC_PARA_<NNNN>         — Paragraph
    DOC_EQ<NNNN>_p<NNN>     — Equation (display)
    DOC_FO<NNNN>            — Formula (inline math)
    DOC_PIC_<NNNN>          — Picture
    DOC_DIA_<NNNN>          — Diagram
    DOC_TAB_<NNN>_p<NNN>    — Table
    DOC_FN<NNNN>            — Footnote
    DOC_SN<NNNN>            — Sidenote
    DOC_LI<NNNN>            — ListItem
    DOC_ABS<NN>             — Abstract
    DOC_TOC<NN>             — Toc
    DOC_<citekey>           — Citation placeholder (one per unique citekey)
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from docmodel.core import Document, DocObject
from ..base import BaseProjector
from .common import embed_image


def _tw_now() -> str:
    n = datetime.now(timezone.utc)
    return n.strftime("%Y%m%d%H%M%S") + f"{n.microsecond // 1000:03d}"


def _sanitize_title(t: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-\.]", "_", t)


def _bibtag(bibkey: str) -> str:
    """The bibkey as a single TiddlyWiki tag ([[...]]-wrapped if it has spaces)."""
    bibkey = bibkey or "DOC"
    return f"[[{bibkey}]]" if (" " in bibkey) else bibkey


# LaTeX sectioning commands that MathPix sometimes leaves inside a paragraph
# body (`\section*{...}`) instead of tagging the line as a section header. The
# PARA template is `<p>{{!!text}}</p>` and KaTeX only renders math, so these
# render as the literal string. Convert to the native WikiText heading the
# document uses (`!`/`!!`/`!!!`). Longest command first so `subsubsection`
# isn't shadowed by `section`. Title taken as the first brace group (titles
# don't nest braces in practice).
# Match the command + opening brace; the title (which may itself contain
# balanced braces, e.g. a `{{...||FO}}` transclusion) is walked brace-balanced.
# Longest command first so `subsubsection` isn't shadowed by `section`.
_SECTIONING_HEAD = re.compile(
    r"\\(chapter|subsubsection|subsection|section)\*?\s*\{")
_HEADING_LEVEL = {"chapter": "!", "section": "!", "subsection": "!!",
                  "subsubsection": "!!!"}


def latex_sectioning_to_wikitext(text: str) -> str:
    """Convert leaked LaTeX sectioning commands in prose to WikiText headings.

    `\\section*{X}` -> `! X`, `\\subsection{X}` -> `!! X`, etc. The title is
    extracted with a balanced-brace walk so a `{{...||FO}}` transclusion inside
    it survives. The heading is put on its own line (WikiText headings must
    start a line); runs of blank lines are collapsed. No-op without a `\\`.
    """
    if not text or "\\" not in text:
        return text
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        m = _SECTIONING_HEAD.search(text, i)
        if not m:
            out.append(text[i:])
            break
        out.append(text[i:m.start()])
        depth, j = 1, m.end()
        while j < n and depth > 0:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        if depth != 0:                       # unbalanced — leave the rest as-is
            out.append(text[m.start():])
            break
        title = text[m.end():j - 1].strip()
        out.append(f"\n\n{_HEADING_LEVEL[m.group(1)]} {title}\n\n")
        i = j
    return re.sub(r"\n{3,}", "\n\n", "".join(out)).strip()


# Footnote anchor patterns (MathPix produces variations like \({ }^{1}\) or { }^{1}).
_FN_REF_RE = re.compile(r"\\\(\s*\{\s*\}\s*\^\s*\{\s*(\d+)\s*\}\s*\\\)|\{\s*\}\s*\^\s*\{\s*(\d+)\s*\}")
_INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
_MD_IMG_RE = re.compile(r"!\[[^\]]*\]\((https?://[^\s)]+)\)")
_CDN_URL_RE = re.compile(r"https?://cdn\.mathpix\.com/cropped/[^\s)\]\}\"<>]+")

# Block-level content types listed inside a Section tiddler's body.
# Formulas/Citations/Footnotes do NOT appear at block level — they're inline.
_BLOCK_TYPES_IN_SECTION = {
    "Paragraph", "Equation", "Table", "Picture", "Diagram",
    "ListItem", "Abstract", "Toc", "Sidenote",
}


class TiddlyWikiProjector(BaseProjector):

    def output_extension(self) -> str:
        return ".tiddlers.json"

    def project(self, doc: Document) -> str:
        bibkey = doc.meta.get("bibkey", "DOC")

        title, inv = self._assign_titles(doc, bibkey)

        # Footnote lookup-by-refnum for inline substitution.
        fn_by_refnum: dict[str, str] = {}
        for fn in inv["footnotes"]:
            rn = fn.props.get("refnum")
            if rn is not None and str(rn) not in fn_by_refnum:
                fn_by_refnum[str(rn)] = title[fn.id]

        # Reference tiddler titles by citekey, so in-text citations can link
        # straight to the bibliographic entry instead of a placeholder.
        ref_title_by_key: dict[str, str] = {}
        ref_title_by_number: dict[str, str] = {}
        for r in inv["references"]:
            rk = (r.props.get("citekey") or "").lower()
            if rk:
                ref_title_by_key[rk] = title[r.id]
            num = r.props.get("number")
            if num is not None:
                ref_title_by_number[str(num)] = title[r.id]

        # Citation tiddler titles, deduplicated by citekey. Prefer a matching
        # Reference (exact or surname-prefix); fall back to a placeholder.
        cit_title_by_key: dict[str, str] = {}
        cit_placeholders: dict[str, str] = {}
        for c in inv["citations"]:
            ck = (c.props.get("citekey") or "").strip()
            if not ck or ck in cit_title_by_key:
                continue
            cl = ck.lower()
            ref_t = (ref_title_by_number.get(ck) if ck.isdigit() else None) \
                or ref_title_by_key.get(cl) or next(
                (t for k, t in ref_title_by_key.items()
                 if len(cl) >= 3 and k.startswith(cl)), None)
            if ref_t:
                cit_title_by_key[ck] = ref_t
            else:
                safe = re.sub(r"[^A-Za-z0-9_\-]", "_", ck)
                cit_title_by_key[ck] = cit_placeholders[ck] = f"{bibkey}_{safe}"
        self._cit_placeholders = cit_placeholders

        # Inline-picture URL → title (only for pictures that originated
        # within text lines, NOT for figure-line Pictures which are block-level).
        inline_url_to_title: dict[str, str] = {}
        for pic in inv["pictures"]:
            if pic.props.get("from_line_type") == "figure":
                continue
            url = pic.props.get("url")
            if url and url not in inline_url_to_title:
                inline_url_to_title[url] = title[pic.id]

        # Equation-number -> tiddler title, for in-text reference substitution
        # ("(1)" in body text -> {{<eq>||FREF}}). Longest first so "(10)" wins
        # over "(1)".
        self._eqref_map = sorted(
            ((e.props.get("equation_number"), title[e.id]) for e in inv["equations"]
             if e.props.get("equation_number")),
            key=lambda kv: -len(kv[0]),
        )

        subs_by_line = self._build_inline_subs(doc, inv, title, cit_title_by_key)

        out = self._emit_tiddlers(
            doc, bibkey, inv, title,
            fn_by_refnum, cit_title_by_key, inline_url_to_title, subs_by_line,
        )
        self.bump("tiddlers_emitted", len(out))
        return json.dumps(out, indent=2, ensure_ascii=False)

    # ----- phase 1: inventory + stable titles -----

    def _assign_titles(
        self, doc: Document, bibkey: str,
    ) -> tuple[dict[str, str], dict[str, list[DocObject]]]:
        """
        Collect every object type in its stable emission order and assign each
        a tiddler title. Returns (title-by-id, inventory) so the emission phase
        can reuse the same ordered lists without re-sorting.
        """
        inv: dict[str, list[DocObject]] = {
            "paragraphs": self._sort_by_flow(doc.objects_of_type("Paragraph")),
            "sections":   self._sort_by_flow(doc.objects_of_type("Section")),
            "equations":  self._sort_by_flow(doc.objects_of_type("Equation")),
            "formulas":   self._sort_by_flow(doc.objects_of_type("Formula")),
            "citations":  doc.objects_of_type("Citation"),
            "pictures":   self._sort_by_flow(doc.objects_of_type("Picture")),
            "diagrams":   self._sort_by_flow(doc.objects_of_type("Diagram")),
            "tables":     self._sort_by_flow(doc.objects_of_type("Table")),
            "footnotes":  doc.objects_of_type("Footnote"),
            "sidenotes":  self._sort_by_flow(doc.objects_of_type("Sidenote")),
            "list_items": self._sort_by_flow(doc.objects_of_type("ListItem")),
            "abstracts":  self._sort_by_flow(doc.objects_of_type("Abstract")),
            "tocs":       self._sort_by_flow(doc.objects_of_type("Toc")),
            "references": self._sort_by_flow(doc.objects_of_type("Reference")),
            "pages":      sorted(doc.objects_of_type("Page"),
                                 key=lambda o: o.props.get("page_number", 0)),
        }

        title: dict[str, str] = {}
        for i, p in enumerate(inv["paragraphs"]):
            title[p.id] = f"{bibkey}_PARA_{i+1:04d}"
        for i, s in enumerate(inv["sections"]):
            title[s.id] = f"{bibkey}_H{i+1}"
        for i, e in enumerate(inv["equations"]):
            title[e.id] = f"{bibkey}_EQ{i+1:04d}_p{int(e.props.get('page') or 0):03d}"
        for i, f in enumerate(inv["formulas"]):
            title[f.id] = f"{bibkey}_FO{i+1:04d}"
        for i, p in enumerate(inv["pictures"]):
            title[p.id] = f"{bibkey}_PIC_{i+1:04d}"
        for i, d in enumerate(inv["diagrams"]):
            title[d.id] = f"{bibkey}_DIA_{i+1:04d}"
        for i, t in enumerate(inv["tables"]):
            title[t.id] = f"{bibkey}_TAB_{i+1:03d}_p{int(t.props.get('page') or 0):03d}"
        for fn in inv["footnotes"]:
            title[fn.id] = f"{bibkey}_FN{int(fn.props.get('refnum') or 0):04d}"
        for i, s in enumerate(inv["sidenotes"]):
            title[s.id] = f"{bibkey}_SN{i+1:04d}"
        for i, li in enumerate(inv["list_items"]):
            title[li.id] = f"{bibkey}_LI{i+1:04d}"
        for i, a in enumerate(inv["abstracts"]):
            title[a.id] = f"{bibkey}_ABS{i+1:02d}"
        for i, t in enumerate(inv["tocs"]):
            title[t.id] = f"{bibkey}_TOC{i+1:02d}"
        for pg in inv["pages"]:
            title[pg.id] = f"{bibkey}_PAGE_{int(pg.props.get('page_number') or 0):03d}"
        for i, ref in enumerate(inv["references"]):
            ck = re.sub(r"[^A-Za-z0-9]", "", ref.props.get("citekey") or "")
            title[ref.id] = f"{bibkey}_REF_{ck or (i + 1)}"
        return title, inv

    # ----- phase 2: per-line inline substitution index -----

    def _build_inline_subs(
        self, doc: Document, inv: dict[str, list[DocObject]],
        title: dict[str, str], cit_title_by_key: dict[str, str],
    ) -> dict:
        """
        Build {line_anchor -> [(offset, length, replacement), ...]} for the
        inline elements that carry explicit sub-line offsets: formulas and
        citations.
        """
        subs_by_line: dict = defaultdict(list)

        for f in inv["formulas"]:
            replacement = "{{" + title[f.id] + "||FO}}"
            for r in f.realizations:
                if (r.stream == "mathpix_lines" and r.role == "surface"
                        and r.start is not None):
                    off = r.props.get("offset")
                    ln = r.props.get("length")
                    if isinstance(off, int) and isinstance(ln, int):
                        subs_by_line[r.start].append((off, ln, replacement))
                        self.bump("formula_inline_subs")

        for c in inv["citations"]:
            ck = (c.props.get("citekey") or "").strip()
            ct = cit_title_by_key.get(ck)
            if not ct:
                continue
            replacement = "{{" + ct + "||CIT}}"
            for r in c.realizations:
                if (r.stream == "mathpix_lines" and r.role == "surface"
                        and r.start is not None):
                    off = r.props.get("offset")
                    ln = r.props.get("length")
                    if isinstance(off, int) and isinstance(ln, int):
                        # Optionally extend to consume the surrounding [ ]
                        new_off, new_len = self._maybe_extend_brackets(
                            doc, r.start, off, ln)
                        subs_by_line[r.start].append(
                            (new_off, new_len, replacement))
                        self.bump("citation_inline_subs")

        return subs_by_line

    # ----- phase 3: tiddler emission -----

    def _emit_tiddlers(
        self, doc: Document, bibkey: str, inv: dict[str, list[DocObject]],
        title: dict[str, str], fn_by_refnum: dict[str, str],
        cit_title_by_key: dict[str, str], inline_url_to_title: dict[str, str],
        subs_by_line: dict,
    ) -> list[dict]:
        out: list[dict] = []
        out.extend(self._templates(bibkey))

        # Synthetic Formula tiddlers for inline math that wraps across line
        # boundaries (FormulaProcessor scans per-line and misses these).
        # key: title -> {"latex": str, "display": bool}
        synthetic_formulas: dict[str, dict] = {}

        # Pages
        for pg in inv["pages"]:
            t = self._t(
                title[pg.id],
                f"Page {pg.props.get('page_number')} of //{bibkey}//.",
                f"page {_bibtag(bibkey)}",
            )
            t["page"] = self._p3(pg.props.get("page_number"))
            if pg.props.get("image_id"):
                t["image_id"] = pg.props["image_id"]
            if pg.props.get("is_blank"):
                t["is_blank"] = "true"
            out.append(t)

        # Paragraphs (with inline transclusions baked into text).
        for p in inv["paragraphs"]:
            transcluded = self._transclude_paragraph(
                p, doc, subs_by_line, fn_by_refnum, inline_url_to_title,
                synthetic_formulas, bibkey,
            )
            t = self._t(
                title[p.id], transcluded,
                f"paragraph {_bibtag(bibkey)}",
            )
            t["page"] = self._p3(p.props.get("page"))
            if p.props.get("first_line_index") is not None:
                t["line"] = str(p.props["first_line_index"])
            ps_id = p.props.get("parent_section")
            if ps_id and ps_id in title:
                t["parent_section"] = title[ps_id]
            # Preserve the raw text if a mutator (e.g. Dehyphenate) saved it.
            if "text_raw" in p.props:
                t["text_raw"] = p.props["text_raw"]
            self.bump("para_tiddlers")
            out.append(t)

        # Sections (with body listing children as transclusions in flow order).
        for s in inv["sections"]:
            body = self._section_body(s, doc, title)
            t = self._t(
                title[s.id], body,
                f"section {_bibtag(bibkey)}",
            )
            t["level"] = str(s.props.get("level", 1))
            t["section_number"] = s.props.get("section_number") or ""
            t["caption"] = s.props.get("caption") or ""
            t["page"] = self._p3(s.props.get("page"))
            t["kind"] = s.props.get("cmd") or "section"
            if s.parent and s.parent in title:
                t["parent_section"] = title[s.parent]
            elif s.parent:
                t["parent_section"] = bibkey
            out.append(t)

        # Formulas
        for f in inv["formulas"]:
            t = self._t(
                title[f.id],
                "<$latex text={{!!latex}} displayMode={{!!displayMode}} />",
                f"formula {_bibtag(bibkey)}",
            )
            t["latex"] = f.props.get("latex", "")
            t["displayMode"] = "true" if f.props.get("display") else "false"
            # Keep the verbatim author source (may use private macros) alongside
            # the expanded `latex` that <$latex>/KaTeX actually renders.
            if f.props.get("latex_original"):
                t["latex_original"] = f.props["latex_original"]
            out.append(t)

        # Equations
        for e in inv["equations"]:
            t = self._t(
                title[e.id],
                "<$latex text={{!!latex}} displayMode=true />",
                f"equation {_bibtag(bibkey)}",
            )
            t["kind"] = "Equation"
            t["latex"] = e.props.get("latex", "")
            if e.props.get("latex_original"):
                t["latex_original"] = e.props["latex_original"]   # verbatim macro source
            t["displayMode"] = "true"   # display equations render in display mode
            t["refnum"] = e.props.get("refnum") or ""
            # Displayed reference "(N)" for the ||FREF transclusion.
            eqn = e.props.get("equation_number")
            if not eqn and e.props.get("refnum"):
                eqn = f"({e.props['refnum']})"
            t["equation_number"] = eqn or ""
            t["page"] = self._p3(e.props.get("page"))
            if e.props.get("cdn_url"):
                t["canonical_uri"] = self._uri(e.props["cdn_url"])
            self._copy_region(t, e.props)
            # Competing LaTeX readings (snip/llm/...) as parallel fields so a
            # TiddlyWiki table macro can show them side by side, like compare.html.
            for r in e.realizations:
                if r.role == "latex_candidate" and r.provenance:
                    t[f"latex_{r.provenance}"] = r.props.get("latex", "")
                    if r.score is not None:
                        t[f"score_{r.provenance}"] = str(r.score)
            out.append(t)

        # Pictures
        for pic in inv["pictures"]:
            t = self._t(
                title[pic.id],
                "<$image source={{!!canonical_uri}} width={{!!width}} height={{!!height}}/>",
                f"picture {_bibtag(bibkey)}",
            )
            t["canonical_uri"] = self._uri(pic.props.get("url") or "")
            t["page"] = self._p3(pic.props.get("page"))
            for k in ("caption", "kind", "refnum"):
                if pic.props.get(k):
                    t[k] = pic.props[k]
            self._copy_region(t, pic.props)
            out.append(t)

        # Diagrams (a `subtype=code` diagram is a source-code listing, not an
        # image — emit it as a fenced code block, which TiddlyWiki renders as
        # <pre><code>; never an <$image>).
        for d in inv["diagrams"]:
            if d.props.get("subtype") == "code":
                lang = d.props.get("language") or ""
                code = d.props.get("code") or d.props.get("latex_code") or ""
                t = self._t(
                    title[d.id],
                    f"```{lang}\n{code}\n```",
                    f"code {_bibtag(bibkey)}",
                )
                t["page"] = self._p3(d.props.get("page"))
                if lang:
                    t["language"] = lang
                out.append(t)
                continue
            # Prefer the locally-rendered SVG (from `pdfdrill svg`): emit it as a
            # separate image/svg+xml tiddler and link it; else fall back to the
            # CDN crop via <$image>.
            svg_title = self._emit_svg_tiddler(out, title[d.id], d.props.get("svg"), bibkey)
            body = (f'<$image source="{svg_title}"/>' if svg_title
                    else "<$image source={{!!canonical_uri}} "
                         "width={{!!width}} height={{!!height}}/>")
            t = self._t(title[d.id], body, f"diagram {_bibtag(bibkey)}")
            t["page"] = self._p3(d.props.get("page"))
            t["latex_code"] = d.props.get("latex_code") or ""
            if d.props.get("latex_original"):
                t["latex_original"] = d.props["latex_original"]   # verbatim macro source
            if svg_title:
                t["svg_tiddler"] = svg_title
            if d.props.get("cdn_url"):
                t["canonical_uri"] = self._uri(d.props["cdn_url"])
            for k in ("caption", "kind", "refnum"):
                if d.props.get(k):
                    t[k] = d.props[k]
            self._copy_region(t, d.props)
            out.append(t)

        # Tables
        for tab in inv["tables"]:
            svg_title = self._emit_svg_tiddler(out, title[tab.id], tab.props.get("svg"), bibkey)
            body = (f'<$image source="{svg_title}"/>' if svg_title
                    else tab.props.get("raw_text", ""))
            t = self._t(title[tab.id], body, f"table {_bibtag(bibkey)}")
            t["page"] = self._p3(tab.props.get("page"))
            if tab.props.get("latex_code"):
                t["latex_code"] = tab.props["latex_code"]
            if tab.props.get("latex_original"):
                t["latex_original"] = tab.props["latex_original"]
            if svg_title:
                t["svg_tiddler"] = svg_title
            out.append(t)

        # Footnotes
        for fn in inv["footnotes"]:
            t = self._t(
                title[fn.id],
                fn.props.get("content", ""),
                f"footnote {_bibtag(bibkey)}",
            )
            t["refnum"] = str(fn.props.get("refnum") or "")
            t["anchor"] = fn.props.get("anchor_marker") or ""
            t["page"] = self._p3(fn.props.get("page"))
            out.append(t)

        # Sidenotes
        for sn in inv["sidenotes"]:
            t = self._t(
                title[sn.id],
                sn.props.get("content", ""),
                f"sidenote {_bibtag(bibkey)}",
            )
            t["page"] = self._p3(sn.props.get("page"))
            out.append(t)

        # ListItems
        for li in inv["list_items"]:
            t = self._t(
                title[li.id],
                li.props.get("content", ""),
                f"listitem {_bibtag(bibkey)}",
            )
            t["marker"] = li.props.get("marker") or ""
            t["page"] = self._p3(li.props.get("page"))
            out.append(t)

        # Abstracts
        for a in inv["abstracts"]:
            t = self._t(
                title[a.id],
                a.props.get("text", ""),
                f"abstract {_bibtag(bibkey)}",
            )
            t["page"] = self._p3(a.props.get("page"))
            out.append(t)

        # TOC
        for toc in inv["tocs"]:
            entries = toc.props.get("entries", []) or []
            body = "\n".join(f"* {e}" for e in entries)
            t = self._t(
                title[toc.id], body,
                f"toc {_bibtag(bibkey)}",
            )
            out.append(t)

        # References (bibliographic entries). The text leads with a {{||CIT}}
        # self-reference so the citekey link shows in front of the entry.
        for ref in inv["references"]:
            body = "{{||CIT}} " + (ref.props.get("raw_text") or "")
            # tagged both `reference` and `bibentry` so existing bibentry
            # macros / updateBibentries.ts work on this output unchanged.
            t = self._t(title[ref.id], body, f"reference bibentry {_bibtag(bibkey)}")
            t["kind"] = "reference"
            t["citekey"] = ref.props.get("citekey") or ""
            t["year"] = ref.props.get("year") or ""
            t["authors"] = ref.props.get("author") or ""   # plural, matches TS
            t["entry_type"] = ref.props.get("entry_type") or "misc"
            if ref.props.get("title"):
                t["titlefield"] = ref.props["title"]
            if ref.props.get("bibtex"):          # full entry from Perplexity
                t["bibtex"] = ref.props["bibtex"]
            if ref.props.get("citations"):
                t["citations"] = ref.props["citations"]
            out.append(t)

        # Citation placeholders — only for citekeys that did NOT resolve to a
        # Reference (resolved ones link straight to the bibliographic tiddler).
        for ck, ct in getattr(self, "_cit_placeholders", {}).items():
            t = self._t(
                ct, f"//Citation placeholder for// `{ck}`",
                f"citation {_bibtag(bibkey)}",
            )
            t["citekey"] = ck
            t["text_display"] = ck
            out.append(t)

        # Synthetic Formula tiddlers (cross-line inline math residuals)
        for title_, info in synthetic_formulas.items():
            t = self._t(
                title_,
                "<$latex text={{!!latex}} displayMode={{!!displayMode}} />",
                f"formula synthetic {_bibtag(bibkey)}",
            )
            t["latex"] = info["latex"]
            t["displayMode"] = "true" if info["display"] else "false"
            out.append(t)

        # Root
        out.append(self._t(
            bibkey,
            self._root_body(bibkey, inv["pages"], inv["sections"],
                            inv["paragraphs"], inv["equations"], inv["formulas"]),
            f"document {_bibtag(bibkey)}",
        ))
        return out

    # ----- substitution -----

    def _transclude_paragraph(
        self,
        para: DocObject,
        doc: Document,
        subs_by_line: dict,
        fn_by_refnum: dict[str, str],
        inline_url_to_title: dict[str, str],
        synthetic_formulas: dict[str, dict],
        bibkey: str,
    ) -> str:
        """Rebuild paragraph text from raw lines, applying transclusions."""
        surface = next(
            (r for r in para.realizations
             if r.stream == "mathpix_lines" and r.role == "surface"
             and r.start is not None),
            None,
        )
        if surface is None:
            return latex_sectioning_to_wikitext(para.props.get("text", ""))

        stream = doc.stream("mathpix_lines")
        anchors = stream.slice_anchors(surface.start, surface.end)

        line_texts: list[str] = []
        for anchor in anchors:
            payload = stream.payload[anchor]
            raw = payload.get("text_display") or payload.get("text") or ""
            substituted = self._apply_line_substitutions(
                raw, subs_by_line.get(anchor, []))
            line_texts.append(substituted)

        joined = " ".join(t for t in line_texts if t)
        joined = self._substitute_footnotes(joined, fn_by_refnum)
        joined = self._substitute_inline_pictures(joined, inline_url_to_title)
        # Final catch-all: cross-line inline math that escaped the per-line
        # offset substitution above. These become synthetic FOX tiddlers.
        joined = self._substitute_residual_inline_math(
            joined, synthetic_formulas, bibkey)
        joined = self._substitute_eq_refs(joined)
        # Convert any leaked LaTeX sectioning command (\section*{...}) to a
        # native WikiText heading — done last so it doesn't disturb the
        # offset-based inline substitutions above.
        return latex_sectioning_to_wikitext(joined)

    def _substitute_eq_refs(self, text: str) -> str:
        """Replace in-text equation references "(N)" with {{<eq>||FREF}}.

        Only numbers that are actual equation numbers are replaced; the literal
        parenthesized form is matched, longest-first, so "(10)" isn't clobbered
        by "(1)".
        """
        for eqnum, eq_title in getattr(self, "_eqref_map", []):
            if eqnum and eqnum in text:
                text = text.replace(eqnum, "{{" + eq_title + "||FREF}}")
                self.bump("eq_ref_subs")
        return text

    @staticmethod
    def _apply_line_substitutions(
        text: str, subs: list[tuple[int, int, str]],
    ) -> str:
        """
        Apply substitutions in descending offset order so earlier offsets
        remain valid. Drop substitutions that overlap with an already-accepted
        one (defensive against pathological data).
        """
        if not subs:
            return text
        sorted_subs = sorted(subs, key=lambda s: s[0], reverse=True)
        accepted: list[tuple[int, int, str]] = []
        for off, length, repl in sorted_subs:
            end = off + length
            overlap = any(
                not (end <= o2 or off >= o2 + l2)
                for o2, l2, _ in accepted
            )
            if not overlap:
                accepted.append((off, length, repl))
        # Apply descending so earlier offsets stay valid.
        for off, length, repl in sorted(accepted, key=lambda s: s[0], reverse=True):
            text = text[:off] + repl + text[off + length:]
        return text

    @staticmethod
    def _maybe_extend_brackets(
        doc: Document, line_anchor, offset: int, length: int,
    ) -> tuple[int, int]:
        """
        Extend a citation's offset/length to consume surrounding `[` `]` if:
          - those characters are actually `[` and `]`,
          - and the span itself contains no comma (solo, not multi-cite).
        """
        stream = doc.stream("mathpix_lines")
        text = stream.payload[line_anchor].get("text_display") \
            or stream.payload[line_anchor].get("text") or ""
        if offset <= 0 or offset + length >= len(text):
            return offset, length
        if text[offset - 1] != "[" or text[offset + length] != "]":
            return offset, length
        if "," in text[offset:offset + length]:
            return offset, length
        return offset - 1, length + 2

    @staticmethod
    def _substitute_footnotes(text: str, fn_by_refnum: dict[str, str]) -> str:
        def repl(m):
            n = m.group(1) or m.group(2)
            title = (fn_by_refnum or {}).get(n)
            if title:
                return "{{" + title + "||FN}}"
            # No Footnote object for this number (common: the body refers to a
            # footnote MathPix didn't capture as a `footnote` line). Still don't
            # leak the empty-base LaTeX `\({ }^{N}\)` — render a plain
            # superscript reference so it reads as the footnote marker it is.
            return f"<sup>{n}</sup>"
        return _FN_REF_RE.sub(repl, text)

    @staticmethod
    def _substitute_inline_pictures(
        text: str, inline_url_to_title: dict[str, str],
    ) -> str:
        if not inline_url_to_title:
            return text

        def repl_with_url(url: str, original: str) -> str:
            t = inline_url_to_title.get(url)
            return ("{{" + t + "||PIC}}") if t else original

        text = _INCLUDEGRAPHICS_RE.sub(
            lambda m: repl_with_url(m.group(1).strip(), m.group(0)),
            text)
        text = _MD_IMG_RE.sub(
            lambda m: repl_with_url(m.group(1).strip(), m.group(0)),
            text)
        text = _CDN_URL_RE.sub(
            lambda m: repl_with_url(m.group(0).strip(), m.group(0)),
            text)
        return text

    def _substitute_residual_inline_math(
        self, text: str, synthetic: dict[str, dict], bibkey: str,
    ) -> str:
        """
        Catch inline math that escaped offset-based substitution (typically
        \\(...\\) that wraps across an OCR line boundary). For every distinct
        LaTeX body we create one synthetic FOX_<hash> tiddler and reuse it
        wherever the same body appears.
        """
        import hashlib

        from docmodel.modules.formula import _is_footnote_marker

        def make_repl(latex_body: str, display: bool, fallback: str) -> str:
            latex = re.sub(r"\s+", " ", latex_body).strip()
            if not latex:
                return fallback
            # A footnote-reference superscript ({ }^{N}) is NOT a formula —
            # don't synthesize a FOX tiddler for it. Leave the literal match so
            # the footnote substitution / FREF handling owns it.
            if _is_footnote_marker(latex):
                return fallback
            h = hashlib.sha1(latex.encode("utf-8")).hexdigest()[:10]
            title = f"{bibkey}_FOX_{h}"
            if title not in synthetic:
                synthetic[title] = {"latex": latex, "display": display}
                self.bump("synthetic_formulas")
            self.bump("synthetic_formula_subs")
            return "{{" + title + "||FO}}"

        # Order matters: try the more specific (display, multi-char) delimiters
        # before the less specific ones to avoid eager $ matches eating $$.
        patterns: list[tuple[str, bool]] = [
            (r"\\\[([\s\S]+?)\\\]", True),
            (r"\$\$([\s\S]+?)\$\$", True),
            (r"\\\(([\s\S]+?)\\\)", False),
            (r"\$([^$\n][^$\n]*?)\$", False),  # single-line $...$
        ]
        for pat, disp in patterns:
            text = re.sub(
                pat,
                lambda m, _d=disp: make_repl(m.group(1), _d, m.group(0)),
                text,
            )
        return text

    # ----- section body -----

    @staticmethod
    def _section_body(section: DocObject, doc: Document,
                      title: dict[str, str]) -> str:
        """
        Section body lists direct child blocks (paragraphs + non-paragraph
        blocks like equations, tables, pictures, ...) in flow order, each as
        an appropriate transclusion. Sub-sections are listed at the end as
        links so they're navigable but don't expand inline (they have their
        own tiddler).
        """
        child_blocks: list[DocObject] = []
        subsection_titles: list[str] = []
        for child_id in section.children:
            child = doc.objects.get(child_id)
            if child is None:
                continue
            if child.type == "Section":
                if child.id in title:
                    subsection_titles.append(title[child.id])
            elif child.type in _BLOCK_TYPES_IN_SECTION:
                child_blocks.append(child)
        child_blocks.sort(key=lambda o: o.props.get("flow_index", 0))

        lines: list[str] = []
        for b in child_blocks:
            if b.id not in title:
                continue
            t = title[b.id]
            # A code-listing Diagram is a fenced code block, NOT an image:
            # transclude it plainly so its own text renders, never via the
            # image-only DIA template (mirrors the standalone-emit branch).
            if b.type == "Diagram" and b.props.get("subtype") == "code":
                lines.append("{{" + t + "}}")
                continue
            tpl = {
                "Paragraph": "PARA",
                "Equation": "EQBLOCK",
                "Table": "TAB",
                "Picture": "PIC",
                "Diagram": "DIA",
                "ListItem": "LI",
                "Abstract": "ABS",
                "Toc": "TOC",
                "Sidenote": "SN",
            }.get(b.type)
            if tpl:
                lines.append("{{" + t + "||" + tpl + "}}")
            else:
                lines.append("{{" + t + "}}")
        if subsection_titles:
            lines.append("")
            lines.append("!! Subsections")
            for st in subsection_titles:
                lines.append("* <$link to=\"" + st + "\">{{" + st + "!!caption}}</$link>")
        return "\n\n".join(lines)

    @staticmethod
    def _root_body(bibkey, pages, sections, paragraphs, equations, formulas) -> str:
        return (
            f"! {bibkey}\n\n"
            f"* Total Pages: {len(pages)}\n"
            f"* Total Sections: {len(sections)}\n"
            f"* Total Paragraphs: {len(paragraphs)}\n"
            f"* Total Equations: {len(equations)}\n"
            f"* Total Formulas: {len(formulas)}\n\n"
            f"!! Top-level Sections\n\n"
            f"<$list filter=\"[tag[section]{_bibtag(bibkey)}]!has[parent_section]] "
            f"[tag[section]parent_section[{bibkey}]]\" variable=\"sec\">\n"
            f"  * <$link to=<<sec>>><<sec>></$link>\n"
            f"</$list>\n"
        )

    # ----- helpers -----

    @staticmethod
    def _sort_by_flow(objs: list[DocObject]) -> list[DocObject]:
        return sorted(objs, key=lambda o: o.props.get("flow_index", 10**9))

    def _uri(self, url: str) -> str:
        """Pass a URL through, or base64-embed it as a data: URI when the
        projector is in --embed mode (self-contained tiddlers)."""
        return embed_image(url) if self.params.get("embed") else url

    @staticmethod
    def _p3(value) -> str:
        """Zero-padded 3-digit page field, e.g. 7 -> '007'."""
        return f"{int(value or 0):03d}"

    @staticmethod
    def _copy_region(t: dict, props: dict) -> None:
        """Copy a region's geometry fields onto a tiddler as string values."""
        region = props.get("region") or {}
        for k in ("height", "width", "top_left_x", "top_left_y"):
            if region.get(k):
                t[k] = str(region[k])

    @staticmethod
    def _t(title: str, text: str, tags: str) -> dict:
        now = _tw_now()
        return {
            "title": _sanitize_title(title),
            "text": text,
            "type": "text/vnd.tiddlywiki",
            "tags": tags,
            "created": now,
            "modified": now,
        }

    def _emit_svg_tiddler(self, out: list, base_title: str, svg: str | None,
                          bibkey: str) -> str | None:
        """If `svg` is a rendered SVG, append a separate `<base>_svg` image
        tiddler (`type: image/svg+xml`, the SVG as its text) and return its
        title; else return None. The owning diagram/table tiddler links it via
        `<$image source="<title>">` and an `svg_tiddler` field."""
        if not svg or not svg.strip():
            return None
        svg_title = _sanitize_title(f"{base_title}_svg")
        st = self._t(svg_title, svg, f"svg {_bibtag(bibkey)}")
        st["type"] = "image/svg+xml"
        out.append(st)
        return svg_title

    @staticmethod
    def _templates(bibkey: str) -> list[dict]:
        """
        Built-in templates referenced by transclusions in paragraph and
        section bodies. Each template renders a tiddler under a particular
        role; the template tiddler's text uses field references on the
        currentTiddler context.
        """
        now = _tw_now()
        templates = [
            # FO — inline formula. Uses the formula tiddler's own !!latex.
            ("FO", "<$latex text={{!!latex}} displayMode={{!!displayMode}}/>"),

            # CIT — inline citation: link to the citation placeholder showing the citekey.
            ("CIT", "[<$link to={{!!title}}>{{!!citekey}}</$link>]"),

            # FN — footnote reference: superscript link.
            ("FN", "<sup><$link to={{!!title}}>{{!!refnum}}</$link></sup>"),

            # PIC — inline picture (small).
            ("PIC", "<$image source={{!!canonical_uri}} width=\"320\"/>"),

            # PARA — paragraph body, wrapped in <p>.
            ("PARA", "<p>{{!!text}}</p>"),

            # EQBLOCK — display equation: numbered, centered.
            ("EQBLOCK",
             "<div class=\"equation\"><$latex text={{!!latex}} displayMode=true/>"
             " <span class=\"refnum\">{{!!refnum}}</span></div>"),

            # EQ — inline equation reference ("see Equation 1.1").
            ("EQ", "<$link to={{!!title}}>{{!!kind}} {{!!refnum}}</$link>"),

            # FO — already defined above; display the equation/formula latex.
            # FREF — equation reference: the displayed number, linked to the eq.
            ("FREF", "<$link to={{!!title}}>{{!!equation_number}}</$link>"),

            # TAB — table block.
            ("TAB", "<div class=\"table\">{{!!text}}</div>"),

            # DIA — diagram (medium size).
            ("DIA", "<$image source={{!!canonical_uri}} width=\"480\"/>"),

            # LI — list item.
            ("LI", "<li>{{!!text}}</li>"),

            # ABS — abstract block.
            ("ABS", "<div class=\"abstract\">{{!!text}}</div>"),

            # TOC — table of contents.
            ("TOC", "<div class=\"toc\">{{!!text}}</div>"),

            # SN — sidenote.
            ("SN", "<aside>{{!!text}}</aside>"),
        ]
        return [
            {
                "title": name,
                "text": text,
                "type": "text/vnd.tiddlywiki",
                "tags": "template",
                "created": now,
                "modified": now,
            }
            for name, text in templates
        ]
