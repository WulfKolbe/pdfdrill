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

IMAGE LINKS — LOCAL CROP FIRST, and this is not a preference. MathPix retired
the crop CDN: every `cdn_url` in every model on disk answers HTTP 500, so a
document whose images are CDN links renders as nothing at all. The bytes are not
lost — the crop layer fetched them into `report-crops/<title>.jpg`, one per
object, named after the TIDDLER TITLE (5,227 of them for BH1org_OCR). So the
link is `<crops_base>/<title>.jpg`, and `crops_base` may be a URL, which is how
the same Markdown is read against a server instead of a folder. `cdn_url` is
still used when no crop exists, because a link that might work beats no link.

The titles come from `tiddlywiki.title_for`, which is documented as THE one
place a title is built. Formatting them here would be a second scheme, and the
crop files are named by the first one — so the links would point at nothing.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..base import BaseProjector

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


def _unwidget(text: str) -> str:
    r"""`<$latex text="x^2" displayMode="false"/>` → `\(x^2\)`.

    MathPix's own Markdown — the reference this output has to match, because it
    is what a reader of this corpus already knows — writes inline mathematics
    `\(…\)` and display `\[…\]`. So does the model's own `latex` prop.
    """
    def one(m: re.Match) -> str:
        tex = (m.group("tex") or "").strip()
        if not tex:
            return ""
        tex = tex.replace("&quot;", '"').replace("&amp;", "&")
        return f"\\[{tex}\\]" if _DISPLAY.search(m.group(0)) else f"\\({tex}\\)"
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
    """

    def project(self, doc) -> str:
        from .tiddlywiki import title_for

        bibkey = str(doc.meta.get("bibkey") or "document")
        self._titles = self._title_map(doc, title_for, bibkey)
        out: list[str] = []
        if self.params.get("front_matter", True):
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

    # ------------------------------------------------------------------ flow
    @staticmethod
    def _flow(doc) -> list:
        """Objects in reading order, skipping the containers and the furniture.

        `Page` is a container, not prose; `TableRow`/`TableCell` are rendered by
        their Table; `Formula` is rendered inside the prose that hosts it.
        """
        skip = {"Document", "Page", "TableRow", "TableCell", "Formula",
                "SyntheticFormula", "Citation", "LtxCommand"}
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

    def _equation(self, obj) -> str:
        r"""A display equation: its LaTeX, else its crop as an image.

        An equation with neither — a CDN-only object whose crop was never
        fetched — yields NOTHING rather than an empty `\[\]`, which every
        renderer shows as a stray bracket.
        """
        tex = str(obj.props.get("latex") or obj.props.get("latex_original")
                  or "").strip()
        if tex:
            num = str(obj.props.get("refnum") or "").strip()
            body = f"\\[{tex}\\]"
            return f"{body}\n\n({num})" if num else body
        link = self._image_link(obj)
        return f"![{self._titles.get(obj.id, 'equation')}]({link})" if link else ""

    def _figure(self, obj) -> str:
        link = self._image_link(obj)
        cap = self._clean(str(obj.props.get("caption") or ""))
        alt = cap or self._titles.get(obj.id, obj.type.lower())
        if not link:
            # No image to link. The CAPTION is still content and is kept — a
            # figure whose bytes are missing is not a reason to lose its words.
            return f"*{cap}*" if cap else ""
        out = f"![{alt}]({link})"
        return f"{out}\n\n*{cap}*" if cap else out

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
            return f"{table}\n\n*{cap}*" if cap else table
        link = self._image_link(obj)
        if link:
            out = f"![{cap or self._titles.get(obj.id, 'table')}]({link})"
            return f"{out}\n\n*{cap}*" if cap else out
        return f"*{cap}*" if cap else ""

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

        The order is forced by measurement, not taste: MathPix retired the crop
        CDN and every `cdn_url` on disk answers HTTP 500, so preferring it shows
        a broken image where a working file exists. `crops_base` may be a URL,
        which is how the same Markdown reads against a server.
        """
        title = self._titles.get(obj.id, "")
        if title and self._crop_exists(title):
            base = str(self.params.get("crops_base", "report-crops")).rstrip("/")
            return f"{base}/{title}.jpg"
        return str(obj.props.get("cdn_url") or "")

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
    def _clean(self, text: str) -> str:
        """Prose fit for Markdown: widgets become LaTeX, markers go, and the
        LaTeX sectioning a MathPix line sometimes carries is unwrapped."""
        text = _unwidget(text)
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
