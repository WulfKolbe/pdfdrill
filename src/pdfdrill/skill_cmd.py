"""
pdfdrill.skill_cmd — read-only `skill` subcommand (additive; never touches the
LLM-facing extraction contract).

Makes pdfdrill self-contained for its SKILL folder. The canonical
`.claude/skills/pdfdrill/` (SKILL.md + commands.yaml, the single source of truth)
is BUNDLED as package data under `src/pdfdrill/skill/`, so even where the repo's
`.claude/` is not mounted (an installed wheel, a fresh sandbox) pdfdrill still
*contains the SKILL folder completely* and can regenerate or serve it.

  pdfdrill skill --emit DIR   write the complete SKILL folder to DIR
                              (when no SKILL.md is present, pdfdrill provides it)
  pdfdrill skill --json       print the typed command manifest as JSON
                              (drillui / any wrapper consumes this)
  pdfdrill skill --check      manifest <-> live HANDLERS parity (nonzero on drift)
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

# Prefer the bundled copy (works from an installed wheel); fall back to the
# repo's canonical .claude/ folder in a source checkout.
_BUNDLED = Path(__file__).with_name("skill")
_REPO_SKILL = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "pdfdrill"


def _skill_dir() -> Path:
    if (_BUNDLED / "commands.yaml").exists():
        return _BUNDLED
    return _REPO_SKILL


def _load_manifest(d: Path) -> dict:
    import yaml
    return yaml.safe_load((d / "commands.yaml").read_text())


def _handler_names() -> set[str]:
    from . import cli
    return set(getattr(cli, "HANDLERS", {}).keys())


def run(args: list[str]) -> str:
    d = _skill_dir()

    if "--emit" in args:
        i = args.index("--emit")
        dest = Path(args[i + 1]) if i + 1 < len(args) else Path(".claude/skills/pdfdrill")
        dest.mkdir(parents=True, exist_ok=True)
        n = 0
        for f in sorted(d.iterdir()):
            if f.is_file():
                shutil.copy2(f, dest / f.name)
                n += 1
        return f"emitted complete SKILL folder ({n} files) to {dest}"

    if "--json" in args:
        print(json.dumps(_load_manifest(d), ensure_ascii=False))
        return ""

    if "--check" in args:
        man = _load_manifest(d)
        man_names = {c["name"] for c in man["commands"]}
        live = _handler_names()
        missing = sorted(live - man_names)        # handler exists, manifest doesn't list it
        stale = sorted(man_names - live)          # manifest lists a non-existent command
        if missing or stale:
            print(f"DRIFT: missing_in_manifest={missing} stale_in_manifest={stale}",
                  file=sys.stderr)
            raise SystemExit(1)
        return f"skill manifest in sync ({len(man_names)} commands)"

    return (f"bundled SKILL folder: {d}\n"
            f"  commands.yaml: {(d / 'commands.yaml').exists()}   "
            f"SKILL.md: {(d / 'SKILL.md').exists()}\n"
            f"  pdfdrill skill --emit DIR | --json | --check")
