"""
LaTeX source ingest — the author's .tex as a competing provenance.

For arXiv papers we usually have BOTH the PDF (→ MathPix lines.json) and the
author's LaTeX source (the e-print .tgz). The .tex is the *gold* form of each
equation, so we lift it in and attach it to each MathPix `Equation` as a
`provenance="tex"` reading (alongside snip/llm) — it becomes another column in
`compare` and a reference for scoring.

Two LaTeX forms are kept per element, exactly as the LATW pipeline does:
  - **original**  — verbatim author LaTeX (may use \\-macros from the preamble),
  - **expanded**  — preamble macros inlined by bounded fixpoint, so the snippet
                    is self-contained (this is what a later latex→dvi→dvisvgm
                    step would compile; TikZ/tables can't render in KaTeX).

This module is pure / network-free / no LaTeX tools — only string processing,
so it is fully unit-testable here. The SVG (dvisvgm) projector is a separate,
later step.
"""
from __future__ import annotations

import os
import re
import tarfile
import tempfile
import zipfile

# Display-math environments whose body we lift as one equation each.
_DISPLAY_ENVS = (
    "equation", "align", "gather", "multline", "eqnarray", "displaymath",
    "alignat", "flalign", "math",
)


# ---------------------------------------------------------------------------
# Source acquisition (.tex file, or arXiv .tgz/.tar.gz of many files)
# ---------------------------------------------------------------------------

def strip_comments(tex: str) -> str:
    """Remove LaTeX line comments (% to EOL) but keep escaped \\%."""
    return re.sub(r"(?<!\\)%.*", "", tex)


def _balanced(text: str, open_idx: int) -> str:
    """Return the substring inclusive of the braces starting at text[open_idx]=='{'."""
    depth, out = 0, []
    for i in range(open_idx, len(text)):
        c = text[i]
        out.append(c)
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                break
    return "".join(out)


def expand_inputs(main_path: str, base_dir: str, _depth: int = 0,
                  _seen: set | None = None, max_depth: int = 12) -> str:
    """Inline \\input/\\include recursively; strip comments. Returns full text."""
    _seen = _seen if _seen is not None else set()
    rp = os.path.realpath(main_path)
    if _depth > max_depth or rp in _seen or not os.path.exists(main_path):
        return ""
    _seen.add(rp)
    text = strip_comments(open(main_path, encoding="utf-8", errors="replace").read())

    def repl(m: re.Match) -> str:
        name = m.group(1).strip()
        for cand in (name, name + ".tex"):
            p = os.path.join(base_dir, cand)
            if os.path.exists(p):
                return expand_inputs(p, base_dir, _depth + 1, _seen, max_depth)
        return ""  # missing include → drop

    return re.sub(r"\\(?:input|include)\s*\{([^}]+)\}", repl, text)


def find_main_tex(paths: dict[str, str]) -> str | None:
    """Pick the main .tex (the one with \\documentclass, else \\begin{document})."""
    cls = [n for n, t in paths.items() if "\\documentclass" in t]
    if cls:
        return max(cls, key=lambda n: len(paths[n]))
    doc = [n for n, t in paths.items() if "\\begin{document}" in t]
    if doc:
        return max(doc, key=lambda n: len(paths[n]))
    texs = [n for n in paths if n.endswith(".tex")]
    return max(texs, key=lambda n: len(paths[n])) if texs else None


def read_source(path: str) -> tuple[str, str]:
    """Load LaTeX source from a .tex file or an arXiv .tgz/.tar.gz.

    Returns (full_text_with_inputs_inlined, main_filename). For a tarball the
    members are extracted to a temp dir so \\input resolves.
    """
    if path.endswith((".tex",)):
        base = os.path.dirname(os.path.abspath(path))
        return expand_inputs(path, base), os.path.basename(path)

    if tarfile.is_tarfile(path):
        from . import config as _cfg
        with tempfile.TemporaryDirectory(dir=str(_cfg.scratch_dir())) as d:
            with tarfile.open(path) as tf:
                tf.extractall(d, filter="data")
            contents: dict[str, str] = {}
            for root, _dirs, files in os.walk(d):
                for f in files:
                    if f.endswith(".tex"):
                        fp = os.path.join(root, f)
                        rel = os.path.relpath(fp, d)
                        contents[rel] = open(fp, encoding="utf-8", errors="replace").read()
            main = find_main_tex(contents)
            if not main:
                return "", ""
            return expand_inputs(os.path.join(d, main), os.path.dirname(os.path.join(d, main))), main

    # A ZIP — notably MathPix's `<name>.tex.zip` (clean LaTeX, minimal preamble,
    # CDN-derived JPGs). Same shape as the tarball branch: extract, find main .tex.
    if zipfile.is_zipfile(path):
        from . import config as _cfg
        with tempfile.TemporaryDirectory(dir=str(_cfg.scratch_dir())) as d:
            with zipfile.ZipFile(path) as zf:
                zf.extractall(d)
            contents = {}
            for root, _dirs, files in os.walk(d):
                for f in files:
                    if f.endswith(".tex"):
                        fp = os.path.join(root, f)
                        contents[os.path.relpath(fp, d)] = open(
                            fp, encoding="utf-8", errors="replace").read()
            main = find_main_tex(contents)
            if not main:
                return "", ""
            return expand_inputs(os.path.join(d, main),
                                 os.path.dirname(os.path.join(d, main))), main
    # plain text fallback
    return strip_comments(open(path, encoding="utf-8", errors="replace").read()), os.path.basename(path)


# ---------------------------------------------------------------------------
# Preamble + macros
# ---------------------------------------------------------------------------

def split_preamble(tex: str) -> tuple[str, str]:
    """Return (preamble, body) split on \\begin{document}…\\end{document}."""
    m = re.search(r"\\begin\{document\}", tex)
    if not m:
        return "", tex
    preamble = tex[:m.start()]
    end = re.search(r"\\end\{document\}", tex)
    body = tex[m.end():end.start()] if end else tex[m.end():]
    return preamble, body


def extract_macros(preamble: str) -> dict[str, dict]:
    """Parse macro definitions into {name: {nargs, default, body}}.

    Handles \\newcommand / \\renewcommand (with optional [n][default]),
    \\def\\name{...}, and \\DeclareMathOperator (→ \\operatorname{...})."""
    macros: dict[str, dict] = {}

    # \newcommand{\name}[n][default]{body}  (also the *-form)
    nc = re.compile(r"\\(?:re)?newcommand\*?\s*\{?\\([A-Za-z]+)\}?(?:\[(\d+)\])?(?:\[([^\]]*)\])?\s*\{")
    for m in nc.finditer(preamble):
        name = m.group(1)
        nargs = int(m.group(2)) if m.group(2) else 0
        default = m.group(3)
        body = _balanced(preamble, m.end() - 1)[1:-1]
        macros[name] = {"nargs": nargs, "default": default, "body": body}

    # \DeclareMathOperator{\name}{text}  → zero-arg \operatorname{text}
    for m in re.finditer(r"\\DeclareMathOperator\*?\s*\{?\\([A-Za-z]+)\}?\s*\{", preamble):
        body = _balanced(preamble, m.end() - 1)[1:-1]
        macros[m.group(1)] = {"nargs": 0, "default": None, "body": f"\\operatorname{{{body}}}"}

    # \def\name{body}
    for m in re.finditer(r"\\def\s*\\([A-Za-z]+)\s*\{", preamble):
        body = _balanced(preamble, m.end() - 1)[1:-1]
        macros.setdefault(m.group(1), {"nargs": 0, "default": None, "body": body})

    return macros


def _resolve_style_file(name: str, base_dir: str) -> Optional[str]:
    """Find a local package/input source file by name, searching common dirs.

    `\\usepackage{mystyle}` → mystyle.sty; `\\input{tex/foo}` → tex/foo.tex.
    Returns the file's text, or None if it's a system package (not local)."""
    name = name.strip()
    cands = []
    for ext in ("", ".sty", ".tex"):
        cands.append(os.path.join(base_dir, name + ext))
        for sub in ("style", "styles", "tex", "include", "preamble"):
            cands.append(os.path.join(base_dir, sub, name + ext))
    for p in cands:
        if os.path.isfile(p):
            try:
                return strip_comments(open(p, encoding="utf-8", errors="replace").read())
            except Exception:
                return None
    return None


