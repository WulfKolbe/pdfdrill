"""
SO.QUANT.EXTRACT — typed quantity extraction over the docmodel (L6 quantity
sublayer, S1.2). Pure over the docmodel exactly like `concepts.concept_records`
(the reference implementation of the record-producer shape): no graph, no
sidecar, records only.

`quantity_records(doc)` walks Formula/Equation objects (`props['latex']`) and
prose (`_PROSE_FIELD`, same map as concepts), emitting
    {value, unit, dimension, raw, obj_id, kind}
with kind ∈ {number, ratio, money, count, named_metric, derivation} plus
kind-specific extras: `approx` (a `\\sim`/"approximately" hedge), `var`
(`k=10`), `qualifier` ("max."), `name`/`param` (named metrics like `R@P90`),
`payload` ({lhs_terms, op, rhs} for arithmetic derivations), `noun` (counts).

Honesty rules (verified by the 2303.11082 fixtures in tests/test_quantities.py):
whole-string typing for LaTeX — a token that is not entirely a quantity shape
(`\\cdot`, `(s,r,o)`, `FT_{vocab}`, `BERT_{large}`) yields NO record, never a
guess; prose extraction fires only when a unit or a `units.COUNT_NOUNS` noun is
attached (bare prose numbers are not quantities).

S1.4: when an object already carries `props['math']` (the `mathir` SymPy srepr),
the tree path is preferred for numeric/derivation extraction; the import is
guarded exactly like `cmd_mathir` — a missing `[math]` extra silently uses the
stdlib lexer, never a hard dep.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from . import units as U
from .registry import FnSpec, register_fn

# same prose-field map as concepts.py (kept local; both are two-line tables)
_PROSE_FIELD = {"Paragraph": "text", "Abstract": "text", "ListItem": "content",
                "Footnote": "content", "Sidenote": "content"}

# one numeric token: comma-grouped int, decimal, or plain int
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d+"
_NUM_RE = re.compile(_NUM)

_APPROX_LATEX = re.compile(r"\\(?:sim|approx)\s*")
_APPROX_PROSE = re.compile(r"(?i)\b(approximately|about|roughly|circa|around)\s+$")


def _to_number(tok: str) -> "int | float":
    tok = tok.replace(",", "")
    return float(tok) if "." in tok else int(tok)


def _rec(kind: str, value, raw: str, unit: Optional[str] = None,
         **extra) -> dict[str, Any]:
    return {"kind": kind, "value": value, "unit": unit,
            "dimension": U.dimension(unit) if unit else None,
            "raw": raw, **{k: v for k, v in extra.items() if v is not None}}


# --------------------------------------------------------------------------- #
#  LaTeX path — whole-string typing (a partial match is NOT a quantity)
# --------------------------------------------------------------------------- #

_DERIV_RE = re.compile(
    rf"^\s*(?P<lhs>(?:{_NUM})(?:\s*(?:\\cdot|\+|-|/)\s*(?:{_NUM}))+)\s*"
    rf"=\s*(?P<rhs>{_NUM})\s*$")
_OPS = {"\\cdot": "mul", "+": "add", "-": "sub", "/": "div"}
_METRIC_RE = re.compile(r"^\s*(?P<name>[A-Za-z]+@[A-Za-z]+)(?P<param>\d+(?:\.\d+)?)\s*$")
_ASSIGN_RE = re.compile(rf"^\s*(?P<var>[A-Za-z][A-Za-z0-9_]{{0,15}})\s*=\s*(?P<num>{_NUM})\s*$")
_MONEY_RE = re.compile(rf"^\s*(?P<ap>\\(?:sim|approx)\s*)?\\\$\s*(?P<num>{_NUM})\s*$")
_RATIO_RE = re.compile(rf"^\s*(?P<ap>\\(?:sim|approx)\s*)?(?P<num>{_NUM})\s*\\%\s*$")
_QUAL_RE = re.compile(rf"^\s*(?P<q>max|min)\.?\s+(?P<num>{_NUM})\s*$", re.IGNORECASE)
_BARE_RE = re.compile(rf"^\s*(?P<ap>\\(?:sim|approx)\s*)?(?P<num>{_NUM})\s*$")


def parse_latex_quantities(latex: str) -> list[dict]:
    """Typed quantity record(s) for one Formula/Equation LaTeX body. Whole-string
    typing: anything that is not entirely a quantity shape yields []."""
    s = (latex or "").strip()
    if not s or not any(c.isdigit() for c in s):
        return []

    m = _DERIV_RE.match(s)
    if m:
        lhs = m.group("lhs")
        ops = {_OPS[o] for o in re.findall(r"\\cdot|\+|-|/", lhs)}
        terms = [_to_number(t) for t in _NUM_RE.findall(lhs)]
        if len(ops) == 1 and len(terms) >= 2:            # one operator chain
            rhs = _to_number(m.group("rhs"))
            return [_rec("derivation", rhs, s,
                         payload={"lhs_terms": terms, "op": ops.pop(), "rhs": rhs})]

    m = _METRIC_RE.match(s)
    if m:
        return [_rec("named_metric", _to_number(m.group("param")), s,
                     name=m.group("name"), param=_to_number(m.group("param")))]

    m = _MONEY_RE.match(s)
    if m:
        return [_rec("money", _to_number(m.group("num")), s, unit="$",
                     approx=True if m.group("ap") else None)]

    m = _RATIO_RE.match(s)
    if m:
        return [_rec("ratio", _to_number(m.group("num")), s, unit="%",
                     approx=True if m.group("ap") else None)]

    m = _ASSIGN_RE.match(s)
    if m:
        return [_rec("number", _to_number(m.group("num")), s, var=m.group("var"))]

    m = _QUAL_RE.match(s)
    if m:
        return [_rec("number", _to_number(m.group("num")), s,
                     qualifier=m.group("q").lower())]

    m = _BARE_RE.match(s)
    if m:
        return [_rec("number", _to_number(m.group("num")), s,
                     approx=True if m.group("ap") else None)]
    return []


# --------------------------------------------------------------------------- #
#  Prose path — fire only on unit- or count-noun-attached numbers
# --------------------------------------------------------------------------- #

_P_MONEY = re.compile(rf"\$\s?(?P<num>{_NUM})")
_P_RATIO = re.compile(rf"(?P<num>{_NUM})\s?%")
# a count: number + optionally ONE lowercase adjective + a whitelisted noun
_P_COUNT = re.compile(rf"(?P<num>{_NUM})(?:\s+[a-z]+)?\s+(?P<noun>[a-z]+)\b")
# unambiguous time/data suffixes only (bare "s"/"B" in prose is too ambiguous)
_P_UNIT = re.compile(rf"\b(?P<num>{_NUM})\s?(?P<unit>ms|min|h|KB|MB|GB)\b")


def _prose_approx(text: str, start: int) -> Optional[bool]:
    return True if _APPROX_PROSE.search(text[:start]) else None


def parse_text_quantities(text: str) -> list[dict]:
    """Quantities in PROSE — only unit-attached (money/%/time/data) or
    count-noun-attached numbers; a bare number in prose is NOT extracted."""
    out: list[dict] = []
    taken: list[tuple[int, int]] = []            # spans already claimed

    def claim(a: int, b: int) -> bool:
        if any(not (b <= x or a >= y) for x, y in taken):
            return False
        taken.append((a, b))
        return True

    for m in _P_MONEY.finditer(text):
        if claim(*m.span()):
            out.append(_rec("money", _to_number(m.group("num")), m.group(0),
                            unit="$", approx=_prose_approx(text, m.start()),
                            span=list(m.span())))
    for m in _P_RATIO.finditer(text):
        if claim(*m.span()):
            out.append(_rec("ratio", _to_number(m.group("num")), m.group(0),
                            unit="%", approx=_prose_approx(text, m.start()),
                            span=list(m.span())))
    for m in _P_UNIT.finditer(text):
        if claim(*m.span()):
            out.append(_rec("number", _to_number(m.group("num")), m.group(0),
                            unit=m.group("unit"), span=list(m.span())))
    for m in _P_COUNT.finditer(text):
        if m.group("noun") in U.COUNT_NOUNS and claim(*m.span()):
            out.append(_rec("count", _to_number(m.group("num")), m.group(0),
                            noun=m.group("noun"), span=list(m.span())))
    out.sort(key=lambda r: r.get("span", [0])[0])
    return out


# --------------------------------------------------------------------------- #
#  SymPy upgrade path (S1.4) — guarded exactly like cmd_mathir
# --------------------------------------------------------------------------- #

def _from_math_props(math: dict, raw: str) -> Optional[list[dict]]:
    """Prefer the mathir SymPy tree when present: an Equality whose lhs is a
    product/sum of numbers and rhs a number is a derivation; a bare Number is a
    number. Returns None to fall back to the stdlib lexer."""
    srepr = (math or {}).get("srepr") or ""
    if not srepr:
        return None
    try:
        import sympy  # noqa: F401 — the [math] extra; missing → lexer path
        expr = sympy.sympify(srepr)
    except Exception:
        return None
    try:
        if expr.is_Number:
            v = float(expr)
            return [_rec("number", int(v) if v.is_integer() else v, raw,
                         source="sympy")]
        import sympy as sp
        if isinstance(expr, sp.Equality):
            lhs, rhs = expr.lhs, expr.rhs
            if rhs.is_Number and isinstance(lhs, (sp.Mul, sp.Add)) and \
                    all(a.is_Number for a in lhs.args):
                terms = [float(a) for a in lhs.args]
                terms = [int(t) if t.is_integer() else t for t in terms]
                rv = float(rhs)
                rv = int(rv) if rv.is_integer() else rv
                op = "mul" if isinstance(lhs, sp.Mul) else "add"
                return [_rec("derivation", rv, raw, source="sympy",
                             payload={"lhs_terms": terms, "op": op, "rhs": rv})]
    except Exception:
        return None
    return None


# --------------------------------------------------------------------------- #
#  The doc walker (the SO.QUANT.EXTRACT entry point)
# --------------------------------------------------------------------------- #

def quantity_records(doc) -> list[dict]:
    """Typed quantity records over the whole docmodel, each tagged with its
    source `obj_id`. Formula/Equation LaTeX first (tree path when `props['math']`
    is present), then unit/count-attached prose numbers."""
    records: list[dict] = []
    objs = sorted(doc.objects.values(),
                  key=lambda o: o.props.get("flow_index") or 0)
    for o in objs:
        if o.type in ("Formula", "Equation"):
            raw = o.props.get("latex") or ""
            recs = None
            if o.props.get("math"):
                recs = _from_math_props(o.props["math"], raw)
            if recs is None:
                recs = parse_latex_quantities(raw)
        else:
            field = _PROSE_FIELD.get(o.type)
            if not field:
                continue
            text = o.props.get(field) or ""
            recs = parse_text_quantities(text) if isinstance(text, str) else []
        for r in recs:
            r["obj_id"] = o.id
            records.append(r)
    return records


register_fn(FnSpec(
    fid="SO.QUANT.EXTRACT",
    description="Typed quantity extraction over the docmodel: numbers/ratios/"
                "money/counts/named metrics/derivations from Formula/Equation "
                "LaTeX and unit-attached prose.",
    version="1",
    params={"count_nouns": sorted(U.COUNT_NOUNS)},
    laws=("whole-string-typing", "no-guess"),
), quantity_records)
