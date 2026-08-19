"""Figure/table captions must not ride the tail of, or swallow, a paragraph.

Live defect (1206.0238 p3, user 2026-08-19): MathPix types the caption as
plain `text` with CONTINUOUS line numbering into the next paragraph (its
figure_label lines are empty), and MathPix lines carry no block_num/par_num —
so ParagraphProcessor's only group split never fired and 'Figure 1. …' merged
with 'Although in the algorithm …' into one 864-char unit.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _line(y, text, h=36):
    return {"type": "text", "text": text, "line": 1, "column": 1,
            "font_size": 29, "region": {"top_left_x": 100, "top_left_y": y,
                                        "width": 800, "height": h},
            "cnt": [[100, y], [900, y], [900, y + h], [100, y + h]]}


def test_caption_splits_from_surrounding_prose(tmp_path):
    lines = [
        _line(100, "Some prose before the figure, first line."),
        _line(139, "and its second line."),
        # caption starts here — same type, continuous flow, no break line
        _line(819, "Figure 1. An example of the celled projection."),
        _line(858, "It is noticeable that both are similar."),
        # body resumes after a LARGER vertical gap (81 vs ~39 pitch)
        _line(939, "Although in the algorithm we consider the input"),
        _line(978, "image to be binarized, grayscale also works."),
    ]
    lj = tmp_path / "doc.lines.json"
    lj.write_text(json.dumps(
        {"pages": [{"page": 1, "page_width": 2000, "page_height": 3000,
                    "image_id": "t-1", "lines": lines}]}))
    from docmodel.main import run as build_model, DEFAULT_CONFIG_PATH
    out = tmp_path / "model.json"
    build_model(lines_path=str(lj), config_path=DEFAULT_CONFIG_PATH,
                bibkey="k", out_path=str(out), debug_modules=[])
    m = json.loads(out.read_text())
    paras = [o for o in m["objects"] if o["type"] == "Paragraph"]
    texts = [o["props"]["text"] for o in paras]
    caps = [o for o in paras if o["props"].get("kind") == "caption"]
    assert len(caps) == 1, texts
    assert caps[0]["props"]["text"].startswith("Figure 1.")
    assert "Although" not in caps[0]["props"]["text"]     # caption ends at gap
    assert any(t.startswith("Although") for t in texts)   # body is its own unit
    assert any("prose before the figure" in t and "Figure 1." not in t
               for t in texts)                            # caption not merged up