def collect_macros(preamble: str, base_dir: str, _depth: int = 0,
                   _seen: Optional[set] = None) -> dict[str, dict]:
    """Macros from the preamble PLUS any local \\usepackage/\\input files it
    pulls in (e.g. a project `mystyle.sty`). System packages (amsmath, …) that
    aren't present as local files are simply skipped. Recurses into nested
    \\usepackage/\\RequirePackage/\\input within those files."""
    _seen = _seen if _seen is not None else set()
    macros: dict[str, dict] = {}
    if _depth > 8:
        return macros

    # 1) the local files this text references (parse their macros first, so
    #    preamble redefinitions can override).
    refs = re.findall(
        r"\\(?:usepackage|RequirePackage)(?:\[[^\]]*\])?\{([^}]+)\}|\\input\{([^}]+)\}",
        preamble)
    for grp in refs:
        for nm in (grp[0] or grp[1] or "").split(","):
            nm = nm.strip()
            key = (base_dir, nm)
            if not nm or key in _seen:
                continue
            _seen.add(key)
            text = _resolve_style_file(nm, base_dir)
            if text:
                macros.update(collect_macros(text, base_dir, _depth + 1, _seen))

    # 2) this text's own definitions (win over included ones).
    macros.update(extract_macros(preamble))
    return macros


def _apply_once(text: str, name: str, mac: dict) -> tuple[str, bool]:
    """Expand all calls of one macro once. Returns (text, changed)."""
    nargs = mac["nargs"]
    body = mac["body"]
    pat = re.compile(r"\\" + re.escape(name) + r"(?![A-Za-z])")
    out, changed, i = [], False, 0
    for m in pat.finditer(text):
        if m.start() < i:
            continue
        out.append(text[i:m.start()])
        j = m.end()
        args: list[str] = []
        # optional [default] arg
        opt = mac.get("default")
        if opt is not None:
            mo = re.match(r"\s*\[([^\]]*)\]", text[j:])
            if mo:
                args.append(mo.group(1)); j += mo.end()
            else:
                args.append(opt)
        need = nargs - len(args)
        ok = True
        for _ in range(need):
            mb = re.match(r"\s*\{", text[j:])
            if not mb:
                ok = False
                break
            grp = _balanced(text, j + mb.start())
            args.append(grp[1:-1]); j = (j + mb.start()) + len(grp)
        if not ok:
            out.append(text[m.start():m.end()]); i = m.end(); continue
        expanded = body
        for k, a in enumerate(args, 1):
            expanded = expanded.replace(f"#{k}", a)
        out.append(expanded); i = j; changed = True
    out.append(text[i:])
    return "".join(out), changed


def expand_macros(fragment: str, macros: dict[str, dict], max_iter: int = 8) -> str:
    """Inline preamble macros into a fragment by bounded fixpoint."""
    text = fragment
    for _ in range(max_iter):
        changed = False
        for name, mac in macros.items():
            text, ch = _apply_once(text, name, mac)
            changed = changed or ch
        if not changed:
            break
    return text


# Packages that fight `standalone`'s content-cropping (fixed page geometry, page
# furniture) or are document-class STYLES that set up a full page — a cropped
# diagram snippet doesn't need them and they cause "Dimension too large" at
# shipout. Anything matching is dropped from the standalone preamble.
_STANDALONE_DROP_PKGS = (
    "geometry", "hyperref", "fancyhdr", "lastpage", "titlesec", "titling",
    "siamproceedings", "siamart", "siamonline", "IEEEtran", "acmart", "revtex4",
)

# Conference/journal PAGE-STYLE packages (named per venue+year, e.g.
# neurips_2022, icml2023, iclr2024_conference) set full-page geometry that
# breaks `standalone` cropping with "Dimension too large". Drop them — but NOT
# style packages that define macros/colors/pgfplots cycle-lists a snippet needs
# (e.g. a local `palettes.sty`), which is why this matches only known venue
# names, never an arbitrary local style.
_CONFERENCE_STYLE_RE = re.compile(
    r"^(?:neurips|nips|icml|iclr|colm|tmlr|jmlr|cvpr|iccv|eccv|wacv|bmvc|aaai|"
    r"ijcai|aamas|acl|emnlp|naacl|eacl|coling|tacl|colt|aistats|uai|kdd|sigir|"
    r"www|chi|interspeech|icassp|siggraph|neurips_data)"
    r"[-_]?\d{0,4}(?:_conference|_data|_submission)?$"
    r"|^[a-z][a-z0-9]*[-_](?:conference|proceedings|submission)$", re.I)


def _drop_from_standalone(name: str) -> bool:
    return name in _STANDALONE_DROP_PKGS or bool(_CONFERENCE_STYLE_RE.match(name))

_DEF_START = re.compile(r"\\(?:re|provide)?newcommand\*?|\\DeclareMathOperator\*?")


def _collect_macro_defs(preamble: str) -> list[str]:
    """Full `\\newcommand`/`\\renewcommand`/`\\providecommand`/`\\DeclareMathOperator`
    and `\\def` definitions, with their (possibly multi-line, brace-balanced)
    bodies intact — unlike a line-anchored regex, which truncated multi-line
    bodies and left a runaway definition (the arXiv 2510.15795 `\\tailxrightarrow`
    failure)."""
    n = len(preamble)
    out: list[str] = []

    def skip_ws(i: int) -> int:
        while i < n and preamble[i] in " \t\r\n":
            i += 1
        return i

    for m in _DEF_START.finditer(preamble):
        i = skip_ws(m.end())
        # macro name: `{\foo}` or `\foo`
        if i < n and preamble[i] == "{":
            i += len(_balanced(preamble, i))
        elif i < n and preamble[i] == "\\":
            i += 1
            while i < n and (preamble[i].isalpha() or preamble[i] == "@"):
                i += 1
        # optional [..] arg-count / default groups
        while True:
            i = skip_ws(i)
            if i < n and preamble[i] == "[":
                depth = 0
                while i < n:
                    if preamble[i] == "[":
                        depth += 1
                    elif preamble[i] == "]":
                        depth -= 1
                        if depth == 0:
                            i += 1
                            break
                    i += 1
            else:
                break
        # the body {..}
        i = skip_ws(i)
        if i < n and preamble[i] == "{":
            i += len(_balanced(preamble, i))
        out.append(preamble[m.start():i])

    for m in re.finditer(r"\\def\\[A-Za-z@]+", preamble):
        i = m.end()
        while i < n and preamble[i] != "{":      # skip delimiter/param text (#1…)
            i += 1
        if i < n and preamble[i] == "{":
            out.append(preamble[m.start():i + len(_balanced(preamble, i))])
    return out


_NC_NAME = re.compile(r"^(\s*)\\(?:re)?newcommand\*?\s*\{?\\([A-Za-z@]+)\}?")


def _robustify_macro_defs(defs: list[str]) -> list[str]:
    """Make every collected \\newcommand/\\renewcommand definition compile in a
    STANDALONE snippet regardless of what the dropped packages defined.

    A thesis that `\\renewcommand{\\C}{...}` a macro defined only by a package
    we drop fails with "Command \\C undefined"; a `\\newcommand{\\x}{...}` of a
    name a KEPT package already defines fails the other way. Both are cured by:
    pre-declare the name with `\\providecommand{\\name}{}` (no-op if it exists),
    then emit the body as `\\renewcommand` (always succeeds once it exists).
    `\\def`/`\\DeclareMathOperator`/`\\providecommand` defs pass through."""
    out: list[str] = []
    for d in defs:
        m = _NC_NAME.match(d)
        if not m:
            out.append(d)
            continue
        name = m.group(2)
        body = re.sub(r"^\s*\\(?:re)?newcommand", r"\\renewcommand", d, count=1).lstrip()
        out.append(f"\\providecommand{{\\{name}}}{{}}{body}")
    return out


