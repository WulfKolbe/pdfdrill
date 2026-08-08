"""`model --force` silently discards a translation. It must not.

The model is rebuilt from `lines.json`, which never held the translation — so a
rebuild reverts every translated field to the source language. It has destroyed
the same document's translation three times during this work, each time
recoverable only because a backup happened to exist.

`--force` is the right escape hatch for a stale model; losing hours of paid
translation without being told is not.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.commands import model_rebuild_blocked


def test_a_translated_model_blocks_a_rebuild():
    msg = model_rebuild_blocked(translated=True, lang="EN-US", allow=False)
    assert msg
    assert "EN-US" in msg
    assert "--force-discard-translation" in msg      # names the escape hatch
    assert "translate" in msg                        # and the cost of using it


def test_the_explicit_escape_hatch_allows_it():
    assert model_rebuild_blocked(True, "EN-US", allow=True) == ""


def test_an_untranslated_model_is_never_blocked():
    assert model_rebuild_blocked(False, None, allow=False) == ""


def test_cmd_model_consults_the_guard():
    import inspect
    from pdfdrill import commands
    assert "model_rebuild_blocked" in inspect.getsource(commands.cmd_model)
