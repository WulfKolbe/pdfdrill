r"""
LaTeXPipeline — the inspectable model→LaTeX generator.

Where `LaTeXProjector` (latex.py) is a single opaque text-dump, this is a PIPELINE
of pure, inspectable STAGES — each returns plain data you can dump to a file and
test independently (the textscan-style inspectability). `pdfdrill latex
--dump-stages` writes them next to the assembled `.tex`:

    00-transclusions.json   {marker-id → LaTeX}      (array lookup)
    01-citations.json       [citekey, …]             (\cite map)
    02-bibliography.bib      thebibliography / .bib   (\bibitem)
    03-glossary.tex          \newacronym/\printindex  (next increment)

The stages fix the "Markdown with a LaTeX header" problem: a MathPix/scan doc's
paragraph text carries `{{<bibkey>_FO0001||FO}}` transclusion markers + Markdown
headings; the body resolver turns each marker into the formula's `$…$` (by array
lookup) and each heading into `\section`, so the body is real LaTeX.

Status: stages 0 (transclusion), 1 (citation), 2 (bibliography) are wired.
Stage 3 (glossary/acronym/index) reuses `semantic.stex` and lands next.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from docmodel.core import Document

# a transclusion marker: {{<title>||<TPL>}} where TPL ∈ FO/FREF/FN/PIC/DIA/CIT…
_MARKER = re.compile(r"\{\{([^|{}]+?)\|\|([A-Z]+)\}\}")
# a Markdown / leaked heading at line start
_MD_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")
_TEX_SECTION = re.compile(r"^\\(sub)*section\*?\{")


# ── stage 0: transclusion as a readarray ARRAY (filecontents + readarray) ────
#
# The formula LaTeX goes ONCE into a `.dat` array (one entry per line); each
# `{{<bibkey>_FO0001||FO}}` marker becomes `\Expr{<index>}`. This is real
# transclusion (define once, reference by index), not inline expansion — the
# user's filecontents+readarray idiom. Deduped by content so identical math
# shares one slot.

# MathPix / OCR emit Unicode math operators INSIDE the LaTeX. In math mode these
# are NOT rendered by xelatex/pdflatex without unicode-math — the classic one is
# U+2212 (a "minus" that isn't ASCII `-`). Map them to LaTeX macros / ASCII.
_MATH_UNICODE = {
    "−": "-", "–": "-", "—": "-", "×": "\\times ",
    "÷": "\\div ", "±": "\\pm ", "∓": "\\mp ",
    "≤": "\\leq ", "≥": "\\geq ", "≠": "\\neq ",
    "≈": "\\approx ", "≡": "\\equiv ", "∞": "\\infty ",
    "∑": "\\sum ", "∏": "\\prod ", "∫": "\\int ",
    "√": "\\sqrt ", "∂": "\\partial ", "∇": "\\nabla ",
    "∈": "\\in ", "∉": "\\notin ", "⊂": "\\subset ",
    "⊆": "\\subseteq ", "∪": "\\cup ", "∩": "\\cap ",
    "→": "\\to ", "⇒": "\\Rightarrow ", "⇔": "\\Leftrightarrow ",
    "∀": "\\forall ", "∃": "\\exists ", "·": "\\cdot ",
    "…": "\\dots ", "°": "^{\\circ}",
    "α": "\\alpha ", "β": "\\beta ", "γ": "\\gamma ",
    "δ": "\\delta ", "ε": "\\epsilon ", "λ": "\\lambda ",
    "μ": "\\mu ", "π": "\\pi ", "σ": "\\sigma ",
    "φ": "\\phi ", "ω": "\\omega ", "Δ": "\\Delta ",
    "Σ": "\\Sigma ", "Ω": "\\Omega ",
}
_MATH_UNICODE_RE = re.compile("|".join(re.escape(k) for k in _MATH_UNICODE))


def sanitize_math(latex: str) -> str:
    """Replace Unicode math operators (U+2212 minus, ×, ≤, Greek, …) with their
    LaTeX macros, so the formula compiles in math mode without `unicode-math`.
    Plain LaTeX is untouched."""
    return _MATH_UNICODE_RE.sub(lambda m: _MATH_UNICODE[m.group(0)], latex)


# DISPLAY-only math environments — invalid inside inline math (`\ensuremath`,
# which is what `\Expr` uses). A Formula carrying one is really a display equation
# mis-classified; strip the env + alignment so `\Expr{i}` compiles (cramped but
# valid) instead of erroring "Not allowed in LR mode".
_DISPLAY_ENV = re.compile(
    r"\\(?:begin|end)\{(?:aligned|split|gathered|gather\*?|align\*?|cases|"
    r"array|equation\*?|multline\*?|eqnarray\*?)\}(?:\{[^}]*\})?")


def _inline_safe(latex: str) -> str:
    """Make a formula safe for INLINE math: strip display-only environments and
    the alignment markers (`\\\\` line breaks, `&`) that error in LR mode."""
    if "\\begin{" not in latex and "\\\\" not in latex and "&" not in latex:
        return latex                                 # plain inline — untouched
    latex = _DISPLAY_ENV.sub(" ", latex)
    latex = latex.replace("\\\\", " \\; ").replace("&", " ")
    return re.sub(r"\s+", " ", latex).strip()


def _flatten(latex: str) -> str:
    """readarray splits entries on `\\par`, so each formula must be a SINGLE line —
    collapse internal whitespace/newlines to one space, normalise Unicode math
    operators (`sanitize_math`), and make display-math inline-safe (`_inline_safe`)
    so `\\Expr{i}` (inline `\\ensuremath`) never hits 'Not allowed in LR mode'."""
    return _inline_safe(sanitize_math(re.sub(r"\s+", " ", latex.strip())))


def formula_array(doc: Document) -> tuple[list[str], dict[str, int]]:
    """Return `(ordered distinct formula LaTeX, {object-title: 1-based index})`.

    Ordered by object title so the array is stable across builds; deduped by
    (flattened) content so an expression used many times shares ONE array slot.
    The index map is what the body resolver rewrites each `{{id||FO}}` into."""
    bibkey = str(doc.meta.get("bibkey") or "DOC")
    order: list[str] = []
    by_content: dict[str, int] = {}          # flattened latex → 1-based index
    title_index: dict[str, int] = {}
    # FLOW order (not obj.id) so the `<bibkey>_FO<NNNN>` numbering matches the
    # source builder's, which numbers by first appearance in the text.
    objs = [o for o in doc.objects.values() if o.type in ("Formula", "Equation")]
    objs.sort(key=lambda o: (o.props.get("flow_index", 0), o.id))
    fo_no = eq_no = 0
    for obj in objs:
        latex = _flatten(obj.props.get("latex") or "")
        if not latex:
            continue
        idx = by_content.get(latex)
        if idx is None:
            order.append(latex)
            idx = len(order)                 # 1-based array position
            by_content[latex] = idx
        title_index[obj.id] = idx            # markers keyed by the object id
        # AND by the transclusion TITLE the source builder / tiddler projector
        # uses (`<bibkey>_FO<NNNN>` / `_EQ<NNNN>`, per-type, by first appearance).
        if obj.type == "Formula":
            fo_no += 1
            title_index[_safe_title(f"{bibkey}_FO{fo_no:04d}")] = idx
        else:
            eq_no += 1
            title_index[_safe_title(f"{bibkey}_EQ{eq_no:04d}")] = idx
    return order, title_index


def _safe_title(t: str) -> str:
    """Match the source builder's title sanitisation (`[^A-Za-z0-9_\\-.]`→`_`)."""
    return re.sub(r"[^A-Za-z0-9_\-.]", "_", t)


