"""Perplexity credentials — loaded from the environment / .env (no secrets here).

Resolution order (see pdfdrill.env): real environment > repo `.env` file.
`.env` is git-ignored; `.env.example` documents the variable names. This file
is SAFE TO COMMIT — it contains no key.
"""
from __future__ import annotations

from .env import get

PERPLEXITY_API_KEY = get("PERPLEXITY_API_KEY", "")


def require() -> str:
    """Return the Perplexity key or exit with a friendly setup message."""
    key = get("PERPLEXITY_API_KEY", "")
    if not key:
        raise SystemExit(
            "Perplexity credentials missing.\n"
            "  export PERPLEXITY_API_KEY=...\n"
            "or copy .env.example to .env and fill it in.\n"
            "Get a key at https://www.perplexity.ai/ (Settings -> API)."
        )
    return key
