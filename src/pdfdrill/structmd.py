r"""Markdown from the PDF's OWN logical structure (`/StructTreeRoot`).

WHY THIS LAYER EXISTS. Measured on the eleven PDF-Association / ISO documents
(1,234 pages) drilled through `md` on 2026-10-13:

    11,036 tagged table cells in ISO 32000-2  ->      1 markdown table
     1,111 licence-footer lines woven into the running prose
        51 running headers fused to the following word: `14to`, `20be`, `41be`
           clause numbers interleaved letter by letter: `3st.a2ndard`

Every one of those is a GUESS about reading order that did not have to be
guessed. Ten of the eleven documents ship a `/StructTreeRoot` -- 78,468
structure elements in ISO 32000-2 alone, with `/TR`, `/TH` and `/TD` naming
every cell of every table -- and before this module
`grep -rn 'StructTreeRoot' src/` returned NOTHING. The authoritative reading
order was in the file and no reader asked for it.

The control case is `PDF20_AN002-AF`: the one document of the eleven whose tag
tree holds no table at all is also the one `md` damaged least. The corpus was
never hard; the route was reading geometry where a tree was available.

HOW IT WORKS -- two sources, each used only for what it is authoritative about:

  * `/StructTreeRoot` (via pikepdf) gives ORDER and ROLE. `/RoleMap` translates
    a producer's private names -- `/Heading_2`, `/Table_Text__10_`, `/Normal`,
    `/H1 bold_` -- into the standard roles of ISO 32000-2, 14.8.4. 23 entries
    in AN001, 18 in AN003, 66 in 32000-2. Never guessed: the file states it.
  * pdfplumber gives the TEXT, keyed by `(page_index, mcid)`. Every char in
    these documents carries an `mcid` (437 of 437 on the page measured), and
    the `chars.json` cache that `md` already writes carries `mcid` and `tag`
    too -- so a document that has been through `md` needs no second extraction.

ARTIFACTS ARE EXCLUDED FOR FREE, and that is the entire fix for the watermark.
A running header, a folio and a licence footer are artifacts, not content, so
they are not in the structure tree and this walk never sees them. No filter, no
heuristic, no list of strings to strip -- which is why this is a layer and not
a cleanup pass.

WHAT THIS MODULE REFUSES TO DO. If there is no `/StructTreeRoot`, or it holds
no content, `project()` raises `NoStructure`. It does not fall back to the
geometric route and quietly return a worse answer under a better name: the
caller says so in prose and names `md`. A tagged PDF whose tags are a stub is
exactly the case where a silent fallback would be indistinguishable from
success.
"""
from __future__ import annotations

import collections
import json
import re
import unicodedata
from pathlib import Path

# ISO 32000-2, 14.8.4: the standard structure types this projector renders.
# A role NOT listed here is treated as a transparent container -- its children
# still render -- because a producer may legitimately nest content inside a
# grouping element we have no opinion about. That is the safe direction: an
# unknown WRAPPER costs nothing, an unknown LEAF would silently drop text.
_HEADING = {f"/H{n}": n for n in range(1, 7)}
_BLOCK_CONTAINER = {"/Document", "/DocumentFragment", "/Part", "/Art", "/Sect",
                    "/Div", "/NonStruct", "/Private", "/Aside"}
_TABLE_SECTION = {"/THead", "/TBody", "/TFoot"}
_INLINE = {"/Span", "/Quote", "/Note", "/Reference", "/BibEntry", "/Code",
           "/Em", "/Strong", "/Sub", "/Annot", "/Ruby", "/Warichu", "/FENote"}

# Roles that MUST get their own block of markdown, so a container holding one
# can never be flattened into a paragraph.
_BLOCK_ROLES = {"/Table", "/L", "/TOC", "/Figure", "/Formula", "/Caption",
                "/BlockQuote"}

_MAX_DEPTH = 120          # 32000-2's deepest observed chain is far below this
_CACHE_BYTES_MAX = 256 * 1024 * 1024   # above this, stream the PDF instead


class NoStructure(Exception):
    """The PDF has no usable logical structure tree."""


