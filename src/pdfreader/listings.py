r"""listings — the properties of a code listing, read off the page.

781 — A LISTING IS A GRID, AND NOTHING READ IT AS ONE.

`LineNode.verbatim` has known since 748 that a line is set in a typewriter
face, and both projectors used that knowledge only to choose a wrapper: the
markdown fenced it, the LaTeX projection did not even do that and ran the
code into a paragraph. The TEXT of the line was built by `_run_text` either
way, which reconstructs word breaks from a gap THRESHOLD -- one space for
any gap wider than a fraction of the type size.

That is right for prose and wrong for code, and it is wrong in the one place
where whitespace is content:

    for (j in 0..M)
      b1[j] = a*f1[i,j]

reaches `_run_text` as two lines starting at x=56.69 and x=73.63, and comes
out flush left, because leading space is not a GAP BETWEEN GLYPHS at all --
there is no glyph to its left. Measured over the gold set before this
module, indentation survived on 24% of lines.

A monospace font gives the exact measurement the threshold was standing in
for. Every character occupies one cell, so the advance between two adjacent
glyphs is a whole number of cells:

    lst-004, 5pt ttfamily        cell 4.23pt
      'float'  f->l->o->a->t     4.23 4.23 4.23 4.23      adjacent
      'b1[M], b2[M]'   ,->b      8.47                     one space
      'for' indented 2           16.83 from the gutter    two cells
      'b1[j]' indented 4         25.31                    four cells

so the number of spaces between two glyphs is `round(dx/cell) - 1`, and the
indent of a line is `round((x0 - left)/cell)` where `left` is the column-0
edge of the block. Both are measurements, not thresholds: a cell that does
not divide the advances evenly is not a grid, and this module abstains.

What it accumulates is what `lstlisting` would have to be told to set the
page again -- the cell, the type size, the line numbers and their step, the
colours, the background -- so that the projection has something to project.
The docmodel stores it on the page (`PageNode.listings`); the projectors
read it there and never re-measure.
"""
from __future__ import annotations

import collections
import re
import statistics
from dataclasses import dataclass, field

import lstlangs
import texmap

#: An advance is a whole number of cells to within this fraction of one.
#: Measured over the gold set: the worst residual on a true grid is 0.07
#: cells (rounding in the PDF's own coordinates); the first non-grid --
#: a proportional face wrongly measured as monospace -- is 0.31.
GRID_TOL = 0.18

#: At least this many advances must land on the grid for the block to be one.
GRID_SHARE = 0.9


@dataclass
class Run:
    """A styled stretch of one line, located in its TEXT, not its glyphs.

    781e — THE COLOURING IS A STYLE TABLE, NOT A MARK IN THE CODE.

    The first projection wrote `moredelim` markers into the body -- `!<for>!`
    -- which is exactly backwards for a listing: what a listing is FOR is a
    body a compiler could be handed. The style belongs beside the code, the
    way `lstlisting` itself says it: `keywordstyle`, `commentstyle`,
    `stringstyle` and a list of words.
    """
    start: int
    end: int
    rgb: tuple
    bold: bool = False
    italic: bool = False
    kind: str = "unknown"        # keyword | comment | string | unknown


@dataclass
class ListingLine:
    """One row of the grid."""
    id: str
    indent: int                  # cells from column 0
    text: str                    # WITHOUT the indent, gutter already dropped
    number: int | None = None    # the line number the page printed, if any
    colors: list = field(default_factory=list)   # list[Run], over `text`
    #: Blank code lines, named by the numbers the page printed for them.
    #: A blank line emits no code glyph at all, so the only thing on the
    #: page that says it exists is its number in the gutter -- and that
    #: number is grouped into the row above or below it, because it stands
    #: in the same column. See `_split_gutter`.
    blank_before: list = field(default_factory=list)
    blank_after: list = field(default_factory=list)


