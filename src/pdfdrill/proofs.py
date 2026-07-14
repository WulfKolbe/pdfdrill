"""
Proof objects — content-hash provenance for a capability.

A capability's proof records the content-hash of every input it was built from
plus a hash of its parameters. Validity is decidable at any later time by
re-hashing the inputs: `verify(proof)` is True iff every recorded input still
matches the file on disk. This REPLACES the mtime `stale` trigger
(`_stale_or_absent`) that fired a silent rebuild whenever `lines.json` was newer
than the model — the mechanism behind the clobber bug. With proofs, an invalid
capability makes rebuild an EXPLICIT plan step the capability planner must justify
against `destroys:`, never a silent side effect.

Phase B of docs/superpowers/plans/2026-07-14-capability-planner.md. Pure stdlib;
uses blake3 when installed (recording `blake3:`), else sha256 (`sha256:`), so the
recorded algorithm never lies.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

try:                                    # optional, better hash if present
    import blake3 as _blake3           # noqa: F401
    _ALGO = "blake3"
except Exception:                       # noqa: BLE001
    _blake3 = None
    _ALGO = "sha256"


def _hash_bytes(data: bytes) -> str:
    if _blake3 is not None:
        return f"blake3:{_blake3.blake3(data).hexdigest()}"
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def content_hash(path: str | Path) -> str | None:
    """`<algo>:<hex>` of the file's bytes, or None if it can't be read."""
    try:
        return _hash_bytes(Path(path).read_bytes())
    except OSError:
        return None


def params_hash(params: dict | None) -> str:
    """Order-independent hash of a parameter dict (bibkey, flags, …)."""
    blob = json.dumps(params or {}, sort_keys=True, ensure_ascii=False, default=str)
    return _hash_bytes(blob.encode("utf-8"))


def make_proof(produced_by: str, inputs=None, params: dict | None = None,
               *, provenance: str | None = None, rank: int | None = None,
               confidence: float | None = None) -> dict:
    """Build a proof object for a capability produced by `produced_by` from
    `inputs` (path-likes) with `params`. Records each input's content-hash,
    a params hash, the algo, and a timestamp. `provenance`/`rank`/`confidence`
    are optional (the ranked-capability layer)."""
    ins: dict[str, str] = {}
    for p in (inputs or []):
        h = content_hash(p)
        if h is not None:
            ins[str(p)] = h
    proof = {
        "produced_by": produced_by,
        "inputs": ins,
        "params_hash": params_hash(params),
        "algo": _ALGO,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if provenance is not None:
        proof["provenance"] = provenance
    if rank is not None:
        proof["rank"] = rank
    if confidence is not None:
        proof["confidence"] = confidence
    return proof


def verify(proof: dict) -> bool:
    """True iff every recorded input still hashes to its stored value (and none
    is missing). An empty-input proof (no tracked inputs) is treated as valid —
    there is nothing to invalidate."""
    for path, want in (proof.get("inputs") or {}).items():
        if content_hash(path) != want:
            return False
    return True