# ---------------------------------------------------------------------------
# text: (page_index, mcid) -> the characters of that marked-content run
# ---------------------------------------------------------------------------
def _runs_from_page_chars(chars, page_index: int, runs, stats) -> None:
    """Fold one page's chars into `(page, mcid) -> text`, in stream order.

    THE NON-BREAKING-SPACE HOLE, and the reason this is not a one-line groupby.
    pdfplumber reports `mcid` and `tag` per char, but loses BOTH on a nested
    marked-content sequence. InDesign splits a text run at a non-breaking space,
    so a page's stream reads:

        tag=H1   mcid=150   '1'
        tag=None mcid=None  'Scope'
        tag=P    mcid=151   '...documents that use the PDF'
        tag=None mcid=None  '1.7 '
        tag=P    mcid=152   'namespace and the PDF'

    Dropping the `mcid=None` runs loses `Scope`, `1.7`, `2.0` and whole clause
    bodies -- 8,583 characters on ISO/TS 32005 alone, 13.8% of the document, and
    it is CONTENT, not furniture. Keeping them unattached is no better: they
    would have no element and no place in the reading order.

    THE RULE: an untagged run is appended to the marked-content run that
    immediately precedes it in the page's own stream, and only when another
    marked-content run follows it on that page -- the sandwich. Stream order is
    the document's own statement of sequence, so this reorders nothing and
    invents nothing; it re-attaches a split run to the half it was split from.

    TWO REFUSALS. An `Artifact` run never absorbs and is never absorbed: the
    licence footer must not be glued to the paragraph above it. An untagged run
    with no marked-content run before or after it on the page stays dropped --
    on a cover page that is the bilingual running title, which belongs to no
    element and has no reading position.
    """
    pending: list[str] = []
    last_key = None
    for ch in chars:
        text = ch.get("text") or ""
        mcid = ch.get("mcid")
        tag = ch.get("tag")
        if tag == "Artifact":
            pending.clear()               # an artifact absorbs nothing
            last_key = None               # and nothing absorbs across it
            stats["artifact_chars"] += len(text)
            continue
        if mcid is None:
            if last_key is None:
                stats["orphan_chars"] += 1 if text.strip() else 0
            else:
                pending.append(text)
            continue
        key = (page_index, int(mcid))
        if pending and last_key is not None:
            # SANDWICHED: the split half belongs to the run before it.
            runs[last_key].extend(pending)
            stats["reattached_chars"] += sum(len(x) for x in pending)
            pending.clear()
        runs[key].append(text)
        last_key = key
    # A trailing untagged run is not sandwiched, so it is dropped on purpose.
    stats["trailing_dropped_chars"] += sum(len(x) for x in pending if x.strip())


def marked_content_from_chars_json(path: Path) -> tuple[dict, dict]:
    """Read the `chars.json` that `md` already wrote.

    Reusing it matters at the top of the corpus: ISO 32000-2's cache is 1.3 GB
    over 1,023 pages and re-extracting it costs minutes, so a document already
    drilled to `md` gets its structure markdown for the price of a JSON read.
    """
    with open(path, "r", encoding="utf-8") as fh:
        blob = json.load(fh)
    runs: dict[tuple[int, int], list[str]] = collections.defaultdict(list)
    stats: dict[str, int] = collections.Counter()
    for page in (blob.get("pages") or []):
        chars = page.get("chars") if isinstance(page, dict) else None
        if not chars:
            continue
        # `page_number` is 1-based in pdfplumber; the structure tree indexes
        # pages 0-based, so normalise HERE and nowhere else.
        pno = chars[0].get("page_number")
        if pno is None:
            continue
        _runs_from_page_chars(chars, int(pno) - 1, runs, stats)
    return {k: "".join(v) for k, v in runs.items()}, dict(stats)


def marked_content_from_pdf(pdf: Path) -> tuple[dict, dict]:
    """Extract `(page, mcid) -> text` straight from the PDF with pdfplumber."""
    import pdfplumber

    runs: dict[tuple[int, int], list[str]] = collections.defaultdict(list)
    stats: dict[str, int] = collections.Counter()
    with pdfplumber.open(str(pdf)) as doc:
        for i, page in enumerate(doc.pages):
            _runs_from_page_chars(page.chars, i, runs, stats)
    return {k: "".join(v) for k, v in runs.items()}, dict(stats)


