"""Residuals = the open points only, worst first. What B was trying to be.

Selection reuses report_tex.findings_rows (509/513/515) so the classes the
21 documents were judged by do not change here; this module adds the
Low-confidence section and joins every selected identifier back to its row
object, so crops and host lines ride along into both renderers.
"""
from __future__ import annotations

import datetime as _dt
import json as _json
from pathlib import Path

from .. import report_tex as rt
from . import budget as _budget
from . import html as H
from . import tex as T
from .rows import EquationRow, row_kind

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

    # 655 review round 1, finding 4 -- `corrected` pairs come from
    # `corrected_pairs` (a JSON record keyed by identifier only, never a row
    # object), so without this they would read their crop straight from the
    # full-size `report-crops/` directory regardless of whatever rung
    # `ensure_crops` already picked for that identifier's kind. Stamping the
    # SAME row's `.crop`/`.px_width` onto the pair here is what lets
    # `residuals.build` route the Corrected section through the budgeted
    # copy exactly like every other section already does via `index`.
    # 655 review round 2 -- `_kind` rides along too, so `build` can report
    # WHICH kind's rung actually governs a corrected pair's crop (a pair's
    # own record carries no kind of its own; only its row does).
    def _with_crop(rec):
        r = index.get(rec.get("identifier"))
        return dict(rec, _crop=(r.crop if r is not None else None),
                   _px_width=(r.px_width if r is not None else ""),
                   _kind=(row_kind(r) if r is not None else None))

    corrected = [_with_crop(p) for p in (found.get("corrected") or [])]
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


OUTPUT = "residuals.%s"


def _ink_meta(doc_dir) -> dict:
    p = Path(doc_dir) / "report.ink.json"
    if not p.is_file():
        return {}
    try:
        return (_json.loads(p.read_text(encoding="utf-8"))
                .get(rt.MEASURED_AGAINST) or {})
    except Exception:
        return {}


def header_lines(doc_dir) -> list:
    ma = _ink_meta(doc_dir)
    if not ma.get("built_at"):
        return ["no ink measurement for this document: the Flagged and "
                "Doubted sections cannot be filled; run `residuals --measure`"]
    mt = ma.get("model_mtime")
    when = (_dt.datetime.fromtimestamp(int(mt), _dt.timezone.utc)
            .strftime("%Y-%m-%d") if mt else "unknown date")
    return ["equations measured %s against the model of %s"
            % (ma["built_at"], when)]


def _rest_line(rest: dict) -> str:
    if not rest or not rest.get("n"):
        return ""
    return ("%d more flagged rows below the band, stated as a count: "
            "%d component, %d weak; confidence high %d, mid %d, low %d, none %d"
            % (rest["n"], rest["C"], rest["W"], rest["high"], rest["mid"],
               rest["low"], rest["none"]))


def _crop_for(corrected: list):
    """`ident -> (Path, px_width) | None`, built from the crop/px_width
    `select`'s `_with_crop` already stamped onto each corrected pair --
    see `findings_tex`'s `crop_for` param (655 review round 1, finding 4)."""
    by_ident = {p["identifier"]: p for p in corrected if p.get("identifier")}

    def lookup(ident):
        p = by_ident.get(ident)
        if p is None or p.get("_crop") is None:
            return None
        return p["_crop"], p.get("_px_width", "")
    return lookup


def _kinds_present(selected: dict) -> set:
    """655 review round 2 -- which of {"equation", "formula"} actually have
    a row in THIS build, derived from the row objects/`_kind` `select`
    already stamped -- residuals.pdf mixes both kinds, so "the rung" for
    it is not one value; this is what lets `build` report exactly the
    kinds that are really there instead of guessing or reporting all of
    them regardless."""
    kinds = set()
    for k in SECTIONS[1:]:
        kinds.update(row_kind(r) for r in selected.get(k) or [])
    kinds.update(p.get("_kind") for p in selected.get("corrected") or []
                if p.get("_kind"))
    return kinds


