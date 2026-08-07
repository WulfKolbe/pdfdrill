"""`translate` writes into the MODEL, so a rebuild discards it.

The translated text lives on the objects (`text` translated, `text_source` the
original). `model --force` reconstructs the Document from lines.json, which
never held the translation — so it is gone, while the sidecar still carries the
TRANSLATED fact and `translated_lang`. The document then reports as translated
and shows one language.

Observed on 576-659-1-PB (ru -> EN-US, 81 objects): after the library rebuild
the model and the tiddler array had zero translated fields, and only a
markdown file written two months earlier still held the Russian.

Same shape as `model:citations_resolved`: a fact about model CONTENT has to be
checked against the model.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmodel.core import Document, DocObject
from pdfdrill import planner


class _SC:
    def __init__(self, facts=()):
        self._f = set(facts)

    def has(self, f):
        return f in self._f


def _model(tmp_path, name, translated: bool):
    doc = Document()
    props = {"text": "Hello world, this is prose."}
    if translated:
        props["text_source"] = "Привет мир, это проза."
    doc.add(DocObject(type="Paragraph", props=props))
    p = tmp_path / name
    p.write_text(json.dumps(doc.to_dict()))
    return p


def test_a_stale_TRANSLATED_fact_does_not_mean_translated(tmp_path):
    """The exact regression: the fact survives the rebuild, the text does not."""
    m = _model(tmp_path, "a.json", translated=False)
    sc = _SC({"TRANSLATED"})
    assert planner.detect("model:translated", sc, Path("d.pdf"), m) is False


def test_translated_model_is_detected(tmp_path):
    m = _model(tmp_path, "b.json", translated=True)
    assert planner.detect("model:translated", _SC(), Path("d.pdf"), m) is True


def test_untranslated_document_without_the_fact_is_not_flagged(tmp_path):
    """A document nobody asked to translate must not look like a failure."""
    m = _model(tmp_path, "c.json", translated=False)
    assert planner.detect("model:translated", _SC(), Path("d.pdf"), m) is False


def test_missing_model_is_not_translated(tmp_path):
    assert planner.detect("model:translated", _SC({"TRANSLATED"}),
                          Path("d.pdf"), tmp_path / "nope.json") is False


def test_status_line_names_the_loss():
    from pdfdrill.commands import _format_translation_state
    out = _format_translation_state(True, False, "EN-US", "ru")
    t = " ".join(out)
    assert "NOT in the model" in t and "ru" in t and "EN-US" in t
    assert "translate" in t                       # says how to restore it


def test_status_is_silent_for_an_untranslated_document():
    from pdfdrill.commands import _format_translation_state
    assert _format_translation_state(False, False, "", "") == []


def test_status_confirms_a_present_translation():
    from pdfdrill.commands import _format_translation_state
    out = _format_translation_state(True, True, "EN-US", "ru")
    assert out and "present in the model" in out[0]
