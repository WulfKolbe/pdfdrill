"""
825 — adopting a translation from an older model of the same document.

`translate` writes the target language IN PLACE over each prose object's
`text`; there is no `text_original`, so `model --force` reverts it and the only
surviving record is an older model FILE. This project lost BH3FR's EN-US
translation exactly that way.

The join is what needs a test. Two builds of one document share no object ids
and no stream anchors — both are minted per build — and prose objects carry no
region. What they do share is `lines.json`, and `(type, page,
from_line_index, to_line_index)` indexes into it, so the key is stable by
construction. The failure this guards against is not "no text copied"; it is
text copied onto the WRONG paragraph, which reads perfectly and is wrong.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmodel.core import Document, DocObject              # noqa: E402
from pdfdrill.translation_restore import restore, translated_text  # noqa: E402


def _obj(otype, page, frm, to, text):
    return DocObject(type=otype,
                     props={"page": page, "from_line_index": frm,
                            "to_line_index": to, "text": text})


def _doc(objs, meta=None):
    d = Document()
    d.meta.update(meta or {})
    for o in objs:
        d.add(o)
    return d


def _source(tmp_path, objs, meta=None):
    """An older model on disk, as `restore` reads it: plain JSON."""
    p = tmp_path / "old.docmodel.json"
    p.write_text(json.dumps({
        "meta": {"translated_lang": "EN-US", "source_lang": "DE", **(meta or {})},
        "streams": {}, "alignments": [],
        "objects": [{"id": o.id, "type": o.type, "props": o.props} for o in objs],
    }), encoding="utf-8")
    return p


def test_the_translation_lands_on_the_matching_paragraph(tmp_path):
    src = _source(tmp_path, [
        _obj("Paragraph", 1, 0, 3, "the first, in English"),
        _obj("Paragraph", 1, 4, 9, "the second, in English"),
    ])
    doc = _doc([_obj("Paragraph", 1, 4, 9, "der zweite, auf Deutsch"),
                _obj("Paragraph", 1, 0, 3, "der erste, auf Deutsch")])
    stats = restore(doc, src)
    assert stats["restored"] == 2
    got = {(o.props["from_line_index"], o.props["text"])
           for o in doc.objects.values()}
    # ORDER is not the key: the second object in the document is the first
    # paragraph of the page, and it must still get its own translation.
    assert got == {(0, "the first, in English"), (4, "the second, in English")}


def test_an_object_a_later_pass_created_is_left_alone(tmp_path):
    """Sections went 6 -> 33 on BH3FR between the two builds. A heading the
    older model never had has nothing to copy, and inventing one would attach
    a translation to text it was never made from."""
    src = _source(tmp_path, [_obj("Paragraph", 1, 0, 3, "in English")])
    doc = _doc([_obj("Paragraph", 1, 0, 3, "auf Deutsch"),
                _obj("Section", 1, 4, 4, "Eine Überschrift")])
    stats = restore(doc, src)
    assert stats["restored"] == 1
    assert stats["skipped"] == {"Section": 1}
    sec = next(o for o in doc.objects.values() if o.type == "Section")
    assert sec.props["text"] == "Eine Überschrift"


def test_an_ambiguous_key_is_withheld_from_both_sides(tmp_path):
    """Two objects with one label: neither can be attributed, so neither is
    used. Picking either would be a coin toss written into the document."""
    src = _source(tmp_path, [
        _obj("Paragraph", 2, 0, 1, "one English"),
        _obj("Paragraph", 2, 0, 1, "another English"),
    ])
    text, _ = translated_text(src)
    assert text == {}
    doc = _doc([_obj("Paragraph", 2, 0, 1, "auf Deutsch")])
    stats = restore(doc, src)
    assert stats["restored"] == 0
    assert stats["skipped"] == {"Paragraph": 1}


def test_a_duplicate_key_in_the_LIVE_model_is_also_withheld(tmp_path):
    src = _source(tmp_path, [_obj("Paragraph", 3, 0, 1, "in English")])
    doc = _doc([_obj("Paragraph", 3, 0, 1, "eins"),
                _obj("Paragraph", 3, 0, 1, "zwei")])
    stats = restore(doc, src)
    assert stats["restored"] == 0
    assert stats["skipped"] == {"Paragraph": 2}


def test_it_is_idempotent(tmp_path):
    src = _source(tmp_path, [_obj("Paragraph", 1, 0, 3, "in English")])
    doc = _doc([_obj("Paragraph", 1, 0, 3, "auf Deutsch")])
    assert restore(doc, src)["restored"] == 1
    again = restore(doc, src)
    assert again["restored"] == 0 and again["unchanged"] == 1


def test_the_provenance_is_the_digest_not_the_path(tmp_path):
    """A path and an mtime do not survive `scp`; the sha256 does. Every model
    on every machine is called model.docmodel.json, so the basename says
    nothing about WHICH translation this text came from."""
    import hashlib
    src = _source(tmp_path, [_obj("Paragraph", 1, 0, 3, "in English")])
    doc = _doc([_obj("Paragraph", 1, 0, 3, "auf Deutsch")])
    restore(doc, src)
    rec = doc.meta["translation_restored"]
    assert rec["sha256"] == hashlib.sha256(src.read_bytes()).hexdigest()
    assert rec["objects"] == 1
    assert doc.meta["translated_lang"] == "EN-US"
    assert doc.meta["source_lang"] == "DE"


def test_an_untranslated_source_sets_no_language(tmp_path):
    """The command refuses on this; `restore` reports it rather than inventing
    a language for text that was never translated."""
    p = tmp_path / "old.docmodel.json"
    p.write_text(json.dumps({"meta": {}, "streams": {}, "alignments": [],
                             "objects": []}), encoding="utf-8")
    doc = _doc([_obj("Paragraph", 1, 0, 3, "auf Deutsch")])
    stats = restore(doc, p)
    assert stats["lang"] is None
    assert "translated_lang" not in doc.meta
