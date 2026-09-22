r"""773 — the 696 bracket repair, and what licenses it.

`brackets.repair()` shipped in 696 and nothing called it; the publish gate
names it in its own refusal and there was no command to obey it with.

The evidence is the author's e-print at DOCUMENT scope. On 1205.5935v1
(Chisolm, *Geometric Algebra*) that source is 6,050 lines and contains
`\left.` zero times, so no `\left.` in any reading of it is the author's.
Nine of its 28 repairable readings are multi-row `aligned` blocks MathPix
merged, which `injectlatex` never paired with a source equation — there is no
per-equation gold for them at all, and the document-scale fact covers them.
"""
import gzip
import io
import tarfile

from docmodel.core import Document, DocObject
from pdfdrill import bracketrepair as br

#: MathPix's reading of a Chisolm row: an invented `\left.` at the head, which
#: TeX then pairs with the typed `\right)` of a group whose plain `(` is left
#: unmatched. It prints correctly and the group closes in the wrong place.
#: The unmatched opener must be of the SAME TYPE as the `\right` — a paren
#: here — or 696 does not call it repairable, which is the point of counting
#: brackets per type.
MATHPIX = r"\left.\quad=\frac{1}{2}(-1)^{j-1} (a\rfloor e_j\right) e_1"
#: the same row as the author wrote it: his own `\lin` macro, no `\left.`
AUTHOR = r"\quad= \half (-1)^{j-1} (a \lin e_j) e_1"


def _tgz(tmp_path, text, name="T.tgz"):
    p = tmp_path / name
    buf = text.encode("utf-8")
    with tarfile.open(p, "w:gz") as tf:
        ti = tarfile.TarInfo("paper.tex")
        ti.size = len(buf)
        tf.addfile(ti, io.BytesIO(buf))
    return p


# --- the source ------------------------------------------------------------

def test_the_author_source_is_the_eprint(tmp_path):
    _tgz(tmp_path, AUTHOR)
    text, name = br.author_source(tmp_path)
    assert AUTHOR in text and name == "T.tgz"


def test_a_bare_gz_counts_too(tmp_path):
    """689 — arXiv serves a single-file submission as gzip(paper.tex)."""
    (tmp_path / "T.gz").write_bytes(gzip.compress(AUTHOR.encode("utf-8")))
    assert AUTHOR in br.author_source(tmp_path)[0]


def test_the_mathpix_texzip_is_never_the_author_source(tmp_path):
    r"""065/out-063: verifying a MathPix reading against MathPix's own
    reconstruction verifies the reading against itself."""
    import zipfile
    with zipfile.ZipFile(tmp_path / "T.tex.zip", "w") as zf:
        zf.writestr("deadbeef.tex", MATHPIX)
    assert br.author_source(tmp_path) == ("", "")


# --- the basis -------------------------------------------------------------

def test_the_basis_holds_when_the_author_never_writes_left_dot():
    assert br.basis_holds(AUTHOR) is True


def test_the_basis_fails_when_he_does():
    """Then 'no `\\left.` here is his' is simply false, and the repair needs
    per-equation evidence this module does not attempt."""
    assert br.basis_holds(r"x \left. y \right] z") is False


def test_an_empty_source_is_not_a_basis():
    assert br.basis_holds("") is False


# --- the candidates --------------------------------------------------------

def _doc(latex: str, type_: str = "Equation") -> Document:
    doc = Document(meta={"bibkey": "T"})
    doc.add(DocObject(id="e1", type=type_,
                      props={"flow_index": 1, "latex": latex, "page": 1}))
    return doc


def test_a_repairable_reading_is_a_candidate():
    (oid, shown, cand, pairs), = br.candidates(_doc(MATHPIX), "T.tgz")
    assert oid == "e1" and shown == MATHPIX and pairs >= 1
    assert "\\left." not in cand


def test_a_clean_reading_is_not():
    assert br.candidates(_doc(r"a = \left( b \right)"), "T.tgz") == []


def test_only_equations_and_formulas_are_considered():
    assert br.candidates(_doc(MATHPIX, "Table"), "T.tgz") == []


def test_the_repair_leaves_nothing_repairable():
    from pdfdrill import brackets
    (_oid, _s, cand, _p), = br.candidates(_doc(MATHPIX), "T.tgz")
    assert brackets.repairable(cand) is False


# --- the record ------------------------------------------------------------

def test_the_proposal_says_what_verified_it():
    """`record_one` refuses a proposal that does not, and `chosen_latex`
    shows a refinement only when that is IDENTITY evidence (686)."""
    from pdfdrill import refine
    p = br.proposal(MATHPIX, "x", 1, "T.tgz")
    assert p["verified_by"] == "source"
    assert p["verified_by"] in refine.IDENTITY_EVIDENCE
    assert p["basis"] == "source"


def test_the_proposal_carries_the_claim_and_the_original():
    p = br.proposal(MATHPIX, "x", 2, "GA_notes.tgz")
    ev = p["evidence"]
    assert ev["source_file"] == "GA_notes.tgz"
    assert ev["left_dot_in_source"] == 0
    assert ev["pairs_repaired"] == 2
    assert ev["original"] == MATHPIX
    assert "not the author's" in ev["claim"]
