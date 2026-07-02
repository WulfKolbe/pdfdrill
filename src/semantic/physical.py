"""
PHY.* — physical/structural constraints over quantity records (S3.2).

Five live checks + two declared stubs, each a small pure function returning the
same three-valued shape as VER.EQ.RECOMPUTE: {'ok': True|False|None, 'detail'}.
ok=None = out of this check's scope / uncheckable — the honest state, never a
guess.

  PHY.BOUNDS    a ratio lies in [0,1] (or [0,100] with the % unit); a count is a
                non-negative integer; money is ≥ 0.
  PHY.CONVERT   two money statements CLAIMED equal must convert consistently
                (units.convert; dimension mismatch → None).
  PHY.CONSERVE  a declared total equals the sum/product of its parts.
  PHY.MONO      an (P, R@P) series: recall non-increasing as precision rises.
  PHY.UNCERT    a quantity derived from an approx parent must itself carry
                approx=True — propagation, not assertion.

  PHY.CAUSE, PHY.FRAME — REGISTERED with laws=() and an impl returning
  {'status': 'not_implemented'}: declared, not faked. They wait for a physics
  corpus (first exercise target: drill 2302.07629 per plan v2 §5 and reconcile
  names there).
"""
from __future__ import annotations

from typing import Optional

from . import units as U
from .registry import FnSpec, register_fn

_TOL = 1e-9


def check_bounds(qrec: dict) -> dict:
    """PHY.BOUNDS: ratio ∈ [0,1] (bare) / [0,100] (%); count ∈ ℕ; money ≥ 0."""
    kind, v = (qrec or {}).get("kind"), (qrec or {}).get("value")
    if kind == "ratio":
        hi = 100 if qrec.get("unit") in ("%", "‰") else 1
        hi = 1000 if qrec.get("unit") == "‰" else hi
        ok = v is not None and 0 <= v <= hi
        return {"ok": bool(ok), "detail": f"ratio {v} within [0,{hi}]" if ok
                else f"ratio {v} outside [0,{hi}]"}
    if kind == "count":
        ok = v is not None and float(v) >= 0 and float(v) == int(v)
        return {"ok": bool(ok), "detail": f"count {v} is a non-negative int" if ok
                else f"count {v} is not a non-negative integer"}
    if kind == "money":
        ok = v is not None and v >= 0
        return {"ok": bool(ok), "detail": f"money {v} ≥ 0" if ok
                else f"money {v} is negative"}
    return {"ok": None, "detail": f"kind {kind!r} out of PHY.BOUNDS scope"}


def check_convert_pair(a: dict, b: dict) -> dict:
    """PHY.CONVERT: two quantities claimed EQUAL must agree after unit
    conversion. None when the units don't share a dimension (uncheckable)."""
    ua, ub = (a or {}).get("unit"), (b or {}).get("unit")
    va, vb = (a or {}).get("value"), (b or {}).get("value")
    if va is None or vb is None:
        return {"ok": None, "detail": "missing value"}
    conv = U.convert(va, ua or "", ub or "")
    if conv is None:
        return {"ok": None, "detail": f"units {ua!r}/{ub!r} not convertible"}
    ok = abs(conv - vb) <= max(_TOL, 0.005 * max(abs(vb), 1.0))
    return {"ok": bool(ok),
            "detail": f"{va} {ua} = {conv:g} {ub} vs stated {vb} {ub}"
                      + ("" if ok else " — INCONSISTENT")}


def check_conserve(rec: dict) -> dict:
    """PHY.CONSERVE: total == sum/product of parts as declared (op: add|mul)."""
    total, parts = (rec or {}).get("total"), list((rec or {}).get("parts") or ())
    op = (rec or {}).get("op", "add")
    if total is None or len(parts) < 2:
        return {"ok": None, "detail": "needs a total and ≥2 parts"}
    acc = 1.0 if op == "mul" else 0.0
    for p in parts:
        acc = acc * float(p) if op == "mul" else acc + float(p)
    ok = abs(acc - float(total)) <= max(_TOL, 0.005 * max(abs(total), 1.0))
    return {"ok": bool(ok),
            "detail": f"{op}(parts) = {acc:g} vs total {total}"
                      + ("" if ok else " — NOT CONSERVED")}


def check_mono(series: list) -> dict:
    """PHY.MONO: an (precision, recall@precision) series — R non-increasing in
    P. None with fewer than 2 points."""
    pts = sorted((float(p), float(r)) for p, r in (series or ()))
    if len(pts) < 2:
        return {"ok": None, "detail": "fewer than 2 points"}
    for (p1, r1), (p2, r2) in zip(pts, pts[1:]):
        if r2 > r1 + _TOL:
            return {"ok": False,
                    "detail": f"R@P rises {r1}→{r2} as P {p1}→{p2} — NOT monotone"}
    return {"ok": True, "detail": f"R non-increasing over {len(pts)} points"}


def check_uncert(qrec: dict, parents: Optional[list] = None) -> dict:
    """PHY.UNCERT: a quantity derived from an approx parent must carry
    approx=True itself — uncertainty propagates, it is never silently dropped."""
    parents = parents or []
    if not any(p.get("approx") for p in parents):
        return {"ok": True, "detail": "no approx parent — nothing to propagate"}
    ok = bool((qrec or {}).get("approx"))
    return {"ok": ok, "detail": "approx propagated" if ok
            else "approx parent but derived quantity lacks approx=True"}


def _not_implemented(*_a, **_k) -> dict:
    return {"status": "not_implemented"}


for _spec, _impl in [
    (FnSpec("PHY.BOUNDS", "Ratio in [0,1]/[0,100]; count a non-negative int; "
            "money ≥ 0.", "1", laws=("three-valued",)), check_bounds),
    (FnSpec("PHY.CONVERT", "Money pair claimed equal must convert consistently "
            "(units.convert); dimension mismatch → None.", "1",
            laws=("three-valued",)), check_convert_pair),
    (FnSpec("PHY.CONSERVE", "A declared total equals the sum/product of its "
            "parts.", "1", laws=("three-valued",)), check_conserve),
    (FnSpec("PHY.MONO", "An (P, R@P) series: recall non-increasing in "
            "precision.", "1", laws=("three-valued", "monotone")), check_mono),
    (FnSpec("PHY.UNCERT", "A quantity derived from an approx parent carries "
            "approx=True — propagation, not assertion.", "1",
            laws=("three-valued",)), check_uncert),
    # declared, not faked — wait for a physics corpus (plan v2 §5: 2302.07629)
    (FnSpec("PHY.CAUSE", "Cause precedes effect (physics corpus pending).",
            "0", laws=()), _not_implemented),
    (FnSpec("PHY.FRAME", "Frame/reference consistency (physics corpus pending).",
            "0", laws=()), _not_implemented),
]:
    register_fn(_spec, _impl)