def formula_preamble(order: list[str], dat_name: str) -> str:
    """The preamble block: write the formula array to `<dat_name>` via the
    `filecontents*` ENVIRONMENT, load it with `readarray`, and define
    `\\Expr{<index>}`.

    The `filecontents` PACKAGE is obsolete — the environment is in the LaTeX
    kernel (2019+), and loading the package prints an "obsolete" warning — so we
    do not `\\usepackage{filecontents}`. `[overwrite]` regenerates the `.dat`
    every run (the kernel default refuses to overwrite an existing file → a
    stale array survives an edit)."""
    if not order:
        return ""
    body = "\n".join(order)
    return (
        f"\\begin{{filecontents*}}[overwrite]{{{dat_name}}}\n{body}\n"
        "\\end{filecontents*}\n"
        "\\usepackage{readarray}\n"
        "\\readarraysepchar{\\par}\n"
        f"\\readdef{{{dat_name}}}{{\\MathData}}\n"
        "\\readarray{\\MathData}{\\MathExpr}[-,\\nrows]\n"
        "\\newcommand{\\Expr}[1]{\\ensuremath{\\MathExpr[#1]}}"
    )


def resolve_transclusions(text: str, title_index: dict[str, int]) -> str:
    """Rewrite each `{{id||FO}}` / `{{id||FREF}}` marker to `\\Expr{<index>}`
    (array lookup — `\\Expr` is `\\ensuremath`-wrapped, so it works in text). An
    unknown id degrades to a readable placeholder, never raw `{{…}}`."""
    def sub(m: re.Match) -> str:
        title, tpl = m.group(1), m.group(2)
        if tpl == "CIT":
            # a citation transclusion `{{<bibkey>_REF_<citekey>||CIT}}` — the
            # citekey is the tail; emit `\cite{<citekey>}` (matches the \bibitem).
            for sep in ("_REF_", "_CIT_", "_BIB_"):
                if sep in title:
                    return f"\\cite{{{title.split(sep, 1)[-1]}}}"
            return f"\\cite{{{title}}}"
        idx = title_index.get(title)
        if idx is None:
            return f"(?{title})"                      # unknown — readable, no braces
        return f"\\Expr{{{idx}}}"
    return _MARKER.sub(sub, text)


