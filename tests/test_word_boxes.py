"""Where a word box comes from, and where it must refuse to come from.

`word_boxes` replaced seven features' private "render the page and run
tesseract". The contract it has to keep is narrow and worth holding: word boxes
WITH TEXT come only from something that read the page (the PDF's own text
layer); word boxes WITHOUT text come from the page's ink; a reading bought from
a provider is never a word-box source, because `gemmaocr` and `mathpix` emit
LINE boxes and a line box offered where a word box is expected is a WRONG
measurement rather than a missing one.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pdfdrill import word_boxes

_TSV = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\t"
    "width\theight\tconf\ttext\n"
    "1\t1\t0\t0\t0\t0\t0\t0\t612\t792\t-1\t\n"
    "5\t1\t1\t1\t1\t1\t72\t100\t40\t10\t-1\tHello\n"
    "5\t1\t1\t1\t1\t2\t120\t100\t44\t10\t-1\tworld\n"
)


def test_the_text_layer_gives_words_with_their_text(monkeypatch):
    monkeypatch.setattr(word_boxes, "text_layer_tsv", lambda *a, **k: _TSV)
    words, dims, src = word_boxes.words_for(Path("x.pdf"))
    assert src == word_boxes.TEXT_LAYER
    assert [w["text"] for w in words] == ["Hello", "world"]
    assert dims[1] == (612.0, 792.0)
    # points, not pixels: a model's regions are in points and nothing rescales
    assert words[0]["x0"] == 72.0 and words[0]["x1"] == 112.0


def test_an_empty_text_layer_is_not_a_source(monkeypatch):
    monkeypatch.setattr(word_boxes, "text_layer_tsv", lambda *a, **k: "")
    words, dims, src = word_boxes.words_for(Path("x.pdf"))
    assert (words, dims, src) == ([], {}, word_boxes.NONE)


def test_a_header_only_tsv_is_not_a_source(monkeypatch):
    """A text layer that exists but holds no level-5 row is the same as none:
    `pdftotext` emits the header for a scan too."""
    monkeypatch.setattr(word_boxes, "text_layer_tsv",
                        lambda *a, **k: _TSV.splitlines()[0] + "\n")
    assert word_boxes.words_for(Path("x.pdf"))[2] == word_boxes.NONE
    assert word_boxes.combined_tsv(Path("x.pdf")) == ("", word_boxes.NONE)


def test_combined_tsv_passes_the_tsv_through_unchanged(monkeypatch):
    monkeypatch.setattr(word_boxes, "text_layer_tsv", lambda *a, **k: _TSV)
    tsv, src = word_boxes.combined_tsv(Path("x.pdf"))
    assert src == word_boxes.TEXT_LAYER
    assert tsv == _TSV          # the page column is already the real page


def test_enriched_keeps_every_level(monkeypatch):
    monkeypatch.setattr(word_boxes, "text_layer_tsv", lambda *a, **k: _TSV)
    parsed, src = word_boxes.enriched_for(Path("x.pdf"))
    assert src == word_boxes.TEXT_LAYER
    assert len(parsed["words"]) == 2
    assert parsed["page_dims"][1] == (612.0, 792.0)


def test_the_note_names_a_lane_and_never_an_engine():
    note = word_boxes.no_words_note(Path("/tmp/scan.pdf"), what="word boxes")
    assert "scan.pdf" in note
    assert "gemmaocr" in note and "--geometry-only" in note and "route" in note
    assert "LINE boxes, not word boxes" in note
    for forbidden in ("tesseract", "apt ", "install"):
        assert forbidden not in note.lower()


# ---- the ink route: boxes, no text ----------------------------------------

def _page_png(tmp_path, rows=3, words_per_row=4):
    """A synthetic page of black word-blobs on white, drawn with PIL."""
    Image = pytest.importorskip("PIL.Image")
    from PIL import ImageDraw
    im = Image.new("L", (800, 400), 255)
    d = ImageDraw.Draw(im)
    for r in range(rows):
        y = 40 + r * 100
        x = 40
        for _w in range(words_per_row):
            d.rectangle([x, y, x + 90, y + 24], fill=0)      # a "word"
            x += 90 + 60                                     # a wide gap
    png = tmp_path / "page-0001.png"
    im.save(png)
    return png


def test_ink_words_finds_one_box_per_blob(tmp_path):
    pytest.importorskip("numpy")
    png = _page_png(tmp_path, rows=3, words_per_row=4)
    boxes = word_boxes.ink_words(png)
    assert len(boxes) == 12, boxes
    # reading order: top to bottom, then left to right
    tops = [b[1] for b in boxes]
    assert tops == sorted(tops)


def test_ink_words_splits_on_the_gap_and_not_inside_a_word(tmp_path):
    """The gap is a RATIO of the row's glyph height, so the same page at a
    different type size splits the same way. Below the ratio the blobs fuse."""
    pytest.importorskip("numpy")
    png = _page_png(tmp_path, rows=1, words_per_row=4)
    wide = word_boxes.ink_words(png, gap_ratio=0.35)
    fused = word_boxes.ink_words(png, gap_ratio=5.0)
    assert len(wide) == 4
    assert len(fused) == 1, "a gap ratio above the real gap must fuse the row"


def test_ink_words_carries_no_text_at_all(tmp_path):
    """The ink route returns BOXES. If it ever returned dicts with a `text`
    key, a consumer could believe a word was read when nothing read it."""
    pytest.importorskip("numpy")
    png = _page_png(tmp_path, rows=1, words_per_row=2)
    for box in word_boxes.ink_words(png):
        assert isinstance(box, tuple) and len(box) == 4
        assert all(isinstance(v, (int, float)) for v in box)
