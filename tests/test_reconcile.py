"""
reconcile — parallel MathPix + pdfminer.six dual-route reconciliation.
P3 math-garble QC (over the pdfminer LaTeX, fixtures VERBATIM from 2607.02234's
lines.json): char-spacing (`_{O P S D}`), prose↔math interleave, truncation
(unbalanced braces). P1 region matching (page-fraction IoU across the two
coordinate systems, comparison-only). Pure/offline.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import reconcile as R


def test_char_spaced_detected():
    assert R.is_char_spaced(r"\mathcal{L}_{O P S D}=D_{J S D}(\pi_{\theta}).")
    assert R.is_char_spaced(r"\Delta_{i t}=l o g \pi_{T}-l o g \pi_{r e f}")
    # a clean equation with normal single-char sub/superscripts is NOT flagged
    assert not R.is_char_spaced(r"P_{0}(v)=\pi_{0}(v \mid \hat{y}_{<t},q)")
    assert not R.is_char_spaced(r"x^2 + y^2 = z^2")


def test_truncation_detected():
    assert R.is_truncated(r"e n \mathcal{L}c e_{o}\parallel^{f}:P_{P M I}),P_{P M I")
    assert R.is_truncated(r"\frac{1}{2")               # unbalanced brace
    assert not R.is_truncated(r"\frac{1}{2}")
    assert not R.is_truncated(r"P_{0}(v)=\pi_{0}(v)")


def test_math_qc_verdict():
    clean = R.math_qc(r"P_{0}(v)=\pi_{0}(v \mid \hat{y}_{<t},q)")
    assert clean["garbled"] is False
    garbled = R.math_qc(
        r"e n \mathcal{L}c e_{o}-_{u}o_{r s}n l=y t D e a_{J}c_{S}h_{D}e(r")
    assert garbled["garbled"] is True
    assert garbled["char_spaced"] is True


def test_page_fraction_and_iou():
    # pdfminer points (page 442x663) vs MathPix pixels (page 1000x1500): the SAME
    # region normalizes to the SAME [0,1] box → IoU ~ 1.
    pm = R.to_page_fraction({"top_left_x": 44.2, "top_left_y": 66.3,
                             "width": 88.4, "height": 13.3}, 442.0, 663.0)
    # same [0,1] box: 100/1000=0.1, 150/1500=0.1, w 200/1000=0.2, h 30/1500=0.02
    mp = R.to_page_fraction({"top_left_x": 100, "top_left_y": 150,
                             "width": 200, "height": 30}, 1000.0, 1500.0)
    assert R.iou(pm, mp) > 0.9
    # a disjoint region → IoU 0
    far = R.to_page_fraction({"top_left_x": 800, "top_left_y": 1400,
                              "width": 100, "height": 30}, 1000.0, 1500.0)
    assert R.iou(pm, far) == 0.0


def test_match_equations_by_region():
    # two pdfminer eqs, two mathpix eqs on the same page → best-IoU pairing
    pm = [{"id": "pm1", "page": 1, "region": {"top_left_x": 100, "top_left_y": 100,
            "width": 200, "height": 20}},
          {"id": "pm2", "page": 1, "region": {"top_left_x": 100, "top_left_y": 400,
            "width": 200, "height": 20}}]
    mp = [{"latex": "A=B", "page": 1, "region": {"top_left_x": 102, "top_left_y": 101,
            "width": 198, "height": 20}},
          {"latex": "C=D", "page": 1, "region": {"top_left_x": 101, "top_left_y": 402,
            "width": 199, "height": 20}}]
    pages = {1: (500.0, 700.0)}                        # same page dims both sides here
    pairs = R.match_equations(pm, mp, pages, pages)
    got = {p[0]["id"]: p[1]["latex"] for p in pairs}
    assert got == {"pm1": "A=B", "pm2": "C=D"}


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try: t(); print(f"PASS {name}")
        except AssertionError as e: failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e: failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed: print(f"\n{len(failed)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} passed.")


def test_plan_adoptions_replaces_garbled_with_mathpix():
    """P2: a region-matched pair whose pdfminer math is garbled adopts MathPix's
    clean LaTeX; the clean one is still matched (recorded, not garbled)."""
    pm = [{"id": "pm1", "page": 1, "latex": r"\mathcal{L}_{O P S D}=D_{J S D}(x)",
           "region": {"top_left_x": 100, "top_left_y": 100, "width": 200, "height": 20}},
          {"id": "pm2", "page": 1, "latex": r"P_{0}(v)=\pi_{0}(v)",
           "region": {"top_left_x": 100, "top_left_y": 400, "width": 200, "height": 20}}]
    mp = [{"latex": r"\mathcal{L}_{\mathrm{OPSD}}=D_{\mathrm{JSD}}(x)", "page": 1,
           "region": {"top_left_x": 100, "top_left_y": 100, "width": 200, "height": 20}},
          {"latex": r"P_0(v)=\pi_0(v)", "page": 1,
           "region": {"top_left_x": 100, "top_left_y": 400, "width": 200, "height": 20}}]
    pages = {1: (500.0, 700.0)}
    ad = {a["pm_id"]: a for a in R.plan_adoptions(pm, mp, pages, pages)}
    assert ad["pm1"]["was_garbled"] is True
    assert "OPSD" in ad["pm1"]["mathpix_latex"] and " " not in ad["pm1"]["mathpix_latex"].split("{")[1][:5]
    assert ad["pm2"]["was_garbled"] is False        # clean, still matched