def build(selected: dict, fmt: str, *, doc_dir, pdf, bibkey, history, px2mm,
          paper, landscape, pages, compile_pdf,
          budget_mb: "float | None" = None, rungs: "dict | None" = None) -> dict:
    doc_dir = Path(doc_dir)
    meta = header_lines(doc_dir)
    rest = _rest_line(selected.get("flagged_rest") or {})
    n = sum(len(selected[k]) for k in SECTIONS)
    title = "%s: residuals" % bibkey
    if fmt == "html":
        parts = []
        for k in SECTIONS:
            if not selected[k]:
                continue
            if k == "corrected":
                rows_html = "".join(
                    "<li>%s: <code>%s</code> \u2192 <code>%s</code></li>"
                    % (H._h.escape(p.get("identifier", "")),
                       H._h.escape(p.get("before", "")),
                       H._h.escape(p.get("after", "")))
                    for p in selected[k])
                parts.append("<h2>%s (%d)</h2><ul>%s</ul>\n"
                             % (CAPTIONS[k], len(selected[k]), rows_html))
                continue
            parts.append(H.render_section(selected[k], "equation",
                                          doc_dir=doc_dir, caption=CAPTIONS[k],
                                          ink_codes=True))
            if k == "flagged" and rest:
                parts.append('<p class="note">%s</p>\n' % H._h.escape(rest))
        body = "".join(parts) if parts else (
            '<h2>Residuals</h2><p class="note">nothing open</p>')
        out = doc_dir / (OUTPUT % "html")
        out.write_text(H.page_shell(title, body, meta_lines=meta),
                       encoding="utf-8")
        return {"out": out, "rows": n, "pages": None, "errors": 0, "demoted": 0}

    widths = T.widths_for(paper, landscape, with_image=True)
    body = ["\\noindent{\\small %s}\\\\[.6em]\n" % rt.esc_text("; ".join(meta))]
    if selected["corrected"]:
        body.append(rt.findings_tex(
            {"corrected": selected["corrected"], "unresolved": [],
             "flagged": [], "doubted": []},
            widths, crops=doc_dir / "report-crops", out_dir=doc_dir,
            px2mm=px2mm, bibkey=bibkey, history=history, form=True,
            legend_on=True, bullets=True,
            crop_for=_crop_for(selected["corrected"])))
    for k in SECTIONS[1:]:
        if not selected[k]:
            continue
        body.append("\\clearpage\n")
        body.append(T.render_table(selected[k], "equation", widths=widths,
                                   out_dir=doc_dir, px2mm=px2mm, bibkey=bibkey,
                                   history=history, caption=CAPTIONS[k],
                                   legend_on=True, form=True, ink_bullets=True))
        if k == "flagged" and rest:
            body.append("\\noindent{\\small %s}\n" % rt.esc_text(rest))
    if n == 0:
        body.append("\\section*{Residuals}\\noindent Nothing open.\n")
    tex_path = doc_dir / (OUTPUT % "tex")
    tex_path.write_text(T.document("".join(body), paper=paper,
                                   landscape=landscape, pages=pages, title=title,
                                   form=True),
                        encoding="utf-8")
    res = {"out": tex_path.with_suffix(".pdf"), "rows": n, "pages": None,
           "errors": 0, "demoted": 0}
    if compile_pdf:
        c = rt.compile_fixpoint(tex_path)
        if c is not None:
            res["pages"], res["errors"], res["demoted"] = c
    # 655 review round 1, finding 3 -- checked against the real artefact,
    # same as `evidence.build`; `residuals.pdf` draws a small subset of
    # already-budgeted rows so this essentially never fires, but "essentially
    # never" is not "never" once finding 4's Corrected-section fix means an
    # unbudgeted-kind identifier could in principle still land here.
    if budget_mb is not None:
        res["bytes"], res["over_budget"] = _budget.check_artifact(
            res["out"], budget_mb=budget_mb)
        res["budget_mb"] = budget_mb
        # 655 review round 2 -- ONLY the kinds that actually contributed a
        # row to this specific build, each with its REAL rung (or None);
        # never a hardcoded assumption about which rung a document is at.
        res["rungs"] = {k: (rungs or {}).get(k) for k in sorted(_kinds_present(selected))}
    return res