@dataclass
class Listing:
    """What `lstlisting` would have to be told to set this block again."""
    lines: list[ListingLine] = field(default_factory=list)
    ids: set = field(default_factory=set)        # LineNode ids covered
    cell: float = 0.0            # character advance, pt
    left: float = 0.0            # x of column 0
    size: float = 10.0           # basicstyle size, pt
    font: str = ""               # the monospace face the page used
    numbers: bool = False        # `numbers=left`
    firstnumber: int = 1
    stepnumber: int = 1
    background: tuple | None = None
    #: The listing's rectangle -- the frame the author DREW around it when
    #: there is one, and the glyph extent otherwise. `framed` says which:
    #: only the drawn frame is independent of the font, and only it
    #: separates a listing from its gutter and its caption.
    rect: tuple | None = None
    framed: bool = False
    #: What the page says the language is, and on what evidence.
    language: str = ""
    language_source: str = ""    # keywords | declared | detected | ""
    #: WHERE ON THE PAGE, in the page's own line stream. A listing that
    #: becomes a file still has to be findable in the document it came
    #: from, and a rectangle alone cannot say which lines those were.
    page: int = 0
    index: int = 0               # 1-based, this listing's place on the page
    line_start: int = -1         # index into `PageNode.lines`, inclusive
    line_end: int = -1           # inclusive

    @property
    def line_count(self) -> int:
        """Rows the page shows, blank ones included.

        Not `len(self.lines)`: a blank code line leaves no glyph and no
        ListingLine, only a number in the gutter, and a file written
        without it has every line after it at the wrong number.
        """
        return len(self.rows())

    @property
    def extension(self) -> str:
        """The file extension for this listing's language, or `.txt`.

        `.txt` is the abstention, not a default: writing `min.c` for a
        listing whose language was never established is a claim, and a
        wrong one renames the file every time the guess changes.
        """
        return SUFFIX.get(self.language.lower(), ".txt")

    @property
    def stem(self) -> str:
        """`p5-lst3` -- where it is, which is all this object can know."""
        return "p%d-lst%d" % (self.page or 0, self.index or 0)

    def filename(self, doc_id: str = "") -> str:
        """The file this listing would be written as.

        The document id is the CALLER'S, because a page does not know what
        document it is in -- `docmodel_six.build` is given a path and keeps
        none of it. Passing it in keeps the naming honest rather than
        inventing an id here.
        """
        stem = ("%s-%s" % (_slug(doc_id), self.stem)) if doc_id else self.stem
        return stem + self.extension

    def path(self, doc_id: str = "", root: str = "listings") -> str:
        return "%s/%s" % (root.rstrip("/"), self.filename(doc_id)) if root \
            else self.filename(doc_id)

    @property
    def code(self) -> str:
        """THE PROGRAM. Plain text, no markup, tabs and spaces as measured.

        This is the field a compiler or an interpreter could be handed, and
        the reason a listing is not an equation: mathematics wants markup,
        and code wants to be left alone.
        """
        return self.text()

    @property
    def keywords(self) -> list:
        """(word, rgb, bold, italic) for every word the page STYLED.

        `keywordstyle` paints a word iff it is in the keyword list of the
        language the author named, so this is both the style table and the
        strongest evidence on the page about which language that was --
        see `out/lstkeywords.py`.
        """
        out, seen = [], set()
        for ln in self.lines:
            for r in ln.colors:
                if r.kind != "keyword":
                    continue
                for w in ln.text[r.start:r.end].split():
                    key = (w, r.rgb, r.bold, r.italic)
                    if w and key not in seen:
                        seen.add(key)
                        out.append(key)
        return out

    def style_of(self, kind: str):
        """(rgb, bold, italic) the page used for comments / strings, or None."""
        seen: dict = {}
        for ln in self.lines:
            for r in ln.colors:
                if r.kind == kind:
                    seen[(r.rgb, r.bold, r.italic)] = seen.get(
                        (r.rgb, r.bold, r.italic), 0) + 1
        if not seen:
            return None
        return max(seen, key=seen.get)

    @property
    def colors(self) -> list:
        """Distinct colours used, in first-seen order."""
        seen: list = []
        for ln in self.lines:
            for r in ln.colors:
                if r.rgb is not None and r.rgb not in seen:
                    seen.append(r.rgb)
        return seen

    def rows(self) -> list:
        """(number, text) for every line the page shows, blanks included."""
        out: list = []
        for ln in self.lines:
            for n in ln.blank_before:
                out.append((n, ""))
            out.append((ln.number, " " * ln.indent + ln.text))
            for n in ln.blank_after:
                out.append((n, ""))
        return out

    def text(self) -> str:
        return "\n".join(t for _n, t in self.rows())

    # --------------------------------------------------- the indent policy
    @property
    def indents(self) -> list:
        """The distinct indents the page shows, in cells."""
        return sorted({ln.indent for ln in self.lines})

    @property
    def indent_unit(self) -> int:
        """One step of indentation, in cells, or 0 if there is no step.

        781i — TAB POLICY IS CONTENT, AND IT HAS TO BE CARRIED.

        In Python the indent IS the block structure, so a consumer that
        rewrites the whitespace changes the program. The step is the
        greatest common divisor of the indents the page actually shows --
        2 for `0 2 4 6`, 4 for `0 4 8`, and 1 when the indents share no
        divisor, which is the honest answer for hand-aligned code.
        """
        from math import gcd
        step = 0
        for n in self.indents:
            step = gcd(step, n)
        return step

    @property
    def tabsize(self) -> int:
        """What `tabsize=` would have to be told, or 0 when it cannot be.

        The page shows SPACES; a tab that produced them left no mark. So
        this is the indent step and nothing more, and it is 0 rather than
        a guess when the block has one indent level or none.
        """
        return self.indent_unit if len(self.indents) > 1 else 0

    # ------------------------------------------------- the first-guess set
    def colours(self) -> list:
        """[(name, rgb)] for every colour this listing uses."""
        out, seen = [], {}
        for rgb in self.colors:
            seen.setdefault(rgb, "lstclr%d" % len(seen))
        for kind in ("comment", "string"):
            st = self.style_of(kind)
            if st and st[0] is not None:
                seen.setdefault(st[0], "lstclr%d" % len(seen))
        if self.background:
            seen.setdefault(self.background, "lstbg")
        for rgb, name in seen.items():
            out.append((name, rgb))
        return out

    def lstset(self) -> list:
        r"""A FIRST GUESS at the `\lstset` that would set this page again.

        A guess, and labelled one: it is assembled from what was measured
        and nothing else, so what the page never showed is absent rather
        than defaulted. `basicstyle` is the size and face we read;
        `morekeywords` is the words the page actually coloured, which is a
        subset of the language's list and not the list itself.
        """
        def style(rgb, bold, italic):
            names = dict((c, n) for n, c in self.colours())
            out = []
            if rgb is not None:
                out.append(r"\color{%s}" % names[rgb])
            if bold:
                out.append(r"\bfseries")
            if italic:
                out.append(r"\itshape")
            return "".join(out) or r"\relax"

        opt = [(r"basicstyle", r"\ttfamily\fontsize{%.1f}{%.1f}\selectfont"
                % (self.size, 1.2 * self.size)),
               ("columns", "fullflexible"),
               ("keepspaces", "true")]
        if self.language:
            opt.append(("language", self.language))
        if self.tabsize:
            opt.append(("tabsize", str(self.tabsize)))
        if self.numbers:
            opt += [("numbers", "left"),
                    ("firstnumber", str(self.firstnumber)),
                    ("stepnumber", str(self.stepnumber)),
                    ("numberstyle", r"\tiny")]
        groups: dict = {}
        for word, rgb, bold, italic in self.keywords:
            groups.setdefault((rgb, bold, italic), []).append(word)
        for i, (st, words) in enumerate(sorted(groups.items(),
                                               key=lambda kv: -len(kv[1])), 1):
            opt.append(("morekeywords", "[%d]{%s}"
                        % (i, ",".join(sorted(set(words))))))
            opt.append(("keywordstyle", "[%d]{%s}" % (i, style(*st))))
        for kind, key in (("comment", "commentstyle"), ("string", "stringstyle")):
            st = self.style_of(kind)
            if st is not None:
                opt.append((key, "{%s}" % style(*st)))
        if self.background:
            opt.append(("backgroundcolor", r"\color{lstbg}"))
        if self.framed:
            opt.append(("frame", "single"))
        return opt

    def preamble(self) -> list:
        r"""The `\usepackage` and `\definecolor` lines the guess needs."""
        out = [r"\usepackage{listings}"]
        cols = self.colours()
        if cols:
            out.append(r"\usepackage{xcolor}")
        for name, rgb in cols:
            out.append(r"\definecolor{%s}{rgb}{%s}"
                       % (name, ",".join(_num(v) for v in rgb)))
        return out


# --------------------------------------------------------------- the grid
def _mono(glyphs) -> list:
    return [g for g in glyphs if texmap.is_monospace(g.fontname)]


def cell_width(glyphs) -> float | None:
    """The character cell of a monospace run, or None if it is not a grid.

    The cell is the SMALLEST advance that occurs often, not the average: a
    listing whose lines are mostly single words would otherwise measure its
    cell as the word gap. Every other advance must then be a whole number of
    it -- that is the test that says this really is a grid.
    """
    adv = []
    for a, b in zip(glyphs, glyphs[1:]):
        d = b.rect[0] - a.rect[0]
        if d > 0.2:
            adv.append(d)
    if len(adv) < 4:
        return None
    base = min(statistics.multimode([round(d, 1) for d in adv]))
    if base <= 0.2:
        return None
    on = sum(1 for d in adv if abs(d / base - round(d / base)) <= GRID_TOL)
    if on < GRID_SHARE * len(adv):
        return None
    # Refine on the advances that ARE one cell: the mode is rounded to 0.1pt
    # and the indent of a 40-line block multiplies that error by six.
    ones = [d for d in adv if abs(d / base - 1.0) <= GRID_TOL]
    return statistics.median(ones) if ones else base


def grid_text(glyphs, cell: float) -> str:
    """The run's text with every space it shows, counted in cells."""
    if not glyphs:
        return ""
    out = [glyphs[0].text]
    for a, b in zip(glyphs, glyphs[1:]):
        n = int(round((b.rect[0] - a.rect[0]) / cell)) - 1
        if n > 0:
            out.append(" " * n)
        out.append(b.text)
    return "".join(out)


#: How a comment opens, across the languages the gold set carries. A
#: comment is recognised by SHAPE, not by the language: it opens with one
#: of these and runs to the end of the line, which no keyword ever does.
_COMMENT_OPEN = ("//", "#", "%", "--", ";", "/*", "<!--", "!", "'")

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")


def _kind(text: str, run) -> str:
    """keyword | string | unknown for ONE run. Comments are decided by line.

    A string is quoted at both ends; a keyword is one bare word. Anything
    else is left unknown rather than guessed -- a style table with a wrong
    entry recolours the wrong token on every page that uses it.
    """
    body = text[run.start:run.end].strip()
    if not body:
        return "unknown"
    if len(body) >= 2 and body[0] == body[-1] and body[0] in "\"'`":
        return "string"
    if _IDENT.match(body):
        return "keyword"
    words = body.split()
    if len(words) > 1 and all(_IDENT.match(w) for w in words):
        # Several bare words in one style. Keywords only if some single
        # language declares every one of them -- `public static void`
        # does, `You will be evaluated` does not.
        r = lstlangs.rank(words, lstlangs.load(), top=1)
        return "keyword" if r and r[0][1] >= 0.999 else "unknown"
    return "unknown"


