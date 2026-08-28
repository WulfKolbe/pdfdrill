"""254 — the equation number MathPix swept into the formula body.

1,047 `math` lines across 63 documents end with a separated, parenthesised
number and have no `equation_number` line to pair with. 29 of those documents
carry a complete numbering sequence and not one `equation_number` line, so the
number is both missing from `equation_number` AND polluting the rendered maths.

The gate is the separator: `\\quad (2.14)` / `.(106)` is a number, `S O(8)` /
`\\mathrm{Cl}(8)` / `\\mathrm{H}(2)` is algebra.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from docmodel.base_module import ModuleConfig
from docmodel.core import Document
from docmodel.modules.page import ingest_lines_json
from docmodel.modules.equation import EquationProcessor, absorbed_equation_number


@pytest.mark.parametrize("latex,num,rest", [
    # Real corpus shapes.
    (r"\[T_{t}:=m m^{\prime}=1+\frac{1}{2} t e_{\infty} .(106)\]",
     "106", r"\[T_{t}:=m m^{\prime}=1+\frac{1}{2} t e_{\infty} .\]"),
    (r"\[F_{MN} := \partial_M A_N \quad (2.14)\]",
     "2.14", r"\[F_{MN} := \partial_M A_N\]"),
    (r"u_i = \delta_{ij} u_j, \quad v_i = \delta_{ij} v_j. (1.2.1)",
     "1.2.1", r"u_i = \delta_{ij} u_j, \quad v_i = \delta_{ij} v_j."),
    (r"\[x = y \qquad (3.13b)\]", "3.13b", r"\[x = y\]"),
    (r"\[a=b~(5)\]", "5", r"\[a=b\]"),
])
def test_absorbed_numbers_are_split_off(latex, num, rest):
    assert absorbed_equation_number(latex) == (num, rest)


@pytest.mark.parametrize("latex", [
    # Glued to an identifier: a group order, not an equation number.
    r"\[S O(8) \cong S s(8)\]",
    r"\[\mathrm{Cl}(\mathrm{q}+8)=\mathrm{Cl}(\mathrm{q}) \times \mathrm{Cl}(8)\]",
    r"\[\mathrm{Cl}(6)=\mathrm{R}(8)=\mathrm{H} \times \mathrm{H}(2)\]",
    r"\[\operatorname{spin}(6) \subset \operatorname{spin}(10)\]",
    r"\[f(x)\]",
    # Nothing trailing at all.
    r"\[a = b\]",
    "",
])
def test_algebra_is_left_alone(latex):
    assert absorbed_equation_number(latex) == ("", latex)


def _doc(lines):
    doc = Document()
    for i, ln in enumerate(lines):
        ln.setdefault("id", f"l{i}")
        ln.setdefault("region", {"top_left_y": i * 40, "height": 30,
                                 "top_left_x": 0, "width": 400})
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "im-01", "lines": lines}]})
    return doc


def _items(doc):
    m = EquationProcessor(ModuleConfig(title="E", classname="E", proc_order=0), "T")
    return m.find_items(doc)


def test_recovered_when_no_equation_number_line():
    item = _items(_doc([
        {"type": "math", "text": r"\[E = m c^{2} \quad (204)\]"},
    ]))[0]
    assert item["refnum"] == "204"
    assert item["refnum_source"] == "absorbed"
    assert "(204)" not in item["latex_raw"]
    assert "(204)" not in item["latex"]


def test_a_stated_equation_number_is_never_second_guessed():
    # The number line is present, so the body is left exactly as MathPix wrote
    # it — including a trailing paren that happens to look like a number.
    item = _items(_doc([
        {"type": "math", "text": r"\[\mathrm{Cl}(8) \times \mathrm{Cl}(8)=\mathrm{Cl}(16)\]"},
        {"type": "equation_number", "text": "(7)"},
    ]))[0]
    assert item["refnum"] == "7"
    assert item["refnum_source"] == "line"
    assert item["latex_raw"].endswith(r"\mathrm{Cl}(16)\]")


def test_source_is_blank_when_no_number_is_found():
    item = _items(_doc([{"type": "math", "text": r"\[a = b\]"}]))[0]
    assert item["refnum"] == ""
    assert item["refnum_source"] == ""


def test_glued_form_is_not_harvested_as_a_number():
    item = _items(_doc([{"type": "math", "text": r"\[S O(8) \cong S s(8)\]"}]))[0]
    assert item["refnum"] == ""
    assert item["latex_raw"] == r"\[S O(8) \cong S s(8)\]"
