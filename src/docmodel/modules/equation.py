"""
EquationProcessor (procOrder 11).

Display equations (lines of type='equation' or type='math') get particularly
rich treatment, since equations are the canonical case for multi-stream
realizations:

  1. Surface realization in `mathpix_lines` — where the equation sits in OCR
     output (one anchor, the whole line).
  2. LaTeX-source realization in a per-equation character-level stream
     `latex_eq_<n>` — character anchors for each codepoint of the normalized
     LaTeX. This is the stream you'd address from a structural LaTeX parser
     (Fraction-of-1-over-2, etc.).
  3. CDN realization — opaque pointer to the MathPix-rendered image URL.

A nearby `equation_number` line (±3 lines around) provides the refnum.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization, Range, Alignment
from ..mathpix import crop_url, image_ref


_OUT_DOLLAR = re.compile(r"^\$\$([\s\S]*)\$\$$")
_OUT_INLDOL = re.compile(r"^\$([\s\S]*)\$$")
_OUT_PAREN = re.compile(r"^\\\(([\s\S]*)\\\)$")
_OUT_BRACK = re.compile(r"^\\\[([\s\S]*)\\\]$")
_BEGIN_EQ = re.compile(r"\\begin\{equation\}")
_END_EQ = re.compile(r"\\end\{equation\}")


#: Environments that belong to the DOCUMENT, not to a formula. MathPix closes
#: a list on the line that carries the last equation in it, so its `math` line
#: reads "\\[ …maths… \\] \\end{itemize}" — verified in its own lines.json, not
#: inferred. For a document reconstruction that is arguably right; as the
#: EQUATION's body it is wrong, and this module lifts the line wholesale.
#:
#: The cost of leaving it: the trailing token also DEFEATS the wrapper strip
#: below, because `_OUT_BRACK` requires the value to END with \\]. So the
#: equation kept its \\[ … \\] delimiters as well, and every one of these
#: failed to compile with "Bad math environment delimiter".
_DOC_ENVS = ("itemize", "enumerate", "description", "document", "proof",
             "remark", "example", "definition", "theorem", "lemma",
             "corollary", "proposition", "exercise", "quote", "center")
_TRAILING_END = re.compile(
    r"\s*\\end\{(" + "|".join(_DOC_ENVS) + r")\}\s*$")
#: The MIRROR case, which the first version left behind: MathPix also OPENS a
#: list on the line carrying the first equation in it —
#:     \\begin{itemize} \\item[] \\[ C=\\gamma T+\\alpha T^{3} \\]
#: an unmatched BEGIN at the head rather than an unmatched END at the tail.
#: Four of the corpus's remaining environment failures were exactly this.
_LEADING_BEGIN = re.compile(
    r"^\s*\\begin\{(" + "|".join(_DOC_ENVS) + r")\}\s*(?:\\item\s*(?:\[[^]]*\])?\s*)*")


def _strip_trailing_structure(s: str) -> str:
    """Drop trailing \\end{...} tokens whose \\begin is not in this value.

    UNMATCHED only: a value that genuinely opens and closes an environment
    keeps both. Removing a closer whose opener is present would corrupt a
    balanced value to fix an unbalanced one.
    """
    while True:
        m = _LEADING_BEGIN.match(s)
        if m and not re.search(r"\\end\{" + m.group(1) + r"\}", s[m.end():]):
            s = s[m.end():].lstrip()
            continue
        m = _TRAILING_END.search(s)
        if not m:
            return s
        env = m.group(1)
        head = s[:m.start()]
        if re.search(r"\\begin\{" + env + r"\}", head):
            return s                     # balanced here; leave it alone
        s = head.rstrip()


def _normalize_latex(raw: str) -> str:
    if not raw:
        return ""
    s = _strip_trailing_structure(raw.strip())
    for rx in (_OUT_BRACK, _OUT_PAREN, _OUT_DOLLAR, _OUT_INLDOL):
        m = rx.match(s)
        if m:
            s = m.group(1)
            break
    s = _BEGIN_EQ.sub("", s)
    s = _END_EQ.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


_MATH_WRAP = (("\\(", "\\)"), ("\\[", "\\]"), ("$$", "$$"), ("$", "$"))


def normalize_equation_number(raw) -> str:
    """The printed equation number, without its wrapping.

    MathPix emits the number bare — `(2.4)` — or wrapped in inline-math
    delimiters — `\\((2.5)\\)`. Stripping paren CHARACTERS turned the second
    into `\\2.5\\`, which `eqnums` then re-wrapped as `(\\2.5\\)`: a number
    with a backslash in it, matching nothing downstream. Remove the DELIMITER
    PAIR first, then the parens.
    """
    t = (raw or "").strip()
    if not t:
        return ""
    changed = True
    while changed:                       # `\(($x$)\)` style nesting
        changed = False
        for open_, close in _MATH_WRAP:
            # >=, not >: `\(\)` is an EMPTY wrapper and must collapse to "",
            # not leave its own backslashes behind as if they were a number.
            if len(t) >= len(open_) + len(close) and t.startswith(open_) and t.endswith(close):
                t = t[len(open_):-len(close)].strip()
                changed = True
    t = re.sub(r"[()]", "", t).strip()
    # An equation number never contains a backslash, so any left here is damage,
    # not content: models built before this fix hold `\\2.5\\` in `refnum`
    # (the old code deleted the parens and kept the delimiters' backslashes).
    # Stripping them repairs those in place, without a rebuild.
    return t.replace("\\", "").strip()


#: 254 — the absorbed equation number. When MathPix does not emit a separate
#: `equation_number` line, the printed number is sometimes swept into the maths
#: body instead, so the equation renders as `... = 1 + \\frac{1}{2} t e_\\infty .(106)`
#: with the number inside the formula AND `equation_number` empty. 1,047 lines
#: in 63 documents corpus-wide (of 130,019 `math` lines); 29 of those documents
#: carry a full numbering sequence and not one `equation_number` line, so the
#: loss is per-document, not per-equation.
#:
#: The discriminator is the SEPARATOR before the paren. An absorbed number is
#: set off from the maths by space, a spacing macro or sentence punctuation
#: (`\\quad (2.14)`, `.(106)`); a group order or function application is glued
#: to its identifier (`S O(8)`, `\\mathrm{Cl}(8)`, `\\mathrm{H}(2)`) and must be
#: left alone. Without that gate the naive trailing-`(N)` test misfires on 74
#: lines of ordinary algebra.
_ABSORBED_EQNUM = re.compile(
    r"(?P<sep>\\quad|\\qquad|\\hspace\{[^}]*\}|\\,|\\;|\\ |~|\s|[.,;])\s*"
    r"\(\s*(?P<num>\d+(?:\.\d+)*[a-zA-Z]?)\s*\)\s*$")
#: Sentence punctuation is part of the DISPLAYED equation ("… t e_\\infty .");
#: a spacing macro is only the gap the number was set in. Keep the first, drop
#: the second — stripping the period too would silently edit the maths.
_KEEP_SEP = frozenset(".,;")
#: Display/inline math delimiters that may trail the number.
_MATH_TAIL = re.compile(r"(?:\\\)|\\\]|\$\$|\$)\s*$")


def absorbed_equation_number(latex: str) -> tuple[str, str]:
    """Split a trailing, separated `(N)` off the end of a math body.

    Returns `(refnum, latex_without_it)`, or `("", latex)` when there is none.
    Only ever called for equations that found NO `equation_number` line, so a
    correctly-emitted number is never second-guessed.
    """
    if not latex:
        return "", latex
    tail = _MATH_TAIL.search(latex)
    delim = latex[tail.start():] if tail else ""
    core = latex[:tail.start()] if tail else latex
    body = core.rstrip()
    m = _ABSORBED_EQNUM.search(body)
    if not m:
        return "", latex
    sep = m.group("sep")
    cut = m.start() + (len(sep) if sep in _KEEP_SEP else 0)
    return m.group("num"), (body[:cut].rstrip() + delim)


#: Environments whose ROWS are separate numbered equations. `cases`, `split`
#: and `multline` are deliberately absent: each is ONE equation set over
#: several lines, and splitting one would invent equations the book never
#: printed.
_MULTI_EQ_ENVS = frozenset({
    "aligned", "align", "align*", "alignat", "alignat*",
    "gather", "gathered", "gather*", "eqnarray", "eqnarray*",
})
_ENV_OPEN = re.compile(r"\\begin\{([A-Za-z*]+)\}")
_CMD_NAME = re.compile(r"[A-Za-z]+")
#: An alignment point that is real, not the escaped literal `\&`.
_LIVE_AMP = re.compile(r"(?<!\\)&")


def alignment_rows(latex: str) -> list[str]:
    r"""The rows of a multi-equation alignment, or `[]` when it is not one.

    Splits on `\\` at environment depth 0 ONLY. A `\\` inside a nested
    `array`, `matrix` or `cases` is that environment's own row break and
    belongs to the formula; cutting there would take a matrix apart.
    """
    m = _ENV_OPEN.search(latex or "")
    if not m or m.group(1) not in _MULTI_EQ_ENVS:
        return []
    end = latex.rfind("\\end{%s}" % m.group(1))
    if end <= m.end():
        return []
    body = latex[m.end():end]
    rows: list[str] = []
    cur: list[str] = []
    depth = i = 0
    while i < len(body):
        if body[i] != "\\":
            cur.append(body[i])
            i += 1
            continue
        if body.startswith("\\\\", i):
            if depth:
                cur.append("\\\\")
            else:
                rows.append("".join(cur))
                cur = []
            i += 2
            continue
        cmd = _CMD_NAME.match(body, i + 1)
        if not cmd:                       # an escaped character: \& \{ \%
            cur.append(body[i:i + 2])
            i += 2
            continue
        if cmd.group(0) == "begin":
            depth += 1
        elif cmd.group(0) == "end":
            depth -= 1
        cur.append(body[i:cmd.end()])
        i = cmd.end()
    rows.append("".join(cur))
    return [r.strip() for r in rows if r.strip()]


def standalone_row(row: str) -> str:
    r"""One alignment row as a formula in its own right.

    The leading `&` was the alignment point against its neighbours and means
    nothing alone. An `&` still inside the row DOES mean something, and outside
    an alignment environment it is a fatal `Misplaced alignment tab`, so such a
    row keeps a one-row `aligned` around it.
    """
    r = re.sub(r"^&\s*", "", row.strip())
    if _LIVE_AMP.search(r):
        return "\\begin{aligned} %s \\end{aligned}" % r
    return r


def number_bands(region: dict, ys: list) -> list[dict]:
    """Divide a block's box into one band per number.

    Cut at the MIDPOINT between consecutive number y-centres rather than into
    equal parts: the rows of an alignment are not equally tall (a fraction is
    twice a bare identifier), and the publisher sets each number on its own
    row's centre, so the numbers are the only evidence on the page for where
    one row ends and the next begins.
    """
    top = int(region.get("top_left_y") or 0)
    height = int(region.get("height") or 0)
    edges = [float(top)]
    for a, b in zip(ys, ys[1:]):
        edges.append(min(max((a + b) / 2.0, edges[-1]), top + height))
    edges.append(float(top + height))
    # INTEGER PIXELS, like every other region in the corpus. A MathPix region
    # is a pixel box and the whole pipeline reads it back with `int(...)` on a
    # STRINGIFIED field: a tiddler carrying "286.0" raises `invalid literal for
    # int()` where "675" does not, and `render_crops` counts that as a skipped
    # row — so the two rows this change exists to recover were the only two in
    # BH3FR's report with no scan beside them. Rounding the EDGES and taking
    # differences keeps the bands tiling the block exactly.
    cuts = [int(round(e)) for e in edges]
    out = []
    for lo, hi in zip(cuts, cuts[1:]):
        band = dict(region)
        band["top_left_y"] = lo
        band["height"] = max(hi - lo, 0)
        out.append(band)
    return out


class EquationProcessor(BaseModule):
    #: 249 — BOTH, and "equation" is not dead. It occurs ZERO times in the
    #: 3,998,456 MathPix line objects of the corpus, which is why out/245
    #: listed it as a literal that never occurs — but that scan read
    #: *.lines.json only, and MathPix is not the only producer of lines. The
    #: visionocr / LLM-delegation route emits `type: "equation"` directly
    #: (tests/test_visionocr.py builds exactly that shape). Removing it broke
    #: two tests immediately.
    #:
    #: "absent from the corpus" is not "absent from the inputs", and the
    #: corpus is one producer's output.
    EQ_TYPES = {"equation", "math"}

    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        anchors = stream.anchors

        # Number equations by page + vertical position, not stream proximity.
        # MathPix often emits all of a page's `math` lines first and then all
        # its `equation_number` lines, so a +-N stream-index window only catches
        # the first equation per page (this left 12/13 equations of arXiv
        # 2312.11532 unnumbered, incl. eq 9, when running `model` alone).
        # 823 — the SPLIT is planned first, because it consumes numbers the
        # greedy pairing below would otherwise hand to a neighbour. One MathPix
        # `math` line can hold several separately-numbered rows; before this,
        # each line took at most ONE number, which dropped 4,826 printed
        # numbers across 307 of 1,506 documents (9.8% of every number the
        # corpus prints) and, worse, left the surviving equation carrying the
        # other rows' formulae under its own label. BH3FR p108 is the shape:
        # `\begin{aligned} & r=… \\ & m=… \end{aligned}` with (25) at
        # y=327 and (26) at y=513 — (25) vanished and (26) claimed both rows.
        splits = self._split_plan(anchors, stream)
        consumed = {na for rows in splits.values() for (_t, na, _r, _g) in rows}
        refnum_by_anchor = self._match_equation_numbers(
            anchors, stream, skip_eq=set(splits), skip_num=consumed)

        items: list[dict[str, Any]] = []
        for i, anchor in enumerate(anchors):
            payload = stream.payload[anchor]
            if payload.get("type") not in self.EQ_TYPES:
                continue
            if anchor in splits:
                items.extend(self._split_items(anchor, payload, splits[anchor]))
                continue
            paired = refnum_by_anchor.get(anchor)
            refnum, refnum_anchor = paired if paired else ("", None)
            if not refnum:
                refnum = self._refnum_near(
                    anchors, stream, i,
                    used={n for n, _a in refnum_by_anchor.values()}
                        | {t for rows in splits.values() for (t, _a, _r, _g) in rows})
            latex_raw = payload.get("text_display") or payload.get("text") or ""
            # 254 — last resort: the number MathPix swept into the maths.
            absorbed = ""
            if not refnum:
                absorbed, stripped = absorbed_equation_number(latex_raw)
                if absorbed:
                    refnum, latex_raw = absorbed, stripped
                    self.bump("equation_numbers_recovered")
            items.append({
                "anchor": anchor,
                "page": payload.get("_page"),
                "image_id": payload.get("_image_id"),
                "region": payload.get("region"),
                "refnum": refnum,
                "refnum_anchor": refnum_anchor,
                # Provenance: this number was read out of the formula body, not
                # from an `equation_number` line. A consumer that cares which
                # numbers MathPix actually stated can tell the two apart.
                "refnum_source": "absorbed" if absorbed else ("line" if refnum else ""),
                "latex_raw": latex_raw,
                "latex": _normalize_latex(latex_raw),
                # MathPix's own doubt about this line. It was in the payload
                # all along and was being dropped here, so nothing downstream
                # could consult it: 0902.0431_EQ0516 reads at confidence 0.041
                # with 19 of 48 array cells wrong or missing, and the report
                # showed it as a clean equation (out/063).
                "confidence": payload.get("confidence"),
                "confidence_rate": payload.get("confidence_rate"),
            })
        return items

    def _split_plan(self, anchors, stream) -> dict:
        """Which math lines hold more than one numbered equation.

        A line splits only when the evidence is unambiguous: the numbers lie
        INSIDE its own box (not merely near it), its LaTeX is a multi-equation
        alignment, and it has exactly as many rows as there are numbers. Any
        other count is left to the greedy pairing exactly as before and
        counted, because a guess about which row a number belongs to is the
        misattribution this change exists to remove.

        Returns {equation_anchor: [(number, number_anchor_id, row, region)]}.
        """
        def box(p):
            r = p.get("region") or {}
            top = r.get("top_left_y")
            if top is None:
                return None
            return float(top), float(top) + float(r.get("height") or 0)

        eqs: dict = {}
        nums: dict = {}
        for a in anchors:
            p = stream.payload[a]
            b = box(p)
            if b is None:
                continue
            pg = p.get("_page")
            if p.get("type") in self.EQ_TYPES:
                eqs.setdefault(pg, []).append((b, a, p))
            elif p.get("type") == "equation_number":
                t = normalize_equation_number(p.get("text") or p.get("text_display"))
                if t:
                    nums.setdefault(pg, []).append(
                        ((b[0] + b[1]) / 2.0, t, getattr(a, "id", a)))

        plan: dict = {}
        for pg, here in eqs.items():
            for (y0, y1), a, p in here:
                inside = sorted(n for n in nums.get(pg, []) if y0 <= n[0] <= y1)
                if len(inside) < 2:
                    continue
                latex = _normalize_latex(
                    p.get("text_display") or p.get("text") or "")
                rows = alignment_rows(latex)
                if len(rows) != len(inside):
                    self.bump("equation_number_blocks_unsplit")
                    continue
                bands = number_bands(p.get("region") or {},
                                     [n[0] for n in inside])
                plan[a] = [(t, na, standalone_row(row), band)
                           for (_y, t, na), row, band
                           in zip(inside, rows, bands)]
                self.bump("equations_split")
                self.bump("equation_numbers_recovered_by_split", len(inside) - 1)
        return plan

    def _split_items(self, anchor, payload, rows) -> list:
        """One item per numbered row of a split block.

        Every row surfaces on the SAME line anchor — a Realization is
        many-to-one, so this needs no change to the line stream and the block
        stays addressable as the one thing MathPix actually emitted.
        """
        out = []
        for k, (num, num_anchor, row, region) in enumerate(rows):
            out.append({
                "anchor": anchor,
                "page": payload.get("_page"),
                "image_id": payload.get("_image_id"),
                "region": region,
                "refnum": num,
                "refnum_anchor": num_anchor,
                "refnum_source": "line",
                "latex_raw": row,
                "latex": _normalize_latex(row),
                "confidence": payload.get("confidence"),
                "confidence_rate": payload.get("confidence_rate"),
                "split_index": k,
                "split_count": len(rows),
            })
        return out

    def _match_equation_numbers(self, anchors, stream,
                                skip_eq=frozenset(),
                                skip_num=frozenset()) -> dict:
        """Pair each math/equation line with the same-page `equation_number`
        line whose region y-center is closest (greedy nearest-pair, each number
        used once). Returns {equation_anchor: ("N", number_anchor)}.

        The number's ANCHOR travels with it so a consumer can point an Alignment
        at the span the string was derived from. Returning the bare string made
        the rewritten value the only record of the input — which is precisely
        why a bad rewrite could not be detected or recovered.
        """
        def y_center(p):
            r = p.get("region") or {}
            top = r.get("top_left_y")
            return None if top is None else top + (r.get("height") or 0) / 2.0

        eqs_by_page: dict = {}
        nums_by_page: dict = {}
        for a in anchors:
            p = stream.payload[a]
            yc = y_center(p)
            if yc is None:
                continue
            pg = p.get("_page")
            if p.get("type") in self.EQ_TYPES:
                if a in skip_eq:          # 823 — already split, row by row
                    continue
                eqs_by_page.setdefault(pg, []).append((yc, a))
            elif p.get("type") == "equation_number":
                t = normalize_equation_number(p.get("text") or p.get("text_display"))
                if t and getattr(a, "id", a) not in skip_num:
                    # the anchor's ID (a string): props are serialised to JSON,
                    # and an Anchor object round-trips as its repr, which then
                    # matches nothing.
                    nums_by_page.setdefault(pg, []).append(
                        (yc, t, getattr(a, "id", a)))

        out: dict = {}
        for pg, eqs in eqs_by_page.items():
            nums = nums_by_page.get(pg, [])
            pairs = sorted(
                ((abs(ey - ny), ea, ny, nt, na)
                 for (ey, ea) in eqs for (ny, nt, na) in nums),
                key=lambda t: t[0],
            )
            used_num: set = set()
            for _d, ea, ny, nt, na in pairs:
                if ea in out or ny in used_num:
                    continue
                out[ea] = (nt, na)
                used_num.add(ny)
        return out

    @staticmethod
    def _refnum_near(anchors, stream, i: int, used: "set | None" = None) -> str:
        """Positional fallback: the nearest `equation_number` in a ±3 stream
        window, for an equation the geometric pass could not place.

        `used` is the set of numbers the geometric pass already assigned, and
        skipping them is the whole point: the two algorithms had no shared
        bookkeeping, so on a page with 3 equations and 2 numbers this handed
        (2.5) to a THIRD equation that already belonged to another — two
        equations printing the same number and the next one printing none.
        """
        used = used if used is not None else set()
        lo, hi = max(0, i - 3), min(len(anchors), i + 4)
        for j in range(lo, hi):
            p = stream.payload[anchors[j]]
            if p.get("type") == "equation_number":
                t = normalize_equation_number(p.get("text") or p.get("text_display"))
                if t and t not in used:
                    return t
        return ""

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        # 1) Build a per-equation char-level stream for the normalized LaTeX.
        eq_no = self.bump("equations_created")
        latex_stream_name = f"latex_eq_{eq_no:04d}"
        latex_stream = doc.ensure_stream(latex_stream_name)
        latex_anchors = [latex_stream.append(codepoint=ch) for ch in item["latex"]]

        obj = DocObject(
            type="Equation",
            props={
                "refnum": item["refnum"],
                "refnum_anchor": item.get("refnum_anchor"),
                "latex": item["latex"],          # convenient copy
                "latex_raw": item["latex_raw"],
                "page": item["page"],
                "image_id": item["image_id"],
                "region": item["region"],
                "confidence": item.get("confidence"),
                "confidence_rate": item.get("confidence_rate"),
                # 823 — this equation is one row of a block MathPix emitted as
                # a single line. A reader comparing against the scan needs to
                # know that its crop is a BAND of a taller box, not the box.
                "split_index": item.get("split_index"),
                "split_count": item.get("split_count"),
                # source-aware crop: MathPix pixels via cdn.mathpix.com, or OUR
                # local pyramid in PDF points (pdfminer/DRILLPDFse) — never mixed.
                "cdn_url": image_ref(item["image_id"], item["region"],
                                     doc.meta.get("source", "mathpix")),
                "bibkey": self.bibkey,
            },
        )
        # surface in the OCR line stream
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchor"], end=item["anchor"],
            role="surface",
        ))
        # latex source as a char-level realization
        if latex_anchors:
            obj.add_realization(Realization(
                stream=latex_stream_name,
                start=latex_anchors[0], end=latex_anchors[-1],
                role="latex_source",
            ))
        # rendered image (no anchor range, just a URL pointer)
        if obj.props["cdn_url"]:
            obj.add_realization(Realization(
                stream="cdn",
                role="image",
                props={"url": obj.props["cdn_url"]},
            ))

        # The rendering relationship "this latex source produces this CDN
        # image" is expressed both as the cdn-role Realization above AND as
        # an Alignment of kind 'render'. The cdn side of the Range has no
        # anchors (the URL is the substance), which is now a first-class
        # case the Range type supports.
        if latex_anchors and obj.props["cdn_url"]:
            doc.add_alignment(Alignment(
                kind="render",
                left=Range(latex_stream_name, latex_anchors[0], latex_anchors[-1]),
                right=Range("cdn", None, None),
                props={"target_url": obj.props["cdn_url"]},
            ))

        return obj
