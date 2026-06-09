"""
Named-concept extraction (src/semantic/concepts.py): acronyms (Schwartz-Hearst)
+ glossary/notation-section terms, each with a definition site + reference sites
located in the docmodel prose. Pure tests (no graph).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic import concepts


def test_extract_acronyms_schwartz_hearst():
    text = ("We use a Convolutional Neural Network (CNN) and a Variational "
            "Auto-Encoder (VAE). The CNN beats the VAE. A Generative "
            "Adversarial Network (GAN) is also tried.")
    ac = concepts.extract_acronyms(text)
    assert ac["CNN"] == "Convolutional Neural Network"
    assert ac["VAE"] == "Variational Auto-Encoder"
    assert ac["GAN"] == "Generative Adversarial Network"


def test_extract_acronyms_rejects_non_acronyms():
    # not acronyms: lowercase, single capital, a number/citation, a long phrase
    text = "see (e.g. above), figure (3), the result (Smith), the (cat)."
    assert concepts.extract_acronyms(text) == {}


def test_concept_records_acronym_define_first_then_references():
    from docmodel.core import Document, DocObject
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Section", id="s1", props={
        "caption": "Method", "section_number": "2", "flow_index": 1}))
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "We train a Convolutional Neural Network (CNN) here.",
        "page": 3, "parent_section": "s1", "flow_index": 2}))
    doc.add(DocObject(type="Paragraph", id="p2", props={
        "text": "The CNN converges fast; the CNN is robust.",
        "page": 5, "parent_section": "s1", "flow_index": 3}))
    recs = {r["name"]: r for r in concepts.concept_records(doc)}
    cnn = recs["CNN"]
    assert cnn["kind"] == "acronym" and cnn["expansion"] == "Convolutional Neural Network"
    assert cnn["define"]["page"] == 3 and cnn["define"]["section_id"] == "s1"
    # one further reference block (p2); p1 is the definition, not a reference
    assert len(cnn["occurrences"]) == 1 and cnn["occurrences"][0]["page"] == 5


def test_concept_records_glossary_section_term():
    from docmodel.core import Document, DocObject
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Section", id="g", props={
        "caption": "Notation", "section_number": "", "flow_index": 1}))
    doc.add(DocObject(type="ListItem", id="i1", props={
        "content": "metric tensor — the field g that measures distances",
        "page": 2, "parent_section": "g", "flow_index": 2}))
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "The metric tensor appears again in section 3.",
        "page": 7, "parent_section": "g", "flow_index": 3}))
    recs = {r["name"]: r for r in concepts.concept_records(doc)}
    mt = recs["metric tensor"]
    assert mt["kind"] == "term" and mt["define"]["page"] == 2     # the glossary entry
    assert any(o["page"] == 7 for o in mt["occurrences"])         # later prose mention


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
            import traceback; traceback.print_exc()
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