def standalone_preamble(preamble: str) -> str:
    """A minimal `standalone` math preamble for the latex→dvi→dvisvgm step: the
    author's math/TikZ packages + their macro definitions — but NOT the document
    class style or page-layout packages, which break standalone cropping.

    Keeps every `\\usepackage` except `_STANDALONE_DROP_PKGS`, plus the FULL macro
    definitions (multi-line bodies preserved via `_collect_macro_defs`). Drops
    everything else in the preamble (theorem setup like `\\newsiamremark`, page
    furniture, title metadata) — none of which a cropped diagram needs."""
    pre = strip_comments(preamble)
    pkgs: list[str] = []
    for m in re.finditer(r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", pre):
        names = [x.strip() for x in m.group(1).split(",")]
        if any(_drop_from_standalone(name) for name in names):
            continue
        pkgs.append(m.group(0))
    # TikZ libraries the diagrams/styles depend on (e.g. decorations.markings,
    # which a \tikzset `decorate` style needs).
    libs = re.findall(r"\\usetikzlibrary\s*\{[^}]*\}", pre)
    defs = _robustify_macro_defs(_collect_macro_defs(pre))
    # Math-alphabet declarations (single-line, self-contained, no \makeatletter
    # needed) that define math letters a diagram may use, e.g.
    # \DeclareMathAlphabet{\mathbbe}{U}{bbold}{m}{n}. (Deliberately NOT \let or
    # font-family/symbol declarations — those often reference \makeatletter `@`
    # internals or span lines, and break a bare standalone preamble.)
    decls = re.findall(
        r"\\(?:DeclareMathAlphabet|SetMathAlphabet)\b[^\n]*", pre)
    # Low-level \font primitives (e.g. \font\maljapanese=dmjhira at 2ex, used to
    # build the Yoneda symbol \yo) — a \def that references the named font fails
    # without the \font load.
    fonts = re.findall(r"\\font\\[A-Za-z@]+\s*=[^\n]*", pre)
    # Custom colors (\definecolor) the diagrams reference (e.g. layerstructural,
    # stagebox) — without them tikz/xcolor errors "Undefined color ...".
    colors = re.findall(r"\\definecolor\b[^\n]*", pre)
    # \tikzset{...}/\tikzcdset{...} blocks define custom arrow/node styles the
    # diagrams use (e.g. utcofarrow); capture the whole brace-balanced block.
    tikzsets: list[str] = []
    for m in re.finditer(r"\\tikz(?:cd)?set\s*\{", pre):
        open_idx = m.end() - 1
        tikzsets.append(pre[m.start():open_idx] + _balanced(pre, open_idx))
    # \pgfplotsset{...} blocks (compat level + custom plot/cycle styles) a
    # pgfplots `axis` diagram needs.
    pgfsets: list[str] = []
    for m in re.finditer(r"\\pgfplotsset\s*\{", pre):
        open_idx = m.end() - 1
        pgfsets.append(pre[m.start():open_idx] + _balanced(pre, open_idx))
    # `class=report` so book/report counters (\thechapter, …) that a project's
    # styles reference exist under standalone; tikz so bare \begin{tikzpicture}
    # compiles even if the project loads it indirectly. (Mirrors LATW.)
    head = "\\documentclass[border=2pt,class=report]{standalone}\n\\usepackage{tikz}"
    return "\n".join([head, *pkgs, *libs, *fonts, *decls, *colors, *defs,
                      *tikzsets, *pgfsets])


# ---------------------------------------------------------------------------
# Display-equation extraction
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def extract_display_equations(body: str) -> list[dict]:
    """Return display equations in document order.

    Each: {env, latex (original body), numbered (bool), label}. Covers
    \\begin{equation|align|…}, \\[ … \\], and $$ … $$. Starred envs are
    unnumbered. `\\label{…}` (if any) is captured; `\\nonumber`/`\\notag` flip
    numbered off.
    """
    items: list[dict] = []
    env_alt = "|".join(_DISPLAY_ENVS)
    env_re = re.compile(r"\\begin\{(" + env_alt + r")(\*?)\}(.*?)\\end\{\1\2\}", re.S)
    for m in env_re.finditer(body):
        env, star, inner = m.group(1), m.group(2), m.group(3)
        label = (re.search(r"\\label\{([^}]*)\}", inner) or [None, None])[1]
        numbered = (star != "*") and ("\\nonumber" not in inner) and ("\\notag" not in inner)
        items.append({"env": env, "latex": _clean_eq(inner, env), "numbered": numbered,
                      "label": label, "pos": m.start()})
    # \[ ... \] — but NOT \\[4pt] (a row-spacing break inside align/array),
    # so require the brackets not be preceded by a backslash (negative
    # lookbehind), and reject a body that itself starts like a length unit.
    for m in re.finditer(r"(?<!\\)\\\[(.*?)(?<!\\)\\\]", body, re.S):
        inner = m.group(1)
        if re.match(r"^\s*-?\d*\.?\d+\s*(pt|mm|cm|ex|em|in|bp|pc|sp)\s*\]", inner):
            continue  # e.g. "4pt] ..." — a mis-split row break, not display math
        items.append({"env": "displaymath", "latex": _clean_eq(inner),
                      "numbered": False, "label": None, "pos": m.start()})
    for m in re.finditer(r"(?<!\\)\$\$(.+?)\$\$", body, re.S):
        items.append({"env": "displaymath", "latex": _clean_eq(m.group(1)),
                      "numbered": False, "label": None, "pos": m.start()})
    items.sort(key=lambda it: it["pos"])
    return items   # keep `pos` so build_source_model can interleave prose by position


# Multi-line math envs whose body uses & / \\ and so needs an `aligned`
# wrapper to render standalone in KaTeX.
_ALIGNED_ENVS = {"align", "gather", "multline", "eqnarray", "alignat", "flalign"}


def _clean_eq(inner: str, env: str = "") -> str:
    """Normalize a display-math body for KaTeX rendering.

    Strips non-math LaTeX (\\label, \\index{…}, \\nonumber), maps old-style
    font switches (\\rm→\\mathrm etc.), and — for align/gather/… bodies, which
    carry bare `&`/`\\` — wraps them in `\\begin{aligned}…\\end{aligned}` so
    KaTeX can render them (bare `&` is otherwise a KaTeX error).
    """
    s = re.sub(r"\\label\{[^}]*\}", "", inner)
    s = re.sub(r"\\index\{(?:[^{}]|\{[^{}]*\})*\}", "", s)  # \index{...}, 1 nest deep
    s = re.sub(r"\\(?:nonumber|notag)\b", "", s)
    s = _norm(s)
    # Strip a dangling trailing line-continuation `\` (e.g. a source line that
    # ended "= 0,\ \ \ \" right before \]) — a lone trailing backslash is a
    # KaTeX error. Remove a run of trailing escaped-spaces / lone backslash,
    # but NOT a real `\\` row break (which align/cases need).
    s = re.sub(r"(?:\\\s|\s)*\\$", "", s).rstrip()
    # Naked super/subscript: a `^`/`_` with no base (LaTeX tolerates the
    # left-transpose idiom "\, ^tD"; KaTeX errors "Expected group after ^").
    # Insert an empty base `{}` when the script follows a spacing macro
    # (\,\;\:\! or \quad/\qquad), an opener, or the start — i.e. there is no
    # real base to its left.
    s = re.sub(r"(^|[({\[]\s*|\\[,;:!]\s*|\\q?quad\s*)([_^])", r"\1{}\2", s)
    # align/gather/… bodies carry bare & and \\ — wrap so KaTeX renders them
    # (KaTeX errors on a bare & outside an environment).
    if env in _ALIGNED_ENVS and ("&" in s or "\\\\" in s):
        s = "\\begin{aligned} " + s + " \\end{aligned}"
    return s


_SECTION_RE = re.compile(
    r"\\(part|chapter|subsubsection|subsection|section)\*?\{")

# `\appendix` (or the appendix-package `\begin{appendices}`) switches every
# following \section into the appendix (lettered A, B, … in real LaTeX output).
_APPENDIX_RE = re.compile(r"\\appendix\b|\\begin\{appendices\}")


def find_appendix_pos(body: str) -> int:
    """Source position where the appendix begins, or -1 if there is none."""
    m = _APPENDIX_RE.search(body)
    return m.start() if m else -1

# Environments that need a real LaTeX→SVG render (KaTeX can't do them).
# NOTE: `array` is intentionally excluded — it is a math-mode matrix/cases
# construct (rendered by KaTeX inside its display equation), not a standalone
# table, and cannot compile on its own.
_GRAPHIC_ENVS = ("tikzpicture", "tabular", "tabularx", "longtable", "tikzcd")


def _env_blocks(body: str, env: str) -> list[dict]:
    """All \\begin{env}…\\end{env} blocks (brace-balanced on the env name),
    returning {env, code (full \\begin..\\end), pos}. Handles options after
    \\begin{env}[...] and nested same-name envs are rare here so a non-greedy
    match per outermost block is sufficient for tabular/tikzpicture."""
    out = []
    begin = re.compile(r"\\begin\{" + re.escape(env) + r"\}")
    end_tok = "\\end{" + env + "}"
    for m in begin.finditer(body):
        depth = 1
        i = m.end()
        bre = re.compile(r"\\(begin|end)\{" + re.escape(env) + r"\}")
        for bm in bre.finditer(body, m.end()):
            depth += 1 if bm.group(1) == "begin" else -1
            if depth == 0:
                i = bm.end()
                break
        out.append({"env": env, "code": body[m.start():i], "pos": m.start()})
    return out


def extract_graphics(body: str) -> list[dict]:
    """TikZ pictures and tables in document order: {env, code, pos, caption}.

    `code` is the verbatim environment, ready to drop into a standalone
    preamble for latex→dvisvgm. A nearby \\caption{...} is captured if the
    block sits inside a figure/table float (best-effort)."""
    out: list[dict] = []
    for env in _GRAPHIC_ENVS:
        out.extend(_env_blocks(body, env))
    # attach a caption from the enclosing float, if any
    for it in out:
        window = body[it["pos"]: it["pos"] + len(it["code"]) + 400]
        cap = re.search(r"\\caption\{", window)
        it["caption"] = _balanced(window, cap.start() + len("\\caption"))[1:-1] if cap else ""
        it["kind"] = "Diagram" if it["env"].startswith("tikz") else "Table"
    out.sort(key=lambda t: t["pos"])
    return out


_ABSTRACT_ENV = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.S)
_ABSTRACT_CMD = re.compile(r"\\abstract\s*\{", re.S)


