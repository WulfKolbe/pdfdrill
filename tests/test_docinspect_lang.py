"""A translated document is BILINGUAL — the inspector must let you read either.

`pdfdrill translate` replaces prose in place and keeps the original under
`<field>_source`, so a translated model carries both languages on every prose
object. The inspector rendered only the replacement, which silently hides half
of what the model holds — and worse, it hid it INCONSISTENTLY: a Paragraph
showed the translation (its `text` prop) while a Footnote showed the original
(no `text` prop, so the renderer fell back to the raw source-stream preview).

These tests pin the three pieces the language selector needs:
  * per element, which of its fields carry an original-language twin
  * per document, the language list (empty when monolingual — no selector)
  * the client contract: the choice is DOCUMENT state, persisted, so paging
    never resets it (the thing the user explicitly asked for).
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import docinspect


# --------------------------------------------------------------------------
# element_translations — the ORIGINAL-language twin per rec key
# --------------------------------------------------------------------------

def test_element_translations_maps_every_prose_field_to_its_rec_key():
    """`content` is the props name but `text` is the rec key the renderers read
    — a footnote's original must arrive under the key that actually renders."""
    assert docinspect.element_translations(
        {"text": "Hello", "text_source": "Hallo"}) == {"text": "Hallo"}
    assert docinspect.element_translations(
        {"caption": "Lattice", "caption_source": "Gitter"}) == {"caption": "Gitter"}
    assert docinspect.element_translations(
        {"content": "A footnote", "content_source": "Eine Fußnote"}) == {"text": "Eine Fußnote"}
    assert docinspect.element_translations(
        {"raw_text": "a | b", "raw_text_source": "a | b."}) == {"raw_text": "a | b."}


def test_element_translations_ignores_untranslated_and_materialised_sources():
    """A `_source` twin also appears from transclusion MATERIALISATION, where it
    is byte-identical prose — not a second language. An identical twin is not a
    translation and must not put a language switch on the element."""
    assert docinspect.element_translations({"text": "same", "text_source": "same"}) == {}
    assert docinspect.element_translations({"text": "only one language"}) == {}
    assert docinspect.element_translations({"text_source": "orphan"}) == {}
    assert docinspect.element_translations({"text": "x", "text_source": "   "}) == {}


# --------------------------------------------------------------------------
# document_languages — [] for a monolingual document
# --------------------------------------------------------------------------

def _model(objects, bibkey="demo"):
    return {"meta": {"bibkey": bibkey, "num_pages": 1,
                     "pages": [{"page": 1, "page_width": 100, "page_height": 100}]},
            "streams": {}, "objects": objects, "alignments": []}


def test_document_languages_empty_when_nothing_is_translated():
    """No twin anywhere → no selector. The widget must not appear on the 3000
    monolingual documents in the library."""
    m = _model([{"id": "p1", "type": "Paragraph",
                 "props": {"text": "plain english"}, "realizations": []}])
    assert docinspect.document_languages(m) == []


def test_document_languages_lists_translated_first_then_original():
    fake = {"In quantum mechanics two quantities": "en",
            "In der Quantenmechanik kann man zwei": "de"}
    m = _model([{"id": "f1", "type": "Footnote", "props": {
        "content": "In quantum mechanics two quantities",
        "content_source": "In der Quantenmechanik kann man zwei"}, "realizations": []}])
    langs = docinspect.document_languages(m, detect=lambda t: fake.get(t, "und"))
    assert [l["code"] for l in langs] == ["en", "de"]
    assert [l["role"] for l in langs] == ["translated", "original"]
    assert langs[0]["flag"] and langs[1]["flag"] == "\U0001F1E9\U0001F1EA"   # 🇩🇪


def test_document_languages_survives_undetectable_text():
    """Detection must never be the reason the switch disappears — the two
    languages demonstrably EXIST (that is what the twin means)."""
    m = _model([{"id": "p1", "type": "Paragraph",
                 "props": {"text": "aaa", "text_source": "bbb"}, "realizations": []}])
    langs = docinspect.document_languages(m, detect=lambda t: "und")
    assert len(langs) == 2
    assert [l["role"] for l in langs] == ["translated", "original"]
    assert all(l["flag"] for l in langs)          # a neutral flag, never blank


def test_flag_for_handles_regional_variants_and_unknowns():
    assert docinspect.flag_for("EN-US") == "\U0001F1FA\U0001F1F8"     # 🇺🇸
    assert docinspect.flag_for("en") == "\U0001F1EC\U0001F1E7"        # 🇬🇧
    assert docinspect.flag_for("de") == "\U0001F1E9\U0001F1EA"        # 🇩🇪
    assert docinspect.flag_for("und") == "\U0001F310"                 # 🌐 — never ""
    assert docinspect.flag_for("") == "\U0001F310"


# --------------------------------------------------------------------------
# wiring: collect_elements + the emitted HTML
# --------------------------------------------------------------------------

def test_collect_elements_prefers_translated_content_and_carries_the_original():
    """The Footnote regression: `content` holds the translation, so the rec must
    read it instead of falling through to the raw source-stream preview."""
    m = _model([{"id": "f1", "type": "Footnote", "props": {
        "content": "A footnote.", "content_source": "Eine Fußnote.", "page": 1},
        "realizations": []}])
    elements, _ = docinspect.collect_elements(m, docinspect.build_stream_index(m))
    fn = [e for e in elements if e["id"] == "f1"][0]
    assert fn["text"] == "A footnote."
    assert fn["alt"] == {"text": "Eine Fußnote."}


def test_monolingual_element_has_no_alt_key():
    m = _model([{"id": "p1", "type": "Paragraph",
                 "props": {"text": "one language", "page": 1}, "realizations": []}])
    elements, _ = docinspect.collect_elements(m, docinspect.build_stream_index(m))
    assert "alt" not in [e for e in elements if e["id"] == "p1"][0]


def test_html_carries_the_language_list_and_a_persisted_choice():
    """The user's requirement in one assertion: the choice is stored per
    DOCUMENT (localStorage keyed by bibkey), so changing page keeps it."""
    m = _model([{"id": "p1", "type": "Paragraph", "props": {
        "text": "translated", "text_source": "übersetzt", "page": 1},
        "realizations": []}], bibkey="kolbe2018hubbard")
    doc = docinspect.build_inspector_html(m, pages={}, title="t")
    data = json.loads(doc.split("const DATA = ", 1)[1].split(";\n", 1)[0])
    assert len(data["languages"]) == 2
    assert 'id="langSel"' in doc
    assert "localStorage" in doc and "docinspect.lang." in doc


def test_selector_is_absent_from_a_monolingual_document():
    m = _model([{"id": "p1", "type": "Paragraph",
                 "props": {"text": "plain", "page": 1}, "realizations": []}])
    doc = docinspect.build_inspector_html(m, pages={}, title="t")
    data = json.loads(doc.split("const DATA = ", 1)[1].split(";\n", 1)[0])
    assert data["languages"] == []


def test_build_from_paths_still_works_on_a_translated_model():
    m = _model([{"id": "p1", "type": "Paragraph", "props": {
        "text": "translated", "text_source": "übersetzt", "page": 1},
        "realizations": []}])
    with tempfile.TemporaryDirectory() as d:
        mp = Path(d) / "model.docmodel.json"
        mp.write_text(json.dumps(m), encoding="utf-8")
        doc, _pages, n_el, _mode = docinspect.build_from_paths(str(mp), embed=True)
        assert n_el == 1 and 'id="langSel"' in doc
