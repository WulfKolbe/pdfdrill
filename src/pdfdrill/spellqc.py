"""
spellqc — hunspell-backed spellcheck + line-break de-hyphenation QC.

The use case (the author's): OCR/PDF wraps a word across a line with a hyphen
(`Versiche-\nrung`). A hyphen-break is an ARTIFACT iff the *joined* word is a
real word, and a REAL compound iff the *hyphenated* form is (`well-known`). A
spell checker decides; what neither form validates is flagged for review.

On-demand, multi-backend, graceful — and sandbox-aware:
  * spylls   — pure-Python Hunspell (reads .aff/.dic; no C build / binding). Best
               for affixed/compounding languages (German). Lazy-imported.
  * enchant  — pyenchant (wraps libhunspell). Used when it has the language.
  * dic-set  — read the .dic directly into a word set. No deps, works offline;
               misses affix-generated forms, so it's the FLOOR, not the goal.
Dictionaries are discovered from disk (/usr/share/hunspell, texstudio, flatpak,
a repo `dicts/`, $HUNSPELL_DICT_DIR). German needs de_DE.{aff,dic} dropped into
one of those (only en_US ships in the locked-down sandbox). When no dictionary is
available the QC falls back to the proven soft-break heuristic.

Distinct from `pyphen` (where hyphens MAY legally go, TeX patterns) — this is the
inverse: detecting and correcting WRONG hyphens via dictionary lookup.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

# well-/self-/non-… : a real prefix-compound, never a soft hyphen
PRESERVE_PREFIXES = {"well", "self", "non", "anti", "pre", "post", "co", "ex",
                     "semi", "sub", "re", "un", "inter", "intra", "multi"}

_TAGS = {"de": ["de_DE", "de_AT", "de_CH"], "en": ["en_US", "en_GB", "en_GB-large"],
         "fr": ["fr_FR", "fr"], "es": ["es_ES", "es"], "it": ["it_IT", "it"],
         "nl": ["nl_NL", "nl"]}

_DICT_DIRS = [
    os.environ.get("HUNSPELL_DICT_DIR", ""),
    str(Path(__file__).resolve().parents[2] / "dicts"),     # repo-bundled
    "/usr/share/hunspell", "/usr/share/myspell/dicts", "/usr/share/texstudio",
    str(Path.home() / ".local/share/hunspell"),
    "/var/lib/flatpak/runtime/org.freedesktop.Platform/x86_64/24.08",
]


def _discover(lang: str) -> Optional[dict]:
    """Find a dictionary for `lang` (ISO-639-1) on disk → {tag, dic, aff?}."""
    tags = _TAGS.get(lang, [f"{lang}_{lang.upper()}", lang])
    for d in _DICT_DIRS:
        if not d or not os.path.isdir(d):
            continue
        for tag in tags:
            hits = list(Path(d).rglob(f"{tag}.dic"))
            if hits:
                dic = hits[0]
                aff = dic.with_suffix(".aff")
                return {"tag": tag, "dic": dic, "aff": aff if aff.exists() else None}
    return None


class Speller:
    """A loaded dictionary for one language. `ok(word)` → True/False, or None when
    no dictionary is available. `strong` is True for affix-aware backends."""

    def __init__(self, lang: str):
        self.lang = lang
        self.backend = None              # 'spylls' | 'enchant' | 'dic' | None
        self._spylls = self._enchant = None
        self._words: Optional[set] = None
        self._load(lang)

    def _load(self, lang: str) -> None:
        found = _discover(lang)
        # 1. spylls (affix-aware, pure-Python) — needs .aff + .dic
        if found and found["aff"]:
            try:
                from spylls.hunspell import Dictionary
                base = str(found["dic"])[:-4]            # path without .dic
                self._spylls = Dictionary.from_files(base)
                self.backend = "spylls"
                return
            except Exception:
                pass
        # 2. enchant (libhunspell) — when it has the language tag
        try:
            import enchant
            for tag in _TAGS.get(lang, []):
                if enchant.dict_exists(tag):
                    self._enchant = enchant.Dict(tag)
                    self.backend = "enchant"
                    return
        except Exception:
            pass
        # 3. pure .dic word-set floor
        if found:
            try:
                self._words = _load_dic_set(found["dic"])
                self.backend = "dic"
            except Exception:
                pass

    @property
    def available(self) -> bool:
        return self.backend is not None

    @property
    def strong(self) -> bool:
        return self.backend in ("spylls", "enchant")

    @lru_cache(maxsize=100_000)
    def ok(self, word: str) -> Optional[bool]:
        if not word:
            return None
        if self.backend == "spylls":
            return bool(self._spylls.lookup(word))
        if self.backend == "enchant":
            return bool(self._enchant.check(word))
        if self.backend == "dic":
            return word.lower() in self._words
        return None


def _load_dic_set(path: Path) -> set:
    words: set = set()
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if i == 0 and line.strip().isdigit():       # the count header
                continue
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            stem = line.split("/", 1)[0].split("\t", 1)[0]
            if stem:
                words.add(stem.lower())
    return words


_SPELLERS: dict[str, Speller] = {}

def get_speller(lang: str) -> Speller:
    """Load (once, on demand) the dictionary for `lang`. Cached per language."""
    if lang not in _SPELLERS:
        _SPELLERS[lang] = Speller(lang)
    return _SPELLERS[lang]


# --- de-hyphenation QC ------------------------------------------------------

@dataclass
class DehyphResult:
    left: str
    right: str
    joined: str
    hyphenated: str
    decision: str          # 'join' | 'keep' | 'review'
    reason: str


def _heuristic_decision(left: str, right: str) -> tuple[str, str]:
    """The proven soft-break heuristic, used when the dictionary can't decide
    (no dict, or both forms unknown with a weak/absent dict — the German case)."""
    if right[:1].islower() and left.lower() not in PRESERVE_PREFIXES:
        return "join", "heuristic: lowercase continuation, no preserve-prefix"
    return "keep", "heuristic: capitalised continuation or preserve-prefix"


def classify(speller: Optional[Speller], left: str, right: str) -> DehyphResult:
    joined, hyph = left + right, f"{left}-{right}"
    j = speller.ok(joined) if (speller and speller.available) else None
    if j is None:
        j = (speller.ok(joined.lower()) if (speller and speller.available) else None)
    h = speller.ok(hyph) if (speller and speller.available) else None

    if j and not h:
        d, r = "join", "joined form is a valid word; hyphenated form is not"
    elif h and not j:
        d, r = "keep", "hyphenated compound is valid; joined form is not"
    elif j and h:
        d, r = "join", "both valid; a line-end break favours de-hyphenation"
    elif speller and speller.strong:
        # an affix-aware dict says NEITHER form is a word → genuine QC flag
        d, r = "review", "neither form recognised by the dictionary — flag for QC"
    else:
        d, r = _heuristic_decision(left, right)      # weak/absent dict → heuristic
    return DehyphResult(left, right, joined, hyph, d, r)


_BREAK = re.compile(r"(\w+)-[­]?[ \t]*\n[ \t]*(\w+)")

def dehyphenate_text(text: str, lang: Optional[str] = None
                     ) -> tuple[str, list[DehyphResult]]:
    """Repair line-break hyphenation in `text`. Auto-detects the language (→ loads
    that dictionary on demand) when `lang` is None. Returns (fixed, decisions)."""
    if lang is None:
        try:
            from features.extract_language import language_of
            lang = language_of(text)
        except Exception:
            lang = "und"
    speller = get_speller(lang) if lang and lang != "und" else None
    decisions: list[DehyphResult] = []

    def _repl(m: re.Match) -> str:
        res = classify(speller, m.group(1), m.group(2))
        decisions.append(res)
        if res.decision == "join":
            return res.joined
        if res.decision == "keep":
            return res.hyphenated
        return m.group(0)                  # review → leave untouched
    return _BREAK.sub(_repl, text), decisions


def dictionary_status() -> dict:
    """Which languages have a loadable dictionary, and via which backend."""
    out = {}
    for lang in _TAGS:
        sp = get_speller(lang)
        out[lang] = sp.backend or "none"
    return out
