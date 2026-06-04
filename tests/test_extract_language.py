"""
Language detection (features.extract_language). Multi-engine (lingua →
langdetect → langid) with a pure-Python stopword fallback so it ALWAYS returns a
result offline with zero deps — the pdfdrill graceful-degradation pattern.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from features import extract_language as el


DE = "Sehr geehrter Herr Kolbe, bitte begleichen Sie den fälligen Betrag für Ihre Versicherung."
EN = "Dear customer, please settle the outstanding amount for your insurance as soon as possible."


def test_detect_language_de_en():
    assert el.detect_language(DE)["lang"] == "de"
    assert el.detect_language(EN)["lang"] == "en"


def test_detect_language_reports_engine_and_confidence():
    r = el.detect_language(DE)
    assert r["engine"] in ("lingua", "langdetect", "langid", "heuristic")
    assert 0.0 <= r["confidence"] <= 1.0


def test_pure_heuristic_fallback_no_libs():
    # the dependency-free path must still tell German from English
    assert el._heuristic("der die das und ist ein brief auf deutsch mit vielen wörtern")["lang"] == "de"
    assert el._heuristic("the and of to in is a letter in english with many words")["lang"] == "en"


def test_short_or_empty_is_undetermined():
    assert el.detect_language("")["lang"] == "und"
    assert el.detect_language("  ")["lang"] == "und"
    assert el.language_of("x") == "und"


def test_extract_emits_one_language_feature():
    feats = el.extract(DE, page_id="p1")
    assert len(feats) == 1
    f = feats[0]
    assert f.type == "LANGUAGE" and f.value == "de" and f.page_id == "p1"


def test_extract_all_includes_language():
    from features import extract_all, available_extractors
    assert available_extractors().get("language") is True   # always available (fallback)
    types = {f.type for f in extract_all(EN, "p1")}
    assert "LANGUAGE" in types


if __name__ == "__main__":
    for fn in (test_detect_language_de_en, test_detect_language_reports_engine_and_confidence,
               test_pure_heuristic_fallback_no_libs, test_short_or_empty_is_undetermined,
               test_extract_emits_one_language_feature, test_extract_all_includes_language):
        fn(); print("PASS", fn.__name__)
    print("\nAll tests passed.")