def _classify(text: str, runs: list) -> list:
    """Name every run on a line, COMMENTS FIRST.

    A comment is a property of the LINE, not of a run. The grid inserts the
    spaces it measured, so a styled comment arrives as one run per word:

        `// set the gain`  ->  '//'  'set'  'the'  'gain'

    and each of `set`, `the`, `gain` is a bare word, so per-run
    classification files three English words in the keyword table -- which
    then recolours them as keywords on every page that table is used for.

    What separates a comment from a run of keywords is that the comment
    REACHES THE END OF THE LINE and opens with a marker, and that no
    keyword sequence does both. So the tail is taken first and merged into
    one run; whatever is left is classified run by run. `public static
    void` stays three keywords, because it opens with none of the markers.
    """
    if not runs:
        return runs
    end = len(text.rstrip())
    for i, r in enumerate(runs):
        if not text[r.start:r.end].strip().startswith(_COMMENT_OPEN):
            continue
        tail = runs[i:]
        style = (tail[0].rgb, tail[0].bold, tail[0].italic)
        if tail[-1].end < end:
            continue
        if any((t.rgb, t.bold, t.italic) != style for t in tail):
            continue
        merged = Run(r.start, tail[-1].end, r.rgb, r.bold, r.italic, "comment")
        runs = runs[:i] + [merged]
        break
    runs = _join_spans(text, runs)
    runs = _join_strings(text, runs)
    for r in runs:
        if r.kind == "unknown":
            r.kind = _kind(text, r)
    return runs


def _join_spans(text: str, runs: list) -> list:
    """Same style, nothing but spaces between: one span.

    781i — NINE WORDS OF ENGLISH ARE NOT NINE KEYWORDS.

    `_color_runs` starts a new run wherever the glyphs stop abutting, and
    in a grid every space does that. So a string literal arrives as one
    run per word, and lst-121 filed `You`, `will`, `be`, `evaluated`,
    `based`, `on`, `this`, `score` as keywords -- which would be written
    into `morekeywords` and recolour those English words as language
    keywords on every page that table is used for.

    Joining them needs an arbiter, because `public static void` is three
    keywords and must stay three. `_kind` has one: `lstlangs`, the
    keyword lists `listings` itself ships. A multi-word span is keywords
    only if some single language declares ALL of its words.
    """
    out: list = []
    for r in runs:
        if (out and r.kind == "unknown" and out[-1].kind == "unknown"
                and (out[-1].rgb, out[-1].bold, out[-1].italic)
                == (r.rgb, r.bold, r.italic)
                and not text[out[-1].end:r.start].strip()):
            out[-1].end = r.end
        else:
            out.append(r)
    return out


_QUOTE = "\"'`"


def _join_strings(text: str, runs: list) -> list:
    """Merge a styled run that OPENS a quote with the run that closes it.

    781i — AND THE SAME THING AGAIN FOR STRINGS.

    `stringstyle` colours a whole string literal, and the grid splits it
    at every space, so

        "you are an expert computer science researcher"

    arrives as eight runs of one bare word each and eight English words
    were filed as KEYWORDS -- which would then be written into
    `morekeywords` and recolour `expert` and `science` as language
    keywords on every page that table is used for. lst-121 filed 21 of
    them, 18 out of one prompt string.

    A string is bounded by its own quotes, which is evidence no keyword
    has: the run that opens one and the run that closes it are found, and
    everything between them of the SAME style is one literal.
    """
    out: list = []
    i = 0
    while i < len(runs):
        r = runs[i]
        body = text[r.start:r.end].strip()
        if r.kind != "unknown" or not body or body[0] not in _QUOTE:
            out.append(r)
            i += 1
            continue
        q = body[0]
        style = (r.rgb, r.bold, r.italic)
        end = None
        for j in range(i, len(runs)):
            t = runs[j]
            if (t.rgb, t.bold, t.italic) != style:
                break
            b = text[t.start:t.end].strip()
            if (j > i or len(b) > 1) and b.endswith(q):
                end = j
                break
        if end is None:
            out.append(r)
            i += 1
            continue
        out.append(Run(r.start, runs[end].end, r.rgb, r.bold, r.italic,
                       "string"))
        i = end + 1
    return out


def _color_runs(glyphs, cell: float) -> list:
    """(start, end, rgb) over `text` for every non-black run.

    Indices are into the text `grid_text` built from the same glyphs and the
    same cell, so the spaces it inserted are counted: a colour that started one character late painted the wrong
    token, which is worse than no colour at all.
    """
    runs: list = []
    pos = 0
    prev = None
    for g in glyphs:
        if prev is not None:
            pos += max(0, int(round((g.rect[0] - prev.rect[0]) / cell)) - 1)
        start = pos
        pos += len(g.text)
        prev = g
        rgb = g.color
        if rgb is None or (max(rgb) < 0.02 and min(rgb) < 0.02):
            rgb = None
        bold = texmap.is_bold(g.fontname)
        italic = texmap.is_italic(g.fontname)
        if (runs and runs[-1].rgb == rgb and runs[-1].end == start
                and runs[-1].bold == bold and runs[-1].italic == italic):
            runs[-1].end = pos
        else:
            runs.append(Run(start, pos, rgb, bold, italic))
    # A run in the basic style is not a style: it is the listing.
    return [r for r in runs if r.rgb is not None or r.bold or r.italic]


# ----------------------------------------------------------- the gutter
def _gutter(glyphs, size: float):
    """(number glyphs, code glyphs) for a line that shows a line number.

    `lstlisting` sets the number in `numberstyle`, which is a SMALLER size
    than the code and a different face, and puts it in its own column to the
    left of every code glyph. Both must hold: a comment set in \\tiny is not
    a line number, and neither is a small superscript inside the code.
    """
    lead = []
    for g in glyphs:
        if g.text.strip().isdigit() and g.size < 0.85 * size:
            lead.append(g)
        else:
            break
    if not lead:
        return [], list(glyphs)
    rest = glyphs[len(lead):]
    if not rest:
        return [], list(glyphs)
    return lead, rest


def _split_gutter(lead, code, size: float):
    """(before, number, after) -- the gutter holds MORE than this line.

    A blank code line puts nothing on the page but its number, in the same
    column as every other number, so `_group_lines` folds it into the
    neighbouring row. lst-021 came back with `12`, `89` and `1134` where the
    page shows 1, 8 and 11: two numbers of adjacent lines read as one number
    of two digits, and the blank lines between them gone.

    The baselines separate them, and nothing else does -- x cannot, because
    that is exactly what they share:

        '1' x=48.3 base=725.34      the number of THIS line
        '2' x=48.3 base=718.72      a blank line below it
        '/' x=56.7 base=725.34      the code

    A digit on the code's own baseline is this line's number; one below it
    belongs to a blank line that follows, one above to a blank line before.
    """
    if not lead:
        return [], None, []
    base = statistics.median([g.baseline for g in code])
    tol = 0.5 * size
    bands: dict = {}
    for g in lead:
        key = round((g.baseline - base) / max(tol, 0.1))
        bands.setdefault(key, []).append(g)
    own = _number(bands.pop(0, []))
    before = [_number(bands[k]) for k in sorted(bands) if k > 0]
    after = [_number(bands[k]) for k in sorted(bands, reverse=True) if k < 0]
    return ([x for x in before if x is not None], own,
            [x for x in after if x is not None])