# ---------------------------------------------------------------------------
# the tree
# ---------------------------------------------------------------------------
class StructTree:
    """The document's logical structure, with `/RoleMap` already applied."""

    def __init__(self, pdf_handle, mc: dict[tuple[int, int], str]):
        self._pdf = pdf_handle
        self._mc = mc
        root = pdf_handle.Root.get("/StructTreeRoot")
        if root is None:
            raise NoStructure("no /StructTreeRoot")
        self.root = root
        rm = root.get("/RoleMap")
        self.rolemap = {str(k): str(v) for k, v in rm.items()} if rm else {}
        self._pageidx = {pg.obj.objgen: i
                         for i, pg in enumerate(pdf_handle.pages)}

    # -- roles -------------------------------------------------------------
    def role(self, node) -> str:
        """The STANDARD role of a node, through `/RoleMap`.

        A producer's own name is followed as far as the map leads (InDesign
        chains `/Subtitle -> /H1`), with a hop limit because a malformed map
        can be circular.
        """
        s = str(node.get("/S") or "")
        for _ in range(8):
            mapped = self.rolemap.get(s)
            if mapped is None or mapped == s:
                return s
            s = mapped
        return s

    def page_of(self, node, inherited: int) -> int:
        """`/Pg` is inheritable: a kid without one lives on its parent's page."""
        pg = node.get("/Pg")
        if pg is None:
            return inherited
        try:
            return self._pageidx.get(pg.objgen, inherited)
        except Exception:                                    # noqa: BLE001
            return inherited

    # -- children ----------------------------------------------------------
    def element_kids(self, node) -> list:
        """The child ELEMENTS, skipping marked-content and object references."""
        import pikepdf

        k = node.get("/K")
        if k is None:
            return []
        items = k if isinstance(k, pikepdf.Array) else [k]
        out = []
        for it in items:
            if isinstance(it, pikepdf.Dictionary) and \
                    it.get("/Type") not in ("/MCR", "/OBJR"):
                out.append(it)
        return out

    def text_of(self, node, pg: int, depth: int = 0) -> str:
        """All text under `node`, in document order.

        `/ActualText` wins outright when present -- it is the producer saying
        "whatever glyphs are here, this is what it says", which is how a
        ligature or a decorative split word reaches a reader intact.
        """
        import pikepdf

        if depth > _MAX_DEPTH:
            return ""
        actual = node.get("/ActualText")
        if actual is not None:
            return str(actual)
        k = node.get("/K")
        if k is None:
            return ""
        items = k if isinstance(k, pikepdf.Array) else [k]
        parts: list[str] = []
        for it in items:
            if isinstance(it, int):
                parts.append(self._mc.get((pg, int(it)), ""))
            elif isinstance(it, pikepdf.Dictionary):
                t = it.get("/Type")
                if t == "/MCR":
                    p2 = self.page_of(it, pg)
                    mcid = it.get("/MCID")
                    if mcid is not None:
                        parts.append(self._mc.get((p2, int(mcid)), ""))
                elif t == "/OBJR":
                    continue                      # an annotation, not text
                else:
                    parts.append(self.text_of(it, self.page_of(it, pg),
                                              depth + 1))
        return "".join(parts)

    def link_uri(self, node) -> str | None:
        """The URI behind a `/Link`, read from the annotation it points at."""
        import pikepdf

        k = node.get("/K")
        if k is None:
            return None
        items = k if isinstance(k, pikepdf.Array) else [k]
        for it in items:
            if isinstance(it, pikepdf.Dictionary) and it.get("/Type") == "/OBJR":
                obj = it.get("/Obj")
                if obj is None:
                    continue
                action = obj.get("/A")
                if action is not None and action.get("/URI") is not None:
                    return str(action.get("/URI"))
        return None


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
# 902c — THREE THINGS IN THE TEXT THAT ARE TYPOGRAPHY, NOT CONTENT, each found
# by a reader of the output rather than by a test:
#
#   * A NUL. `/Alt` on a figure ends with one in two documents — a C-string
#     terminator left in a PDF text string: `![Logo: GrackleDocs \x00](figure)`.
#     It made `grep` call the whole markdown a BINARY FILE and refuse to print a
#     match, so one NUL hides a 65 KB document from every line-based tool.
#   * A SOFT HYPHEN (U+00AD), 10 of them in ISO/TS 32005 — `exposi<AD>tion`,
#     `sur<AD>rounding`. It is a discretionary break the producer wrote into the
#     source; it is invisible, and it makes a search for `exposition` fail.
#   * A DOT LEADER. A table-of-contents row reaches the tree as real content
#     with its leader attached: `...........................6`. 38 such rows in
#     ISO/TS 32004 — MORE than the geometric route produced, because this layer
#     keeps the TOC it is right to keep.
#
# WHAT GOES AND WHAT STAYS, narrowed after pdf2mmd2 pointed out that the first
# version of this was too wide. Dropping the whole of category Cf takes the
# ZERO WIDTH JOINER and NON-JOINER with it, and those are not noise: Devanagari,
# Arabic and emoji sequences are spelled with them, so stripping Cf corrupts
# every script that needs one. This corpus is Latin and would never have shown
# it; the rule lives in a shared path and the next document is not ours to
# assume.
#
# So: CONTROL characters (Cc) go, except tab and newline — that covers NUL, DEL
# and the C1 block. Plus exactly two format characters that are never content in
# extracted text: the SOFT HYPHEN, which is a discretionary break (13 measured
# here), and a BYTE ORDER MARK, which is a file-encoding artifact. Every other
# format character stays.
#
# A PRIVATE-USE character (Co) stays too and is counted instead — U+F0A7 and
# U+F06E are Symbol-font glyphs here. That is the `(cid:N)` principle: a visible
# oddity someone can find beats a silent guess about what a private glyph meant.
#
# Measured on the raw chars cache of all eleven documents: ZERO Cc and ZERO Cf
# characters, 25 private-use. So none of this noise comes through pdfplumber —
# it arrives in the tree's OWN strings, `/ActualText` and `/Alt`, which are
# producer-authored. That is exactly where a C-string terminator and a
# discretionary hyphen would be written by hand.
_DROP_FORMAT = {"\u00ad", "\ufeff"}
_DOT_LEADER = re.compile(r"\s*\.{4,}\s*")


