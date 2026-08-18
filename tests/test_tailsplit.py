"""P7 — prose tails inside math regions split into <id> + <id>.tail.

Census that scoped this (2026-08-18): 36 display equations across
bh2/BH1org/WDorg4 carry a tail, 0 of 12,253 inline formulas — a contained
cleanup, not the main work.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.mathqc import text_tail, _collapse_letters

USER_EXAMPLE = (r"\mathrm{n a c h\;A d d i t i o n}\;"
                r"\underset{n_{1}}{\overset{v}{\boldsymbol{S}}}\varphi\eth n+"
                r"\underset{v+1}{\overset{n_{2}}{\boldsymbol{S}}}\varphi\eth n"
                r"=\phi(n_{2})-\phi(n_{1}-1),\;\mathrm{w a s~i m~V e r-}")


def test_user_example_has_lead_and_trail():
    lead, trail = text_tail(USER_EXAMPLE)
    assert lead and "n a c h" in lead
    assert trail and "V e r-" in trail
    assert _collapse_letters(r"n a c h\;A d d i t i o n") == "nach Addition"


def test_math_notation_is_not_a_tail():
    assert text_tail(r"x = \mathrm{const}") == (None, None)
    assert text_tail(r"\mathrm{d}x") == (None, None)
    assert text_tail(r"x_{5}") == (None, None)
    # mid-string connector text is not a LEAD or TRAIL
    assert text_tail(r"a=b \text { und } c=d") == (None, None)


def test_cmd_tailsplit_splits_and_is_idempotent():
    from docmodel.core import Document, DocObject
    from pdfdrill.model_io import save_model
    from pdfdrill.commands import cmd_tailsplit, _model_path
    from pdfdrill.sidecar import Sidecar

    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        doc = Document()
        eq = DocObject(type="Equation",
                       props={"latex": USER_EXAMPLE, "page": "007"})
        doc.add(eq)
        sc = Sidecar(pdf)
        mp = _model_path(sc)
        mp.parent.mkdir(parents=True, exist_ok=True)
        save_model(mp, doc)

        out = cmd_tailsplit(pdf)
        assert "1 math region(s) split" in out
        from pdfdrill.model_io import load_model
        doc2 = load_model(mp)
        tail = doc2.objects[f"{eq.id}.tail"]
        assert tail.type == "MathTail"
        assert "nach Addition" in tail.props["text"]
        assert "Ver-" in tail.props["text"]
        src = doc2.objects[eq.id]
        assert "mathrm" not in src.props["latex"]          # tail stripped
        assert src.props["latex_pretail"] == USER_EXAMPLE  # original kept

        out2 = cmd_tailsplit(pdf)
        assert "0 math region(s) split" in out2 and "already split" in out2
