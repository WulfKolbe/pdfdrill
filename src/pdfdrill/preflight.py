"""
Preflight attestation gate — the hard stop that disqualifies an LLM which did not
read the SKILL from silently driving pdfdrill into a disaster.

The failure mode this defends against: pdfdrill's prose output LOOKS authoritative,
so an LLM that skimmed or truncated the SKILL produces trusted-but-wrong results
(wrong extraction route, duplicate equations, a directory stat'ed as a PDF). A CLI
cannot force an LLM to read anything, so instead:

1. SKILL.md ends with an ATTESTATION TOKEN — a checksum of the SKILL body printed
   as its last line. An LLM that read the whole SKILL sees the token; one that
   truncated/skimmed never does.
2. `pdfdrill preflight` prints the critical rules + a dep check and instructs the
   LLM to run `pdfdrill preflight --ack <TOKEN>`.
3. `--ack <TOKEN>` verifies the token against pdfdrill's own copy of the SKILL and
   writes a session marker.
4. BUILD/COST commands hard-stop without the marker; read-only bootstrap commands
   (size/pdfinfo/doctor/help/config/skill/steps/plan/status/…) stay open so the
   LLM can always reach `preflight` and discover the gate.

Escape hatch: `PDFDRILL_NO_PREFLIGHT=1` disables the gate (CI, tests, trusted
automation); `PDFDRILL_PREFLIGHT_TOKEN=<token>` attests statelessly.

Pure stdlib. Spec: docs/superpowers/specs/2026-07-14-preflight-attestation-gate.md.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

TOKEN_BEGIN = "<!-- PREFLIGHT-TOKEN:BEGIN -->"
TOKEN_END = "<!-- PREFLIGHT-TOKEN:END -->"
_TOKEN_PREFIX = "DRILL-"
_MARKER_NAME = ".pdfdrill-preflight.json"
_TTL_SECONDS = 24 * 3600

# Skill resolution mirrors skill_cmd: the bundled copy that ships with the package,
# else the repo's .claude/skills copy.
_BUNDLED = Path(__file__).with_name("skill")
_REPO_SKILL = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "pdfdrill"

# Read-only bootstrap / introspection commands that are ALWAYS allowed, so the LLM
# can reach `preflight`, check the environment, and discover the gate. Everything
# NOT in this set is a build/mutate/cost command and is gated.
EXEMPT = frozenset({
    "preflight", "doctor", "help", "--help", "-h", "config", "skill",
    "size", "pdfinfo", "steps", "plan", "status", "artifacts", "ls",
    "links", "dests", "urls", "fonts", "fonts_layer", "images", "route",
})


# ── token ──────────────────────────────────────────────────────────────────

def _strip_token_region(text: str) -> str:
    """The SKILL body with the token region removed — the thing we hash (so the
    token can be stable: it never hashes itself)."""
    if TOKEN_BEGIN in text and TOKEN_END in text:
        pre = text[: text.index(TOKEN_BEGIN)]
        post = text[text.index(TOKEN_END) + len(TOKEN_END):]
        return pre + post
    return text


def compute_token(text: str) -> str:
    """`DRILL-<8 hex>` checksum of the SKILL body (excluding the token region).
    Trailing whitespace is normalised (`.rstrip()`) so render-time and verify-time
    agree regardless of how the token block is spaced at the end of the file."""
    body = _strip_token_region(text).rstrip().encode("utf-8")
    return _TOKEN_PREFIX + hashlib.sha256(body).hexdigest()[:8]


def render_token_block(text: str) -> str:
    """Return `text` with a fresh token region appended/replacing the old one, so
    the SKILL ends with the current attestation token (skillsync calls this)."""
    stripped = _strip_token_region(text).rstrip() + "\n"
    token = compute_token(text)
    block = (f"\n{TOKEN_BEGIN}\n"
             f"Attestation token — the LAST line of this SKILL. If you can read "
             f"this, you read the whole file. Run `pdfdrill preflight --ack "
             f"{token}` before any build/extract command.\n"
             f"{token}\n"
             f"{TOKEN_END}\n")
    return stripped + block


def skill_text() -> str:
    """pdfdrill's own copy of SKILL.md (bundled preferred, else repo). '' if none."""
    for d in (_BUNDLED, _REPO_SKILL):
        p = d / "SKILL.md"
        try:
            if p.is_file():
                return p.read_text(encoding="utf-8")
        except OSError:
            continue
    return ""


