"""
LaTeXProjector — project a drilled Document to a compilable `.tex` document.

The LaTeX analog of the Markdown projector: sections → `\\section`/`\\subsection`,
prose paragraphs (their materialized text, inline math kept as `$…$`), display
equations → an `equation` environment carrying the object's `\\label`, tables →
their gold `latex_code` when present (else the raw grid), figures/diagrams noted.

This is the OUTPUT direction. `injectlatex` is the INPUT one (pull the author's
`.tex` source in as gold provenance). `pdfdrill latex` drives this projector.

Deliberately format-faithful, not semantic: it renders what the model holds. For
enriched LaTeX (acronyms/glossary/index, ORKG metadata) see `stex` / `scikgtex`.
"""
from __future__ import annotations

import re

from docmodel.core import Document
from ..base import BaseProjector
from ..conserve import CONTAINER_TYPES as _CONTAINER_TYPES_TUPLE
from .common import flow_ordered_content, equation_label
from . import latex_pipeline as _pipe
from . import footnotes as _fn
from . import citations as _cit
from .tiddlywiki import titles_by_id as _titles_by_id
from .tiddlywiki import parse_title as _parse_title

#: 635 — reuse 634/646's container exclusion (`Page` spans its page BY
#: CONSTRUCTION, never by claim) rather than reinventing it: a Page is never
#: a flow content type either (see `common.CONTENT_TYPES`), so it could never
#: have rendered standalone, and counting it as "suppressed" would report an
#: action that never happens.
_CONTAINER_TYPES = frozenset(_CONTAINER_TYPES_TUPLE)

#: 640-a — templates whose target ALSO renders as a standalone block, so a
#: materialised transclusion of it means "printed here, not there". Keyed by
#: template, valued by the object type the title must name.
_TRANSCLUDED_STANDALONE = {
    "FN": "Footnote", "SN": "Sidenote", "PIC": "Picture", "DIA": "Diagram",
    "TAB": "Table", "LI": "ListItem", "PARA": "Paragraph", "ABS": "Abstract",
    "PROOF": "Proof", "TOC": "Toc",
}

#: 635 — the manual TOC headings a `\tableofcontents` supersedes. Dropped by
#: NAME, per the brief: a document with a Toc object does not also print a
#: hand-written "Contents" section holding nothing (or the orphan maths
#: MathPix cut out of a contents line). Measure/List of Figures/List of
#: Tables are NOT separately represented in the model (one flat Toc
#: `entries`/`rows` list, no sub-region boundary — out/635.txt) so there is
#: no evidence to emit `\listoffigures`/`\listoftables` from; their entries
#: stay dropped-and-counted under `toc_region_suppressed` like every other
#: TOC-line fragment.
_TOC_WRECKAGE_TITLES = {"Contents", "List of Figures", "List of Tables"}

# level → sectioning command (1-indexed; clamped)
_SECTION_CMDS = ["section", "section", "subsection", "subsubsection",
                 "paragraph", "subparagraph"]

_DEFAULT_PREAMBLE = (
    "\\documentclass[11pt]{article}\n"
    # Compiled with XELATEX (see cmd_latex): it is natively UTF-8, so NO
    # inputenc/fontenc — `\\usepackage[utf8]{inputenc}` actively CLASHES with
    # xelatex and the model can carry raw Unicode inputenc/pdflatex would reject.
    # amsmath/symb/fonts + bm (\bm), mathtools, xcolor/url (leaked commands),
    # booktabs/multirow (tables) — the packages a projected paper commonly needs.
    "\\usepackage{amsmath,amssymb,amsfonts,mathtools,bm}\n"
    "\\usepackage{graphicx,booktabs,multirow,xcolor,url,hyperref}\n"
)


def _escape_text(s: str) -> str:
    """Escape the LaTeX specials in a caption/title/author. IDEMPOTENT (`(?<!\\\\)`):
    an already-escaped `C\\#` from the source is NOT doubled into `C\\\\#` (which is
    a line break + a bare `#` → error). `$`, `\\`, `{`, `}`, `^` are left alone so
    inline math / already-LaTeX spans the model carries survive."""
    s = re.sub(r"(?<!\\)&", r"\\&", s)
    s = re.sub(r"(?<!\\)%", r"\\%", s)
    s = re.sub(r"(?<!\\)#", r"\\#", s)
    s = re.sub(r"(?<!\\)_", r"\\_", s)
    s = re.sub(r"(?<!\\)~", r"\\textasciitilde{}", s)
    return s


