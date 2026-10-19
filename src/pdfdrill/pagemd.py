r"""One page of model-read Markdown -> the printed-line items a lines.json holds.

WHERE THIS SITS
---------------
A vision model reads a page image and returns Markdown with LaTeX in it. That
is a reading of the page's CONTENT and carries no geometry at all. A
`lines.json` is a reading of content AND geometry, one record per printed line.
This module does the content half: Markdown in, typed items out, each item one
printed line with the `type` and `text` MathPix would have given it.
`gemma_reader` then attaches the geometry and writes the file.

The split is deliberate. The content half is pure, total and testable from a
string; the geometry half needs a 400-dpi render and numpy. Keeping them apart
is what makes it possible to test a reading against MathPix's without a key, a
network call or a GPU — which is the only way this lane could be verified at
all, since every verification run would otherwise cost money from a 10 EUR
account.

THE TYPE VOCABULARY IS NOT OURS TO INVENT
-----------------------------------------
`src/docmodel/line_types.py` is the single source of truth for what a line
type MEANS here, and five readers enforce it. A reader that invents a type
puts a line outside every one of those gates: it is not a transclusion host,
not furniture, not a caption anchor — it is nothing, and it fails silently,
which is the failure class that gate exists to prevent. So this module emits
only types MathPix emits, and `KNOWN_TYPES` below is checked by a test against
`line_types` rather than written out a second time.

WHAT THE MODEL IS ASKED FOR, AND WHAT IS DERIVED
------------------------------------------------
The prompt (`docs/prompts/2026-10-19-page-ocr-markdown-prompt.md`) asks for
ordinary Markdown: one line per printed line, `$$...$$` for a display
equation, `$...$` inline, `#` headings, `|` tables, `[^1]:` footnotes, and the
page's own furniture (running head, folio) inside an HTML comment so it cannot
be mistaken for body text. Everything else here is DERIVED, because a model
asked for structural metadata invents it:

* an equation's number is lifted out of the display into its own
  `equation_number` item — MathPix emits it as a separate line, and pdfdrill's
  equation-number recovery (`eqnums`, and T-0024's splitter) reads it there;
* paragraph starts come from blank lines, not from a model's claim about them,
  and become the leading "\n\n" in `text_display` that every projector reads;
* a continued line's `subtype` comes from how the previous line ENDED (a
  hyphen, or no terminal punctuation), which is a property of the text and not
  an opinion.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

#: Every type this module can emit. Each one is a type MathPix emits and
#: `docmodel.line_types` knows; `test_pagemd.py` holds that to the module
#: rather than trusting this comment.
KNOWN_TYPES = frozenset({
    "text", "math", "equation_number", "section_header", "page_info",
    "footnote", "figure_label", "diagram", "table", "simple_cell",
    "list_item", "title",
})

#: Types whose text is prose a sentence runs through, so a paragraph can
#: continue across them and `subtype` is meaningful.
_PROSE = frozenset({"text", "list_item", "footnote"})

# A display equation's number, either tagged or printed at the left margin.
_TAG = re.compile(r"\\tag\*?\{([^{}]*)\}")
_LEADING_NUMBER = re.compile(r"^\(\s*([0-9]+[a-z]?'*)\s*\)\s*(?:\\q?quad\s*)?")
_TRAILING_NUMBER = re.compile(r"\s*(?:\\q?quad\s*)?\(\s*([0-9]+[a-z]?'*)\s*\)$")

# Page furniture the prompt asks for inside an HTML comment, and the
# `page N | Head` spelling it asks for inside that comment.
_COMMENT = re.compile(r"^<!--\s*(.*?)\s*-->$")
_FURNITURE = re.compile(r"^(?:page|seite|p\.?)\s*([0-9ivxlcIVXLC]+)\s*[|\u2014-]\s*(.*)$",
                        re.I)
# A printed footnote rule \u2014 everything under it on the page is footnote text,
# which is the ONLY way a footnote continued from the previous page (no label
# of its own) can be recognised at all.
_RULE = re.compile(r"^[_\-\u2014\u2013]{4,}$")
# A Markdown thematic break the model wrote of its own accord. Not the printed
# footnote rule and not printed text: dropped, and it opens nothing.
_THEMATIC = re.compile(r"^(?:\*\s*){3,}$|^(?:\*{3,})$")
_FOOTNOTE_DEF = re.compile(r"^\[\^([^\]]+)\]:\s*(.*)$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST_ITEM = re.compile(r"^(?:[-*+]|\(?[0-9]+[.)])\s+(.+)$")
_FIGURE_LABEL = re.compile(
    r"^[\[*]*(?:Fig\.|Figure|Abb\.|Abbildung|Tab\.|Table|Tafel)\s*"
    r"[0-9IVXivx]+[.:]?[\]*]*$", re.I)
_FIGURE_DESC = re.compile(
    r"^\[\s*(?:Graph|Figure|Fig\.|Chart|Diagram|Image|Picture|Plot)\b", re.I)
_TABLE_SEP = re.compile(r"^\|(?:\s*:?-{2,}:?\s*\|)+$")
#: A heading that is ONLY a section number. Its title is printed on the NEXT
#: line, and MathPix emits the pair as one container (measured: 9 of 9 on the
#: reference document). A heading with words in it is a heading already.
_NUMBER_ONLY = re.compile(
    r"^(?:§|Art\.|Kap\.|Chap\.|Sect\.)?\s*[0-9]+[a-z]?\s*\.?$|"
    r"^(?:§|Art\.|Kap\.)?\s*[IVXLCDM]+\s*\.?$")
_EMPH = re.compile(r"\*\*(.+?)\*\*|\*(.+?)\*|__(.+?)__|_(.+?)_")
# `$...$` that is not `$$`, not escaped. Non-greedy, so two inline spans on
# one line stay two spans.
_INLINE = re.compile(r"(?<![\\$])\$(?!\$)(.+?)(?<![\\$])\$(?!\$)")

#: A prose line that ends with one of these is a finished sentence; anything
#: else is a line the next one continues.
_TERMINAL = ".!?:;\u2019\"')]}\u00bb\u201d"


def _reduce(s: str) -> str:
    """A line down to its letters and digits, lowercased \u2014 for comparing two
    spellings of the same running head without caring about the markup the
    model put around it."""
    return re.sub(r"[^0-9a-z\u00e4\u00f6\u00fc\u00df]", "", s.lower())


@dataclass
class Item:
    """One printed line, before it has a box.

    `text` is in MathPix's spelling (`\\(..\\)` inline, `\\[..\\]` display) so
    that everything downstream — the model builder, the projectors, the
    transclusion gate — reads it the way it reads a bought reading.
    """
    type: str
    text: str
    para_start: bool = False
    #: The display equation this number belongs to; only set on an
    #: `equation_number`. A REFERENCE TO THE ITEM, not an index into the list:
    #: three post-passes insert containers and renumber everything after them,
    #: and an index that silently comes to mean a different line is how a
    #: number ends up boxed onto someone else's equation.
    numbers: Optional["Item"] = None
    #: Table identity: rows of one printed table share it.
    table: Optional[int] = None
    cells: Optional[list[str]] = None
    #: A cell's (printed row, column) inside its table.
    cell: Optional[tuple[int, int]] = None
    #: The item whose INK ROW this item shares — the second and later cells
    #: of a printed table row share the first cell's row, the way a running
    #: head shares the folio's. Set here because only the parser knows which
    #: items were one printed row.
    shares: Optional["Item"] = None
    #: "continues_line_space" / "continues_line_no_hyphen", MathPix's spelling.
    subtype: str = ""
    #: The source Markdown line, kept for diagnostics and for the ink
    #: alignment, which needs to know how wide a line's content is.
    md: str = ""
    #: True when the model DESCRIBED something instead of transcribing it (a
    #: figure). Such an item is furniture with a box, never prose.
    described: bool = False
    #: Container structure, MathPix's: a parent holds its children and has
    #: empty `text`; a child names its parent. By reference, as `numbers` is.
    children: list["Item"] = field(default_factory=list)
    parent: Optional["Item"] = None
    #: An explicit `text_display`, when it is not derivable from the text (the
    #: `\footnotetext{…}` wrapper that spans a footnote's children).
    display: Optional[str] = None


def inline_math(s: str) -> str:
    r"""`$x$` -> `\(x\)`, leaving `\(`/`\[` already present alone."""
    return _INLINE.sub(lambda m: "\\(" + m.group(1).strip() + "\\)", s)


def strip_emphasis(s: str) -> str:
    """Markdown bold/italic markers off: the printed line has no asterisks.

    Applied to PROSE only. A display equation may legitimately contain `*`
    (a multiplication dot in some readings) and a table cell's `**` is the
    model's emphasis of a header cell, which `table` keeps verbatim.
    """
    prev = None
    while prev != s:                       # nested **_x_** needs two passes
        prev = s
        s = _EMPH.sub(lambda m: next(g for g in m.groups() if g is not None), s)
    return s


def _continuation(prev_text: str) -> str:
    """How the NEXT line continues `prev_text`, in MathPix's vocabulary."""
    t = prev_text.rstrip()
    if not t:
        return ""
    if t.endswith("-") or t.endswith("\u00ad"):
        # A hyphen at a line end is a broken word. MathPix calls the line that
        # follows it nothing at all (the join is in the text); we mark it so
        # `compose`'s join rules have the same information from either reader.
        return "continues_line_hyphen"
    if t[-1] in _TERMINAL:
        return ""
    return "continues_line_no_hyphen"


