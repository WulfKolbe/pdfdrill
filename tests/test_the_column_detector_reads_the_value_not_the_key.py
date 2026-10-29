r"""`rectoverso._column_signal` gave up before it measured anything, on every
reading pdfdrill can produce.

    explicit = all("column" in ln for ln in lines if _region(ln))
    key = ln["column"] if explicit else round(x / pw, 1)   # cluster by left edge
    ...
    if len(stats) < 2:
        return None, {"columns_found": len(stats)}

`"column" in ln` is a KEY-PRESENCE test and every line carries the key, so
`explicit` is always True, every line's key is the literal `0`, every line lands
in ONE bucket, and the function returns `None, {"columns_found": 1}`. The
left-edge clustering underneath — the branch that works — is unreachable.

Its job is the recto/verso signal: a narrow MARGIN column beside a wide body
column tells you which side of the leaf you are on. It has never been able to
answer.

MEASURED 2026-10-29: `column` is `0` on all 11,071 lines of the fifteen CCL
readings, and it is 0 because MathPix puts 0 there — a real MathPix reading
(2025_05_15_4ff45b8a311ea255c52dg) carries `column: 0` on all 194 of its lines
and states the column in the CONTAINER nesting instead, `parent_id` pointing at
a `type: "column"` record. `docmodel_six._add_column_containers` follows that
same convention: 659 lines under col0 and 468 under col1 on 2009tiplabeling.

So the value was never a column number in either producer, and the fix is not
to start writing one — it is to stop believing a key. Believe the field only
where it DISTINGUISHES something, prefer the container nesting that actually
carries the column, and otherwise cluster by left edge as before. This is the
`hasattr(LTChar, "glyphname")` shape again: a presence test standing in for a
value test, costing a whole capability in silence (2026-10-28).
"""
import pytest

from pdfdrill import rectoverso

PW, PH = 1000.0, 1400.0


def _page(*, column_key=None, parent=False):
    """A wide body column with a narrow margin column to its LEFT — the shape
    `_column_signal` exists to recognise, which makes it a verso."""
    out = []
    for i in range(14):
        y = 300 + i * 60
        out.append({"region": {"top_left_x": 250, "top_left_y": y,
                               "width": 620, "height": 40},
                    "text": f"body {i}"})
        if i % 2 == 0:                      # a few marginal notes
            out.append({"region": {"top_left_x": 70, "top_left_y": y,
                                   "width": 120, "height": 40},
                        "text": f"note {i}"})
    if column_key is not None:
        for ln in out:
            ln["column"] = column_key
    if parent:
        for ln in out:
            ln["parent_id"] = ("p1-col0" if ln["region"]["top_left_x"] < 200
                               else "p1-col1")
    return out


def test_the_signal_is_found_when_every_line_carries_column_zero():
    """THE CASE BUILT TO FAIL — the shape of every reading on disk."""
    side, ev = rectoverso._column_signal(_page(column_key=0), PW, PH)
    assert ev.get("columns_found") != 1, (
        "a key-presence test put every line in one bucket: " + str(ev))
    assert side == "verso", (side, ev)


def test_the_signal_is_the_same_whether_the_dead_key_is_there_or_not():
    """The same page, the same answer. A field that distinguishes nothing must
    not change the result."""
    with_key = rectoverso._column_signal(_page(column_key=0), PW, PH)
    without = rectoverso._column_signal(_page(), PW, PH)
    assert with_key[0] == without[0] == "verso", (with_key, without)


def test_the_container_nesting_is_believed_when_it_distinguishes():
    """`parent_id` is where both producers really state the column, so a
    reading that carries it is answered from it rather than from geometry."""
    side, ev = rectoverso._column_signal(_page(column_key=0, parent=True),
                                         PW, PH)
    assert side == "verso", (side, ev)


def test_a_column_field_that_really_distinguishes_is_still_believed():
    """If a producer ever does write real column numbers, they win over
    geometry — that was the intent of the `explicit` branch all along."""
    lines = _page(column_key=0)
    for ln in lines:
        ln["column"] = 0 if ln["region"]["top_left_x"] < 200 else 1
    side, ev = rectoverso._column_signal(lines, PW, PH)
    assert side == "verso", (side, ev)


def test_a_single_column_page_still_answers_nothing():
    """No narrow margin column, no signal — and it must say which it was."""
    lines = [{"region": {"top_left_x": 250, "top_left_y": 300 + i * 60,
                         "width": 620, "height": 40}, "text": f"body {i}",
              "column": 0} for i in range(14)]
    side, ev = rectoverso._column_signal(lines, PW, PH)
    assert side is None
    assert ev.get("columns_found") == 1 or "note" in ev, ev