# Ligatures the PDF text layer emits as single codepoints — decompose so the
# font doesn't have to carry them (and word search / spell works).
_LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
              "ﬅ": "ft", "ﬆ": "st"}
_LIG_RE = re.compile("|".join(_LIGATURES))
# Source LaTeX commands that leak into prose but must NOT survive projection: a
# bibliography is emitted as a `thebibliography` block, so a `\bibliography{db}` /
# `\bibliographystyle{s}` would try to load a missing .bib.
_LEAKED_CMD = re.compile(r"\\bibliography(?:style)?\s*\{[^}]*\}")

# Document-STRUCTURE / frontmatter commands that leak from a LaTeX source into
# body prose (the source builder can ingest a `\maketitle` line as a Paragraph).
# The projection OWNS this scaffolding (`\maketitle` only when a title exists,
# its own `\begin{document}`, its own bibliography), so a stray copy in the body
# is at best noise and at worst fatal (`\maketitle` with no `\title` → error).
# `\title{…}`/`\author{…}` are captured by the projector first (see
# `leaked_title`), then stripped here.
_STRUCT_CMD = re.compile(
    r"\\(?:maketitle|tableofcontents|begin\s*\{document\}|end\s*\{document\}"
    r"|appendix|newpage|clearpage|cleardoublepage|pagebreak|nopagebreak"
    r"|pagestyle\s*\{[^}]*\}|thispagestyle\s*\{[^}]*\}"
    r"|title|author|date|institute|affiliation)\s*(?:\{[^}]*\})?"
)
# a leaked `\title{…}` — captured so a title-less model still gets one.
_TITLE_CMD = re.compile(r"\\title\s*\{([^}]*)\}")


def leaked_title(text: str) -> str | None:
    """A `\\title{…}` the source builder left in body prose (title-less model)."""
    m = _TITLE_CMD.search(text or "")
    return m.group(1).strip() if m and m.group(1).strip() else None


# every natbib / biblatex cite variant → plain `\cite` (the projection's
# bibliography is a numeric `thebibliography`, and the default preamble does NOT
# load natbib, so `\citep`/`\citet`/`\parencite`/… would be UNDEFINED). Optional
# `[pre]`/`[post]` args are dropped; the `{keys}` are kept.
_CITE_CMD = re.compile(
    r"\\(?:[Cc]ite(?:t|p|al[tp]|author|year(?:par)?|num)?|parencite|textcite"
    r"|autocite|smartcite|footcite|supercite)\*?\s*(?:\[[^\]]*\]){0,2}\s*(\{[^}]*\})")


def normalize_cite_commands(text: str) -> str:
    """Rewrite `\\citep[..]{k}` / `\\citet{k}` / `\\parencite{k}` / … → `\\cite{k}`."""
    return _CITE_CMD.sub(lambda m: "\\cite" + m.group(1), text)


# inline math spans to PROTECT from prose-special escaping (subscripts, `&`
# alignment inside `$…$` must survive).
_MATH_SPAN = re.compile(r"(\$\$.*?\$\$|\\\[.*?\\\]|\$[^$]*\$|\\\(.*?\\\))", re.DOTALL)


