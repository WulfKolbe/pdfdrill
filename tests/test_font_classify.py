"""
Image-based font identification (pdfdrill.font_classify) — torch-free ONNX, for
SCANNED/OCR input where the PDF font layer is empty. Tests the pure pieces
(tools/availability, vote aggregation, preprocess shape); the model inference
itself is exercised only when the ~61 MB model is cached (skipped otherwise).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import font_classify as fc


def test_tools_available_reports_missing_clearly():
    ok, msg = fc.tools_available()
    # all of onnxruntime/cv2/yaml/numpy/PIL are present in this env
    assert ok or "fontid" in msg


def test_aggregate_votes_and_confidence():
    preds = [("Roboto-Regular", 0.9), ("Roboto-Regular", 0.7),
             ("Lato-Regular", 0.6), ("Roboto-Regular", 0.8)]
    a = fc.aggregate(preds)
    assert a["font"] == "Roboto-Regular" and a["votes"] == 3 and a["total"] == 4
    assert a["agreement"] == 0.75 and 0.79 <= a["mean_conf"] <= 0.81
    assert fc.aggregate([]) is None


def test_preprocess_shape_when_model_present():
    import numpy as np
    if not fc.available():
        print("SKIP (model not cached)"); return
    img = (np.random.rand(40, 300, 3) * 255).astype("uint8")
    t = fc.preprocess(img)
    assert t.shape == (1, 3, fc._cfg["size"], fc._cfg["size"])
    assert t.dtype.name == "float32"


def test_classify_returns_topk_when_model_present():
    import numpy as np
    if not fc.available():
        print("SKIP (model not cached)"); return
    img = (np.ones((60, 400, 3)) * 255).astype("uint8")  # blank → some prediction, low conf
    pred = fc.classify_crop(img, k=3)
    assert len(pred) == 3 and all(isinstance(n, str) and 0 <= p <= 1 for n, p in pred)


def test_field_fonts_one_font_per_text_field():
    # font is a property of each TEXT FIELD (OCR block), not one document vote:
    # a heading block and a body block must come back as separate fields with
    # their OWN fonts — never collapsed to a single dominant.
    classified = [
        ({"page": 1, "block": 1, "text": "Rechnung"}, ("Roboto-Bold", 0.92)),
        ({"page": 1, "block": 1, "text": "Energie"},  ("Roboto-Bold", 0.81)),
        ({"page": 1, "block": 2, "text": "Sehr"},     ("Lora-Regular", 0.74)),
        ({"page": 1, "block": 2, "text": "geehrte"},  ("Lora-Regular", 0.66)),
        ({"page": 1, "block": 2, "text": "Damen"},    ("Roboto-Bold", 0.51)),
    ]
    fields = fc.field_fonts(classified)
    assert len(fields) == 2                                   # two fields, not one vote
    assert fields[0]["block"] == 1 and fields[0]["font"] == "Roboto-Bold"
    assert fields[0]["total"] == 2
    assert fields[1]["font"] == "Lora-Regular" and fields[1]["votes"] == 2
    assert fields[1]["total"] == 3                            # within-field majority
    assert "Sehr" in fields[1]["sample"]                      # field carries its own text
    assert {f["font"] for f in fields} == {"Roboto-Bold", "Lora-Regular"}


def test_field_fonts_empty_is_empty():
    assert fc.field_fonts([]) == []


def test_category_of_maps_known_fonts():
    # the bundled font_categories.json maps Google-Fonts classnames to a category;
    # the category is the ROBUST signal on out-of-class scanned text.
    assert fc.category_of("Roboto-Bold") == "sans-serif"
    assert fc.category_of("Lora[wght]") == "serif"
    assert fc.category_of("FiraCode[wght]") == "monospace"
    assert fc.category_of("NoSuchFont-Regular") is None


def test_field_fonts_votes_a_robust_category():
    # exact faces disagree (every word a different Google font) but all are
    # sans-serif — so the CATEGORY vote is unanimous where the exact-face vote
    # is 1/3. This is what makes fontid useful on scanned standard-font docs.
    classified = [
        ({"page": 1, "block": 7, "text": "Abrechnung"},  ("Varta[wght]", 0.58)),
        ({"page": 1, "block": 7, "text": "Konzession"},  ("Athiti-Medium", 0.50)),
        ({"page": 1, "block": 7, "text": "Einzelpreis"}, ("Roboto-Light", 0.40)),
    ]
    f = fc.field_fonts(classified)[0]
    assert f["category"] == "sans-serif"
    assert f["cat_votes"] == 3 and f["cat_total"] == 3      # unanimous category
    assert f["agreement"] < f["cat_agreement"]              # category beats exact face


def test_format_report_has_stats_and_per_field():
    fields = [
        {"page": 1, "block": 5, "font": "ZenMaruGothic-Black", "votes": 1, "total": 1,
         "mean_conf": 0.35, "agreement": 1.0, "category": "sans-serif",
         "cat_votes": 1, "cat_total": 1, "cat_agreement": 1.0, "sample": "einfach"},
        {"page": 1, "block": 6, "font": "SplineSans[wght]", "votes": 1, "total": 4,
         "mean_conf": 0.42, "agreement": 0.25, "category": "sans-serif",
         "cat_votes": 3, "cat_total": 3, "cat_agreement": 1.0, "sample": "Erlaeuterungen"},
        {"page": 2, "block": 9, "font": "PostNoBillsJaffna-SemiBold", "votes": 1, "total": 2,
         "mean_conf": 0.31, "agreement": 0.5, "category": None,
         "cat_votes": 0, "cat_total": 0, "cat_agreement": 0.0, "sample": "Energie"},
    ]
    r = fc.format_report("allocr.pdf", fields, n_words=8)
    assert "allocr.pdf" in r
    assert "predominantly sans-serif" in r          # 2 of 3 fields sans
    assert "Fields: 3" in r and "Pages: 2" in r
    assert "Words classified: 8" in r
    assert "Distinct faces: 3" in r
    assert "67%" in r and "33%" in r                # category distribution percentages
    assert "uncertain" in r                         # the unresolved field is shown
    assert "mean" in r and "max" in r               # confidence statistics
    assert "field  5" in r and "ZenMaruGothic-Black" in r
    assert fc.format_report("x.pdf", []) == "FONTID: no classifiable text fields."


if __name__ == "__main__":
    for fn in (test_tools_available_reports_missing_clearly, test_aggregate_votes_and_confidence,
               test_preprocess_shape_when_model_present, test_classify_returns_topk_when_model_present,
               test_field_fonts_one_font_per_text_field, test_field_fonts_empty_is_empty,
               test_category_of_maps_known_fonts, test_field_fonts_votes_a_robust_category,
               test_format_report_has_stats_and_per_field):
        fn(); print("PASS", fn.__name__)
    print("\nAll tests passed.")
