"""
LLMTextProjector (src/docops/projectors/llm_text.py): a flat, delimiter-
separated dump for an LLM — per unit the tiddler-style TITLE then the content
(paragraph text, or a formula's latex), units separated by a configurable
delimiter (default '%%%%'). A LaTeX paragraph is one block: text is split on
double line breaks into separate units. Formulas with empty/null latex are
skipped (they carry only a CDN crop — nothing for the LLM to read).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from docops.base import OperatorConfig
from docops.projectors.llm_text import LLMTextProjector


def _doc():
    doc = Document()
    doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "First logical paragraph.\n\nSecond logical paragraph here.",
        "flow_index": 1}))
    doc.add(DocObject(type="Equation", id="e1", props={
        "latex": "E = mc^2", "page": 3, "flow_index": 2}))
    doc.add(DocObject(type="Paragraph", id="p2", props={
        "text": "A single clean paragraph.", "flow_index": 3}))
    doc.add(DocObject(type="Formula", id="f1", props={
        "latex": "\\alpha + \\beta", "flow_index": 4}))
    doc.add(DocObject(type="Formula", id="f2", props={      # empty -> skipped
        "latex": "", "cdn_url": "https://cdn/x.png", "flow_index": 5}))
    return doc


def _project(doc, **params):
    cfg = OperatorConfig(op="projector", classname="LLMTextProjector", params=params)
    return LLMTextProjector(cfg).project(doc)


def test_units_titles_and_delimiter():
    out = _project(_doc())
    blocks = out.split("\n%%%%\n")
    # p1 splits into 2; e1; p2; f1 -> 5 units (f2 skipped)
    assert len(blocks) == 5
    assert blocks[0].startswith("T_PARA_0001")
    assert "First logical paragraph." in blocks[0]
    assert "Second logical paragraph" not in blocks[0]      # split happened
    assert "Second logical paragraph" in blocks[1]


def test_flow_order_interleaves_paragraphs_and_formulas():
    out = _project(_doc())
    titles = [b.splitlines()[0] for b in out.split("\n%%%%\n")]
    # flow order: p1a, p1b, EQ, p2, FO
    assert titles[2] == "T_EQ0001"          # page is a field, not in the title
    assert titles[3].startswith("T_PARA_0002")
    assert titles[4].startswith("T_FO0001")


def test_empty_and_null_formula_skipped():
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Formula", id="f1", props={"latex": None, "flow_index": 1}))
    doc.add(DocObject(type="Formula", id="f2", props={"latex": "null", "flow_index": 2}))
    doc.add(DocObject(type="Formula", id="f3", props={"latex": "x^2", "flow_index": 3}))
    out = _project(doc)
    assert out.count("%%%%") == 0          # only one real unit -> no delimiter
    assert "x^2" in out and "null" not in out


def test_custom_delimiter_and_no_split():
    out = _project(_doc(), delimiter="=====", split_paragraphs=False)
    blocks = out.split("\n=====\n")
    assert len(blocks) == 4                # p1 NOT split now
    assert "First logical paragraph.\n\nSecond logical paragraph here." in blocks[0]


def test_split_titles_are_suffixed_and_unique():
    out = _project(_doc())
    blocks = out.split("\n%%%%\n")
    assert blocks[0].splitlines()[0] == "T_PARA_0001#1"
    assert blocks[1].splitlines()[0] == "T_PARA_0001#2"


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


def test_llmtext_includes_sections_and_figures_and_code_algorithm():
    """llm.txt must carry the STRUCTURE an LLM references: Section headings (incl.
    promoted appendix sections), figure/table captions, and a code-subtype Diagram's
    code (a MathPix 'Algorithm 1' box) — not only Paragraph/Equation/Formula."""
    import types as _t
    from docops.projectors.llm_text import build_llm_text

    def _o(t, **props):
        return _t.SimpleNamespace(type=t, id=props.get("id", t), props=props)

    objs = [
        _o("Section", id="s1", caption="Dataset Split Details", refnum="A",
           is_appendix=True, flow_index=1),
        _o("Paragraph", id="p1", text="Some prose here.", flow_index=2),
        _o("Diagram", id="d1", subtype="code", language="text", flow_index=3,
           code="Algorithm 1 Incremental construction of a user memory pyramid.\n"
                "Require: sessions S\nInitialize store C"),
        _o("Picture", id="fig1", caption="Figure 3 | Latency stats.",
           cdn_url="https://cdn.mathpix.com/x.png", flow_index=4),
    ]
    out = build_llm_text(objs, {"bibkey": "D"})
    assert "Dataset Split Details" in out                 # section heading present
    assert "Algorithm 1 Incremental construction of a user memory pyramid." in out
    assert "Require: sessions S" in out                   # the algorithm code body
    assert "Figure 3 | Latency stats." in out             # figure caption
    assert "https://cdn.mathpix.com/x.png" in out         # image reference for the LLM
