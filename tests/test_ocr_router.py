"""
ocr_router.choose_route — the automatic OCR-lane selector (the user's decision
model): born-digital → pdfminer/text-layer (free); scanned & small → Gemma 4
(≤20 pages, 5-parallel adaptive); scanned & large → MathPix (the only option for
large books). The state machine picks and REPORTS — nothing silent.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import ocr_router as R


def test_born_digital_goes_pdfminer_free():
    d = R.choose_route(text_layer=True, needs_ocr=False, page_count=800)
    assert d.lane == "born_digital" and d.cost == "free"
    # born-digital wins even for a huge book (text layer beats page count)
    assert "pdfminer" in d.command.lower() or "text" in d.command.lower()


def test_scanned_small_goes_gemma():
    d = R.choose_route(text_layer=False, needs_ocr=True, page_count=12)
    assert d.lane == "gemma" and d.cost == "keyed"
    assert "12" in d.reason and "20" in d.reason
    assert "gemma" in d.command.lower()


def test_scanned_at_cutoff_is_gemma():
    assert R.choose_route(text_layer=False, needs_ocr=True, page_count=20).lane == "gemma"


def test_scanned_large_goes_mathpix():
    d = R.choose_route(text_layer=False, needs_ocr=True, page_count=21)
    assert d.lane == "mathpix" and d.cost == "paid"
    assert "mathpix" in d.command.lower()


def test_scanned_unknown_pagecount_defaults_mathpix():
    # a scan whose page count is unknown (size not run / 0) → MathPix, the safe
    # choice for a possibly-large book, and the reason says so.
    d = R.choose_route(text_layer=False, needs_ocr=True, page_count=0)
    assert d.lane == "mathpix"
    assert "unknown" in d.reason.lower() or "assum" in d.reason.lower()


def test_unknown_when_unclassified():
    d = R.choose_route(text_layer=None, needs_ocr=None, page_count=0)
    assert d.lane == "unknown"
    assert "size" in d.command.lower()


def test_configurable_cutoff():
    assert R.choose_route(text_layer=False, needs_ocr=True, page_count=40,
                          gemma_max=50).lane == "gemma"


def test_format_decision_is_readable():
    d = R.choose_route(text_layer=False, needs_ocr=True, page_count=12)
    line = R.format_decision(d, "scan.pdf")
    assert "scan.pdf" in line and "Gemma" in line and "→" in line


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try:
            t(); print(f"PASS {name}")
        except AssertionError as e:
            failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e:
            failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