def escape_prose_specials(text: str) -> str:
    """Escape `#`, `%`, `&` in the NON-math parts of prose — each is illegal in
    text mode and never needed literally here (a bare `%` comments the rest of the
    line; `C#` / `R&D` error). IDEMPOTENT (`(?<!\\\\)`), and math spans (`$…$`,
    `\\(…\\)`) are left untouched so subscripts / alignment survive. `_ ^ { } $ \\`
    are deliberately NOT escaped (they carry the model's inline LaTeX)."""
    parts = _MATH_SPAN.split(text)
    for i in range(0, len(parts), 2):             # even indices = non-math text
        seg = parts[i]
        seg = re.sub(r"(?<!\\)#", r"\\#", seg)
        seg = re.sub(r"(?<!\\)%", r"\\%", seg)
        seg = re.sub(r"(?<!\\)&", r"\\&", seg)
        parts[i] = seg
    return "".join(parts)


def clean_prose(text: str) -> str:
    """Normalise prose before it is emitted: expand ligatures, strip leaked
    source-LaTeX bibliography / structure commands (the projection owns those),
    and normalise natbib/biblatex cite commands to `\\cite`."""
    text = _LIG_RE.sub(lambda m: _LIGATURES[m.group(0)], text)
    text = _LEAKED_CMD.sub("", text)
    text = _STRUCT_CMD.sub("", text)          # leaked \maketitle/\begin{document}/…
    text = normalize_cite_commands(text)      # \citep/\citet/… → \cite
    return text


def balance_math(text: str) -> str:
    """Contain a runaway: extraction sometimes drops a closing `\\)` or `$`, and an
    unclosed inline-math span then swallows everything up to the next `\\section`
    ('Not allowed in LR mode'). Balance the delimiters PER BLOCK — append the
    missing `\\)` / `$` — so a malformed span stays inside its own paragraph."""
    opens = len(re.findall(r"\\\(", text))
    closes = len(re.findall(r"\\\)", text))
    if opens > closes:
        text = text + "\\)" * (opens - closes)
    elif closes > opens:
        text = "\\(" * (closes - opens) + text
    # `$` inline math: an odd count is unbalanced (ignore `\$` escaped dollars)
    dollars = len(re.findall(r"(?<!\\)\$", text))
    if dollars % 2:
        text = text + "$"
    return text


def resolve_headings(line: str) -> str:
    """A Markdown `## X` (or a leaked heading) → `\\section{X}` at the right depth.
    Non-heading text passes through; an existing `\\section{…}` is left alone."""
    if _TEX_SECTION.match(line.strip()):
        return line
    m = _MD_HEADING.match(line)
    if not m:
        return line
    depth = len(m.group(1))
    cmd = {1: "section", 2: "section", 3: "subsection",
           4: "subsubsection", 5: "paragraph", 6: "subparagraph"}[depth]
    return f"\\{cmd}{{{m.group(2).strip()}}}"


# ── stage 1: citations (\cite map) ───────────────────────────────────────────

def reference_section_ids(doc: Document) -> set[str]:
    """Ids of every References/Bibliography Section AND the objects under it (its
    printed `[1] …` list). The projector skips these — the `thebibliography` block
    built from Reference objects replaces them, so the list is not duplicated and
    its reference LABELS `[1]` are never mangled into `\\cite`."""
    ref_secs = {
        o.id for o in doc.objects.values()
        if o.type == "Section"
        and re.search(r"\b(references|bibliography|literatur|literaturverzeichnis)\b",
                      str(o.props.get("caption", "")), re.I)
    }
    ids = set(ref_secs)
    for o in doc.objects.values():
        if o.props.get("parent_section") in ref_secs:
            ids.add(o.id)
    return ids


def reference_map(doc: Document) -> dict[int, str]:
    """`{reference number: citekey}` — rewrites a numeric in-text `[N]` to the
    matching `\\cite{<citekey>}` (and the same citekey the bibliography `\\bibitem`
    uses, so they resolve)."""
    m: dict[int, str] = {}
    for o in doc.objects.values():
        if o.type != "Reference":
            continue
        num, key = o.props.get("number"), o.props.get("citekey")
        if num is not None and key:
            try:
                m[int(num)] = str(key)
            except (TypeError, ValueError):
                pass
    return m


