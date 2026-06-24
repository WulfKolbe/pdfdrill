"""MathPix credentials — loaded from the environment / .env (no secrets here).

Resolution order (see pdfdrill.env): real environment > repo `.env` file.
`.env` is git-ignored; `.env.example` documents the variable names. This file
is SAFE TO COMMIT — it contains no keys.
"""
from __future__ import annotations

from .env import get

APP_ID = get("MATHPIX_APP_ID", "")
APP_KEY = get("MATHPIX_APP_KEY", "")


def available() -> bool:
    """True iff both MathPix keys are configured (env / .env) — checked LIVE, so
    it reflects the current environment, not import-time constants. Lets callers
    (e.g. `pdfdrill md`) just RUN MathPix when keys exist instead of printing a
    setup discussion."""
    return bool(get("MATHPIX_APP_ID", "") and get("MATHPIX_APP_KEY", ""))


def require() -> tuple[str, str]:
    """Return (app_id, app_key) or exit with a friendly setup message."""
    app_id = get("MATHPIX_APP_ID", "")
    app_key = get("MATHPIX_APP_KEY", "")
    if not app_id or not app_key:
        raise SystemExit(
            "MathPix credentials missing.\n"
            "  export MATHPIX_APP_ID=...\n"
            "  export MATHPIX_APP_KEY=...\n"
            "or copy .env.example to .env and fill it in.\n"
            "Get keys at https://mathpix.com/ (Console -> API Keys)."
        )
    return app_id, app_key
