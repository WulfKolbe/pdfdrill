"""Materialization must never overwrite a translation.

`materialize_transclusions` rebuilds a paragraph's text from the TiddlyWiki
projector, which builds from the IMMUTABLE SOURCE stream — the document's
ORIGINAL language. On a translated model it therefore writes the original over
the translation and, because it uses `setdefault`, leaves `text_source` equal to
`text`: both languages become the source one, and the object still looks
translated to every check that only asks whether the twin exists.

Running `pdfdrill clean` on kolbe2018hubbard destroyed 23 of 200 translated
paragraphs exactly this way. Presence of a `_source` twin is not evidence of a
translation; a twin that DIFFERS is.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.heading_cleanup import is_translated, materialize_transclusions


class _Obj:
    def __init__(self, type_, **props):
        self.type = type_
        self.props = dict(props)


class _Doc:
    def __init__(self, objs, bibkey="k"):
        self._objs = objs
        self.meta = {"bibkey": bibkey}

    @property
    def objects(self):
        return {str(i): o for i, o in enumerate(self._objs)}

    def objects_of_type(self, t):
        return [o for o in self._objs if o.type == t]


def test_is_translated_needs_a_DIFFERING_twin():
    assert is_translated(_Obj("Paragraph", text="EN", text_source="DE"), "text")
    # materialised, not translated — the twin is the same prose
    assert not is_translated(_Obj("Paragraph", text="X", text_source="X"), "text")
    assert not is_translated(_Obj("Paragraph", text="X"), "text")
    assert not is_translated(_Obj("Paragraph"), "text")


def test_a_translated_paragraph_is_skipped(monkeypatch):
    """The source stream is German; the paragraph is English. Materializing
    would put the German back and call it done."""
    doc = _Doc([_Obj("Paragraph", flow_index=1,
                     text="Correlation in the Hubbard Model",
                     text_source="Korrelation im Hubbard Modell")])
    monkeypatch.setattr("pdfdrill.heading_cleanup._projected_paragraphs",
                        lambda d: {"k_PARA_0001": "Korrelation im Hubbard Modell"})
    assert materialize_transclusions(doc) == 0
    p = doc.objects["0"]
    assert p.props["text"] == "Correlation in the Hubbard Model"
    assert p.props["text_source"] == "Korrelation im Hubbard Modell"


def test_an_untranslated_paragraph_is_still_materialized(monkeypatch):
    doc = _Doc([_Obj("Paragraph", flow_index=1, text="See \\(x\\) here")])
    monkeypatch.setattr("pdfdrill.heading_cleanup._projected_paragraphs",
                        lambda d: {"k_PARA_0001": "See {{k_FO0001||FO}} here"})
    assert materialize_transclusions(doc) == 1
    p = doc.objects["0"]
    assert p.props["text"] == "See {{k_FO0001||FO}} here"
    assert p.props["text_source"] == "See \\(x\\) here"


def test_a_second_run_over_a_materialized_paragraph_changes_nothing(monkeypatch):
    doc = _Doc([_Obj("Paragraph", flow_index=1,
                     text="See {{k_FO0001||FO}} here",
                     text_source="See \\(x\\) here")])
    monkeypatch.setattr("pdfdrill.heading_cleanup._projected_paragraphs",
                        lambda d: {"k_PARA_0001": "See {{k_FO0001||FO}} here"})
    assert materialize_transclusions(doc) == 0
