"""Portuguese must not be reported as Spanish.

The dependency-free fallback knew en/de/fr/es/it/nl. A Brazilian-Portuguese
translation therefore came back as `es` at 0.6 — and the inspector's language
selector renders the detected code as a FLAG, so a Portuguese document would
have flown the Spanish one. Found while translating arXiv 2409.18839 to PT-BR:
the translation was correct and my verification of it was not.

Portuguese and Spanish share most function words (de/que/e/en/no/por/con), so
the set has to lean on what differs: `não/são/com/uma/dos/das/pelo/ser/mais/já`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from features.extract_language import _heuristic, language_of

_PT = ("Uma solução de código aberto para a extração precisa do conteúdo de "
       "documentos. Os resultados não são apenas mais rápidos, mas também "
       "melhores do que os métodos existentes, com uma qualidade superior.")
_ES = ("Una solución de código abierto para la extracción precisa del contenido "
       "de los documentos. Los resultados no son sólo más rápidos, sino también "
       "mejores que los métodos existentes, con una calidad superior.")
_EN = ("An open-source solution for precise document content extraction. The "
       "results are not only faster but also better than existing methods.")
_DE = ("Eine quelloffene Lösung für die präzise Extraktion von Dokumentinhalten. "
       "Die Ergebnisse sind nicht nur schneller, sondern auch besser.")


def test_portuguese_is_portuguese():
    assert _heuristic(_PT)["lang"] == "pt", _heuristic(_PT)
    assert language_of(_PT) == "pt"


def test_spanish_is_still_spanish():
    """Adding pt must not steal es — they share most function words."""
    assert _heuristic(_ES)["lang"] == "es", _heuristic(_ES)


def test_the_other_languages_are_unaffected():
    assert _heuristic(_EN)["lang"] == "en"
    assert _heuristic(_DE)["lang"] == "de"


def test_the_inspector_flies_the_right_flag_for_a_pt_br_translation():
    from pdfdrill.docinspect import document_languages, flag_for
    m = {"meta": {"bibkey": "k"}, "streams": {}, "alignments": [],
         "objects": [{"id": "p1", "type": "Paragraph", "realizations": [],
                      "props": {"text": _PT, "text_source": _EN}}]}
    langs = document_languages(m)
    assert [l["code"] for l in langs] == ["pt", "en"]
    assert langs[0]["flag"] == "\U0001F1F5\U0001F1F9"      # 🇵🇹 for bare pt
    assert flag_for("PT-BR") == "\U0001F1E7\U0001F1F7"     # 🇧🇷 for the variant


# --------------------------------------------------------------------------
# scoring: a word shared by five languages is not evidence for any of them
# --------------------------------------------------------------------------

def test_a_shared_word_counts_for_less_than_a_distinctive_one():
    """`de` appears in fr/es/it/nl/pt; `são` only in pt. Counting both as one
    hit is what let Spanish win on Portuguese text — the sets overlap by
    construction, so the SHARE of a hit has to fall with the number of
    languages that claim it."""
    from features.extract_language import _word_weight
    assert _word_weight("são") > _word_weight("de")
    assert _word_weight("de") > 0                   # still evidence, just weak


def test_a_long_real_paragraph_is_classified_by_the_document_sample():
    """The document-level sample is thousands of characters of mixed prose —
    where the near-tie actually bit. Short strings were already fine."""
    long_pt = (_PT + " ") * 12
    assert _heuristic(long_pt)["lang"] == "pt", _heuristic(long_pt)
    long_es = (_ES + " ") * 12
    assert _heuristic(long_es)["lang"] == "es", _heuristic(long_es)


def test_unrecognisable_text_is_still_und():
    assert _heuristic("xyzzy plugh frobnicate")["lang"] == "und"
    assert _heuristic("")["lang"] == "und"


def test_the_recorded_translation_target_beats_detection():
    """`translate` records the target it actually asked DeepL for
    (`meta["translated_lang"]`). Detection can only ever return the bare
    language, so a PT-BR translation flew the Portugal flag. The recorded
    target is not a guess — prefer it."""
    from pdfdrill.docinspect import document_languages
    m = {"meta": {"bibkey": "k", "translated_lang": "PT-BR"},
         "streams": {}, "alignments": [],
         "objects": [{"id": "p1", "type": "Paragraph", "realizations": [],
                      "props": {"text": _PT, "text_source": _EN}}]}
    langs = document_languages(m)
    assert langs[0]["code"] == "PT-BR"
    assert langs[0]["flag"] == "\U0001F1E7\U0001F1F7"     # 🇧🇷
    assert langs[0]["label"] == "PT-BR"
    assert langs[1]["code"] == "en"                        # source still detected


def test_detection_still_used_when_nothing_was_recorded():
    from pdfdrill.docinspect import document_languages
    m = {"meta": {"bibkey": "k"}, "streams": {}, "alignments": [],
         "objects": [{"id": "p1", "type": "Paragraph", "realizations": [],
                      "props": {"text": _PT, "text_source": _EN}}]}
    assert document_languages(m)[0]["code"] == "pt"


# --------------------------------------------------------------------------
# both languages are KNOWN — `--from EN --to PT-BR` needs no detector at all
# --------------------------------------------------------------------------

def test_a_declared_translation_needs_no_detection():
    """`translate --from EN --to PT-BR` states both languages. Detecting them
    afterwards is guessing at a fact already on record — and guessing wrongly,
    since a detector returns a bare language and cannot know PT-BR from PT."""
    from pdfdrill.docinspect import document_languages
    called = []

    def _never(text):
        called.append(text)
        return "xx"

    m = {"meta": {"bibkey": "k", "translated_lang": "PT-BR", "source_lang": "EN"},
         "streams": {}, "alignments": [],
         "objects": [{"id": "p1", "type": "Paragraph", "realizations": [],
                      "props": {"text": _PT, "text_source": _EN}}]}
    langs = document_languages(m, detect=_never)
    assert called == [], "the detector was consulted for a declared translation"
    assert [l["code"] for l in langs] == ["PT-BR", "EN"]
    assert [l["flag"] for l in langs] == ["\U0001F1E7\U0001F1F7", "\U0001F1EC\U0001F1E7"]


def test_detection_fills_only_what_was_not_declared():
    """`--from` is optional (DeepL can auto-detect), so a half-declared
    translation still detects the missing half — and only that half."""
    from pdfdrill.docinspect import document_languages
    seen = []

    def _detect(text):
        seen.append(text[:20])
        return "en"

    m = {"meta": {"bibkey": "k", "translated_lang": "PT-BR"},
         "streams": {}, "alignments": [],
         "objects": [{"id": "p1", "type": "Paragraph", "realizations": [],
                      "props": {"text": _PT, "text_source": _EN}}]}
    langs = document_languages(m, detect=_detect)
    assert len(seen) == 1, "detected more than the undeclared half"
    assert [l["code"] for l in langs] == ["PT-BR", "en"]


def test_translate_records_the_source_language_it_was_given():
    import inspect
    from pdfdrill import commands
    body = inspect.getsource(commands.cmd_translate)
    assert 'meta["source_lang"]' in body
