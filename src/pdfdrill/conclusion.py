"""Retrieve a document's CONCLUDING paragraphs.

The Abstract states the goal + the chosen method, NOT the results; the conclusion
is where the actual outcome lives (and is sometimes much narrower than the
abstract promised). This module locates the conclusion SECTION by a heading
heuristic over the Section captions — the document's own TOC — preferring a strong
match ("Conclusion") that sits before the References/Appendix boundary, and returns
its paragraphs in flow order. With no named conclusion it falls back to the final
body paragraphs.

Pure: every function takes an iterable of objects exposing `.type` / `.props`
(a DocObject or a docgraph node), ordered by `props["flow_index"]`.
"""
from __future__ import annotations

# heading keywords, tiered by how strongly they signal a conclusion
_STRONG = ("conclusion", "concluding", "fazit", "schlussfolgerung")
_MEDIUM = ("summary", "discussion", "outlook", "closing", "final remark",
           "future work", "future direction", "perspectives",
           "zusammenfassung", "schluss")
# sections that mark the END of the main body (the conclusion precedes these)
_END = ("reference", "bibliography", "acknowledg", "appendix", "supplement",
        "literatur", "anhang")


def _cap(o) -> str:
    return (getattr(o, "props", {}).get("caption") or "").strip()


def _text(o) -> str:
    return (getattr(o, "props", {}).get("text") or "").strip()


def _fi(o):
    v = getattr(o, "props", {}).get("flow_index")
    return v if isinstance(v, (int, float)) else None


def _has(cap: str, words) -> bool:
    c = cap.lower()
    return any(w in c for w in words)


def _sections(objs):
    secs = [o for o in objs if getattr(o, "type", None) == "Section"]
    secs.sort(key=lambda o: (_fi(o) is None, _fi(o) or 0))
    return secs


def _end_fi(secs):
    for s in secs:
        if _has(_cap(s), _END):
            return _fi(s)
    return None


def find_conclusion_section(objs):
    """The Section that holds the conclusion, or None. Strong keyword before the
    References/Appendix boundary wins (last one if several); else any strong;
    else a medium keyword before the boundary."""
    secs = _sections(objs)
    if not secs:
        return None
    end = _end_fi(secs)

    def before_end(s):
        return end is None or (_fi(s) is not None and _fi(s) < end)

    for tier, gated in ((_STRONG, True), (_STRONG, False), (_MEDIUM, True)):
        cands = [s for s in secs if _has(_cap(s), tier)
                 and (before_end(s) if gated else True)]
        if cands:
            return max(cands, key=lambda s: _fi(s) or 0)
    return None


def _paragraphs_in_range(objs, sec, secs):
    """Paragraph/ListItem text between `sec` and the next section, in flow order
    (plus any object whose parent_section is this section, for source models)."""
    sfi = _fi(sec)
    later = [_fi(s) for s in secs if _fi(s) is not None and sfi is not None and _fi(s) > sfi]
    nxt = min(later) if later else None
    picked = []
    for o in objs:
        if getattr(o, "type", None) not in ("Paragraph", "ListItem"):
            continue
        fi = _fi(o)
        if fi is None:
            if o.props.get("parent_section") == getattr(sec, "id", None):
                picked.append((-1, o))
            continue
        if sfi is not None and fi > sfi and (nxt is None or fi < nxt):
            picked.append((fi, o))
    picked.sort(key=lambda t: t[0])
    return [_text(o) for _, o in picked if _text(o)]


def conclusion_text(objs, final_n: int = 6) -> dict:
    """{"section": caption|None, "paragraphs": [...], "source": "section"|
    "final_paragraphs"}. Locates the conclusion section; on miss, returns the last
    `final_n` MAIN-body paragraphs (before References/Appendix)."""
    objs = list(objs)
    secs = _sections(objs)
    sec = find_conclusion_section(objs)
    if sec is not None:
        paras = _paragraphs_in_range(objs, sec, secs)
        if paras:
            return {"section": _cap(sec), "paragraphs": paras, "source": "section"}

    # fallback: final body paragraphs, excluding the References/Appendix region
    end = _end_fi(secs)
    body = []
    for o in objs:
        if getattr(o, "type", None) != "Paragraph":
            continue
        t = _text(o)
        if not t:
            continue
        fi = _fi(o)
        if end is not None and fi is not None and fi >= end:
            continue
        body.append((fi if fi is not None else 0, t))
    body.sort(key=lambda t: t[0])
    return {"section": None, "paragraphs": [t for _, t in body[-final_n:]],
            "source": "final_paragraphs"}