def _gutter_column(rows, cell: float):
    r"""The x at which the CODE starts, when a line-number column exists.

    781l — A GUTTER THE SIZE TEST CANNOT SEE.

    `_gutter` recognises the line-number column by its type size, because
    `numberstyle` is `\tiny` by convention. An author who sets
    `numbers=left` and leaves `numberstyle` alone gets numbers at the
    CODE'S OWN SIZE, and the size test is blind to them. 2310.02304v3 does
    exactly that, and its listings came back with the number inside the
    code --

        '1  import concurrent.futures'

    -- which put every line one space further right than it is. Measured
    over the gold set, that single cause accounted for 719 of the 1166
    wrong indents: 4 read as 5, 8 as 9, 0 as 1.

    What the size cannot say, the COLUMN can. A gutter is a leading run of
    digits at one x on every row, whose numbers increase, followed by the
    code at one x on every row. Nothing else on a page does all three.
    Returns that code x, or None.
    """
    left, right, code, nums = [], [], [], []
    for _ln, gs in rows:
        gs = [g for g in gs if g.text.strip()]
        i = 0
        while i < len(gs) and gs[i].text.isdigit():
            i += 1
        if not i or i >= len(gs):
            continue
        left.append(gs[0].rect[0])
        right.append(gs[i - 1].rect[2])
        code.append(gs[i].rect[0])
        nums.append(int("".join(g.text for g in gs[:i])))
    if len(nums) < max(3, 0.7 * len(rows)):
        return None
    if any(b <= a for a, b in zip(nums, nums[1:])):
        return None
    tol = 0.5 * cell
    # NEITHER EDGE IS CONSTANT IN GENERAL. `numbers=left` RIGHT-aligns the
    # column, so the gutter's left edge moves with the number's width
    # (` 6`, ` 9`, `10`); and the CODE's left edge moves with the
    # indentation, which is the whole thing being measured. What holds is
    # that one side of the digit run is flush: right-aligned numbers end
    # at one x, left-aligned ones begin at one x. Requiring the wrong one
    # refused every listing past line nine.
    flush = (max(right) - min(right) <= tol) or (max(left) - min(left) <= tol)
    if not flush:
        return None
    # And the code is SEPARATED from it -- a number that is simply the
    # first token of the line is not a gutter.
    if min(code) - max(right) < 0.5 * cell:
        return None
    return max(right) + 0.5 * cell


def _number(lead) -> int | None:
    t = "".join(g.text for g in lead).strip()
    return int(t) if t.isdigit() else None


# ------------------------------------------------------------- the frame
#: A frame rule is thin. `_is_plain_rule` has already said so; this is the
#: side it is thin on.
def _horizontal(r) -> bool:
    return (r.rect[3] - r.rect[1]) <= 2.0 and (r.rect[2] - r.rect[0]) > 20.0


def _vertical(r) -> bool:
    return (r.rect[2] - r.rect[0]) <= 2.0 and (r.rect[3] - r.rect[1]) > 2.0


def _columns(vert) -> list:
    """(x, y_bottom, y_top) for each stack of vertical segments.

    `frame=single` does NOT draw one tall rule down each side. listings sets
    the frame line by line, so a twelve-line listing has twelve segments per
    side, each one line high and abutting the next:

        lst-027   x=52.91   714.39..725.34
                  x=52.91   703.43..714.39
                  x=52.91   692.47..703.43

    Read segment by segment, no side of the frame is ever as tall as the
    box; stacked, they are.
    """
    by_x: dict = {}
    for r in vert:
        by_x.setdefault(round(r.rect[0], 0), []).append(r)
    out = []
    for seg in by_x.values():
        seg.sort(key=lambda r: r.rect[1])
        # The KEY is rounded so segments a hundredth apart stack; the x that
        # comes back is the one actually drawn.
        x = min(r.rect[0] for r in seg)
        lo, hi = seg[0].rect[1], seg[0].rect[3]
        for r in seg[1:]:
            if r.rect[1] <= hi + 1.0:
                hi = max(hi, r.rect[3])
            else:
                out.append((x, lo, hi))
                lo, hi = r.rect[1], r.rect[3]
        out.append((x, lo, hi))
    return out


def frames(rules, span_pt: float = 10.0) -> list:
    r"""Rectangles drawn on the page that could enclose a listing.

    The frame is the one boundary that does not depend on the font, and it
    is the only thing that separates a listing from what surrounds it: the
    glyph extent cannot. lst-027 --

        frame     52.91 688.48 559.09 729.33
        glyphs    48.32 688.28 566.86 739.09

    -- is wider on the left because `numbers=left` sets the gutter OUTSIDE
    the frame, wider on the right because of an escaped `\label`, and taller
    because the caption sits above the box. A reader that takes the glyph
    extent for the listing takes the caption with it.

    A pair of horizontal rules of the same width, far enough apart, is the
    candidate; vertical stacks at either end extend it sideways where the
    author asked for a full box. `frame=tb` draws only the pair, which is
    why the verticals are optional.
    """
    horiz = sorted((r for r in rules if _horizontal(r)), key=lambda r: -r.rect[1])
    cols = _columns([r for r in rules if _vertical(r)])
    out: list = []
    for i, a in enumerate(horiz):
        for b in horiz[i + 1:]:
            if (abs(a.rect[0] - b.rect[0]) > 2.0
                    or abs(a.rect[2] - b.rect[2]) > 2.0):
                continue
            lo, hi = b.rect[1], a.rect[3]
            if hi - lo < 1.5 * span_pt:
                continue
            x0, x1 = a.rect[0], a.rect[2]
            # A side counts when its stack covers the box to within one line:
            # `framesep` leaves a gap of about 4pt at each end.
            for cx, cy0, cy1 in cols:
                if cy0 > lo + span_pt or cy1 < hi - span_pt:
                    continue
                if abs(cx - x0) < 2.0 * span_pt:
                    x0 = min(x0, cx)
                elif abs(cx - x1) < 2.0 * span_pt:
                    x1 = max(x1, cx)
            out.append((x0, lo, x1, hi))
            break         # the NEXT rule down closes this box, not a later one
    return out


# --------------------------------------------------------------- the pass
def _continues(ln) -> bool:
    """A short typewriter line inside an open block is still code.

    `LineNode.verbatim` needs three alphanumerics before it will call a line
    monospace, because two letters are not evidence of a face. That is the
    right rule for opening a block and the wrong one for continuing it: a
    listing whose third line is `}` or `*` or `%` would be cut in half by
    it. lst-001 and lst-002 are two content lines with exactly such a line
    between them, and produced no block at all.
    """
    gs = sorted((g for g in ln.glyphs if g.text.strip()),
                key=lambda g: g.rect[0])
    if not gs:
        return False
    # THE GUTTER IS NEVER MONOSPACE. `numberstyle` is `\tiny` in the
    # document's own text font, so a line whose only code is `}` or `BT`
    # arrived as one roman digit plus one typewriter glyph and failed the
    # all-monospace test -- which ended the block. e-stream came back as
    # four blocks of a 28-line listing and e-htmljs lost every line that
    # was a lone brace. The leading small digits are the gutter, and the
    # same test `_gutter` uses drops them.
    # NOTHING BUT DIGITS is a blank code line, and the size test cannot
    # say so: with no code on the row it compares the digits against
    # THEMSELVES -- `4.5 < 0.85 * 4.5` -- and never strips. Decided here,
    # before the loop that needs a code glyph to measure against.
    if all(g.text.isdigit() for g in gs):
        return True
    size = statistics.median([g.size for g in gs])
    while gs and gs[0].text.isdigit() and gs[0].size < 0.85 * max(
            (g.size for g in gs if not g.text.isdigit()), default=size):
        gs = gs[1:]
    if not gs:
        # NOTHING BUT A NUMBER IS A BLANK CODE LINE, and a blank line does
        # not end a listing. Two consecutive blanks did: the first is
        # absorbed as the previous row's `blank_after`, the second had
        # only its gutter digit left and was refused, so g-github's
        # 16-line listing came back as two blocks with line 16 missing
        # entirely. This runs only with a block already open, so it can
        # never START one from a stray page number.
        return True
    return all(texmap.is_monospace(g.fontname) for g in gs)


