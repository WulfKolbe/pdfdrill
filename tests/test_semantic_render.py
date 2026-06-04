"""
The semantic command's output is consumed by an LLM, not a human. render_for_llm
must therefore be: structured (entities / relations / markers / warnings),
complete (no truncation of the graph), clean (scan-noise markers suppressed),
and free of human narration — with a pointer to the full JSON for per-fact
evidence. This tests that contract.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic.graph import SemanticGraph
from semantic.identity import IdentityResolver
from semantic.build import ingest_document
from semantic.render import render_for_llm


def _graph():
    g = SemanticGraph()
    r = IdentityResolver(g)
    ingest_document(g, r, source="AOK", sender=None,
                    entities_rec={"iban": [{"iban": "DE24300400000180384000", "bic": "COBADEFFXXX"}],
                                  "bic": [], "address": [], "ids": []},
                    recipient_name="Alexander Kolbe",
                    recipient_rec={"address": ["Rotkäppchenweg 1, 51515 Kürten"]})
    return g


def test_render_is_structured_complete_and_clean():
    g = _graph()
    markers = [{"page": 2, "side": "left", "role": "marginal", "text": "o"},
               {"page": 2, "side": "left", "role": "marginal", "text": "N~"},
               {"page": 2, "side": "left", "role": "page_number", "text": "5"}]
    out = render_for_llm(g, bibkey="AOK", validity="valid", warnings=[],
                         markers=markers, json_name="AOK.semantic.json", n_docs=1)
    # structured sections, machine-scannable
    assert "SEMANTIC GRAPH AOK" in out and "validity=valid" in out
    assert "ENTITIES" in out and "RELATIONS" in out
    # complete: the agent/account entities are present with their key facts
    assert "person:1" in out and "Alexander Kolbe" in out
    assert "bank_account:1" in out and "DE24300400000180384000" in out
    # relations rendered as a graph the LLM can read
    assert "sent_to" in out and "—" in out
    # markers cleaned: the single-char scan noise is gone, the page number stays
    assert "page_number" in out
    assert " o\n" not in out and "N~" not in out
    # pointer to full evidence, and NO human narration
    assert "AOK.semantic.json" in out
    assert "Extractors are sensors" not in out


def test_render_flags_invalid_with_warnings():
    g = _graph()
    out = render_for_llm(g, bibkey="X", validity="invalid",
                         warnings=[{"severity": "critical", "code": "type_violation",
                                    "message": "belongs_to: object is document"}],
                         markers=[], json_name="X.semantic.json", n_docs=1)
    assert "validity=invalid" in out
    assert "WARNINGS" in out and "type_violation" in out


if __name__ == "__main__":
    test_render_is_structured_complete_and_clean(); print("PASS render")
    test_render_flags_invalid_with_warnings(); print("PASS warnings")
    print("\nAll tests passed.")
