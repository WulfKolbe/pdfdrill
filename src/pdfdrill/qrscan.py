"""
QR / barcode scanning for PDFs — confirmation data outside the text layer.

Commercial documents carry QR codes (GiroCode/EPC SEPA payment), Data Matrix
franking/routing marks, and barcodes. These are CONFIRMATION the OCR text can't
give: a GiroCode independently encodes the creditor name, IBAN, amount and
payment reference — often supplying the issuer the text layer omits and
corroborating the extracted IBAN/reference. So QR/barcodes join continuity
numbers and out-of-column control keys as first-class margin confirmation.

Engine: zxing-cpp (`import zxingcpp`). Pages are rasterized with the existing
pdftoppm path (no new system dep). Both degrade gracefully when absent.
"""
from __future__ import annotations

import base64
import re
import shutil
from pathlib import Path
from typing import Any, Optional


def tools_available() -> tuple[bool, str]:
    import importlib.util
    if importlib.util.find_spec("zxingcpp") is None:
        return False, ("QR/barcode scanning needs zxing-cpp. Install the [qr] "
                       "extra: `pip install 'pdfdrill[qr]'` (zxing-cpp).")
    if shutil.which("pdftoppm") is None:
        return False, "QR scanning needs pdftoppm (poppler-utils) to rasterize pages."
    return True, ""


# ---------------------------------------------------------------------------
# EPC / GiroCode (SEPA Credit Transfer QR) parser — pure
# ---------------------------------------------------------------------------

def parse_epc(text: str) -> Optional[dict[str, str]]:
    """Parse a GiroCode / EPC QR (`BCD` service tag) into SEPA payment fields.
    Returns None for any non-EPC content. Field order per the EPC069-12 spec."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines or lines[0].strip() != "BCD":
        return None

    def g(i: int) -> str:
        return lines[i].strip() if i < len(lines) else ""

    amount = g(7)
    m = re.match(r"([A-Z]{3})\s*([\d.,]+)", amount)
    currency, amt = (m.group(1), m.group(2)) if m else ("", amount)
    return {
        "service": g(0), "version": g(1), "charset": g(2), "identification": g(3),
        "bic": g(4), "name": g(5), "iban": g(6),
        "currency": currency, "amount": amt,
        "purpose": g(8), "reference": g(9), "remittance": g(10) or g(9),
    }


# ---------------------------------------------------------------------------
# zxing result → finding dict (binary-safe), pure / duck-typed
# ---------------------------------------------------------------------------

def _result_to_dict(r: Any, page: int) -> dict[str, Any]:
    text = getattr(r, "text", "") or ""
    item: dict[str, Any] = {"format": str(r.format), "content": text, "page": page}
    pos = getattr(r, "position", None)
    if pos is not None:
        try:
            tl, br = pos.top_left, pos.bottom_right
            item["bbox"] = [int(tl.x), int(tl.y), int(br.x), int(br.y)]
        except Exception:
            pass
    try:
        raw = bytes(r.bytes)
        if not text and raw:                      # binary code (e.g. franking) → base64
            item["content_base64"] = base64.b64encode(raw).decode("ascii")
    except Exception:
        pass
    orient = getattr(r, "orientation", None)
    if orient is not None:
        item["orientation_deg"] = orient
    epc = parse_epc(text)
    if epc:
        item["epc"] = epc
    return item


# ---------------------------------------------------------------------------
# Scanning (rasterize via pdftoppm, decode with zxing-cpp)
# ---------------------------------------------------------------------------

def _formats(formats: Optional[str]):
    if not formats:
        return None
    import zxingcpp
    return zxingcpp.barcode_formats_from_str(formats.replace(",", "|"))

def _scan_pil(img, fmts) -> list:
    import zxingcpp
    kwargs = {"formats": fmts} if fmts else {}
    return [r for r in zxingcpp.read_barcodes(img, **kwargs) if getattr(r, "valid", True)]


def scan_pdf(pdf: Path, out_dir: Path, *, dpi: int = 300,
             pages: Optional[list[int]] = None, formats: Optional[str] = None
             ) -> list[dict[str, Any]]:
    """Rasterize page(s) (pdftoppm) and decode every QR/barcode. Returns findings
    {format, content, bbox, page, epc?, content_base64?}."""
    from . import pdf_reading
    from PIL import Image
    fmts = _formats(formats)
    findings: list[dict[str, Any]] = []
    imgs = pdf_reading.rasterize(pdf, out_dir, pages=pages, dpi=dpi, fmt="png")
    for img_path in imgs:
        digits = "".join(c for c in img_path.stem if c.isdigit())
        page_no = int(digits) if digits else 0
        for r in _scan_pil(Image.open(img_path), fmts):
            findings.append(_result_to_dict(r, page_no))
    return findings


def scan_image(path: Path, formats: Optional[str] = None) -> list[dict[str, Any]]:
    from PIL import Image
    fmts = _formats(formats)
    return [_result_to_dict(r, 1) for r in _scan_pil(Image.open(path), fmts)]
