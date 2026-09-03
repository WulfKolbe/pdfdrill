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
             "unrendered": "U",
             # 386 — a row whose Rendered AND Scan cells are both empty. Not
             # clean (nothing was compared) and not unrendered (the report did
             # render it); _INK_COLOUR already maps it to inkUnmeasured.
             "absent": "A"}
FIVE_L = ("L_comp", "L_holes", "L_stk", "L_cen", "L_off")
FIVE_R = ("R_comp", "R_holes", "R_stk", "R_cen", "R_off")

_IDENT = re.compile(r"\\ident\{([^&\n]*?EQ\d+)\}[^&\n]*& *(\d+) *&")

#: 386 — the DTZ figure report carries neither half of the contract above: its
#: identifiers are DTZ00000, not <bib>_EQ0001, and its Page cell holds
#: "shard 00 / row 0" rather than a bare page number. `identifiers` therefore
#: found none, `convert` saw 100 measured rows against 0 identifiers, and
#: refused — correctly, on the rule it was given.
#:
#: This is a SECOND pattern, not a loosened first one. Relaxing `_IDENT` to
#: accept a non-numeric Page cell would widen the contract for the eleven
#: published reports too, whose alignment is the thing out/237 verified 64 of
#: 64 at offset zero. A new report form gets a new pattern; the proven one is
#: not edited to accommodate it.
_IDENT_FIG = re.compile(r"\\ident\{([^&\n]*?[A-Z]{2,4}\d{3,})\}[^&\n]*&")

#: 562 — the FINDINGS row form, and a THIRD pattern rather than a looser
#: first one, for 386's reason: relaxing `_IDENT` would widen the contract for
#: every full-listing report too, and those are what out/237 verified 64 of 64
#: at offset zero.
#:
#: Two things differ. The identifier carries a SUFFIX — `\ident{k_EQ0001
#: (was)}`, `(now)`, `(basis)` — so `EQ\d+` is no longer flush against the
#: closing brace. And the Page cell may be EMPTY: an inline formula row has no
#: page of its own, which is the whole of 550. `_IDENT` requires a bare number
#: there and matched nothing, so publishready reported "report.tex yields no
#: row identifiers" on every findings report and its coverage check could not
#: run.
_IDENT_FIND = re.compile(
    r"\\ident\{([^&\n]*?(?:EQ|FO|TAB)\d+)[^&\n}]*\}[^&\n]*&")


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
    """Row identifiers in TABLE order, which is the order the TSV rows are in.

    The EQ form is tried FIRST and alone: if it matches anything at all, that
    is the answer. Only a report where it matches NOTHING falls through to the
    figure form, so no document can ever be read by both patterns and no
    existing report's pairing can change. A fallback that could fire on a
    partial match would be a silent re-pairing of the eleven.
    """
    ids = [clean_ident(m.group(1)) for m in _IDENT.finditer(tex_body)]
    if ids:
        return ids
    ids = [clean_ident(m.group(1)) for m in _IDENT_FIND.finditer(tex_body)]
    if ids:
        return ids
    return [clean_ident(m.group(1)) for m in _IDENT_FIG.finditer(tex_body)]


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


def page_identifiers(pdf: Path) -> "dict[int, list[str]]":
    """{page: [identifier, ...]} read from the built PDF's own text layer.

    The tex gives table order but not PAGE, and page is what makes the
    pairing containable. pdftotext is already a hard dependency of every
    build command here.
    """
    import subprocess
    out = {}
    n = int(re.search(r"^Pages:\s+(\d+)",
                      subprocess.run(["pdfinfo", str(pdf)], capture_output=True,
                                     text=True).stdout, re.M).group(1))
    for pg in range(1, n + 1):
        txt = subprocess.run(["pdftotext", "-f", str(pg), "-l", str(pg),
                              str(pdf), "-"], capture_output=True,
                             text=True, errors="replace").stdout
        seen = []
        for m in re.finditer(r"[A-Z]{2,4}\d{3,}", txt):
            if m.group(0) not in seen:
                seen.append(m.group(0))
        if seen:
            out[pg] = seen
    return out


def convert_by_page(tsv: Path, pdf: Path, *, stamp: dict | None = None) -> dict:
    """386 — the same conversion, paired PER PAGE instead of per document.

    Two things forced this, both measured on the DTZ report and both real.

    THE FOOTER RULE IS VALUE-BASED AND SHOULD BE STRUCTURAL. `read_tsv` calls
    a row a footer when its five-tuple pair is all zero, and the docstring
    above records that on the eleven this coincided exactly with the last row
    of every page, 1232/1232. It is not an identity. DTZ page 25 holds a real
    data row whose Rendered and Scan cells are both empty — the `absent` case
    _INK_COLOUR already names — and the all-zero rule ate it as a footer,
    losing a row and shifting the tail. Here the footer is the LAST row of the
    page, which is what the longtable's endfoot actually emits.

    A MISSING ROW MUST NOT COST THE WHOLE DOCUMENT. Whole-document zip is
    all-or-nothing: one page whose lattice loses a row refuses 100 rows
    because of 3. Pairing per page contains it — 33 of 34 DTZ pages pair
    exactly and a page that does not is dropped whole, with its identifiers
    named. That is the rule this file already states in another form: a wrong
    identifier is worse than none.

    Pages are dropped, never truncated. If a page's row count and identifier
    count disagree the pairing on that page is unknown, and taking the first
    N would be the silent zip() this converter exists to refuse.
    """
    import csv as _csv
    rows = list(_csv.DictReader(tsv.open(encoding="utf-8", errors="replace"),
                                delimiter="\t"))
    bypage: dict = {}
    for r in rows:
        bypage.setdefault(int(r["report_page"]), []).append(r)
    ids_by_page = page_identifiers(pdf)
    out, dropped, footers = [], [], 0
    for pg in sorted(bypage):
        rs = sorted(bypage[pg], key=lambda r: int(r["line"]))
        body, footers = rs[:-1], footers + 1      # the last row is the footer
        ids = ids_by_page.get(pg, [])
        if len(body) != len(ids):
            dropped.append({"page": pg, "rows": len(body),
                            "identifiers": len(ids), "ids": ids})
            continue
        for ident, r in zip(ids, body):
            L = [int(r[k]) for k in FIVE_L]
            R = [int(r[k]) for k in FIVE_R]
            distance = sum(abs(a - b) for a, b in zip(L, R))
            signed = R[0] - L[0]
            # An all-zero pair is an ABSENT reading, not a clean one: it would
            # otherwise take flag_of's first branch and the best class.
            if not any(L) and not any(R):
                flag = "absent"
            else:
                flag = flag_of(distance, abs(signed),
                               str(r.get("A_eq_B", "")).strip().lower()
                               in ("yes", "true", "1"))
            out.append({
                "id": ident, "report_page": pg, "line": int(r["line"]),
                "L": L, "R": R, "distance": distance,
                "comp_delta": abs(signed), "signed_delta": signed,
                "flag": flag, "rendered": True,
                "code": ("%s|%+d" % (FLAG_CODE[flag], signed))
                        if flag in FLAG_CODE else "",
            })
    payload = {
        "rows": out,
        "footers_dropped": footers,
        "display_pages": len(bypage),
        "pages_dropped": dropped,
        "source": tsv.name,
        "paired": "per page",
    }
    if stamp:
        payload["measured_against"] = stamp
    return payload


def write(payload: dict, dest: Path) -> Path:
    dest.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return dest