def extract_abstract(body: str) -> "dict | None":
    """The `\\begin{abstract}…\\end{abstract}` (or `\\abstract{…}`) body + its
    source position, or None. First-class so it becomes an Abstract object (→ a
    `## Abstract` heading in markdown and a bibkey Abstract tiddler)."""
    m = _ABSTRACT_ENV.search(body)
    if m:
        return {"text": m.group(1).strip(), "pos": m.start()}
    m = _ABSTRACT_CMD.search(body)
    if m:
        return {"text": _balanced(body, m.end() - 1)[1:-1].strip(), "pos": m.start()}
    return None


def extract_sections(body: str) -> list[dict]:
    """Headings in document order: {level, caption, pos}. Levels 1..4."""
    level = {"part": 1, "chapter": 1, "section": 2, "subsection": 3, "subsubsection": 4}
    appendix_pos = find_appendix_pos(body)
    out = []
    for m in _SECTION_RE.finditer(body):
        kind = m.group(1)
        cap = _balanced(body, m.end() - 1)[1:-1]
        d = {"level": level.get(kind, 2), "caption": _norm(cap),
             "kind": kind, "pos": m.start()}
        if 0 <= appendix_pos <= m.start():
            d["is_appendix"] = True
        out.append(d)
    return out


# --------------------------------------------------------------------------- #
#  Environment census + custom-environment / theorem-like declarations
#  (the LATW EnvironmentWrapperScanner/EnvironmentCleaner analogue, but as a
#  TRACKING layer for higher levels — e.g. a LEAN4 theorem/proof export).
# --------------------------------------------------------------------------- #
_ENV_NAME = r"[A-Za-z@][A-Za-z0-9@*]*"
_BEGIN_ENV_RE = re.compile(r"\\begin\s*\{(" + _ENV_NAME + r")\}")
# \newtheorem{name}{Title}[reset]  OR  \newtheorem{name}[shared]{Title}  (+ *)
_NEWTHEOREM_RE = re.compile(
    r"\\newtheorem(?P<star>\*)?\s*\{(?P<name>[^}]+)\}"
    r"(?:\s*\[(?P<shared>[^\]]+)\])?"
    r"\s*\{(?P<title>[^}]+)\}"
    r"(?:\s*\[(?P<reset>[^\]]+)\])?")
_NEWENV_RE = re.compile(r"\\(?:re)?newenvironment\s*\*?\s*\{(?P<name>[^}]+)\}")
_PROOF_ENVS = ("proof",)


def _local_style_text(base_dir: str) -> str:
    """Concatenated text of the local .sty/.cls bundled in the source dir —
    where `\\newtheorem`/`\\newenvironment` often live (publisher styles,
    algorithmicx, …). e-print tarballs bundle exactly the styles they use."""
    import glob as _glob
    out = []
    for ext in ("sty", "cls"):
        for sub in ("", "style", "styles", "tex", "include", "preamble"):
            for p in sorted(_glob.glob(os.path.join(base_dir, sub, f"*.{ext}"))):
                try:
                    out.append(strip_comments(
                        open(p, encoding="utf-8", errors="replace").read()))
                except OSError:
                    pass
    return "\n".join(out)


def scan_environments(decl_text: str, body: str) -> dict:
    """Track LaTeX environments for higher layers:
      - `used`: census of `\\begin{X}` in the body ({name: count});
      - `newtheorem`: theorem-like envs DECLARED (name/title/shared+reset
        counter/starred) — the theorem/proof structure a LEAN4 export needs;
      - `newenvironment`: custom or redefined environment names;
      - `theorem_like`: the declared theorem-env names;
      - `theorem_blocks`/`proof_blocks`: how many are actually USED.
    `decl_text` is where declarations live (preamble + local .sty/.cls);
    `body` is the document body. Pure."""
    from collections import Counter
    used = Counter(m.group(1) for m in _BEGIN_ENV_RE.finditer(body))
    newtheorem = []
    for m in _NEWTHEOREM_RE.finditer(decl_text):
        newtheorem.append({
            "name": m.group("name").strip(),
            "title": _norm(m.group("title")),
            "shared_counter": (m.group("shared") or "").strip(),
            "reset_counter": (m.group("reset") or "").strip(),
            "starred": bool(m.group("star")),
        })
    # de-dup declarations by name (a style + preamble may both declare; keep first)
    seen: set = set()
    newtheorem = [t for t in newtheorem
                  if not (t["name"] in seen or seen.add(t["name"]))]
    # Skip names carrying a `#` — those are `\newenvironment{#1}` templates inside
    # a macro body (e.g. algorithmicx.sty), not real environment names.
    newenvironment = sorted({m.group("name").strip()
                             for m in _NEWENV_RE.finditer(decl_text)
                             if "#" not in m.group("name")})
    theorem_like = [t["name"] for t in newtheorem]
    thm_set = set(theorem_like)
    return {
        "used": dict(used),
        "newtheorem": newtheorem,
        "newenvironment": newenvironment,
        "theorem_like": theorem_like,
        "theorem_blocks": sum(v for k, v in used.items() if k in thm_set),
        "proof_blocks": sum(used.get(p, 0) for p in _PROOF_ENVS),
    }


def _cap_key(cap: str) -> str:
    """Loose caption key for cross-source matching: lowercase alphanumerics of
    the first few words (tolerates MathPix/OCR drift, dropped \\ref{}, etc.)."""
    cap = re.sub(r"\\[A-Za-z]+\*?(\{[^}]*\})?", " ", cap or "")   # drop \cmd / \ref{}
    return re.sub(r"[^a-z0-9]", "", cap.lower())[:16]


