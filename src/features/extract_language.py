"""
extract_language — detect the language of a text.

Multi-engine, best-first: lingua (most accurate on short/mixed text) → langdetect
→ langid; each is lazy-imported and skipped if absent. A pure-Python stopword
heuristic is the final fallback, so detection ALWAYS returns a result offline
with zero dependencies (the pdfdrill graceful-degradation pattern). Returns an
ISO-639-1 code ("de"/"en"/…), a confidence, and which engine decided — or "und"
when the text is too short / has no signal.

Optional accuracy upgrade: `pip install 'pdfdrill[lang]'` (lingua-language-detector
+ langdetect). Without it, langdetect (if present) or the heuristic is used.
"""
from __future__ import annotations

import re

from .features import Feature

# Small common-function-word sets for the dependency-free fallback. Distinctive
# words (der/die/das vs the/and/of vs le/la/les …) separate the common European
# languages pdfdrill meets; overlaps (de "de" ↔ nl "de") are broken by the rest.
_STOP = {
    "en": {"the", "and", "of", "to", "in", "is", "that", "for", "with", "you",
           "this", "are", "be", "on", "it", "as", "at", "by", "your", "we", "an"},
    "de": {"der", "die", "und", "das", "ist", "den", "von", "zu", "mit", "für",
           "sie", "ein", "eine", "auf", "nicht", "dem", "des", "im", "ihr", "wir",
           "sich", "bitte", "wörtern", "auch", "oder", "werden"},
    "fr": {"le", "la", "les", "et", "de", "des", "un", "une", "est", "que",
           "pour", "dans", "avec", "vous", "sur", "ne", "pas", "ce", "qui"},
    "es": {"el", "la", "los", "las", "de", "que", "y", "en", "un", "una", "por",
           "con", "para", "su", "no", "se", "del", "es", "como"},
    "it": {"il", "la", "di", "che", "e", "un", "una", "per", "con", "non", "le",
           "si", "del", "della", "sono", "come", "anche"},
    "nl": {"de", "het", "een", "en", "van", "is", "dat", "op", "te", "niet",
           "met", "zijn", "voor", "aan", "ook", "wij", "uw"},
}

_TOK = re.compile(r"[a-zà-ÿ]+", re.I)
_lingua = None


def _heuristic(text: str) -> dict:
    toks = [t.lower() for t in _TOK.findall(text or "")]
    if not toks:
        return {"lang": "und", "confidence": 0.0, "engine": "heuristic"}
    scores = {lang: sum(1 for t in toks if t in sw) / len(toks) for lang, sw in _STOP.items()}
    best = max(scores, key=scores.get)
    hit = scores[best]
    if hit < 0.02:                                  # essentially no function words matched
        return {"lang": "und", "confidence": round(hit, 3), "engine": "heuristic"}
    return {"lang": best, "confidence": round(min(hit * 3.0, 0.95), 3), "engine": "heuristic"}


def _lingua_detect(text: str):
    global _lingua
    try:
        from lingua import LanguageDetectorBuilder
    except Exception:
        return None
    try:
        if _lingua is None:
            _lingua = LanguageDetectorBuilder.from_all_languages().build()
        lang = _lingua.detect_language_of(text)
        if lang is None:
            return None
        code = lang.iso_code_639_1.name.lower()
        try:
            conf = float(_lingua.compute_language_confidence(text, lang))
        except Exception:
            conf = 0.9
        return {"lang": code, "confidence": round(conf, 3), "engine": "lingua"}
    except Exception:
        return None


def _langdetect_detect(text: str):
    try:
        from langdetect import detect_langs, DetectorFactory
        DetectorFactory.seed = 0                    # deterministic
    except Exception:
        return None
    try:
        res = detect_langs(text)
        if res:
            return {"lang": str(res[0].lang), "confidence": round(float(res[0].prob), 3),
                    "engine": "langdetect"}
    except Exception:
        return None
    return None


def _langid_detect(text: str):
    try:
        import langid
    except Exception:
        return None
    try:
        lang, score = langid.classify(text)
        return {"lang": lang, "confidence": round(1.0 / (1.0 + pow(2.718, -score / 100.0)), 3),
                "engine": "langid"}
    except Exception:
        return None


def detect_language(text: str) -> dict:
    """Return {lang (ISO-639-1 or 'und'), confidence 0..1, engine}."""
    t = (text or "").strip()
    if len(t) < 3:
        return {"lang": "und", "confidence": 0.0, "engine": "none"}
    for engine in (_lingua_detect, _langdetect_detect, _langid_detect):
        r = engine(t)
        if r and r.get("lang") and r["lang"] != "und":
            return r
    return _heuristic(t)


def language_of(text: str) -> str:
    """Just the ISO-639-1 code (or 'und')."""
    return detect_language(text)["lang"]


def available() -> bool:
    return True                                     # the heuristic fallback always runs


def extract(text: str, page_id: str = "") -> list[Feature]:
    """One LANGUAGE feature for the whole text (the document/page language)."""
    r = detect_language(text)
    if r["lang"] == "und":
        return []
    return [Feature.create(page_id, "LANGUAGE", r["lang"], r["confidence"])]
