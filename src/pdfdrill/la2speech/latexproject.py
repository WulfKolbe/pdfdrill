"""LaTeX -> expanded LaTeX projection.

`latex2mathml` has no macro table: it converts what it is handed, so a
document's own `\\newcommand` definitions and `readarray` transclusions never
reach the speech engine -- they survive as literal text and get spoken
("backslash FO of 2"). This module is the projection that closes the gap. It
rewrites LaTeX into *expanded* LaTeX, in which

  * every user-defined macro has been substituted away,
  * every formula-array reference has been resolved, and
  * every multi-letter identifier is wrapped so the speech engine reads it as a
    word instead of spelling it out.

Why here and not after the MathML conversion: a MathML-level fix can only reach
identifiers that survived to MathML, and anything still inside an unexpanded
macro never gets there. Wrapping at the LaTeX layer also makes
`\\text{AVERAGE}_{s}` bind the subscript to the whole identifier, which the
per-letter `<mi>` form does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

__all__ = [
    "MacroDef",
    "MacroTable",
    "ArrayRef",
    "harvest_macros",
    "harvest_arrays",
    "find_array_macro",
    "expand",
    "protect_identifiers",
    "project",
    "DEFAULT_MAX_DEPTH",
]

DEFAULT_MAX_DEPTH = 32

#: environments whose bodies are math. Kept in sync with latex2speech by import
#: at call time to avoid a circular import at module load.
_MATH_ENVS_FALLBACK = frozenset({
    "math", "displaymath", "equation", "eqnarray", "align", "alignat",
    "gather", "multline", "flalign", "split", "aligned", "alignedat",
    "gathered", "cases", "array", "matrix", "pmatrix", "bmatrix",
})


def _math_envs() -> frozenset:
    try:
        from latex2speech import MATH_ENVIRONMENTS
        return MATH_ENVIRONMENTS
    except Exception:                                   # pragma: no cover
        return _MATH_ENVS_FALLBACK


# --------------------------------------------------------------------------
# definitions
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class MacroDef:
    """One `\\newcommand`-family definition.

    `default` is the optional-argument default from `\\newcommand{\\x}[2][d]{..}`;
    when present the first argument is optional and `#1` falls back to it.
    """
    name: str
    nargs: int
    body: str
    default: Optional[str] = None


@dataclass
class MacroTable:
    defs: Dict[str, MacroDef] = field(default_factory=dict)

    def get(self, name: str) -> Optional[MacroDef]:
        return self.defs.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self.defs

    def __len__(self) -> int:
        return len(self.defs)

    def names(self) -> List[str]:
        return sorted(self.defs)


@dataclass(frozen=True)
class ArrayRef:
    """The document's formula-array hook: `\\NAME[n]` indexes `entries`."""
    macro: Optional[str] = None
    data_file: Optional[str] = None
    entries: Tuple[str, ...] = ()


# --------------------------------------------------------------------------
# scanning primitives
# --------------------------------------------------------------------------

_CMD = re.compile(r"\\([A-Za-z@]+)")


def _skip_ws(tex: str, i: int) -> int:
    while i < len(tex) and tex[i] in " \t\n\r":
        i += 1
    return i


def _read_delimited(tex: str, i: int, open_ch: str, close_ch: str):
    """Read a balanced `{..}` / `[..]` starting at the delimiter.

    Returns (body, index_after_close) or (None, i) when `tex[i]` is not the
    opening delimiter.
    """
    if i >= len(tex) or tex[i] != open_ch:
        return None, i
    depth, j = 1, i + 1
    while j < len(tex):
        c = tex[j]
        if c == "\\":
            j += 2
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return tex[i + 1:j], j + 1
        j += 1
    return None, i


def _read_group(tex: str, i: int):
    return _read_delimited(tex, i, "{", "}")


def _read_bracket(tex: str, i: int):
    return _read_delimited(tex, i, "[", "]")


# --------------------------------------------------------------------------
# harvesting
# --------------------------------------------------------------------------

_DEF_START = re.compile(
    r"\\(?:new|renew|provide)command\s*\*?\s*"
    r"(?:\{\s*\\([A-Za-z@]+)\s*\}|\\([A-Za-z@]+))\s*")


def harvest_macros(tex: str) -> MacroTable:
    """Collect every `\\newcommand`/`\\renewcommand`/`\\providecommand`.

    Later definitions win, matching LaTeX's own last-one-loaded behaviour.
    """
    table = MacroTable()
    for m in _DEF_START.finditer(tex):
        name = m.group(1) or m.group(2)
        i = m.end()
        nargs, default = 0, None
        spec, j = _read_bracket(tex, i)
        if spec is not None and spec.strip().isdigit():
            nargs = int(spec.strip())
            i = j
            dflt, j2 = _read_bracket(tex, i)
            if dflt is not None:
                default = dflt
                i = j2
        body, j3 = _read_group(tex, i)
        if body is None:
            continue
        table.defs[name] = MacroDef(name, nargs, body, default)
    return table