def _cap_match(a: str, b: str) -> bool:
    ka, kb = _cap_key(a), _cap_key(b)
    if not ka or not kb:
        return False
    return ka == kb or ka.startswith(kb) or kb.startswith(ka)


def mark_appendix_from_source(doc, src_dir: str) -> int:
    """Overlay the LaTeX-source `\\appendix` onto a model's Section objects.

    A MathPix/OCR model carries Section objects but no `\\appendix` signal; when
    the arXiv e-print source is on hand (the "if LaTeX is available it must be
    used" rule) this flags every model Section at/after the source `\\appendix`
    as `is_appendix`. Sequential caption alignment (both lists are in document
    order) finds the boundary; once crossed it is TAIL-STICKY (every later
    section is appendix), so a large appendix with MathPix caption drift is
    still fully marked. Idempotent; returns the number flagged."""
    main = None
    paths = {}
    try:
        for root, _dirs, files in os.walk(src_dir):
            for fn in files:
                if fn.endswith(".tex"):
                    p = os.path.join(root, fn)
                    try:
                        paths[p] = open(p, encoding="utf-8", errors="replace").read()
                    except OSError:
                        paths[p] = ""
        main = find_main_tex(paths)
    except OSError:
        return 0
    if not main:
        return 0
    full, _ = read_source(main)
    _pre, body = split_preamble(full)
    if find_appendix_pos(body) < 0:
        return 0
    src_secs = extract_sections(body)
    model_secs = sorted((o for o in doc.objects.values() if o.type == "Section"),
                        key=lambda o: o.props.get("flow_index") or 0)
    marked = 0
    j = 0
    in_app = False
    for s in model_secs:
        if in_app:
            s.props["is_appendix"] = True
            marked += 1
            continue
        cap = s.props.get("caption") or ""
        if not cap:
            continue
        k = j
        while k < len(src_secs) and not _cap_match(src_secs[k]["caption"], cap):
            k += 1
        if k < len(src_secs):
            j = k + 1
            if src_secs[k].get("is_appendix"):
                in_app = True
                s.props["is_appendix"] = True
                marked += 1
    return marked


# --------------------------------------------------------------------------- #
#  Algorithm extraction (algorithmicx / algpseudocode / algorithmic)
# --------------------------------------------------------------------------- #
# Structural commands by role (matched case-insensitively, so both the
# CamelCase algorithmicx \If/\EndIf and the uppercase algorithmic \IF/\ENDIF
# are covered). Openers add a level; closers remove one; the mid-keywords
# (\Else/\ElsIf) sit one level out from their block body.
_ALG_OPEN = {"if": "if", "for": "for", "forall": "for all", "while": "while",
             "loop": "loop", "repeat": "repeat", "function": "function",
             "procedure": "procedure"}
_ALG_MID = {"else": "else", "elsif": "else if", "elif": "else if"}
_ALG_CLOSE = {"endif", "endfor", "endforall", "endwhile", "endloop",
              "endfunction", "endprocedure", "until"}
_ALG_STMT = {"state": "", "statex": "", "require": "Require: ",
             "ensure": "Ensure: ", "input": "Input: ", "output": "Output: "}
_ALG_ALL = set(_ALG_OPEN) | set(_ALG_MID) | _ALG_CLOSE | set(_ALG_STMT)
_ALG_CMD = re.compile(r"\\([A-Za-z]+)\*?")
_ALGORITHMIC_RE = re.compile(r"\\begin\{algorithmic\}(?:\[[^\]]*\])?", re.S)
_ALGORITHM_FLOAT_RE = re.compile(r"\\begin\{algorithm\}(\*?)")


