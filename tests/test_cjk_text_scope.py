r"""662 — the cases that discriminate the text-scoped `cjk_defect` from
task 617's run-length-only gate, AND from 662's own first (fixed) attempt.

Two independent discriminators combine (see report_tex.cjk_defect's
docstring for the full decision table over (does the character's entire
run sit inside a `CJK_TEXT_MACROS` argument) x (IDC / `\zh` / run == 1 /
CJK_TEXT_RUN_MIN <= run < CJK_RUN_MIN / run >= CJK_RUN_MIN): an IDC or
`\zh` refuses everywhere (unscoped); a run of CJK_RUN_MIN (3) or more was
already permitted everywhere by 617 and stays permitted; a SINGLE stray
ideograph (run == 1) refuses everywhere, INCLUDING inside a text span —
662's fix-round-1 correction, after a real document (BH1org_OCR) showed
"inside `\text{}`" has zero discriminating power for a run of exactly one
on a non-Chinese document. The ONE cell 662 actually relaxes: a run of
exactly CJK_TEXT_RUN_MIN (2) inside a text span, which a bare-math run of
two still refuses — text-scoping LOWERS the bar inside text mode, it does
not remove it.

Rule 17: a fixture with no character actually inside a text span cannot
discriminate the new gate from the old one — cases 5, 6, 10, 12 and 13
below each place at least one CJK character inside a `CJK_TEXT_MACROS`
argument.
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


# 5. A SINGLE stray ideograph (run == 1) INSIDE \text{} -- still REFUSED.
#    662's fix-round-1 correction: an earlier version of this gate
#    permitted this cell unconditionally, on the premise that "inside
#    \text{}" is itself evidence of prose. BH1org_OCR (a German physics OCR
#    book, no genuine Chinese content anywhere) falsified that premise
#    directly: all 3 of its real CJK-in-text occurrences were run-length
#    ONE, and all 3 were OCR/MathPix failing on an unidentified symbol, not
#    prose. So "inside \text{}" alone is not enough; the run-length rule
#    keeps refusing a lone character in EITHER location.
def test_5_single_ideograph_inside_text_is_still_refused():
    assert refused(r"\text{中}")


# 6. A single stray ideograph inside \mbox{} -- still REFUSED. Confirms the
#    correction applies across the whole text-macro list, not just \text.
def test_6_single_ideograph_inside_mbox_is_still_refused():
    assert refused(r"\mbox{文}")


# 7. A single stray ideograph bare in math, no macro at all -- REFUSED,
#    unchanged from 617: the original decomposition shape.
def test_7_single_ideograph_bare_is_refused():
    assert refused(r"x = 中")


# 8. \mathrm{中} -- still REFUSED. The auditor's other pinned case:
#    `\mathrm` selects a math alphabet, not text mode, so a single
#    ideograph inside it is "outside a text span" by this table even
#    though it sits inside SOME macro's braces -- and hits the run == 1
#    row regardless.
def test_8_mathrm_cjk_is_still_refused():
    assert refused(r"\mathrm{中}")


# 9. \operatorname{中} -- REFUSED. The judgement call this task had to
#    make: `\operatorname` is in the SAME family as `\mathrm` (a
#    math-alphabet selector for a symbol/operator name, not prose), so
#    report_tex.py's CJK_TEXT_MACROS deliberately excludes it even though
#    text_escapes.TEXT_IN_MATH (a font question, not a content question)
#    keeps it for tools/audit_glyph_sites.py's own, different purpose.
def test_9_operatorname_cjk_is_refused():
    assert refused(r"\operatorname{中}")


# 10. A run of exactly CJK_TEXT_RUN_MIN (2) INSIDE \text{} -- PERMITTED.
#     THE cell this task actually relaxes: two consecutive ideographs
#     forming a real short word/phrase (e.g. "的确", "indeed") get credit
#     for being marked as text that the same length would not get bare in
#     math mode. A BOUNDED relaxation (one character's worth), not a
#     bypass -- contrast with case 11.
def test_10_run_of_two_inside_text_is_permitted():
    assert not refused(r"\text{的确}")


# 11. The SAME run length (2), OUTSIDE any text span -- still REFUSED.
#     Unchanged from 617: a short run bare in math gets no text-mode
#     credit. Proves the relaxation in case 10 is genuinely bounded to
#     "inside a text span", not a global lowering of CJK_RUN_MIN.
def test_11_run_of_two_bare_is_refused():
    assert refused(r"x = 两个")


# 12. A run of CJK_RUN_MIN (3) or more INSIDE \text{} -- PERMITTED. Was
#     already permitted by 617's run-length rule alone; text-scoping
#     cannot make it MORE permitted.
def test_12_long_run_inside_text_is_permitted():
    assert not refused(r"\text{对零件跳过检测}")


# 13. A run of CJK_RUN_MIN or more bare in math -- PERMITTED, unchanged
#     from 617 (the original motivating case: genuine Chinese is nothing
#     but runs, and MathPix sometimes emits it without a \text{} wrapper).
def test_13_long_run_bare_is_permitted():
    assert not refused(r"判别式法")


# 14. Two single ideographs split across a text-span boundary: one
#     immediately inside \text{}, the next immediately outside it.
#     cjk_run_spans breaks the run at the closing brace (a non-CJK
#     character), so BOTH are independently "run == 1" -- both refuse now
#     (before the fix-round-1 correction, the inside one used to be
#     wrongly permitted). Exercises per-RUN, not per-character or
#     whole-string, scoping: the returned reason names whichever run is
#     encountered FIRST in the string (中, U+4E2D), since that one now
#     refuses on its own and the walk never reaches 文.
def test_14_split_across_text_span_boundary_refuses_on_the_first_run():
    r = cjk_defect(r"\text{中}文")
    assert r != ""
    assert "U+4E2D" in r        # 中 -- the first run, now refused itself


# 15. The real BH1org_OCR rows this correction exists for (see
#     out/662.txt): all three carry a SINGLE ideograph inside a \text{}
#     argument on a document with no genuine Chinese content anywhere.
#     Must refuse.
def test_15_bh1org_ocr_matrix_slot_still_refused():
    src = (r"\left[\begin{array}{c} i \\ m \\ \text { 真 } "
           r"\end{array}\right]")
    assert refused(src)


def test_16_bh1org_ocr_stackrel_empty_text_pair_still_refused():
    src = (r"\stackrel{n}{\boldsymbol{S}}_{n_{1}} "
           r"\stackrel{\text { }}{\text { 作 }} \partial n")
    assert refused(src)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
