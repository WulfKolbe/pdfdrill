"""
classify — math/subject classification of a drilled document against the
vocabnet controlled vocabularies (MSC first; any compiled scheme in
vocab/compiled/ participates, and the federation keeps the misses as signal).

Pure helpers here (`gather_classification_text`, `has_translation`,
`msc_rollup`, `classify_document`); `commands.cmd_classify` wires them over the
fast DocGraph read path and persists the result in the sidecar.

The vocabulary labels are English (MSC titles), so German prose only matches
after translation — `pdfdrill translate` writes the English into each object's
`text` field and keeps the original under `text_source` (which `has_translation`
detects). Equation LaTeX and section captions are strong, often
language-neutral signal regardless.
"""
from __future__ import annotations

import re

# object types whose prose carries subject signal
_PROSE = ("Section", "Paragraph", "Abstract", "ListItem", "Footnote", "Toc")
_MATH = ("Equation", "Formula")
_CONCEPT = ("Concept",)

_LATEX_CMD = re.compile(r"\\[a-zA-Z]+")


def _strip_latex(s: str) -> str:
    """Remove LaTeX control words so math doesn't inject English noise:
    `\\partial`→"partial", `\\right`→"right", `\\frac` etc. spuriously match MSC
    titles ("PDEs with multivalued right-hand sides", "Right alternative rings").
    What remains is identifiers (mass, energy names) — the real lexical signal."""
    return _LATEX_CMD.sub(" ", s)


def has_translation(nodes) -> bool:
    """True if any prose object carries a `*_source` field (a translation has
    replaced the original in place)."""
    for o in nodes:
        p = getattr(o, "props", {})
        if any(k.endswith("_source") and p.get(k) for k in p):
            return True
    return False


def classification_segments(nodes, prefer_source: bool = False) -> list[str]:
    """The classifiable units of a document, one string each: section/abstract/
    toc captions, paragraph/list/footnote prose, equation/formula LaTeX, named
    concepts. Empty/null math skipped; non-text objects (pictures) excluded.
    Segments (not one giant blob) are what the voting classifier scores.

    `prefer_source` reads the ORIGINAL-language field (`<field>_source`, written
    by `pdfdrill translate`) when present, else falls back to the current field —
    so a German vocabulary classifies the German original directly. Math/concept
    text is language-neutral and identical either way."""
    prose_keys = (("text_source", "caption_source", "content_source",
                   "text", "caption", "content", "title") if prefer_source
                  else ("text", "caption", "content", "title"))
    segs: list[str] = []
    for o in nodes:
        t = getattr(o, "type", "")
        p = getattr(o, "props", {})
        if t in _PROSE:
            for key in prose_keys:
                v = p.get(key)
                if v:
                    segs.append(str(v))
                    break
        elif t in _MATH:
            v = p.get("latex") or p.get("latex_original") or ""
            if v and str(v).lower() not in ("null", "none"):
                stripped = _strip_latex(str(v))
                if len(re.findall(r"[A-Za-z]{3,}", stripped)) >= 1:
                    segs.append(stripped)
        elif t in _CONCEPT:
            v = p.get("name") or p.get("pref") or p.get("title")
            if v:
                segs.append(str(v))
    return segs


def gather_classification_text(nodes) -> str:
    """The classifiable text as one string (segments joined) — for language
    detection and a char count."""
    return "\n".join(classification_segments(nodes))


def msc_rollup(hits) -> dict:
    """Sum hit scores by two-digit MSC class (81T08/81Txx -> 81), sorted by
    summed score descending — the document's discipline distribution."""
    roll: dict[str, float] = {}
    for h in hits:
        m = re.match(r"^(\d{2})", getattr(h, "code", "") or "")
        if not m:
            continue
        roll[m.group(1)] = roll.get(m.group(1), 0.0) + float(getattr(h, "score", 0.0))
    return dict(sorted(roll.items(), key=lambda kv: (-kv[1], kv[0])))


# MSC-title filler bigrams: structural phrases that appear in many titles and in
# generic prose, so a hit grounded only on these is not evidence of subject.
_FILLER_BIGRAMS = {
    "in connection", "connection with", "none of", "of the", "such as",
    "and other", "related to", "other than", "the above", "as in", "and their",
    "general and", "based on", "the topics", "topics on", "but in",
    "above but",
}

# Function/stop words (EN + DE). A bigram of TWO stopwords ("in die", "with the",
# "und der") is never subject evidence — this generalises the per-language filler
# lists so we don't have to enumerate every function-word pair (the "in die"
# bug behind the "Eintritt <Raumfahrt>" outlier). A bigram with >=1 content word
# ("eintritt in", "gravitational field") still counts.
_STOPWORDS = {
    # English
    "a", "an", "the", "of", "in", "on", "for", "and", "or", "to", "with", "by",
    "as", "at", "is", "are", "be", "but", "from", "into", "this", "that", "its",
    "their", "other", "above", "general", "than", "such", "these", "those",
    # German (folded: umlauts stripped)
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einer", "einem",
    "einen", "im", "an", "auf", "fur", "und", "oder", "mit", "von", "zu", "zur",
    "zum", "aus", "uber", "durch", "bei", "ist", "sind", "wird", "werden", "als",
    "am", "um", "vor", "nach", "bis", "dass", "sich", "auch", "nur", "wie",
}


