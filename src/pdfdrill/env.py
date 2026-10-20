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


#: The credential variables pdfdrill reads. Named explicitly rather than matched
#: by shape, because `PDFDRILL_OCR_BUDGET_EUR` is an env var about a paid route
#: and must keep working when the keys are gone — a budget of nothing is not the
#: same as no budget.
CREDENTIAL_NAMES = frozenset({
    "MATHPIX_APP_ID", "MATHPIX_APP_KEY",
    "OPENAI_API_KEY", "DEEPL_API_KEY", "PERPLEXITY_API_KEY",
    "NOVITA_API_KEY", "MAKORA_API_KEY",
})

#: Set to 1 to make this machine answer as a FRESH SANDBOX does: every
#: credential absent, `.env` not read at all.
SANDBOX_ENV = "PDFDRILL_SANDBOX"


def sandbox() -> bool:
    """True when the caller asked to be answered as a keyless install.

    The sandbox the work ships to starts with no keys, and the machine it is
    built on has seven. Every lane decision is therefore a different decision
    on the two machines, and the only way to check the one that matters is to
    be able to ASK FOR IT — `PDFDRILL_SANDBOX=1 pdfdrill route <pdf>` answers
    exactly as the sandbox will. Reading the real environment variable each
    time (not a module constant) so it can be set per command.
    """
    return os.environ.get(SANDBOX_ENV, "").strip() not in ("", "0", "false", "no")


def get(name: str, default: str = "") -> str:
    """Return an env var, loading the .env file first if needed.

    Under `PDFDRILL_SANDBOX=1` every name in `CREDENTIAL_NAMES` answers empty
    and the `.env` file is never read, so a keyed machine can be asked what the
    keyless one will do. Nothing else changes: the same code runs, it is simply
    told the truth about a different install.
    """
    if sandbox():
        if name in CREDENTIAL_NAMES:
            return default
        return os.environ.get(name, default)
    load_env()
    return os.environ.get(name, default)