def expected_token() -> str:
    """The token pdfdrill currently expects (from its own SKILL.md)."""
    return compute_token(skill_text())


# ── marker (attestation state) ───────────────────────────────────────────────

def marker_dir() -> Path:
    from . import config as cfg
    return cfg.download_dir()


def _marker_path() -> Path:
    return marker_dir() / _MARKER_NAME


def attest(token: str) -> bool:
    """Validate `token` against the expected token; on success write a session
    marker and return True. Wrong token → False, no marker."""
    if not token or token.strip() != expected_token():
        return False
    try:
        _marker_path().write_text(json.dumps(
            {"token": token.strip(), "ts": int(time.time())}), encoding="utf-8")
    except OSError:
        return False
    return True


def is_attested() -> bool:
    """True if a valid, unexpired marker exists whose token still matches the
    current SKILL (a SKILL change invalidates it → the LLM must re-read/attest).
    `PDFDRILL_PREFLIGHT_TOKEN` env attests statelessly."""
    env_tok = os.environ.get("PDFDRILL_PREFLIGHT_TOKEN")
    if env_tok and env_tok.strip() == expected_token():
        return True
    try:
        data = json.loads(_marker_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if data.get("token") != expected_token():
        return False
    return (time.time() - float(data.get("ts", 0))) < _TTL_SECONDS


def clear() -> None:
    try:
        _marker_path().unlink()
    except OSError:
        pass


# ── gate ─────────────────────────────────────────────────────────────────────

def enforced() -> bool:
    """The gate is on unless `PDFDRILL_NO_PREFLIGHT` is set truthy."""
    return os.environ.get("PDFDRILL_NO_PREFLIGHT", "").lower() not in ("1", "true", "yes")


def is_gated(cmd: str) -> bool:
    """True for build/mutate/cost commands (everything not in EXEMPT)."""
    return cmd not in EXEMPT


def blocks(cmd: str) -> bool:
    """The hard-stop decision: this command must be refused right now."""
    return enforced() and is_gated(cmd) and not is_attested()


# ── prose ────────────────────────────────────────────────────────────────────

CRITICAL_RULES = [
    "Pass an identifier (path / https URL / bare arXiv id) as <pdf>; pdfdrill "
    "downloads + resolves it. NEVER curl/wget/tar/unzip a PDF or e-print yourself.",
    "Start shallow (size, pdfinfo, links, abstract) before building a model; "
    "escalate only when the question needs it.",
    "A built model may be a DIFFERENT species (geometry vs math). Trust `status`, "
    "not the bare MODEL_BUILT fact.",
    "Never present a 0-equation model of a math paper as complete — it means the "
    "math was dropped (run mathpix/visionocr).",
    "One command per step; let pdfdrill manage prerequisites (`--ensure`, `steps`).",
    "Read outputs pdfdrill writes (llmtext, report, tables) from the drill folder; "
    "do not re-extract by hand.",
]


def rules_card() -> str:
    lines = ["pdfdrill CRITICAL RULES (read the full SKILL for the rest):"]
    lines += [f"  {i}. {r}" for i, r in enumerate(CRITICAL_RULES, 1)]
    return "\n".join(lines)


def gate_message(cmd: str) -> str:
    return (
        f"⛔ pdfdrill STOP: `{cmd}` is a build/extract command and is BLOCKED "
        f"until you attest that you read the SKILL.\n\n"
        f"Why: pdfdrill output looks authoritative, so using it without the usage "
        f"rules produces silently-WRONG results. Read the SKILL, then:\n"
        f"  1. run `pdfdrill preflight`\n"
        f"  2. read SKILL.md to its LAST line to get the attestation token\n"
        f"  3. run `pdfdrill preflight --ack <TOKEN>`\n"
        f"Then re-run your command. (Automation may set PDFDRILL_NO_PREFLIGHT=1.)")