def _strip_noise(s: str) -> str:
    out = []
    for ch in s or "":
        if ch in "\n\t":
            out.append(ch)
        elif ch in _DROP_FORMAT:
            continue
        elif unicodedata.category(ch) == "Cc":
            continue
        else:
            out.append(ch)
    return _DOT_LEADER.sub(" … ", "".join(out))


def _clean(s: str) -> str:
    """Collapse whitespace and drop what is typography rather than content.

    A marked-content run carries the line breaks of the PAGE, which are a
    typesetting fact and not a content one.
    """
    return " ".join(_strip_noise(s or "").split())


def _cell(s: str) -> str:
    """A pipe table cell: no bare `|`, no newline."""
    return _clean(s).replace("|", "\\|")


class _Renderer:
    def __init__(self, tree: StructTree):
        self.t = tree
        self.out: list[str] = []
        self.stats = collections.Counter()
        self._blockcache: dict = {}

    def _has_block_descendant(self, node, depth: int = 0) -> bool:
        """Does anything under `node` need its own block of markdown?

        Memoised by object id: ISO 32000-2 has 78,468 elements and this
        question is asked of every `/P` on the way down.
        """
        try:
            key = node.objgen
        except Exception:                                    # noqa: BLE001
            key = id(node)
        hit = self._blockcache.get(key)
        if hit is not None:
            return hit
        found = False
        if depth <= _MAX_DEPTH:
            for c in self.t.element_kids(node):
                r = self.t.role(c)
                if r in _BLOCK_ROLES or r in _HEADING or \
                        self._has_block_descendant(c, depth + 1):
                    found = True
                    break
        self._blockcache[key] = found
        return found

    # -- emit helpers ------------------------------------------------------
    def para(self, text: str):
        text = _clean(text)
        if text:
            self.out.append(text)
            self.stats["paragraphs"] += 1

    def table(self, node, pg: int):
        """A `/Table` as a pipe table, header row from `/TH` or `/THead`."""
        rows: list[tuple[bool, list[str]]] = []

        def walk(n, p, in_head: bool):
            r = self.t.role(n)
            if r == "/TR":
                cells, kinds = [], []
                for c in self.t.element_kids(n):
                    cr = self.t.role(c)
                    if cr in ("/TD", "/TH"):
                        kinds.append(cr)
                        cells.append(_cell(self.t.text_of(c, self.t.page_of(c, p))))
                # A HEADER ROW IS ALL `/TH`, or sits inside `/THead`. ISO tables
                # put a `/TH` in the LEFT COLUMN of every data row as a row
                # label, and treating one `/TH` as a header promoted every such
                # row — which merges the whole table into its own header.
                head = in_head or (bool(kinds) and all(k == "/TH" for k in kinds))
                if cells:
                    rows.append((head, cells))
                return
            nxt = in_head or r == "/THead"
            for c in self.t.element_kids(n):
                walk(c, self.t.page_of(c, p), nxt)

        walk(node, pg, False)
        if not rows:
            return
        width = max(len(cells) for _, cells in rows)
        # The header is the LEADING run of header rows. A /TH appearing later
        # is a row label (ISO tables use them in the left column), not a new
        # header, and promoting it would split one table into several.
        head_count = 0
        for is_head, _ in rows:
            if not is_head:
                break
            head_count += 1
        if head_count == len(rows) > 1:
            # EVERY ROW IS ALL-`/TH`. 8 of ISO 32000-2's 732 tables are like
            # this — the PostScript operator tables, where the producer tagged
            # each cell as a header. Taking them all as header leaves no data
            # rows and the separator lands at the BOTTOM of the block, which no
            # markdown reader shows as a table. One header, the rest data.
            head_count = 1
        if head_count == 0:
            # No header row at all. Markdown has no such table, so emit an
            # empty header rather than silently promoting the first data row.
            rows.insert(0, (True, [""] * width))
            head_count = 1

        def line(cells):
            cells = list(cells) + [""] * (width - len(cells))
            return "| " + " | ".join(cells) + " |"

        block = [line(cells) for _, cells in rows[:head_count]]
        block.append("|" + "|".join([" --- "] * width) + "|")
        block.extend(line(cells) for _, cells in rows[head_count:])
        self.out.append("\n".join(block))
        self.stats["tables"] += 1
        self.stats["table_rows"] += len(rows)

    def lst(self, node, pg: int, depth: int = 0):
        """Entry point: render the whole list as ONE block."""
        lines: list[str] = []
        self._lst_lines(node, pg, depth, lines)
        if lines:
            self.out.append("\n".join(lines))

    def _lst_lines(self, node, pg: int, depth: int, lines: list):
        """`/L` -> a markdown list. `/Lbl` becomes the bullet when it is one."""
        indent = "  " * depth
        for li in self.t.element_kids(node):
            if self.t.role(li) != "/LI":
                continue
            label, body, sublists = "", [], []
            for part in self.t.element_kids(li):
                pr = self.t.role(part)
                p2 = self.t.page_of(part, pg)
                if pr == "/Lbl":
                    label = _clean(self.t.text_of(part, p2))
                elif pr == "/LBody":
                    inner = [c for c in self.t.element_kids(part)
                             if self.t.role(c) == "/L"]
                    sublists.extend(inner)
                    body.append(_clean(self.t.text_of(part, p2)) if not inner
                                else _clean(self.t.text_of(part, p2)))
                elif pr == "/L":
                    sublists.append(part)
            text = _clean(" ".join(x for x in body if x))
            bullet = "-"
            if label and label.rstrip(".").rstrip(")").isdigit():
                bullet = label if label.endswith((".", ")")) else label + "."
            if text:
                lines.append(f"{indent}{bullet} {text}")
                self.stats["list_items"] += 1
            for sub in sublists:
                self._lst_lines(sub, self.t.page_of(sub, pg), depth + 1, lines)

    # -- the walk ----------------------------------------------------------
    def walk(self, node, pg: int, depth: int = 0, section: int = 0):
        if depth > _MAX_DEPTH:
            return
        role = self.t.role(node)
        pg = self.t.page_of(node, pg)
        self.stats[f"role:{role}"] += 1

        if role in _HEADING:
            text = _clean(self.t.text_of(node, pg))
            if text:
                self.out.append("#" * _HEADING[role] + " " + text)
                self.stats["headings"] += 1
            return
        if role == "/H":
            # The generic heading carries no level; its nesting depth is the
            # only level information the file gives.
            text = _clean(self.t.text_of(node, pg))
            if text:
                self.out.append("#" * max(1, min(6, section + 1)) + " " + text)
                self.stats["headings"] += 1
            return
        if role == "/Table":
            self.table(node, pg)
            return
        if role == "/L" or role == "/TOC":
            self.lst(node, pg)
            return
        if role == "/Figure":
            alt = node.get("/Alt")
            cap = _clean(str(alt)) if alt is not None else ""
            self.out.append(f"![{cap}](figure)" if cap else "![](figure)")
            self.stats["figures"] += 1
            return
        if role == "/Formula":
            alt = node.get("/Alt")
            body = _clean(str(alt)) if alt is not None else \
                _clean(self.t.text_of(node, pg))
            if body:
                self.out.append(f"$$ {body} $$")
                self.stats["formulas"] += 1
            return
        if role == "/Caption":
            text = _clean(self.t.text_of(node, pg))
            if text:
                self.out.append(f"*{text}*")
                self.stats["captions"] += 1
            return
        if role == "/BlockQuote":
            text = _clean(self.t.text_of(node, pg))
            if text:
                self.out.append("> " + text)
                self.stats["blockquotes"] += 1
            return
        if role == "/P" or role in _INLINE:
            # A `/P` CAN CONTAIN A BLOCK. Measured on ISO/TS 32005, whose every
            # table hangs below one: the ancestor chain to the first row is
            # `/Document > /Art > /Sect > /P > /Table > /THead > /TR`, because
            # the producer's `/Table_Position` style maps to `/P` through
            # `/RoleMap`. Treating `/P` as a leaf flattened 583 table elements
            # and 151 rows into running prose and reported 0 tables — the exact
            # fault this layer exists to remove, reintroduced one level up.
            if self._has_block_descendant(node):
                for c in self.t.element_kids(node):
                    self.walk(c, self.t.page_of(c, pg), depth + 1, section)
                return
            self.para(self.t.text_of(node, pg))
            return
        if role == "/Link":
            text = _clean(self.t.text_of(node, pg))
            uri = self.t.link_uri(node)
            if text:
                self.out.append(f"[{text}]({uri})" if uri else text)
                self.stats["links"] += 1
            return

        # A container, standard or unknown: recurse. Unknown wrappers cost
        # nothing; an unknown LEAF would drop its text, which is why only
        # recognised leaves return above.
        nxt = section + 1 if role in _BLOCK_CONTAINER and role != "/Document" \
            else section
        kids = self.t.element_kids(node)
        if not kids:
            # A leaf we have no rule for still has text, and dropping it would
            # be the silent loss this module exists to avoid.
            self.para(self.t.text_of(node, pg))
            self.stats[f"unrecognised_leaf:{role}"] += 1
            return
        for c in kids:
            self.walk(c, self.t.page_of(c, pg), depth + 1, nxt)


