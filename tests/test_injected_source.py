r"""769 — is the injected author LaTeX actually the author's?

Measured on 1205.5935v1 (Chisolm, *Geometric Algebra*): the author's e-print
contains no `\left.` at all, MathPix's tex.zip contains 224, and the model's
`latex_eq_0062` stream contains two — and its text occurs verbatim inside the
tex.zip. 458 of that document's 479 injected equations are MathPix's own.
"""
import gzip
import io
import tarfile
import zipfile

from docmodel.core import Document
from pdfdrill import injected_source as inj

#: The Chisolm equation, as MathPix reconstructed it -- note the `\left.`
#: opening a scope that closes on `\right\rfloor` in the middle of the row.
MATHPIX = (r"\begin{aligned} & \frac{1}{r!} \sum_{\pi_{j}}\left(\operatorname{sgn} "
           r"\pi_{j}\right) e_{j} a_{\pi_{j}(1)} \\ & \left.\quad=\frac{1}{2}"
           r"(-1)^{j-1} a e_{j}\right\rfloor e_{1}\end{aligned}")
#: The same equation as the AUTHOR wrote it: no `\left.`, his own macros.
AUTHOR = (r"\begin{aligned} & \frac{1}{r!} \sum_{\pi_j} (\sgn\pi_j) e_j "
          r"a_{\pi_j(1)} \\ & \quad= \half (-1)^{j-1} a e_j \lin e_1 \end{aligned}")


def _doc(name: str, text: str) -> Document:
    doc = Document(meta={"bibkey": "T"})
    st = doc.ensure_stream(name)
    for ch in text:
        st.append(codepoint=ch)
    return doc


def _write_zip(tmp_path, text):
    p = tmp_path / "T.tex.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("deadbeef-0000-0000-0000-000000000000.tex", text)
    return p


def _write_tgz(tmp_path, text):
    p = tmp_path / "T.tgz"
    buf = text.encode("utf-8")
    with tarfile.open(p, "w:gz") as tf:
        ti = tarfile.TarInfo("paper.tex")
        ti.size = len(buf)
        tf.addfile(ti, io.BytesIO(buf))
    return p


# --- the sources ----------------------------------------------------------

def test_author_tex_never_reads_the_mathpix_zip(tmp_path):
    r"""The one property everything else rests on. `.tex.zip` is MathPix's own
    reconstruction; reading it as the author's is out/063."""
    _write_zip(tmp_path, MATHPIX)
    assert inj.author_tex(tmp_path) == ""
    assert MATHPIX[:40] in inj.mathpix_tex(tmp_path)


def test_author_tex_reads_a_tgz(tmp_path):
    _write_tgz(tmp_path, AUTHOR)
    assert AUTHOR[:40] in inj.author_tex(tmp_path)


def test_author_tex_reads_a_bare_gz(tmp_path):
    """689 — arXiv serves a single-file submission as gzip(paper.tex)."""
    (tmp_path / "T.gz").write_bytes(gzip.compress(AUTHOR.encode("utf-8")))
    assert AUTHOR[:40] in inj.author_tex(tmp_path)


# --- the verdict ----------------------------------------------------------

def test_a_stream_only_in_the_zip_is_mathpix_s():
    assert inj.classify(MATHPIX, inj.norm(MATHPIX), inj.norm(AUTHOR)) == inj.FROM_ZIP


def test_a_stream_in_the_eprint_is_the_author_s():
    assert inj.classify(AUTHOR, inj.norm(MATHPIX), inj.norm(AUTHOR)) == inj.FROM_EPRINT


def test_the_eprint_wins_a_tie():
    """MathPix reproduces long stretches of a paper correctly, so a string in
    BOTH is not evidence of contamination."""
    both = inj.norm(AUTHOR)
    assert inj.classify(AUTHOR, both, both) == inj.FROM_EPRINT


def test_a_stream_in_neither_is_unknown():
    assert inj.classify(AUTHOR, "nothing here", "nor here") == inj.UNKNOWN


def test_a_short_stream_carries_no_evidence():
    r"""`\alpha` is in both sources and in every other document."""
    assert inj.classify(r"\alpha", inj.norm(MATHPIX), inj.norm(AUTHOR)) == inj.UNKNOWN


def test_whitespace_does_not_hide_a_match():
    reflowed = MATHPIX.replace(" ", "\n   ")
    assert inj.classify(reflowed, inj.norm(MATHPIX), "") == inj.FROM_ZIP


# --- the audit ------------------------------------------------------------

def test_audit_names_the_contaminated_streams(tmp_path):
    _write_zip(tmp_path, MATHPIX)
    _write_tgz(tmp_path, AUTHOR)
    doc = _doc("latex_eq_0001", MATHPIX)
    a = inj.audit(doc, tmp_path)
    assert (a["streams"], a["mathpix"], a["author"]) == (1, 1, 0)
    assert a["has_eprint"] is True
    assert "MathPix's OWN" in inj.verdict_line(a, "T")
    assert "injectlatex --force" in inj.verdict_line(a, "T")


def test_audit_is_quiet_when_the_gold_is_the_author_s(tmp_path):
    _write_zip(tmp_path, MATHPIX)
    _write_tgz(tmp_path, AUTHOR)
    doc = _doc("latex_eq_0001", AUTHOR)
    a = inj.audit(doc, tmp_path)
    assert (a["mathpix"], a["author"]) == (0, 1)
    assert "none of them MathPix's own output" in inj.verdict_line(a, "T")


def test_without_an_eprint_the_advice_is_to_drop_it(tmp_path):
    """716 documents in this library have no e-print at all. There is nothing
    to repair the gold WITH, and keeping it is keeping a false reference."""
    _write_zip(tmp_path, MATHPIX)
    doc = _doc("latex_eq_0001", MATHPIX)
    line = inj.verdict_line(inj.audit(doc, tmp_path), "T")
    assert "cannot be repaired, only dropped" in line


def test_a_model_with_no_injected_latex_says_so(tmp_path):
    a = inj.audit(Document(meta={"bibkey": "T"}), tmp_path)
    assert a["streams"] == 0
    assert "no injected author LaTeX" in inj.verdict_line(a, "T")


def test_only_latex_eq_streams_are_audited(tmp_path):
    _write_zip(tmp_path, MATHPIX)
    doc = _doc("latex_eq_0001", MATHPIX)
    other = doc.ensure_stream("mathpix_lines")
    for ch in MATHPIX:
        other.append(codepoint=ch)
    assert inj.audit(doc, tmp_path)["streams"] == 1
