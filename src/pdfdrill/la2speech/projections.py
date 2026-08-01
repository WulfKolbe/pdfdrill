"""Named projections.

A projection is one named, declared transformation of a document representation.
There is more than one useful projection of the same source, so they are
registered by name rather than hardwired into a single `project()`:

    latex     .tex      -> expanded LaTeX   (macros expanded, identifiers protected)
    docmodel  .tex      -> tiddler array    (formulas -> math tiddlers, uses -> {{FO/n}})
    speech    tiddlers  -> tiddlers + speech field

Each declares what it reads and what it writes, so `--list-projections` can
describe the set without importing anything that needs a speech engine.

`docmodel` is what moves transclusion out of the LaTeX layer: it resolves the
`filecontents`/`readarray` machinery once, at docmodel construction, turning
every array entry into a tiddler and every use into a `{{..}}` reference. After
that the speech pass never sees `\\FO[n]` at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import latexproject as lp

__all__ = ["Projection", "PROJECTIONS", "get", "names", "describe",
           "project_latex", "project_docmodel"]


@dataclass(frozen=True)
class Projection:
    name: str
    summary: str
    reads: str
    writes: str
    run: Callable


PROJECTIONS: Dict[str, Projection] = {}


def _register(p: Projection) -> Projection:
    PROJECTIONS[p.name] = p
    return p


def get(name: str) -> Projection:
    try:
        return PROJECTIONS[name]
    except KeyError:
        raise KeyError(
            f"unknown projection {name!r}; known: {', '.join(names())}") from None


def names() -> List[str]:
    return sorted(PROJECTIONS)


def describe() -> str:
    w = max(len(n) for n in names())
    return "\n".join(
        f"  {p.name:<{w}}  {p.reads} -> {p.writes}\n"
        f"  {'':<{w}}  {p.summary}"
        for p in (PROJECTIONS[n] for n in names()))


# --------------------------------------------------------------------------
# latex: .tex -> expanded LaTeX
# --------------------------------------------------------------------------

def project_latex(tex: str, protect: bool = True,
                  exclude: Sequence[str] = (),
                  warnings: Optional[List[str]] = None) -> str:
    """Expand user macros and protect multi-letter identifiers."""
    table, array = lp.harvest_macros(tex), lp.resolve_array(tex)
    return lp.project(tex, table, array, protect=protect, exclude=exclude,
                      warnings=warnings)


_register(Projection(
    name="latex",
    summary="expand \\newcommand macros and formula-array references; wrap "
            "multi-letter identifiers in \\text{}",
    reads=".tex",
    writes="expanded LaTeX",
    run=project_latex))


# --------------------------------------------------------------------------
# docmodel: .tex -> tiddler array
# --------------------------------------------------------------------------

_FILECONTENTS = re.compile(
    r"\\begin\{filecontents\*?\}(?:\[[^\]]*\])?\{[^}]*\}\n.*?"
    r"\\end\{filecontents\*?\}", re.S)
_DOCBODY = re.compile(r"\\begin\{document\}(.*?)\\end\{document\}", re.S)
#: `\ensuremath{ {{X}} }` / `${{X}}$` -- a transclusion needs no math shift of
#: its own; the target tiddler carries its own representation.
_UNWRAP = re.compile(r"\\ensuremath\s*\{\s*(\{\{[^{}]*\}\})\s*\}|"
                     r"\$\s*(\{\{[^{}]*\}\})\s*\$")

#: A display environment wrapping nothing but a transclusion is scaffolding the
#: docmodel must not keep. Left in place, a cached transclusion substitutes
#: already-spoken text back inside `\begin{equation}`, which then goes through
#: the math pipeline a second time and comes out spelled: "R s u b 12".
#: applied anywhere in the body, not just to whole paragraphs -- a source with
#: no blank line before its first equation glues it onto the preceding text, and
#: the scaffolding would survive there too.
_ENV_LONE = re.compile(
    r"\\begin\{([A-Za-z@]+)\*?\}\s*(\{\{[^{}]*\}\})\s*\\end\{\1\*?\}", re.S)
_SHIFT_LONE = re.compile(r"\$\$\s*(\{\{[^{}]*\}\})\s*\$\$", re.S)
_BRACKET_LONE = re.compile(r"\\\[\s*(\{\{[^{}]*\}\})\s*\\\]", re.S)

#: Display math is a unit of the document in its own right, so it becomes its
#: own tiddler whether or not the source left a blank line around it. gummi.tex
#: has none before its first equation, which would otherwise glue that equation
#: onto the end of the preceding paragraph.
_DISPLAY_ENVS = ("equation", "displaymath", "eqnarray", "align", "alignat",
                 "gather", "multline", "flalign", "split", "dmath", "dgroup",
                 "aligned", "gathered", "alignedat")
_DISPLAY = re.compile(
    r"\$\$.*?\$\$|\\\[.*?\\\]|"
    r"\\begin\{(" + "|".join(_DISPLAY_ENVS) + r")\*?\}.*?\\end\{\1\*?\}", re.S)


def _split_units(body: str):
    """Yield (chunk, is_display) covering the body in order, no gaps."""
    pos = 0
    for m in _DISPLAY.finditer(body):
        if m.start() > pos:
            yield body[pos:m.start()], False
        yield m.group(0), True
        pos = m.end()
    if pos < len(body):
        yield body[pos:], False


def project_docmodel(tex: str, prefix: str = "FO", para: str = "Para",
                     warnings: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Split a document into tiddlers, formulas first.

    Every formula-array entry becomes its own tiddler carrying the LaTeX in a
    `latex` field; every reference to it in the body becomes a `{{prefix/n}}`
    transclusion. Expansion is reused for the rewrite by pointing the array at
    transclusion strings instead of at the formulas themselves, so `\\FO[2]`,
    `\\Expr{2}` and `\\EqExpr{2}` are all rewritten by the same machinery that
    already knows how to find them.
    """
    table = lp.harvest_macros(tex)
    array = lp.resolve_array(tex)
    tiddlers: List[Dict[str, Any]] = []

    for i, entry in enumerate(array.entries, 1):
        tiddlers.append({"title": f"{prefix}/{i}", "latex": entry,
                         "kind": "math"})

    refs = lp.ArrayRef(macro=array.macro, data_file=array.data_file,
                       entries=tuple("{{%s/%d}}" % (prefix, i)
                                     for i in range(1, len(array.entries) + 1)))
    body = tex
    m = _DOCBODY.search(tex)
    if m:
        body = m.group(1)
    body = _FILECONTENTS.sub("", body)
    body = lp.expand(body, table, refs, warnings=warnings, fix_ensuremath=False)
    # inline shifts only; the display forms are stripped per unit below, after
    # the split, so that being display is not lost with the wrapper.
    body = _UNWRAP.sub(lambda g: g.group(1) or g.group(2), body)

    n = 0
    for chunk, is_display in _split_units(body):
        pieces = ([(chunk.strip(), True)] if is_display
                  else [(p.strip(), False) for p in re.split(r"\n\s*\n", chunk)])
        for text, display in pieces:
            if not text:
                continue
            lone = (_ENV_LONE.fullmatch(text) or _SHIFT_LONE.fullmatch(text)
                    or _BRACKET_LONE.fullmatch(text))
            if lone:
                text, display = lone.group(lone.lastindex), True
            n += 1
            t: Dict[str, Any] = {"title": f"{para}/{n}", "kind": "text",
                                 "text": text}
            # display comes from the source having a display wrapper, not from a
            # paragraph merely containing one reference: \Expr is defined with
            # \ensuremath and is inline even when it stands on its own line.
            if display:
                t["display"] = True
            tiddlers.append(t)
    return tiddlers


