"""psstream - the content stream's ACTIONS, not their results.

Every reader in this project so far has taken `LTChar`: a glyph with a final
position, after pdfminer has composed the CTM, the text matrix, the font
size and the advance into one rectangle. That is the RESULT. It cannot say
how the position was reached, and two very different actions land in the
same place:

    a superscript of this line, raised by a text-matrix move
    a subscript of the line above, lowered by one

Measured on a real page, those differ by less than the line spacing and the
coordinates cannot separate them. The operator sequence can: the producer
moves the point, shows the base, moves up, shows the script, moves back.
The script is emitted BESIDE ITS BASE whatever the geometry looks like.

This module reads the operators and keeps the structure they carry:

    q / Q        the graphics state STACK -- push and pop, with depth
    cm           CTM concatenation, inside that stack
    BT / ET      a text object; the text matrix is reset by BT
    Tm           set the text matrix outright
    Td / TD / T* relative moves of the text LINE matrix
    Ts           text rise -- a raise with NO matrix change
    Tf           font and size
    TJ / Tj      show, TJ with its per-element kerns
    Tc/Tw/Tz/TL  the spacing parameters that scale an advance

A `Show` records what was shown AND the action that placed it: the move that
preceded it, the stack depth it happened at, the rise in force, and the CTM
scale. That is the topological view -- a large delimiter drawn by pushing a
scaled CTM and popping it again is a different object from an ordinary glyph
at the same size, and only the stack says so.

CONTRACT
    tokenize(data)          -> yields (operands, operator)
    read(data)              -> list[Show]
    Show.move               the ('Td'|'TD'|'Tm'|'T*'|None, operands) before it
    Show.depth              q/Q nesting depth at the time of the show
    Show.rise               Ts in force
    Show.ctm_scale          the CTM's scale factor at that depth
    Show.font, Show.size    from the last Tf
    Show.kerns              TJ adjustments, thousandths of an em

Nothing here computes a page position. Composing the matrices is what a
renderer does, and doing it again would only reproduce the result this
module exists to look behind.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUM = re.compile(rb"[+-]?(?:\d+\.?\d*|\.\d+)")
_NAME = re.compile(rb"/[^\s/\[\]<>(){}%]*")
_OP = re.compile(rb"[A-Za-z'\"*][A-Za-z0-9'\"*]*")


def tokenize(data: bytes):
    """Yield (operands, operator) for a content stream.

    A minimal PDF content-stream reader: numbers, names, strings, hex
    strings, arrays and dictionaries, then the operator that consumes them.
    Inline images (`BI`..`EI`) are skipped whole -- their binary payload is
    not tokenisable and nothing here needs it.
    """
    i, n = 0, len(data)
    operands: list = []
    while i < n:
        c = data[i : i + 1]
        if c in b" \t\r\n\f\x00":
            i += 1
            continue
        if c == b"%":                                  # comment
            j = data.find(b"\n", i)
            i = n if j < 0 else j + 1
            continue
        if c == b"(":                                  # literal string
            j, depth, esc = i + 1, 1, False
            while j < n and depth:
                ch = data[j : j + 1]
                if esc:
                    esc = False
                elif ch == b"\\":
                    esc = True
                elif ch == b"(":
                    depth += 1
                elif ch == b")":
                    depth -= 1
                j += 1
            operands.append(data[i + 1 : j - 1])
            i = j
            continue
        if c == b"<" and data[i : i + 2] != b"<<":      # hex string
            j = data.find(b">", i)
            j = n if j < 0 else j
            operands.append(bytes.fromhex(
                re.sub(rb"[^0-9A-Fa-f]", b"", data[i + 1 : j]).decode()
                .ljust(2 * ((j - i) // 2), "0") or "00"))
            i = j + 1
            continue
        if data[i : i + 2] == b"<<":
            depth, j = 0, i
            while j < n:
                if data[j : j + 2] == b"<<":
                    depth += 1
                    j += 2
                elif data[j : j + 2] == b">>":
                    depth -= 1
                    j += 2
                    if not depth:
                        break
                else:
                    j += 1
            operands.append(("dict", data[i:j]))
            i = j
            continue
        if c == b"[":
            depth, j = 0, i
            while j < n:
                if data[j : j + 1] == b"[":
                    depth += 1
                elif data[j : j + 1] == b"]":
                    depth -= 1
                    if not depth:
                        j += 1
                        break
                j += 1
            operands.append(list(tokenize_array(data[i + 1 : j - 1])))
            i = j
            continue
        m = _NUM.match(data, i)
        if m and (c.isdigit() or c in b"+-."):
            operands.append(float(m.group()))
            i = m.end()
            continue
        m = _NAME.match(data, i)
        if m:
            operands.append(m.group().decode("latin1"))
            i = m.end()
            continue
        m = _OP.match(data, i)
        if m:
            op = m.group().decode("latin1")
            i = m.end()
            if op == "BI":                              # inline image
                j = data.find(b"EI", i)
                i = n if j < 0 else j + 2
                operands = []
                continue
            yield operands, op
            operands = []
            continue
        i += 1


def tokenize_array(data: bytes):
    """The elements of a TJ array: strings and kern numbers, IN ORDER.

    Parsed directly rather than through `tokenize`, which yields only on an
    operator -- an array has none, so the strings were dropped and only the
    kerns survived.
    """
    i, n = 0, len(data)
    while i < n:
        c = data[i : i + 1]
        if c in b" \t\r\n\f\x00":
            i += 1
            continue
        if c == b"(":
            j, depth, esc = i + 1, 1, False
            while j < n and depth:
                ch = data[j : j + 1]
                if esc:
                    esc = False
                elif ch == b"\\":
                    esc = True
                elif ch == b"(":
                    depth += 1
                elif ch == b")":
                    depth -= 1
                j += 1
            yield data[i + 1 : j - 1]
            i = j
            continue
        if c == b"<":
            j = data.find(b">", i)
            j = n if j < 0 else j
            hexs = re.sub(rb"[^0-9A-Fa-f]", b"", data[i + 1 : j])
            if len(hexs) % 2:
                hexs += b"0"
            yield bytes.fromhex(hexs.decode())
            i = j + 1
            continue
        m = _NUM.match(data, i)
        if m:
            yield float(m.group())
            i = m.end()
            continue
        i += 1


@dataclass
class Show:
    """One show operator, with the ACTION that placed it."""
    op: str                                  # Tj, TJ, ', "
    text: bytes
    kerns: list = field(default_factory=list)
    font: str | None = None
    size: float = 0.0
    rise: float = 0.0
    depth: int = 0                           # q/Q nesting
    ctm_scale: float = 1.0
    move: tuple | None = None                # the positioning op before it
    index: int = 0                           # order within the page
    # Which TEXT OBJECT this show sits in. `BT` resets the text matrix to
    # identity, so a `Td` right after one is an ABSOLUTE page position, not
    # a relative move. Without this, accumulating Td drifted a page-1
    # baseline from 701 to 10954: the producer opens a new text object
    # around every fraction rule -- 59 of them on that page.
    text_object: int = 0

    @property
    def raised(self) -> bool:
        """Was this placed by an explicit RAISE rather than a plain advance?"""
        if self.rise:
            return True
        return bool(self.move and self.move[0] in ("Td", "TD", "Tm")
                    and len(self.move[1]) >= 2 and self.move[1][-1] != 0)

    @property
    def scaled(self) -> bool:
        """Was a non-unit CTM pushed for this? A big delimiter usually is."""
        return abs(self.ctm_scale - 1.0) > 1e-6


def read(data: bytes) -> list[Show]:
    """The shows on a page, each with the action that produced it."""
    out: list[Show] = []
    font, size, rise = None, 0.0, 0.0
    depth = 0
    scale_stack: list[float] = [1.0]
    pending: tuple | None = None
    text_object = 0
    idx = 0
    for operands, op in tokenize(data):
        if op == "q":
            depth += 1
            scale_stack.append(scale_stack[-1])
        elif op == "Q":
            depth = max(depth - 1, 0)
            if len(scale_stack) > 1:
                scale_stack.pop()
        elif op == "cm" and len(operands) >= 4:
            a, b, c, d = operands[:4]
            scale_stack[-1] *= ((a * a + b * b) ** 0.5 or 1.0)
        elif op == "BT":
            pending = ("BT", [])
            text_object += 1
        elif op == "Tf" and len(operands) >= 2:
            font, size = str(operands[0]), float(operands[1])
        elif op == "Ts" and operands:
            rise = float(operands[0])
        elif op in ("Td", "TD", "Tm", "T*"):
            pending = (op, [float(x) for x in operands
                            if isinstance(x, (int, float))])
        elif op in ("Tj", "TJ", "'", '"'):
            text, kerns = b"", []
            if op == "TJ" and operands:
                for el in operands[-1] if isinstance(operands[-1], list) else []:
                    if isinstance(el, bytes):
                        text += el
                    elif isinstance(el, (int, float)):
                        kerns.append(float(el))
            else:
                for el in operands:
                    if isinstance(el, bytes):
                        text += el
            out.append(Show(op=op, text=text, kerns=kerns, font=font,
                            size=size, rise=rise, depth=depth,
                            ctm_scale=scale_stack[-1], move=pending,
                            index=idx, text_object=text_object))
            idx += 1
            pending = None
    return out


@dataclass
class ScriptGroup:
    """A run of shows the producer entered SCRIPT STYLE to emit."""
    base: int | None        # index of the show this attaches to
    members: list           # indices of the shows inside the group
    kind: str               # "sup" | "sub" | "level"
    scale: float            # script size / main size
    drop: float             # baseline change, points (negative is down)


def script_groups(shows: list[Show], ratio: float = 0.92) -> list[ScriptGroup]:
    """Script groups, read from the ACTIONS that made them.

    dvips marks a script by setting the text matrix to a SMALLER scale and
    restoring it afterwards -- a push into script style and a pop back:

        /F15 TD [-32.42,-1.89]  'T'      the base
        /F4  Tm a=6.97 f=404.27 'P'      scale drops: the script opens
        /F18 TD [0.89,0]        ',A'     still inside
        /F5  Tm a=9.96 f=405.76 ''       scale restored: the script closes

    The group attaches to the show immediately BEFORE it opened, whatever
    the geometry looks like. That is what the coordinates cannot say: on the
    page this subscript sits 1.49pt below its base, which at this line
    spacing is nearer the line above than to the base it belongs to.

    `ratio` is the scale fraction below which a Tm counts as entering script
    style. TeX's own script size is 0.7 of text size and scriptscript 0.5,
    so anything at or under about 0.9 is a script and 1.0 is not.
    """
    out: list[ScriptGroup] = []
    main: float | None = None
    open_at: int | None = None
    members: list[int] = []
    base: int | None = None
    open_f = 0.0

    def matrix(s: Show):
        """The EFFECTIVE size and baseline of a show.

        Producers split the size between `Tf` and `Tm` differently, and a
        rule that reads one of them alone works on half the corpus:

            dvips       /F14 1 Tf        9.96 0 0 9.96 x y Tm
            Distiller   /F21 13.45 Tf    1    0 0 1    x y Tm

        Keying on the matrix scale alone found 35 script groups on a dvips
        page and ZERO on five Elsevier papers, whose matrix is always the
        identity. The size is the product of the two.
        """
        if s.move and s.move[0] == "Tm" and len(s.move[1]) >= 6:
            m = s.move[1]
            return (m[0] or 1.0) * (s.size or 1.0), m[5]
        return None

    for i, s in enumerate(shows):
        mt = matrix(s)
        if mt is None:
            if open_at is not None:
                members.append(i)
            continue
        scale, f = mt
        if main is None:
            main = scale
            continue
        if open_at is None:
            if scale <= ratio * main:                  # entering script style
                open_at, open_f = i, f
                base = i - 1 if i else None
                members = [i]
            else:
                main = scale
        else:
            # the scale came back up: the script closes here
            if scale > ratio * main:
                drop = open_f - f
                # A script's baseline moves by a FRACTION of an em. A drop of
                # several em is a new line or a new block that happens to be
                # set smaller -- measured, a `+75.17` between a running head
                # and the body. Bounding it keeps a page move from being read
                # as a script.
                if abs(drop) > 0.6 * main:
                    open_at, members, base = None, [], None
                    main = scale
                    continue
                # A script MOVES THE BASELINE. Distiller emits a `Tm` for
                # every show and alternates size constantly -- a symbol font
                # for the spaces against the body face -- so a size change at
                # the SAME baseline is not a script: 4150 "groups" in 10812
                # shows on one Elsevier paper, against 73 on a dvips page.
                if abs(drop) < 0.05:
                    open_at, members, base = None, [], None
                    main = scale
                    continue
                out.append(ScriptGroup(
                    base=base, members=list(members),
                    kind="sub" if drop < 0 else "sup",
                    scale=round((matrix(shows[open_at]) or (0.0, 0.0))[0]
                                / (main or 1.0), 3),
                    drop=round(drop, 2)))
                open_at, members, base = None, [], None
            else:
                members.append(i)
    return out


# --- line breaks -----------------------------------------------------------
#
# A display equation has NO END MARKER. The producer saves the graphics
# state, draws the expression -- closing and reopening the text object around
# every fraction rule -- and pops the state, which restores the current
# point. What follows looks like ordinary text. So the equation's extent can
# only be known from the command that STARTS THE NEXT LINE.
#
# That command is visible: a `Td`/`TD` whose dx is strongly negative and
# whose dy moves down. Measured on page 1 of 91.pdf: 1183 Td events, of
# which 22 are line returns, and all 22 also move down -- no false positives
# to separate out. My geometric row clustering made 85 rows of that page.
#
#     doc   stream lines   geometric rows   gold equations
#     91              22               85                2
#     93              16               78                2
#     95              16               87                4
#
# A fraction's numerator, rule and denominator are three y values and ONE
# line; each script is a fourth. Baseline clustering cannot recover that and
# no threshold on it will.


def line_breaks(shows: list[Show], min_return: float = 50.0) -> list[int]:
    """Indices in `shows` at which a NEW LINE begins.

    A line return carries the text back toward the left margin and down. The
    threshold is on the RETURN, not on the line height, because the height
    varies with what the line contains while the return is always most of the
    measure.
    """
    out: list[int] = []
    for s in shows:
        mv = s.move
        # `move` is (op, [dx, dy]) -- the operands are a LIST, not spread
        # into the tuple. Reading it as (op, dx, dy) found zero line breaks
        # on a page that has twenty-two, and the zero looked exactly like
        # "this producer does not express line breaks that way".
        if not mv or len(mv) != 2 or not isinstance(mv[1], (list, tuple)) \
                or len(mv[1]) < 2:
            continue
        op, (dx, dy) = mv[0], mv[1][:2]
        if op in ("Td", "TD") and dx <= -min_return and dy < -1.0:
            out.append(s.index)
    return out


def line_index(shows: list[Show], min_return: float = 50.0) -> dict:
    """Map each show's index to the LINE it belongs to."""
    breaks = set(line_breaks(shows, min_return))
    out: dict = {}
    line = 0
    for s in shows:
        if s.index in breaks:
            line += 1
        out[s.index] = line
    return out