def _split_number(body: str) -> tuple[str, Optional[str]]:
    r"""A display equation's body and its printed number, separated.

    Three spellings, all seen in the same document: `\tag{3}`, a number at the
    left margin (`(3)\quad x=y`, German 19th-century practice), and one at the
    right (`x=y \quad (3)`). The number is removed from the body because the
    body is what gets typeset and compared; a number left inside it reappears
    as part of the equation and then as its own line, which is the duplicate
    `eqnums` exists to reconcile.
    """
    nums = _TAG.findall(body)
    body = _TAG.sub("", body).strip()
    if not nums:
        m = _LEADING_NUMBER.match(body)
        if m:
            nums = [m.group(1)]
            body = body[m.end():].strip()
    if not nums:
        m = _TRAILING_NUMBER.search(body)
        if m:
            nums = [m.group(1)]
            body = body[:m.start()].strip()
    return body, (nums[0] if nums else None)


def items(md: str) -> list[Item]:
    """Parse one page's Markdown into printed-line items, in reading order."""
    out: list[Item] = []
    para_start = True
    in_footnotes = False
    table_no = 0
    last_prose = ""
    furniture: list[str] = []          # reductions of this page's head/folio

    for raw in md.splitlines():
        s = raw.strip()
        if not s:
            para_start = True
            continue

        # --- page furniture: the running head / folio, in a comment -------
        m = _COMMENT.match(s)
        if m:
            text = m.group(1).strip()
            if text:
                # MEASURED on both reference readings: MathPix emits the folio
                # and the running head as TWO page_info lines with separate
                # boxes, because they are printed at opposite ends of the same
                # row. One line carrying "5 | Head" would be a box spanning the
                # whole row, which is not where either piece of ink is.
                f = _FURNITURE.match(text)
                parts = [f.group(1), f.group(2)] if f else [text]
                for piece in parts:
                    piece = piece.strip()
                    if piece:
                        out.append(Item("page_info", piece,
                                        para_start=True, md=s))
                        furniture.append(_reduce(piece))
            para_start = True
            continue

        # --- a thematic break the model invented: not printed -------------
        if _THEMATIC.match(s):
            para_start = True
            continue

        # --- the footnote rule: a horizontal line, then footnote text -----
        if _RULE.match(s):
            in_footnotes = True
            para_start = True
            continue

        # --- the running head written a second time, as text --------------
        # The prompt asks for it once, in the comment. Models repeat it
        # anyway (measured: 1 of 48 Killing pages), and a repeat typed as
        # prose is a paragraph of body text that never existed — it joins the
        # paragraph below it and corrupts the join, which is exactly the
        # defect T-0010 was about.
        if furniture and not in_footnotes:
            red = _reduce(s)
            if red and any(h and h in red and len(red) <= len(h) + 8
                           for h in furniture):
                para_start = True
                continue

        # --- tables ------------------------------------------------------
        if s.startswith("|"):
            if _TABLE_SEP.match(s):
                continue                   # alignment row: nothing is printed
            cells = [c.strip() for c in s.strip().strip("|").split("|")]
            if not any(cells):
                continue                   # a padded empty row
            if not (out and out[-1].type == "table" and out[-1].table):
                table_no += 1
            out.append(Item("table", " ".join(c for c in cells if c),
                            para_start=True, table=table_no,
                            cells=[inline_math(c) for c in cells], md=s))
            para_start = True
            continue

        # --- a figure the model described rather than transcribed --------
        if _FIGURE_DESC.match(s):
            out.append(Item("diagram", s.strip("[]").strip(),
                            para_start=True, md=s, described=True))
            para_start = True
            continue

        # --- display math ------------------------------------------------
        if s.startswith("$$"):
            body, num = _split_number(s.strip("$").strip())
            if body:
                out.append(Item("math", "\\[\n" + body + "\n\\]",
                                para_start=True, md=s))
                if num:
                    out.append(Item("equation_number", f"({num})",
                                    numbers=out[-1], md=s))
            para_start = True
            last_prose = ""
            continue

        # --- headings ----------------------------------------------------
        m = _HEADING.match(s)
        if m:
            text = strip_emphasis(m.group(2).strip())
            out.append(Item("title" if len(m.group(1)) == 1 and not out
                            else "section_header",
                            inline_math(text), para_start=True, md=s))
            para_start = True
            last_prose = ""
            continue

        # --- a label on its own line -------------------------------------
        if _FIGURE_LABEL.match(s):
            out.append(Item("figure_label", strip_emphasis(s.strip("[]*")),
                            para_start=True, md=s))
            para_start = True
            continue

        # --- footnotes ---------------------------------------------------
        m = _FOOTNOTE_DEF.match(s)
        if m:
            label, body = m.group(1), m.group(2)
            # `FootnoteProcessor._refnum` reads the label as `\( { }^{n} \)`;
            # a `[^1]:` spelling is invisible to it, and a footnote whose
            # refnum never parses cannot be paired with its marker in the
            # text. So the label is rewritten into the shape that reader
            # looks for — `footnote_split.LABEL`.
            text = ("\\( { }^{" + label + "} \\) "
                    + inline_math(strip_emphasis(body))).strip()
            out.append(Item("footnote", text, para_start=True, md=s))
            in_footnotes = True
            para_start = True
            last_prose = body
            continue

        # --- ordinary prose (or footnote continuation) --------------------
        text = inline_math(strip_emphasis(s))
        kind = "footnote" if in_footnotes else "text"
        m = _LIST_ITEM.match(s)
        if m and kind == "text":
            kind = "list_item"
        it = Item(kind, text, para_start=para_start, md=s)
        if not para_start and last_prose:
            it.subtype = _continuation(last_prose)
        out.append(it)
        para_start = False
        last_prose = s

    return _wrap_footnotes(_wrap_section_headers(_wrap_tables(out)))


