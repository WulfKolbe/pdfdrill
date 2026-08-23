r"""124 — a form-field build gate.

hyperref's \TextField / \CheckBox produce NOTHING outside a
\begin{Form}...\end{Form} environment, and say nothing about it. Measured on the
three-field fixture below: dropping the two Form lines leaves pdflatex exiting
0, with 0 errors, writing a 13.8 KB PDF, and read_form_fields returning 0 fields
and NO error. Both "form" matches in the log are incidental (`format=pdflatex`,
"Key value format"). Every signal a caller would normally trust reports success.

A silent zero cannot be caught downstream — an empty form is indistinguishable
from a document that never had one — so the count is asserted at BUILD time
against what the source declared.

Note also what this file adds beyond the gate: docs/CLAUDE-FULL.md records the
3-field AcroForm round-trip as "verified end-to-end", but the suite carried only
the NEGATIVE case (test_read_form_fields_no_form). read_form_fields returning 0
for a real form would have been caught by nothing.
"""
import shutil, subprocess, sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.pdf_reading import (assert_form_fields, read_form_fields,
                                  FormFieldMismatch)

#: three field-producing commands — the number the gate is asserted against
FORM_BODY = r"""
\TextField[name=city,width=4cm]{City: }\par
\TextField[name=street,width=4cm]{Street: }\par
\CheckBox[name=paid]{Paid: }
"""
DOC = r"""\documentclass{article}
\usepackage[T1]{fontenc}
\usepackage{hyperref}
\begin{document}
%s
\end{document}
"""

pytestmark = pytest.mark.skipif(shutil.which("pdflatex") is None,
                                reason="pdflatex not installed")


def _build(tmp_path: Path, body: str, name: str) -> Path:
    tex = tmp_path / f"{name}.tex"
    tex.write_text(DOC % body, encoding="utf-8")
    subprocess.run(["pdflatex", "-interaction=nonstopmode", tex.name],
                   cwd=tmp_path, capture_output=True, timeout=300)
    return tmp_path / f"{name}.pdf"


def test_gate_passes_when_the_form_environment_is_present(tmp_path):
    pdf = _build(tmp_path, r"\begin{Form}" + FORM_BODY + r"\end{Form}", "good")
    assert pdf.is_file()
    assert assert_form_fields(pdf, 3, context="good") == 3


def test_the_round_trip_the_docs_claimed_but_never_tested(tmp_path):
    """Field names, types and checkbox options actually survive the build."""
    pdf = _build(tmp_path, r"\begin{Form}" + FORM_BODY + r"\end{Form}", "good")
    fields, err = read_form_fields(pdf)
    assert err is None
    by = {f["name"]: f for f in fields}
    assert set(by) == {"city", "street", "paid"}
    assert by["city"]["type"] == "text"
    assert by["paid"]["type"] == "button/checkbox"
    assert "/Yes" in by["paid"]["options"]


def test_gate_fires_when_begin_Form_is_missing(tmp_path):
    """The whole point. Same three commands, no Form environment: the build
    SUCCEEDS and produces zero fields, so only the gate can catch it."""
    pdf = _build(tmp_path, FORM_BODY, "bad")
    assert pdf.is_file(), "pdflatex still writes a PDF — that is the trap"
    fields, err = read_form_fields(pdf)
    assert (len(fields), err) == (0, None), "silent zero is the expected shape"
    with pytest.raises(FormFieldMismatch) as e:
        assert_form_fields(pdf, 3, context="bad")
    msg = str(e.value)
    assert "expected 3" in msg and "found 0" in msg
    assert "begin{Form}" in msg, "the message must name the likely cause"


def test_gate_fires_on_a_partial_shortfall(tmp_path):
    """Not only the zero case: two fields where three were declared must fail
    too, or the gate would only catch the total-loss version."""
    body = r"\begin{Form}" + FORM_BODY.replace(
        r"\CheckBox[name=paid]{Paid: }", "") + r"\end{Form}"
    pdf = _build(tmp_path, body, "partial")
    with pytest.raises(FormFieldMismatch) as e:
        assert_form_fields(pdf, 3, context="partial")
    assert "found 2" in str(e.value)
    assert assert_form_fields(pdf, 2, context="partial") == 2


def test_gate_reports_a_read_error_rather_than_passing(tmp_path):
    """A PDF that cannot be read must FAIL the gate, not satisfy it by
    returning an empty list."""
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf at all")
    with pytest.raises(FormFieldMismatch):
        assert_form_fields(broken, 3, context="broken")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
