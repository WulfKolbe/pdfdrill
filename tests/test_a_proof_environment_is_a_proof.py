r"""A proof is a Proof object whatever the class calls its environment.

T-0156, the class the audit called E. On arxiv.0912.2444 fourteen proofs and
four remarks were Paragraph PROSE with their own delimiters embedded in the
text — `\begin{pf*}{Proof of Theorem (theoremMainResultER)} Since …` — so
`Environment pf* undefined` and `\begin{document} ended by \end{pf*}`.

THREE GAPS, none of them needing a class reader. `scan_environments` is
already called with the preamble PLUS `_local_style_text(base_dir)`, which
concatenates every bundled .sty/.cls as text, comment-stripped; nothing is
`\input` and nothing executed. The declarations were in hand and two patterns
could not see three forms of them:

  * `_NEWTHEOREM_RE` matched `\newtheorem` only. `remark` is declared
    `\newproclaim{remark}{Remark}`, and the class states what that means:
    arximspdf.cls:1408, `\def\newproclaim{\theoremstyle{proclaim}
    \old@newtheorem}` — a `\newtheorem` with a style.
  * the proof scan was hard-coded `_env_blocks(body, "proof")`, so imsart's
    `pf` (arximspdf.cls:1436) and `pf*` (`\@namedef{pf*}`, :1441) built no
    Proof object at all.
  * `_PROOF_ENVS = ("proof",)`, so `meta["environments"]["proof_blocks"]`
    reported 0 on a document with 14 proof blocks while its own docstring
    advertises it as "how many are actually USED".

MEASURED over 2,717 library source documents — a body that OPENS an
environment these patterns miss while the declaration text declares it, with
standard names a class merely redefines excluded: 23 documents. `\newproclaim`
17, `\newdefinition` 2; by name `pf*` 14, `remark` 8, then singles.

`\spnewtheorem` IS DELIBERATELY ABSENT: it reached 14 documents before the
standard names were excluded and none after, so every one of its payloads was
`figure`, `table` or `proof`, which LaTeX already has.

THE RESULT IS STRUCTURAL, and the error count is a poor instrument for it:
Proof objects 0 -> 14, Theorem 18 -> 22, Paragraph 203 -> 75, proof_blocks
0 -> 14, while the compile went 103 -> 95 because about 31 environment errors
were traded for about 23 maths-mode errors that were always in those
statements and that nothing typeset while they were prose.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

LS = pytest.importorskip("pdfdrill.latex_source")

DECL = "\n".join([
    r"\newtheorem{theorem}{Theorem}",
    r"\newproclaim{remark}{Remark}",
    r"\newdefinition{defn}{Definition}",
    r"\newenvironment{pf}{}{}",
])
BODY = "\n".join([
    r"\begin{theorem}\label{t1}A statement.\end{theorem}",
    r"\begin{pf*}{Proof of Theorem \ref{t1}}Body one.\end{pf*}",
    r"\begin{pf}Body two.\end{pf}",
    r"\begin{proof}[Proof of the lemma]Body three.\end{proof}",
    r"\begin{remark}A remark.\end{remark}",
])


def _scan():
    return LS.scan_environments(DECL, BODY)


# ── the declarators ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["theorem", "remark", "defn"])
def test_a_declarator_that_means_newtheorem_is_one(name):
    r"""`\newproclaim` and `\newdefinition` declare a theorem-like
    environment; the class says so for the first."""
    assert name in _scan()["theorem_like"]


def test_spnewtheorem_is_not_a_declarator_here():
    """Measured: 14 documents before standard names were excluded, 0 after.
    Every payload was `figure`, `table` or `proof`."""
    envs = LS.scan_environments(r"\spnewtheorem{zzz}{Zzz}",
                                r"\begin{zzz}x\end{zzz}")
    assert "zzz" not in envs["theorem_like"]


# ── the proof environments ──────────────────────────────────────────────────

@pytest.mark.parametrize("env", ["proof", "proof*", "pf", "pf*"])
def test_the_proof_environments_are_named(env):
    assert env in LS._PROOF_ENVS


def test_proof_blocks_counts_them():
    """The field that reported 0 on a document with 14 proof blocks."""
    assert _scan()["proof_blocks"] == 3        # pf*, pf, proof


def test_every_proof_environment_builds_a_proof():
    """Hard-coded to "proof", the scan built no object for `pf`/`pf*`."""
    got = LS.extract_theorems(BODY, _scan()["theorem_like"],
                              _scan()["newtheorem"])
    assert len(got["proofs"]) == 3


def test_a_proof_statement_keeps_none_of_its_own_delimiters():
    r"""The defect that RAISED the document, 103 -> 123: the strip was
    hard-coded `^\\begin\{proof\}`, so a `pf*` block kept its own
    `\begin{pf*}{…}` and the projector wrapped THAT in `\begin{proof}` — 18
    "\begin{proof} … ended by"."""
    got = LS.extract_theorems(BODY, _scan()["theorem_like"],
                              _scan()["newtheorem"])
    for pr in got["proofs"]:
        assert "\\begin{pf" not in pr["statement"]
        assert "\\end{pf" not in pr["statement"]
        assert "\\begin{proof}" not in pr["statement"]
    assert sorted(p["statement"].strip() for p in got["proofs"]) == [
        "Body one.", "Body three.", "Body two."]


# ── where the proof's title lives ───────────────────────────────────────────

def test_a_starred_proof_takes_its_title_from_a_brace():
    r"""amsthm's `proof` takes `[name]`; imsart's starred form is declared
    `\@namedef{pf*}#1{…\def\proofname{#1}…}` (arximspdf.cls:1441) — one
    MANDATORY argument."""
    got = LS.extract_theorems(BODY, _scan()["theorem_like"],
                              _scan()["newtheorem"])
    names = {p["name"] for p in got["proofs"]}
    assert "Proof of Theorem \\ref{t1}" in names
    assert "Proof of the lemma" in names


def test_an_unstarred_proof_body_keeps_its_opening_group():
    r"""The brace form is restricted to STARRED envs on the class's own
    evidence, so a `proof` whose body opens with a group cannot lose it to a
    title."""
    body = r"\begin{proof}{\bf Proof.} The argument.\end{proof}"
    got = LS.extract_theorems(body, [], [])
    assert len(got["proofs"]) == 1
    assert got["proofs"][0]["name"] == ""
    assert "\\bf Proof." in got["proofs"][0]["statement"]


def test_the_starred_title_pairs_the_proof_to_its_theorem():
    r"""A side effect worth keeping: the `\ref` inside that brace title is the
    internal cross-reference the owner's fifth requirement asks for."""
    got = LS.extract_theorems(BODY, _scan()["theorem_like"],
                              _scan()["newtheorem"])
    paired = [p for p in got["proofs"] if p["of_label"] == "t1"]
    assert len(paired) == 1
    assert paired[0]["statement"].strip() == "Body one."