def _tabular(rows_of_cells: list[list[str]]) -> str:
    r"""The LaTeX `tabular` MathPix puts in a `table` line's `text`.

    Spelled the way MathPix spells it — `\begin{tabular}[t]{|l|l|}`, `\hline`
    before each row, `\\` between them — because `TableProcessor` reads this
    string and `docops`' table projections re-emit it. A reader that invents
    its own table spelling produces a table that renders differently from the
    same table read by MathPix, in the same document.
    """
    ncol = max((len(r) for r in rows_of_cells), default=0)
    if not ncol:
        return ""
    spec = "|" + "|".join("l" * ncol) + "|"
    body = []
    for r in rows_of_cells:
        padded = list(r) + [""] * (ncol - len(r))
        body.append("\\hline " + " & ".join(padded))
    return ("\\begin{tabular}[t]{" + spec + "}\n"
            + " \\\\\n".join(body) + " \\\\\n\\hline\n\\end{tabular}")


def _wrap_tables(out: list[Item]) -> list[Item]:
    """A run of printed table rows -> MathPix's `table` + `simple_cell` shape.

    MEASURED: MathPix emits ONE `table` line carrying the whole `tabular` in
    `text` with `conversion_output` true, plus one `simple_cell` per cell with
    its own tight box and `conversion_output` false. The cells are where a
    table's geometry lives — 2,364 of them on one 14-page document — and a
    reader that emits a box per table ROW has no geometry for any cell in it.
    """
    res: list[Item] = []
    i = 0
    while i < len(out):
        if out[i].type != "table" or out[i].cells is None:
            res.append(out[i])
            i += 1
            continue
        j = i
        tid = out[i].table
        while (j < len(out) and out[j].type == "table"
               and out[j].table == tid):
            j += 1
        block = out[i:j]
        grid = [list(b.cells or []) for b in block]
        parent = Item("table", _tabular(grid), para_start=True,
                      md=block[0].md, table=tid, display="")
        res.append(parent)
        for r, brow in enumerate(block):
            head: Optional[Item] = None
            for c, text in enumerate(brow.cells or []):
                it = Item("simple_cell", text, md=brow.md, table=tid,
                          cell=(r, c), parent=parent, display="")
                if head is None:
                    head = it
                else:
                    it.shares = head
                parent.children.append(it)
                res.append(it)
        i = j
    return res


