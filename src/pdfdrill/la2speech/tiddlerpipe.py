"""Tiddler docmodel -> speech, as a projection/import pass.

The docmodel is a list of tiddlers, each a dict with a `title` and an open bag
of fields. Nothing here builds a parallel index: in TiddlyWiki the *title* is
already the unique, deterministic, source-correlated identifier, so it is the
provenance marker the contract asks for, and results merge back onto the same
object as another field.

    docmodel ──project()──> pipeline input ──speak()──> results ──import()──> docmodel

Why the batch matters: the speech backend costs ~260 ms to start and ~4 ms per
expression, so the whole docmodel goes through one long-lived process. A tiddler
is never handed to a freshly started engine.

Macros are harvested across the *whole* docmodel before any single tiddler is
projected. A preamble tiddler defines `\\FO` while body tiddlers use it, so
per-tiddler harvesting would silently fail to expand exactly those references.

Three transclusion modes are implemented because they put the spoken form in
three different places; see TRANSCLUSION_MODES.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import latexproject as lp

__all__ = [
    "is_math_tiddler",
    "math_source",
    "load_tiddlers",
    "save_tiddlers",
    "harvest_docmodel",
    "speak_tiddlers",
    "resolve_transclusions",
    "parse_hybrid",
    "TRANSCLUSION_MODES",
]

#: A -- "inline": `{{FO/2}}` pulls the target's `latex` and speaks it at each use
#:      site. The spoken form lives only in the referring tiddler.
#: B -- "cached": math tiddlers are spoken first into their own `speech` field;
#:      a reference then pulls that field. Spoken once, reused, and correctable
#:      in one place.
#: C -- "hybrid": `{{key||MACRO, latex="..", speech=".."}}` carries source and
#:      speech inside the marker itself; nothing external is consulted.
TRANSCLUSION_MODES = ("inline", "cached", "hybrid")

_TRANSCLUDE = re.compile(r"\{\{([^{}|!]+?)(?:!!([A-Za-z0-9_-]+))?\}\}")

#: A math wrapper whose entire body is one reference is scaffolding: the target
#: tiddler already knows it is math. Stripped before resolution so cached speech
#: is not substituted back into a math context and re-spoken as letters
#: ("R s u b 12"). Covers $..$, $$..$$, \[..\], \(..\) and \begin{env}..\end{env}.
_WRAPPED_ALONE = (
    re.compile(r"\\begin\{([A-Za-z@]+)\*?\}\s*(\{\{[^{}]*\}\})\s*\\end\{\1\*?\}", re.S),
    re.compile(r"\$\$\s*(\{\{[^{}]*\}\})\s*\$\$", re.S),
    re.compile(r"\\\[\s*(\{\{[^{}]*\}\})\s*\\\]", re.S),
    re.compile(r"\\\(\s*(\{\{[^{}]*\}\})\s*\\\)", re.S),
    re.compile(r"\$\s*(\{\{[^{}]*\}\})\s*\$", re.S),
)

_MATH_REGION = re.compile(
    r"\\begin\{([A-Za-z@]+\*?)\}.*?\\end\{\1\}|\$\$.*?\$\$|"
    r"\\\[.*?\\\]|\\\(.*?\\\)|(?<!\\)\$.*?(?<!\\)\$", re.S)


def _strip_lone_wrappers(text: str) -> str:
    for rx in _WRAPPED_ALONE:
        text = rx.sub(lambda m: m.group(m.lastindex), text)
    return text


def _math_spans(text: str) -> List[Tuple[int, int]]:
    """Character ranges that are math, for deciding how a reference resolves."""
    out = []
    for m in _MATH_REGION.finditer(text):
        if m.group(0).startswith("\\begin"):
            env = m.group(1).rstrip("*")
            from .latexproject import _math_envs
            if env not in _math_envs():
                continue
        out.append((m.start(), m.end()))
    return out
_HYBRID = re.compile(r"\{\{([^{}|]+?)\|\|(.+?)\}\}", re.S)
_KV = re.compile(r'([A-Za-z0-9_-]+)\s*=\s*"((?:[^"\\]|\\.)*)"')


# --------------------------------------------------------------------------
# docmodel I/O
# --------------------------------------------------------------------------

def load_tiddlers(path: str) -> List[Dict[str, Any]]:
    """Read a LATW-style tiddler array."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON array of tiddlers")
    for t in data:
        if not isinstance(t, dict) or "title" not in t:
            raise ValueError(f"{path}: every tiddler needs a title: {t!r}")
    return data


