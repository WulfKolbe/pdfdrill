"""
Source-path algorithm isolation (src/pdfdrill/latex_source.py): parse
\\begin{algorithm} floats and \\begin{algorithmic} bodies (algorithmicx /
algpseudocode: \\Require/\\Ensure/\\If{}/\\State/\\Return/\\EndIf/\\For{}…) into
Algorithm + AlgorithmStep DocObjects with per-step indentation `depth` derived
from the If/For/While nesting — the LaTeX-source analogue of `pdfdrill
algorithms` (which only reads MathPix `pseudocode` lines). The graphbook is the
test corpus (93 algorithm floats, 62 algorithmic bodies).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import latex_source as ls

# the real graphbook shape (algorithm/random-graphs/expected-linear-random-GnN.tex)
ALGORITHMIC = r"""\begin{algorithmic}[1]
%% input and output
\Require Positive integer $n$ and integer $N$ with
  $0 \leq N \leq \binom{n}{2}$.
\Ensure A random graph from $G(n,N)$.
%%
%% algorithm body
\If{$N \leq \binom{n}{2} / 2$}
  \State \Return result of Algorithm~\ref{alg:foo}
\EndIf
\State $G \gets K_n$
\For{$i \gets 1, 2, \dots, \binom{n}{2} - N$}
  \State $e \gets$ draw uniformly at random from $E(G)$
  \State remove edge $e$ from $G$
