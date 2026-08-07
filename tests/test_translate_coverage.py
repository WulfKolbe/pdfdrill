"""Everything a reader READS must switch language — captions and the TOC too.

`translate` covered Paragraph/Abstract/Section/Footnote/Sidenote/ListItem and
stopped, on the reasoning that "math/code/image/table objects are not
natural-language prose". True of an image; false of its CAPTION. So an English
view of a German thesis showed English paragraphs interleaved with German figure
captions ("Figure 1.1. Darstellung einer Heisenberg-Kette …") and a wholly German
table of contents — measured on kolbe2018hubbard as 37 untranslated of the first
59 rendered nodes.

A partially translated document is worse than an untranslated one: the reader
cannot tell which parts they are allowed to trust.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.commands import _TRANSLATE_MODEL_FIELD, translate_model_prose


class _Obj:
    def __init__(self, type_, **props):
        self.type = type_
        self.props = dict(props)


class _Doc:
    def __init__(self, objs):
        self.objects = {str(i): o for i, o in enumerate(objs)}


def _fake_batch(texts, target, source):
    return ["EN:" + t for t in texts]


def test_figure_and_table_captions_are_translated():
    for t in ("Picture", "Diagram", "Chart", "Table", "Figure"):
        assert _TRANSLATE_MODEL_FIELD.get(t) == "caption", t


def test_the_table_of_contents_is_translated():
    assert _TRANSLATE_MODEL_FIELD.get("Toc") == "text"


def test_image_content_itself_is_never_touched():
    """The caption is prose; the LaTeX, the URL and the cell data are not."""
    d = _Doc([_Obj("Diagram", caption="Darstellung einer Kette",
                   latex_code="\\begin{tikzpicture}\\end{tikzpicture}",
                   cdn_url="https://cdn.mathpix.com/x.jpg"),
              _Obj("Table", caption="Ergebnisse", raw_text="1 | 2 | 3")])
    assert translate_model_prose(d, _fake_batch, "EN-US") == 2
    dia, tab = d.objects["0"], d.objects["1"]
    assert dia.props["caption"] == "EN:Darstellung einer Kette"
    assert dia.props["caption_source"] == "Darstellung einer Kette"
    assert dia.props["latex_code"] == "\\begin{tikzpicture}\\end{tikzpicture}"
    assert dia.props["cdn_url"] == "https://cdn.mathpix.com/x.jpg"
    assert tab.props["raw_text"] == "1 | 2 | 3"      # cell data is data


def test_math_objects_stay_out_of_the_translator():
    for t in ("Formula", "Equation", "Link", "Reference", "Citation", "Page"):
        assert t not in _TRANSLATE_MODEL_FIELD, t


def test_a_caption_already_translated_is_not_retranslated():
    """Re-running must cost nothing for what is done — the DeepL call is paid."""
    d = _Doc([_Obj("Diagram", caption="EN:done", caption_source="fertig")])
    assert translate_model_prose(d, _fake_batch, "EN-US") == 0


def test_only_the_missing_fields_are_sent():
    """A document translated before this fix has its paragraphs done and its
    captions missing; re-running must send the captions ONLY."""
    sent = []

    def spy(texts, target, source):
        sent.extend(texts)
        return ["EN:" + t for t in texts]

    d = _Doc([_Obj("Paragraph", text="EN:already", text_source="schon"),
              _Obj("Diagram", caption="Abbildung einer Kette"),
              _Obj("Toc", text="1 Einleitung 1")])
    assert translate_model_prose(d, spy, "EN-US") == 2
    assert sorted(sent) == ["1 Einleitung 1", "Abbildung einer Kette"]
