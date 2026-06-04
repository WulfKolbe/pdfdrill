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


def classify_image_file(path, k: int = 3) -> list[tuple[str, float]]:
    import numpy as np
    from PIL import Image
    return classify_crop(np.array(Image.open(path).convert("RGB")), k)
