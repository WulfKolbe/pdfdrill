"""
Minimal .env loader (stdlib only — no python-dotenv dependency).

On first credential lookup we load `KEY=VALUE` lines from a `.env` file at the
repository root (or `$PDFDRILL_ENV`) into `os.environ`, WITHOUT overwriting
variables already set in the real environment. So precedence is:

    real environment  >  .env file  >  (nothing → friendly error)

The `.env` file holding real keys is git-ignored; `.env.example` (committed)
documents the variable names with dummy values.
"""
from __future__ import annotations

import os
from pathlib import Path

_loaded = False


def _candidate_paths() -> list[Path]:
    paths = []
    explicit = os.environ.get("PDFDRILL_ENV")
    if explicit:
        paths.append(Path(explicit))
    # repo root is three levels up from this file: src/pdfdrill/env.py -> repo/
    repo_root = Path(__file__).resolve().parents[2]
    paths.append(repo_root / ".env")
    paths.append(Path.cwd() / ".env")
    return paths


def _parse(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        # strip matching surrounding quotes
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key:
            out[key] = val
    return out


def load_env(force: bool = False) -> None:
    """Load the first existing .env into os.environ (real env wins). Idempotent."""
    global _loaded
    if _loaded and not force:
        return
    for p in _candidate_paths():
        try:
            if p.is_file():
                for k, v in _parse(p.read_text(encoding="utf-8")).items():
                    os.environ.setdefault(k, v)   # do not clobber the real env
                break
        except Exception:
            continue
    _loaded = True


def get(name: str, default: str = "") -> str:
    """Return an env var, loading the .env file first if needed."""
    load_env()
    return os.environ.get(name, default)