def project(pdf: Path, chars_json: Path | None = None) -> tuple[str, dict]:
    """Markdown from `pdf`'s structure tree, plus a stats dict.

    Raises `NoStructure` when the file has no usable tree -- never a silent
    fallback to the geometric route.
    """
    import pikepdf

    # WHICH SOURCE FOR THE TEXT. The cache is far faster, but it is one JSON
    # document and `json.load` holds all of it: ISO 32000-2's is 1.3 GB over
    # 1,023 pages, which is tens of gigabytes of Python objects. Above the
    # threshold, read the PDF instead — pdfplumber walks a page at a time, so
    # the memory is bounded by the biggest page and only the time changes.
    chars_json = Path(chars_json) if chars_json is not None else None
    if chars_json is not None and chars_json.exists() and \
            chars_json.stat().st_size <= _CACHE_BYTES_MAX:
        mc, mcstats = marked_content_from_chars_json(chars_json)
        mcstats["text_source"] = "chars.json"
    else:
        mc, mcstats = marked_content_from_pdf(pdf)
        mcstats["text_source"] = "pdfplumber"

    with pikepdf.open(str(pdf)) as handle:
        tree = StructTree(handle, mc)
        r = _Renderer(tree)
        kids = tree.element_kids(tree.root)
        if not kids:
            raise NoStructure("/StructTreeRoot has no child elements")
        for k in kids:
            r.walk(k, tree.page_of(k, 0))
        body = "\n\n".join(x for x in r.out if x.strip())
        if not body.strip():
            raise NoStructure("the structure tree yielded no text")
        stats = dict(r.stats)
        stats["marked_content_runs"] = len(mc)
        stats["rolemap_entries"] = len(tree.rolemap)
        stats.update(mcstats)
        pua = sum(1 for ch in body if unicodedata.category(ch) == "Co")
        if pua:
            stats["private_use_chars"] = pua
        return body + "\n", stats