_CITE_BRACKET = re.compile(r"\[(\d+(?:\s*[,\-–]\s*\d+)*)\]")


def _expand_bracket_numbers(inner: str) -> "list[int] | None":
    """`"11"` → [11]; `"11, 12"` → [11,12]; `"11-13"` → [11,12,13]. None if it
    isn't a clean numeric citation group."""
    nums: list[int] = []
    for part in re.split(r"\s*,\s*", inner.strip()):
        rng = re.fullmatch(r"(\d+)\s*[\-–]\s*(\d+)", part)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            if b < a or b - a > 50:
                return None
            nums.extend(range(a, b + 1))
        elif part.isdigit():
            nums.append(int(part))
        else:
            return None
    return nums


def resolve_citations(text: str, ref_map: dict[int, str]) -> str:
    """Rewrite a numeric in-text `[N]` / `[N, M]` / `[N-M]` to
    `\\cite{key,...}` using the reference map. A bracket whose numbers are NOT all
    references (an array index, an interval `[0,1]`) is left RAW — never a broken
    `\\cite`."""
    if not ref_map:
        return text

    def sub(m: re.Match) -> str:
        nums = _expand_bracket_numbers(m.group(1))
        if not nums or any(n not in ref_map for n in nums):
            return m.group(0)                    # not a citation — leave raw
        return "\\cite{" + ",".join(ref_map[n] for n in nums) + "}"
    return _CITE_BRACKET.sub(sub, text)


def citation_keys(doc: Document) -> list[str]:
    """The in-text citation keys, in flow order — resolved to the REFERENCE
    citekey when the Citation is numeric (so the dump matches the `\\cite` output),
    else the Citation's own key."""
    ref_map = reference_map(doc)
    cites = [o for o in doc.objects.values() if o.type == "Citation"]
    cites.sort(key=lambda o: o.props.get("flow_index", 0))
    out: list[str] = []
    for o in cites:
        key = str(o.props.get("citekey") or "").strip()
        num = o.props.get("number")
        if num is not None:
            try:
                key = ref_map.get(int(num), key)
            except (TypeError, ValueError):
                pass
        if key:
            out.append(key)
    return out


# ── stage 2: bibliography (\bibitem / thebibliography) ───────────────────────

def _bib_escape(s: str) -> str:
    """Escape the specials in a bibliography/glossary entry (author/title). IDEMPOTENT:
    only an UNescaped special is escaped (`(?<!\\)`), so an entry that already
    carries `\\&`/`\\_` from the source `.bbl` is not double-escaped into `\\\\&`.
    Leaves `$ { } \\` for accents / math the BibTeX carries."""
    s = re.sub(r"(?<!\\)&", r"\\&", s)
    s = re.sub(r"(?<!\\)%", r"\\%", s)
    s = re.sub(r"(?<!\\)#", r"\\#", s)
    s = re.sub(r"(?<!\\)_", r"\\_", s)
    s = re.sub(r"(?<!\\)~", r"\\textasciitilde{}", s)
    return s


def _balance_braces(s: str) -> str:
    """Make `s` brace-balanced: drop a stray `}`, append `}` for each unmatched
    `{`. Escaped braces (`\\{` / `\\}`) are literals, not grouping."""
    depth, out, i, n = 0, [], 0, len(s)
    while i < n:
        c = s[i]
        if c == "\\" and i + 1 < n and s[i + 1] in "{}":
            out.append(s[i:i + 2]); i += 2; continue
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0:
                i += 1; continue                  # drop a stray closer
            depth -= 1
        out.append(c); i += 1
    return "".join(out) + "}" * depth


# a TRUNCATED accent (`Van Merri{\` ← `{\"e}`, `Manning {\{`, `Rockt{\`): a `{\`
# whose control word is missing (followed by a space/brace/punctuation/EOF).
_BROKEN_ACCENT = re.compile(r"\{\\(?=[\s{}(),.;:]|$)")


