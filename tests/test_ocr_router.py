"""
`ocr_router.choose_route` — THE LANE CONTRACT (docs/LANES.md). Five lanes in a
fixed order, each taken only because every cheaper one above it is unavailable:

    born_digital  the PDF's own text layer                       free
    source        no text layer, but an arXiv e-print            free
    gemma         a scan + MAKORA/NOVITA                         metered
    mathpix       a scan + MathPix only                          paid
    geometry      a scan + no reading key at all                 free

OCR IS THE LAST RESORT: the three OCR lanes are reached only when the document
has neither a text layer of its own nor an author's source. Page count does NOT
select a lane — the old ">20 pages means MathPix" threshold was set when the
alternative was a 50 s/page vision call.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import ocr_router as R

GEMMA = frozenset({R.GEMMA_KEY})
MPX = frozenset({R.MATHPIX_KEY})
BOTH = GEMMA | MPX


# --------------------------------------------------------------------------- #
#  1-2 — the free lanes, and that they come first
# --------------------------------------------------------------------------- #

def test_born_digital_wins_at_any_page_count():
    d = R.choose_route(text_layer=True, needs_ocr=False, page_count=800,
                       keys=BOTH)
    assert d.lane == "born_digital" and d.cost == "free"
    assert "model" in d.command


def test_born_digital_beats_both_keys():
    """A key present is not a reason to spend. The free lane is the lane."""
    for keys in (GEMMA, MPX, BOTH):
        assert R.choose_route(text_layer=True, needs_ocr=False, page_count=12,
                              keys=keys).lane == "born_digital"


def test_born_digital_on_arxiv_says_both_sources_merge():
    d = R.choose_route(text_layer=True, needs_ocr=False, page_count=9,
                       arxiv_source=True)
    assert d.lane == "born_digital" and d.cost == "free"
    assert "LaTeX" in d.reason and "merge" in d.reason


def test_scan_with_an_arxiv_source_is_not_an_ocr_document():
    """The author's LaTeX is gold and free, so OCR has nothing to add but
    geometry — even with both keys in hand and 400 pages to read."""
    d = R.choose_route(text_layer=False, needs_ocr=True, page_count=400,
                       arxiv_source=True, keys=BOTH)
    assert d.lane == "source" and d.cost == "free"
    assert "e-print" in d.reason


# --------------------------------------------------------------------------- #
#  3-5 — the OCR lanes, and the order among them
# --------------------------------------------------------------------------- #

def test_scan_with_a_gemma_key_is_metered_not_paid():
    d = R.choose_route(text_layer=False, needs_ocr=True, page_count=22,
                       keys=GEMMA)
    assert d.lane == "gemma" and d.cost == "metered"
    assert "gemmaocr" in d.command
    assert "PDFDRILL_OCR_BUDGET_EUR" in d.reason


def test_gemma_beats_mathpix_when_both_keys_are_present():
    """Measured on penev_A: 88% of MathPix's boxes at about a fortieth of the
    price. So MathPix is lane 4, not lane 3."""
    assert R.choose_route(text_layer=False, needs_ocr=True, page_count=22,
                          keys=BOTH).lane == "gemma"


def test_page_count_no_longer_selects_a_lane():
    """The stale rule. A 400-page scan and a 12-page scan take the SAME lane."""
    small = R.choose_route(text_layer=False, needs_ocr=True, page_count=12,
                           keys=GEMMA)
    large = R.choose_route(text_layer=False, needs_ocr=True, page_count=400,
                           keys=GEMMA)
    assert small.lane == large.lane == "gemma"
    for keys in (MPX, frozenset()):
        a = R.choose_route(text_layer=False, needs_ocr=True, page_count=12,
                           keys=keys)
        b = R.choose_route(text_layer=False, needs_ocr=True, page_count=400,
                           keys=keys)
        assert a.lane == b.lane


def test_scan_with_only_mathpix_is_the_paid_lane():
    d = R.choose_route(text_layer=False, needs_ocr=True, page_count=300,
                       keys=MPX)
    assert d.lane == "mathpix" and d.cost == "paid"
    assert "mathpix" in d.command


def test_keyless_scan_gets_the_free_geometry_lane():
    """The sandbox's default: no words for free, but the SHAPE is free."""
    d = R.choose_route(text_layer=False, needs_ocr=True, page_count=22,
                       keys=frozenset())
    assert d.lane == "geometry" and d.cost == "free"
    assert "--geometry-only" in d.command
    assert "STRUCTURE" in d.reason and "linescmp" in d.reason


