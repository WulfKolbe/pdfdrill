r"""A page read a third of the way through must not arrive looking like a page.

MEASURED, 2026-11-25, a board scan extract read on a local host. One of the six
calls that make up page 2 returned 24,565 characters, every one of them part of
`(9.25) $\quad \quad \quad …`, to the 8,192-token completion ceiling. The chain
appended it to the page and reported "Read 3 printed pages": the bottom two
thirds of that page were gone, the reading said nothing, and the only place the
truncation was visible at all was `finish: length` in the call log, which
nothing read.

The board already knew this failure on this model ("every read aborts on
Ollama's repeat limit (dot leaders)" — board.md, scan-20260723-1130 p2). What
pdfdrill had was no limit at all.

Two signals, deliberately: `finish_reason == "length"` is the host's own and
needs no interpretation; `periodic_tail` catches a loop that stopped by itself.
Neither identifies a loop by its CONTENT — a list of looping fragments
(`\quad`, a dot leader, a dash) is a list to maintain — but by its SHAPE.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import gemma_reader as GR


def test_the_measured_loop_is_a_loop():
    text = "(9.25) $" + "\\quad " * 1900
    cut = GR.periodic_tail(text)
    assert cut > 0
    # everything but the line's own head is the loop
    assert len(text) - cut < 20


def test_a_contents_row_of_dot_leaders_is_not_a_loop():
    """The failure the board recorded was ON a dot-leader page, so the rule
    that catches the loop must not catch the leaders: a row of them is one
    printed line, and a printed line is content."""
    assert GR.periodic_tail("Chapter 1 " + ". " * 40 + " 7") == 0
    assert GR.periodic_tail("Chapter 1 " + ". " * 40) == 0


def test_prose_and_latex_are_not_loops():
    assert GR.periodic_tail("But suppose we make the substitution (9.20) in "
                            "equation (9.17). Since, in these last equations, "
                            "addition is to be regarded as commutative.") == 0
    assert GR.periodic_tail(r"\[ \sum_{i=1}^{n} a_i x_i = 0 \]") == 0
    assert GR.periodic_tail("") == 0
    assert GR.periodic_tail("   \n ") == 0


def _one_page(tmp_path, replies, monkeypatch):
    """Run `read_page` over a 1-pixel-wide page with a canned reply per chunk."""
    Image = pytest.importorskip("PIL.Image")
    png = tmp_path / "page-0001.png"
    Image.new("L", (40, 120), 255).save(png)
    seen = iter(replies)

    def fake_run(task, image=None, text=None, **kw):
        rec = dict(next(seen))
        rec["provider"] = "ollama"
        return rec

    from pdfdrill import vision_router
    monkeypatch.setattr(vision_router, "run", fake_run)
    # one strip per chunk, so a reply is a chunk
    return GR.read_page(png, tmp_path / "work", strips=1, max_tokens=99)


def test_a_chunk_that_ran_to_the_ceiling_says_the_page_stops_mid_way(
        tmp_path, monkeypatch):
    got = _one_page(tmp_path, [{"text": "a line of prose",
                                "finish_reason": "length", "usage": {}}],
                    monkeypatch)
    assert got["markdown"] == "a line of prose"      # what was read is kept
    assert got["lost"] and "ceiling" in got["lost"][0]


def test_a_loop_is_dropped_and_reported(tmp_path, monkeypatch):
    reply = "real text here\n" + "\\quad " * 300
    got = _one_page(tmp_path, [{"text": reply, "finish_reason": "stop",
                                "usage": {}}], monkeypatch)
    assert "\\quad \\quad \\quad" not in got["markdown"]
    assert got["markdown"].startswith("real text here")
    assert got["lost"] and "repeated fragment" in got["lost"][0]


def test_a_page_the_model_finished_loses_nothing(tmp_path, monkeypatch):
    got = _one_page(tmp_path, [{"text": "a whole page", "finish_reason": "stop",
                                "usage": {}}], monkeypatch)
    assert got["lost"] == [] and got["markdown"] == "a whole page"


def test_the_mark_is_written_beside_the_markdown_so_a_resume_sees_it(tmp_path):
    """A resumed run reads the page back from disk and spends nothing. A page
    that comes back WITHOUT its mark comes back looking complete, so the mark
    is a file next to the Markdown rather than a value in memory."""
    printed = tmp_path / "printed"
    printed.mkdir()
    md = printed / "page-0002.md"
    md.write_text("half a page\n", encoding="utf-8")
    mark = md.with_suffix(".incomplete")
    mark.write_text("part 2 of 2 ran to the ceiling\n", encoding="utf-8")
    # the shape fetch_gemma reads back
    assert mark.is_file() and md.is_file()
    assert "ceiling" in mark.read_text(encoding="utf-8")
    assert mark.name == "page-0002.incomplete"


def test_the_reading_itself_carries_the_incomplete_pages():
    """`ocr.incomplete` is where a consumer already looks. `gd3-learn` learns a
    dictionary from these pages' text, and learning from a third of a page is
    how a gate fails for a reason nothing in the file can explain."""
    doc = GR.assemble([(1, "a line", None)], prompt_name="p", model="ollama")
    assert "incomplete" not in doc["ocr"]            # nothing lost, nothing said
    doc["ocr"]["incomplete"] = {"2": "it stops mid-page"}
    assert doc["ocr"]["incomplete"]["2"]