\EndFor
\State \Return $G$
\end{algorithmic}"""

FLOAT = (r"\begin{algorithm}" + "\n"
         r"\caption{Generate a random graph}\label{alg:rand}" + "\n"
         + ALGORITHMIC + "\n"
         r"\end{algorithm}")


def test_extract_algorithmic_steps_and_depth():
    algos = ls.extract_algorithms(ALGORITHMIC)
    assert len(algos) == 1
    a = algos[0]
    steps = a["steps"]
    # Require, Ensure, if, (return in body of if), G<-Kn, for, (e<-..), (remove..), return G
    depths = [s["depth"] for s in steps]
    assert depths == [0, 0, 0, 1, 0, 0, 1, 1, 0]
    # first two are the pre/post conditions
    assert steps[0]["text"].lower().startswith("require")
    assert steps[1]["text"].lower().startswith("ensure")
    # the conditional carries its condition text
    assert "if" in steps[2]["text"].lower() and "binom" in steps[2]["text"]
    # the \State \Return inside the If is indented one level
    assert "return" in steps[3]["text"].lower()
    # the for-loop opens depth-1 with its range, two indented body statements
    assert steps[5]["text"].lower().startswith("for") and "gets" in steps[5]["text"] or "\\gets" in steps[5]["text"]


def test_extract_algorithm_float_caption_label_number():
    algos = ls.extract_algorithms(FLOAT)
    assert len(algos) == 1
    a = algos[0]
    assert a["title"] == "Generate a random graph"
    assert a["label"] == "alg:rand"
    assert a["number"] == 1                    # first float -> auto-number 1
    assert len(a["steps"]) == 9                # same body parsed


def test_standalone_algorithmic_has_no_number_or_caption():
    algos = ls.extract_algorithms(ALGORITHMIC)
    a = algos[0]
    assert a["number"] is None                 # not inside an algorithm float
    assert a["title"] == ""
    assert a.get("label") in (None, "")


def test_two_algorithms_in_order():
    body = FLOAT + "\n\nSome prose.\n\n" + (
        r"\begin{algorithm}\caption{Second}\label{alg:two}"
        r"\begin{algorithmic}\State do a thing\end{algorithmic}\end{algorithm}")
    algos = ls.extract_algorithms(body)
    assert [a["number"] for a in algos] == [1, 2]
    assert algos[1]["title"] == "Second"
    assert algos[1]["steps"][0]["text"].lower().endswith("do a thing")


def test_build_source_model_emits_algorithm_objects():
    tex = (r"\documentclass{book}" + "\n"
           r"\usepackage{algorithm}\usepackage{algpseudocode}" + "\n"
           r"\begin{document}" + "\n"
           r"\section{Intro}" + "\n" + FLOAT + "\n"
           r"\end{document}")
    import tempfile
    p = Path(tempfile.mkdtemp()) / "book.tex"
    p.write_text(tex, encoding="utf-8")
    doc = ls.build_source_model(str(p), bibkey="GB")
    algs = [o for o in doc.objects.values() if o.type == "Algorithm"]
    steps = [o for o in doc.objects.values() if o.type == "AlgorithmStep"]
    assert len(algs) == 1
    assert algs[0].props["title"] == "Generate a random graph"
    assert algs[0].props["bibkey"] == "GB"
    assert len(steps) == 9
    # AlgorithmStep children are parented to the Algorithm
    assert all(s.parent == algs[0].id for s in steps)
    assert len(algs[0].children) == 9
    # depth survives onto the steps
    assert max(s.props["depth"] for s in steps) == 1
    assert doc.meta["source_counts"]["algorithms"] == 1


def test_scan_environments_usage_newtheorem_newenvironment():
    r"""Track environment names used + custom/theorem-like declarations — the
    2110.11150 case (valuable for higher layers / a LEAN4 theorem-proof export)."""
    decl = (r"\newtheorem{theorem}{Theorem}[section]" "\n"
            r"\newtheorem{lemma}[theorem]{Lemma}" "\n"
            r"\newtheorem*{remark*}{Remark}" "\n"
            r"\newenvironment{myenv}{\begingroup}{\endgroup}" "\n"
            r"\renewenvironment{abstract}{}{}")
    body = (r"\begin{theorem} x \end{theorem}"
            r"\begin{lemma} y \end{lemma}\begin{lemma} z \end{lemma}"
            r"\begin{proof} p \end{proof}\begin{align} a \end{align}")
    env = ls.scan_environments(decl, body)
    assert env["used"]["lemma"] == 2 and env["used"]["proof"] == 1
    thm = {t["name"]: t for t in env["newtheorem"]}
    assert thm["theorem"]["reset_counter"] == "section"
    assert thm["lemma"]["shared_counter"] == "theorem"      # [theorem] before title
    assert thm["remark*"]["starred"] is True
    assert "myenv" in env["newenvironment"] and "abstract" in env["newenvironment"]
    assert set(env["theorem_like"]) >= {"theorem", "lemma", "remark*"}
    assert env["theorem_blocks"] == 3                        # 1 theorem + 2 lemma
    assert env["proof_blocks"] == 1


def test_format_environments_status_lines():
    from pdfdrill.commands import _format_environments
    env = {
        "used": {"theorem": 1, "lemma": 4, "proof": 6, "align": 22},
        "newtheorem": [{"name": "theorem"}, {"name": "lemma"}],
        "newenvironment": ["abstract", "ALC@g", "table"],   # @-name hidden in display
        "theorem_like": ["theorem", "lemma"],
        "theorem_blocks": 5, "proof_blocks": 6,
    }
    lines = _format_environments(env)
    assert "4 distinct used, 33 total" in lines[0]
    assert any("theorem, lemma" in l for l in lines)
    assert any("5 theorem/lemma/def block(s) + 6 proof" in l and "LEAN4" in l
               for l in lines)
    custom = next(l for l in lines if "custom" in l)
    assert "3 custom" in custom and "abstract" in custom and "table" in custom
    assert "ALC@g" not in custom                            # @-internal hidden
    assert _format_environments({}) == []


def test_algorithm2e_float_without_inner_algorithmic():
    r"""The 2110.11150 case: an algorithm2e \begin{algorithm}[h!] with NO inner
    \begin{algorithmic} (its own \KwIn/\For{}{}) and a \caption{\texttt{...}}.
    It must still be isolated, with the nested-brace caption recovered."""
    body = (r"\begin{algorithm}[h!]" + "\n"
            r"\caption{\texttt{edge-popup-scaled}}\label{alg:ep}" + "\n"
            r"\KwIn{Data $(X,y)$}" + "\n"
            r"\For{$i=1$ to $e$}{ step one\\ step two }" + "\n"
            r"output: $f$" + "\n"
            r"\end{algorithm}")
    algs = ls.extract_algorithms(body)
    assert len(algs) == 1
    assert algs[0]["number"] == 1
    assert algs[0]["title"] == r"\texttt{edge-popup-scaled}"
    assert algs[0]["label"] == "alg:ep"
    assert len(algs[0]["steps"]) >= 3            # one step per non-empty line


def test_format_algorithms_counts_model_objects_not_sidecar():
    """The bug: a source-built model HAS Algorithm objects but the sidecar
    `algorithms_*` evidence is unset (only the MathPix path sets it), so
    `_format_algorithms` reported 0. It must count from the model objects."""
    from pdfdrill.commands import _format_algorithms
    from docmodel.core import Document, DocObject
    doc = Document()
    alg = DocObject(type="Algorithm", props={"number": 1, "title": "edge-popup"})
    doc.add(alg)
    for i in range(3):
        doc.add(DocObject(type="AlgorithmStep",
                          props={"text": f"s{i}", "depth": i % 2}, parent=alg.id))
    out = _format_algorithms(doc)
    assert "1 Algorithm block(s)" in out and "3 steps" in out
    assert "edge-popup" in out
    assert "No algorithm blocks found" in _format_algorithms(Document())


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