def save_tiddlers(path: str, tiddlers: Sequence[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(list(tiddlers), fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def _by_title(tiddlers: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {t["title"]: t for t in tiddlers}


# --------------------------------------------------------------------------
# projection
# --------------------------------------------------------------------------

def harvest_docmodel(tiddlers: Sequence[Dict[str, Any]],
                     source_fields: Sequence[str] = ("text", "latex")):
    """Collect macros and the formula array across every tiddler at once.

    Returns (MacroTable, ArrayRef). Definitions in a preamble tiddler must be
    visible to body tiddlers, so the whole docmodel is concatenated first.
    """
    joined = "\n".join(str(t[f]) for t in tiddlers
                       for f in source_fields if t.get(f))
    return lp.harvest_macros(joined), lp.resolve_array(joined)


def parse_hybrid(marker_body: str) -> Tuple[Optional[str], Dict[str, str]]:
    """Split `MACRO, latex="..", speech=".."` into (macro, fields)."""
    fields = {k: v.replace('\\"', '"') for k, v in _KV.findall(marker_body)}
    head = marker_body.split(",", 1)[0].strip()
    macro = head if head and "=" not in head else None
    return macro, fields


def resolve_transclusions(text: str,
                          index: Dict[str, Dict[str, Any]],
                          mode: str,
                          field: str,
                          warnings: Optional[List[str]] = None) -> str:
    """Replace `{{..}}` references according to `mode`.

    Returns text in which every reference has become either LaTeX (to be spoken
    downstream) or an already-spoken string.
    """
    def _warn(msg: str) -> None:
        if warnings is not None:
            warnings.append(msg)

    if mode == "hybrid":
        def sub_hybrid(m):
            key, body = m.group(1).strip(), m.group(2)
            _macro, kv = parse_hybrid(body)
            if kv.get("speech"):
                return kv["speech"]
            if kv.get("latex"):
                return "$" + kv["latex"] + "$"
            _warn(f"hybrid transclusion {key!r} carries neither speech nor latex")
            return ""
        return _HYBRID.sub(sub_hybrid, text)

    text = _strip_lone_wrappers(text)
    math = _math_spans(text)

    def in_math(pos: int) -> bool:
        return any(a <= pos < b for a, b in math)

    def sub_ref(m):
        title = m.group(1).strip()
        explicit = m.group(2)
        target = index.get(title)
        if target is None:
            _warn(f"transclusion target not found: {title!r}")
            return ""
        if explicit:
            if explicit not in target:
                _warn(f"{title!r} has no field {explicit!r}")
                return ""
            return str(target[explicit])
        if mode == "cached":
            # Still inside math after the lone-wrapper strip means the reference
            # is one operand among others (`{{FO/1}} + x`). Spoken English is not
            # a valid operand there, so fall back to the LaTeX and let the math
            # pipeline speak the whole expression.
            if in_math(m.start()):
                pass
            elif target.get(field):
                return str(target[field])
            elif not in_math(m.start()):
                _warn(f"{title!r} has no {field!r} field yet; falling back to latex")
        src = target.get("latex") or target.get("text") or ""
        if not src:
            _warn(f"{title!r} has no latex/text to transclude")
            return ""
        # already inside math -- a second math shift would nest and break it
        return str(src) if in_math(m.start()) else "$" + str(src) + "$"

    return _TRANSCLUDE.sub(sub_ref, text)


# --------------------------------------------------------------------------
# the pass
# --------------------------------------------------------------------------

def is_math_tiddler(t: Dict[str, Any], math_kind: str = "math") -> bool:
    """A tiddler is math if it carries a `latex` field.

    Real pdfdrill output marks these with `tags: formula` and gives them a
    `text` holding the TiddlyWiki widget `<$latex text={{!!latex}} .../>`, not
    the formula. Keying off `kind == "math"` matched nothing in that corpus, and
    reading `text` spoke the widget markup ("latex text=!!latex displayMode=..")
    because the `$` in `<$latex` opened math mode. The presence of `latex` is
    the reliable signal; `kind`/`tags` are accepted as secondary.
    """
    if t.get("latex"):
        return True
    if t.get("kind") == math_kind:
        return True
    return "formula" in str(t.get("tags") or "").split()


def math_source(t: Dict[str, Any]) -> str:
    """The LaTeX to speak for a math tiddler, preferring `latex` over `text`."""
    src = t.get("latex") or t.get("latex_original") or ""
    if not src:
        return ""
    display = str(t.get("displayMode", "")).lower() in ("true", "1", "yes")
    return ("$$" + str(src) + "$$") if display else "$" + str(src) + "$"


def speak_tiddlers(tiddlers: Sequence[Dict[str, Any]],
                   speaker,
                   field: str = "speech",
                   mode: str = "cached",
                   error_field: Optional[str] = None,
                   math_kind: str = "math") -> Dict[str, int]:
    """Speak every tiddler and merge the result back onto the same object.

    `speaker` is a LatexSpeaker; it holds one long-lived backend, so the whole
    docmodel is a single batch. Returns counters for reporting.

    Mutates the tiddlers in place: `tiddler[field]` gains the spoken text, and
    `tiddler[error_field]` any per-tiddler failures.
    """
    if mode not in TRANSCLUSION_MODES:
        raise ValueError(f"mode must be one of {TRANSCLUSION_MODES}")
    error_field = error_field or f"{field}-errors"
    index = _by_title(tiddlers)
    table, array = harvest_docmodel(tiddlers)
    stats = {"spoken": 0, "calls": 0, "skipped": 0, "warnings": 0}

    def run(t: Dict[str, Any], src: str) -> None:
        before_err = len(speaker.errors)
        before_calls = speaker.math_calls
        warnings: List[str] = []
        resolved = resolve_transclusions(src, index, mode, field, warnings)
        if not resolved.strip():
            stats["skipped"] += 1
            return
        out = speaker.speak(resolved, strip_preamble=False,
                            table=table, array=array)
        stats["calls"] += speaker.math_calls - before_calls
        t[field] = out.strip()
        stats["spoken"] += 1
        new = warnings + speaker.errors[before_err:]
        if new:
            t[error_field] = new
            stats["warnings"] += len(new)

    # cached mode has to speak the math objects before any body that pulls their
    # field, so the docmodel is walked in two passes rather than one.
    if mode == "cached":
        for t in tiddlers:
            if is_math_tiddler(t, math_kind):
                src = math_source(t)
                if src:
                    run(t, src)
        for t in tiddlers:
            if not is_math_tiddler(t, math_kind) and t.get("text"):
                run(t, str(t["text"]))
    else:
        for t in tiddlers:
            src = (math_source(t) if is_math_tiddler(t, math_kind)
                   else str(t.get("text") or ""))
            if src:
                run(t, src)
    return stats