def _balance_braces(s: str) -> str:
    """Contain a runaway brace to THIS block — the brace analogue of
    `latex_pipeline.balance_math`, and needed for the same reason.

    MEASURED, not defensive: 1 penev_A and 4 penev_B Paragraphs carry a
    `\\footnotetext{` that MathPix left in the prose of a line the paragraph
    ALSO claims (646's Footnote+Paragraph doubly-claimed class), and one of
    penev_B's is never closed. Emitted verbatim it swallows the rest of the
    file: 'File ended while scanning use of \\@footnotetext', Emergency stop,
    and every page after it is simply absent from the PDF. 0 Footnote BODIES
    are unbalanced on either document — the runaway is in prose."""
    opens = len(re.findall(r"(?<!\\)\{", s))
    closes = len(re.findall(r"(?<!\\)\}", s))
    if opens > closes:
        return s + "}" * (opens - closes)
    if closes > opens:
        return "{" * (closes - opens) + s
    return s


class LaTeXProjector(BaseProjector):

    def output_extension(self) -> str:
        return ".tex"

    def project(self, doc: Document) -> str:
        meta = doc.meta
        self._prepare(doc)

        # Render the BODY first: it decides which graphics packages the preamble
        # must load (a Diagram's `tikzpicture` / `\addplot` in a table).
        items = [o for o in flow_ordered_content(doc) if o.id not in self._skip_ids]
        body_blocks = self._render_flow(items)
        body_text = "\n".join(body_blocks)

        preamble = self._doc_preamble(meta)
        out: list[str] = [preamble.rstrip()]
        # graphics setup (tikz/pgfplots/definecolor/…) the body needs but the
        # default preamble lacks — pulled from the source's captured preamble.
        gfx = _pipe.graphics_preamble(doc, body_text)
        if gfx:
            out += ["% graphics setup (tikz/pgfplots) carried from the source:", gfx]
        out.append("")
        if self._formula_preamble:                # the formula ARRAY (readarray)
            out += ["% formula transclusion array (filecontents + readarray):",
                    self._formula_preamble, ""]

        title = meta.get("title") or self._leaked_title(doc)
        authors = meta.get("authors") or []
        if title:
            out.append(f"\\title{{{_escape_text(str(title))}}}")
        if authors:
            names = " \\and ".join(_escape_text(str(a)) for a in authors)
            out.append(f"\\author{{{names}}}")
        out.append("\\begin{document}")
        if title:
            out.append("\\maketitle")
        out.append("")

        # STAGE 3: the Acronyms list (front matter)
        gloss = _pipe.glossary_block(self._acronyms)
        if gloss:
            out += [gloss, ""]

        out += body_blocks

        # STAGE 2: bibliography — printed `\bibitem`s from the model's References.
        bib = _pipe.bibliography_block(doc)
        if bib:
            out.append(bib)
            out.append("")

        out.append("\\end{document}")
        return "\n".join(out).rstrip() + "\n"

    # ── shared setup + rendering (reused by the beamer projector) ────────────

    def _prepare(self, doc: Document) -> None:
        """Set up the pipeline state used by the content renderers: the
        transclusion ARRAY (`{{id||FO}}`→`\\Expr{i}`), the citation reference map
        (`[N]`→`\\cite`), and the References-section skip set."""
        key = str(doc.meta.get("bibkey") or "DOC")
        # Anchor the SHALLOWEST section to `\section` (level 1), exactly like the
        # fractal-index TOC. A paper whose top sections are level 2 (no `\section`
        # in the model) would otherwise render `\subsection{Introduction}` →
        # numbered 0.1; the shift makes it `\section{Introduction}` → 1.
        levels = [int(o.props.get("level", 1) or 1)
                  for o in doc.objects.values() if o.type == "Section"]
        self._level_shift = (min(levels) - 1) if levels else 0
        self._order, self._title_index = _pipe.formula_array(doc)
        self._formula_preamble = _pipe.formula_preamble(
            self._order, f"{key}.formulas.dat")
        self._ref_map = _pipe.reference_map(doc)
        self._skip_ids = _pipe.reference_section_ids(doc) if self._ref_map else set()
        # 638 — pair every running-text footnote MARKER with its Footnote body.
        # A body that a marker takes is printed by that marker's paragraph
        # (`\footnotetext[n]{…}`), so it must not ALSO be emitted standalone.
        self._footnotes = _fn.resolve(doc)
        # 642 — every in-text Citation back into the running text as `\cite`,
        # by GROUP, through the same `docops.citation_spans` the TiddlyWiki
        # projector reads. Resolved once here so `_cite` is a lookup.
        self._citations = _cit.resolve(doc)
        self._doc_objects = doc.objects
        self._skip_ids = set(self._skip_ids) | set(self._footnotes.used)
        # 637 — the maths a footnote body already prints. MathPix extracts the
        # maths INSIDE a footnote body as its own Formula on the body's line, so
        # the projection printed it inside the `\footnotetext{…}` AND again as a
        # standalone `$…$` block. Only a Formula whose latex the body actually
        # carries is folded; see `footnotes.body_math_ids` for why 'inside a
        # body' alone would be loss.
        self._skip_ids |= set(self._footnotes.body_math)
        # 640-a — the MATERIALISED lane. After `clean`, a paragraph's prose is
        # the TiddlyWiki projection, so its footnote markers and citations are
        # `{{<title>||FN}}` / `{{<title>||CIT}}` rather than raw LaTeX. Build
        # the title→object index ONCE (from the tiddler projector's own
        # numbering, not a second copy of it) and a handler per template.
        self._by_title = {}
        try:
            for oid, t in _titles_by_id(doc, key).items():
                obj = doc.objects.get(oid)
                if obj is not None:
                    self._by_title[t] = obj
        except Exception:                                 # noqa: BLE001
            self._by_title = {}
        self._template_counts: dict[str, int] = {}
        self._notes_emitted: set = set()
        self._tpl_handlers = self._template_handlers()
        self._pending_notes: list[str] = []
        self._in_footnote_body = False
        self._tpl_depth = 0
        # An object a materialised marker TRANSCLUDES is printed by the block
        # that carries the marker, so it must not ALSO be emitted standalone.
        # Pre-computed here and not while rendering: `_skip_ids` is read ONCE,
        # before the first block, so an in-render `add` would come too late for
        # anything earlier in the flow and would silently double-print it.
        # Only the templates whose handler is guaranteed to render (the object
        # exists, of the right type) are pre-skipped — skipping an object whose
        # handler then returns None would DROP it.
        for obj in doc.objects.values():
            if obj.type not in _fn.RUNNING_TEXT_TYPES:
                continue
            text = _fn.object_text(obj)
            for tpl, want in _TRANSCLUDED_STANDALONE.items():
                for t in _pipe.marker_titles(text, tpl):
                    o = self._by_title.get(t)
                    if o is not None and o.type == want and o.id != obj.id:
                        self._skip_ids.add(o.id)
        # 635 — the table of contents as a COMMAND, not as its wreckage. A Toc
        # object (`docmodel.modules.toc.TocProcessor`) is `derived: True`
        # (262: every entry duplicates a `section_header` elsewhere in the
        # document); `_render`'s "Toc" branch emits `\tableofcontents` from it
        # once, at its own flow position. What has to leave the projection is
        # (a) the wreckage Section objects titled Contents / List of Figures /
        # List of Tables — a publication does not print its own table of
        # contents twice, by NAME, exactly as the brief states it — and (b)
        # every OTHER object anchored on a line the Toc's own realization
        # spans. (b) is NOT 634/646's block/inline "claim" rule — that rule
        # exists to stop a Formula NESTED inside a paragraph's line from
        # looking like a second consumption of that line, which is a
        # question about the INPUT side. Here the question is the OUTPUT
        # side: does this object print standalone in the flow at all? And it
        # measurably does — penev_A's 23 orphan `$T=15$`-shaped Formulas
        # carry ONLY inline (sub-anchor) realizations on their TOC lines (no
        # Paragraph claims a TOC line to transclude them FROM), so under the
        # block-only rule they were never caught and kept printing (out/635
        # first run). A Formula's flow position is its EARLIEST realization
        # (`document_flow.DocumentFlowProcessor`, `surface[0]`); measured on
        # penev_A, every object touching the Toc's span at all has that
        # earliest realization INSIDE the span too (0 counterexamples), so an
        # object suppressed here never had a legitimate rendering anywhere
        # else — it is printed exactly once, and that once is the TOC.
        # CONTAINER_TYPES (`Page`, 634/646's own exclusion) are skipped: a
        # Page's realization spans its whole page BY CONSTRUCTION, not by
        # claim, and it is not a flow content type in the first place — never
        # rendered standalone regardless, so counting it as "suppressed"
        # would report an action that never happens (rule 11).
        # Evidence off the Toc's own anchors, never a guess by position or by
        # title: on penev_A the "Contents" and "List of Figures"
        # section_header lines sit just OUTSIDE the Toc's own claimed range
        # (`TocProcessor` only walks `table_of_contents_*`-typed lines, so its
        # first/last anchor is never a `section_header`), which is exactly
        # why (a) is a separate, title-driven rule and not derived from (b) —
        # see out/635.txt.
        # Gated on a Toc actually existing: with none, nothing here fires, and
        # a Section that happens to be titled "Contents" is left exactly as
        # the model states it (there is no `\tableofcontents` to justify
        # dropping it).
        self._toc_region_suppressed: dict[str, int] = {}
        self._toc_emitted = False
        tocs = doc.objects_of_type("Toc")
        if tocs:
            lines_stream = doc.streams.get("mathpix_lines")
            toc_span: set = set()
            if lines_stream is not None:
                for toc in tocs:
                    for r in toc.realizations:
                        if r.stream != "mathpix_lines" or r.role != "surface" \
                                or r.start is None:
                            continue
                        end = r.end if r.end is not None else r.start
                        try:
                            toc_span.update(a.id for a in
                                            lines_stream.slice_anchors(r.start, end))
                        except KeyError:
                            continue
            for obj in doc.objects.values():
                if obj.id in self._skip_ids or obj.type == "Toc" \
                        or obj.type in _CONTAINER_TYPES:
                    continue
                bump = None
                cap = str(obj.props.get("caption") or "").strip()
                if obj.type == "Section" and cap in _TOC_WRECKAGE_TITLES:
                    bump = obj.type
                elif toc_span:
                    for r in obj.realizations:
                        if r.stream != "mathpix_lines" or r.role != "surface" \
                                or r.start is None:
                            continue
                        end = r.end if r.end is not None else r.start
                        try:
                            span = lines_stream.slice_anchors(r.start, end)
                        except KeyError:
                            continue
                        if any(a.id in toc_span for a in span):
                            bump = obj.type
                            break
                if bump is not None:
                    self._skip_ids.add(obj.id)
                    self._toc_region_suppressed[bump] = \
                        self._toc_region_suppressed.get(bump, 0) + 1
        # STAGE 3: acronyms / glossary from the named-concept layer (lazy — the
        # `semantic` package; degrade to none if unavailable).
        self._acronyms: list = []
        try:
            from semantic import concepts as _concepts
            self._acronyms = [(r.get("name"), r.get("expansion"))
                              for r in _concepts.concept_records(doc)
                              if r.get("name") and r.get("expansion")]
        except Exception:                                 # noqa: BLE001
            self._acronyms = []

    def _leaked_title(self, doc) -> str | None:
        """When the model carries no `meta['title']` (common on a LaTeX-source
        build), recover a `\\title{…}` the builder left in body prose, so the
        projection gets a real `\\title` instead of a `\\maketitle` with none."""
        for obj in doc.objects.values():
            if obj.type in ("Paragraph", "Abstract"):
                t = _pipe.leaked_title(str(obj.props.get("text") or ""))
                if t:
                    return t
        return None

    def _doc_preamble(self, meta) -> str:
        """A document-specific preamble captured by `injectlatex` (macros the
        equations need) wins; else a sane default. May be a plain string OR a dict
        ({"expanded"/"standalone": …}); coerce to a usable string.

        A `standalone` preamble is REJECTED: it typesets the body in a box (LR
        mode) for CROPPING figures in the SVG step, so `\\section` errors 'Not
        allowed in LR mode' in a full document. Fall back to the article default."""
        pre = meta.get("latex_preamble")
        if isinstance(pre, dict):
            pre = pre.get("expanded") or pre.get("standalone") or pre.get("preamble")
        if not (isinstance(pre, str) and pre.strip()):
            return _DEFAULT_PREAMBLE
        if re.search(r"\\documentclass\s*(\[[^\]]*\])?\s*\{\s*standalone\s*\}", pre):
            return _DEFAULT_PREAMBLE                 # figure-crop preamble → not a document
        return pre

    def _render_flow(self, items) -> list[str]:
        """Render a flat list of objects to LaTeX blocks, grouping consecutive
        ListItems into one `itemize` (bare `\\item` is invalid). Returns blocks
        (each followed by a blank line)."""
        out: list[str] = []
        i = 0
        while i < len(items):
            obj = items[i]
            if obj.type == "ListItem":
                run = []
                while i < len(items) and items[i].type == "ListItem":
                    run.append(items[i]); i += 1
                out.append(self._render_list(run))
                out.append("")
                continue
            block = self._render(obj)
            if block:
                out.append(block)
                out.append("")
            i += 1
        return out

    def _render_list(self, run) -> str:
        """A run of ListItems → one `itemize`; each item keeps its source marker
        as the `[label]` (braced so a bracket in the marker is safe), and its
        content passes through `_prose` (transclusions / citations resolve)."""
        lines = ["\\begin{itemize}"]
        for it in run:
            self._sup_page = it.props.get("page")
            marked, notes = self._mark_footnotes(it, self._cite(it))
            content, owed = self._prose_notes(marked.strip())
            notes = notes + owed                  # 640-a: materialised {{…||FN}}
            if notes:
                content = " ".join([content] + notes)
            marker = str(it.props.get("marker") or "").strip()
            label = f"[{{{marker}}}]" if marker else ""
            lines.append(f"  \\item{label} {content}".rstrip())
        lines.append("\\end{itemize}")
        return "\n".join(lines)

    # ── 642: citations ───────────────────────────────────────────────────────

    def _cite(self, obj, text: str | None = None) -> str:
        """`text` (default: the object's own) with each citation GROUP replaced
        by one `\\cite{a,b}`.

        Runs BEFORE `_mark_footnotes`, and must: a numeric citation group is the
        literal `[2]`, and once a footnote marker has become `\\footnotemark[2]`
        a literal search for `[2]` would find the mark's own optional argument.
        The reverse order is safe — `\\cite{…}` carries no inline-math span, so
        the marker sequence `_mark_footnotes` re-derives is untouched by it.

        EVERY caller that emits prose goes through here (fix round 2). A block
        this cannot resolve — no object to resolve against — gets NO citation
        rewriting at all rather than the number map's, because the number map
        does not know which Citation owns a bracket."""
        if text is None:
            text = _fn.object_text(obj)
        res = getattr(self, "_citations", None)
        if res is None:
            return text
        subs = res.subs_for(obj.id)
        if not subs:
            return text
        return _cit.apply_subs(
            text, subs,
            on_missing=lambda s: res.counts.__setitem__(
                "cite_source_not_in_text",
                res.counts["cite_source_not_in_text"] + 1))

    # ── 638: footnote markers ────────────────────────────────────────────────

    def _mark_footnotes(self, obj, text: str | None = None) -> tuple[str, list[str]]:
        """`(running text with each resolved marker replaced, the
        `\\footnotetext[n]{…}` blocks those marks owe)`.

        One walk, three outcomes, decided by `footnotes.resolve` and only read
        here: a marker with a Footnote body on its page becomes
        `\\footnotemark[n]` (638); a marker with none whose number names a
        NUMBERED bibitem becomes `\\cite{<citekey>}` (641 — a superscript
        citation is the same maths as a footnote marker, and the document, not
        the maths, tells them apart); anything else stands.

        An UNRESOLVED marker is left byte-for-byte as it was — the resolution
        counts it (`markers_unresolved`) rather than guessing a body. When the
        object's text no longer holds the markers the resolution was built from,
        nothing is substituted at all: a positional edit against a text that
        moved would replace the wrong characters.

        `text` defaults to the object's own text; 642 passes the text its
        citation groups have already been substituted into."""
        if text is None:
            text = _fn.object_text(obj)
        res = getattr(self, "_footnotes", None)
        if res is None:
            return text, []
        marks = res.marks_for(obj.id)
        if not marks:
            return text, []
        found = _fn.find_markers(text)
        if [rn for _s, _e, rn in found] != [m.refnum for m in marks]:
            return text, []
        out: list[str] = []
        notes: list[str] = []
        last = 0
        for (start, end, refnum), mark in zip(found, marks):
            out.append(text[last:start])
            if mark.footnote_id:
                out.append(f"\\footnotemark[{refnum}]")
                fn = self._doc_objects.get(mark.footnote_id)
                if fn is not None:
                    notes.append(self._footnotetext(fn))
            elif mark.citekey:
                # 641 — the key comes from the numbered Reference, so the
                # `\bibitem` 639 emits for that Reference exists by
                # construction and the key cannot dangle.
                out.append("\\cite{" + mark.citekey + "}")
            else:
                out.append(text[start:end])
            last = end
        out.append(text[last:])
        return "".join(out), notes

    def _sup_marker(self, n: str) -> str | None:
        """`<sup>n</sup>` — the MATERIALISED spelling of the bare `{ }^{n}`
        `_mark_footnotes` walks, and it goes through the SAME rule
        (`footnotes.decide`) so the two spellings cannot disagree.

        641 fix round 1, ruled from 641-a: 640 turned every `<sup>n</sup>` into
        `\\footnotemark[n]` unconditionally, which is right for a mark whose body
        is merely missing and WRONG for a numeric citation superscript on a
        cleaned document — rule (b) never got a look. It gets one here, second,
        after the page lookup, exactly as it does in the bare walk.

        `\\footnotemark[n]` is this spelling's "stands": the tiddler projector
        already decided it is a mark, and reverting to the literal `<sup>` tag is
        640-a. The three outcomes are counted on the resolution the projector
        printed, so the lane is visible rather than inferred."""
        res = getattr(self, "_footnotes", None)
        if res is None:
            return None
        # `used` — the bodies the BARE walk already consumed. This lane asks
        # `decide` to run rule (a) itself, so it must not be handed a body an
        # earlier marker took (638-e; fix round 2).
        d = _fn.decide(n, getattr(self, "_sup_page", None), res.lookups,
                       rule_a=_fn.BY_LOOKUP, used=res.used)
        res.counts["sup_markers"] += 1
        if d.outcome == "cite":
            res.counts["sup_marker_cited"] += 1
            res.counts["markers_cited"] += 1
            return "\\cite{" + d.citekey + "}"
        if d.outcome == "footnote":
            res.counts["sup_marker_footnote"] += 1
            if d.both:
                res.counts["sup_marker_both"] += 1
                res.counts["marker_both"] += 1
            return None                        # the default IS \footnotemark[n]
        res.counts["sup_marker_default"] += 1
        return None

    def _footnotetext(self, fn) -> str:
        """A Footnote body as `\\footnotetext[n]{…}` — the PRINTED number, so the
        projection reads like the publication. Without a `refnum` the optional
        argument is omitted rather than emitted empty (`\\footnotetext[]{}` is a
        LaTeX error). The body goes through `_prose`, not `_escape_text`: the
        latter escapes `_` inside maths too and turned `\\(F_{r}\\)` into
        `\\(F\\_{r}\\)` — both of penev_A's 'Missing $ inserted' errors.

        637 — the body is `footnotes.body_text(fn)`: the CLEANED realization
        when the object has one, else the `content` prop. ONE of them, never
        both."""
        # fix round 2 — the body's citations go through the RESOLVER, like every
        # other block of prose. It was the last caller on the old number map,
        # and Citations do sit on footnote lines (8 penev_A / 5 penev_B), so the
        # mis-wire was live here AND a footnote-body citation reached the page
        # as nothing at all (645-a, closed for this lane).
        was = getattr(self, "_in_footnote_body", False)
        was_page = getattr(self, "_sup_page", None)
        self._in_footnote_body = True                     # no \footnotetext nesting
        # the page this BODY is on — otherwise a `<sup>n</sup>` inside it would
        # be decided against whatever block was rendered last (fix round 2).
        self._sup_page = fn.props.get("page")
        try:
            body = self._prose(
                self._cite(fn, _fn.body_text(fn)).strip())
        finally:
            self._in_footnote_body = was
            self._sup_page = was_page
        body = re.sub(r"\n\s*\n+", " ", body).strip()     # no \par inside a footnote
        refnum = str(fn.props.get("refnum") or "").strip()
        opt = f"[{refnum}]" if refnum.isdigit() else ""
        return f"\\footnotetext{opt}{{{body}}}"

    # ── 640-a: one branch per TiddlyWiki template ────────────────────────────

    def _template_handlers(self) -> dict:
        """`{TPL: f(title) -> str | None}` — the object-aware half of
        `latex_pipeline.TEMPLATE_ACTIONS`. This module has the Document; the
        pipeline module does not, which is the whole reason the table is split.

        Returning None means "not renderable from that title", and the pipeline
        then COUNTS the marker instead of printing it. Nothing here may return a
        literal `(?…)` — that placeholder is what 640-a is.
        """
        block = lambda title: self._transcluded_block(title)      # noqa: E731
        return {
            "FO": self._math_token, "FREF": self._math_token,
            "EQ": self._math_token, "EQBLOCK": self._math_token,
            "CIT": self._cite_token,
            "FN": self._footnote_token,
            "SN": self._sidenote_token,
            "PIC": block, "DIA": block, "TAB": block, "LI": block,
            "PARA": block, "ABS": block, "PROOF": block, "TOC": block,
        }

    def _math_token(self, title: str) -> str | None:
        """The array lookup first (`\\Expr{i}` — one slot per distinct body);
        failing that the object's own LaTeX inline, so an unindexed formula is
        still typeset rather than dropped."""
        idx = getattr(self, "_title_index", {}).get(title)
        if idx is not None:
            return f"\\Expr{{{idx}}}"
        obj = self._by_title.get(title)
        if obj is None:
            return None
        latex = _pipe.sanitize_math(str(obj.props.get("latex") or "").strip())
        return f"${latex}$" if latex else None

    def _cite_token(self, title: str) -> str | None:
        """`{{<bibkey>_REF_<citekey>||CIT}}` → `\\cite{<citekey>}`.

        The citekey comes from `parse_title` (the ONE title reader) when the
        title parses, and from the object's own `citekey` prop otherwise — a
        materialised CIT names its REF tiddler, so this is exact and needs none
        of 642's span arithmetic."""
        obj = self._by_title.get(title)
        if obj is not None and obj.type == "Reference":
            key = str(obj.props.get("citekey") or "").strip()
            if key:
                return f"\\cite{{{key}}}"
        parsed = _parse_title(title)
        if parsed is not None and parsed.key:
            return f"\\cite{{{parsed.key}}}"
        return None

    def _footnote_token(self, title: str) -> str | None:
        """`{{<bibkey>_FN0003||FN}}` → `\\footnotemark[n]`, and the body is owed
        as `\\footnotetext[n]{…}` at the end of the block that carries the mark.

        A MATERIALISED marker names its Footnote by TITLE, so there is no
        disambiguation to do: 638's page/refnum rule exists for a BARE
        `{ }^{n}` marker, which carries no identity at all. The two lanes live
        side by side — `_mark_footnotes` still owns the bare ones.

        Inside a footnote body a nested mark emits the SUPERSCRIPT only:
        `\\footnotetext` inside `\\footnotetext` is a LaTeX error, and 638
        measured that a marker inside a body is usually the next body's printed
        label rather than a reference."""
        fn = self._by_title.get(title)
        if fn is None or fn.type != "Footnote":
            return None
        refnum = str(fn.props.get("refnum") or "").strip()
        mark = f"\\footnotemark[{refnum}]" if refnum.isdigit() else "\\footnotemark"
        if self._in_footnote_body:
            return mark
        if fn.id not in self._notes_emitted:
            self._notes_emitted.add(fn.id)
            self._pending_notes.append(self._footnotetext(fn))
        return mark

    def _sidenote_token(self, title: str) -> str | None:
        """`{{…||SN}}` → `\\marginpar{\\footnotesize …}`.

        STATED CHOICE: a margin note, not a footnote. The TiddlyWiki template is
        `<aside>` — margin typography — and the model keeps Sidenote and
        Footnote apart on purpose; collapsing a sidenote into the footnote
        stream would renumber the footnotes the publication printed, which is
        the one thing 638 exists to preserve. `\\marginpar` is the article
        class's own margin note, so the result reads like the publication.
        """
        sn = self._by_title.get(title)
        if sn is None:
            return None
        # the page of the SIDENOTE, not of whatever block was rendered last —
        # a `<sup>n</sup>` inside this body is decided against it (fix round 2).
        was_page = getattr(self, "_sup_page", None)
        self._sup_page = sn.props.get("page")
        try:
            body = self._prose(str(sn.props.get("text")
                                   or sn.props.get("content") or "").strip())
        finally:
            self._sup_page = was_page
        body = re.sub(r"\n\s*\n+", " ", body).strip()
        if not body:
            return None
        return f"\\marginpar{{\\footnotesize {body}}}"

    def _transcluded_block(self, title: str) -> str | None:
        """A BLOCK template (PIC/DIA/TAB/LI/PARA/ABS/PROOF/TOC) transcluded into
        prose: render the object exactly as it would render standalone, so
        there is one renderer per type and not two. Depth-guarded — a paragraph
        that transcludes itself would otherwise recurse forever."""
        obj = self._by_title.get(title)
        if obj is None or self._tpl_depth >= 3:
            return None
        self._tpl_depth += 1
        try:
            out = self._render(obj)
        finally:
            self._tpl_depth -= 1
        if not out.strip():
            return None
        return out

    def _prose_notes(self, text: str) -> tuple[str, list[str]]:
        """`_prose`, plus the `\\footnotetext[n]{…}` blocks that the materialised
        `{{…||FN}}` markers inside `text` owe to the block carrying them."""
        before = len(self._pending_notes) if hasattr(self, "_pending_notes") else 0
        out = self._prose(text)
        owed = self._pending_notes[before:]
        del self._pending_notes[before:]
        return out, owed

    def _prose(self, text: str) -> str:
        """Resolve a prose block to LaTeX: transclusion markers → `\\Expr{<index>}`
        (readarray lookup), leaked Markdown headings → `\\section`. Line-wise so a
        heading mid-paragraph still converts.

        IT DOES NOT TOUCH CITATIONS. `_pipe.resolve_citations` used to run here,
        rewriting any `[N]` bracket through `{Reference.number: citekey}` with no
        idea which Citation owns it — so after `_cite` had decided, it UNDID the
        decision: a Citation `NoSuchKey` over `[5]`, left verbatim and counted,
        became `\\cite{Realname2001}` because an unrelated Reference was numbered
        5. It compiles, and it cites the wrong paper. Every caller now runs
        `_cite` first (Paragraph/Abstract, ListItem, Footnote body, the beamer
        Abstract), and the numeric fallback lives in `projectors.citations`
        behind the claim, so this method has no citation branch left to
        disagree with."""
        ti = getattr(self, "_title_index", {})
        text = _pipe.clean_prose(text)                # ligatures + leaked \bibliography
        text = _pipe.resolve_transclusions(
            text, ti, handlers=getattr(self, "_tpl_handlers", None),
            counts=getattr(self, "_template_counts", None))
        # `<sup>N</sup>` — what the tiddler projector emits for a marker whose
        # refnum names no Footnote. A mark with no body IS `\footnotemark[N]`.
        text = _pipe.resolve_sup_markers(
            text, getattr(self, "_template_counts", None),
            handler=self._sup_marker)
        # contain any runaway inline math (a dropped `\)`/`$`) to THIS block, so
        # it can't swallow the next \section ("Not allowed in LR mode").
        text = _pipe.balance_math(text)
        text = _balance_braces(text)                  # and a runaway brace
        # headings FIRST (so a leaked `## X` still matches — escaping `#` would
        # break it), THEN escape prose specials (`#`/`%`/`&` outside math).
        lines = (_pipe.resolve_headings(ln) for ln in text.split("\n"))
        return "\n".join(_pipe.escape_prose_specials(ln) for ln in lines)

    def _render(self, obj) -> str:
        t, p = obj.type, obj.props
        # the page the `<sup>n</sup>` handler resolves against — the block being
        # emitted, which is where that marker is printed.
        self._sup_page = p.get("page")
        if t == "Section":
            lvl = int(p.get("level", 1) or 1) - getattr(self, "_level_shift", 0)
            cmd = _SECTION_CMDS[max(1, min(len(_SECTION_CMDS) - 1, lvl))]
            cap = _escape_text(str(p.get("caption") or "").strip())
            if not cap:
                return ""
            s = f"\\{cmd}{{{cap}}}"
            label = p.get("label")
            return s + (f"\n\\label{{{label}}}" if label else "")
        if t in ("Paragraph", "Abstract"):
            marked, notes = self._mark_footnotes(obj, self._cite(obj))
            text, owed = self._prose_notes(marked.strip())
            notes = notes + owed                  # 640-a: materialised {{…||FN}}
            if not text.strip():
                return ""
            if t == "Abstract":
                text = f"\\begin{{abstract}}\n{text}\n\\end{{abstract}}"
            # the bodies this paragraph's marks own, at the END of the paragraph
            # that carries the mark (so `\footnotetext` executes on the page the
            # mark was set on).
            return "\n".join([text] + notes) if notes else text
        if t == "Equation":
            latex = _pipe.sanitize_math((p.get("latex") or "").strip())
            if not latex:                                 # CDN-crop-only — nothing to typeset
                return ""
            label = p.get("label") or equation_label(obj)
            lab = f"\n\\label{{{label}}}" if label else ""
            # TRANSCLUDE from the readarray array (`\EqExpr{i}`) — consistent with
            # inline `\Expr{i}` formulas; the array entry keeps display structure.
            # Fall back to the inline latex if this object isn't indexed.
            idx = getattr(self, "_title_index", {}).get(obj.id)
            body = f"\\EqExpr{{{idx}}}" if idx else latex
            return f"\\begin{{equation}}\n{body}{lab}\n\\end{{equation}}"
        if t == "Formula":
            latex = _pipe.sanitize_math((p.get("latex") or "").strip())
            return f"${latex}$" if latex else ""
        if t == "Table":
            code = (p.get("latex_code") or "").strip()
            if code:
                # a tabular can carry `\citep{…}` (undefined here) — normalise to
                # `\cite`; keep the table's own `&`/`\\` untouched.
                return _pipe.normalize_cite_commands(code)
            raw = (p.get("raw_text") or "").strip()
            return f"% table p{p.get('page')}\n\\begin{{verbatim}}\n{raw}\n\\end{{verbatim}}" if raw else ""
        if t in ("Picture", "Diagram"):
            code = (p.get("latex_code") or "").strip()
            if code:
                return code
            # 640 — a figure caption can carry a numeric citation exactly as a
            # paragraph does (`Adelson's checkerboard illusion [29]`), and
            # Picture/Diagram is in `CITED_TEXT_TYPES` for that reason. `_cite`
            # runs on the RAW caption, same order as every other caller
            # (before `_escape_text`, so a citekey is never re-escaped).
            cap = _escape_text(self._cite(obj, str(p.get("caption") or "").strip()))
            return f"% figure p{p.get('page')}" + (f": {cap}" if cap else "")
        if t == "ListItem":
            # a lone ListItem (not part of a run) — still needs an environment
            return self._render_list([obj])
        if t == "Footnote":
            # A body no marker took — emitted where it stands, but WITH its
            # printed number: a bare `\footnotetext{…}` never steps the counter,
            # so every one of penev_A's 54 of them printed as footnote "0".
            return self._footnotetext(obj)
        if t == "Toc":
            # 635 — read the Toc, don't skip it. `\tableofcontents` needs two
            # xelatex passes (642 already made the compile two-pass) and a
            # real `\section` per entry, which `_render`'s Section branch
            # already emits — no separate rebuild of the table is needed.
            # Emitted ONCE, at THIS object's flow position (`flow_ordered_
            # content` already put it there); a second Toc object (should one
            # ever exist) renders nothing rather than a second command.
            if self._toc_emitted:
                return ""
            self._toc_emitted = True
            return "\\tableofcontents"
        return ""
