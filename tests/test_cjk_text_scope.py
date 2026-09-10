r"""662 — the 12 cases that discriminate the text-scoped `cjk_defect` from
the run-length-only gate task 617 built.

Two independent discriminators now combine (see report_tex.cjk_defect's
docstring for the full decision table over (inside a `CJK_TEXT_MACROS`
argument, or not) x (IDC / `\zh` / run < CJK_RUN_MIN / run >= CJK_RUN_MIN)):
an IDC or `\zh` refuses everywhere (unscoped); a run of CJK_RUN_MIN or more
was already permitted everywhere by 617 and stays permitted; the ONE cell
this task changes is a SHORT run (what the old code called "isolated")
sitting inside real text mode — `\text{中}` and siblings — which used to be
refused for being short and is now permitted for being text.

Rule 17: a fixture with no character actually inside a text span cannot
discriminate the new gate from the old one — cases 5, 6, 10 and 12 below
each place at least one CJK character inside a `CJK_TEXT_MACROS` argument,
which is the shape the old (task 617) gate never distinguished.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.report_tex import cjk_defect


def refused(latex):
    return cjk_defect(latex) != ""


# 1. IDC inside \text{} -- still REFUSED. The auditor's pinned case: an IDC
#    is a recipe, not a glyph, regardless of which macro happens to wrap it.
def test_1_idc_inside_text_is_still_refused():
    assert refused(r"\text{⿱ 日 一}")


# 2. IDC outside any text span (bare math) -- REFUSED, unchanged from 617.
def test_2_idc_bare_is_refused():
    assert refused(r"x = ⿱ 日 一")


# 3. \zh inside \text{} -- REFUSED. Unscoped for the same reason as the IDC:
#    it marks HOW the value was produced, not WHERE the OCR placed it.
def test_3_zh_inside_text_is_refused():
    assert refused(r"\text{\zh{x}}")


# 4. \zh outside any text span -- REFUSED, unchanged (existing pin in
#    test_cjk_validator.py, repeated here as a decision-table cell).
def test_4_zh_bare_is_refused():
    assert refused(r"a + \zh{x}")


# 5. A SHORT run (here: one character) inside \text{} -- PERMITTED. This is
#    the cell 662 actually changes: `\text{中}` is one ordinary Chinese
#    character in a sentence, not a decomposition (the decomposition path
#    emits bare IDCs in math mode, not characters wrapped in \text{}).
def test_5_isolated_ideograph_inside_text_is_permitted():
    assert not refused(r"\text{中}")


# 6. A short run inside \mbox{} -- PERMITTED. Confirms the text-scoping
#    macro list is not `\text` alone.
def test_6_isolated_ideograph_inside_mbox_is_permitted():
    assert not refused(r"\mbox{文}")


# 7. A short run bare in math, no macro at all -- REFUSED, unchanged from
#    617: this is exactly the decomposition shape (isolated characters,
#    zero multi-character runs) that motivated CJK_RUN_MIN in the first
#    place.
def test_7_isolated_ideograph_bare_is_refused():
    assert refused(r"x = 中")


# 8. \mathrm{中} -- still REFUSED. The auditor's other pinned case:
#    `\mathrm` selects a math alphabet, not text mode, so a single
#    ideograph inside it is "outside a text span" by this table even
#    though it sits inside SOME macro's braces.
def test_8_mathrm_cjk_is_still_refused():
    assert refused(r"\mathrm{中}")


# 9. \operatorname{中} -- REFUSED. The judgement call this task had to make:
#    `\operatorname` is in the SAME family as `\mathrm` (a math-alphabet
#    selector for a symbol/operator name, not prose), so report_tex.py's
#    CJK_TEXT_MACROS deliberately excludes it even though
#    text_escapes.TEXT_IN_MATH (a font question, not a content question)
#    keeps it for tools/audit_glyph_sites.py's own, different purpose.
def test_9_operatorname_cjk_is_refused():
    assert refused(r"\operatorname{中}")


# 10. A run of CJK_RUN_MIN (3) or more inside \text{} -- PERMITTED. Was
#     already permitted by 617's run-length rule alone; text-scoping cannot
#     make it MORE permitted, so this cell is unchanged in outcome even
#     though a text span now exists around it.
def test_10_long_run_inside_text_is_permitted():
    assert not refused(r"\text{对零件跳过检测}")


# 11. A run of CJK_RUN_MIN or more bare in math -- PERMITTED, unchanged from
#     617 (the original motivating case: genuine Chinese is nothing but
#     runs, and MathPix sometimes emits it without a \text{} wrapper).
def test_11_long_run_bare_is_permitted():
    assert not refused(r"判别式法")


# 12. Two ideographs split across a text-span boundary: one immediately
#     inside \text{}, the next immediately outside it. cjk_runs breaks the
#     run at the closing brace (a non-CJK character), so BOTH are "short
#     runs" (length 1) individually -- the case that actually exercises
#     per-character scoping rather than whole-string scoping. The inside
#     character is permitted and the outside one is refused, so the value
#     as a whole is still refused, and the message names the OUTSIDE
#     character (文, U+6587), not the permitted one (中, U+4E2D).
def test_12_split_across_text_span_boundary_refuses_on_the_outside_char():
    r = cjk_defect(r"\text{中}文")
    assert r != ""
    assert "U+6587" in r        # 文 -- the refused, out-of-span character
    assert "U+4E2D" not in r    # 中 -- the permitted, in-span character


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
