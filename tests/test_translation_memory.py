"""A translation must survive the rebuild that regenerates its file — 786.

The tiddler translation cannot live on the model: the TiddlyWiki projector
rebuilds transcluded paragraphs from the immutable source stream BY OFFSET, so
a translated `text` on a model object never reaches the tiddler. Which is why
`translate` runs a second, tiddler-level pass — and why, before this, the
translation existed in exactly one file.

Any plain `pdfdrill tiddlers` then regenerated that file from the model and
dropped every translation without a word. BH1org_OCR shows it in two
timestamps — `.md` translated 2026-08-27, `.tiddlers.json` rebuilt 2026-08-29 —
and recovering it re-sent 689,340 characters to DeepL for prose already paid
for once, about EUR 14 at Pro rates.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import translation_memory as tm


def _field_for(t):
    return "text" if "text" in t else None


def _translated():
    return [
        {"title": "A", "text": "Elementary Structures of Matter",
         "text_source": "Elementarstrukturen der Materie"},
        {"title": "B", "text": "Unified Field Theory",
         "text_source": "Einheitliche Feldtheorie"},
        {"title": "C", "text": "never translated"},
    ]


def _rebuilt():
    """What the projector emits: the German back, no `_source` anywhere."""
    return [
        {"title": "A", "text": "Elementarstrukturen der Materie"},
        {"title": "B", "text": "Einheitliche Feldtheorie"},
        {"title": "C", "text": "never translated"},
    ]


def test_a_rebuild_gets_its_translation_back(tmp_path):
    entries = tm.harvest(_translated(), _field_for)
    tm.save(tmp_path, "BH1org_OCR", entries, target_lang="EN-US", source_lang="DE")

    fresh = _rebuilt()
    applied, stale = tm.reapply(fresh, tm.load(tmp_path, "BH1org_OCR"), _field_for)

    assert (applied, stale) == (2, 0)
    assert fresh[0]["text"] == "Elementary Structures of Matter"
    assert fresh[0]["text_source"] == "Elementarstrukturen der Materie"
    assert "text_source" not in fresh[2], "an untranslated tiddler is untouched"


def test_prose_the_projection_changed_is_left_alone(tmp_path):
    """The one failure worse than an untranslated tiddler: an OLD translation
    pasted over NEW text. Nothing downstream can detect that, so the source
    hash decides and a mismatch abstains."""
    entries = tm.harvest(_translated(), _field_for)
    tm.save(tmp_path, "k", entries, target_lang="EN-US")

    fresh = _rebuilt()
    fresh[0]["text"] = "Elementarstrukturen der Materie, zweite Auflage"
    applied, stale = tm.reapply(fresh, tm.load(tmp_path, "k"), _field_for)

    assert (applied, stale) == (1, 1)
    assert fresh[0]["text"].endswith("zweite Auflage")
    assert "text_source" not in fresh[0]


def test_an_already_translated_tiddler_is_not_touched_again(tmp_path):
    """Idempotence: reapplying to a file that still carries its translations
    changes nothing, so a rerun costs neither an edit nor a character."""
    entries = tm.harvest(_translated(), _field_for)
    tm.save(tmp_path, "k", entries, target_lang="EN-US")
    already = _translated()
    assert tm.reapply(already, tm.load(tmp_path, "k"), _field_for) == (0, 0)


def test_a_record_shape_from_another_version_is_ignored(tmp_path):
    p = tm.path_for(tmp_path, "k")
    p.write_text('{"version": 0, "entries": {"A": {"field": "text"}}}')
    assert tm.load(tmp_path, "k") == {}, \
        "half-reading an older shape is worse than translating again"


def test_no_memory_is_an_empty_dict_not_an_error(tmp_path):
    assert tm.load(tmp_path, "never-translated") == {}