def _strip_tex_comments(s: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", s)


# bib-database discovery: the file(s) the LaTeX source actually NAMES, not a
# guessed <stem>.bib. BibTeX: \bibliography{a,b} -> a.bib,b.bib. biblatex:
# \addbibresource{x.bib} / \bibresource{x.bib}.
_BIB_BIBLIOGRAPHY = re.compile(r"\\bibliography\s*\{([^}]*)\}")
_BIB_ADDRESOURCE = re.compile(r"\\(?:addbibresource|bibresource)(?:\[[^\]]*\])?\s*\{([^}]*)\}")


# in-text citations: any \cite-family command (BibTeX \cite/\citep/\citet/…,
# biblatex \parencite/\textcite/\autocite/…), with optional [..] args before {keys}.
_CITE_CMD = re.compile(
    r"\\[a-zA-Z]*cite[a-zA-Z]*\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^}]*)\}")


def extract_citation_occurrences(tex: str) -> list[tuple[str, int]]:
    """Every (citekey, source_position) from all \\cite-family commands, in order.
    `\\cite{a,b}` yields two occurrences; a `*` key (\\nocite{*}) is skipped."""
    out: list[tuple[str, int]] = []
    for m in _CITE_CMD.finditer(_strip_tex_comments(tex)):
        for key in m.group(1).split(","):
            key = key.strip()
            if key and key != "*":
                out.append((key, m.start()))
    return out


def extract_citations(tex: str) -> list[str]:
    """Ordered, de-duplicated citekeys the paper cites — used to build THIS
    paper's bibliography (the cited subset) from a possibly-larger shared .bib."""
    seen: dict[str, None] = {}
    for key, _ in extract_citation_occurrences(tex):
        seen.setdefault(key, None)
    return list(seen)


def find_bib_resources(source_dir) -> dict:
    """Discover the bibliography database(s) a LaTeX source NAMES, by reading the
    `.tex` files in `source_dir` for `\\bibliography{}` (BibTeX) and
    `\\addbibresource{}`/`\\bibresource{}` (biblatex), resolving each name to an
    existing `.bib` in the dir. Plus any compiled `.bbl`. Falls back to any
    `.bib` in the dir when no command names one. Returns {"bib": [...], "bbl":
    [...]} of existing paths (deduped, order-stable)."""
    from pathlib import Path
    d = Path(source_dir)
    if not d.is_dir():
        return {"bib": [], "bbl": []}
    blob = ""
    for tex in sorted(d.glob("*.tex")):
        try:
            blob += "\n" + _strip_tex_comments(tex.read_text(errors="replace"))
        except Exception:
            pass
    names: list[str] = []
    for rx in (_BIB_BIBLIOGRAPHY, _BIB_ADDRESOURCE):
        for m in rx.finditer(blob):
            for nm in m.group(1).split(","):
                nm = nm.strip()
                if nm:
                    names.append(nm if nm.lower().endswith(".bib") else nm + ".bib")
    bib = [str(d / nm) for nm in names if (d / nm).exists()]
    if not bib:                                  # no command named one → any .bib
        bib = [str(p) for p in sorted(d.glob("*.bib"))]
    bbl = [str(p) for p in sorted(d.glob("*.bbl"))]
    return {"bib": list(dict.fromkeys(bib)), "bbl": list(dict.fromkeys(bbl))}


def _clean_step_text(s: str) -> str:
    """Light prettify of a step's content: drop the \\State carrier, lower a few
    very common inline keywords, collapse whitespace. Math is left verbatim."""
    s = re.sub(r"\\Return\b", "return", s)
    s = re.sub(r"\\Comment\{", "// ", s).replace("\\Comment ", "// ")
    s = re.sub(r"\\(?:State|Statex)\b", " ", s)
    s = re.sub(r"\\label\{[^}]*\}", "", s)                       # drop \label anchors
    s = re.sub(r"\\(?:rm|bf|it|tt|sf|em|sl|sc|normalfont)\b", "", s)  # font switches
    s = s.replace("~", " ")
    s = re.sub(r"\s+", " ", s).strip(" {}")
    return s.strip()


def _parse_algorithmic_steps(body: str) -> list[dict]:
    """Walk an algorithmic body into [{text, depth}], depth from the block
    nesting (\\If/\\For/… open a level, \\EndIf/… close it, \\Else/\\ElsIf dedent
    their own line)."""
    body = _strip_tex_comments(body)
    bounds = [(m.start(), m.end(), m.group(1).lower())
              for m in _ALG_CMD.finditer(body) if m.group(1).lower() in _ALG_ALL]
    steps: list[dict] = []
    depth = 0
    cursor = 0
    for i, (s, e, name) in enumerate(bounds):
        if s < cursor:                       # swallowed inside a previous arg
            continue
        # capture immediately-following {…} groups as the keyword argument
        j = e
        args: list[str] = []
        while j < len(body) and body[j] in " \t":
            j += 1
        while j < len(body) and body[j] == "{":
            grp = _balanced(body, j)
            args.append(grp[1:-1])
            j += len(grp)
        cursor = j
        nxt = next((bs for (bs, _, _) in bounds[i + 1:] if bs >= cursor), len(body))
        tail = body[cursor:nxt]
        arg = " ".join(a.strip() for a in args if a.strip())

        if name in _ALG_CLOSE:
            depth = max(0, depth - 1)
            continue
        if name in _ALG_MID:
            text = (_ALG_MID[name] + " " + arg + " " + tail).strip()
            steps.append({"text": _clean_step_text(text), "depth": max(0, depth - 1)})
            continue
        if name in _ALG_OPEN:
            text = (_ALG_OPEN[name] + " " + arg + " " + tail).strip()
            steps.append({"text": _clean_step_text(text), "depth": depth})
            depth += 1
            continue
        # statement: \State / \Statex content, or \Require/\Ensure/\Input/\Output
        prefix = _ALG_STMT[name]
        text = (prefix + arg + " " + tail).strip()
        cleaned = _clean_step_text(text)
        if cleaned:
            steps.append({"text": cleaned, "depth": depth})
    return steps


def extract_algorithms(body: str) -> list[dict]:
    """Isolate every algorithm in document order: each
    {number, title, label, page, pos, steps:[{text, depth}]}.

    Primary unit = an `algorithmic` body (the part with parseable steps). A
    `\\begin{algorithm}` float around it supplies `\\caption` (title), `\\label`,
    and the auto-`number` (floats number sequentially in document order). A
    standalone `algorithmic` (not in a float) has number=None / no caption.
    """
    # float spans → (start, end, ordinal, caption, label)
    floats: list[dict] = []
    n = 0
    for m in _ALGORITHM_FLOAT_RE.finditer(body):
        endm = re.compile(r"\\end\{algorithm\*?\}").search(body, m.end())
        end = endm.end() if endm else len(body)
        n += 1
        head = body[m.start():end]
        cap = re.search(r"\\caption\{", head)
        title = _norm(_balanced(head, cap.start() + len("\\caption"))[1:-1]) if cap else ""
        lab = re.search(r"\\label\{([^}]*)\}", head)
        floats.append({"start": m.start(), "end": end, "number": n,
                       "title": title, "label": lab.group(1) if lab else ""})

    out: list[dict] = []
    consumed_floats: set[int] = set()
    for m in _ALGORITHMIC_RE.finditer(body):
        endm = re.compile(r"\\end\{algorithmic\}").search(body, m.end())
        inner_end = endm.start() if endm else len(body)
        inner = body[m.end():inner_end]
        owner = next((f for fi, f in enumerate(floats)
                      if f["start"] <= m.start() < f["end"]
                      and not consumed_floats.add(fi)), None)
        out.append({
            "number": owner["number"] if owner else None,
            "title": owner["title"] if owner else "",
            "label": owner["label"] if owner else "",
            "page": None, "pos": m.start(),
            "steps": _parse_algorithmic_steps(inner),
        })

    # algorithm floats with NO inner algorithmic body (algorithm2e / plain):
    # isolate them too, one step per non-empty line.
    for f in floats:
        if f["number"] in {o["number"] for o in out if o["number"]}:
            continue
        head = body[f["start"]:f["end"]]
        inner = re.sub(r"\\(?:begin|end)\{algorithm\*?\}", "", head)
        inner = re.sub(r"\\caption\{.*?\}|\\label\{[^}]*\}", "", inner, flags=re.S)
        lines = [_clean_step_text(x) for x in re.split(r"\\\\|\\;|\n", inner)]
        steps = [{"text": x, "depth": 0} for x in lines if x]
        if not steps:
            continue
        out.append({"number": f["number"], "title": f["title"], "label": f["label"],
                    "page": None, "pos": f["start"], "steps": steps})

    out.sort(key=lambda a: a["pos"])
    return out


def _clean_theorem_body(s: str) -> str:
    """Strip the `\\label{}` from a theorem/proof body and normalise whitespace.
    Cite-transclusion + prose cleaning happen in build_source_model (it has the
    bibkey), exactly as for a Paragraph."""
    s = re.sub(r"\\label\{[^}]*\}", "", s)
    return _norm(s)


def extract_theorems(body: str, theorem_envs, newtheorem_decls: list) -> dict:
    r"""Isolate theorem-like blocks and proofs in document order, for a LEAN4/
    theorem-proof export. `theorem_envs` = the env names declared via
    `\newtheorem` (from `scan_environments`); `newtheorem_decls` supplies each
    env's printed title, shared/own counter and starred-ness.

    Returns {theorems:[…], proofs:[…]}:
      theorem = {env, kind, printed_title, bracket_title, label, number,
                 statement, start, end, pos, starred}
      proof   = {name, of_label, of_pos, statement, start, end, pos}
    Numbering follows the shared-counter chain (`\newtheorem{lemma}[theorem]…`
    → lemma shares theorem's counter); starred envs are unnumbered. Caveat: the
    `[section]` reset/prefix is NOT applied (plain sequential per counter group).
    A proof pairs to the theorem named by a `\ref` in its `[optional]` arg, else
    to the nearest preceding unclaimed theorem (adjacency)."""
    decl_by_name = {d["name"]: d for d in newtheorem_decls}

    def root(name: str) -> str:
        seen: set = set()
        d = decl_by_name.get(name)
        while (d and d.get("shared_counter")
               and d["shared_counter"] in decl_by_name and name not in seen):
            seen.add(name)
            name = d["shared_counter"]
            d = decl_by_name.get(name)
        return name

    blocks = []
    for env in theorem_envs:
        for b in _env_blocks(body, env):
            blocks.append((b["pos"], b["pos"] + len(b["code"]), env, b["code"]))
    blocks.sort()

    counters: dict = {}
    theorems = []
    for start, end, env, code in blocks:
        d = decl_by_name.get(env, {})
        starred = d.get("starred", False)
        inner = re.sub(r"^\\begin\{" + re.escape(env) + r"\}", "", code, count=1)
        inner = re.sub(r"\\end\{" + re.escape(env) + r"\}\s*$", "", inner, count=1)
        mt = re.match(r"\s*\[([^\]]*)\]", inner)
        bracket = ""
        if mt:
            bracket = mt.group(1).strip()
            inner = inner[mt.end():]
        lm = re.search(r"\\label\{([^}]*)\}", inner)
        label = lm.group(1).strip() if lm else ""
        number = None
        if not starred:
            r = root(env)
            counters[r] = counters.get(r, 0) + 1
            number = counters[r]
        theorems.append({
            "env": env, "kind": env.rstrip("*"),
            "printed_title": d.get("title") or env.rstrip("*").title(),
            "bracket_title": bracket, "label": label, "number": number,
            "statement": _clean_theorem_body(inner),
            "start": start, "end": end, "pos": start, "starred": starred})

    th_by_pos = sorted(theorems, key=lambda t: t["pos"])
    claimed: set = set()
    proofs = []
    for b in sorted(_env_blocks(body, "proof"), key=lambda b: b["pos"]):
        start, code = b["pos"], b["code"]
        inner = re.sub(r"^\\begin\{proof\}", "", code, count=1)
        inner = re.sub(r"\\end\{proof\}\s*$", "", inner, count=1)
        mt = re.match(r"\s*\[([^\]]*)\]", inner)
        name = ""
        if mt:
            name = mt.group(1).strip()
            inner = inner[mt.end():]
        rm = re.search(r"\\ref\{([^}]*)\}", name)
        of_label = rm.group(1).strip() if rm else ""
        of_pos = None
        if of_label:
            c = next((t for t in th_by_pos if t["label"] == of_label), None)
            if c:
                of_pos = c["pos"]
                claimed.add(of_pos)
        if of_pos is None:
            prev = [t for t in th_by_pos if t["pos"] < start and t["pos"] not in claimed]
            if prev:
                of_pos = prev[-1]["pos"]
                claimed.add(of_pos)
        proofs.append({"name": name, "of_label": of_label, "of_pos": of_pos,
                       "statement": _clean_theorem_body(inner),
                       "start": start, "end": start + len(code), "pos": start})
    return {"theorems": theorems, "proofs": proofs}


# Structural blocks excluded from prose (blanked to equal-length whitespace so
# the surrounding prose still splits into paragraphs at the right positions).
_STRUCT_RE = re.compile(
    r"\\\[.*?\\\]"
    r"|\$\$.*?\$\$"
    r"|\\begin\{(equation|align|gather|multline|eqnarray|displaymath|figure|table|"
    r"tikzpicture|algorithm|algorithmic|verbatim|lstlisting|tabular|cases|array|"
    r"itemize|enumerate|description|abstract|thebibliography)\*?\}.*?\\end\{\1\*?\}"
    r"|\\(?:section|subsection|subsubsection|chapter|paragraph|subparagraph)\*?\s*\{[^{}]*\}",
    re.S)

# Inline math: \( … \) or $ … $ (never $$). Named groups p / d.
_INLINE_MATH = re.compile(
    r"(?<!\\)\\\((?P<p>.+?)(?<!\\)\\\)"
    r"|(?<![\\$])\$(?!\$)(?P<d>.+?)(?<!\\)\$",
    re.S)

_PROSE_CLEAN = [
    (re.compile(r"\\(?:textbf|textit|emph|texttt|textsc|textrm|textsf|mathrm)\s*\{([^{}]*)\}"), r"\1"),
    # NB: \cite is NOT bracketed here — it's turned into a {{…||CIT}} transclusion
    # by _transclude_cites BEFORE _clean_prose runs (LATW ReferenceScanner style).
    (re.compile(r"\\(?:eqref|ref|autoref|cref|Cref)\s*\{[^}]*\}"), "(ref)"),
    (re.compile(r"\\(?:bibliography|bibliographystyle|addbibresource|bibresource"
                r"|printbibliography|input|include)\s*\{[^}]*\}"), ""),
    (re.compile(r"\\label\s*\{[^}]*\}"), ""),
    (re.compile(r"\\%"), "%"), (re.compile(r"~"), " "),
]


def _transclude_cites(text: str, bibkey: str) -> str:
    """Replace every in-text \\cite-family command with a citation TRANSCLUSION
    per key — `\\cite{a,b}` → `{{<bibkey>_REF_<a>||CIT}} {{<bibkey>_REF_<b>||CIT}}`
    (LATW ReferenceScanner behaviour). The target title matches the TiddlyWiki
    projector's Reference titling (`<bibkey>_REF_<alnum citekey>`), so it resolves
    once the bibliography is built (`pdfdrill bibliography`/`bibsource`)."""
    def repl(m):
        keys = [k.strip() for k in m.group(1).split(",") if k.strip()]
        return " ".join("{{" + bibkey + "_REF_" + re.sub(r"[^A-Za-z0-9]", "", k)
                        + "||CIT}}" for k in keys)
    return _CITE_CMD.sub(repl, text)


# formatting / no-content commands that leak into prose — captured (not deleted)
# as LtxCommand objects so the original LaTeX is preserved + tagged, and rendered
# per-output via the LTX transclusion template (undefined ⇒ shows nothing).
_LTX_LEAK = re.compile(
    r"\\(?:setlength|setcounter|pagestyle|thispagestyle|pagenumbering|"
    r"vspace\*?|hspace\*?|vskip|hskip|vfill|hfill|smallskip|medskip|bigskip|"
    r"noindent|clearpage|cleardoublepage|newpage|pagebreak|nopagebreak|"
    r"linebreak|newline|centering|raggedright|raggedleft)\b"
    r"(?:\s*\{[^{}]*\}|\s*\[[^\]]*\]|\s*[-\d.][\w.]*)*")


def _capture_ltx(text: str, bibkey: str, start_n: int) -> "tuple[str, list, int]":
    """Replace each leaked formatting command with a `{{<bibkey>_LTX<n>||LTX}}`
    transclusion; return (text, [{title, latex_code}], next_n). The command is
    PRESERVED in the returned dict (→ an LtxCommand tiddler), never deleted."""
    objs: list = []
    n = [start_n]

    def repl(m):
        n[0] += 1
        title = f"{bibkey}_LTX{n[0]}"
        objs.append({"title": title, "latex_code": m.group(0).strip()})
        return "{{" + title + "||LTX}}"
    out = _LTX_LEAK.sub(repl, text)
    return out, objs, n[0]


def _clean_prose(s: str) -> str:
    for rx, rep in _PROSE_CLEAN:
        s = rx.sub(rep, s)
    return re.sub(r"[ \t]+", " ", s).strip()


def _prose_chunks(body: str):
    """Yield (pos, raw_prose) for each blank-line-separated prose block, with
    structural blocks blanked out (length preserved → positions stay valid)."""
    cleaned = _STRUCT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), body)
    for m in re.finditer(r"(?s)\S.*?(?=\n[ \t]*\n|\Z)", cleaned):
        if m.group(0).strip():
            yield m.start(), m.group(0)


