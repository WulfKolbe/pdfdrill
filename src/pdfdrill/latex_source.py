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
        with tempfile.TemporaryDirectory() as d:
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


def standalone_preamble(preamble: str) -> str:
    """A `standalone` docclass + the author's packages + macro defs, for the
    future latex→dvi→dvisvgm step (TikZ/tables that KaTeX can't render)."""
    pkgs = [m.group(0) for m in re.finditer(r"\\usepackage(\[[^\]]*\])?\{[^}]*\}", preamble)]
    defs = [m.group(0) for m in re.finditer(
        r"\\(?:re)?newcommand\*?.*|\\DeclareMathOperator\*?.*|\\def\\.*", preamble)]
    return "\n".join(["\\documentclass{standalone}", *pkgs, *defs])


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
        items.append({"env": env, "latex": _clean_eq(inner), "numbered": numbered,
                      "label": label, "pos": m.start()})
    for m in re.finditer(r"\\\[(.*?)\\\]", body, re.S):
        items.append({"env": "displaymath", "latex": _clean_eq(m.group(1)),
                      "numbered": False, "label": None, "pos": m.start()})
    for m in re.finditer(r"(?<!\\)\$\$(.+?)\$\$", body, re.S):
        items.append({"env": "displaymath", "latex": _clean_eq(m.group(1)),
                      "numbered": False, "label": None, "pos": m.start()})
    items.sort(key=lambda it: it["pos"])
    for it in items:
        it.pop("pos", None)
    return items


def _clean_eq(inner: str) -> str:
    s = re.sub(r"\\label\{[^}]*\}", "", inner)
    s = re.sub(r"\\(?:nonumber|notag)\b", "", s)
    return _norm(s)


_SECTION_RE = re.compile(r"\\(part|chapter|section|subsection)\*?\{")


def extract_sections(body: str) -> list[dict]:
    """Headings in document order: {level, caption, pos}. Levels 1..4."""
    level = {"part": 1, "chapter": 1, "section": 2, "subsection": 3, "subsubsection": 4}
    out = []
    for m in _SECTION_RE.finditer(body):
        kind = m.group(1)
        cap = _balanced(body, m.end() - 1)[1:-1]
        out.append({"level": level.get(kind, 2), "caption": _norm(cap),
                    "kind": kind, "pos": m.start()})
    return out


def build_source_model(tex_path: str, bibkey: str = "DOC") -> "object":
    """Build a docmodel `Document` from a LaTeX source file (NO OCR/MathPix).

    Inlines \\input/\\include, resolves macros from the preamble AND local
    style files (\\usepackage{mystyle} -> mystyle.sty), then emits Section and
    display-Equation DocObjects in document order. Each Equation carries the
    author's `latex_original` and a macro-`latex` (expanded) form; no cdn_url
    (there is no rendered crop on the source-only path). Returns the Document.
    """
    from docmodel.core import Document, DocObject

    full, main = read_source(tex_path)
    pre, body = split_preamble(full)
    base_dir = os.path.dirname(os.path.abspath(tex_path))
    macros = collect_macros(pre, base_dir)

    doc = Document()
    doc.meta["bibkey"] = bibkey
    doc.meta["source_path"] = f"{main} (LaTeX source, no OCR)"
    doc.meta["latex_preamble"] = {"main": main, "num_macros": len(macros),
                                  "standalone": standalone_preamble(pre)}

    # Merge sections + equations into one flow-ordered stream by source pos.
    items = ([("section", s) for s in extract_sections(body)]
             + [("equation", e) for e in extract_display_equations(body)])
    items.sort(key=lambda t: t[1].get("pos", 0))

    fi = 0
    n_sec = n_eq = 0
    for kind, it in items:
        fi += 1
        if kind == "section":
            doc.add(DocObject(type="Section", props={
                "level": it["level"], "caption": it["caption"],
                "flow_index": fi, "bibkey": bibkey}))
            n_sec += 1
        else:
            original = it["latex"]
            doc.add(DocObject(type="Equation", props={
                "latex": expand_macros(original, macros),
                "latex_original": original,
                "numbered": it.get("numbered"), "label": it.get("label"),
                "env": it.get("env"), "flow_index": fi, "bibkey": bibkey}))
            n_eq += 1
    doc.meta["source_counts"] = {"sections": n_sec, "equations": n_eq,
                                 "macros": len(macros)}
    return doc
