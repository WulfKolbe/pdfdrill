"""815 — the four defects a `translate --from CN` run exposed."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pdfdrill import deepl_client as D                       # noqa: E402


# ── 1. a wrong language code is refused before anything is spent ─────────────

def test_CN_is_refused_and_named():
    """`CN` is the ISO COUNTRY code for China; DeepL wants the LANGUAGE code ZH.
    Before this, CN reached DeepL, got a 400, had its error discarded, and the
    run reported a successful translation with every string unchanged."""
    why = D.check_lang("CN", target=False)
    assert why and "ZH" in why and "--from ZH" in why


@pytest.mark.parametrize("bad,good", [
    ("CN", "ZH"), ("JP", "JA"), ("KR", "KO"), ("ZH-CN", "ZH"),
])
def test_common_mistakes_name_the_right_code(bad, good):
    why = D.check_lang(bad, target=False)
    assert why and good in why


def test_a_bare_EN_target_is_refused_because_DeepL_wants_a_region():
    why = D.check_lang("EN", target=True)
    assert why and ("EN-US" in why or "EN-GB" in why)


@pytest.mark.parametrize("code", ["ZH", "DE", "RU", "JA", "en", "de"])
def test_a_valid_source_passes(code):
    assert D.check_lang(code, target=False) is None


@pytest.mark.parametrize("code", ["EN-US", "EN-GB", "PT-BR", "DE", "ZH-HANS"])
def test_a_valid_target_passes(code):
    assert D.check_lang(code, target=True) is None


def test_an_unknown_code_lists_what_is_accepted():
    why = D.check_lang("XX", target=False)
    assert why and "ZH" in why and "DE" in why


def test_no_code_is_no_objection():
    assert D.check_lang("", target=False) is None


def test_the_source_and_target_sets_are_not_the_same():
    """DeepL accepts `EN` as a source and refuses it as a target; conflating the
    two lists is how a bare `EN` target slips through."""
    assert "EN" in D.SOURCE_LANGS and "EN" not in D.TARGET_LANGS
    assert "EN-US" in D.TARGET_LANGS and "EN-US" not in D.SOURCE_LANGS


# ── 2. a refused request raises instead of returning the originals ───────────

def test_an_http_error_raises_and_carries_DeepLs_message(monkeypatch):
    """The client read DeepL's error body into a local variable and then threw it
    away, returning the ORIGINAL texts — so a refused paid call was
    byte-identical to a successful one."""
    import urllib.error
    import io

    def boom(*a, **kw):
        raise urllib.error.HTTPError(
            "u", 400, "Bad Request", {},
            io.BytesIO(json.dumps(
                {"message": "Value for 'source_lang' not supported."}
            ).encode()))

    monkeypatch.setattr(D.net, "urlopen", boom)
    monkeypatch.setattr(D, "_api_key", lambda: "k:fx")
    with pytest.raises(D.DeepLError) as ei:
        D.translate_batch(["你好"], "EN-US", "CN")
    assert "source_lang" in str(ei.value)
    assert "400" in str(ei.value)


def test_empty_input_still_short_circuits(monkeypatch):
    monkeypatch.setattr(D, "_api_key", lambda: "k:fx")
    assert D.translate_batch([], "EN-US") == []
    assert D.translate_batch(["", "  "], "EN-US") == ["", "  "]


# ── 3. the canonical Markdown is not overwritten by the LLM-compact form ─────

def test_translate_writes_the_bilayer_to_its_own_name():
    """`<bibkey>.md` is the canonical Markdown, written only by `_write_md`
    (which maintains the `md` layer that fetch/toc/abstract/render read). The
    bi-layer is the LLM-compact form — no images, no tables, a formula appendix
    — and belongs beside it, not on top of it."""
    src = (Path(__file__).resolve().parents[1]
           / "src" / "pdfdrill" / "commands.py").read_text()
    body = src.split("def cmd_translate", 1)[1].split("\ndef ", 1)[0]
    assert 'f"{key}.bilayer.md"' in body
    assert 'f"{key}.md"' not in body


def test_the_message_does_not_claim_a_translation_that_did_not_happen():
    src = (Path(__file__).resolve().parents[1]
           / "src" / "pdfdrill" / "commands.py").read_text()
    body = src.split("def cmd_translate", 1)[1].split("\ndef ", 1)[0]
    assert "Nothing to translate" in body
    assert "No DeepL call was made" in body


# ── 4. the loop: tiddlers says re-run translate, and re-running restores it ──

def test_reapply_runs_even_when_no_rebuild_is_needed():
    """`cmd_tiddlers` rewrites the file from the model, so the file is newer than
    the model and nothing changed — while the prose has just reverted to the
    source language. The old early return did nothing in exactly that state, so
    the advice `tiddlers` prints ("re-run translate to restore it") could not
    work."""
    src = (Path(__file__).resolve().parents[1]
           / "src" / "pdfdrill" / "commands.py").read_text()
    body = src.split("def _rebuild_tiddlers_for_translation", 1)[1].split("\ndef ", 1)[0]
    guard = body.split("if not (model_changed or stale or force):", 1)[1]
    early = guard.split("\n        return", 1)[0]      # the statement, not the word
    assert "_reapply_from_memory" in early, (
        "the no-rebuild path must still put the remembered translations back")


def test_reapply_from_memory_restores_a_reverted_tiddler(tmp_path):
    from pdfdrill import commands as C
    from pdfdrill import translation_memory as tm
    tid = tmp_path / "t.json"
    original = "Das ist ein Satz."
    tiddlers = [{"title": "X_PARA_0001", "tags": "paragraph X",
                 "text": original}]
    tid.write_text(json.dumps(tiddlers))
    # `tm.load` returns the ENTRIES dict, which is what `reapply` takes.
    remembered = {"X_PARA_0001": {
        "field": "text", "src_key": tm.key_of(original),
        "source": original, "translated": "This is a sentence."}}
    n = C._reapply_from_memory(tid, remembered)
    assert n == 1
    back = json.loads(tid.read_text())
    assert back[0]["text"] == "This is a sentence."


def test_reapply_leaves_a_tiddler_whose_prose_changed_alone(tmp_path):
    from pdfdrill import commands as C
    from pdfdrill import translation_memory as tm
    tid = tmp_path / "t.json"
    tid.write_text(json.dumps([{"title": "X_PARA_0001", "tags": "paragraph X",
                                "text": "Etwas ganz anderes."}]))
    remembered = {"X_PARA_0001": {
        "field": "text", "src_key": tm.key_of("Das ist ein Satz."),
        "source": "Das ist ein Satz.", "translated": "This is a sentence."}}
    C._reapply_from_memory(tid, remembered)
    assert json.loads(tid.read_text())[0]["text"] == "Etwas ganz anderes."