_register(Projection(
    name="docmodel",
    summary="one tiddler per formula-array entry plus one per paragraph; "
            "array references become {{..}} transclusions",
    reads=".tex",
    writes="tiddler array",
    run=project_docmodel))


# --------------------------------------------------------------------------
# speech: tiddlers -> tiddlers + speech field
# --------------------------------------------------------------------------

def project_speech(tiddlers, speaker, field: str = "speech",
                   mode: str = "cached"):
    """Merge spoken text onto each tiddler. Imported lazily: this is the only
    projection that needs a running speech engine."""
    from . import tiddlerpipe
    return tiddlerpipe.speak_tiddlers(tiddlers, speaker, field=field, mode=mode)


_register(Projection(
    name="speech",
    summary="speak every tiddler through one long-lived engine and merge the "
            "result back onto the same object",
    reads="tiddler array",
    writes="tiddler array + speech field",
    run=project_speech))


# --------------------------------------------------------------------------
# text: tiddlers -> flat speakable string
# --------------------------------------------------------------------------

def project_text(tiddlers: Sequence[Dict[str, Any]], field: str = "speech",
                 math_kind: str = "math", sep: str = "\n\n") -> str:
    """Flatten a spoken docmodel back into one string, in document order.

    Math tiddlers are skipped: they are transcluded into the bodies that
    reference them, so emitting them as well would say every formula twice.
    """
    out = [str(t[field]).strip() for t in tiddlers
           if t.get("kind") != math_kind and str(t.get(field, "")).strip()]
    return sep.join(out)


_register(Projection(
    name="text",
    summary="flatten a spoken docmodel into one string in document order, "
            "skipping math tiddlers already transcluded into their bodies",
    reads="tiddler array + speech field",
    writes="flat text",
    run=project_text))
