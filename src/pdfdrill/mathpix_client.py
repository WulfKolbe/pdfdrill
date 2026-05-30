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
import os
import sys
import time
import urllib.error
import urllib.request
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
            "escape_ampersand": "true",
            "escape_dollar": "true",
            "escape_percent": "false",
            "escape_hash": "true",
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

def encode_multipart_formdata(fields, files) -> tuple[str, bytes]:
    """fields: iterable of (name, value); files: (name, filename, bytes).

    Returns (content_type, body_bytes).
    """
    boundary = uuid.uuid4().hex
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


# ---------------------------------------------------------------------------
# API operations
# ---------------------------------------------------------------------------

def upload_pdf(file_path: str, log: Callable[[str], None] = print) -> str:
    log(f"Uploading {file_path}...")
    with open(file_path, "rb") as f:
        file_content = f.read()

    content_type, body = encode_multipart_formdata(
        fields=[("options_json", json.dumps(CONVERSION_OPTIONS))],
        files=[("file", os.path.basename(file_path), file_content)],
    )
    req = urllib.request.Request(
        f"{API_BASE}/pdf-file",
        data=body,
        method="POST",
        headers={**_auth_headers(), "Content-Type": content_type},
    )
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode("utf-8"))
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
        with urllib.request.urlopen(req) as response:
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
        with urllib.request.urlopen(req) as response:
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

    if not force and all(os.path.exists(p) for p in targets.values()):
        log("All MathPix outputs already present — skipping upload.")
        return {"status": "cached", "pdf_id": None, "files": targets}

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
