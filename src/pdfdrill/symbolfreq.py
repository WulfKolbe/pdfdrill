"""
277 — the frequency check: a rare spelling in a position a sibling dominates.

out/210 built the ARITY check: a turnstile-family relation carrying a sub- or
superscript cannot be right, because ⊢ and ⊨ join two expressions and are not
operators. It found 20 across the corpus, 11 of them in 2010.14265, where
MathPix drew the conditional-independence glyph ⫫ as ⊮.

Arity is a rule about ONE symbol family and needs the index to fire. The
frequency check needs neither: it asks whether a document, in one syntactic
position, spells the same thing two ways and overwhelmingly prefers one.

    X \\Perp_{P} Y          128 occurrences   the document's own spelling
    X \\nVdash_{P} Y          8
    X \\nvdash_{P} Y          3

THE POSITION KEY is the whole math fragment with the symbol replaced by a slot
and its operands generalised, NOT a window of characters either side:

    X \\Perp_{P} Y     ->  V§_{V}V
    X \\nVdash_{P} Y   ->  V§_{V}V      same position, so they are siblings

A first version keyed on a fixed character window. It missed every turnstile hit
(the window cut through `_{P}`) and flagged six set operators alternating around
a `\\boldsymbol` — inventing a false-positive class in place of the one it was
removing, which is the failure out/210 named and out/187 before it.

WHAT IS EXCLUDED, AND WHY EACH EXCLUSION IS A CLAIM
------------------------------------------------------------------------------
Frequency alone flags real mathematics. Three families are excluded because
alternating between them is what a correct document DOES:

  STYLING     `\\mathbf` vs `\\boldsymbol`, `\\mathrm` vs `\\text` — two spellings
              of a typeface, both legitimate, and a document mixing them is
              untidy rather than wrong.
  NEGATION    `\\in`/`\\notin`, `\\subset`/`\\not\\subset`, `\\leq`/`\\nleq` — a
              negation is a DIFFERENT operator that shares a position with its
              positive by design.
  DELIMITERS  `\\mid`, `\\cup`, `\\cap`, `\\setminus` and friends genuinely
              alternate in set expressions.

Each exclusion narrows what the check can find. That is the trade the arity
check does not have to make, and it is why the two are reported together rather
than one replacing the other.
"""
from __future__ import annotations

import collections
import re
from typing import Any, Iterable

#: Inline (`\( … \)`) and display (`\[ … \]`, `$$ … $$`) math.
_MATH = re.compile(r"\\\((.+?)\\\)|\\\[(.+?)\\\]|\$\$(.+?)\$\$", re.S)
_CMD = re.compile(r"\\[A-Za-z]+")

#: Typeface macros — alternating between them is untidy, not wrong.
_STYLING = {
    "\\mathbf", "\\boldsymbol", "\\mathrm", "\\text", "\\textrm", "\\mathit",
    "\\mathsf", "\\mathtt", "\\mathnormal", "\\bm", "\\operatorname",
    "\\textbf", "\\textit", "\\emph", "\\rm", "\\bf", "\\it",
}

#: Set/logic connectives that legitimately alternate in one position.
_CONNECTIVE = {
    "\\mid", "\\cup", "\\cap", "\\setminus", "\\backslash", "\\times",
    "\\oplus", "\\otimes", "\\wedge", "\\vee", "\\sqcup", "\\uplus",
    "\\to", "\\rightarrow", "\\leftarrow", "\\Rightarrow", "\\Leftarrow",
    "\\mapsto", "\\hookrightarrow", "\\leftrightarrow", "\\Leftrightarrow",
}


def _is_negation_pair(a: str, b: str) -> bool:
    """True when one spelling is the negation of the other — `\\in`/`\\notin`,
    `\\vdash`/`\\nvdash`, `\\leq`/`\\nleq`. A negation shares its position with
    the positive BY DESIGN, so the pair is never a substitution."""
    x, y = sorted((a.lstrip("\\").lower(), b.lstrip("\\").lower()), key=len)
    return y in (f"n{x}", f"not{x}", f"n{x}q", f"{x}not")


