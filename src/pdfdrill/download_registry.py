"""A single JSON log of every URL download — the download dir's `pdfdrill-
downloads.json`.

The URL is the identity (the user supplies URLs, not filenames), so each record
keys a complete URL to its local filename, its **BLAKE3** content hash, the byte
size and a timestamp. Two purposes:
  1. Re-resolving a URL is a registry lookup → the same local file (true cache).
  2. Two different papers sharing a basename (`host1/fulltext.pdf` vs
     `host2/fulltext.pdf`) get distinct files — the colliding one is renamed with
     its content hash (`<stem>-<hash8>.pdf`) — instead of clobbering each other;
     identical content (same hash) is de-duplicated to one file.

BLAKE3 if the `blake3` package is installed, else sha256 — the chosen algorithm
is recorded per entry (`algo`), so the log never lies about which hash it holds.
Pure stdlib (+ optional blake3). One writer at a time (atomic replace)."""
from __future__ import annotations

import json
import time
from pathlib import Path

REGISTRY_NAME = "pdfdrill-downloads.json"


def registry_path(dest_dir) -> Path:
    return Path(dest_dir) / REGISTRY_NAME


def load(dest_dir) -> dict:
    """{url: entry}. Empty/corrupt → {}."""
    p = registry_path(dest_dir)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:                                    # noqa: BLE001
            return {}
    return {}


def save(dest_dir, reg: dict) -> None:
    p = registry_path(dest_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)                                           # atomic


def hash_file(path) -> tuple[str, str]:
    """(hex_digest, algo). BLAKE3 if available, else sha256."""
    try:
        import blake3                                        # type: ignore
        h, algo = blake3.blake3(), "blake3"
    except Exception:                                        # noqa: BLE001
        import hashlib
        h, algo = hashlib.sha256(), "sha256"
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest(), algo


def record(dest_dir, url: str, filename: str, digest: str, algo: str,
           nbytes: int) -> dict:
    """Log/refresh one download. Returns the updated registry."""
    reg = load(dest_dir)
    reg[url] = {
        "url": url, "filename": filename, "hash": digest, "algo": algo,
        "bytes": int(nbytes),
        "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save(dest_dir, reg)
    return reg


def hash_for_filename(reg: dict, filename: str) -> "str | None":
    """The recorded content hash of whatever URL currently owns `filename`."""
    for e in reg.values():
        if e.get("filename") == filename:
            return e.get("hash")
    return None
