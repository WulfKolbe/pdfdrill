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


if __name__ == "__main__":
    for fn in (test_tools_available_reports_missing_clearly, test_aggregate_votes_and_confidence,
               test_preprocess_shape_when_model_present, test_classify_returns_topk_when_model_present):
        fn(); print("PASS", fn.__name__)
    print("\nAll tests passed.")
