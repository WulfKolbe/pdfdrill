"""spec 2026-09-06, task 10 (+ fix round) — report, breport, inkreport are
thin aliases of evidence/residuals; `report` and `breport` and `inkreport`'s
default path actually route there, removal is a later task. `reporttex` is
NOT an alias — it stays the ink chain's measure build (`_inkreport_chain`
depends on its legend/formula-rule/findings/pages-refusal/ink_bullets/
cellrect behaviour, none of which `evidence` has an equivalent for) — and is
tracked separately in `commands.SUPERSEDED`.
"""
import yaml

from pdfdrill import commands as C


def test_alias_table_names_the_three():
    assert set(C.ALIASES) == {"report", "breport", "inkreport"}
    assert C.alias_note("breport").startswith("breport is an alias of residuals --pdf")


def test_reporttex_is_superseded_not_aliased():
    assert "reporttex" not in C.ALIASES
    assert C.SUPERSEDED == {"reporttex": "evidence --all-kinds --pdf"}


def test_manifest_summaries_say_alias_of():
    d = yaml.safe_load(open(".claude/skills/pdfdrill/commands.yaml"))
    by = {c["name"]: c for c in d["commands"]}
    for name, target in C.ALIASES.items():
        assert by[name]["summary"].startswith("ALIAS of %s" % target.split(" /")[0]), name


def test_manifest_summary_says_superseded_for_reporttex():
    d = yaml.safe_load(open(".claude/skills/pdfdrill/commands.yaml"))
    by = {c["name"]: c for c in d["commands"]}
    assert by["reporttex"]["summary"].startswith("SUPERSEDED")


def test_report_alias_writes_the_old_file_name(tmp_path, monkeypatch):
    """`report` used to write formula-report.html; keep that name as a copy."""
    import pdfdrill.commands as mod
    calls = []
    monkeypatch.setattr(mod, "cmd_evidence",
                        lambda pdf, **kw: calls.append(kw) or "ok")
    (tmp_path / "evidence-formula.html").write_text("<html>")
    (tmp_path / "D.pdf").write_bytes(b"%PDF-1.4\n")
    out = mod.cmd_report(tmp_path / "D.pdf")
    assert [c["kind"] for c in calls] == ["formula", "equation"]
    assert (tmp_path / "formula-report.html").read_text() == "<html>"
    assert "alias" in out
