"""MathPix PDF conversion client (pure stdlib).

Ported from the tested `mtestzx.py`: uploads a PDF to the MathPix v3 API,
polls until conversion completes, and downloads the requested outputs
(`lines.json`, `md`, `tex.zip`) next to the source PDF.

Credentials are read from the environment first
(`MATHPIX_APP_ID` / `MATHPIX_APP_KEY`), falling back to an optional,
git-ignored `mathpix_creds.py` module sitting next to this file. Keys are
never hard-coded here, so nothing sensitive enters version control.

The high-level entry point is `fetch_mathpix()`, which is idempotent: if the
expected outputs already exist next to the PDF it returns them without
touching the network (so re-runs cost no MathPix credits).
"""
from __future__ import annotations

import json
import mimetypes
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request

from . import net
import uuid
from pathlib import Path
from typing import Callable, Iterable, Optional

API_BASE = "https://api.mathpix.com/v3"

# Output formats fetched by default, in download order.
DEFAULT_FORMATS = ("lines.json", "md", "tex.zip")

# Conversion options — copied verbatim from the tested mtestzx.py.
CONVERSION_OPTIONS = {
    "conversion_options": {
        "tex.zip": {
            "include_equation_tags": True,
            "idiomatic_eqn_arrays": True,
        },
        "md": {
            "math_inline_delimiters": ["$", "$"],
            "math_display_delimiters": ["$$", "$$"],
            # 258 — BOOLEANS, not the strings they were copied as. These four
            # are documented as booleans and went on the wire as "true"/"false"
            # from the first commit (98d131b, 2026-05-29) unchanged.
            #
            # The corpus shows the request being read as truthy on both values.
            # Same options, three periods, prose only, tables/fences/URLs/
            # headings excluded:
            #
            #            % escaped/bare     & escaped/bare    # escaped/bare
            #   2026-06     102 / 2,857        738 / 888        117 / 663
            #   2026-08   4,964 /    85      3,767 / 4,815      684 /   7
            #
            # By August every one of them escapes — including `percent`, the
            # only one set to "false" and the only one where the request and
            # the behaviour disagree. A non-empty string is truthy in every
            # language a server might parse this in, so "false" asks for the
            # same thing "true" does.
            #
            # 456 documents carry \% in prose against an explicit request not
            # to escape it. Nothing downstream reads it, so no artefact is
            # being corrected here — the wire format is.
            "escape_ampersand": True,
            "escape_dollar": True,
            "escape_percent": False,
            "escape_hash": True,
        },
    }
}


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def _creds() -> tuple[str, str]:
    """Resolve (app_id, app_key) from the environment / .env (see env.py)."""
    from . import mathpix_creds
    return mathpix_creds.require()


def _auth_headers() -> dict[str, str]:
    app_id, app_key = _creds()
    return {"app_id": app_id, "app_key": app_key}


# ---------------------------------------------------------------------------
# Multipart encoding (stdlib only) — verbatim from the tested port
# ---------------------------------------------------------------------------

# MathPix /v3/pdf upload limits (the documented file-size cap) + soft warnings.
MATHPIX_MAX_BYTES = 512 * 1024 * 1024        # hard refuse above this
MATHPIX_WARN_BYTES = 100 * 1024 * 1024       # large: slow upload / costly
MATHPIX_WARN_PAGES = 100


def upload_preflight(size_bytes: int, pages: Optional[int] = None) -> tuple[bool, str, str]:
    """Decide whether to attempt a MathPix upload. Returns (ok, level, message),
    level ∈ {ok, warn, refuse}. Over the cap we refuse (and route the caller to
    OCR) rather than OOM on the in-memory encode or POST a doomed body."""
    mb = size_bytes / (1024 * 1024)
    if size_bytes > MATHPIX_MAX_BYTES:
        return (False, "refuse",
                f"{mb:.0f} MB exceeds MathPix's ~{MATHPIX_MAX_BYTES // (1024 * 1024)} MB "
                f"upload limit — pdfdrill will not attempt a doomed upload. Use "
                f"`pdfdrill ocr` (keyless tesseract) for the text layer, or split with "
                f"`pdfseparate in.pdf part-%d.pdf` and run `mathpix` per chunk.")
    if size_bytes > MATHPIX_WARN_BYTES or (pages and pages > MATHPIX_WARN_PAGES):
        return (True, "warn",
                f"large input ({mb:.0f} MB" + (f", {pages} pages" if pages else "")
                + ") — the upload is streamed (bounded RAM) but may be slow and "
                  "consume credits; `pdfdrill ocr` is the keyless alternative.")
    return (True, "ok", "")