def _sanitize_bib_body(s: str) -> str:
    """Make a heuristic/OCR bibliography body COMPILE-SAFE, from the RAW body.
    Such a body can carry a truncated accent that leaves an unbalanced brace
    (`Van Merri{\\ (2014)`), OCR forced line breaks (`\\\\`), or an unescaped `&` —
    all fatal in `thebibliography`. Order matters: collapse the `\\\\` breaks and
    drop the broken accent FIRST, THEN escape specials (so a collapsed `\\\\&`
    becomes ` &` → `\\&`, never a bare `&`), then balance braces."""
    s = s.replace("\\\\", " ")                    # OCR forced line breaks first
    s = _BROKEN_ACCENT.sub("", s)                 # truncated `{\` accent → drop
    s = _bib_escape(s)                            # escape unescaped &/%/#/_/~
    s = re.sub(r"[ \t]{2,}", " ", s).strip()
    return _balance_braces(s)


def _bibitem(ref) -> str:
    """A `\\bibitem` for one Reference. ALWAYS emitted (even for a ref carrying full
    `bibtex`): a `.bib` needs a 2-pass bibtex compile, so the self-contained
    `thebibliography` is the default. Formatted from the structured
    author/year/title (from bibsource / the heuristic parse), else raw_text."""
    p = ref.props
    key = str(p.get("citekey") or "ref").strip()
    author = str(p.get("author") or "").strip()
    year = str(p.get("year") or "").strip()
    title = str(p.get("title") or p.get("titlefield") or "").strip()
    body = " ".join(x for x in (author, f"({year})" if year else "", title) if x) \
        or str(p.get("raw_text") or "").strip() or key
    return f"\\bibitem{{{key}}} {_sanitize_bib_body(body)}"


def bibliography_block(doc: Document) -> str:
    """A `thebibliography` environment from the model's Reference objects (empty
    string when there are none). References carrying full `bibtex` are emitted to
    a `.bib` by `bib_database` instead; here we render the printed entries."""
    refs = [o for o in doc.objects.values() if o.type == "Reference"]
    refs.sort(key=lambda o: str(o.props.get("citekey") or ""))
    items = [b for b in (_bibitem(r) for r in refs) if b]
    if not items:
        return ""
    # `\bibitem` here carries NO optional [label], so labels are auto-NUMBERED
    # ([1]…[N]); the width arg must be the widest NUMBER, not a long citekey.
    widest = "9" * len(str(len(items)))
    return ("\\begin{thebibliography}{%s}\n" % widest
            + "\n".join(items) + "\n\\end{thebibliography}")


def bib_database(doc: Document) -> str:
    """The `.bib` file: every Reference that carries a full `bibtex` record."""
    out = []
    for o in doc.objects.values():
        if o.type == "Reference" and o.props.get("bibtex"):
            out.append(str(o.props["bibtex"]).strip())
    return "\n\n".join(out)


# ── driver: run + dump the stages ────────────────────────────────────────────

def run_stages(doc: Document, bibkey: str = "DOC") -> dict:
    """Every stage's inspectable data, keyed by dump-filename stem. Stage 0 is the
    readarray formula array — the `.dat` (one formula per line) AND the
    `{title: index}` map — plus the citation list and the bibliography."""
    order, title_index = formula_array(doc)
    return {
        "00-formulas.dat": "\n".join(order),          # the readarray data file
        "00-formula-index": title_index,               # title → 1-based index
        "01-citations": citation_keys(doc),
        "02-bibliography": bibliography_block(doc),
        "02-bib-database": bib_database(doc),
    }


def dump_stages(stages: dict, out_dir: Path) -> list[Path]:
    """Write each stage to an inspectable file (`.json` for data maps, `.dat`/
    `.bib`/`.tex` for text). Returns the written paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, data in stages.items():
        if isinstance(data, (dict, list)):
            p = out_dir / f"{name}.json"
            p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            p = out_dir / (name if "." in name else f"{name}.bib" if "bib" in name
                           else f"{name}.tex")
            p.write_text(str(data), encoding="utf-8")
        written.append(p)
    return written


# ── stage 3: acronyms / glossary (from the named-concept layer) ──────────────

def glossary_block(records) -> str:
    """An `Acronyms` section as a `description` list (single-pass — no
    `makeglossaries`). `records` is `[(name, expansion), …]` from the concept
    layer; empty → empty string."""
    items = [(str(n).strip(), str(e).strip()) for n, e in records
             if str(n).strip() and str(e).strip()]
    if not items:
        return ""
    lines = ["\\section*{Acronyms}", "\\begin{description}"]
    for name, exp in items:
        lines.append(f"  \\item[{_bib_escape(name)}] {_bib_escape(exp)}")
    lines.append("\\end{description}")
    return "\n".join(lines)