_FILECONTENTS = re.compile(
    r"\\begin\{filecontents\*?\}(?:\[[^\]]*\])?\{([^}]*)\}\n(.*?)\n?"
    r"\\end\{filecontents\*?\}", re.S)


def harvest_arrays(tex: str) -> Dict[str, List[str]]:
    """{filename: [entry, ...]} from every `filecontents`/`filecontents*` block.

    readarray indexes are 1-based, so entry `n` is `entries[n - 1]`.
    """
    return {m.group(1): m.group(2).split("\n") for m in _FILECONTENTS.finditer(tex)}


#: `\readarray{\data}{\NAME}` and `\readdef{file}{\NAME}` were already handled by
#: the old transclusion path. `\readrecordarray{file}\NAME` is the form gummi.tex
#: actually uses and the one that was silently missed.
_READARRAY = re.compile(
    r"\\readarray\s*\{\s*\\?([A-Za-z@.]+)\s*\}\s*\{\s*\\([A-Za-z@]+)\s*\}")
_READDEF = re.compile(r"\\readdef\s*\{([^}]*)\}\s*\{\s*\\([A-Za-z@]+)\s*\}")
_READRECORD = re.compile(
    r"\\read(?:record)?array\s*\{([^}]*)\}\s*\\([A-Za-z@]+)")