def build_source_model(tex_path: str, bibkey: str = "DOC") -> "object":
    """Build a docmodel `Document` from a LaTeX source file (NO OCR/MathPix).

    Inlines \\input/\\include, resolves macros from the preamble AND local
    style files (\\usepackage{mystyle} -> mystyle.sty), then emits Section,
    display-Equation, graphic (TikZ/table) and Algorithm DocObjects in document
    order. Each Equation carries the author's `latex_original` and a macro-`latex`
    (expanded) form; no cdn_url (there is no rendered crop on the source-only
    path). Returns the Document.
    """
    from docmodel.core import Document, DocObject, Realization

    full, main = read_source(tex_path)
    pre, body = split_preamble(full)
    base_dir = os.path.dirname(os.path.abspath(tex_path))
    macros = collect_macros(pre, base_dir)

    doc = Document()
    doc.meta["bibkey"] = bibkey
    doc.meta["source_path"] = f"{main} (LaTeX source, no OCR)"
    doc.meta["latex_preamble"] = {"main": main, "num_macros": len(macros),
                                  "standalone": standalone_preamble(pre)}

    # Environment census + theorem/proof extraction (theorem-like blocks become
    # Theorem objects with a label \ref can resolve; proofs pair to them). Needs
    # the \newtheorem declarations, so scan the preamble + local styles up front.
    env_scan = scan_environments(pre + "\n" + _local_style_text(base_dir), body)
    thm = extract_theorems(body, env_scan["theorem_like"], env_scan["newtheorem"])

    # Merge sections + equations + graphics + theorems/proofs + PROSE PARAGRAPHS
    # into one flow-ordered (by source position) stream, so the tiddler reading
    # order matches the document. Paragraphs carry inline math as real Formula
    # objects (latex = expanded for KaTeX, latex_original = the author macro src).
    # Blank theorem/proof spans from the prose body so their statements don't
    # ALSO surface as Paragraphs (length-preserved → positions stay valid).
    prose_body = body
    for blk in thm["theorems"] + thm["proofs"]:
        seg = prose_body[blk["start"]:blk["end"]]
        prose_body = (prose_body[:blk["start"]]
                      + re.sub(r"[^\n]", " ", seg) + prose_body[blk["end"]:])

    _ab = extract_abstract(body)
    items = ([("section", s["pos"], s) for s in extract_sections(body)]
             + [("equation", e["pos"], e) for e in extract_display_equations(body)]
             + [("graphic", g["pos"], g) for g in extract_graphics(body)]
             + ([("abstract", _ab["pos"], _ab)] if _ab else [])
             + [("theorem", t["pos"], t) for t in thm["theorems"]]
             + [("proof", p["pos"], p) for p in thm["proofs"]]
             + [("para", pos, raw) for pos, raw in _prose_chunks(prose_body)])
    items.sort(key=lambda t: t[1])
    pos_to_theorem_id: dict = {}        # theorem source pos -> Theorem object id
    pending_proofs: list = []           # (proof dict, Proof object) to pair after

    n_sec = n_eq = n_dia = n_tab = n_para = n_formula = n_abs = n_ltx = 0
    fi = 0
    formula_no = 0
    formula_titles: dict[str, str] = {}    # content key -> FO title (de-dup)
    ltx_no = 0
    current_section = None        # id of the most recent Section (parent linkage)
    for kind, _pos, it in items:
        fi += 1
        if kind == "section":
            s_obj = DocObject(type="Section", props={
                "level": it["level"], "caption": it["caption"],
                "flow_index": fi, "bibkey": bibkey,
                **({"is_appendix": True} if it.get("is_appendix") else {})})
            doc.add(s_obj)
            current_section = s_obj.id
            n_sec += 1
        elif kind == "abstract":
            doc.add(DocObject(type="Abstract", props={
                "text": _clean_prose(_transclude_cites(it["text"], bibkey)),
                "flow_index": fi, "bibkey": bibkey}))
            n_abs += 1
        elif kind == "theorem":
            t_obj = DocObject(type="Theorem", props={
                "kind": it["kind"], "env": it["env"],
                "printed_title": it["printed_title"],
                "title": it["bracket_title"], "number": it["number"],
                "label": it["label"], "starred": it["starred"],
                "statement": _clean_prose(_transclude_cites(it["statement"], bibkey)),
                "flow_index": fi, "bibkey": bibkey,
                **({"parent_section": current_section} if current_section else {})})
            doc.add(t_obj)
            pos_to_theorem_id[it["pos"]] = t_obj.id
        elif kind == "proof":
            p_obj = DocObject(type="Proof", props={
                "name": it["name"], "of_label": it["of_label"],
                "statement": _clean_prose(_transclude_cites(it["statement"], bibkey)),
                "flow_index": fi, "bibkey": bibkey,
                **({"parent_section": current_section} if current_section else {})})
            doc.add(p_obj)
            pending_proofs.append((it, p_obj))
        elif kind == "equation":
            original = it["latex"]
            doc.add(DocObject(type="Equation", props={
                "latex": expand_macros(original, macros),
                "latex_original": original,
                "numbered": it.get("numbered"), "label": it.get("label"),
                "env": it.get("env"), "flow_index": fi, "bibkey": bibkey}))
            n_eq += 1
        elif kind == "graphic":
            code = expand_macros(it["code"], macros)
            doc.add(DocObject(type=it["kind"], props={
                "latex_code": code, "latex_original": it["code"],
                "caption": it.get("caption", ""), "env": it["env"],
                "flow_index": fi, "bibkey": bibkey}))
            if it["kind"] == "Diagram":
                n_dia += 1
            else:
                n_tab += 1
        else:  # prose paragraph: extract inline math → Formula objects, transclude
            text = it
            out, last = [], 0
            for mm in _INLINE_MATH.finditer(text):
                original = (mm.group("p") or mm.group("d") or "").strip()
                if not original:
                    continue
                expanded = expand_macros(original, macros)     # KaTeX renders this
                # CONTENT DE-DUPLICATION (LATW FormulaScanner / MathPix
                # FormulaProcessor parity): identical inline math = ONE Formula
                # tiddler, transcluded everywhere — so the symbol `f` used 20×
                # is one FO tiddler, not 20. Key on the expanded LaTeX (what
                # KaTeX renders), whitespace-collapsed.
                key = re.sub(r"\s+", " ", expanded).strip()
                if key in formula_titles:
                    title = formula_titles[key]
                else:
                    formula_no += 1
                    fi += 1
                    doc.add(DocObject(type="Formula", props={
                        "latex": expanded,
                        "latex_original": original,            # author's macro source
                        "display": False, "flow_index": fi, "bibkey": bibkey}))
                    n_formula += 1
                    title = re.sub(r"[^A-Za-z0-9_\-\.]", "_",
                                   f"{bibkey}_FO{formula_no:04d}")
                    formula_titles[key] = title
                out.append(text[last:mm.start()])
                out.append("{{" + title + "||FO}}")            # transclude the FO tiddler
                last = mm.end()
            out.append(text[last:])
            prose = _clean_prose(_transclude_cites("".join(out), bibkey))
            prose, _ltx_objs, ltx_no = _capture_ltx(prose, bibkey, ltx_no)
            for _lo in _ltx_objs:
                doc.add(DocObject(type="LtxCommand", props={
                    **_lo, "flow_index": fi, "bibkey": bibkey}))
                n_ltx += 1
            if not prose:
                continue
            props = {"text": prose, "flow_index": fi, "bibkey": bibkey}
            if current_section:
                props["parent_section"] = current_section
            doc.add(DocObject(type="Paragraph", props=props))
            n_para += 1

    # Pair each Proof to its Theorem (by \ref label or adjacency, resolved in
    # extract_theorems) so a Theorem tiddler can transclude its proof and back.
    n_thm = sum(1 for o in doc.objects.values() if o.type == "Theorem")
    n_proof = 0
    for pdict, p_obj in pending_proofs:
        n_proof += 1
        tid = pos_to_theorem_id.get(pdict["of_pos"])
        if tid:
            p_obj.props["proof_of"] = tid
            doc.objects[tid].props.setdefault("proof_id", p_obj.id)

    # In-text citations: one Citation per \cite-family key, anchored in a
    # `source_cites` stream so it carries a linkable surface. We pick ALL \cite
    # commands — the paper's citation set — so a larger shared .bib is later
    # restricted to exactly what THIS paper cites (cmd_bibsource).
    n_cit = 0
    occ = extract_citation_occurrences(body)
    if occ:
        cstream = doc.ensure_stream("source_cites")
        for key, pos in occ:
            fi += 1
            anchor = cstream.append(citekey=key, pos=pos)
            cobj = DocObject(type="Citation", props={
                "citekey": key, "style": "latex", "added_by": "latex",
                "flow_index": fi, "bibkey": bibkey})
            cobj.add_realization(Realization(stream="source_cites", start=anchor,
                                             end=anchor, role="surface",
                                             provenance="latex"))
            doc.add(cobj)
            n_cit += 1

    # Algorithms: each is an Algorithm DocObject with AlgorithmStep children
    # (mirroring the MathPix `pdfdrill algorithms` shape, here from LaTeX source).
    n_alg = n_steps = 0
    for a in extract_algorithms(body):
        fi += 1
        alg = DocObject(type="Algorithm", props={
            "number": a["number"], "title": a["title"], "label": a.get("label", ""),
            "page": a.get("page"), "flow_index": fi, "bibkey": bibkey,
            "added_by": "latex"})
        doc.add(alg)
        n_alg += 1
        for s in a["steps"]:
            st = DocObject(type="AlgorithmStep",
                           props={"text": s["text"], "depth": s["depth"],
                                  "bibkey": bibkey, "added_by": "latex"},
                           parent=alg.id)
            doc.add(st)
            alg.children.append(st.id)
            n_steps += 1

    # Environment tracking (used census + custom/theorem-like declarations) —
    # valuable for higher layers (e.g. a LEAN4 theorem/proof export). Computed
    # up front (env_scan) for theorem extraction; stored here.
    doc.meta["environments"] = env_scan

    doc.meta["source_counts"] = {"sections": n_sec, "equations": n_eq,
                                 "paragraphs": n_para, "formulas": n_formula,
                                 "diagrams": n_dia, "tables": n_tab,
                                 "algorithms": n_alg, "algorithm_steps": n_steps,
                                 "theorems": n_thm, "proofs": n_proof,
                                 "abstract": n_abs, "ltx_commands": n_ltx,
                                 "citations": n_cit, "macros": len(macros)}
    return doc
