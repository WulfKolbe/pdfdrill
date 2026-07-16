"""I-B) drillui drag & drop producer — two modes.

A browser drop gives you one of two things, and they need different handling:

- **Path-reference mode** — the file manager hands over ``text/uri-list``
  (``file:///home/...``). The bridge runs on the machine that owns the files, so
  we record a manifest entry pointing at the ORIGINAL. Zero copying. This is only
  safe behind an allowlist, so it mirrors the bridge's ``safeResolve`` root check.
- **Upload mode** — the drop gives bytes but no usable path (or the bridge is
  remote). We write into the job's ``raw/`` and ingest that.

Everything here is pure logic over bytes/paths so it is testable without a
server, and so the same functions serve a future Bun-hosted endpoint.

Security note: both modes take attacker-influenced names. A multipart
``filename`` is arbitrary client input (``../../.ssh/authorized_keys``), and a
dropped URI can point anywhere on the filesystem. The guards below are the whole
point of this module, not decoration.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse

from ..ingest import IMAGE_EXTS, add_path
from ..manifest import Manifest, Page

MAX_NAME_LEN = 120


class UploadError(ValueError):
    pass


# ---- path safety ----------------------------------------------------------------

def under_root(root: str | Path, candidate: str | Path) -> Path | None:
    """Resolved ``candidate`` if it is inside ``root``, else None.

    Resolves BOTH sides first: without that, ``root/../etc`` or a symlink out of
    the tree would pass a naive string prefix check.
    """
    try:
        r = Path(root).resolve(strict=False)
        c = Path(candidate)
        if not c.is_absolute():
            c = r / c
        c = c.resolve(strict=False)
    except (OSError, RuntimeError):     # RuntimeError: symlink loop
        return None
    if c == r or r in c.parents:
        return c
    return None


def safe_resolve(roots: list[str | Path], candidate: str | Path) -> Path | None:
    """First root that contains ``candidate`` (mirrors the bridge's safeResolve)."""
    for root in roots:
        got = under_root(root, candidate)
        if got is not None:
            return got
    return None


def safe_filename(name: str, *, fallback: str = "page") -> str:
    """Reduce client-supplied filename to a harmless basename.

    Strips directory components (``../../etc/passwd`` → ``passwd``), NUL bytes,
    and control characters; refuses names that reduce to nothing or to a dotfile.
    """
    if not name:
        return fallback
    name = unicodedata.normalize("NFKD", name)
    name = name.replace("\x00", "")
    # Both separators: a Windows client may send backslashes.
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    name = name.lstrip(".")                       # no dotfiles, no ".."
    name = re.sub(r'[<>:"|?*]', "_", name)
    if len(name) > MAX_NAME_LEN:
        stem, dot, ext = name.rpartition(".")
        keep = MAX_NAME_LEN - (len(ext) + 1 if dot else 0)
        name = (stem[:keep] + dot + ext) if dot else name[:MAX_NAME_LEN]
    return name or fallback


def is_image_name(name: str) -> bool:
    return Path(name).suffix.lower() in IMAGE_EXTS


# ---- text/uri-list --------------------------------------------------------------

def parse_uri_list(text: str) -> list[str]:
    """Parse a ``text/uri-list`` drop payload into local paths.

    Per RFC 2483 lines starting with ``#`` are comments. Desktop environments
    vary (this is the bit that needs checking on the target DE): some send
    ``text/uri-list`` with ``file://`` URIs, some send plain paths as
    ``text/plain``. Both are accepted; non-file schemes are dropped.
    """
    out: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("file://"):
            parsed = urlparse(line)
            if parsed.netloc not in ("", "localhost"):
                continue                      # file://otherhost/... is not ours
            out.append(unquote(parsed.path))
        elif "://" in line:
            continue                          # http:, data:, ... not a local file
        else:
            out.append(unquote(line) if "%" in line else line)
    return out


# ---- the two modes --------------------------------------------------------------

def add_reference(
    manifest: Manifest,
    path: str | Path,
    *,
    roots: list[str | Path],
    blank_threshold: float | None = 0.999,
) -> Page:
    """Path-reference mode: manifest entry pointing at the original. No copy.

    Refuses anything outside ``roots`` — a drop can name any path on the box.
    """
    resolved = safe_resolve(roots, path)
    if resolved is None:
        raise UploadError(f"path outside the allowed roots: {path}")
    if not resolved.is_file():
        raise UploadError(f"not a file: {path}")
    if not is_image_name(resolved.name):
        raise UploadError(f"not an image: {resolved.name}")
    return add_path(
        manifest, resolved,
        origin={"kind": "drop", "mode": "reference", "path": str(resolved)},
        rel_to=None,                     # absolute src: the original stays put
        blank_threshold=blank_threshold,
    )


def add_upload(
    manifest: Manifest,
    filename: str,
    data: bytes,
    *,
    job_dir: str | Path,
    blank_threshold: float | None = 0.999,
    max_bytes: int = 200 * 1024 * 1024,
) -> Page:
    """Upload mode: write bytes into ``job_dir/raw/`` and ingest them."""
    if not data:
        raise UploadError(f"empty upload: {filename}")
    if len(data) > max_bytes:
        raise UploadError(f"upload too large: {filename} ({len(data)} bytes)")
    safe = safe_filename(filename)
    if not is_image_name(safe):
        raise UploadError(f"not an image: {filename}")

    raw = Path(job_dir) / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    # Sequence-prefix the stored name: two drops of "scan.png" must not collide,
    # and the prefix preserves drop order for the default `name` ordering.
    dest = raw / f"p{len(manifest.pages) + 1:04d}_{safe}"
    dest.write_bytes(data)

    try:
        return add_path(
            manifest, dest,
            origin={"kind": "drop", "mode": "upload", "filename": safe},
            rel_to=Path(job_dir),
            blank_threshold=blank_threshold,
        )
    except Exception:
        dest.unlink(missing_ok=True)     # don't leave a half-ingested file behind
        raise


def add_drop(
    manifest: Manifest,
    payload: str,
    *,
    roots: list[str | Path],
    blank_threshold: float | None = 0.999,
) -> tuple[list[Page], list[str]]:
    """Reference-mode drop of a whole ``text/uri-list``. Returns (pages, errors).

    One bad entry must not sink the rest of the drop — a drag of 20 files with a
    stray directory should ingest 19 and say why the 20th failed.
    """
    pages, errors = [], []
    for p in parse_uri_list(payload):
        try:
            pages.append(add_reference(manifest, p, roots=roots,
                                       blank_threshold=blank_threshold))
        except UploadError as exc:
            errors.append(str(exc))
    return pages, errors


# ---- multipart ------------------------------------------------------------------

def parse_multipart(content_type: str, body: bytes) -> list[tuple[str, bytes]]:
    """Extract ``(filename, data)`` from a multipart/form-data body.

    stdlib only: ``cgi`` was REMOVED in Python 3.13, so this uses
    ``email.parser`` — feed it the Content-Type header plus the body and it does
    the boundary handling.
    """
    from email.parser import BytesParser
    from email.policy import default as default_policy

    if "multipart/form-data" not in (content_type or ""):
        raise UploadError(f"expected multipart/form-data, got {content_type!r}")
    head = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode()
    msg = BytesParser(policy=default_policy).parsebytes(head + body)
    if not msg.is_multipart():
        raise UploadError("body is not multipart")

    out: list[tuple[str, bytes]] = []
    for part in msg.iter_parts():
        fn = part.get_filename()
        if not fn:
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        out.append((fn, payload))
    return out
