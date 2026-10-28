# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Agreement between two lines.json readings of the same document.

`ours` is a reading this program wrote, `ref` a reference (a MathPix
export). Every number is a count or a share that can be recomputed from the
two files alone.
"""
from __future__ import annotations

import re
import statistics

WORD = re.compile(r"[A-Za-z]{4,}")
# slack, in page pixels, when asking whether a reference line lies in ours
SLACK_X, SLACK_Y = 8, 4


_COMMAND = re.compile(r"\\[A-Za-z]+")


def _words(text: str) -> list[str]:
    """Words of 4+ letters; a LaTeX command name is not a word."""
    return [w.lower() for w in WORD.findall(_COMMAND.sub(" ", text))]


def words(page: dict) -> list[str]:
    return [w for ln in page["lines"] for w in _words(ln["text"])]


def word_share(ours: dict, ref: dict) -> float | None:
    """Share of our 4+-letter words the reference page also has.

    None when our page has no such word: a formula-only page says nothing
    about text agreement.
    """
    mine = words(ours)
    if not mine:
        return None
    known = set(words(ref))
    return sum(w in known for w in mine) / len(mine)


def _box(ln: dict) -> tuple[int, int, int, int]:
    r = ln["region"]
    return (r["top_left_x"], r["top_left_y"],
            r["top_left_x"] + r["width"], r["top_left_y"] + r["height"])


def _is_text_content(ln: dict) -> bool:
    return ln["type"] == "text" and ln["conversion_output"]


def located(ours: dict, ref: dict) -> tuple[int, int, list[float]]:
    """(hit, total, font ratios): reference text lines whose centre lies in
    one of our line regions, and reference font_size over ours for each."""
    boxes = [(_box(ln), ln["font_size"]) for ln in ours["lines"]]
    hit = total = 0
    ratios: list[float] = []
    for ln in ref["lines"]:
        if not _is_text_content(ln):
            continue
        total += 1
        x0, y0, x1, y1 = _box(ln)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        near = [(b, f) for b, f in boxes
                if b[0] - SLACK_X <= cx <= b[2] + SLACK_X
                and b[1] - SLACK_Y <= cy <= b[3] + SLACK_Y]
        if near:
            hit += 1
            _, font = min(near, key=lambda bf: abs((bf[0][1] + bf[0][3]) / 2
                                                   - cy))
            if font:
                ratios.append(ln["font_size"] / font)
    return hit, total, ratios


# A line inside one of these containers is read as the container's type.
WRAPPERS = frozenset({"section_header", "title", "authors", "abstract",
                      "footnote", "list_item", "figure_label"})
# The types this program assigns; everything else it leaves as `text`.
TYPED = ("section_header", "title", "page_info", "equation_number", "math",
         "simple_cell")


def _leaves(page: dict) -> list[tuple[dict, str]]:
    """Lines that carry text, each with its effective type."""
    by_id = {ln["id"]: ln for ln in page["lines"]}
    out = []
    for ln in page["lines"]:
        if "children_ids" in ln or not ln["text"]:
            continue
        parent = by_id.get(ln.get("parent_id"))
        kind = (parent["type"] if parent is not None
                and parent["type"] in WRAPPERS else ln["type"])
        out.append((ln, kind))
    return out


def type_table(ours: dict, ref: dict) -> dict:
    """{(reference type, our type or None): lines}. A reference line is
    paired with our line whose region contains its centre."""
    mine = [(_box(ln), kind) for ln, kind in _leaves(ours)]
    table: dict = {}
    for ln, kind in _leaves(ref):
        x0, y0, x1, y1 = _box(ln)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        near = [(b, k) for b, k in mine
                if b[0] - SLACK_X <= cx <= b[2] + SLACK_X
                and b[1] - SLACK_Y <= cy <= b[3] + SLACK_Y]
        got = (min(near, key=lambda bk: abs((bk[0][1] + bk[0][3]) / 2 - cy))[1]
               if near else None)
        table[(kind, got)] = table.get((kind, got), 0) + 1
    return table


def _line_words(ln: dict) -> list[str]:
    return _words(ln["text"])


def _contained(lines: list[list[str]], others: list[list[str]]) -> int:
    """How many of `lines` have all their words in one line of `others`."""
    where: dict[str, set[int]] = {}
    for i, ws in enumerate(others):
        for w in ws:
            where.setdefault(w, set()).add(i)
    count = 0
    for ws in lines:
        common = None
        for w in ws:
            hit = where.get(w)
            if not hit:
                common = None
                break
            common = set(hit) if common is None else common & hit
            if not common:
                break
        count += bool(common)
    return count


def line_match(ours: dict, ref: dict) -> tuple[int, int, int, int]:
    """(pure, ours, covered, ref) over lines with two or more words.

    `pure`: our lines whose words all sit in one reference text line. A row
    that runs across two columns, or two lines read as one, is not pure.
    `covered`: reference text lines whose words all sit in one of our
    lines. A line we split into pieces is not covered.
    """
    mine = [ws for ws in map(_line_words, ours["lines"]) if len(ws) >= 2]
    theirs = [ws for ln in ref["lines"] if _is_text_content(ln)
              for ws in [_line_words(ln)] if len(ws) >= 2]
    return (_contained(mine, theirs), len(mine),
            _contained(theirs, mine), len(theirs))


ORDER_STEP = 2      # reference lines we may skip between two of ours


def reading_order(ours: dict, ref: dict) -> tuple[int, int]:
    """(in order, pairs) over consecutive lines of ours that each sit in one
    reference text line: in order when the second is at most ORDER_STEP
    reference lines after the first. Two columns read row by row jump back
    and forth between distant reference lines and score near zero."""
    theirs = [ws for ln in ref["lines"] if _is_text_content(ln)
              for ws in [_line_words(ln)] if len(ws) >= 2]
    where: dict[str, set[int]] = {}
    for i, ws in enumerate(theirs):
        for w in ws:
            where.setdefault(w, set()).add(i)
    positions = []
    for ln in ours["lines"]:
        ws = _line_words(ln)
        if len(ws) < 2:
            continue
        common = None
        for w in ws:
            hit = where.get(w)
            if not hit:
                common = None
                break
            common = set(hit) if common is None else common & hit
            if not common:
                break
        if common:
            positions.append(min(common))
    pairs = list(zip(positions, positions[1:]))
    return sum(0 <= b - a <= ORDER_STEP for a, b in pairs), len(pairs)


_ENVIRONMENT = re.compile(r"\\(?:begin|end)\{[A-Za-z*]+\}")
_TOKEN = re.compile(r"\\[A-Za-z]+|\\.|\S")
_LAYOUT = frozenset({"{", "}", "&", "\\\\", "\\left", "\\right", "\\quad",
                     "\\qquad", "\\,", "\\;", "\\!", "\\:", "\\[", "\\]",
                     "\\(", "\\)"}
                    | {"\\" + size + side
                       for size in ("big", "Big", "bigg", "Bigg")
                       for side in ("", "l", "r", "m")})
_INLINE = re.compile(r"\\\((.*?)\\\)", re.S)


def math_tokens(latex: str) -> list[str]:
    """What a formula says, without how it is laid out: commands and
    symbols, no braces, delimiter sizing, spacing or environments."""
    return [t for t in _TOKEN.findall(_ENVIRONMENT.sub(" ", latex))
            if t not in _LAYOUT]


def _overlap(a: list[str], b: list[str]) -> int:
    count: dict[str, int] = {}
    for t in a:
        count[t] = count.get(t, 0) + 1
    same = 0
    for t in b:
        if count.get(t):
            count[t] -= 1
            same += 1
    return same


def formula_table(ours: dict, ref: dict) -> dict:
    """{"display": (same, ours, ref), "inline": (same, ours, ref)} in
    tokens. A reference `math` line is held against our `math` line at its
    place; the inline formulas of any other reference line against those
    of our line at its place. A formula with no counterpart counts in
    full on its own side."""
    mine = [(_box(ln), kind, ln) for ln, kind in _leaves(ours)]
    used: set[str] = set()
    score = {"display": [0, 0, 0], "inline": [0, 0, 0]}

    def tokens_of(ln: dict, kind: str) -> tuple[str, list[str]] | None:
        if kind == "math":
            return "display", math_tokens(ln["text"])
        if "\\(" in ln["text"]:           # prose, a cell, a list item
            return "inline", [t for m in _INLINE.findall(ln["text"])
                              for t in math_tokens(m)]
        return None

    for ln, kind in _leaves(ref):
        theirs = tokens_of(ln, kind)
        if theirs is None:
            continue
        which, ref_tokens = theirs
        x0, y0, x1, y1 = _box(ln)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        near = [(b, k, o) for b, k, o in mine
                if b[0] - SLACK_X <= cx <= b[2] + SLACK_X
                and b[1] - SLACK_Y <= cy <= b[3] + SLACK_Y]
        got = (min(near, key=lambda t: abs((t[0][1] + t[0][3]) / 2 - cy))
               if near else None)
        our_tokens: list[str] = []
        if got is not None and got[2]["id"] not in used:
            ours_kind = tokens_of(got[2], got[1])
            if ours_kind is not None and ours_kind[0] == which:
                our_tokens = ours_kind[1]
                used.add(got[2]["id"])
        row = score[which]
        row[0] += _overlap(ref_tokens, our_tokens)
        row[1] += len(our_tokens)
        row[2] += len(ref_tokens)
    for _b, kind, ln in mine:                 # ours with no counterpart
        if ln["id"] not in used:
            extra = tokens_of(ln, kind)
            if extra is not None:
                score[extra[0]][1] += len(extra[1])
    return {k: tuple(v) for k, v in score.items()}


def _f1(same: int, ours: int, ref: int) -> float | None:
    if not ours and not ref:
        return None
    if not same:
        return 0.0
    precision, recall = same / ours, same / ref
    return round(2 * precision * recall / (precision + recall), 4)


def unmapped(page: dict) -> int:
    return sum(ln["text"].count("�") for ln in page["lines"])


def summary(ours: dict, ref: dict | None) -> dict:
    out = {
        "pages": len(ours["pages"]),
        "lines": sum(len(p["lines"]) for p in ours["pages"]),
        "unmapped": sum(unmapped(p) for p in ours["pages"]),
    }
    if ref is None:
        return out
    ref_pages = {p["page"]: p for p in ref["pages"]}
    has_geometry = any(ln["region"]["width"] for p in ours["pages"]
                       for ln in p["lines"])
    shares: list[float] = []
    match = [0, 0, 0, 0]
    order = [0, 0]
    size_equal = hit = total = 0
    ratios: list[float] = []
    table: dict = {}
    formulas = {"display": [0, 0, 0], "inline": [0, 0, 0]}
    subs: dict = {}
    for pg in ours["pages"]:
        rp = ref_pages.get(pg["page"])
        if rp is None:
            continue
        share = word_share(pg, rp)
        if share is not None:
            shares.append(share)
        match = [a + b for a, b in zip(match, line_match(pg, rp))]
        order = [a + b for a, b in zip(order, reading_order(pg, rp))]
        size_equal += ((pg["page_width"], pg["page_height"])
                       == (rp["page_width"], rp["page_height"]))
        if has_geometry:
            h, t, r = located(pg, rp)
            hit, total = hit + h, total + t
            ratios += r
            for key, count in type_table(pg, rp).items():
                table[key] = table.get(key, 0) + count
            for key, row in formula_table(pg, rp).items():
                formulas[key] = [a + b for a, b in zip(formulas[key], row)]
            for key, count in subtype_table(pg, rp).items():
                subs[key] = subs.get(key, 0) + count
    out.update({
        "ref_pages": len(ref["pages"]),
        "ref_content_lines": sum(bool(ln["conversion_output"])
                                 for p in ref["pages"] for ln in p["lines"]),
        "prose_pages": len(shares),
        "word_share_mean": (round(statistics.fmean(shares), 4)
                            if shares else None),
        "word_share_min": round(min(shares), 4) if shares else None,
        "pages_ge_95": sum(s >= 0.95 for s in shares),
        "line_purity": round(match[0] / match[1], 4) if match[1] else None,
        "line_coverage": round(match[2] / match[3], 4) if match[3] else None,
        "reading_order": round(order[0] / order[1], 4) if order[1] else None,
        "page_size_equal": size_equal if has_geometry else None,
        "located": hit if has_geometry else None,
        "locatable": total if has_geometry else None,
        "font_ratio_median": (round(statistics.median(ratios), 3)
                              if ratios else None),
    })
    types = {}
    for kind in TYPED:
        row = {"ref": sum(n for (r, _), n in table.items() if r == kind),
               "ours": sum(n for (_, o), n in table.items() if o == kind),
               "both": table.get((kind, kind), 0)}
        if row["ref"] or row["ours"]:
            types[kind] = row
    out["types"] = types if has_geometry else None
    out["type_hits"] = (sum(t["both"] for t in types.values())
                        if has_geometry else None)
    out["type_false"] = (sum(t["ours"] - t["both"] for t in types.values())
                         if has_geometry else None)
    out["subtypes"] = ({f"{_short(r)}|{_short(o)}": n
                        for (r, o), n in sorted(subs.items(), key=str)}
                       if has_geometry else None)
    out["subtype_same"] = (sum(n for (r, o), n in subs.items() if r == o)
                           if has_geometry else None)
    out["subtype_lines"] = sum(subs.values()) if has_geometry else None
    out["math_display_f1"] = (_f1(*formulas["display"])
                              if has_geometry else None)
    out["math_inline_f1"] = (_f1(*formulas["inline"])
                             if has_geometry else None)
    out["math_tokens"] = ({k: list(v) for k, v in formulas.items()}
                          if has_geometry else None)
    return out


def _short(subtype: str | None) -> str:
    return (subtype or "none").replace("continues_line_", "")


def subtype_table(ours: dict, ref: dict) -> dict:
    """{(reference subtype, our subtype): lines} over the reference's text
    lines that pair with one of our text lines by position."""
    mine = [(_box(ln), ln.get("subtype")) for ln, kind in _leaves(ours)
            if kind == "text"]
    table: dict = {}
    for ln, kind in _leaves(ref):
        if kind != "text":
            continue
        x0, y0, x1, y1 = _box(ln)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        near = [(b, s) for b, s in mine
                if b[0] - SLACK_X <= cx <= b[2] + SLACK_X
                and b[1] - SLACK_Y <= cy <= b[3] + SLACK_Y]
        if not near:
            continue
        got = min(near, key=lambda bs: abs((bs[0][1] + bs[0][3]) / 2 - cy))[1]
        key = (ln.get("subtype"), got)
        table[key] = table.get(key, 0) + 1
    return table