def _columns_of(run, spans) -> list:
    """Split a run of lines into COLUMNS, by horizontal overlap.

    781g — A BLOCK THAT CROSSED THE GUTTER MEASURED ITS INDENT FROM THE
    OTHER COLUMN. Page 5 of 1804.10694v5 sets four listings in two columns;
    read in band order, a verbatim run picks up lines from both, and `left`
    -- the x of column 0 -- then comes from whichever column starts further
    left. Every right-column line came back indented by 56 spaces.

    Indentation can never be mistaken for a column here, because the test
    is not x0 but OVERLAP: inside one column the lines overlap, since a
    long line spans the indent of every other. Between columns nothing
    overlaps at all -- the left column ends before the right begins. So the
    split is the classic interval partition, and it is exact:

        listing 3   x0 314.0 316.5 395.7          one column
        listing 2   x0  60.5  70.7  73.2 314.0 ... two

    A part of one line is not a column; those lines stay with the block
    they came from rather than becoming a listing of their own.
    """
    order = sorted(range(len(run)), key=lambda i: spans[i][0])
    parts, cur, edge = [], [order[0]], spans[order[0]][1]
    for i in order[1:]:
        if spans[i][0] > edge:
            parts.append(cur)
            cur, edge = [i], spans[i][1]
        else:
            cur.append(i)
            edge = max(edge, spans[i][1])
    parts.append(cur)
    if len(parts) < 2 or any(len(x) < 2 for x in parts):
        return [run]
    # Reading order inside each column is the order they arrived in.
    return [[run[i] for i in sorted(part)] for part in parts]


def _join_across_lines(lines) -> None:
    r"""A literal that opens on one line and closes on another is one.

    781i — AND ONCE MORE, ACROSS THE LINE BREAK.

    A triple-quoted Python string, or any string long enough to wrap, is
    styled continuously from its opening quote to its closing one. Within
    a line `_join_strings` finds it by the quotes; across lines there is
    no closing quote to find, so lst-121 still filed `You`, `must`,
    `return`, `an`, `improved` as keywords -- 38 of them out of one
    prompt.

    What the page shows is a style that RUNS OFF THE END of one line and
    RESUMES AT COLUMN 0 of the next, in exactly the same style. No
    keyword does that: a keyword ends where the word ends. So a chain of
    such rows whose head opens with a quote is one literal, and every run
    in it is that literal, not a word.
    """
    for a, b in zip(lines, lines[1:]):
        if not a.colors or not b.colors:
            continue
        la, fb = a.colors[-1], b.colors[0]
        if (la.rgb, la.bold, la.italic) != (fb.rgb, fb.bold, fb.italic):
            continue
        if la.end < len(a.text.rstrip()) or fb.start > 0:
            continue
        if la.kind == "string" or fb.kind == "string":
            la.kind = fb.kind = "string"
            continue
        head = a.text[la.start:la.end].lstrip()
        if head[:1] in _QUOTE or la.kind == "comment":
            la.kind = fb.kind = la.kind if la.kind == "comment" else "string"


def _blocks(page) -> list:
    """Maximal runs of verbatim lines, in reading order."""
    out: list = []
    run: list = []
    for ln in page.lines:
        if ln.rotated:
            keep = False
        elif ln.verbatim:
            keep = True
        else:
            keep = bool(run) and _continues(ln)
        if keep:
            run.append(ln)
        else:
            if len(run) >= 2:
                out.append(run)
            run = []
    if len(run) >= 2:
        out.append(run)
    # A trailing continuation line is not evidence of anything on its own.
    out = [r if r[-1].verbatim else r[:-1] for r in out
           if len(r) >= 2 and (r[-1].verbatim or len(r) > 2)]
    split: list = []
    for r in out:
        spans = [(min(g.rect[0] for g in ln.glyphs),
                  max(g.rect[2] for g in ln.glyphs)) for ln in r]
        split += [c for c in _columns_of(r, spans) if len(c) >= 2]
    return split


def _fill_under(page, rect):
    """The page's own background colour behind a block, if it has one."""
    best = None
    for f in getattr(page, "fills", []):
        r = f.rect
        if (r[0] <= rect[0] + 2 and r[2] >= rect[2] - 2
                and r[1] <= rect[1] + 2 and r[3] >= rect[3] - 2):
            if f.color is not None and min(f.color) < 0.995:
                best = f.color
    return best


def _row_pitch(run) -> float:
    """The distance between two rows of this block, measured."""
    base = sorted({round(statistics.median([g.baseline for g in ln.glyphs]), 2)
                   for ln in run if ln.glyphs}, reverse=True)
    gaps = [a - b for a, b in zip(base, base[1:]) if a - b > 0.5]
    return statistics.median(gaps) if gaps else 0.0


def _merge_rows(run) -> list:
    """[(line, glyphs)] with lines that share a ROW merged into one.

    781g — A GLYPH SET 1.4pt LOW IS NOT A LINE OF ITS OWN.

    `listings` does not set every character on the row's baseline. In
    1804.10694v5 the multiplication star of `i0*32+i1` is placed 1.39pt
    below the code it belongs to, and line grouping -- which has no idea
    it is looking at a grid -- made it a line:

        base 676.88   'int i = i0 32+i1'
        base 675.49   '*'

    so the listing came back with the star on its own row and a hole where
    it should be, four times on one page. Against the author's own source
    that was 4 of 22 lines wrong, and it was the ONLY thing wrong.

    A block knows its row pitch -- here 7.17pt -- and 1.39 is a fifth of
    it. Nothing closer than half a pitch can be a separate row.
    """
    pitch = _row_pitch(run)
    if pitch <= 0:
        return [(ln, list(ln.glyphs)) for ln in run]
    rows: list = []
    for ln in run:
        if not ln.glyphs:
            continue
        base = statistics.median([g.baseline for g in ln.glyphs])
        x0 = min(g.rect[0] for g in ln.glyphs)
        x1 = max(g.rect[2] for g in ln.glyphs)
        for row in rows:
            # A SHARED BASELINE IS NOT ENOUGH. Two cells of one table row
            # share a baseline exactly, so merging on baseline alone put
            # the neighbouring cell back into this listing and undid the
            # column split -- page 5 of 1804.10694v5, block 5. What this
            # pass is for sits INSIDE the row it belongs to (the `*` of
            # `i0*32+i1`, x 395.7..400.5 inside 316.5..424.4); a cell
            # beside it lies wholly outside. So containment, not proximity.
            if (abs(row[2] - base) < 0.5 * pitch
                    and x0 >= row[3] - 0.5 and x1 <= row[4] + 0.5):
                row[1].extend(ln.glyphs)
                break
        else:
            rows.append([ln, list(ln.glyphs), base, x0, x1])
    return [(r[0], sorted(r[1], key=lambda g: g.rect[0])) for r in rows]


