"""
Preflight attestation gate: an LLM that did not read the SKILL to the end cannot
run pdfdrill's build/cost commands, so it can't silently produce trusted-but-wrong
output. Proof-of-reading = a token printed as the LAST line of SKILL.md
(catches truncation/skimming); the gate blocks build/cost commands until the LLM
acknowledges that token; read-only bootstrap commands stay open.

See docs/superpowers/specs/2026-07-14-preflight-attestation-gate.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import preflight as PF


SKILL = """# pdfdrill
Some prose the LLM must read.
- rule one
- rule two

<!-- PREFLIGHT-TOKEN:BEGIN -->
Attestation token (last line — prove you read to here): DRILL-PLACEHOLDER
<!-- PREFLIGHT-TOKEN:END -->
"""


def test_token_is_deterministic_and_ignores_its_own_region():
    t1 = PF.compute_token(SKILL)
    # re-rendering the token block must not change the computed token (the token
    # region is excluded from the hash — otherwise it could never be stable)
    rendered = PF.render_token_block(SKILL)
    assert PF.compute_token(rendered) == t1
    assert t1.startswith("DRILL-") and len(t1) == len("DRILL-") + 8


def test_render_writes_the_token_as_last_meaningful_line():
    rendered = PF.render_token_block(SKILL)
    token = PF.compute_token(rendered)
    assert token in rendered
    assert rendered.rstrip().endswith(PF.TOKEN_END)          # region closes the file
    # the token line inside the region carries the real token
    assert any(token in line for line in rendered.splitlines())


def test_skill_change_changes_token():
    changed = SKILL.replace("rule two", "rule two — NEW important rule")
    assert PF.compute_token(changed) != PF.compute_token(SKILL)


def test_attest_roundtrip_and_wrong_token(tmp_path, monkeypatch):
    rendered = PF.render_token_block(SKILL)
    token = PF.compute_token(rendered)
    monkeypatch.setattr(PF, "skill_text", lambda: rendered)
    monkeypatch.setattr(PF, "marker_dir", lambda: tmp_path)
    assert PF.is_attested() is False
    assert PF.attest("DRILL-wrong0") is False                # wrong token → no marker
    assert PF.is_attested() is False
    assert PF.attest(token) is True                          # correct token → attested
    assert PF.is_attested() is True


def test_attestation_invalidated_when_skill_changes(tmp_path, monkeypatch):
    rendered = PF.render_token_block(SKILL)
    token = PF.compute_token(rendered)
    monkeypatch.setattr(PF, "skill_text", lambda: rendered)
    monkeypatch.setattr(PF, "marker_dir", lambda: tmp_path)
    PF.attest(token)
    assert PF.is_attested() is True
    # SKILL changes → old marker token no longer matches → must re-attest
    monkeypatch.setattr(PF, "skill_text",
                        lambda: PF.render_token_block(SKILL.replace("rule two", "rule 2 CHANGED")))
    assert PF.is_attested() is False


def test_gate_blocks_build_allows_bootstrap():
    assert PF.is_gated("model") and PF.is_gated("mathpix") and PF.is_gated("latex")
    assert PF.is_gated("tiddlers") and PF.is_gated("make")
    # read-only bootstrap / introspection stay open
    for cmd in ("preflight", "doctor", "help", "size", "pdfinfo", "config",
                "skill", "steps", "plan", "status"):
        assert not PF.is_gated(cmd), f"{cmd} should be exempt"


def test_env_bypass(monkeypatch):
    monkeypatch.setenv("PDFDRILL_NO_PREFLIGHT", "1")
    assert PF.enforced() is False                            # gate disabled entirely


def test_bundled_skill_token_is_not_stale():
    """Drift gate: the token printed in the real bundled SKILL.md must equal the
    checksum pdfdrill recomputes from it — i.e. `skillsync` was re-run after any
    SKILL edit. A stale token would make the whole SKILL unattestable."""
    text = PF.skill_text()
    assert text, "no bundled SKILL.md found"
    assert PF.TOKEN_BEGIN in text and PF.TOKEN_END in text, "SKILL has no token block"
    printed = None
    for line in text.splitlines():
        if line.strip().startswith("DRILL-") and len(line.strip()) == len("DRILL-") + 8:
            printed = line.strip()
    assert printed == PF.expected_token(), (
        f"stale token: SKILL prints {printed}, checksum is {PF.expected_token()} "
        f"— re-run `python3 tools/skillsync.py all .`")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
