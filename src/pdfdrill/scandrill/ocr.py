"""Add a searchable text layer WITHOUT touching the image.

The point of this module is what it refuses to do. Every off-the-shelf route to
"a PDF with an OCR part" writes the PDF itself and takes the image with it:

- **Ghostscript ``pdfocr8/24/32``** — absent from this build (needs gs compiled
  with Tesseract), and rasterizes the page through the gs renderer regardless.
  ``pdfocr8`` is *grayscale*: it would silently destroy a Color scan.
- **``tesseract in out pdf``** — writes its own PDF. It passes JPEG through
  verbatim (measured), but we lose /Lang, DocInfo, XMP and page labels.

So we take only the piece we want: ``-c textonly_pdf=1`` makes Tesseract emit a
PDF containing *only* the invisible text, correctly positioned, with no image.
``pikepdf.Page.add_overlay`` composites that onto our page. The image XObject is
never rewritten — the embed stays byte-identical.

Per the project rule, OCR here exists only to *prepare a better PDF*; pdfdrill
still runs its own analysis downstream.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pikepdf

# tesseract wants 'deu', 'eng' — the manifest carries BCP-47 ('de-DE').
_LANG_MAP = {
    "de": "deu", "en": "eng", "fr": "fra", "es": "spa", "it": "ita",
    "nl": "nld", "pt": "por", "pl": "pol", "ru": "rus", "da": "dan",
    "sv": "swe", "no": "nor", "fi": "fin", "cs": "ces", "tr": "tur",
}


class OcrError(RuntimeError):
    pass


def tesseract_lang(lang: str) -> str:
    """'de-DE' → 'deu'. Falls back to the string itself if already a 3-letter code."""
    if not lang:
        return "eng"
    primary = lang.replace("_", "-").split("-")[0].lower()
    if len(primary) == 3:
        return primary
    return _LANG_MAP.get(primary, "eng")


def have_tesseract() -> bool:
    try:
        subprocess.run(["tesseract", "--version"], capture_output=True, timeout=15)
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def available_langs() -> list[str]:
    try:
        p = subprocess.run(["tesseract", "--list-langs"], capture_output=True,
                           text=True, timeout=15)
    except (subprocess.SubprocessError, OSError):
        return []
    return [ln.strip() for ln in p.stdout.splitlines()[1:] if ln.strip()]


def text_only_pdf(image: str | Path, out_pdf: str | Path, *, lang: str = "deu",
                  dpi: int | None = None, timeout: float = 300.0) -> Path:
    """OCR one page image → a PDF holding ONLY the invisible text layer.

    ``textonly_pdf=1`` is what makes this safe: no image is embedded, so grafting
    it cannot disturb ours.
    """
    out_pdf = Path(out_pdf)
    stem = out_pdf.with_suffix("")          # tesseract appends .pdf itself
    cmd = ["tesseract", str(image), str(stem), "-l", lang]
    if dpi:
        cmd += ["--dpi", str(dpi)]
    cmd += ["pdf", "-c", "textonly_pdf=1"]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except (subprocess.SubprocessError, OSError) as exc:
        raise OcrError(f"tesseract failed: {exc}") from exc
    if not out_pdf.exists():
        err = p.stderr.decode("utf-8", errors="replace").strip()
        raise OcrError(f"tesseract produced no text layer: {err}")
    return out_pdf


def graft_text_layer(
    pdf_path: str | Path,
    page_images: list[Path],
    *,
    lang: str = "deu",
    dpi: int | None = None,
    timeout: float = 300.0,
) -> int:
    """Add an invisible OCR text layer to an existing PDF, in place.

    ``page_images[i]`` must be the source image of page ``i`` — the same list
    assembly used, in the same order. Returns the number of pages grafted.

    The image streams are not rewritten: only each page's content stream gains
    the overlaid text. Verify with ``tests/test_ocr.py``, which asserts the raw
    image bytes are identical before and after.
    """
    pdf_path = Path(pdf_path)
    # Fail on a missing language pack rather than silently OCR-ing German as
    # English and grafting a plausible-looking wrong text layer.
    installed = available_langs()
    if installed and lang not in installed:
        raise OcrError(
            f"tesseract language {lang!r} is not installed "
            f"(have: {', '.join(installed[:12])}{'...' if len(installed) > 12 else ''})"
        )
    grafted = 0
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
            if len(pdf.pages) != len(page_images):
                raise OcrError(
                    f"page/image count mismatch: {len(pdf.pages)} pages vs "
                    f"{len(page_images)} images"
                )
            for i, (page, img) in enumerate(zip(pdf.pages, page_images)):
                layer = text_only_pdf(img, td / f"p{i}.pdf", lang=lang, dpi=dpi,
                                      timeout=timeout)
                with pikepdf.open(layer) as text:
                    if not len(text.pages):
                        continue
                    page.add_overlay(text.pages[0])
                    grafted += 1
            pdf.save()
    return grafted