def _cell_boundaries(run) -> list:
    """x values where the PRODUCER stopped one cell and started another.

    781j — A LINE THAT IS TWO CELLS.

    Line grouping sees one baseline and makes one line, so two listings
    side by side in a `tabular` row arrive as a single line and no
    geometric test can separate them: every line spans the gap, so the
    overlap partition collapses to one column.

    TeX emits a table CELL AT A TIME. So inside such a line the content
    stream jumps where the cells meet, and it jumps at the SAME x on
    every row of the table:

        e-tables, a 2x2 table of listings
            '1 for (i in 0..N)   1 GPUBlock for...'   jump 51 at x=420.6
            '2 for (j in 0..M)   2 GPUThread for...'  jump 74 at x=420.6
            '3 b1[j] = a*f1[i,j] 3 int i = i0*32+i1'  jump 98 at x=420.6

    The jump SIZE is not the signal -- page 5 of 1804.10694v5 jumps 600+
    at a cell and 21-47 at a blank line's gutter number, while this page
    jumps 36-98 at a cell. The agreement of x across rows is.
    """
    votes: collections.Counter = collections.Counter()
    for ln in run:
        gs = sorted([g for g in ln.glyphs if g.stream >= 0],
                    key=lambda g: g.rect[0])
        if len(gs) < 4:
            continue
        jumps = [(b.stream - a.stream, b.rect[0]) for a, b in zip(gs, gs[1:])
                 if b.stream - a.stream > 1]
        if jumps:
            votes[round(max(jumps)[1])] += 1
    return [x for x, n in votes.most_common() if n >= 2]


def _cell_split(page) -> None:
    """Rewrite `page.lines`, splitting the lines the producer says are two.

    Self-validating: a split is kept only if it leaves two groups of at
    least two lines each whose x-ranges do not overlap -- the same test
    `_columns_of` uses for columns, applied to the result. A candidate
    that does not produce two clean columns was not a cell boundary, and
    nothing is changed.

    781j — AND IT REFUSES PAGE 5 OF 1804.10694v5, WHICH IS CORRECT.

    Three lines there are two cells merged, and the split is not taken.
    Every way of making it acceptable also makes a WRONG boundary on the
    same page acceptable:

                          split lines   edge spread      gap
        e-tables  x=421       4          0.00 cells   +51.06 cells
        page 5    x=314 TRUE  3          0.00 cells    -0.21 cells
        page 5    x=317 false 20         0.00 cells    -0.69 cells
        page 5    x=400 false 19         5.00 cells    -0.00 cells

    The true boundary has a NEGATIVE gap -- the left cell's last glyph, a
    `)`, ends at 315.01 and the right cell begins at 314.0, so the cells
    physically abut. Nor is that a bearing: measured over this run and 22
    gold listings the ink box equals the advance exactly (width/cell =
    1.00). There is no corridor to find.

    Tried and reverted: a cell of slack on the disjointness test (let in
    x=317, which cuts the right column's own text -- 5 blocks became 9
    and `Parallel for(i0` was truncated mid-token); scoring candidates by
    smallest overshoot (let in x=400, inside two runs that are one
    listing each); counting glyphs that cross (1 glyph, 0.17%, for the
    true AND the false candidate); requiring the right pieces to share a
    left edge (0.00 cells for the true boundary and for two false ones).

    A split that is right on one page and wrong on the same page is not a
    rule. What would settle it is the tabular's own column boundary,
    which reaches the PDF only if the author drew a rule there -- and on
    this page they did not. The cost is 3 lines of one block; the other
    four listings on that page are read exactly.
    """
    from docmodel_six import LineNode

    for run in _blocks(page):
        for x in _cell_boundaries(run):
            pieces = []
            for ln in run:
                gs = sorted(ln.glyphs, key=lambda g: g.rect[0])
                cut = next((i for i, g in enumerate(gs)
                            if g.rect[0] >= x - 0.5), len(gs))
                a, b = gs[:cut], gs[cut:]
                # THE RIGHT CELL'S GUTTER SITS LEFT OF ITS CODE, so a cut
                # placed at the first code glyph leaves the number behind
                # on the left -- e-tables came back with every row of the
                # left cell ending in the right cell's line number. A
                # glyph separated from its own piece by a wide gap and
                # sitting next to the other one belongs to the other one.
                wide = 3.0 * statistics.median(
                    [g.rect[2] - g.rect[0] for g in gs if g.text.strip()]
                    or [1.0])
                while len(a) >= 2 and a[-1].rect[0] - a[-2].rect[2] > wide:
                    b.insert(0, a.pop())
                pieces.append((ln, a, b))
            left = [a for _l, a, _b in pieces if a]
            right = [b for _l, _a, b in pieces if b]
            if len(left) < 2 or len(right) < 2:
                continue
            # SELF-VALIDATING. The same overlap test `_columns_of` uses,
            # applied to the RESULT: a candidate that does not leave two
            # clean columns was not a cell boundary, and nothing changes.
            if (max(g.rect[2] for gs in left for g in gs)
                    > min(g.rect[0] for gs in right for g in gs)):
                continue
            # A CELL IS CODE ON BOTH SIDES. The gutter is x-disjoint from
            # the code by construction, so geometry alone let a split cut
            # the LINE NUMBERS off as if they were a cell -- lst-021 came
            # back with `10` as a `1` on one row and a `0` on the next,
            # and 3 documents stopped being fixed points. `numberstyle` is
            # set in the document's text font, so "both pieces contain a
            # monospace glyph" is the test the gutter cannot pass.
            if not all(any(texmap.is_monospace(g.fontname) for g in gs)
                       for gs in (left[0], right[0])):
                continue
            out: list = []
            for ln in page.lines:
                hit = next((p for p in pieces if p[0] is ln), None)
                if hit is None or not hit[1] or not hit[2]:
                    out.append(ln)
                    continue
                _l, a, b = hit
                for suffix, gs in (("", a), ("c", b)):
                    r = (min(g.rect[0] for g in gs), min(g.rect[1] for g in gs),
                         max(g.rect[2] for g in gs), max(g.rect[3] for g in gs))
                    out.append(LineNode(id=ln.id + suffix, page=ln.page,
                                        rect=r, type=ln.type, glyphs=gs,
                                        rules=list(ln.rules), merged=ln.merged,
                                        rotated=ln.rotated))
            page.lines = out
            break


#: A glyph pdfminer could not map arrives as the literal `(cid:123)`. A
#: block mostly made of those is not a listing whose text we read badly --
#: it is a FONT WE CANNOT READ, and every property derived from it is
#: derived from nothing.
_CID = re.compile(r"\(cid:\d+\)")

#: Above this share of placeholder characters the block is refused.
#: Measured on the Wolfram-Language book, whose code cells come back as
#: `(cid:7)(cid:8)(cid:9)...(cid:9)l(cid:20)(cid:13)i(cid:2)(cid:17)s`:
#: the four letters that resolved were filed as four single-letter
#: keywords, and each fragment got a full descriptive header, so 26% of
#: that document's markdown was a comment about text nobody can read.
CID_REFUSE = 0.30


def _unreadable(text: str) -> bool:
    """True when the block is mostly glyphs no encoding could resolve."""
    if not text:
        return False
    placeholder = sum(len(m.group(0)) for m in _CID.finditer(text))
    return placeholder > CID_REFUSE * len(text)


