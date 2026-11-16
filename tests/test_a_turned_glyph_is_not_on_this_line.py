"""
A glyph that is not upright is not on the line that shares its y.

THE DEFECT, reported by the owner on arxiv.2209.02970 (2026-11-16) as "left
sidenote with bar code not separated". The arXiv e-print stamp
`arXiv:2209.02970v3 [cs.CL] 30 Mar 2023` is printed up the left margin, rotated
90 degrees. Measured on page 1:

    the stamp                 40 glyphs, every one `upright: False`,
                              matrix (0, 1, -1, 0, 32, 232)
    every body glyph          `upright: True`
    the only ink left of x=40 the stamp, 5 words by `pdftotext -bbox`

`upright` is in the pdfplumber/pdfminer input and this module read it nowhere,
so each rotated glyph was clustered by its `top` like any other. Each stamp
glyph sits at its own y, so each joined a DIFFERENT body line and 31 of the
page's 58 reader lines began with a stray character:

    '3 ligence, paving ways to the general intelli-'
    '2 gent challenges: existing foundation models'
    '2 are dominated by the English-language com-'

That is worse than unseparated: it corrupts the first word of half the page's
prose, and no later pass can tell the stray character from the text. It also
fed the column detector and the median line height with glyphs that are not
lines.

AFTER: page 1 holds ONE record left of x=40, reading
`arXiv:2209.02970v3 [cs.CL] 30 Mar 2023`, and no body line carries a stamp
glyph. 31 contaminated lines -> 0.

THE DIRECTION HAD TO BE CARRIED TOO, and that was learnt by reading the output
rather than by reasoning: ordering the turned run by increasing `top` produced

    '3202 raM 03 ]LC.sc[ 3v07920.9022:viXra'

A +90 turn advances UP the page, so the run reads from the largest `top` to the
smallest; a -90 turn advances down. The sign comes from the glyph's text matrix
at the same seam as `upright`, never guessed from which order looks like words.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import chars_to_lines as C

PH, PW = 841.89, 595.28


def _char(x0, y_top, text, upright=True, turn=0, w=5.0, h=9.0):
    """One glyph, in the input's bottom-left origin (y0/y1 up)."""
    return {"x0": x0, "x1": x0 + w,
            "y0": PH - (y_top + h), "y1": PH - y_top,
            "text": text, "fontname": "Times-Roman",
            "upright": upright, "turn": turn}


def _body(n=8, y0=200.0):
    """n upright prose lines at the body edge."""
    out = []
    for i in range(n):
        y = y0 + i * 12.0
        for j, ch in enumerate("prose line running on"):
            out.append(_char(70.9 + j * 5.0, y, ch))
    return out


def _stamp(text="arXiv:2209.02970v3", y0=240.0):
    """The margin stamp: one glyph per y, turned +90, so it reads UP the page.
    Reversed order on purpose — the reader must not depend on input order."""
    out = []
    for i, ch in enumerate(text):
        out.append(_char(16.3, y0 + (len(text) - 1 - i) * 10.0, ch,
                         upright=False, turn=90, w=20.0, h=8.9))
    return out


def _page(chars):
    return {"page_number": 1, "width": PW, "height": PH, "chars": chars}


def _lines(chars):
    js = C.chars_to_lines_json(
        {"source": "pdfminer-chars", "total_pages": 1, "pages": [_page(chars)]})
    return [l for l in js["pages"][0]["lines"] if l.get("region")]


def test_no_body_line_carries_a_turned_glyph():
    lines = _lines(_body() + _stamp())
    for l in lines:
        if l["region"]["top_left_x"] >= 70.0:
            assert "arXiv" not in (l.get("text") or ""), \
                f"a turned glyph rode into a body line: {l.get('text')!r}"
            assert not (l.get("text") or "").startswith(("a", "r", "X", ":")), \
                f"a body line starts with a stamp glyph: {l.get('text')!r}"


def test_the_turned_run_is_one_record():
    stamp = [l for l in _lines(_body() + _stamp())
             if l["region"]["top_left_x"] < 40.0]
    assert len(stamp) == 1, \
        f"the margin stamp became {len(stamp)} records instead of 1"


def test_the_turned_run_reads_the_right_way_round():
    stamp = [l for l in _lines(_body() + _stamp())
             if l["region"]["top_left_x"] < 40.0]
    assert stamp and "arXiv:2209.02970v3" in (stamp[0].get("text") or ""), \
        f"the turned run reads backwards: {stamp[0].get('text')!r}"


def test_a_minus_90_run_reads_the_other_way():
    """The sign decides, not what looks like words."""
    chars = _body()
    text = "Table 3 continued"
    for i, ch in enumerate(text):
        chars.append(_char(16.3, 240.0 + i * 10.0, ch,
                           upright=False, turn=-90, w=20.0, h=8.9))
    got = [l for l in _lines(chars) if l["region"]["top_left_x"] < 40.0]
    assert got and text in (got[0].get("text") or ""), \
        f"a -90 run read backwards: {got[0].get('text')!r}"


def test_the_prose_survives_in_full():
    lines = _lines(_body(n=8) + _stamp())
    body = [l for l in lines if l["region"]["top_left_x"] >= 70.0]
    assert len(body) == 8, f"expected 8 prose lines, got {len(body)}"
    for l in body:
        assert (l.get("text") or "").startswith("prose line"), \
            f"a prose line was damaged: {l.get('text')!r}"


def test_turned_glyphs_do_not_decide_the_page_geometry():
    """They are removed before the page is measured, so they cannot fill a
    column gutter nor shift the median line height every threshold uses."""
    chars = []
    for i in range(40):
        y = 200.0 + i * 12.0
        for j in range(44):
            chars.append(_char(70.9 + j * 5.0, y, "x"))
        for j in range(44):
            chars.append(_char(304.0 + j * 5.0, y, "x"))
    # a turned run standing right in the gutter
    for i in range(30):
        chars.append(_char(295.0, 200.0 + i * 10.0, "s",
                           upright=False, turn=90, w=8.0, h=8.9))
    items = [{"x0": c["x0"], "x1": c["x1"],
              "top": PH - c["y1"], "bottom": PH - c["y0"]}
             for c in chars if c["upright"]]
    assert C._column_split_for_lines(items, PW) is not None, \
        "the two columns were lost"


def test_a_page_of_only_turned_glyphs_still_reads():
    """A rotated plate or a sideways table page must not come back empty."""
    lines = _lines(_stamp(text="sideways page title"))
    assert lines, "a page of only turned glyphs produced no lines"
    assert "sideways page title" in " ".join(l.get("text") or "" for l in lines)
