r"""`pdfdrill latex` writes each formula where it stands. No transclusion array.

OWNER, 2026-11-12: "please me try to explain and clear some misunderstanding
related to the transclusion array in LaTeX, this was an example from my first
days working with transclusions (3 years ago). There is no need to have
transclusions in the LaTeX code."

So the `\Expr` array was never a design — it was an example that became the
default. It is also the one thing that stopped the output compiling at all.
MEASURED on BH2 (5,214 math objects), xelatex on the preamble ALONE:

      100 array rows    0.7 s
      500 array rows    2.0 s
    1 500 array rows   23.5 s
    5 202 array rows  > 300 s, no page produced

x3 rows -> x12 time. `readarray` is quadratic in the number of formulas, so the
DEFAULT output could not reach page one on any formula-heavy document, and
every compiling measurement of BH2 needed `--no-transclude`.

TRANSCLUSION INSIDE THE DOCMODEL IS A DIFFERENT THING AND STAYS. It is what
keeps formulas out of the prose stream, which is why `translate` can send prose
to DeepL and get it back with the mathematics intact (BH2: 824 prose fields
translated, 5,214 math objects untouched). The owner's words: "The docmodel can
export to Deepl.com and import the results as long we have transclusion inside
the docmodel and the text send to deepl.com." Nothing here touches that.

`--transclude` keeps the old behaviour reachable rather than deleting it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject            # noqa: E402
from pdfdrill import model_io                            # noqa: E402
from pdfdrill.commands import cmd_latex                   # noqa: E402
from pdfdrill.sidecar import Sidecar                      # noqa: E402

BODY = r"\alpha + \beta = \gamma"


def _drilled(tmp_path):
    home = tmp_path / "doc"
    home.mkdir(parents=True, exist_ok=True)
    pdf = home / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.7 stub\n%%EOF\n")
    doc = Document()
    doc.meta["bibkey"] = "doc"
    doc.meta["num_pages"] = 1
    doc.meta["pages"] = [{"page": 1, "page_width": 1000, "page_height": 1400}]
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "flow_index": 1, "page": 1, "text": "Prose around the mathematics."}))
    doc.add(DocObject(type="Formula", id="f1", props={
        "flow_index": 2, "page": 1, "latex": BODY, "display": True}))
    sc = Sidecar(pdf)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    model_io.save_model(sc.blob_dir / "model.docmodel.json", doc)
    sc.set_evidence("pages", 1)
    sc.add_fact("MODEL_BUILT")
    sc.save()
    return pdf, sc


def _tex(sc):
    return (sc.blob_dir / "latex" / "doc.tex").read_text(encoding="utf-8")


def test_the_default_builds_no_transclusion_array(tmp_path):
    pdf, sc = _drilled(tmp_path)
    cmd_latex(pdf)
    tex = _tex(sc)
    for construct in ("filecontents", "readarray", "\\MathExpr", "\\Expr"):
        assert construct not in tex, f"{construct} is still in the default output"


def test_the_formula_is_written_where_it_stands(tmp_path):
    """Not a lookup into an array — the body itself, like `md` already does."""
    pdf, sc = _drilled(tmp_path)
    cmd_latex(pdf)
    assert BODY in _tex(sc), _tex(sc)[-600:]


def test_the_default_output_has_no_formulas_dat_beside_it(tmp_path):
    pdf, sc = _drilled(tmp_path)
    cmd_latex(pdf)
    assert not list((sc.blob_dir / "latex").glob("*.formulas.dat")), \
        "the array data file is still written"


def test_transclude_opts_back_in(tmp_path):
    """Kept reachable, not deleted: the mechanism is three years of work and
    the owner called it unnecessary here, not wrong everywhere."""
    pdf, sc = _drilled(tmp_path)
    cmd_latex(pdf, transclude=True, force=True)
    tex = _tex(sc)
    assert "readarray" in tex and "filecontents" in tex, tex[:400]


def test_no_transclude_still_means_what_it_says(tmp_path):
    """Scripts that already pass it keep working, and it is NOT a silent no-op:
    it states the behaviour it gets."""
    pdf, sc = _drilled(tmp_path)
    cmd_latex(pdf, transclude=False, force=True)
    assert "readarray" not in _tex(sc)
