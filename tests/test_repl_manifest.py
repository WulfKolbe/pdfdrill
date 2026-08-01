"""
Drift gate: per-command FACTS the REPL relies on must live in commands.yaml.

Found by audit: `drillui_chat._COMBINED_OK` was a hand-maintained
`{"bibtex"}` while pdfdrill had meanwhile made `abstract`, `docs`, `retrieve`
and `context` combined-store aware. drillui therefore fanned those out per
document and never used the session-aware implementations — a silent capability
regression, invisible to every existing test.

This locks the two sides together: a command whose implementation reads a
combined store MUST carry `accepts_combined: true` in the manifest, and vice
versa.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / ".claude" / "skills" / "pdfdrill" / "commands.yaml"
COMMANDS_PY = ROOT / "src" / "pdfdrill" / "commands.py"


def _manifest_combined() -> set[str]:
    """Names carrying `accepts_combined: true` (line-based: the manifest is a
    hand-maintained SSOT, so we do not round-trip it through a YAML dumper)."""
    out, name = set(), None
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^- name: (\S+)", line)
        if m:
            name = m.group(1)
        elif name and re.match(r"^  accepts_combined:\s*true\s*$", line):
            out.add(name)
    return out


def _code_combined() -> set[str]:
    """Commands whose `cmd_<name>` body reads a combined store."""
    src = COMMANDS_PY.read_text(encoding="utf-8")
    funcs = re.split(r"^def ", src, flags=re.M)
    out = set()
    for f in funcs:
        m = re.match(r"cmd_(\w+)\s*\(", f)
        if not m:
            continue
        if "_load_combined_store(" in f or "_store_sources(" in f:
            out.add(m.group(1))
    return out


def test_manifest_marks_every_combined_aware_command():
    code, man = _code_combined(), _manifest_combined()
    missing = code - man
    assert not missing, (
        f"these commands read a combined store but lack "
        f"`accepts_combined: true` in commands.yaml: {sorted(missing)} — "
        f"drillui will fan them out per-document instead of using them")


def test_manifest_does_not_claim_unsupported_commands():
    code, man = _code_combined(), _manifest_combined()
    extra = man - code
    assert not extra, (
        f"commands.yaml marks these `accepts_combined` but no implementation "
        f"reads a combined store: {sorted(extra)}")


def test_the_known_set_is_present():
    """Regression anchor for the four that were missing."""
    man = _manifest_combined()
    for name in ("abstract", "docs", "bibtex", "retrieve", "context"):
        assert name in man, f"{name} must be marked accepts_combined"


def test_repl_falls_back_but_prefers_the_manifest():
    """`_COMBINED_OK` is a fallback; `load_commands` must overwrite it from the
    manifest so the REPL can never lag pdfdrill's real capabilities."""
    chat = (ROOT / "tools" / "drillui_chat.py").read_text(encoding="utf-8")
    assert "accepts_combined" in chat, "the REPL must read the manifest field"
    assert "_COMBINED_OK.update(" in chat, "it must replace the fallback set"