def encode_multipart_formdata(fields, files, boundary: Optional[str] = None) -> tuple[str, bytes]:
    """fields: iterable of (name, value); files: (name, filename, bytes).

    Returns (content_type, body_bytes).
    """
    boundary = boundary or uuid.uuid4().hex
    crlf = b"\r\n"
    parts: list[bytes] = []

    for name, value in fields:
        parts.append(f"--{boundary}".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        parts.append(b"")
        parts.append(value.encode() if isinstance(value, str) else value)

    for name, filename, content in files:
        ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        parts.append(f"--{boundary}".encode())
        parts.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode()
        )
        parts.append(f"Content-Type: {ctype}".encode())
        parts.append(b"")
        parts.append(content)

    parts.append(f"--{boundary}--".encode())
    parts.append(b"")
    body = crlf.join(parts)
    return f"multipart/form-data; boundary={boundary}", body


def _stream_multipart(out_path, options_json: str, file_path: str,
                      boundary: str) -> tuple[str, int, str]:
    """Write the upload multipart body to `out_path`, streaming the PDF in chunks
    so RAM never holds 2× the file (the 463 MB OOM). Byte-identical to
    encode_multipart_formdata; returns (content_type, length, out_path)."""
    crlf = b"\r\n"
    fname = os.path.basename(file_path)
    ctype = mimetypes.guess_type(fname)[0] or "application/octet-stream"
    prefix = crlf.join([
        f"--{boundary}".encode(),
        b'Content-Disposition: form-data; name="options_json"', b"",
        options_json.encode(),
        f"--{boundary}".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{fname}"'.encode(),
        f"Content-Type: {ctype}".encode(), b"", b"",
    ])
    suffix = crlf.join([b"", f"--{boundary}--".encode(), b""])
    with open(out_path, "wb") as out:
        out.write(prefix)
        with open(file_path, "rb") as f:
            shutil.copyfileobj(f, out, length=4 * 1024 * 1024)
        out.write(suffix)
    return (f"multipart/form-data; boundary={boundary}",
            os.path.getsize(out_path), str(out_path))


# ---------------------------------------------------------------------------
# API operations
# ---------------------------------------------------------------------------

def upload_pdf(file_path: str, log: Callable[[str], None] = print) -> str:
    # Credentials FIRST. Without them this used to log "Uploading <path>..." and
    # then stream the whole PDF into a temporary multipart body before the POST
    # was rejected — a full copy of every document, for a request that could
    # never be made, while printing a line that reads like a paid upload in
    # progress. On a keyless batch over thousands of books that is both alarming
    # and expensive in I/O.
    app_id, app_key = _creds()
    if not (app_id and app_key):
        raise RuntimeError(
            "MathPix credentials are not set (MATHPIX_APP_ID / MATHPIX_APP_KEY) "
            "— no upload attempted; the caller falls back to the free routes.")
    log(f"Uploading {file_path}...")
    boundary = uuid.uuid4().hex
    tf = tempfile.NamedTemporaryFile(prefix="mxupload_", suffix=".bin", delete=False)
    tf.close()
    # Stream the body to a temp file (bounded RAM), then POST it with an explicit
    # Content-Length so http.client streams the file object rather than buffering.
    content_type, length, body_path = _stream_multipart(
        tf.name, json.dumps(CONVERSION_OPTIONS), file_path, boundary)
    bf = open(body_path, "rb")
    try:
        req = urllib.request.Request(
            f"{API_BASE}/pdf-file", data=bf, method="POST",
            headers={**_auth_headers(), "Content-Type": content_type,
                     "Content-Length": str(length)},
        )
        with net.urlopen(req, host="api.mathpix.com") as response:
            data = json.loads(response.read().decode("utf-8"))
    finally:
        bf.close()
        try:
            os.unlink(body_path)
        except OSError:
            pass
    if "pdf_id" not in data:
        raise RuntimeError("Upload failed: " + json.dumps(data))
    return data["pdf_id"]


def poll_pdf_status(
    pdf_id: str,
    interval: float = 3.0,
    log: Callable[[str], None] = print,
) -> None:
    log("Polling for completion...")
    while True:
        req = urllib.request.Request(
            f"{API_BASE}/pdf/{pdf_id}", headers=_auth_headers()
        )
        with net.urlopen(req, host="api.mathpix.com") as response:
            data = json.loads(response.read().decode("utf-8"))
        percent = data.get("percent_done") or 0
        log(f"Status: {data.get('status')} - {percent:.2f}%")
        status = data.get("status")
        if status == "completed":
            return
        if status == "error":
            raise RuntimeError("Error processing PDF: " + json.dumps(data))
        time.sleep(interval)


