"""
VER.EQ.RECOMPUTE — arithmetic verification of derivation quantities (S3.1).

A `derivation` quantity record carries its own proof obligation: the payload
{lhs_terms, op, rhs} claims that combining the terms yields the stated result.
`verify_derivation` RECOMPUTES it and returns
    {'ok': True|False|None, 'computed', 'stated', 'detail'}
ok=None means uncheckable (not a derivation / malformed payload) — the honest
third state, distinct from refuted.

Tolerances: papers round ("7,871,085 · 0.86 = 6,769,133" — the exact product is
6,769,133.1), so the default is ±1 absolute (integer rounding) CAPPED at 0.5% of
the stated value — a large integer tolerates the rounding unit, while a small
stated value (10/4 = 3?) compares tight instead of hiding inside the ±1. A
record flagged `approx=True` (a \\sim/≈ hedge) widens to ±5% relative.
`tol_abs`/`tol_rel` override both.
"""
from __future__ import annotations

from typing import Optional

from .registry import FnSpec, register_fn

_APPROX_REL = 0.05


def _fmt(x: float) -> str:
    """Plain fixed-point formatting — never scientific notation, so the detail
    string literally contains the recomputed digits an auditor greps for."""
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _combine(terms: list, op: str) -> Optional[float]:
    if not terms or len(terms) < 2:
        return None
    acc = float(terms[0])
    for t in terms[1:]:
        t = float(t)
        if op == "mul":
            acc *= t
        elif op == "add":
            acc += t
        elif op == "sub":
            acc -= t
        elif op == "div":
            if t == 0:
                return None
            acc /= t
        else:
            return None
    return acc


def verify_derivation(qrec: dict, tol_abs: float = 1,
                      tol_rel: Optional[float] = None) -> dict:
    """Recompute a derivation quantity record. ok=None when uncheckable."""
    if (qrec or {}).get("kind") != "derivation":
        return {"ok": None, "computed": None, "stated": None,
                "detail": "not a derivation record"}
    payload = qrec.get("payload") or {}
    terms, op, rhs = payload.get("lhs_terms"), payload.get("op"), payload.get("rhs")
    computed = _combine(list(terms or ()), op or "")
    if computed is None or rhs is None:
        return {"ok": None, "computed": computed, "stated": rhs,
                "detail": "malformed derivation payload"}
    stated = float(rhs)

    rel = tol_rel if tol_rel is not None else (_APPROX_REL if qrec.get("approx") else None)
    if rel is not None:
        ok = abs(computed - stated) <= rel * max(abs(stated), 1e-12)
        tol_note = f"±{rel:.0%} rel"
    else:
        # ±tol_abs for integer rounding, but never looser than 0.5% of the
        # stated value — so "10/4 = 3" refutes instead of hiding inside the ±1.
        tol = max(min(tol_abs, 0.005 * max(abs(stated), 1.0)), 1e-9)
        ok = abs(computed - stated) <= tol
        tol_note = f"±{tol:g} abs"
    return {"ok": bool(ok), "computed": computed, "stated": stated,
            "detail": (f"computed {_fmt(computed)} vs stated {_fmt(stated)} "
                       f"({tol_note})" + ("" if ok else " — REFUTED"))}


register_fn(FnSpec(
    fid="VER.EQ.RECOMPUTE",
    description="Recompute a derivation quantity (mul/add/sub/div chain) and "
                "confirm/refute the stated result; ±1 abs (integer rounding), "
                "approx widens to ±5% rel; ok=None = uncheckable.",
    version="1",
    params={"tol_abs": 1, "approx_tol_rel": _APPROX_REL},
    laws=("three-valued", "recompute-not-trust"),
), verify_derivation)
