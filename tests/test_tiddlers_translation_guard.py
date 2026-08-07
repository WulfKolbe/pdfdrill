"""Regenerating tiddlers silently reverts a translated document.

The TiddlyWiki projector rebuilds paragraphs from the IMMUTABLE SOURCE stream by
offset, to re-insert `{{..||FO}}` tokens — so it emits the ORIGINAL language.
`translate` knows this and translates the projected file afterwards, at the
tiddler level. Any later `pdfdrill tiddlers` re-projects and throws that away:
the wiki reverts to the source language (and to any markup `clean` removed)
while the model still holds the translation, and nothing says so.

Found by the external drillcheck audit as `translate.parity.tiddlers`; I then
reproduced it by regenerating this document's tiddlers myself and reverting 170
translated tiddlers to German without noticing.

The projection is not fixed here — re-deriving offset-aligned transclusions for
translated prose is the deeper change flagged in CLAUDE.md. What must not stand
is that it happens QUIETLY.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.commands import _tiddler_translation_warning


def _tids(with_source):
    t = {"title": "k_PARA_0001", "tags": "paragraph", "text": "Korrelation"}
    if with_source:
        t["text_source"] = "Korrelation"
    return [t, {"title": "k", "tags": "bibtex", "text": "root"}]


def test_a_translated_document_projected_monolingual_is_reported():
    msg = _tiddler_translation_warning(claims_translated=True, lang="EN-US",
                                       tiddlers=_tids(False))
    assert msg
    assert "EN-US" in msg
    assert "translate" in msg               # names the command that repairs it


def test_a_projection_that_kept_the_source_layer_is_silent():
    assert _tiddler_translation_warning(True, "EN-US", _tids(True)) == ""


def test_an_untranslated_document_is_silent():
    """The 3000 monolingual documents must not grow a warning."""
    assert _tiddler_translation_warning(False, None, _tids(False)) == ""


def test_an_empty_projection_is_silent():
    assert _tiddler_translation_warning(True, "EN-US", []) == ""