def line_starts(shows: list[Show], min_return: float = 50.0) -> list[float]:
    """The absolute y at which each line BEGINS, in text space.

    `Td` is relative to the start of the CURRENT line and `Tm` sets the line
    outright, so the absolute position has to be accumulated: a `Tm` resets
    the line matrix, a `Td`/`TD` advances it, and everything between two
    line returns belongs to one line however many y values it occupies.

    This is what lets a fraction's numerator, rule and denominator -- three y
    values -- be recognised as ONE line, which baseline clustering cannot do.
    """
    out: list[float] = []
    x = y = 0.0
    started = False
    absolute = True
    obj = None
    for s in shows:
        if s.text_object != obj:
            # `BT` resets the text matrix to identity, so the next move is
            # ABSOLUTE. Treating it as relative drifted a baseline from 701
            # to 10954 over one page.
            #
            # But a reset is NOT a new line. The producer opens a text object
            # around every fraction rule -- 59 on one page -- and what
            # follows RESUMES the line it interrupted. Counting each reset as
            # a line gave 81 starts where the Td returns say 22.
            obj = s.text_object
            absolute = True
        mv = s.move
        if not mv or len(mv) != 2 or not isinstance(mv[1], (list, tuple)):
            continue
        op, ops = mv[0], mv[1]
        if op == "Tm" and len(ops) >= 6:
            x, y = float(ops[4]), float(ops[5])
            absolute = False
            if not started:
                out.append(y)
                started = True
            continue
        if op in ("Td", "TD") and len(ops) >= 2:
            dx, dy = float(ops[0]), float(ops[1])
            if absolute:
                # the first move of a text object is the pen position itself
                x, y = dx, dy
                absolute = False
                if not started:
                    out.append(y)
                    started = True
                continue
            x += dx
            y += dy
            # ONLY a return counts as a line. A text-object reset does not.
            if dx <= -min_return and dy < -1.0:
                out.append(y)
    return out