def accumulate(page) -> list:
    """Every listing on the page, with the properties that would set it."""
    _cell_split(page)
    out: list = []
    boxes: list = []
    where = {ln.id: i for i, ln in enumerate(page.lines)}
    for run in _blocks(page):
        glyphs = [g for ln in run for g in ln.glyphs]
        mono = _mono(glyphs)
        if len(mono) < 8:
            continue
        size = statistics.median([g.size for g in mono])
        cell = cell_width([g for ln in run
                           for g in sorted(ln.glyphs, key=lambda g: g.rect[0])
                           if texmap.is_monospace(g.fontname)])
        if cell is None:
            continue
        rows: list = []
        numbered = 0
        _merged = _merge_rows(run)
        _code_x = _gutter_column(_merged, cell)
        for ln, gs in _merged:
            # A ROW THAT IS ONLY ITS NUMBER IS A BLANK CODE LINE, and its
            # glyphs are the GUTTER, not code. Treating them as code made
            # the blank line's number the row's text (`|16|`) and, worse,
            # dragged `left` out to the gutter column -- every indent in
            # g-github gained seven cells from one blank line.
            if all(g.text.isdigit() for g in gs if g.text.strip()):
                rows.append((ln, list(gs), []))
                numbered += 1
                continue
            if _code_x is not None:
                lead = [g for g in gs if g.rect[0] < _code_x - 0.5]
                code = [g for g in gs if g.rect[0] >= _code_x - 0.5]
                if not code:
                    lead, code = [], list(gs)
            else:
                lead, code = _gutter(gs, size)
            if lead:
                numbered += 1
            while code and not code[0].text.strip():
                code = code[1:]     # a leading space glyph IS the indent
            while code and not code[-1].text.strip():
                code = code[:-1]
            if not code:
                continue
            rows.append((ln, lead, code))
        if not rows:
            continue
        _coded = [c for _ln, _lead, c in rows if c]
        if not _coded:
            continue
        left = min(c[0].rect[0] for c in _coded)
        lst = Listing(cell=cell, left=left, size=size,
                      font=statistics.mode([g.fontname for g in mono]),
                      numbers=numbered >= 0.8 * len(rows))
        for ln, lead, code in rows:
            if not code:                      # a numbered blank line
                before, own, after = _split_gutter(lead, lead, size)
                lst.lines.append(ListingLine(
                    id=ln.id, indent=0, text="", number=own,
                    blank_before=before, blank_after=after))
                lst.ids.add(ln.id)
                continue
            text = grid_text(code, cell)
            indent = int(round((code[0].rect[0] - left) / cell))
            before, own, after = _split_gutter(lead, code, size)
            lst.lines.append(ListingLine(
                id=ln.id, indent=max(0, indent), text=text.rstrip(),
                number=own, blank_before=before, blank_after=after,
                colors=_color_runs(code, cell)))
            _row = lst.lines[-1]
            # UNINDENTED: `_color_runs` counts from the first code glyph, so
            # a run's offsets index `text`, not the indented row. Handing
            # `_classify` the indented string shifted every slice by the
            # indent and filed `[`, `{` and `}` as keywords -- which reached
            # `morekeywords={[1]{[,{,}}}` and made the .tex uncompilable.
            _row.colors = _classify(_row.text, _row.colors)
            lst.ids.add(ln.id)
        lst.ids |= {ln.id for ln in run}
        # A literal is only recognisable once its neighbours exist.
        for _ in range(3):
            _join_across_lines(lst.lines)
        nums = [n for x in lst.lines
                for n in (x.blank_before + [x.number] + x.blank_after)
                if n is not None]
        if lst.numbers and nums:
            lst.firstnumber = nums[0]
            steps = [b - a for a, b in zip(nums, nums[1:]) if b > a]
            lst.stepnumber = min(steps) if steps else 1
        rect = (min(g.rect[0] for g in glyphs), min(g.rect[1] for g in glyphs),
                max(g.rect[2] for g in glyphs), max(g.rect[3] for g in glyphs))
        if _unreadable(lst.text()):
            # Refused, not repaired: a reader that cannot name the glyphs
            # cannot name the language, the keywords or the indent either.
            continue
        lst.background = _fill_under(page, rect)
        seen = [where[ln.id] for ln in run if ln.id in where]
        lst.page = getattr(page, "page", 0)
        lst.index = len(out) + 1
        lst.line_start = min(seen) if seen else -1
        lst.line_end = max(seen) if seen else -1
        lst.rect = rect
        lst.language, lst.language_source = _language(lst)
        boxes.append(rect)
        out.append(lst)
    # The frames are assigned once every block is known: a frame is a
    # listing's only when it is around that listing ALONE.
    for i, lst in enumerate(out):
        drawn = _encloses(getattr(page, "frames", ()), boxes[i],
                          [b for j, b in enumerate(boxes) if j != i])
        if drawn:
            lst.rect, lst.framed = drawn, True
    return out


#: The conventional file extension for each language `listings` names, for
#: a listing that is written out as a file. Only the ones whose extension
#: is not in dispute; anything else gets `.txt`, which says "this is text
#: we read" rather than making a claim about what it is.
SUFFIX = {
    "c": ".c", "c++": ".cpp", "cpp": ".cpp", "java": ".java",
    "python": ".py", "ruby": ".rb", "perl": ".pl", "php": ".php",
    "html": ".html", "xml": ".xml", "css": ".css", "json": ".json",
    "sql": ".sql", "bash": ".sh", "sh": ".sh", "csh": ".csh",
    "awk": ".awk", "make": ".mk", "lua": ".lua", "r": ".R",
    "go": ".go", "rust": ".rs", "scala": ".scala", "swift": ".swift",
    "haskell": ".hs", "erlang": ".erl", "lisp": ".lisp", "ml": ".ml",
    "caml": ".ml", "prolog": ".pl", "ada": ".adb", "fortran": ".f90",
    "pascal": ".pas", "delphi": ".pas", "matlab": ".m", "octave": ".m",
    "tex": ".tex", "verilog": ".v", "vhdl": ".vhd", "assembler": ".asm",
    "basic": ".bas", "cobol": ".cob", "eiffel": ".e", "julia": ".jl",
    "vbscript": ".vbs", "postscript": ".ps", "gnuplot": ".gp",
    "mathematica": ".m", "maple": ".mpl", "elisp": ".el",
}

_SLUG = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(name: str) -> str:
    """A document id safe to put in a filename, and recognisable after."""
    return _SLUG.sub("-", name.strip()).strip("-.") or "doc"


#: The coverage below which the words seen do not name a language. A
#: listing that colours `for` and `float` is covered 100% by Modula-2,
#: Java and C alike; saying one of them would be inventing evidence.
_LANG_COVER = 0.75


def _language(lst) -> tuple:
    """(language, source) from the words the page STYLED, or ("", "").

    781e — ASK THE PACKAGE THAT PAINTED THE PAGE.

    `keywordstyle` colours a word if and only if that word is in the
    keyword list of the language the author named, so the coloured words
    are a SUBSET of one language's keywords and the language can be looked
    up rather than guessed. `listings` ships 94 of those lists; `lstlangs`
    reads them out, the same move `texmap` makes with `mathabx.dcl`.

    Each style group is tried alone -- a page has a keyword colour, a
    comment colour and a string colour, and only one of them is keywords.
    Two languages that fit equally well is an abstention: measured over the
    112 gold listings whose declared language `listings` also defines, this
    answered 34 and was right 34 times, abstaining on the rest. A reader
    that is silent when the page is silent is worth more than one that
    guesses.
    """
    table = lstlangs.load()
    groups: dict = {}
    for word, rgb, bold, italic in lst.keywords:
        groups.setdefault((rgb, bold, italic), set()).add(word)
    best, cover = "", 0.0
    for words in groups.values():
        if len(words) < 2:
            continue
        r = lstlangs.rank(words, table, top=2)
        if not r or (len(r) > 1 and abs(r[1][1] - r[0][1]) < 1e-9):
            continue
        if r[0][1] > cover:
            best, cover = r[0][0], r[0][1]
    return (best, "keywords") if cover >= _LANG_COVER else ("", "")


