"""
pdfdrill classify (src/pdfdrill/classify.py): gather a document's classifiable
text (section captions + prose + equation LaTeX) and run the vocabnet Federation
over it to get MSC (and any other compiled scheme) subject hits, with a
two-digit MSC rollup. German prose is matched after translation (the `text`
field carries English once `pdfdrill translate` has run; `has_translation`
detects the `text_source` marker).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import classify
from vocabnet import Vocabulary, Concept, Federation


class N:
    def __init__(self, type, **props):
        self.type, self.id, self.props = type, props.get("id", "x"), props


def _nodes():
    return [
        N("Section", caption="Quantum field theory of gravitation"),
        N("Paragraph", text="We derive a mass formula from a unified field theory."),
        N("Equation", latex=r"E = m c^2 \quad \text{energy}"),
        N("Formula", latex=""),                       # empty -> skipped
        N("Picture", caption="a figure"),             # non-text type -> skipped
    ]


def test_gather_classification_text():
    txt = classify.gather_classification_text(_nodes())
    assert "Quantum field theory of gravitation" in txt
    assert "unified field theory" in txt
    assert "energy" in txt                            # math identifiers survive
    assert "quad" not in txt and "text" not in txt    # LaTeX commands stripped
    assert "a figure" not in txt                      # pictures excluded


def test_has_translation_marker():
    assert classify.has_translation([N("Paragraph", text="x", text_source="y")])
    assert not classify.has_translation([N("Paragraph", text="x")])


def test_phrase_evidence_rejects_function_word_bigrams():
    from vocabnet import Hit
    # a bigram of two stop/function words ("in die", "with the") is not evidence
    assert not classify._phrase_evidence(Hit("gnd", "x", "Eintritt", 1.0, ["in die", "die"]))
    assert not classify._phrase_evidence(Hit("msc", "x", "y", 1.0, ["with the", "the"]))
    # an explicit MSC filler bigram (content word, but boilerplate) is rejected
    assert not classify._phrase_evidence(Hit("msc", "x", "y", 1.0, ["in connection"]))
    # a contentful phrase (>=1 non-stopword) counts
    assert classify._phrase_evidence(Hit("msc", "x", "y", 1.0, ["gravitational field"]))
    assert classify._phrase_evidence(Hit("gnd", "x", "y", 1.0, ["einheitliche feldtheorie"]))
    # a content+stopword bigram still counts (the content word carries signal)
    assert classify._phrase_evidence(Hit("gnd", "x", "y", 1.0, ["eintritt in"]))


def test_msc_rollup_two_digit():
    from vocabnet import Hit
    hits = [Hit("msc", "81T08", "Constructive QFT", 30.0),
            Hit("msc", "81Txx", "QFT", 20.0),
            Hit("msc", "83C05", "Einstein equations", 10.0)]
    roll = classify.msc_rollup(hits)
    assert roll["81"] == 50.0 and roll["83"] == 10.0
    assert list(roll)[0] == "81"                      # sorted by score desc


def test_classify_document_end_to_end():
    fed = Federation([Vocabulary.compile("msc", [
        Concept("81-XX", pref="Quantum theory"),
        Concept("81Txx", pref="Quantum field theory; related classical field theories",
                parent="81-XX"),
        Concept("83-XX", pref="Relativity and gravitational theory"),
        Concept("35Q55", pref="NLS-like equations (nonlinear Schrödinger)"),
    ])])
    res = classify.classify_document(_nodes(), fed, k=5)
    assert "msc" in res["present"]
    top = res["msc_top"]
    assert top and top[0]["code"] in ("81Txx", "81-XX", "83-XX")
    assert "81" in res["msc_sections"]
    assert res["chars"] > 0


def test_german_vocab_skipped_on_english_document():
    """A German-language vocab (stw/gnd) must NOT classify an untranslated
    English doc (de_segs falls back to the English text) — else it matches
    German noise (COMPASS-Detektor / German economics on an AI paper). The
    English scheme still runs."""
    fed = Federation([
        Vocabulary.compile("msc", [        # phrase-matches the English fixture
            Concept("81Txx", pref="Quantum field theory; related classical field theories"),
            Concept("83-XX", pref="Relativity and gravitational theory")]),
        Vocabulary.compile("stw", [
            Concept("E1", pref="Preiskonvergenz"),
            Concept("E2", pref="Leistungsfähigkeitsprinzip")],
            meta={"lang": "de"}),
    ])
    res = classify.classify_document(_nodes(), fed, k=5)   # _nodes() is English
    assert "stw" in res["absent"] and "stw" not in res["present"]
    assert "msc" in res["present"]


def test_classify_document_no_vocab_is_graceful():
    res = classify.classify_document(_nodes(), Federation([]), k=5)
    assert res["present"] == [] and res["msc_top"] == []


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
