"""469 — --profile sets the formula rule and nothing else."""
import ast, json, sys, pathlib, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest
from pdfdrill import commands, report_tex as rt

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_the_two_profiles_and_the_default():
    assert commands.INKREPORT_PROFILES == {"internal": "unresolved",
                                           "published": "none"}
    assert commands.INKREPORT_PROFILE_DEFAULT == "internal"
    # every value is a rule report_tex actually accepts
    for rule in commands.INKREPORT_PROFILES.values():
        assert rule in rt.FORMULA_RULES


def test_an_unknown_profile_is_refused_before_anything_is_spent(tmp_path):
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    msg = commands.cmd_inkreport(pdf, profile="quick")
    assert "--profile must be one of internal, published" in msg
    # nothing was written beside the document
    assert not (tmp_path / "report.build.json").exists()


def test_a_profile_sets_the_formula_rule_AND_NOTHING_ELSE():
    """The claim in the name, checked against the source rather than trusted.

    `cmd_inkreport` must use `rule` only as the `formulas=` argument of its two
    builds. A profile that also reached for the paper size or the legend would
    make "which profile built this" a question about behaviour instead of one
    field.
    """
    src = ast.parse((ROOT / "src" / "pdfdrill" / "commands.py")
                    .read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(src)
              if isinstance(n, ast.FunctionDef) and n.name == "cmd_inkreport")
    uses = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and node.id == "rule" and \
                isinstance(node.ctx, ast.Load):
            uses.append(node)
    # Every load of `rule` is the value of one of these keywords:
    #   formulas=      the two builds — what the profile SETS
    #   formula_rule=  the resume test (463) — CONSULTING the same rule to
    #                  decide whether a measurement of a differently-shaped
    #                  report may be reused. Reading the rule is not setting a
    #                  second thing.
    # plus the one line that prints the PROFILE header.
    ALLOWED = {"formulas", "formula_rule"}
    kw_uses = [k for n in ast.walk(fn) if isinstance(n, ast.Call)
               for k in n.keywords
               if k.arg in ALLOWED and isinstance(k.value, ast.Name)
               and k.value.id == "rule"]
    builds = [k for k in kw_uses if k.arg == "formulas"]
    # 557 — THREE builds now, not two. Phase 1, phase 2, and the RESTORE that
    # `_bail` runs when a measurement fails: step 2 has already replaced
    # report.pdf with a legend-off phase-1 build, and returning that as the
    # published artefact is what the 557 sweep did to six of nine documents.
    # The restore is a phase-2 build and must therefore take the same rule.
    assert len(builds) == 3, "every build must take the rule, not some of them"
    assert len(uses) == len(kw_uses) + 1, [ast.dump(u) for u in uses]


def test_every_build_in_inkreport_takes_the_rule_AND_the_shape():
    """561's defect, as an invariant rather than a memory.

    The rule was passed to both builds on purpose and the SHAPE was passed to
    neither, so `findings` defaulted False in both: internally consistent, and
    not what gets published. 539 measured the result — all 21 published
    documents had an ink measured against a differently-shaped report. A build
    inside `cmd_inkreport` that takes one and not the other is that defect
    coming back.
    """
    src = ast.parse((ROOT / "src" / "pdfdrill" / "commands.py")
                    .read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(src)
              if isinstance(n, ast.FunctionDef) and n.name == "cmd_inkreport")
    calls = [n for n in ast.walk(fn)
             if isinstance(n, ast.Call)
             and getattr(n.func, "id", getattr(n.func, "attr", "")) == "cmd_reporttex"]
    assert calls, "cmd_inkreport builds no report"
    for c in calls:
        kw = {k.arg: k.value for k in c.keywords}
        assert isinstance(kw.get("formulas"), ast.Name) and kw["formulas"].id == "rule", \
            "a build without formulas=rule"
        assert isinstance(kw.get("findings"), ast.Name) and kw["findings"].id == "findings", \
            "a build without findings=findings — 561"


def _doc(tmp_path):
    tp = tmp_path / "doc.tiddlers.json"
    tp.write_text(json.dumps([
        {"title": "doc_FO_001", "latex": "x^2", "page": 1},
        {"title": "doc_FO_002", "latex": "a & b", "page": 2},
        {"title": "doc_EQ_001", "latex": "a=b", "page": 1, "confidence": 0.9},
    ]))
    return tp


def test_published_omits_the_rows_but_NOT_the_count(tmp_path):
    out = tmp_path / "report.tex"
    r = rt.build_report(_doc(tmp_path), out=out, formulas="none")
    tex = out.read_text()
    assert r["formulas"] == 0
    assert "Inline formulas" not in tex          # no section
    assert "section omitted; 1 did not render" in tex   # but the fact remains


def test_published_says_so_when_everything_rendered(tmp_path):
    tp = tmp_path / "doc.tiddlers.json"
    tp.write_text(json.dumps([{"title": "doc_FO_001", "latex": "x^2",
                               "page": 1}]))
    out = tmp_path / "report.tex"
    rt.build_report(tp, out=out, formulas="none")
    assert "section omitted; all rendered" in out.read_text()


def test_internal_keeps_the_rows_that_did_not_render(tmp_path):
    out = tmp_path / "report.tex"
    r = rt.build_report(_doc(tmp_path), out=out, formulas="unresolved")
    assert r["formulas"] == 1
    assert "Inline formulas that did not render (1 of 2)" in out.read_text()


def test_the_build_stamp_records_which_rule_built_it(tmp_path):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    stamp = rt.write_build_stamp(pdf, legend=True, ink_adopted=True,
                                 prefer_refined=False, filters={},
                                 formula_rule="none")
    assert stamp["formula_rule"] == "none"
    on_disk = json.loads((tmp_path / rt.BUILD_STAMP).read_text())
    assert on_disk["formula_rule"] == "none"


def test_the_profile_is_declared_in_the_manifest():
    import yaml
    man = yaml.safe_load((ROOT / ".claude" / "skills" / "pdfdrill"
                          / "commands.yaml").read_text(encoding="utf-8"))
    cmd = next(c for c in man["commands"] if c["name"] == "inkreport")
    flags = {f["flag"] for f in cmd.get("flags", [])}
    assert "--profile" in flags
