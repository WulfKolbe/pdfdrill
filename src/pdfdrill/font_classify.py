"""
font_classify — torch-free image-based font identification for SCANNED/OCR input.

A scanned PDF has no font layer, so `fonts`/`fonts_layer` (pdffonts) return
nothing. This recovers a font *visually*: render clean text-line crops and
classify them with the storia/font-classify ONNX model (3473 Google-Fonts
classes), CPU-only, using ONLY libraries already common in the sandbox —
onnxruntime + numpy + cv2 + PIL + yaml (NO torch / timm / huggingface_hub). The
training stack in the model repo's requirements is a red herring for inference;
the three preprocessing ops (CutMax crop, ResizeWithPad, Normalize) are pure
numpy/cv2 and reimplemented here.

Model (~61 MB) + config are fetched on demand to a cache dir
($FONT_CLASSIFY_DIR or ~/.cache/pdfdrill/fontclassify) via net.urlopen (graceful
when the host is blocked). Caveat: Google Fonts only — classic LaTeX faces
(Computer/Latin Modern) are absent and land on a Times-ish neighbour (Tinos/
STIX); commercial/scanned faces (Roboto/Lato/Arial-metric clones) classify well.
Best on clean single-line crops, not whole pages.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Optional

_BASE = "https://huggingface.co/storia/font-classify-onnx/resolve/main"
_FILES = ("model.onnx", "model_config.yaml")
_MEAN = (0.485, 0.456, 0.406)
_STD = (0.229, 0.224, 0.225)

_session = None
_cfg: Optional[dict] = None
_input_name: Optional[str] = None


def cache_dir() -> Path:
    return Path(os.environ.get("FONT_CLASSIFY_DIR")
               or (Path.home() / ".cache" / "pdfdrill" / "fontclassify"))


def tools_available() -> tuple[bool, str]:
    for mod in ("onnxruntime", "cv2", "yaml", "numpy", "PIL"):
        if importlib.util.find_spec(mod) is None:
            return False, (f"font-classify needs {mod}. Install the [fontid] extra: "
                           f"`pip install 'pdfdrill[fontid]'` (onnxruntime + opencv + pyyaml).")
    return True, ""


def ensure_model(download: bool = True) -> Optional[Path]:
    """Return the cache dir with model.onnx + model_config.yaml, fetching them on
    demand. Returns None when unavailable (offline + not cached)."""
    d = cache_dir()
    if all((d / f).exists() and (d / f).stat().st_size > 0 for f in _FILES):
        return d
    if not download:
        return None
    d.mkdir(parents=True, exist_ok=True)
    from . import net
    for f in _FILES:
        if (d / f).exists() and (d / f).stat().st_size > 0:
            continue
        try:
            data = net.urlopen(f"{_BASE}/{f}", timeout=120, host="huggingface.co").read()
            (d / f).write_bytes(data)
        except Exception:
            return None
    return d if all((d / f).exists() for f in _FILES) else None


def _load() -> bool:
    global _session, _cfg, _input_name
    if _session is not None:
        return True
    ok, _ = tools_available()
    if not ok:
        return False
    d = ensure_model()
    if d is None:
        return False
    import onnxruntime as ort
    import yaml
    with open(d / "model_config.yaml", encoding="utf-8") as f:
        _cfg = yaml.safe_load(f)
    _session = ort.InferenceSession(str(d / "model.onnx"), providers=["CPUExecutionProvider"])
    _input_name = _session.get_inputs()[0].name
    return True


def available() -> bool:
    return _load()


def preprocess(img_rgb):
    """uint8 HxWx3 RGB → model input tensor (CutMax 1024 → ResizeWithPad size →
    Normalize → NCHW float32)."""
    import cv2
    import numpy as np
    size = _cfg["size"]
    img = img_rgb[:1024, :1024, :]
    h, w = img.shape[:2]
    r = size / max(w, h)
    nw, nh = max(1, int(w * r)), max(1, int(h * r))
    img = cv2.resize(img, (nw, nh))
    dw, dh = size - nw, size - nh
    img = cv2.copyMakeBorder(img, dh // 2, dh - dh // 2, dw // 2, dw - dw // 2,
                             cv2.BORDER_CONSTANT, value=(255, 255, 255))
    mean = np.array(_MEAN, np.float32)
    std = np.array(_STD, np.float32)
    img = (img.astype(np.float32) / 255.0 - mean) / std
    return np.expand_dims(np.transpose(img, (2, 0, 1)), 0).astype(np.float32)


def classify_crop(img_rgb, k: int = 3) -> list[tuple[str, float]]:
    """Top-k (font_name, probability) for a single text-line crop (RGB ndarray)."""
    import numpy as np
    if not _load():
        return []
    logits = _session.run(None, {_input_name: preprocess(img_rgb)})[0][0]
    e = np.exp(logits - logits.max())
    p = e / e.sum()
    idx = p.argsort()[::-1][:k]
    return [(_cfg["classnames"][int(i)], float(p[int(i)])) for i in idx]


def aggregate(top1s: list[tuple[str, float]]) -> Optional[dict]:
    """Vote across many line-crop top-1 predictions → the dominant font, its vote
    share and mean confidence. Voting + confidence is how we stay honest on a
    Google-Fonts-only model over noisy scans: low agreement / low confidence = a
    weak guess, not a fact."""
    from collections import Counter
    top1s = [(f, c) for f, c in top1s if f]
    if not top1s:
        return None
    votes = Counter(f for f, _ in top1s)
    font, n = votes.most_common(1)[0]
    confs = [c for f, c in top1s if f == font]
    return {"font": font, "votes": n, "total": len(top1s),
            "mean_conf": round(sum(confs) / len(confs), 3),
            "agreement": round(n / len(top1s), 3)}


_CATEGORIES: Optional[dict] = None


def category_of(font_name: str) -> Optional[str]:
    """Map a Google-Fonts classname to its font category (sans-serif / serif /
    monospace / handwriting / display) from the bundled font_categories.json, or
    None if unresolved. The category is the ROBUST signal on out-of-class scanned
    text: the exact face may be wrong, but a sans-serif scan's top guesses are all
    sans-serif. Table built by tools/build_font_categories.py (committed)."""
    global _CATEGORIES
    if _CATEGORIES is None:
        import json
        path = Path(__file__).with_name("font_categories.json")
        try:
            _CATEGORIES = json.loads(path.read_text())
        except Exception:
            _CATEGORIES = {}
    return _CATEGORIES.get(font_name)


def field_fonts(classified, page_key: str = "page", block_key: str = "block") -> list[dict]:
    """Font as a property of each TEXT FIELD, not one document-level vote.

    `classified` is a list of `(word_meta, (font, conf))` where `word_meta` is the
    word's tesseract dict (page/block/line/bbox/text). Words are grouped by their
    OCR field — `(page, block)` — and voted WITHIN the field, so a heading block
    and a body block surface as separate fields each carrying their own font.
    Returns one dict per field (first-seen order) with the field's font, vote
    share, mean confidence, bbox, and a text sample. Empty input → []."""
    from collections import OrderedDict
    groups: "OrderedDict[tuple, list]" = OrderedDict()
    for w, pred in classified:
        groups.setdefault((w.get(page_key), w.get(block_key)), []).append((w, pred))
    from collections import Counter
    out: list[dict] = []
    for (page, block), items in groups.items():
        agg = aggregate([p for _, p in items])
        if agg is None:
            continue
        ws = [w for w, _ in items]
        xs0 = [w["x0"] for w in ws if "x0" in w]; ys0 = [w["y0"] for w in ws if "y0" in w]
        xs1 = [w["x1"] for w in ws if "x1" in w]; ys1 = [w["y1"] for w in ws if "y1" in w]
        bbox = ([min(xs0), min(ys0), max(xs1), max(ys1)]
                if xs0 and ys0 and xs1 and ys1 else None)
        sample = " ".join(w.get("text", "") for w in ws).strip()[:48]
        # category vote: each word's top-1 font → its category; the majority
        # category is robust even when the exact faces disagree.
        cats = [c for c in (category_of(pred[0]) for _, pred in items) if c]
        if cats:
            cvotes = Counter(cats)
            cat, cn = cvotes.most_common(1)[0]
            category, cat_votes, cat_total = cat, cn, len(cats)
            cat_agreement = round(cn / len(cats), 3)
        else:
            category, cat_votes, cat_total, cat_agreement = None, 0, 0, 0.0
        out.append({"page": page, "block": block, "font": agg["font"],
                    "votes": agg["votes"], "total": agg["total"],
                    "mean_conf": agg["mean_conf"], "agreement": agg["agreement"],
                    "category": category, "cat_votes": cat_votes,
                    "cat_total": cat_total, "cat_agreement": cat_agreement,
                    "bbox": bbox, "sample": sample})
    return out


def format_report(name: str, fields: list[dict], n_words: Optional[int] = None) -> str:
    """A human-readable fontid report with summary statistics + a per-field table,
    written to `.drill/fontid/fontid.txt`. Leads with the document category verdict
    (the robust signal), then category distribution, confidence stats, and one line
    per text field. Pure (no I/O) so it is unit-tested directly."""
    from collections import Counter
    if not fields:
        return "FONTID: no classifiable text fields."
    n = len(fields)
    pages = sorted(set(f["page"] for f in fields))
    distinct = len(set(f["font"] for f in fields))
    cat_counts = Counter((f["category"] or "uncertain") for f in fields)
    resolved = Counter(f["category"] for f in fields if f["category"])
    confs = [f["mean_conf"] for f in fields]
    cagrs = [f["cat_agreement"] for f in fields]
    hi = sum(1 for f in fields if f["category"] and f["cat_agreement"] >= 0.5)
    verdict = (f"predominantly {resolved.most_common(1)[0][0]}"
               if resolved else "category uncertain (faces out of the class set)")

    head = f"FONTID REPORT — {name}"
    L = [head, "=" * len(head),
         "VISUAL estimate — the PDF has no font layer. The exact Google-Fonts face is",
         "a low-confidence guess (Arial/Helvetica/Computer-Modern aren't classes); the",
         "CATEGORY vote is the robust signal.", "",
         f"Document verdict:    {verdict}",
         f"Fields: {n}   Pages: {len(pages)}"
         + (f"   Words classified: {n_words}" if n_words is not None else "")
         + f"   Distinct faces: {distinct}",
         "",
         "Category distribution (share of fields):"]
    for c, k in cat_counts.most_common():
        bar = "#" * round(20 * k / n)
        L.append(f"  {c:12} {k:3}  ({k / n:.0%})  {bar}")
    mc = sum(confs) / n
    L += ["",
          "Statistics (face confidence is weak by design — judge by category agreement):",
          f"  face confidence:     mean {mc:.2f}   min {min(confs):.2f}   max {max(confs):.2f}",
          f"  category agreement:  mean {sum(cagrs) / n:.2f}   "
          f"fields with high (>=0.5) agreement: {hi}/{n}",
          f"  resolved categories: {len([f for f in fields if f['category']])}/{n} fields",
          "",
          "Per field (page · block · category · face guess · sample):"]
    for f in fields:
        cat = f["category"] or "uncertain"
        flag = "" if (f["category"] and f["cat_agreement"] >= 0.5) else "  <weak>"
        L.append(f"  p{f['page']} field {f['block']:>2}  {cat:11} "
                 f"({f['cat_votes']}/{f['cat_total']}, agr {f['cat_agreement']:.2f})  "
                 f"face≈{f['font']} (conf {f['mean_conf']:.2f})  {f['sample']!r}{flag}")
    return "\n".join(L)


def classify_image_file(path, k: int = 3) -> list[tuple[str, float]]:
    import numpy as np
    from PIL import Image
    return classify_crop(np.array(Image.open(path).convert("RGB")), k)
