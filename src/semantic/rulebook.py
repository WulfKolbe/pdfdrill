"""
The rulebook — projection, not storage (two-store plan, step 4).

Selects kitems whose status clears the bar (accepted, supported), groups them
by kind, and emits flat Markdown: ONE statement per line, formula-collection
style, each carrying its `[→k:hash8]` drill-down anchor. The disclosure
ladder underneath: rulebook line → kitem (statement/status/evidence refs) →
evidence spans → the exact node/page in the source document.

proposed/disputed kitems are EXCLUDED but counted — the rulebook never
silently hides how much is below the bar.

Support column (A2, 2606.28429v1): each line may carry `support≈X.XX`, the
HYBRID readout r₍₂₎ + α(c⁺ − 2) over the kitem's span-evidence confidences —
the accumulator that sees both the count margin (5 corroborating spans vs 2)
and the edge margin (a barely-matching extra span vs a strong one), which min
and count each miss. DISPLAY ONLY: it never feeds `status` (the belief.py
stance — the lattice stays the only authoritative judgement).
"""
from __future__ import annotations

from . import kitems as _kitems

_KIND_ORDER = ("rule", "formula", "definition", "claim", "derivation",
               "reuse_event", "contradiction")
_INCLUDE = ("accepted", "supported")

_SUPPORT_K = 2          # matches the accepted threshold
_SUPPORT_ALPHA = 0.1    # a gentle count-surplus weight for a report column


def _support(e) -> "float | None":
    """The hybrid support strength over the kitem's OWN span confidences —
    None below k spans (no invented margins)."""
    from . import aggregate as _agg
    confs = [ev.confidence for ev in e.evidence if ev.prop == "span"]
    return _agg.Hybrid(k=_SUPPORT_K, alpha=_SUPPORT_ALPHA)(confs)


def project_rulebook(graph, bibkey: str,
                     include: tuple = _INCLUDE) -> str:
    by_kind: dict[str, list[tuple]] = {}
    below_bar = 0
    for e in _kitems.all_kitems(graph):
        status = _kitems.status_of(graph, e.id)
        if status not in include:
            below_bar += 1
            continue
        p = e.properties()
        h = p.get("content_hash") or _kitems.kitem_hash(p.get("statement_md", ""))
        by_kind.setdefault(e.subtype or p.get("kind", "claim"), []).append(
            (p.get("statement_md", ""), h[:8], status, _support(e)))

    lines = [f"# Rulebook — {bibkey}", ""]
    total = 0
    for kind in list(_KIND_ORDER) + sorted(set(by_kind) - set(_KIND_ORDER)):
        items = by_kind.get(kind)
        if not items:
            continue
        lines.append(f"## {kind.capitalize()}s")
        for stmt, h8, status, support in sorted(items, key=lambda t: t[0].lower()):
            marker = "" if status == "accepted" else f" ({status})"
            sup = f" support≈{support:.2f}" if support is not None else ""
            lines.append(f"- {stmt} [→k:{h8}]{marker}{sup}")
            total += 1
        lines.append("")
    lines.append(f"_{total} statement(s); {below_bar} kitem(s) below the bar "
                 f"(proposed/disputed) not shown._")
    return "\n".join(lines)
