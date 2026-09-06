"""Residuals = the open points only, worst first. What B was trying to be.

Selection reuses report_tex.findings_rows (509/513/515) so the classes the
21 documents were judged by do not change here; this module adds the
Low-confidence section and joins every selected identifier back to its row
object, so crops and host lines ride along into both renderers.
"""
from __future__ import annotations

from .. import report_tex as rt
from .rows import EquationRow

SECTIONS = ("corrected", "unresolved", "flagged", "lowconf", "doubted")
CAPTIONS = {"corrected": "Corrected",
            "unresolved": "Unresolved",
            "flagged": "Flagged, not acted on",
            "lowconf": "Low confidence",
            "doubted": "Doubted but correct"}


def _by_conf(rows):
    return sorted(rows, key=lambda r: (r.shown_confidence
                                       if r.shown_confidence is not None else 2.0))


def findings(rows_by_kind: dict, doc_dir) -> dict:
    r"""{corrected, unresolved, flagged, doubted} — findings_rows (509/513/515)
    ported over ROW OBJECTS, so no tiddler is read.

    Iterates equation then formula rows; a row whose identifier is already in
    a corrected pair is skipped (the pair already says what was wrong).
    A row that does not render is unresolved. Otherwise, for an EquationRow,
    `conf < DOUBTED_MAX_CONF` with an agreeing ink code is doubted; a flagging
    ink code is flagged. A FormulaRow never carries `conf`/`code` (its
    confidence lives on the host line, not the formula) so it can only land
    in unresolved. Finally, `_contradicted_identifiers` (511) is appended to
    unresolved.
    """
    pairs = rt.corrected_pairs(doc_dir)
    done = {p["identifier"] for p in pairs if p.get("identifier")}
    unresolved, doubted, flagged = [], [], []
    contradicted = rt._contradicted_identifiers(doc_dir)
    for row in list(rows_by_kind.get("equation", [])) + \
               list(rows_by_kind.get("formula", [])):
        title, latex, page = row.identifier, row.latex, row.page
        if not latex or title in done:
            continue
        if not rt.renderable(latex):
            unresolved.append({"identifier": title, "page": page,
                               "latex": latex, "why": "does not render"})
            continue
        conf = row.confidence if isinstance(row, EquationRow) else None
        code = row.ink_code if isinstance(row, EquationRow) else ""
        if (conf is not None and conf < rt.DOUBTED_MAX_CONF
                and code[:1] in rt.INK_AGREES):
            doubted.append({"identifier": title, "page": page, "latex": latex,
                            "conf": conf, "code": code})
        elif code[:1] in rt.INK_FLAGS:
            flagged.append({"identifier": title, "page": page, "latex": latex,
                            "conf": conf, "code": code})
    for ident in sorted(contradicted):
        unresolved.append({"identifier": ident, "page": contradicted[ident][0],
                           "latex": contradicted[ident][1],
                           "why": "a refinement whose two records disagree "
                                  "(511) — the original is shown"})
    return {"corrected": pairs, "unresolved": unresolved,
            "flagged": flagged, "doubted": doubted}


def select(rows_by_kind: dict, found: dict, *, conf: float = rt.CONF_THRESHOLD) -> dict:
    index = {r.identifier: r for lst in rows_by_kind.values() for r in lst}
    taken = set()

    def pick(records):
        out = []
        for rec in records:
            ident = rec.get("identifier")
            r = index.get(ident)
            if r is None or ident in taken:
                continue
            taken.add(ident)
            out.append(r)
        return _by_conf(out)

    corrected = list(found.get("corrected") or [])
    taken.update(p.get("identifier") for p in corrected if p.get("identifier"))
    unresolved = pick(found.get("unresolved") or [])
    shown, rest = rt.flagged_split(found.get("flagged") or [])
    flagged = pick(shown)
    taken.update(r.get("identifier") for r in (found.get("flagged") or []))
    doubted_recs = found.get("doubted") or []
    doubted_ids = {r.get("identifier") for r in doubted_recs}
    lowconf = _by_conf([r for r in rows_by_kind.get("equation", [])
                        if isinstance(r, EquationRow)
                        and r.confidence is not None and r.confidence < conf
                        and r.identifier not in taken
                        and r.identifier not in doubted_ids])
    taken.update(r.identifier for r in lowconf)
    doubted = pick(doubted_recs)
    return {"corrected": corrected, "unresolved": unresolved,
            "flagged": flagged, "lowconf": lowconf, "doubted": doubted,
            "flagged_rest": rest}
