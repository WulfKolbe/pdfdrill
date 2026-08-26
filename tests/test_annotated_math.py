"""202 — the annotated_math selector.

Mathematics inside a delimiter pair with text or arrows OUTSIDE it. Every
other selector fills one field; this one fills two and they are COMPOSED, not
chosen between.
"""
from pdfdrill import openai_vision as ov
from pdfdrill import svg

ARR = r"\left[\begin{array}{cc} 1 & 0 \\ 0 & 1 \end{array}\right]"
OVL = r"\draw[->] (M.east) -- ++(1,0) node[right] {$R_2-R_1$};"


def test_selector_is_offered_to_the_model():
    assert "annotated_math" in ov.DEFAULT_PROMPT
    assert "|annotated_math|" in ov.DEFAULT_PROMPT


def test_both_fields_are_in_the_structured_schema():
    props = ov._SCHEMA["schema"]["properties"]
    assert "annotated_math" in props and "annotation_overlay" in props


def test_the_rule_forbids_folding_the_annotation_into_the_array():
    """out/189 found a row-reduction where the arrow had been read INTO a
    cell: `0 & 0 & \\uparrow-1 & 1 & 0`. That is the failure this prevents."""
    assert "Do NOT copy the annotation into the array" in ov.DEFAULT_PROMPT


def test_composition_keeps_BOTH_parts():
    out = ov.compose_annotated_math(ARR, OVL)
    assert "\\begin{array}" in out          # the mathematics survives
    assert "R_2-R_1" in out                 # and so does the annotation
    assert out.startswith("\\begin{tikzpicture}")


def test_the_maths_becomes_the_node_the_overlay_refers_to():
    out = ov.compose_annotated_math(ARR, OVL)
    assert "(M)" in out and "(M.east)" in out


def test_a_full_tikzpicture_overlay_is_unwrapped_not_nested():
    """The model often returns a complete picture. Nesting one inside another
    compiles to the wrong thing."""
    out = ov.compose_annotated_math(ARR, r"\begin{tikzpicture}" + OVL + r"\end{tikzpicture}")
    assert out.count("\\begin{tikzpicture}") == 1


def test_no_overlay_returns_bare_maths_not_an_empty_picture():
    """A node with nothing drawn around it would be a tikzpicture pretending
    to be an annotation."""
    assert ov.compose_annotated_math(ARR, "") == ARR


def test_no_maths_returns_the_overlay():
    assert ov.compose_annotated_math("", OVL) == OVL


def test_result_to_latex_dispatches_the_pair():
    sel, code = ov.result_to_latex({"selector": "annotated_math",
                                    "annotated_math": ARR,
                                    "annotation_overlay": OVL})
    assert sel == "annotated_math"
    assert "\\begin{array}" in code and "R_2-R_1" in code


def test_the_composed_snippet_routes_by_the_existing_tikz_path():
    """It begins with \\begin{tikzpicture}, so svg.py already renders it —
    no new plumbing."""
    assert svg.is_latex_graphic(ov.compose_annotated_math(ARR, OVL))


def test_plain_math_is_untouched_by_the_new_branch():
    sel, code = ov.result_to_latex({"selector": "math", "math": "$x^2$"})
    assert (sel, code) == ("math", "x^2")
