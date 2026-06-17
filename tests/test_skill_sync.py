"""
skill-sync drift gate (the single-source-of-truth for the command surface).

`.claude/skills/pdfdrill/commands.yaml` is canonical; `--help`, the SKILL.md
tables, the bundled wheel copy, and the external drillui TUI are generated from
it. These tests are the gate that keeps the four in lock-step: they would have
caught the historical `citedrill`/`classify` drift.
"""
import sys
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import skillsync  # noqa: E402


def _manifest():
    return yaml.safe_load((ROOT / ".claude/skills/pdfdrill/commands.yaml").read_text())


def test_manifest_matches_live_handlers():
    from pdfdrill import cli
    man = {c["name"] for c in _manifest()["commands"]}
    live = set(cli.HANDLERS.keys())
    assert man == live, (f"DRIFT — missing_in_manifest={sorted(live - man)} "
                         f"stale_in_manifest={sorted(man - live)}")


def test_skillsync_check_passes():
    assert skillsync.cmd_check(ROOT) == 0          # the CI gate, green on the repo


def test_skill_check_subcommand_in_sync():
    from pdfdrill import skill_cmd
    msg = skill_cmd.run(["--check"])
    assert "in sync" in msg


def test_bundled_skill_folder_matches_canonical():
    # the wheel copy (src/pdfdrill/skill/) must equal the canonical .claude/ folder
    canon = ROOT / ".claude/skills/pdfdrill"
    bundle = ROOT / "src/pdfdrill/skill"
    for name in ("commands.yaml", "SKILL.md"):
        assert (bundle / name).read_text() == (canon / name).read_text(), \
            f"{name} bundle drifted — run `python3 tools/skillsync.py bundle .`"


def test_generated_help_is_committed_and_current():
    gen = (ROOT / "src/pdfdrill/_help_generated.txt").read_text()
    fresh = skillsync.render_help_text(_manifest())
    assert gen == fresh, "run `python3 tools/skillsync.py render-help .` and commit"


def test_skill_md_tables_region_is_current():
    skill = (ROOT / ".claude/skills/pdfdrill/SKILL.md").read_text()
    region = skillsync.render_tables(_manifest())
    assert region in skill, "run `python3 tools/skillsync.py render-skill .` and commit"


def test_every_command_has_section_and_summary():
    for c in _manifest()["commands"]:
        assert c.get("section") and c.get("summary"), f"{c['name']} missing section/summary"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
