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

def _flatten(latex: str) -> str:
    """readarray splits entries on `\\par`, so each formula must be a SINGLE line —
    collapse internal whitespace/newlines to one space."""
    return re.sub(r"\s+", " ", latex.strip())


def formula_array(doc: Document) -> tuple[list[str], dict[str, int]]:
    """Return `(ordered distinct formula LaTeX, {object-title: 1-based index})`.

    Ordered by object title so the array is stable across builds; deduped by
    (flattened) content so an expression used many times shares ONE array slot.
    The index map is what the body resolver rewrites each `{{id||FO}}` into."""
    order: list[str] = []
    by_content: dict[str, int] = {}          # flattened latex → 1-based index
    title_index: dict[str, int] = {}
    objs = [o for o in doc.objects.values() if o.type in ("Formula", "Equation")]
    objs.sort(key=lambda o: o.id)
    for obj in objs:
        latex = _flatten(obj.props.get("latex") or "")
        if not latex:
            continue
        idx = by_content.get(latex)
        if idx is None:
            order.append(latex)
            idx = len(order)                 # 1-based
            by_content[latex] = idx
        title_index[obj.id] = idx
    return order, title_index


def formula_preamble(order: list[str], dat_name: str) -> str:
    """The preamble block: write the formula array to `<dat_name>` via
    `filecontents*`, load it with `readarray`, and define `\\Expr{<index>}`."""
    if not order:
        return ""
    body = "\n".join(order)
    return (
        "\\usepackage{filecontents}\n"
        f"\\begin{{filecontents*}}{{{dat_name}}}\n{body}\n\\end{{filecontents*}}\n"
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
        idx = title_index.get(title)
        if idx is None:
            return f"(?{title})"                      # unknown — readable, no braces
        if tpl in ("FO", "FREF"):
            return f"\\Expr{{{idx}}}"
        return f"\\Expr{{{idx}}}"
    return _MARKER.sub(sub, text)


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

def _bibitem(ref) -> str:
    p = ref.props
    key = str(p.get("citekey") or "ref").strip()
    if p.get("bibtex"):                              # a real BibTeX record present
        return ""                                    # → collected into a .bib instead
    author = str(p.get("author") or "").strip()
    year = str(p.get("year") or "").strip()
    title = str(p.get("titlefield") or p.get("title") or "").strip()
    body = " ".join(x for x in (author, f"({year})" if year else "", title) if x) \
        or str(p.get("raw_text") or "").strip() or key
    return f"\\bibitem{{{key}}} {body}"


def bibliography_block(doc: Document) -> str:
    """A `thebibliography` environment from the model's Reference objects (empty
    string when there are none). References carrying full `bibtex` are emitted to
    a `.bib` by `bib_database` instead; here we render the printed entries."""
    refs = [o for o in doc.objects.values() if o.type == "Reference"]
    refs.sort(key=lambda o: str(o.props.get("citekey") or ""))
    items = [b for b in (_bibitem(r) for r in refs) if b]
    if not items:
        return ""
    widest = max((str(r.props.get("citekey") or "") for r in refs), key=len, default="9")
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