def line_origins(shows: list[Show], min_return: float = 50.0) -> list:
    """Where each line BEGINS, as (x, y) in text space.

    `line_starts` returns only the y, which is enough to bound a line and not
    enough to bound an EXPRESSION. The x is what says whether the next line
    resumes the body or continues a display: a display equation is indented,
    a paragraph is not.

    That is the look-ahead the end of an expression needs. Nothing inside a
    display says where it stops -- the producer pops the graphics state and
    the current point with it -- but the line AFTER it announces itself by
    starting at the body margin.
    """
    out: list = []
    x = y = 0.0
    started = False
    absolute = True
    obj = None
    for s in shows:
        if s.text_object != obj:
            obj = s.text_object
            absolute = True
        mv = s.move
        if not mv or len(mv) != 2 or not isinstance(mv[1], (list, tuple)):
            continue
        op, ops = mv[0], mv[1]
        if op == "Tm" and len(ops) >= 6:
            x, y = float(ops[4]), float(ops[5])
            absolute = False
            if not started:
                out.append((x, y))
                started = True
            continue
        if op in ("Td", "TD") and len(ops) >= 2:
            dx, dy = float(ops[0]), float(ops[1])
            if absolute:
                x, y = dx, dy
                absolute = False
                if not started:
                    out.append((x, y))
                    started = True
                continue
            x += dx
            y += dy
            if dx <= -min_return and dy < -1.0:
                out.append((x, y))
    return out


def display_runs(origins: list, margin_tol: float = 4.0) -> list:
    """Group line origins into RUNS: body lines, and the displays between.

    The body margin is the x that the most lines begin at. A line starting
    there is prose; one starting further right is part of a display. A
    display therefore ENDS at the first following line that returns to the
    margin -- which is the only statement of its end that exists.

    Returns a list of (kind, [indices]) with kind "body" or "display".
    """
    if not origins:
        return []
    from collections import Counter
    votes = Counter(round(x / margin_tol) for x, _ in origins)
    margin = votes.most_common(1)[0][0] * margin_tol
    out: list = []
    for i, (x, _) in enumerate(origins):
        kind = "body" if x <= margin + margin_tol else "display"
        if out and out[-1][0] == kind:
            out[-1][1].append(i)
        else:
            out.append((kind, [i]))
    return out
