"""
recto/verso page-side classification (src/pdfdrill/rectoverso.py): page-number
parity + page-number x-position + column-width asymmetry, fused by confidence-
weighted vote; sequence alternation as the post-pass. Pure tests on synthetic
MathPix-shaped pages.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import rectoverso as rv


def _line(text, x, y, w=60, h=30, **kw):
    d = {"text": text,
         "region": {"top_left_x": x, "top_left_y": y, "width": w, "height": h}}
    d.update(kw)
    return d


def _page(lines, w=1000, h=1400):
    return {"image_width": w, "image_height": h, "lines": lines}


def _body(n=6, x=120, w=600):
    return [_line(f"body line {i}", x, 300 + 60 * i, w=w) for i in range(n)]


# ---------------------------------------------------------------- signals
def test_odd_printed_number_is_recto():
    pg = _page([_line("17", 870, 30)] + _body())
    r = rv.classify_page(pg)
    assert r.side == "recto" and r.confidence > 0.5
    assert r.evidence["signals"]["number_parity"] == "recto"
    assert r.evidence["signals"]["number_position"] == "recto"  # right edge


def test_even_printed_number_left_edge_is_verso():
    pg = _page([_line("42", 60, 1360)] + _body(x=280))
    r = rv.classify_page(pg)
    assert r.side == "verso"
    assert r.evidence["signals"]["number_parity"] == "verso"
    assert r.evidence["signals"]["number_position"] == "verso"


def test_roman_numeral_parity_counts():
    # xii = 12 -> verso, even without an arabic number
    pg = _page([_line("xii", 80, 30)] + _body(x=280))
    r = rv.classify_page(pg)
    assert r.side == "verso"
    assert r.evidence["signals"]["number_parity"] == "verso"
    assert r.evidence.get("printed_number") == 12


def test_narrow_margin_column_right_means_recto():
    # wide body left + narrow side-note column right (no page number at all)
    lines = _body(x=100, w=600) + [
        _line("side note", 800, 350, w=140),
        _line("another note", 800, 600, w=130),
    ]
    r = rv.classify_page(_page(lines))
    assert r.side == "recto"
    assert r.evidence["signals"]["column_asymmetry"] == "recto"


def test_no_signals_abstains():
    r = rv.classify_page(_page(_body()))
    assert r.side is None and r.confidence == 0.0


def test_centered_number_position_abstains_parity_decides():
    pg = _page([_line("8", 480, 1360)] + _body())   # centered -> no position vote
    r = rv.classify_page(pg)
    assert r.side == "verso"
    assert "number_position" not in r.evidence["signals"]


# ---------------------------------------------------------------- sequence
def test_alternation_fills_weak_pages():
    pages = [
        _page([_line("17", 870, 30)] + _body()),        # recto, strong
        _page(_body()),                                  # unknown
        _page([_line("19", 880, 30)] + _body()),        # recto, strong
    ]
    raw = [rv.classify_page(p) for p in pages]
    assert raw[1].side is None
    fused = rv.apply_alternation(raw)
    assert [r.side for r in fused] == ["recto", "verso", "recto"]
    assert fused[1].evidence.get("signals", {}).get("alternation") == "verso"
    assert 0 < fused[1].confidence <= 1


def test_alternation_overrules_isolated_contradiction():
    # 4 strong pages in an alternating phase + 1 weak contradicting page
    pages = [
        _page([_line("11", 880, 30)] + _body()),        # recto
        _page([_line("12", 70, 30)] + _body(x=280)),    # verso
        _page(_body(x=100, w=600) + [                   # column says VERSO (narrow left)
            _line("note", 60, 350, w=120), _line("note2", 60, 600, w=110)]),
        _page([_line("14", 70, 30)] + _body(x=280)),    # verso
    ]
    raw = [rv.classify_page(p) for p in pages]
    fused = rv.apply_alternation(raw)
    # phase fits 11/12/14 => page 3 must be recto despite its weak column vote
    assert [r.side for r in fused] == ["recto", "verso", "recto", "verso"]


def test_alternation_abstains_without_anchors():
    # A slide deck has NO book layout: every per-page signal abstains, and the
    # alternation pass must NOT invent sides from an unanchored phase.
    raw = [rv.classify_page(_page(_body())) for _ in range(5)]
    assert all(r.side is None for r in raw)
    fused = rv.apply_alternation(raw)
    assert all(r.side is None for r in fused)


def test_classify_lines_json_roundtrip(tmp_path=None):
    import json, tempfile
    data = {"pages": [_page([_line("3", 880, 30)] + _body()),
                      _page([_line("4", 60, 30)] + _body(x=280))]}
    res = rv.classify_lines_json(data)
    assert [r.side for r in res] == ["recto", "verso"]
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.lines.json"
        p.write_text(json.dumps(data))
        res2 = rv.classify_lines_json(str(p))
        assert [r.side for r in res2] == ["recto", "verso"]


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