def _inside(frame, rect) -> bool:
    return (frame[0] <= rect[0] + 2 and frame[2] >= rect[2] - 2
            and frame[1] <= rect[1] + 2 and frame[3] >= rect[3] - 2)


def _encloses(frames, rect, others) -> tuple | None:
    """The smallest drawn frame around `rect` ALONE, or None.

    781g — A BOX AROUND TWO LISTINGS IS NOT EITHER LISTING'S FRAME.

    Page 5 of 1804.10694v5 draws three page-wide rules that band the
    figures, and each band holds two listings side by side. Taking the
    smallest enclosing rectangle gave BOTH of them the same rect and
    called both framed -- which is exactly the over-claim the frame was
    introduced to avoid, since the whole point of a drawn boundary is that
    it says which glyphs belong to WHICH block.

    So a frame is this listing's only when it contains this listing and no
    other. Smallest still wins among those, because a listing in a table
    cell sits inside two rectangles and the inner one is its own.
    """
    fit = [f for f in frames
           if _inside(f, rect) and not any(_inside(f, o) for o in others)]
    if not fit:
        return None
    return min(fit, key=lambda f: (f[2] - f[0]) * (f[3] - f[1]))


#: Characters a `\ttfamily` listing shows when the source had ASCII and
#: the setup did not ask for `upquote`. Seeing them is evidence about the
#: SETUP, not about the code: the author typed ` and ', and the font gave
#: back ‘ and ’.
_CURLY = {"‘": "`", "’": "'", "“": '"', "”": '"'}


def hints(lst) -> list:
    """What the page shows that a consumer of the CODE has to know.

    781i — THE DIFFERENCE BETWEEN WHAT WAS TYPED AND WHAT WAS PRINTED.

    e-self.py lists its own source, and every character that could break
    LaTeX came back exactly: 29 backslashes, 25 braces, the `%`, the `$`,
    the `#`. Seven lines still differed, and not one of them was ours --
    the listing did not set `upquote`, so every ` and ' the author typed
    was printed as ‘ and ’, and the em dash is not in the T1 font at all.
    A consumer handing this text to a compiler needs to be told that, and
    nothing else on the page says it.
    """
    out: list = []
    code = lst.code
    curly = sorted({c for c in code if c in _CURLY})
    if curly:
        out.append("upquote=true is missing: %s printed where the source had %s"
                   % (" ".join(curly), " ".join(_CURLY[c] for c in curly)))
    high = sorted({c for c in code if ord(c) > 127 and c not in _CURLY})
    if high:
        out.append("non-ASCII in the code, needs `literate=` or a unicode "
                   "engine: " + " ".join("U+%04X %s" % (ord(c), c)
                                         for c in high[:12]))
    if lst.indent_unit and lst.indent_unit > 1:
        out.append("indentation is in steps of %d -- if this language is "
                   "whitespace-significant, it is CONTENT" % lst.indent_unit)
    if any(("\t" in ln.text) for ln in lst.lines):
        out.append("a literal tab survived into the text, which a page "
                   "cannot show -- treat as suspect")
    return out


def _num(v: float) -> str:
    return ("%.4f" % v).rstrip("0").rstrip(".") or "0"


def describe(lst, doc_id: str = "", width: int = 76) -> list:
    """Wrapper: a DESCRIPTION must never be able to cost a document."""
    try:
        return _describe(lst, doc_id)
    except Exception as exc:                                # noqa: BLE001
        return ["listing %s" % getattr(lst, "stem", "?"),
                "  description unavailable: %s" % str(exc)[:120]]


def _describe(lst, doc_id: str = "") -> list:
    r"""Everything measured about one listing, as plain lines.

    781i — ONE PLACE, NOT SIX.

    The properties were spread over the object, the projection and two
    measurement scripts, so anyone reading a `.md` or a `.tex` had the
    code and none of what was read to get it: not the cell, not the
    indent policy, not which words were coloured and in what, not the
    rectangle, not where on the page it was. This is that, in one block,
    put at the head of every listing in every projection.

    Plain lines, no comment marker: the caller knows whether it is
    writing `%` or `<!--`, and a block that already carries one cannot be
    reused by the other.
    """
    def row(k, v):
        out.append("  %-16s %s" % (k, v))

    out: list = []
    out.append("listing %s" % lst.stem)
    row("where", "page %d, block %d, lines %d..%d of the page"
        % (lst.page, lst.index, lst.line_start, lst.line_end))
    if lst.rect:
        row("rectangle", "%s   %s" % (" ".join("%.1f" % v for v in lst.rect),
                                      "a frame the author DREW"
                                      if lst.framed else "the glyph extent"))
    row("rows", "%d, blanks included" % lst.line_count)
    row("grid", "cell %.2fpt, column 0 at x=%.2f, type %.1fpt"
        % (lst.cell, lst.left, lst.size))
    row("face", lst.font or "(unnamed)")
    if lst.numbers:
        row("line numbers", "left, from %d step %d"
            % (lst.firstnumber, lst.stepnumber))
    else:
        row("line numbers", "none on the page")
    row("indents seen", " ".join(str(n) for n in lst.indents) or "0")
    row("indent step", ("%d cells" % lst.indent_unit) if lst.indent_unit
        else "none -- one level, or no common divisor")
    row("tabsize", ("%d" % lst.tabsize) if lst.tabsize
        else "not established: the page shows spaces, a tab left no mark")
    row("language", ("%s, from %s" % (lst.language, lst.language_source))
        if lst.language else
        "not established -- no keyword colour, or the words fit more than one")
    if lst.background:
        row("background", "rgb %s" % ",".join(_num(v) for v in lst.background))
    kw = lst.keywords
    row("styled words", "%d" % len(kw))
    for word, rgb, bold, italic in kw[:40]:
        face = " ".join(x for x in ("bold" if bold else "",
                                    "italic" if italic else "") if x)
        out.append("      %-22s %s%s"
                   % (word, ("rgb " + ",".join(_num(v) for v in rgb))
                      if rgb else "(basic colour)",
                      (" " + face) if face else ""))
    if len(kw) > 40:
        out.append("      ... and %d more" % (len(kw) - 40))
    for kind in ("comment", "string"):
        st = lst.style_of(kind)
        if st is None:
            continue
        rgb, bold, italic = st
        face = " ".join(x for x in ("bold" if bold else "",
                                    "italic" if italic else "") if x)
        row("%s style" % kind, "%s%s"
            % (("rgb " + ",".join(_num(v) for v in rgb)) if rgb
               else "(basic colour)", (" " + face) if face else ""))
    for h in hints(lst):
        row("hint", h)
    row("as a file", lst.path(doc_id))
    out.append("")
    out.append("  A FIRST GUESS at the setup that would print this again.")
    out.append("  Assembled from what was measured and nothing else, so what")
    out.append("  the page never showed is absent rather than defaulted.")
    out += ["    " + x for x in lst.preamble()]
    out.append(r"    \lstset{")
    opt = lst.lstset()
    for i, (k, v) in enumerate(opt):
        out.append("      %s=%s%s" % (k, v, "," if i + 1 < len(opt) else ""))
    out.append("    }")
    return out


def listing_of(page, line):
    """The listing this line belongs to, or None."""
    for lst in getattr(page, "listings", ()):
        if line.id in lst.ids:
            return lst
    return None
