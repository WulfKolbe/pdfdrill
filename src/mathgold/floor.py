r"""The floor — what the born-digital text layer alone recovers of an equation.

Read the characters inside the equation's rectangle, in reading order, and
join them left to right. No scripts, no fractions, no structure. That is the
number every recogniser has to beat, and the baseline M2.x is measured against.

Three things here are decisions, not facts, and each is stated where it is made:

1. COORDINATES. `props["region"]` is in MathPix page PIXELS, top-left origin;
   pdfplumber chars are in PDF POINTS, also top-left. `meta["pages"]` carries
   the pixel dimensions, so the scale is exact — not estimated from a DPI guess.

2. VOCABULARY. Gold labels are LaTeX tokens (`\times`); floor labels are
   codepoints (`×`). `LATEX_UNICODE` bridges them, and every entry was chosen
   by MEASURING what pdfplumber actually emits for that construct in the gold
   corpus — `\phi` maps to U+03D5 (the phi SYMBOL) and `\epsilon` to U+03F5
   (LUNATE) because that is what comes out, not what a chart would suggest.
   A command with no single emitted codepoint (`\dots`, `\frac`, `\coloneq`)
   is NOT given a plausible one. It stays itself, mismatches, and is counted
   by `unmapped_commands` so the vocabulary gap stays separable from the
   extraction gap. Rule 5.

3. CORRESPONDENCE. LgEval compares two graphs over the SAME primitive set —
   node ids are the correspondence. Gold symbols and PDF characters have no
   correspondence a priori, so `align_labels` establishes one by sequence
   alignment and every LgEval number is conditional on it. Unmatched nodes are
   kept, not dropped: LgEval scores a node only one file declares as `ABSENT`
   (verified — a 3-vs-2 pair reports `nNodes,3`), and dropping them would
   delete the floor's largest error class and improve the score by hiding it.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from .slt import RIGHT, Node, SLT, Unresolved

Box = tuple[float, float, float, float]          # x0, top, x1, bottom (points)


# --------------------------------------------------------------------- geometry
def region_box(region: dict, page_px: tuple[float, float],
               page_pt: tuple[float, float]) -> Box:
    """A MathPix pixel rectangle as a PDF-point rectangle, top-left origin."""
    px_w, px_h = page_px
    pt_w, pt_h = page_pt
    sx, sy = pt_w / float(px_w), pt_h / float(px_h)
    x = float(region["top_left_x"])
    y = float(region["top_left_y"])
    return (x * sx, y * sy,
            (x + float(region["width"])) * sx,
            (y + float(region["height"])) * sy)


def chars_in_box(chars: Iterable[dict], box: Box, pad: float = 1.0) -> list[dict]:
    x0, top, x1, bottom = box
    return [c for c in chars
            if c["x0"] >= x0 - pad and c["x1"] <= x1 + pad
            and c["top"] >= top - pad and c["bottom"] <= bottom + pad]


def reading_order(chars: list[dict], row_factor: float = 0.8) -> list[dict]:
    """Characters in reading order: rows top to bottom, left to right within.

    Rows are found by clustering on the vertical CENTRE with a tolerance scaled
    to the dominant character height, not on `top`. Keying on `top` puts every
    subscript in a row of its own, and the flat reading comes out as `J=y...x`
    with all the scripts swept to the end — a sorting bug reported as a
    recognition floor.
    """
    if not chars:
        return []
    heights = sorted(float(c["bottom"]) - float(c["top"]) for c in chars)
    line_h = heights[len(heights) // 2] or 1.0
    tol = line_h * row_factor

    def centre(c):
        return (float(c["top"]) + float(c["bottom"])) / 2.0

    rows: list[list[dict]] = []
    for c in sorted(chars, key=centre):
        if rows and abs(centre(c) - centre(rows[-1][0])) <= tol:
            rows[-1].append(c)
        else:
            rows.append([c])
    out: list[dict] = []
    for row in rows:
        out.extend(sorted(row, key=lambda c: float(c["x0"])))
    return out


def chars_to_slt(chars: list[dict]) -> SLT:
    """One node per character, joined left to right. This IS the floor."""
    slt = SLT()
    prev: Optional[str] = None
    for i, c in enumerate(reading_order(list(chars))):
        nid = f"c{i}"
        slt.nodes.append(Node(nid, c["text"]))
        if prev is not None:
            from .slt import Edge
            slt.edges.append(Edge(prev, nid, RIGHT))
        prev = nid
    return slt


# ------------------------------------------------------------------ vocabulary
# Every entry verified against pdfplumber output over the gold corpus.
LATEX_UNICODE: dict[str, str] = {
    r"\hat": "ˆ",            # U+02C6, emitted as its own character
    r"\vec": "⃗",       # U+20D7 combining right arrow above
    r"\bar": "̄",
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
    r"\epsilon": "ϵ",        # U+03F5 LUNATE — what the layer emits, not U+03B5
    r"\zeta": "ζ", r"\eta": "η", r"\theta": "θ", r"\kappa": "κ",
    r"\lambda": "λ", r"\mu": "μ", r"\nu": "ν", r"\xi": "ξ",
    r"\pi": "π", r"\rho": "ρ", r"\sigma": "σ", r"\tau": "τ",
    r"\phi": "ϕ",            # U+03D5 PHI SYMBOL
    r"\chi": "χ", r"\psi": "ψ", r"\omega": "ω",
    r"\Gamma": "Γ", r"\Delta": "Δ", r"\Theta": "Θ", r"\Lambda": "Λ",
    r"\Sigma": "Σ", r"\Phi": "Φ", r"\Psi": "Ψ", r"\Omega": "Ω",
    r"\partial": "∂", r"\nabla": "∇", r"\hbar": "ℏ", r"\infty": "∞",
    r"\otimes": "⊗", r"\times": "×", r"\cdot": "·", r"\pm": "±",
    r"\in": "∈", r"\forall": "∀", r"\exists": "∃",
    r"\equiv": "≡", r"\geq": "≥", r"\leq": "≤", r"\neq": "≠",
    r"\approx": "≈", r"\sim": "∼", r"\propto": "∝",
    r"\rightarrow": "→", r"\to": "→", r"\leftarrow": "←",
    r"\uparrow": "↑", r"\downarrow": "↓", r"\Leftrightarrow": "⇔",
    r"\langle": "⟨", r"\rangle": "⟩", r"\mid": "|",
    r"\dagger": "†", r"\prime": "′", r"\sqrt": "√",
    r"\{": "{", r"\}": "}",
}

# Same glyph, two spellings. Applied to BOTH sides so the canonical form is
# one thing: LaTeX source writes ASCII `-`, the text layer emits U+2212.
_UNIFY: dict[str, str] = {"−": "-", "′": "'", "ˆ": "ˆ"}

# Typeface selectors and text wrappers. They put no ink of their own on the
# page, so no reader of the PDF could recover them. Reported as `no_ink`
# rather than counted against the floor or quietly deleted.
NO_INK = {r"\mathcal", r"\mathbf", r"\mathbb", r"\mathrm", r"\mathit",
          r"\mathsf", r"\mathfrak", r"\text", r"\textrm", r"\textbf",
          r"\operatorname", r"\boldsymbol"}


def to_symbol(label: Any) -> Any:
    """Canonical form of a node label, or the label unchanged if unmapped."""
    if isinstance(label, Unresolved):
        return label
    text = str(label)
    if text in LATEX_UNICODE:
        text = LATEX_UNICODE[text]
    return _UNIFY.get(text, text)


def unmapped_commands(slt: SLT) -> set[str]:
    """LaTeX commands in this graph that the vocabulary does not bridge."""
    out = set()
    for n in slt.nodes:
        if isinstance(n.label, Unresolved):
            continue
        text = str(n.label)
        if text.startswith("\\") and text not in LATEX_UNICODE and text not in NO_INK:
            out.add(text)
    return out


# ------------------------------------------------------------------- alignment
def align_labels(gold: list[Any], floor: list[Any]) -> list[tuple[int, int]]:
    """Pair gold positions with floor positions by sequence alignment.

    Levenshtein with a backtrace: a spurious floor character (a combining
    accent, a `(cid:18)`) is absorbed as an insertion instead of shifting
    every later symbol into a mismatch.
    """
    n, m = len(gold), len(floor)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        d[i][0] = i
    for j in range(1, m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            same = gold[i - 1] == floor[j - 1] and not isinstance(gold[i - 1], Unresolved)
            d[i][j] = min(d[i - 1][j] + 1,
                          d[i][j - 1] + 1,
                          d[i - 1][j - 1] + (0 if same else 1))
    pairs: list[tuple[int, int]] = []
    i, j = n, m
    while i > 0 and j > 0:
        same = gold[i - 1] == floor[j - 1] and not isinstance(gold[i - 1], Unresolved)
        if same and d[i][j] == d[i - 1][j - 1]:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif d[i][j] == d[i - 1][j - 1] + 1 and not same:
            i, j = i - 1, j - 1          # substitution: NOT a correspondence
        elif d[i][j] == d[i - 1][j] + 1:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


# ------------------------------------------------------------------ lg emission
def _lg(nodes: list[tuple[str, Any]], edges: list[tuple[str, str, str]],
        weight: float = 1.0) -> str:
    from .slt import _lab_out
    out = ["# label graph emitted by pdfdrill mathgold floor"]
    for nid, label in nodes:
        out.append(f"N, {nid}, {_lab_out(label)}, {weight}")
    for p, c, rel in edges:
        out.append(f"E, {p}, {c}, {rel}, {weight}")
    return "\n".join(out) + "\n"


def lg_pair(gold: SLT, floor: SLT) -> tuple[str, str, dict]:
    """Both graphs as `.lg`, over one primitive set established by alignment.

    Matched nodes share an id — that shared id is the whole basis of the
    comparison. Unmatched nodes keep disjoint ids so LgEval reports them
    `ABSENT` on the other side rather than pairing them with a symbol they
    have nothing to do with.
    """
    g_labels = [to_symbol(n.label) for n in gold.nodes]
    f_labels = [to_symbol(n.label) for n in floor.nodes]
    pairs = align_labels(g_labels, f_labels)

    g_id, f_id = {}, {}
    for k, (gi, fi) in enumerate(pairs):
        shared = f"s{k}"
        g_id[gold.nodes[gi].id] = shared
        f_id[floor.nodes[fi].id] = shared
    for n in gold.nodes:
        g_id.setdefault(n.id, f"g_{n.id}")
    for n in floor.nodes:
        f_id.setdefault(n.id, f"f_{n.id}")

    g_nodes = [(g_id[n.id], to_symbol(n.label)) for n in gold.nodes]
    f_nodes = [(f_id[n.id], to_symbol(n.label)) for n in floor.nodes]
    g_edges = [(g_id[e.parent], g_id[e.child], e.relation) for e in gold.edges]
    f_edges = [(f_id[e.parent], f_id[e.child], e.relation) for e in floor.edges]

    matched = {gold.nodes[gi].id for gi, _ in pairs}
    no_ink = sum(1 for n in gold.nodes
                 if n.id not in matched and str(n.label) in NO_INK)
    stats = {
        "matched": len(pairs),
        "gold_only": len(gold.nodes) - len(pairs) - no_ink,
        "floor_only": len(floor.nodes) - len(pairs),
        "no_ink": no_ink,
        "gold_nodes": len(gold.nodes),
        "floor_nodes": len(floor.nodes),
        "gold_edges": len(gold.edges),
        "unmapped": sorted(unmapped_commands(gold)),
    }
    return _lg(g_nodes, g_edges), _lg(f_nodes, f_edges), stats