#: One LaTeX "operand": a braced group, a `\{ … \}` set, a command, or a char.
_TOKEN = re.compile(r"\\[A-Za-z]+|\\[{}]|\{[^{}]*\}|\S")


def _generalise(tok: str) -> str:
    """A token as its SHAPE: variables collapse, digits collapse, commands stay."""
    if re.fullmatch(r"[A-Za-z]", tok):
        return "V"
    if re.fullmatch(r"\d+", tok):
        return "D"
    tok = re.sub(r"(?<![A-Za-z\\])[A-Za-z](?![A-Za-z])", "V", tok)
    return re.sub(r"\d+", "D", tok)


def norm_shape(fragment: str, start: int, end: int, window: int = 1) -> str:
    """The symbol's LOCAL position: one operand either side, plus whatever
    sub/superscript is attached to the symbol itself.

    Token-local, not whole-fragment. The first version keyed on a fixed
    character window and missed every hit (it cut through `_{P}`); the second
    keyed on the entire fragment and matched only 5 of 11, because
    ``X \\nVdash_{P} Y \\mid \\boldsymbol{S}`` and ``X \\Perp_{P} Y`` are the same
    RELATIONAL position and different strings. What makes them siblings is the
    operand either side, and nothing further out.
    """
    toks = [(m.group(0), m.start(), m.end()) for m in _TOKEN.finditer(fragment)]
    idx = next((i for i, (_t, a, b) in enumerate(toks) if a <= start < b), None)
    if idx is None:
        return "§"
    attach = ""
    j = idx + 1
    while j < len(toks) and toks[j][0] in ("_", "^"):
        attach += toks[j][0] + (_generalise(toks[j + 1][0]) if j + 1 < len(toks) else "")
        j += 2
    left = "".join(_generalise(t) for t, _a, _b in toks[max(0, idx - window):idx])
    right = "".join(_generalise(t) for t, _a, _b in toks[j:j + window])
    return f"{left}§{attach}{right}"


def occurrences(lines: Iterable[dict]) -> list[dict]:
    """Every `\\command` inside a math fragment, with its position shape.

    Lines are de-duplicated on TEXT first. MathPix repeats the same string
    under `text` and `diagram`/`list_item`, so counting each container inflates
    every spelling by its container count rather than its use count —
    2010.14265 carries 128 raw `\\Perp` that way. The key was `(type, text)`,
    which is exactly the key that does NOT collapse them, beside a docstring
    saying it did.
    """
    out: list[dict] = []
    seen: set = set()
    for ln in lines:
        text = ln.get("text_display") or ln.get("text") or ""
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        for m in _MATH.finditer(text):
            frag = next(g for g in m.groups() if g is not None)
            for c in _CMD.finditer(frag):
                out.append({
                    "cmd": c.group(0),
                    "shape": norm_shape(frag, c.start(), c.end()),
                    "page": ln.get("_page") or ln.get("page"),
                    "fragment": frag.strip()[:120],
                    "line_type": ln.get("type"),
                })
    return out


