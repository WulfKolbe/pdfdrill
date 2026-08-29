"""244 — inkdrill's report.compare.tsv -> report.ink.json.

The TSV carries NO identifiers: report_page, line, dis, A_eq_B and the two
five-tuples, nothing else. Identifiers come from report.tex, positionally, in
table order. Two things make that safe and both are asserted, not assumed:

FOOTERS. The TSV holds one all-zero row per page — the legend footer, whose
Rendered and Scan cells are blank because the legend spans all columns via
\\multicolumn. Measured across the eleven: all-zero rows == display pages ==
last row of every page, 1232/1232/1232. Zipping without dropping them attaches
every identifier after the first footer to another equation's measurement.

And they must not merely be skipped, they must not be CLASSIFIED: an all-zero
pair scores distance 0, and flag_of's first branch returns "clean". Kept, the
1,232 footers arrive as K|+0 — an absent reading taking the best class — and
the clean count across the eleven goes from 1,207 to 2,439.

THE COUNT. After dropping footers, rows must equal identifiers exactly. It did
for all eleven (8,032 - 1,232 = 6,800 = the display-equation total). If it does
not, the pairing is unknown and this refuses rather than truncating: zip()
would silently drop the tail and produce a file that passes every structural
check.

Alignment was verified independently (out/237): rows demoted to
\\emph{(not rendered)} have a constant rendered ink of 13 components, so each
is a known-answer test at a known position — 64 of 64 hit at offset 0.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

#: inkdrill's measured floors (tools/findings.py) — not re-derived here
NOISE_DISTANCE = 7
NOISE_COMP_DELTA = 2
FLAG_CODE = {"clean": "K", "noise": "N", "weak": "W", "stable": "S",
             "component": "C",
             # A row demoted to \emph{(not rendered)} has NO rendering to
             # compare. Measuring it against the scan compares italic English
             # against a formula, which scores a large component delta and was
             # being classified `component` — a defect in the conversion, not
             # in the extraction. inkdrill excludes such rows from its own
             # tally; my count read C 92 against their 90 on 2103.01507, and
             # the two rows were EQ0383 and EQ1005, both demoted.
             #
             # It matters beyond the tally: publishready gates on the p90
             # component ratio, and `component_ratio_p90` already takes a
             # `rendered` mask for exactly this reason. A false `component`
             # inflates the number the gate reads.
             "unrendered": "U"}
FIVE_L = ("L_comp", "L_holes", "L_stk", "L_cen", "L_off")
FIVE_R = ("R_comp", "R_holes", "R_stk", "R_cen", "R_off")

_IDENT = re.compile(r"\\ident\{([^&\n]*?EQ\d+)\}[^&\n]*& *(\d+) *&")


class ConversionRefused(Exception):
    """The pairing cannot be established. No file is written."""


def flag_of(distance: int, comp_delta: int, scale_stable: bool) -> str:
    if distance == 0:
        return "clean"
    if comp_delta > NOISE_COMP_DELTA:
        return "component"
    if distance <= NOISE_DISTANCE:
        return "noise"
    return "stable" if scale_stable else "weak"


def clean_ident(text: str) -> str:
    return text.replace("\\allowbreak{}", "").replace("\\", "")


def identifiers(tex_body: str) -> list:
    """EQ identifiers in TABLE order, which is the order the TSV rows are in."""
    return [clean_ident(m.group(1)) for m in _IDENT.finditer(tex_body)]


def read_tsv(path: Path) -> tuple:
    """(measured rows, footer rows). A footer is an all-zero five-tuple pair."""
    rows = list(csv.DictReader(path.open(encoding="utf-8", errors="replace"),
                               delimiter="\t"))
    body, footers = [], []
    for r in rows:
        if all(r.get(k) == "0" for k in FIVE_L + FIVE_R):
            footers.append(r)
        else:
            body.append(r)
    return body, footers


def convert(tsv: Path, tex: Path, *, stamp: dict | None = None) -> dict:
    """The ink.json payload, or ConversionRefused. Writes nothing."""
    from .report_tex import demoted_flags
    body, footers = read_tsv(tsv)
    tex_body = tex.read_text(encoding="utf-8", errors="replace")
    ids = identifiers(tex_body)
    did_render = demoted_flags(tex_body)
    pages = {r.get("report_page") for r in footers}
    if len(body) != len(ids):
        raise ConversionRefused(
            "%d measured rows against %d identifiers — the pairing is unknown. "
            "zip() would drop the tail silently and the result would pass every "
            "structural check." % (len(body), len(ids)))
    out = []
    for ident, r in zip(ids, body):
        L = [int(r[k]) for k in FIVE_L]
        R = [int(r[k]) for k in FIVE_R]
        distance = sum(abs(a - b) for a, b in zip(L, R))
        signed = R[0] - L[0]
        # `A_eq_B` IS the scale_stable input, and it has been in this header
        # since the first file — I quoted the fourteen columns back to inkdrill
        # myself with A_eq_B fourth. This passed a hardcoded False beside a
        # comment asserting the column did not exist, so `stable` was
        # unreachable and every such row became `weak`. The "zero S in 6,207
        # measured rows corpus-wide" that comment offered as evidence was the
        # branch refusing to fire, measured and then explained by the thing
        # causing it.
        #
        # A_eq_B: the 300 dpi five-tuple equals the 600 dpi one — two
        # INDEPENDENT renders agreeing. Not to be confused with `B_stable`,
        # which is B against its own half-scale resample: one render, weaker,
        # and not what this class means.
        rendered = did_render[len(out)] if len(out) < len(did_render) else True
        flag = flag_of(distance, abs(signed),
                       str(r.get("A_eq_B", "")).strip().lower()
                       in ("yes", "true", "1")) if rendered else "unrendered"
        out.append({
            "id": ident,
            "report_page": int(r["report_page"]),
            "line": int(r["line"]),
            "L": L, "R": R,
            "distance": distance,
            "comp_delta": abs(signed),
            "signed_delta": signed,
            "flag": flag,
            # False when the report demoted this row: there is no rendering,
            # so its distance measures an absence, not a disagreement.
            "rendered": bool(rendered),
            "code": "%s|%+d" % (FLAG_CODE[flag], signed),
        })
    payload = {
        "rows": out,
        "footers_dropped": len(footers),
        "display_pages": len(pages),
        "source": tsv.name,
    }
    if stamp:
        payload["measured_against"] = stamp
    return payload


def write(payload: dict, dest: Path) -> Path:
    dest.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return dest
