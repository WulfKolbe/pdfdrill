"""230 — the second acceptance route, and the record that says what verified it.

out/229 found a row the ink gate cannot reach: 0707.4470_FO0175, an INLINE
formula, so no region and no crop (out/125). MathPix emitted \\mathscr{g};
rsfs10 has no lowercase, so it drops silently. The author's arXiv e-print
writes \\mathcal{J} there.

The route is a CHECK, not a flag. A requester says "the author wrote X"; the
gate goes to the author's source, finds the site by its surrounding prose, and
reads off what is there.
"""
import pytest

from pdfdrill import refine as rf


class _Obj:
    def __init__(self, oid, typ, props):
        self.id, self.type, self.props = oid, typ, props
        self.realizations = []

    def add_realization(self, r):
        self.realizations.append(r)


class _Doc:
    def __init__(self, objs):
        self.objects = {o.id: o for o in objs}
        self.streams = {}

    def ensure_stream(self, name):
        from docmodel.core import Stream
        return self.streams.setdefault(name, Stream(name=name))


#: the real sentence, from computationalEM.tex
SRC = (r"""
\begin{proof} The idea of this proof is to emulate the derivation of the
continuous Maxwell's equations from \autoref{MaxwellEquations}.
Given a discrete $1$-form $A$ and dual source $3$-form
  $\mathcal{J}$, define the discrete Lagrangian $4$-form
\begin{equation}
  \mathcal{L} _d = -\frac{1}{2} \mathrm{d} A \wedge *\mathrm{d} A + A
  \wedge \mathcal{J} , \nonumber
\end{equation}
""")

#: how MathPix wrote the same paragraph, with the formula inline in its text
PARA = (r"Interpreting this in the sense of DEC, we will obtain the discrete "
        r"Maxwell's equations. Given a discrete 1-form \(A\) and dual source "
        r"3-form \(\mathscr{g}\), define the discrete Lagrangian 4-form")


def _doc():
    return _Doc([
        _Obj("f1", "Formula", {"latex": r"\mathscr{g}", "display": False}),
        _Obj("p1", "Paragraph", {"text": PARA}),
    ])


# ---------------------------------------------------------------- deriving ---

def test_the_authors_value_is_DERIVED_from_the_source():
    val, ev = rf.eprint_value(_doc(), "f1", SRC)
    assert val == r"\mathcal{J}"
    assert ev["occurrences"] == 1
    assert "dual source" in ev["context_before"]


def test_the_context_is_prose_only():
    r"""The author writes `$1$-form` where MathPix writes `1-form`, so digits
    and punctuation disagree at every site and prove nothing. Only the prose
    around the mathematics is written identically by both."""
    assert rf._ctx_words(r"a discrete $1$-form $A$ and dual source $3$-form",
                         8, tail=True) == \
        ["a", "discrete", "form", "and", "dual", "source", "form"]


def test_an_ambiguous_site_is_refused_not_guessed():
    """Two identical contexts mean the gate cannot say WHICH one it read."""
    val, ev = rf.eprint_value(_doc(), "f1", SRC + SRC)
    assert val == ""
    assert "ambiguous" in ev["reason"]


def test_a_disagreeing_tail_is_refused():
    bad = SRC.replace("define the discrete Lagrangian",
                      "consider instead the Hamiltonian")
    val, ev = rf.eprint_value(_doc(), "f1", bad)
    assert val == ""
    assert "AFTER" in ev["reason"]


def test_absent_prose_is_refused():
    val, ev = rf.eprint_value(_doc(), "f1", r"\section{Unrelated} $x=1$")
    assert val == ""
    assert "does not occur" in ev["reason"]


def test_a_value_with_no_flow_text_cannot_be_located():
    d = _Doc([_Obj("f1", "Formula", {"latex": r"\mathscr{g}"})])
    val, ev = rf.eprint_value(d, "f1", SRC)
    assert val == ""
    assert "no flow text" in ev["reason"]


def test_same_latex_ignores_whitespace_only():
    assert rf.same_latex(r"\mathcal {J}", r"\mathcal{J}")
    assert not rf.same_latex(r"\mathcal{J}", r"\mathcal{G}")


# ------------------------------------------------------- never MathPix's tex ---

def test_author_eprint_never_reads_the_tex_zip(tmp_path):
    r"""out/229 nearly used `<stem>.tex.zip` as gold. It agreed with the
    markdown perfectly, because it IS the markdown: MathPix's own LaTeX
    output. A verification that reads the thing it is verifying confirms
    anything."""
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    (tmp_path / "x.tex.zip").write_bytes(b"PK\x03\x04not really")
    text, name = rf.author_eprint(pdf)
    assert text == "" and name == ""


# ------------------------------------------------------------------ record ---

def test_record_refuses_a_proposal_that_does_not_say_what_verified_it():
    """A record whose provenance is guessed is worth less than no record."""
    d = _doc()
    with pytest.raises(ValueError, match="what verified it"):
        rf.record_one(d, "f1", {"proposed": r"\mathcal{J}"})


def test_record_carries_the_verification_that_actually_ran():
    """This was the literal string "ink" however the row had been accepted, so
    a row verified any other way was recorded as ink-verified — a claim about
    an instrument that never ran."""
    d = _doc()
    ok = rf.record_one(d, "f1", {
        "proposed": r"\mathcal{J}", "verified_by": rf.VERIFIED_EPRINT,
        "basis": "eprint", "evidence": {"file": "computationalEM.tex"},
    })
    assert ok
    r = d.objects["f1"].realizations[-1]
    assert r.provenance == "change"
    assert r.props["verified_by"] == "eprint"
    assert r.props["evidence"]["file"] == "computationalEM.tex"
    assert r.props["ink_before"] is None      # honestly absent, not fabricated


def test_the_original_value_is_never_overwritten():
    d = _doc()
    rf.record_one(d, "f1", {"proposed": r"\mathcal{J}",
                            "verified_by": rf.VERIFIED_EPRINT})
    assert d.objects["f1"].props["latex"] == r"\mathscr{g}"
    assert d.objects["f1"].props[rf.REFINED_FIELD] == r"\mathcal{J}"