def flags(occ: list[dict], *, ratio: int = 4, min_common: int = 5) -> list[dict]:
    """Rare spellings sharing a position with a spelling that dominates it.

    `ratio` — the common sibling must outnumber the rare one by this factor.
    `min_common` — and must itself be frequent enough to be the document's
    settled choice rather than the other half of a coin toss.
    """
    by_shape: dict = collections.defaultdict(collections.Counter)
    samples: dict = collections.defaultdict(list)
    for o in occ:
        by_shape[o["shape"]][o["cmd"]] += 1
        samples[(o["shape"], o["cmd"])].append(o)

    out: list[dict] = []
    for shape, counts in by_shape.items():
        if len(counts) < 2:
            continue
        common, n_common = counts.most_common(1)[0]
        if n_common < min_common or common in _STYLING:
            continue
        for cmd, n in counts.items():
            if cmd == common or n * ratio > n_common:
                continue
            if cmd in _STYLING or (cmd in _CONNECTIVE and common in _CONNECTIVE):
                continue
            if _is_negation_pair(cmd, common):
                continue
            ex = samples[(shape, cmd)][0]
            out.append({
                "rare": cmd, "rare_count": n,
                "common": common, "common_count": n_common,
                "shape": shape, "page": ex["page"], "example": ex["fragment"],
                # A position carrying a sub/superscript is a SPECIFIC relational
                # slot — `V§_{V}V` is "a relation between two variables indexed
                # by a third". A position without one is `V§V`, "two things with
                # something between them", which every binary operator in the
                # document shares, so unrelated operators collide there.
                #
                # Both are reported. Only the first is a defect count; the
                # second is a population to look at, which is the distinction
                # out/210 had to make about its own 614.
                "tier": "specific" if ("_" in shape or "^" in shape) else "generic",
            })
    out.sort(key=lambda r: (-r["rare_count"], r["rare"]))
    return out


def check(lines: Iterable[dict], **kw) -> list[dict]:
    """Convenience: occurrences -> flags."""
    return flags(occurrences(lines), **kw)


def specific(rows: Iterable[dict]) -> list[dict]:
    """The high-confidence tier: positions carrying an attachment."""
    return [r for r in rows if r.get("tier") == "specific"]

# ===========================================================================
# WHAT THE CORPUS SAID — and it is a negative result.
#
#   documents scanned                              1,351
#   specific tier (position carries an index)     37,505 in 406 documents
#   generic tier                                 155,102 in 687 documents
#   arity (out/210 middle tier, re-measured)          66 in   8 documents
#
# 37,505 is not a defect count. The examples are ordinary mathematics:
#
#   \circ   x94 vs \prime x628      \lambda x49 vs \alpha x208
#   \pi     x59 vs \prime x501      \alpha  x38 vs \kappa x733
#
# A subscript slot holds ANY index, so "a rare spelling in a position a sibling
# dominates" describes mathematical variety, not substitution. By (class of
# common, class of rare): greek/greek 15,017 · other/greek 8,909 ·
# other/other 7,849 · greek/other 3,299 · relation/relation 130.
#
# 2010.14265 fits because it has ONE overwhelmingly dominant relation
# (\Perp x51) and the substitutions are rare spellings of exactly that. That is
# a property of the document, not of the method.
#
# Gating on relation-vs-relation leaves 130 occurrences in 24 documents, and
# most of those are still legitimate — `\geq x14 vs \leq x58`,
# `\in x14 vs \geq x114`. The 12 real ones in 2010.14265 survive, but a gate
# that keeps 12 signal in 130 is a POPULATION TO READ, not a check to run.
#
# So this module is not registered as a command and `flags()` is not a defect
# list. out/210 made the same distinction about its own 614, and the reason to
# make it again is that the first version of this check DID invent a
# false-positive class — twice, once per position key — while looking like it
# worked on the document it was built against.
# ===========================================================================

#: Binary relation symbols. Substitutions of the kind out/210 found land here:
#: MathPix reaching for one relation glyph to draw another.
RELATIONS = frozenset("""
Perp perp vdash Vdash vDash VDash nvdash nVdash nvDash nVDash models
equiv sim simeq approx cong leq geq subset supset subseteq supseteq
in ni prec succ preceq succeq parallel bot measuredangle asymp doteq
propto ll gg mid nmid vartriangleleft vartriangleright
""".split())


def relation_pairs(rows: Iterable[dict]) -> list[dict]:
    """The narrowest reportable tier: both spellings are relations.

    130 occurrences in 24 documents corpus-wide. Reviewable by hand, which is
    the most this method earns — see the note above.
    """
    def rel(c: str) -> bool:
        return c.lstrip("\\") in RELATIONS
    return [r for r in rows if rel(r["rare"]) and rel(r["common"])]