def _wrap_section_headers(out: list[Item]) -> list[Item]:
    """A number-only heading plus the title under it = one `section_header`.

    MEASURED: MathPix emits a two-line section heading as a container with
    empty text whose children are the number line and the title line, both
    typed `text` — the same shape it uses for a footnote and for a title
    block. A reader that emits the number as a `section_header` and the title
    as body prose disagrees with it on BOTH lines: the number's box is one
    line where the reference has two, and the title becomes a paragraph of
    body text that the section it names does not contain.
    """
    res: list[Item] = []
    i = 0
    while i < len(out):
        it = out[i]
        nxt = out[i + 1] if i + 1 < len(out) else None
        if (it.type == "section_header" and _NUMBER_ONLY.match(it.text.strip())
                and nxt is not None and nxt.type == "text" and nxt.text):
            parent = Item("section_header", "", para_start=True,
                          md=it.md, display="")
            res.append(parent)
            for child in (it, nxt):
                child.type = "text"
                child.parent = parent
                child.display = child.text
                parent.children.append(child)
                res.append(child)
            i += 2
            continue
        res.append(it)
        i += 1
    return res


def _wrap_footnotes(out: list[Item]) -> list[Item]:
    r"""Turn each run of footnote lines into MathPix's container shape.

    MEASURED on both reference readings, and this is not a detail: MathPix
    does NOT type a footnote's printed lines `footnote`. It emits ONE
    `footnote` line with EMPTY text, `conversion_output` false, a region that
    is the union of the block, and `children_ids`; the printed lines are its
    children, typed `text`, each carrying `parent_id`. The first child's
    `text_display` opens `\footnotetext{` and the last child's closes it.

    That wrapper is the whole point. `FootnoteProcessor` takes a footnote's
    body from a balanced `\footnotetext{…}` and its refnum from a
    `\( { }^{n} \)` label; a reading that types the lines `footnote` and
    writes no wrapper produces objects with the right type and no body —
    measured at 0 bodies before the wrapper was added, 3 after. So emitting
    the container is not imitation for its own sake: it is the difference
    between a footnote pdfdrill can read and one it cannot.
    """
    res: list[Item] = []
    i = 0
    while i < len(out):
        if out[i].type != "footnote":
            res.append(out[i])
            i += 1
            continue
        j = i
        while j < len(out) and out[j].type == "footnote":
            j += 1
        block = out[i:j]
        parent = Item("footnote", "", para_start=True,
                      md=block[0].md, display="")
        res.append(parent)
        for k, child in enumerate(block):
            child.type = "text"
            child.parent = parent
            body = child.text
            if k == 0 and len(block) == 1:
                child.display = "\n\n\\footnotetext{\n" + body + "\n}"
            elif k == 0:
                child.display = "\n\n\\footnotetext{\n" + body
            elif k == len(block) - 1:
                child.display = body + "\n}"
            else:
                child.display = body
            parent.children.append(child)
            res.append(child)
        i = j
    return res


def text_display(it: Item) -> str:
    r"""MathPix's `text_display`: the line's text with its paragraph break.

    MathPix writes a leading "\n\n" on the first line of a paragraph and "\n"
    before a display equation, and every projector in `docops` reads that
    rather than recomputing it. An `equation_number` has an EMPTY
    `text_display` — measured on both reference readings — because it is not
    part of the flowed text at all.
    """
    if it.display is not None:
        return it.display
    if it.type == "equation_number":
        return ""
    if it.type == "math":
        return "\n" + it.text
    if it.para_start and it.type in _PROSE:
        return "\n\n" + it.text
    return it.text