def find_array_macro(tex: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (array_macro_name, data_file) declared by the document."""
    m = _READRECORD.search(tex)
    if m:
        return m.group(2), m.group(1)
    m = _READARRAY.search(tex)
    if m:
        return m.group(2), m.group(1)
    m = _READDEF.search(tex)
    if m:
        return m.group(2), m.group(1)
    return None, None


def resolve_array(tex: str,
                  external: Optional[Sequence[str]] = None) -> ArrayRef:
    """Work out the document's formula array from its own declarations."""
    macro, data_file = find_array_macro(tex)
    if external is not None:
        return ArrayRef(macro, data_file, tuple(external))
    arrays = harvest_arrays(tex)
    entries: Sequence[str] = ()
    if data_file and data_file in arrays:
        entries = arrays[data_file]
    elif len(arrays) == 1:
        entries = next(iter(arrays.values()))
    return ArrayRef(macro, data_file, tuple(entries))


# --------------------------------------------------------------------------
# expansion
# --------------------------------------------------------------------------

class ExpansionError(RuntimeError):
    """A macro could not be expanded (bad arity, array index out of range)."""


def _substitute(body: str, args: Sequence[str]) -> str:
    """Replace #1..#9 in a macro body. `##` is a literal `#`."""
    out, i = [], 0
    while i < len(body):
        c = body[i]
        if c != "#":
            out.append(c)
            i += 1
            continue
        if i + 1 < len(body) and body[i + 1] == "#":
            out.append("#")
            i += 2
            continue
        if i + 1 < len(body) and body[i + 1].isdigit():
            n = int(body[i + 1])
            out.append(args[n - 1] if 1 <= n <= len(args) else "")
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


_TRAILING_CMD = re.compile(r"\\[A-Za-z@]+$")


def _emit(out: List[str], text: str) -> None:
    """Append `text`, keeping a preceding control word from swallowing it.

    `\\alpha\\A` with `\\A -> x` must not become `\\alphax`, which is a different
    (undefined) macro. TeX ends a control word at the first non-letter, so a
    separating space is required and is itself absorbed by the same rule.
    """
    if text and text[0].isalpha() and out and _TRAILING_CMD.search(out[-1]):
        out.append(" ")
    out.append(text)


def _expand_once(tex: str, table: MacroTable, array: ArrayRef,
                 warnings: Optional[List[str]]) -> Tuple[str, bool]:
    out: List[str] = []
    i, n, changed = 0, len(tex), False
    while i < n:
        c = tex[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        m = _CMD.match(tex, i)
        if not m:                       # escaped literal: \{ \} \\ \_ \$
            out.append(tex[i:i + 2])
            i += 2
            continue

        # A \newcommand is a definition, not a use: its body is a template
        # containing #1 and the array macro, and expanding in place would both
        # destroy the definition and emit spurious out-of-range warnings.
        md = _DEF_START.match(tex, i)
        if md:
            k = md.end()
            spec, after_spec = _read_bracket(tex, k)
            if spec is not None and spec.strip().isdigit():
                k = after_spec
                dflt, after_dflt = _read_bracket(tex, k)
                if dflt is not None:
                    k = after_dflt
            body, after_body = _read_group(tex, k)
            if body is not None:
                out.append(tex[i:after_body])
                i = after_body
                continue

        name, j = m.group(1), m.end()

        if array.macro and name == array.macro:
            k = _skip_ws(tex, j)
            idx, k2 = _read_bracket(tex, k)
            if idx is None:
                out.append(m.group(0))
                i = j
                continue
            try:
                pos = int(idx.strip())
                if pos < 1:
                    raise IndexError(pos)
                entry = array.entries[pos - 1]
            except (ValueError, IndexError):
                if warnings is not None:
                    warnings.append(
                        f"formula array index {idx.strip()!r} out of range "
                        f"(1..{len(array.entries)})")
                out.append(m.group(0))
                i = j
                continue
            _emit(out, entry)
            i, changed = k2, True
            continue

        d = table.get(name)
        if d is None:
            out.append(m.group(0))
            i = j
            continue

        args: List[str] = []
        k = j
        want = d.nargs
        if d.default is not None and want:
            k_opt = _skip_ws(tex, k)
            opt, k2 = _read_bracket(tex, k_opt)
            args.append(d.default if opt is None else opt)
            if opt is not None:
                k = k2
            want -= 1
        ok = True
        for _ in range(want):
            k_arg = _skip_ws(tex, k)
            grp, k2 = _read_group(tex, k_arg)
            if grp is None:
                # a single undelimited token is a legal LaTeX argument
                if k_arg < n and tex[k_arg] != "\\":
                    args.append(tex[k_arg])
                    k = k_arg + 1
                    continue
                ok = False
                break
            args.append(grp)
            k = k2
        if not ok:
            if warnings is not None:
                warnings.append(f"\\{name} used with too few arguments")
            out.append(m.group(0))
            i = j
            continue
        _emit(out, _substitute(d.body, args))
        i, changed = k, True
    return "".join(out), changed


_ENSUREMATH = re.compile(r"\\ensuremath\s*\{")
_ENV_BEGIN = re.compile(r"\\begin\{([A-Za-z@*]+)\}")
_ENV_END = re.compile(r"\\end\{([A-Za-z@*]+)\}")


def _fix_ensuremath(tex: str) -> str:
    """`\\ensuremath{X}` -> `$X$` in prose, -> `X` already inside math.

    An expanded `\\Expr{1}` lands in a text run and has to become a real math
    run for the segmenter to find it; the same macro used inside an `equation`
    body must *not* gain a `$`, which is exactly the leak the old inline/raw
    transclusion classification produced ("dollar R sub 12 dollar").
    """
    math_envs = _math_envs()
    out: List[str] = []
    i, n, depth = 0, len(tex), 0
    dollar = False
    env_stack: List[str] = []
    while i < n:
        c = tex[i]
        if c == "\\":
            m = _ENSUREMATH.match(tex, i)
            if m:
                body, j = _read_group(tex, m.end() - 1)
                if body is not None:
                    in_math = depth > 0 or dollar
                    out.append(body if in_math else "$" + body + "$")
                    i = j
                    continue
            mb = _ENV_BEGIN.match(tex, i)
            if mb:
                env_stack.append(mb.group(1))
                if mb.group(1).rstrip("*") in math_envs:
                    depth += 1
                out.append(mb.group(0))
                i = mb.end()
                continue
            me = _ENV_END.match(tex, i)
            if me:
                if env_stack:
                    env_stack.pop()
                if me.group(1).rstrip("*") in math_envs and depth:
                    depth -= 1
                out.append(me.group(0))
                i = me.end()
                continue
            if tex.startswith(r"\[", i) or tex.startswith(r"\(", i):
                depth += 1
                out.append(tex[i:i + 2])
                i += 2
                continue
            if tex.startswith(r"\]", i) or tex.startswith(r"\)", i):
                depth = max(0, depth - 1)
                out.append(tex[i:i + 2])
                i += 2
                continue
            out.append(tex[i:i + 2])
            i += 2
            continue
        if c == "$":
            run = 2 if tex.startswith("$$", i) else 1
            dollar = not dollar
            out.append(tex[i:i + run])
            i += run
            continue
        out.append(c)
        i += 1
    return "".join(out)


def expand(tex: str,
           table: Optional[MacroTable] = None,
           array: Optional[ArrayRef] = None,
           max_depth: int = DEFAULT_MAX_DEPTH,
           warnings: Optional[List[str]] = None,
           fix_ensuremath: bool = True) -> str:
    """Substitute user macros and formula-array references away.

    Unknown macros pass through untouched -- `\\alpha` has to survive to
    `latex2mathml`, which knows it. Expansion repeats until it reaches a fixed
    point or `max_depth`, so a self-referential definition terminates instead of
    hanging.
    """
    table = table if table is not None else MacroTable()
    array = array if array is not None else ArrayRef()
    if not table.defs and not array.macro:
        return _fix_ensuremath(tex) if fix_ensuremath else tex
    for _ in range(max_depth):
        tex, changed = _expand_once(tex, table, array, warnings)
        if not changed:
            break
    else:
        if warnings is not None:
            warnings.append(
                f"macro expansion hit the depth cap ({max_depth}); "
                "a definition is probably self-referential")
    return _fix_ensuremath(tex) if fix_ensuremath else tex


# --------------------------------------------------------------------------
# identifier protection
# --------------------------------------------------------------------------

#: macro arguments that are already typeset as words -- descending into them
#: would produce `\text{\text{already}}`.
_TEXTUAL_MACROS = frozenset({
    "text", "textrm", "textit", "textbf", "textsf", "texttt", "textnormal",
    "mathrm", "mathit", "mathbf", "mathsf", "mathtt", "mathnormal",
    "operatorname", "operatornamewithlimits", "mbox", "hbox", "label", "ref",
    "eqref", "cite", "begin", "end",
})

_UPPER_RUN = re.compile(r"(?<![A-Za-z])[A-Z]{2,}(?![A-Za-z])")
_LOWER_FUNC = re.compile(r"(?<![A-Za-z])[a-z]{3,}(?![A-Za-z])(?=\s*\()")


def _chars_spans(nodes: Iterable, out: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    for nd in nodes or ():
        if nd is None:
            continue
        cls = type(nd).__name__
        if cls == "LatexCharsNode":
            out.append((nd.pos, nd.pos + nd.len))
        elif cls in ("LatexGroupNode", "LatexEnvironmentNode", "LatexMathNode"):
            _chars_spans(getattr(nd, "nodelist", None), out)
        elif cls == "LatexMacroNode":
            if nd.macroname in _TEXTUAL_MACROS:
                continue
            argd = getattr(nd, "nodeargd", None)
            if argd is not None and getattr(argd, "argnlist", None):
                _chars_spans(argd.argnlist, out)
    return out


def _plain_spans(tex: str) -> List[Tuple[int, int]]:
    """Character spans that are ordinary text, not macro names or word-macro args."""
    try:
        from pylatexenc.latexwalker import LatexWalker
        nodes, _, _ = LatexWalker(tex, tolerant_parsing=True).get_latex_nodes()
    except Exception:
        return [(0, len(tex))]
    return _chars_spans(nodes, [])


def protect_identifiers(tex: str, exclude: Iterable[str] = ()) -> str:
    """Wrap multi-letter identifiers in `\\text{}` so they are read as words.

    SRE reads one `<mi>` at a time, so `AVERAGE` becomes "A V E R A G E" --
    correct for a listener, useless for an embedder. Two rules, applied to
    ordinary character runs only:

      * ASCII uppercase, length >= 2          -> AVERAGE, IDF, TF
      * ASCII lowercase, length >= 3 before ( -> siblings(c,p), count(x)

    Everything else is left alone, so `xy` stays a product, `dx` stays a
    differential, and `\\alpha` never matches because a macro name is not a
    character run.

    Known limitation: `AB` as a geometry segment matches the uppercase rule.
    Pass it in `exclude`.
    """
    skip = {s for s in exclude}
    spans = _plain_spans(tex)
    if not spans:
        return tex

    def inside(a: int, b: int) -> bool:
        return any(s <= a and b <= e for s, e in spans)

    hits: List[Tuple[int, int, str]] = []
    for rx in (_UPPER_RUN, _LOWER_FUNC):
        for m in rx.finditer(tex):
            if m.group(0) in skip or not inside(m.start(), m.end()):
                continue
            hits.append((m.start(), m.end(), m.group(0)))
    if not hits:
        return tex
    hits.sort()
    out, prev = [], 0
    for start, end, name in hits:
        if start < prev:                       # overlapping rules; first wins
            continue
        out.append(tex[prev:start])
        out.append("\\text{" + name + "}")
        prev = end
    out.append(tex[prev:])
    return "".join(out)


# --------------------------------------------------------------------------
# the projection
# --------------------------------------------------------------------------

def project(tex: str,
            table: Optional[MacroTable] = None,
            array: Optional[ArrayRef] = None,
            protect: bool = True,
            exclude: Iterable[str] = (),
            max_depth: int = DEFAULT_MAX_DEPTH,
            warnings: Optional[List[str]] = None,
            fix_ensuremath: bool = True) -> str:
    """Full projection: expanded LaTeX with identifiers protected."""
    tex = expand(tex, table, array, max_depth=max_depth, warnings=warnings,
                 fix_ensuremath=fix_ensuremath)
    if protect:
        tex = protect_identifiers(tex, exclude)
    return tex