def _is_filler_bigram(g: str) -> bool:
    """A bigram carries no subject signal if it is a known boilerplate phrase OR
    both of its tokens are stop/function words."""
    if g in _FILLER_BIGRAMS:
        return True
    parts = g.split()
    return len(parts) == 2 and all(p in _STOPWORDS for p in parts)


def _phrase_evidence(hit) -> bool:
    """True if the match rests on a CONTENTFUL multi-word phrase: a bigram in the
    evidence that is neither MSC-title boilerplate ("in connection with") nor a
    pure function-word pair ("in die", "with the"). A single shared word doesn't
    count."""
    return any(" " in g and not _is_filler_bigram(g)
               for g in getattr(hit, "evidence", []))


def _is_catchall(pref: str) -> bool:
    p = (pref or "").lower()
    return ("none of the above" in p or p.startswith("general reference")
            or "miscellaneous" in p)


def classify_document(nodes, federation, k: int = 8, per_seg: int = 3,
                      require_phrase: bool = True) -> dict:
    """Classify by SEGMENT VOTING: run the federation over each segment, tally
    per-scheme code votes (+ summed score), and rank by votes then score. This
    is robust to document length (a whole-doc blob lets generic high-frequency
    words dominate); a code that recurs as a top match across many segments is
    the real subject.

    `require_phrase` (default) only counts a hit grounded in a multi-word phrase
    match ("gravitational field", "quantum field theory") — a single shared
    generic word ("right", "theory", "structure") does not vote. This is the key
    precision lever on lexical subject matching. If a segment yields no phrase
    hit at all, its (unigram-only) hits are dropped rather than adding noise.
    Returns a JSON-ready result. Graceful when no vocabulary."""
    # English vocabularies match the (translated) `text`; German vocabularies
    # match the original `text_source` — so each scheme classifies the language
    # it was built in.
    en_segs = [s for s in classification_segments(nodes) if s.strip()]
    de_segs = [s for s in classification_segments(nodes, prefer_source=True) if s.strip()]
    text_chars = sum(len(s) for s in en_segs)
    if not federation.vocabs or not en_segs:
        return {"present": [], "absent": sorted(federation.vocabs),
                "profile": {}, "msc_top": [], "msc_sections": {},
                "per_source": {}, "chars": text_chars, "segments": len(en_segs)}

    votes: dict[str, dict[str, int]] = {s: {} for s in federation.vocabs}
    score: dict[str, dict[str, float]] = {s: {} for s in federation.vocabs}
    pref: dict[str, str] = {}
    for scheme, vocab in federation.vocabs.items():
        lang = (vocab.meta.get("lang") or "en").lower()
        segs = de_segs if lang.startswith("de") else en_segs
        for seg in segs:
            hits = vocab.classify(seg, k=per_seg * 2 if require_phrase else per_seg)
            if require_phrase:
                hits = [h for h in hits if _phrase_evidence(h)][:per_seg]
            for h in hits:
                if _is_catchall(h.pref):
                    continue
                votes[scheme][h.code] = votes[scheme].get(h.code, 0) + 1
                score[scheme][h.code] = score[scheme].get(h.code, 0.0) + h.score
                pref[h.code] = h.pref

    def ranked(scheme: str) -> list[dict]:
        codes = sorted(votes[scheme],
                       key=lambda c: (-votes[scheme][c], -score[scheme][c], c))
        return [{"code": c, "pref": pref.get(c, ""), "votes": votes[scheme][c],
                 "score": round(score[scheme][c], 3)} for c in codes[:k]]

    present = sorted(s for s in federation.vocabs if votes[s])
    per_source = {s: ranked(s) for s in present}
    msc_top = per_source.get("msc", [])
    sections: dict[str, int] = {}
    for h in msc_top:
        cl = h["code"][:2]
        sections[cl] = sections.get(cl, 0) + h["votes"]
    return {
        "present": present,
        "absent": sorted(s for s in federation.vocabs if not votes[s]),
        "profile": {s: (per_source[s][0]["score"] if per_source.get(s) else 0.0)
                    for s in federation.vocabs},
        "msc_top": msc_top,
        "msc_sections": dict(sorted(sections.items(), key=lambda kv: (-kv[1], kv[0]))),
        "per_source": per_source,
        "chars": text_chars,
        "segments": len(segs),
    }