def test_keyless_scan_with_no_detector_still_gets_the_ink(monkeypatch):
    """It used to answer "there is no free lane on this install", and then
    `drill` produced 355 boxed lines on hilbert10 in 6.6 s. Without the
    detector the ink still finds the lines; what is missing is their TYPE."""
    monkeypatch.setattr(R, "ink_available", lambda: True)
    d = R.choose_route(text_layer=False, needs_ocr=True, page_count=22,
                       keys=frozenset(), detector=False)
    assert d.lane == "geometry" and d.cost == "free"
    assert "NO type" in d.reason and "PDFDRILL_YOLO_PYTHON" in d.reason
    assert "no types" in d.command


def test_without_the_ink_either_there_really_is_no_free_lane(monkeypatch):
    monkeypatch.setattr(R, "ink_available", lambda: False)
    d = R.choose_route(text_layer=False, needs_ocr=True, page_count=22,
                       keys=frozenset(), detector=False)
    assert d.lane == "geometry" and d.cost == "none"
    assert "MAKORA_API_KEY" in d.command and "numpy" in d.command.lower()


# --------------------------------------------------------------------------- #
#  The OCR underlay, and the unclassified case
# --------------------------------------------------------------------------- #

def test_an_ocr_underlay_is_not_the_free_lane():
    """A text layer on full-page scans is somebody else's reading of the page.
    Serving it as 'free and exact' is the one thing this flag exists to stop."""
    d = R.choose_route(text_layer=True, needs_ocr=False, page_count=200,
                       scanned_images=True, keys=GEMMA)
    assert d.lane == "gemma"


def test_unclassified_asks_for_size_and_costs_nothing():
    d = R.choose_route(text_layer=None, needs_ocr=None, page_count=0)
    assert d.lane == "unknown" and d.cost == "none"
    assert "size" in d.command


# --------------------------------------------------------------------------- #
#  Defaults, and purity
# --------------------------------------------------------------------------- #

def test_every_optional_argument_defaults_to_assuming_least():
    """A caller that knows nothing is told to use a free lane, never to spend."""
    d = R.choose_route(text_layer=False, needs_ocr=True, page_count=10)
    assert d.lane == "geometry" and d.cost == "free"


def test_the_lane_order_is_the_contract():
    """LANES is the published order and the function must agree with it."""
    assert R.LANES == ("born_digital", "source", "gemma", "mathpix", "geometry")
    seen = [
        R.choose_route(text_layer=True, needs_ocr=False, page_count=5).lane,
        R.choose_route(text_layer=False, needs_ocr=True, page_count=5,
                       arxiv_source=True).lane,
        R.choose_route(text_layer=False, needs_ocr=True, page_count=5,
                       keys=GEMMA).lane,
        R.choose_route(text_layer=False, needs_ocr=True, page_count=5,
                       keys=MPX).lane,
        R.choose_route(text_layer=False, needs_ocr=True, page_count=5).lane,
    ]
    assert seen == list(R.LANES)


def test_every_decision_carries_a_known_cost():
    for keys in (frozenset(), GEMMA, MPX, BOTH):
        for tl, ocr, src in ((True, False, False), (False, True, True),
                             (False, True, False), (None, None, False)):
            d = R.choose_route(text_layer=tl, needs_ocr=ocr, page_count=7,
                               arxiv_source=src, keys=keys)
            assert d.cost in R.COSTS, (d.lane, d.cost)
            assert d.lane in R.LANES + ("unknown",)
            assert d.reason and d.command


def test_format_decision_is_readable():
    d = R.choose_route(text_layer=False, needs_ocr=True, page_count=12,
                       keys=GEMMA)
    line = R.format_decision(d, "scan.pdf")
    assert "scan.pdf" in line and "gemmaocr" in line and "→" in line


# --------------------------------------------------------------------------- #
#  keys_present — the one impure helper, and the sandbox switch
# --------------------------------------------------------------------------- #

def test_keys_present_is_empty_under_the_sandbox(monkeypatch):
    monkeypatch.setenv("MATHPIX_APP_ID", "x")
    monkeypatch.setenv("MATHPIX_APP_KEY", "y")
    monkeypatch.setenv("MAKORA_API_KEY", "z")
    assert R.keys_present() == {R.MATHPIX_KEY, R.GEMMA_KEY}
    monkeypatch.setenv("PDFDRILL_SANDBOX", "1")
    assert R.keys_present() == frozenset()


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        if "monkeypatch" in t.__code__.co_varnames:
            continue
        try:
            t(); print(f"PASS {name}")
        except AssertionError as e:
            failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e:
            failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
