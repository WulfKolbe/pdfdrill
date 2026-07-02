"""
Question→context retrieval (src/pdfdrill/retrieve.py): the "question
transformation" step of the chat proxy. Score the drilled units
(paragraphs/sections/formulas/concepts) against a question by IDF-weighted
lexical overlap and return the top-k as grounded context, each carrying its
object id so the answer can cite which units it used. Pure + stdlib (reuses the
classify segment/strip-latex helpers).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import retrieve


class N:
    def __init__(self, type, id, **props):
        self.type, self.id, self.props = type, id, props


def _nodes():
    return [
        N("Abstract", "abs", text="A heat kernel on a graph and its spectral properties."),
        N("Paragraph", "p1", text="The Laplacian eigenvalues determine the heat kernel decay."),
        N("Paragraph", "p2", text="We discuss unrelated administrative matters and invoices."),
        N("Section", "s1", caption="Heat kernel signatures"),
        N("Equation", "e1", latex=r"k_t(x,y)=\sum_i e^{-\lambda_i t}\phi_i(x)\phi_i(y)"),
        N("Formula", "e2", latex=""),                 # empty -> skipped
        N("Picture", "fig", caption="a figure"),       # non-text -> skipped
    ]


def test_gather_units_includes_text_math_skips_empty_and_nontext():
    units = retrieve.gather_units(_nodes())
    ids = {u["id"] for u in units}
    assert {"abs", "p1", "p2", "s1", "e1"} <= ids
    assert "e2" not in ids and "fig" not in ids     # empty formula + picture excluded
    # latex control words stripped from math units (so \sum/\lambda aren't noise)
    e1 = next(u for u in units if u["id"] == "e1")
    assert e1["text"] and "\\sum" not in e1["text"]


def test_retrieve_ranks_relevant_units_first():
    hits = retrieve.retrieve("how does the heat kernel decay relate to Laplacian eigenvalues?",
                             _nodes(), k=3)
    ids = [h["id"] for h in hits]
    assert ids[0] in ("p1", "abs", "s1", "e1")       # a heat-kernel unit, not the invoice para
    assert "p2" not in ids                            # the unrelated paragraph is excluded
    assert all("score" in h and h["score"] > 0 for h in hits)


def test_retrieve_empty_question_or_no_overlap_returns_nothing():
    assert retrieve.retrieve("zzz qqq xxx", _nodes(), k=5) == []
    assert retrieve.retrieve("", _nodes(), k=5) == []


def test_retrieve_is_deterministic():
    a = retrieve.retrieve("heat kernel eigenvalues", _nodes(), k=4)
    b = retrieve.retrieve("heat kernel eigenvalues", _nodes(), k=4)
    assert [x["id"] for x in a] == [x["id"] for x in b]


def test_build_context_prompt_is_grounded_and_cites_ids():
    hits = retrieve.retrieve("heat kernel eigenvalues", _nodes(), k=3)
    ctx = retrieve.build_context(hits)
    assert "[p1]" in ctx or "[abs]" in ctx            # units labelled by id for citation
    assert "heat kernel" in ctx.lower()


def test_measurement_units_rank_above_prose_for_quantitative_questions():
    """S6.1: a bound Measurement is its own retrievable unit — the question
    "how many facts at what precision" hits it above the Abstract."""
    nodes = [
        N("Abstract", "abs", text="We probe language models for missing "
          "knowledge and evaluate their factual precision on benchmarks."),
        N("Formula", "q1", latex="5,550,689",
          quant=[{"kind": "count", "value": 5550689, "unit": None,
                  "dimension": None, "raw": "x", "noun": "facts",
                  "witness": ["q1"]}]),
        N("Paragraph", "p1",
          text="We could add {{X_FO0001||FO}} new facts automatically.",
          meas=[{"concept": "facts addable", "concept_source": "section",
                 "measure": "could add",
                 "quantity_ref": {"obj_id": "q1", "idx": 0},
                 "conditions": {"precision": 0.82},
                 "sentence_span": [0, 40], "witness": ["p1", "q1"]}]),
    ]
    units = retrieve.gather_units(nodes)
    mu = [u for u in units if u["type"] == "Measurement"]
    assert len(mu) == 1 and mu[0]["id"] == "p1#m0"
    assert "facts addable" in mu[0]["text"] and "5550689" in mu[0]["text"]
    assert "precision" in mu[0]["text"]

    hits = retrieve.retrieve("how many facts at what precision", nodes, k=3)
    ranked = [h["id"] for h in hits]
    assert "p1#m0" in ranked
    assert ranked.index("p1#m0") < ranked.index("abs"), ranked


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
