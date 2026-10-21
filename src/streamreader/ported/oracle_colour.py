# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# Ported from psred (github.com/WulfKolbe/psred), playground/featjudge/featjudge/oracle_colour.py at origin/master 344c27d.
# Kept as close to the original as its new home allows; changes are marked "pdf2mmd2:".
"""oracle_colour - labels from a COLOUR TWIN of the source, via pdfminer.

The same LaTeX compiled twice: plain (psred reads it) and with
\\everymath{\\color{red}} \\everydisplay{\\color{blue}}. Colour does not move
glyphs (fixture: 351/351 identical positions), so the colour of the glyph at
the same origin is an exact label that no feature can leak into.

CONTRACT
    glyph_labels(colour_pdf) -> {(page, round(x,1), round(y,1)): label}
      label 'inline' (red), 'display' (blue), 'text' (anything else)
    label_of(labels, page, x0, base) -> label or None (no glyph there)
    same_layout(plain_pdf, colour_pdf) -> bool   the precondition
    valid_labels(plain_chars, colour_chars) -> (labels, coverage): labels as
      glyph_labels, but ONLY for colour glyphs whose (page, x, y) rounded to
      0.001 and text equal a plain glyph's that is BLACK (is_black): glyphs the
      document colours itself (hyperref colorlinks, FINDINGS F11) carry no
      oracle information; coverage = matched plain glyphs /
      all plain glyphs (0.0 when there are none). Chars: (page, x, y, text, ncolor).
    twin_labels(plain_pdf, colour_pdf) -> valid_labels on the two PDFs
    line_join(A, B, xtol=0.05, max_dy=6.0) -> (mapping, coverage): glyphs
      grouped into lines by (page, round(y, 1)); within a candidate line of B
      (same page, unused, |dy| <= max_dy) glyphs pair one by one: x within
      xtol and the same NFKC-normalised text (a ligature 'ﬂ' = 'fl'); the line
      pair counts when >= min_share (0.9) of A's line pairs up; the candidate
      with most pairs (then smallest |dy|) wins; only paired glyphs map. mapping: A key (page, x, y rounded 0.1) -> B key;
      coverage = matched A glyphs / all A glyphs. For twins whose vertical
      spacing differs per line (another TeX installation) but whose lines
      and x positions are identical (PDF2LaTeX-102, F35).
    line_labels(A, B) -> (labels keyed by A positions, coverage): the colour
      label of each A glyph read from its line_join partner in B.
    coloured_keys(plain_chars) -> {(page, round(x,1), round(y,1))} of plain
      glyphs that are NOT black (the document's own colours, F11)"""
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar


def _chars(pdf):
    out = []
    for pno, page in enumerate(extract_pages(pdf), 1):
        stack = [page]
        while stack:
            o = stack.pop()
            if isinstance(o, LTChar):
                out.append((pno, o.matrix[4], o.matrix[5], o.get_text(), getattr(o.graphicstate, "ncolor", None)))
            elif hasattr(o, "__iter__"):
                stack.extend(o)
    return out


def _label(c):
    if isinstance(c, (tuple, list)) and len(c) == 3:
        r, g, b = c
        if r > 0.5 and g < 0.5 and b < 0.5:
            return "inline"
        if b > 0.5 and r < 0.5 and g < 0.5:
            return "display"
    return "text"


def glyph_labels(colour_pdf):
    return {(p, round(x, 1), round(y, 1)): _label(c) for p, x, y, _, c in _chars(colour_pdf)}


def label_of(labels, page, x0, base):
    for dx in (0.0, -0.1, 0.1):
        for dy in (0.0, -0.1, 0.1):
            hit = labels.get((page, round(x0 + dx, 1), round(base + dy, 1)))
            if hit:
                return hit
    return None


def same_layout(plain_pdf, colour_pdf):
    key = lambda cs: sorted((p, round(x, 3), round(y, 3), t) for p, x, y, t, _ in cs)
    return key(_chars(plain_pdf)) == key(_chars(colour_pdf))


def is_black(c):
    """gray 0, RGB (0,0,0) or CMYK (0,0,0,1); scalars or 1-element lists."""
    if c is None:
        return False
    if isinstance(c, (int, float)):
        c = [c]
    c = list(c)
    return c in ([0], [0, 0, 0], [0, 0, 0, 1])


def valid_labels(plain_chars, colour_chars):
    k = lambda p, x, y, t: (p, round(x, 3), round(y, 3), t)
    allp = [(k(p, x, y, t), c) for p, x, y, t, c in plain_chars]
    plain = {key for key, c in allp if is_black(c)}
    labels, hit = {}, set()
    for p, x, y, t, c in colour_chars:
        key = k(p, x, y, t)
        if key in plain:
            hit.add(key)
            labels[(p, round(x, 1), round(y, 1))] = _label(c)
    return labels, (len(hit) / len(allp) if allp else 0.0)


def twin_labels(plain_pdf, colour_pdf):
    return valid_labels(_chars(plain_pdf), _chars(colour_pdf))


def coloured_keys(plain_chars):
    return {(p, round(x, 1), round(y, 1)) for p, x, y, t, c in plain_chars if not is_black(c)}


def _lines(chars):
    by = {}
    for p, x, y, t, c in chars:
        by.setdefault((p, round(y, 1)), []).append((x, t, c, y))
    return {k: sorted(v) for k, v in by.items()}


def _nk(t):
    import unicodedata
    return unicodedata.normalize("NFKC", t)


def line_join(A, B, xtol=0.05, max_dy=6.0, min_share=0.9):
    la, lb = _lines(A), _lines(B)
    used, mapping = set(), {}
    for (pa, ya), ga in sorted(la.items(), key=lambda kv: (kv[0][0], -kv[0][1])):
        best = None
        for (pb, yb), gb in lb.items():
            if pb != pa or (pb, yb) in used or abs(yb - ya) > max_dy:
                continue
            pairs, j = [], 0
            for a in ga:                     # both x-sorted: walk B alongside A
                while j < len(gb) and gb[j][0] < a[0] - xtol:
                    j += 1
                k = j
                while k < len(gb) and gb[k][0] <= a[0] + xtol:
                    if _nk(gb[k][1]) == _nk(a[1]):
                        pairs.append((a, gb[k]))
                        break
                    k += 1
            if len(pairs) >= min_share * len(ga) and (best is None or len(pairs) > len(best[1])
                                                      or (len(pairs) == len(best[1]) and abs(yb - ya) < abs(best[0][1] - ya))):
                best = ((pb, yb), pairs)
        if best:
            used.add(best[0])
            for a, b in best[1]:
                mapping[(pa, round(a[0], 1), round(a[3], 1))] = (pa, round(b[0], 1), round(b[3], 1))
    return mapping, (len(mapping) / len(A) if A else 0.0)


def line_labels(A, B):
    mapping, cov = line_join(A, B)
    colour = {(p, round(x, 1), round(y, 1)): c for p, x, y, t, c in B}
    return {k: _label(colour[v]) for k, v in mapping.items()}, cov
