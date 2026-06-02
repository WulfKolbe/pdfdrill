"""MathPix Snip client — OCR a single image via POST /v3/text.

Unlike /v3/pdf (which produces a separate lines.json file), the image
endpoint embeds the structured per-line data in its JSON response when
`include_line_data` is set. We use it as a competing "snip" provenance for
individual equation crops: it returns LaTeX (in `latex_styled` / a `data`
entry of type `latex`, or inside the Mathpix-Markdown `text`) plus a per-line
`confidence` we can later use as a quality score.

`src` may be:
  - a local image path  -> encoded as a base64 `data:` URI,
  - an http(s) image URL -> passed through (e.g. a cdn.mathpix.com crop),
  - an already-formed `data:` URI -> passed through.

Credentials are resolved by the shared helper in `mathpix_client`
(env first: MATHPIX_APP_ID / MATHPIX_APP_KEY, then a git-ignored
`mathpix_creds.py`), so nothing sensitive lives here.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import sys
import urllib.error
import urllib.request

from . import net
from typing import Any, Iterable, Optional

from .mathpix_client import API_BASE, _auth_headers

TEXT_ENDPOINT = f"{API_BASE}/text"


# ---------------------------------------------------------------------------
# src construction
# ---------------------------------------------------------------------------

def _is_url(src: str) -> bool:
    return src.startswith("http://") or src.startswith("https://")


def _is_datauri(src: str) -> bool:
    return src.startswith("data:")


def to_src(image: str) -> str:
    """Turn a local path into a base64 `data:` URI; pass URLs / data-URIs through."""
    if _is_url(image) or _is_datauri(image):
        return image
    ctype = mimetypes.guess_type(image)[0] or "image/png"
    with open(image, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{ctype};base64,{b64}"


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def build_payload(
    image: str,
    formats: Iterable[str] = ("text", "data"),
    include_line_data: bool = True,
    math_inline_delimiters: Iterable[str] = ("$", "$"),
    rm_spaces: bool = True,
    is_async: bool = False,
    extra: Optional[dict] = None,
) -> dict:
    """Assemble the JSON body for POST /v3/text (pure, network-free)."""
    formats = list(formats)
    payload: dict[str, Any] = {
        "src": to_src(image),
        "formats": formats,
        "math_inline_delimiters": list(math_inline_delimiters),
        "rm_spaces": rm_spaces,
    }
    if include_line_data:
        payload["include_line_data"] = True
    if "data" in formats:
        payload["data_options"] = {"include_latex": True}
    if is_async:
        payload["is_async"] = True
    if extra:
        payload.update(extra)
    return payload


def snip(image: str, timeout: float = 120.0, **kwargs) -> dict:
    """OCR one image via /v3/text and return the raw JSON response."""
    payload = build_payload(image, **kwargs)
    req = urllib.request.Request(
        TEXT_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={**_auth_headers(), "Content-Type": "application/json"},
    )
    try:
        with net.urlopen(req, timeout=timeout, host="api.mathpix.com") as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"MathPix /v3/text failed: HTTP {e.code} {e.reason}") from e
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"MathPix /v3/text error: {data.get('error')}")
    return data


# ---------------------------------------------------------------------------
# Response extraction
# ---------------------------------------------------------------------------

_DELIMS = (("\\[", "\\]"), ("\\(", "\\)"), ("$$", "$$"), ("$", "$"))


def _strip_delims(s: str) -> str:
    s = s.strip()
    for left, right in _DELIMS:
        if s.startswith(left) and s.endswith(right) and len(s) >= len(left) + len(right):
            return s[len(left):-len(right)].strip()
    return s


def best_latex(response: dict) -> str:
    """Best available LaTeX: latex_styled, then a data[].latex, then stripped text."""
    ls = response.get("latex_styled")
    if ls:
        return ls.strip()
    for d in response.get("data", []) or []:
        if d.get("type") == "latex" and d.get("value"):
            return d["value"].strip()
    return _strip_delims(response.get("text", "") or "")


def line_candidates(response: dict) -> list[dict]:
    """Flatten the `line_data` array into compact per-line records."""
    out: list[dict] = []
    for ld in response.get("line_data", []) or []:
        out.append({
            "type": ld.get("type"),
            "text": ld.get("text"),
            "confidence": ld.get("confidence"),
            "confidence_rate": ld.get("confidence_rate"),
            "included": ld.get("included"),
            "is_printed": ld.get("is_printed"),
            "is_handwritten": ld.get("is_handwritten"),
            "cnt": ld.get("cnt"),
        })
    return out


def snip_result(image: str, **kwargs) -> dict:
    """High-level: OCR an image, return a compact 'snip' provenance record."""
    resp = snip(image, **kwargs)
    lines = line_candidates(resp)
    # Top-level confidence if present, else the max line confidence.
    conf = resp.get("confidence")
    if conf is None and lines:
        confs = [l["confidence"] for l in lines if l.get("confidence") is not None]
        conf = max(confs) if confs else None
    return {
        "provenance": "snip",
        "latex": best_latex(resp),
        "text": resp.get("text", ""),
        "confidence": conf,
        "lines": lines,
    }


def main(argv: Optional[list[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("Usage: python -m pdfdrill.mathpix_snip <image-path-or-url>", file=sys.stderr)
        return 1
    try:
        r = snip_result(argv[0])
        print("latex:", r["latex"])
        if r["confidence"] is not None:
            print("confidence:", r["confidence"])
        print(f"({len(r['lines'])} line(s))")
        return 0
    except Exception as e:  # noqa: BLE001 — top-level CLI guard
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