def download_result(
    pdf_id: str, ext: str, dest_file: str, log: Callable[[str], None] = print
) -> None:
    log(f"Downloading {ext} format...")
    req = urllib.request.Request(
        f"{API_BASE}/pdf/{pdf_id}.{ext}", headers=_auth_headers()
    )
    try:
        with net.urlopen(req, host="api.mathpix.com") as response:
            content = response.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Failed to download {ext}: HTTP {e.code} {e.reason}") from e

    if ext == "lines.json":
        json_data = json.loads(content.decode("utf-8"))
        with open(dest_file, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
    elif ext == "md":
        with open(dest_file, "w", encoding="utf-8") as f:
            f.write(content.decode("utf-8"))
    else:
        with open(dest_file, "wb") as f:
            f.write(content)
    log(f"Downloaded {dest_file} successfully")


# ---------------------------------------------------------------------------
# High-level, idempotent entry point
# ---------------------------------------------------------------------------

def base_name(pdf_path: str) -> str:
    """Strip a trailing .pdf (case-insensitive), like the original script."""
    return pdf_path[:-4] if pdf_path.lower().endswith(".pdf") else pdf_path



#: Fields MathPix puts on a line and pdfminer does not. A `.lines.json` that
#: carries none of them was written by another extractor.
_MATHPIX_LINE_FIELDS = ("confidence", "confidence_rate", "cnt", "is_printed",
                        "is_handwritten", "font_size")


def _is_mathpix_output(ext: str, path: str) -> bool:
    """Does this file exist AND look like MathPix wrote it?

    Existence alone is not enough. A document can hold a `.lines.json` from a
    later pdfminer pass beside a MathPix `.tex.zip` and `.md`, and an
    existence-only guard then reports "already present" and skips forever —
    which is how 29 documents kept equations with no confidence through a run
    that was supposed to give them some. Presence is not adequacy
    (HANDOVER-RULES rule 6).

    Only `.lines.json` is inspected; the other formats have no cheap
    discriminator and their presence is taken at face value.
    """
    if not os.path.exists(path):
        return False
    if not path.endswith(".lines.json"):
        return True
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
        for page in data.get("pages", [])[:3]:
            for line in page.get("lines", [])[:40]:
                if any(k in line for k in _MATHPIX_LINE_FIELDS):
                    return True
        return False
    except Exception:
        return False            # unreadable: treat as absent, re-fetch

def expected_outputs(
    pdf_path: str, formats: Iterable[str] = DEFAULT_FORMATS
) -> dict[str, str]:
    """Map each format to the path where its output would be written."""
    base = base_name(pdf_path)
    return {ext: f"{base}.{ext}" for ext in formats}


def fetch_mathpix(
    pdf_path: str,
    formats: Iterable[str] = DEFAULT_FORMATS,
    force: bool = False,
    interval: float = 3.0,
    log: Callable[[str], None] = lambda m: print(m, file=sys.stderr),
) -> dict:
    """Download MathPix outputs for `pdf_path`, skipping work already done.

    Returns a dict: {"status": "cached"|"downloaded", "pdf_id": str|None,
    "files": {ext: path}}. Idempotent: if every expected output already
    exists and `force` is False, no network call is made.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"File not found: {pdf_path}")

    formats = tuple(formats)
    targets = expected_outputs(pdf_path, formats)

    if not force and all(_is_mathpix_output(ext, p)
                         for ext, p in targets.items()):
        log("All MathPix outputs already present — skipping upload.")
        return {"status": "cached", "pdf_id": None, "files": targets}
    stale = [p for ext, p in targets.items()
             if os.path.exists(p) and not _is_mathpix_output(ext, p)]
    if stale:
        log("Present but NOT MathPix output, re-fetching: "
            + ", ".join(os.path.basename(p) for p in stale))

    pdf_id = upload_pdf(pdf_path, log=log)
    log(f"Uploaded PDF ID: {pdf_id}")
    poll_pdf_status(pdf_id, interval=interval, log=log)
    for ext, dest in targets.items():
        download_result(pdf_id, ext, dest, log=log)
    return {"status": "downloaded", "pdf_id": pdf_id, "files": targets}


def main(argv: Optional[list[str]] = None) -> int:
    """Standalone CLI, equivalent to the original mtestzx.py."""
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("Usage: python -m pdfdrill.mathpix_client <filename.pdf>", file=sys.stderr)
        return 1
    try:
        result = fetch_mathpix(argv[0], force="--force" in argv[1:])
        print(f"{result['status']}: " + ", ".join(result["files"].values()))
        return 0
    except Exception as e:  # noqa: BLE001 — top-level CLI guard
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
