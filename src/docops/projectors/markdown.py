"""
MarkdownProjector — the docmodel as Markdown a reader (and a Markdown editor)
can actually use.

816 — THERE WAS NO MARKDOWN PROJECTOR. `<bibkey>.md` had three producers and two
of them were `LLMCompactProjector`, the token-economical LLM form: it drops
images and tables by design and ends with an appendix of every inline formula
and display equation, the body referring INTO that appendix. Measured on
60cfff3d1e0c8: 0 images, 0 tables, 63 `**F…**` entries, 8 display entries. A
reader who asked for Markdown got an LLM prompt (audit
docs/superpowers/specs/2026-09-26-projection-audit.md, F1).

The rules this projector exists to satisfy, as the user stated them:

  * transclusion is NEVER in Markdown. No `{{…||FO}}`, and no reference into an
    appendix either — a formula is rendered where it stands.
  * a Markdown projection carries the document's IMAGES and TABLES.
  * an image is a LINK, never base64: "my Markdown editor can follow CDN links,
    we have some example with crop links at the server for these, that was the
    intended function".

IMAGE LINKS — LOCAL CROP FIRST, and this is not a preference. A MathPix
`cdn_url` is PERISHABLE: measured 2026-09-27, BH1org_OCR (converted months ago)
answers HTTP 500 while 1-s2.0-S2590118425000565-main (16 Sep) and
arxiv.2609.12039 (today) both answer 200. (An earlier note here said the CDN was
retired and every `cdn_url` answered 500; that was measured on BH1org_OCR alone
and is true only of expired crops.) A local file does not expire, which is the
reason for the order.

The crop layer fetches them into `report-crops/<title>.jpg`, one per object,
named after the TIDDLER TITLE (5,227 of them for BH1org_OCR). So the link is
`<crops_base>/<title>.jpg`, and `crops_base` may be a URL, which is how the same
Markdown is read against a server instead of a folder. `cdn_url` is still used
when no crop exists — it may well work — and `image_base` rebases it onto a local
crop server when it does not (see `_rebase`).

The titles come from `tiddlywiki.title_for`, which is documented as THE one
place a title is built. Formatting them here would be a second scheme, and the
crop files are named by the first one — so the links would point at nothing.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..base import BaseProjector
from .common import (resolve_citation_markers, resolve_formula_markers,
                     theorem_head)

#: Object types rendered as an image, in the order a reader meets them.
_FIGURE_TYPES = ("Picture", "Diagram", "Chart", "Figure")

#: A transclusion marker, which must never appear in the output. Kept as a
#: pattern rather than a promise: `_strip_transclusions` enforces it, and a test
#: asserts the output is free of them.
_TRANSCLUSION = re.compile(r"\{\{([^{}]*?)\|\|[A-Z]{2,4}\}\}")

#: The TiddlyWiki `<$latex text="…"/>` widget. `mathdelims` renders in-place
#: mathematics as this for the wiki; in Markdown it is the LaTeX itself.
_LATEX_WIDGET = re.compile(
    r"<\$latex\s+text=(\"|')(?P<tex>.*?)\1[^>]*?/>", re.S)

#: `displayMode="true"` inside such a widget.
_DISPLAY = re.compile(r'displayMode\s*=\s*("|\')true\1')

#: MathPix's own Markdown delimiters — the dialect this corpus is written in.
#:
#: NOT a style choice. `pdfdrill mathpix` asks for these on the wire
#: (`mathpix_client.CONVERSION_OPTIONS["conversion_options"]["md"]`), so every
#: bought `.md` in the library carries them: measured on 600 intact downloads,
#: `$…$` in 100% and a `$$` fence on its own line in 84%, against one `\tag{}`
#: in the whole sample. The UI's export defaults differ (`\(…\)`, `\[…\]`,
#: `\section*`, `\begin{tabular}`) — that is the MathPix dialect this
#: projector used to emit, and it matches no file pdfdrill ever downloaded.
#:
#: Mirrored rather than imported: `docops` does not depend on the CLI package,
#: and `tests/test_md_is_mathpix_shaped.py` holds the two definitions equal so
#: a change to the purchase cannot silently outrun the projection.
MATH_INLINE = ("$", "$")
MATH_DISPLAY = ("$$", "$$")


#: A math span as MathPix's `lines.json` delimits it — which is NOT what its
#: `.md` uses. The md options choose `$…$`; the reading always says `\(…\)`,
#: so every prose string the model holds arrives in the UI dialect and has to
#: be re-delimited on the way out. `_unwidget` never saw these: they are not
#: widgets, they are the text itself.
_MATH_SPAN = re.compile(r"\\\[(?P<d>.+?)\\\]|\\\((?P<i>.+?)\\\)", re.S)

#: The same, for prose that came from the AUTHOR'S LaTeX rather than from a
#: provider's reading. There `$ … $` is mathematics and a literal dollar is
#: written `\$` — the opposite convention to MathPix's, which escapes the
#: literal one on the wire (`escape_dollar: True`) and delimits its mathematics
#: `\( … \)`. Reading the author's `$\alpha(M)$` with the provider's rule
#: escaped both delimiters and shipped `\$\alpha(M)\$` as prose: the defect this
#: pattern exists for. Mirrors `latex_source._INLINE_MATH`, which is what
#: harvested the same spans on the way in.
_MATH_SPAN_SOURCE = re.compile(
    r"\\\[(?P<d>.+?)\\\]"
    r"|\\\((?P<i>.+?)\\\)"
    r"|(?<!\\)\$\$(?P<dd>.+?)(?<!\\)\$\$"
    r"|(?<![\\$])\$(?!\$)(?P<ii>.+?)(?<!\\)\$",
    re.S)

#: The FO and CIT markers this projector RESOLVES rather than strips live in
#: `common` (`resolve_formula_markers` / `resolve_citation_markers`), because
#: `llm_text` has to resolve the same two and its own docstring forbids them
#: ("no markup, no transclusion tokens"). One implementation, two callers.

#: A display environment the author wrote inside running prose. MathPix's md
#: dialect is `$$ … $$`; a Markdown renderer types no `\begin{equation}`.
#:
#: Measured on arxiv.math_9807032: 22 inside Theorem statements and 24 inside
#: Proof statements, which is exactly the 46 its `.md` carried. Only MARKDOWN
#: converts these — in the LaTeX projection the environment is already right,
#: and `$$` would be the wrong thing there.
_DISPLAY_ENV = re.compile(
    r"\\begin\{(?P<env>equation|displaymath|align|alignat|gather|multline"
    r"|eqnarray|flalign)(?P<star>\*?)\}(?P<body>.*?)"
    r"\\end\{\1\2\}", re.S)

#: Of those, the ones whose body carries `&` alignment. Inside `$$ … $$` a bare
#: `align` is invalid for KaTeX and MathJax both; `aligned` is the form they
#: accept, and it is what the body means.
_ALIGNED_ENVS = frozenset({"align", "alignat", "gather", "multline",
                           "eqnarray", "flalign"})

#: How `build_source_model` sanitises a tiddler title before writing it into a
#: marker. Mirrored, because the marker in the prose is the sanitised form and
#: the title map is built from `title_for`, which is not.
_TITLE_SAFE = re.compile(r"[^A-Za-z0-9_\-\.]")

#: A dollar that is not already escaped AND does not open a TiddlyWiki widget.
#: `escape_dollar: True` is in the conversion options pdfdrill sends, and 58 of
#: 400 intact downloads carry an escaped `\$` (302 occurrences): in a `$…$`
#: dialect a bare literal dollar opens mathematics and swallows the rest of the
#: line. The `<` guard is not cosmetic — without it this escaped the `$` of
#: `<$latex text="x^2"/>`, `_unwidget` no longer recognised the widget, and the
#: projection shipped the widget source as prose. Four tests caught it.
_BARE_DOLLAR = re.compile(r"(?<![\\<])\$")


def _mathpix_math(text: str, source_math: bool = False) -> str:
    r"""Prose into MathPix's md dialect: `\(x\)` → `$x$`, `\[x\]` → `$$x$$`,
    and a literal `$` BETWEEN the spans escaped.

    One pass over the math spans rather than two substitutions, because the
    escaping must not reach inside a formula: `\(a\$b\)` is mathematics with a
    dollar in it, and escaping that changes the equation.

    `source_math=True` reads `$ … $` as a span too, which is right for the
    author's own LaTeX and wrong for a provider's reading — see
    `_MATH_SPAN_SOURCE`. Either way a `\$` stays an escaped dollar sign.
    """
    out: list[str] = []
    pos = 0
    for m in (_MATH_SPAN_SOURCE if source_math else _MATH_SPAN).finditer(text):
        g = m.groupdict()
        display = g["d"] if g["d"] is not None else g.get("dd")
        inline = g["i"] if g["i"] is not None else g.get("ii")
        out.append(_BARE_DOLLAR.sub(r"\\$", text[pos:m.start()]))
        if display is not None:
            out.append(f"{MATH_DISPLAY[0]}{display}{MATH_DISPLAY[1]}")
        else:
            out.append(f"{MATH_INLINE[0]}{inline}{MATH_INLINE[1]}")
        pos = m.end()
    out.append(_BARE_DOLLAR.sub(r"\\$", text[pos:]))
    return "".join(out)


def _is_latex_source(doc) -> bool:
    """Was this model built from the author's own LaTeX?

    The twin of `pdfdrill.commands._is_latex_source_model`, which asks the same
    question of a model on disk. Mirrored rather than imported for the reason
    `MATH_INLINE` is: `docops` does not depend on the CLI package.
    `source_counts` is the positive marker — `latex_source.build_source_model`
    and `markdown_source` are the only writers of it — and the two meta fields
    the CLI predicate reads are honoured as well.
    """
    meta = getattr(doc, "meta", None) or {}
    return bool(meta.get("source_counts")
                or meta.get("latex_source_dir")
                or "LaTeX source" in str(meta.get("source_path") or ""))


def _unwidget(text: str) -> str:
    r"""`<$latex text="x^2" displayMode="false"/>` → `$x^2$`.

    MathPix's own Markdown is the reference this output has to match, because
    it is what a reader of this corpus already knows — and what it writes is
    `$…$` / `$$…$$`, because that is what pdfdrill asks for. See `MATH_INLINE`:
    this returned `\(…\)` / `\[…\]` until 2026-10-23, which is the UI export's
    dialect and matches no file in the library.
    """
    def one(m: re.Match) -> str:
        tex = (m.group("tex") or "").strip()
        if not tex:
            return ""
        tex = tex.replace("&quot;", '"').replace("&amp;", "&")
        d = MATH_DISPLAY if _DISPLAY.search(m.group(0)) else MATH_INLINE
        return f"{d[0]}{tex}{d[1]}"
    return _LATEX_WIDGET.sub(one, text)


_WRAPPER = re.compile(
    r"\\(?:title|author|section|subsection|subsubsection|paragraph)\*?\s*\{")


def _unwrap_latex_wrapper(text: str) -> str:
    """Remove a `\title{…}` / `\author{…}` wrapper, keeping its contents.

    Brace-balanced, because stripping the opening alone strands the closing one:
    the first run of this projector emitted a paragraph whose last line was a
    lone `}`. Same defect class as 811's caption truncation — a `[^}]*` that
    cannot see nesting — approached from the other side.
    """
    out = text
    while True:
        m = _WRAPPER.search(out)
        if not m:
            return out
        depth, i = 1, m.end()
        while i < len(out) and depth:
            depth += (out[i] == "{") - (out[i] == "}")
            i += 1
        inner = out[m.end():i - 1] if depth == 0 else out[m.end():]
        out = out[:m.start()] + inner + (out[i:] if depth == 0 else "")


def _strip_transclusions(text: str) -> str:
    """Drop a transclusion marker, keeping nothing behind.

    A marker's payload is rendered in place by the caller before this runs, so
    anything still matching here is a marker the caller did not resolve — and a
    literal `{{X_FO0001||FO}}` in prose is the "invalid transclusion" a reader
    reported. Removing it is right: the alternative is shipping a token that
    means nothing outside TiddlyWiki.
    """
    return _TRANSCLUSION.sub("", text)


class MarkdownProjector(BaseProjector):
    """The document as Markdown: headings, prose, images, tables, mathematics.

    Params:
      ``crops_base``  link prefix for images (default ``report-crops``). A URL
                      works: the same Markdown then reads against a server.
      ``crops_dir``   where to CHECK a crop exists. Without it no crop link is
                      emitted, because a link to a file that is not there is the
                      failure this replaces.
      ``front_matter``  YAML front matter (default True).
      ``image_base``  origin that resolves MathPix-shaped crop URLs, e.g.
                      ``http://localhost:8791``. See `_image_link`.
    """

    def project(self, doc) -> str:
        from .tiddlywiki import title_for

        bibkey = str(doc.meta.get("bibkey") or "document")
        self._titles = self._title_map(doc, title_for, bibkey)
        self._formulas = self._formula_map(doc, bibkey)
        self._source_math = _is_latex_source(doc)
        out: list[str] = []
        if self.params.get("front_matter", False):
            out.append(self._front_matter(doc, bibkey))
        for obj in self._flow(doc):
            block = self._block(obj, doc)
            if block:
                out.append(block)
        text = "\n\n".join(b.strip("\n") for b in out if b.strip())
        return text.rstrip() + "\n"

    # ---------------------------------------------------------------- titles
    @staticmethod
    def _title_map(doc, title_for, bibkey: str) -> dict:
        """{object id: tiddler title} — the SAME titles the crop files carry.

        Numbered per type in flow order, exactly as the TiddlyWiki projector
        numbers them, because `report-crops/<title>.jpg` was named by that pass.
        A type with no row in TITLE_SHAPES is skipped rather than guessed.
        """
        seen: dict = {}
        out: dict = {}
        for obj in sorted(doc.objects.values(),
                          key=lambda o: (o.props.get("flow_index") is None,
                                         o.props.get("flow_index") or 0)):
            kind = obj.type
            seen[kind] = seen.get(kind, 0) + 1
            try:
                out[obj.id] = title_for(bibkey, kind, seen[kind])
            except KeyError:
                continue
        return out

    @staticmethod
    def _formula_map(doc, bibkey: str) -> dict:
        """{marker title: Formula object} — the reverse of what the prose holds.

        `math_titles` is the numbering, and it is NOT re-derived here: its own
        docstring says a second implementation "would silently drift and emit
        references that resolve to the wrong formula", and a marker resolved to
        the wrong formula is worse than one resolved to none. It numbers
        `Formula` and `Equation`; a `SyntheticFormula` is content-addressed
        (`FOX_<sha1>`) and has no row there, so it stays unresolved — and
        `build_source_model`, which is what writes these markers, never makes
        one.
        """
        from .tiddlywiki import math_titles

        out: dict = {}
        titles = math_titles(doc, bibkey)
        for obj in doc.objects.values():
            title = titles.get(obj.id) if obj.type == "Formula" else None
            if title:
                out[_TITLE_SAFE.sub("_", title)] = obj
        return out

    # ------------------------------------------------------------------ flow
    @staticmethod
    def _flow(doc) -> list:
        """Objects in reading order, skipping the containers and the furniture.

        `Page` is a container, not prose; `TableRow`/`TableCell` are rendered by
        their Table and `AlgorithmStep` by its Algorithm; `Formula` is rendered
        inside the prose that hosts it.

        An `AlgorithmStep` carries no `flow_index` at all, so left in the flow
        it does not merely duplicate its Algorithm — it sorts to the end and
        prints the steps after the bibliography.
        """
        skip = {"Document", "Page", "TableRow", "TableCell", "AlgorithmStep",
                "Formula", "SyntheticFormula", "Citation", "LtxCommand"}
        objs = [o for o in doc.objects.values() if o.type not in skip]
        return sorted(objs, key=lambda o: (o.props.get("flow_index") is None,
                                           o.props.get("flow_index") or 0))

    # ----------------------------------------------------------------- parts
    def _front_matter(self, doc, bibkey: str) -> str:
        import collections
        c = collections.Counter(o.type for o in doc.objects.values())
        # The DOCUMENT's title, not the first level-1 heading — which on a
        # paper is "1. Introduction" and is not what the document is called.
        title = str(doc.meta.get("title") or "")
        if not title:
            for o in doc.objects.values():
                if o.type == "Title":
                    title = self._clean(str(o.props.get("text")
                                            or o.props.get("caption") or ""))
                    break
        # THE FIRST LINE ONLY. A `\title{}` block on this corpus runs title,
        # then `\\`, then the author list and the affiliation — and `_clean`
        # turns each `\\` into a line break, so taking the whole thing put 200
        # characters of authors into a YAML `title:`.
        title = title.split("\n")[0].strip()
        rows = [
            "---",
            f"bibkey: {bibkey}",
            f'title: "{(title or bibkey).replace(chr(34), chr(39))}"',
        ]
        lang = doc.meta.get("translated_lang")
        if lang:
            rows.append(f"language: {lang}")
            if doc.meta.get("source_lang"):
                rows.append(f"translated_from: {doc.meta['source_lang']}")
        for kind in ("Page", "Section", "Paragraph", "Equation", "Table",
                     "Picture", "Diagram"):
            if c.get(kind):
                rows.append(f"{kind.lower()}s: {c[kind]}")
        rows.append("generator: pdfdrill MarkdownProjector")
        rows.append("---")
        return "\n".join(rows)

    def _block(self, obj, doc) -> str:
        t = obj.type
        if t == "Section":
            return self._heading(obj)
        if t in _FIGURE_TYPES:
            return self._figure(obj)
        if t == "Table":
            return self._table(obj, doc)
        if t == "Equation":
            return self._equation(obj)
        if t == "ListItem":
            return self._list_item(obj)
        if t == "CodeListing":
            return self._code(obj)
        if t == "Theorem":
            return self._theorem(obj)
        if t == "Proof":
            return self._proof(obj)
        if t == "Algorithm":
            return self._algorithm(obj, doc)
        if t in ("Paragraph", "Abstract", "Toc", "Footnote", "Sidenote"):
            return self._prose(obj, t)
        return ""

    def _heading(self, obj) -> str:
        level = int(obj.props.get("level") or 1)
        cap = self._clean(str(obj.props.get("caption") or ""))
        return f"{'#' * max(1, min(6, level))} {cap}" if cap else ""

    def _prose(self, obj, kind: str) -> str:
        body = self._clean(str(obj.props.get("text")
                               or obj.props.get("content") or ""))
        if not body:
            return ""
        if kind == "Abstract":
            return f"## Abstract\n\n{body}"
        if kind == "Footnote":
            num = obj.props.get("refnum") or ""
            return f"[^{num}]: {body}" if num else f"> {body}"
        if kind == "Sidenote":
            return f"> {body}"
        return body

    def _list_item(self, obj) -> str:
        marker = str(obj.props.get("marker") or "").strip()
        body = self._clean(str(obj.props.get("content")
                               or obj.props.get("text") or ""))
        if not body:
            return ""
        # A numbered marker stays numbered; anything else becomes a bullet, so
        # the list reads as a list in every Markdown renderer.
        return f"{marker} {body}" if re.match(r"^\d+[.)]$", marker) \
            else f"- {body}"

    def _code(self, obj) -> str:
        body = str(obj.props.get("content") or obj.props.get("text") or "")
        if not body.strip():
            return ""
        lang = str(obj.props.get("language") or "")
        return f"```{lang}\n{body.rstrip()}\n```"

    def _theorem(self, obj) -> str:
        """A theorem-like block: `**Theorem 3 (Hirzebruch).** <statement>`.

        The shape the TiddlyWiki projector already gives the same object, so the
        two projections of one model agree. The printed title is the author's
        own (`\\newtheorem{lemma}{Lemma}` → "Lemma"), the number follows the
        shared-counter chain the reader resolved, and a starred environment has
        neither.
        """
        body = self._clean(str(obj.props.get("statement")
                               or obj.props.get("text") or ""))
        if not body:
            return ""
        return f"**{theorem_head(obj, self._clean)}.** {body}"

    def _proof(self, obj) -> str:
        r"""`**Proof.** <statement> $\square$`.

        `\begin{proof}[Proof of Theorem 2]` names its target, and Markdown has
        no field to keep that in — so the name belongs in the text. The box ends
        the proof, which matters when prose follows it; a proof that already
        ends in one does not get a second.
        """
        body = self._clean(str(obj.props.get("statement")
                               or obj.props.get("text") or ""))
        if not body:
            return ""
        name = str(obj.props.get("name") or "").strip().rstrip(".") or "Proof"
        if not re.search(r"(?:\\square|\\blacksquare|\\qed\w*)\s*\$?\s*$", body):
            body = f"{body} {MATH_INLINE[0]}\\square{MATH_INLINE[1]}"
        return f"**{name}.** {body}"

    def _algorithm(self, obj, doc) -> str:
        """`**Algorithm 1** <title>` and its steps as a numbered list.

        The steps are reached through the Algorithm's `children`, else by their
        own `parent` — `cmd_algorithms` and the LaTeX reader both build them,
        and an Algorithm whose steps arrived by only one of those routes is
        still an Algorithm. Depth indents: a nested step is a step OF the step
        above it, and flattening them loses the loop body.
        """
        num = str(obj.props.get("number") or "").strip()
        head = f"**Algorithm {num}**" if num else "**Algorithm**"
        title = self._clean(str(obj.props.get("title")
                                or obj.props.get("caption") or "")).strip()
        if title:
            head = f"{head} {title}"

        steps = [doc.objects[i] for i in (obj.children or [])
                 if i in doc.objects
                 and doc.objects[i].type == "AlgorithmStep"]
        if not steps:
            steps = [o for o in doc.objects.values()
                     if o.type == "AlgorithmStep"
                     and getattr(o, "parent", None) == obj.id]
        rows: list[str] = []
        top = 0
        for st in steps:
            body = self._clean(str(st.props.get("text")
                                   or st.props.get("content") or "")).strip()
            if not body:
                continue
            try:
                depth = max(0, int(st.props.get("depth") or 0))
            except (TypeError, ValueError):
                depth = 0
            if depth:
                # Three spaces is the content column of `N. `, so the nested
                # item belongs to the item above in every CommonMark renderer.
                rows.append(f"{'   ' * depth}1. {body}")
            else:
                top += 1
                rows.append(f"{top}. {body}")
        return f"{head}\n\n" + "\n".join(rows) if rows else head

    def _equation(self, obj) -> str:
        r"""A display equation: its LaTeX, else its crop as an image.

        An equation with neither — a CDN-only object whose crop was never
        fetched — yields NOTHING rather than an empty `$$$$`, which every
        renderer shows as a stray fence.
        """
        tex = str(obj.props.get("latex") or obj.props.get("latex_original")
                  or "").strip()
        if tex:
            num = str(obj.props.get("refnum") or "").strip()
            # The fence on its own line, as MathPix writes it. The NUMBER stays
            # plain text beside it: `\tag{}` appears once in 600 reference
            # files, so it is not part of the dialect — and dropping the number
            # would cut the only handle the prose has on the equation.
            body = f"{MATH_DISPLAY[0]}\n{tex}\n{MATH_DISPLAY[1]}"
            return f"{body}\n\n({num})" if num else body
        link = self._image_link(obj)
        return f"![]({link})" if link else ""

    def _figure(self, obj) -> str:
        link = self._image_link(obj)
        cap = self._clean(str(obj.props.get("caption") or ""))
        if not link:
            # No image to link. The CAPTION is still content and is kept — a
            # figure whose bytes are missing is not a reason to lose its words.
            return cap
        out = f"![]({link})"
        return f"{out}\n\n{cap}" if cap else out

    def _table(self, obj, doc) -> str:
        """A pipe table from the Table's rows, else its crop, else its caption.

        MathPix ships a table as rows of cells; a model built from a lane that
        measured only the rectangle has none, and for those the crop IS the
        table. Both are better than the nothing this used to emit.
        """
        cap = self._clean(str(obj.props.get("caption") or ""))
        rows = self._rows(obj, doc)
        if rows:
            width = max(len(r) for r in rows)
            rows = [r + [""] * (width - len(r)) for r in rows]
            head, body = rows[0], rows[1:]
            lines = ["| " + " | ".join(head) + " |",
                     "| " + " | ".join(["---"] * width) + " |"]
            lines += ["| " + " | ".join(r) + " |" for r in body]
            table = "\n".join(lines)
            return f"{table}\n\n{cap}" if cap else table
        link = self._image_link(obj)
        if link:
            out = f"![]({link})"
            return f"{out}\n\n{cap}" if cap else out
        return cap

    def _rows(self, obj, doc) -> list:
        """[[cell text, …], …] for a Table, from its `cells` GRID.

        Not from `TableRow.children`, which is empty: the model hangs every
        TableRow AND every TableCell off the Table itself (measured on
        1-s2.0-S2590118425000565-main: a 4x2 table has 12 children and its rows
        have 0), so walking the tree finds rows with no cells in them and yields
        nothing — which is why this projector emitted 0 pipe rows for a document
        with 3 tables on the first run.

        `props["cells"]` is the grid MathPix actually measured: each entry
        carries `row`, `col`, `row_span`, `col_span` and `text`. A spanned cell
        is written once at its origin and the covered positions are left empty,
        because Markdown pipe tables have no spans and repeating the text would
        state a value the document does not have.
        """
        cells = obj.props.get("cells")
        if not isinstance(cells, list) or not cells:
            return []
        n_rows = int(obj.props.get("n_rows") or 0)
        n_cols = int(obj.props.get("n_cols") or 0)
        if not (n_rows and n_cols):
            for c in cells:
                if isinstance(c, dict):
                    n_rows = max(n_rows, int(c.get("row") or 0) + 1)
                    n_cols = max(n_cols, int(c.get("col") or 0) + 1)
        if not (n_rows and n_cols):
            return []
        grid = [["" for _ in range(n_cols)] for _ in range(n_rows)]
        for c in cells:
            if not isinstance(c, dict):
                continue
            r, k = int(c.get("row") or 0), int(c.get("col") or 0)
            if not (0 <= r < n_rows and 0 <= k < n_cols):
                continue
            txt = self._clean(str(c.get("text") or ""))
            grid[r][k] = txt.replace("|", r"\|").replace("\n", " ")
        return [row for row in grid if any(x.strip() for x in row)]

    # ---------------------------------------------------------------- images
    def _image_link(self, obj) -> str:
        """The image URL for an object — local crop first, then `cdn_url`.

        The order is forced by measurement, not taste: a `cdn_url` EXPIRES
        (2026-09-27: 500 for a months-old conversion, 200 for two recent ones),
        so preferring it risks a broken image where a permanent local file sits.
        `crops_base` may be a URL, which is how the same Markdown reads against
        a server.
        """
        title = self._titles.get(obj.id, "")
        if title and self._crop_exists(title):
            base = str(self.params.get("crops_base", "report-crops")).rstrip("/")
            return f"{base}/{title}.jpg"
        return self._rebase(str(obj.props.get("cdn_url") or ""))

    def _rebase(self, url: str) -> str:
        """Point a MathPix crop URL at `image_base` instead of the retired CDN.

        819d — the URLs are not wasted, they are UNRESOLVED. A `cdn_url` is
        `https://cdn.mathpix.com/cropped/<image_id>.jpg?height=H&width=W&
        top_left_y=Y&top_left_x=X`, and that is EXACTLY the route
        `pdf2mmd/inspectserver.py` and `tools/imageserver/mathpix_server.py`
        serve — deliberately, so "any Mathpix-syntax Markdown works against
        either". Swapping the host is the whole fix: verified against a real
        dead `cdn_url` from 2609.12039, HTTP 200, 168 KB, and the crop's aspect
        ratio matches the request exactly (834/571 = 1334/914).

        This beats fetching crops, because nothing has to be stored: the server
        cuts the rectangle out of the page PNG `inspect` already wrote. It also
        beats the images inside MathPix's `.tex.zip`, whose names are opaque
        hashes tied to nothing — where a crop URL carries its own rectangle.
        """
        base = str(self.params.get("image_base") or "").rstrip("/")
        if not (base and url):
            return url
        m = re.match(r"https?://[^/]+(/cropped/.*)$", url)
        return f"{base}{m.group(1)}" if m else url

    def _crop_exists(self, title: str) -> bool:
        """Checked on disk, never assumed — with no `crops_dir` there is no
        crop link, because a link to a file that is not there is the failure
        this replaces (the same rule tiddlywiki._local_crop follows)."""
        base = self.params.get("crops_dir")
        if not (base and title):
            return False
        try:
            return (Path(str(base)) / f"{title}.jpg").is_file()
        except OSError:
            return False

    # ----------------------------------------------------------------- prose
    def _render_formulas(self, text: str) -> str:
        """`{{Schick2001_FO0001||FO}}` → `$\\pi_1(M)$`, in place.

        This is the projector's first stated rule — "a formula is rendered
        where it stands" — and the half of it that was never implemented for a
        model built from the author's LaTeX. A marker naming no Formula, or one
        whose Formula carries no LaTeX, is left for `_strip_transclusions`:
        there is nothing to render, and an empty `$$` is a stray fence in every
        renderer.
        """
        return resolve_formula_markers(text, getattr(self, "_formulas", None),
                                       inline=MATH_INLINE, display=MATH_DISPLAY)

    @staticmethod
    def _render_citations(text: str) -> str:
        """`{{<bibkey>_REF_<key>||CIT}}` → `[<key>]`, in place."""
        return resolve_citation_markers(text)

    @staticmethod
    def _render_display_envs(text: str) -> str:
        r"""`\begin{equation} x = y \end{equation}` → `$$x = y$$`.

        The author writes display maths inside a theorem statement as an
        environment, and `latex_source` keeps the statement as prose, so the
        environment travels in the text rather than becoming an `Equation`
        object. Markdown has to type it; the aligned family keeps its own inner
        environment because `&` needs one.
        """
        def one(m: "re.Match") -> str:
            body = (m.group("body") or "").strip()
            if not body:
                return ""
            if m.group("env") in _ALIGNED_ENVS:
                body = f"\\begin{{aligned}}\n{body}\n\\end{{aligned}}"
            return f"{MATH_DISPLAY[0]}{body}{MATH_DISPLAY[1]}"

        return _DISPLAY_ENV.sub(one, text)

    def _clean(self, text: str) -> str:
        """Prose fit for Markdown: widgets become LaTeX, markers go, and the
        LaTeX sectioning a MathPix line sometimes carries is unwrapped."""
        # A display ENVIRONMENT first, before anything looks at delimiters: it
        # is the only form here that carries its own, and the `$$` it becomes
        # must not then be read as prose dollars.
        text = self._render_display_envs(text)
        # The READING's delimiters first, while the widget output is not yet in
        # the string: `_unwidget` emits `$…$` now, and escaping would eat it.
        text = _mathpix_math(text, getattr(self, "_source_math", False))
        text = _unwidget(text)
        # THEN the formula transclusions, which emit final delimiters and so
        # must come after the pass that would re-read them as prose. Before
        # `_strip_transclusions`, which is what used to delete them.
        text = self._render_formulas(text)
        text = self._render_citations(text)
        text = _strip_transclusions(text)
        # `\title{X}` / `\author{X}` / `\section{X}` leak in from MathPix's
        # `text_display` on front-matter lines. Stripping only the OPENING
        # `\title{` left its closing brace stranded on a line of its own — the
        # first run produced a paragraph ending in a bare `}` — so the whole
        # wrapper goes, brace-balanced, keeping the contents.
        text = _unwrap_latex_wrapper(text)
        # A LIST ENVIRONMENT is scaffolding here, not content: its items are
        # ListItem objects of their own, so the `\begin{itemize}` that MathPix
        # leaves in a paragraph's `text_display` would announce a list whose
        # items are rendered elsewhere.
        text = re.sub(r"\\(?:begin|end)\s*\{(?:itemize|enumerate|description)\}",
                      "", text)
        # `\\` is a TeX line break, and in Markdown two trailing spaces are.
        text = re.sub(r"\s*\\\\\s*", "  \n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        # A LINE OF NOTHING BUT CLOSING BRACES is never Markdown. There is
        # always one more LaTeX wrapper than `_WRAPPER` lists — this corpus also
        # carries `\footnotetext{`, which left a lone `}` after a footnote —
        # and chasing the names one at a time is how the last one is missed.
        text = "\n".join(ln for ln in text.split("\n")
                          if ln.strip().strip("}") or not ln.strip())
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
