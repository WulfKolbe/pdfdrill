"""The publish gate for the redrawn surface.

The old gate compared the ink's PDF checksum with the measure build's, so a
layout change could never publish without re-measuring. The measurement is
about the MODEL's equations, not about a PDF: the ink records the model it
measured (sha256 and mtime, 575), and that is what is compared. The PDF
checksum is recorded and never compared.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .. import report_tex as rt

PUBLISHED_FILES = ("evidence-equation.pdf", "evidence-formula.pdf",
                   "evidence-table.pdf", "evidence-image.pdf", "residuals.pdf")
FIX = "run `pdfdrill residuals --measure --pdf <pdf>`"


class GateStatus(tuple):
    """(ok, detail), plus `.verified` — a check that PASSED because it looked
    and found nothing wrong, versus one that passed because it had nothing to
    look AT, are different claims and `ok` alone cannot carry both. `detail`
    can say the difference in prose, but prose is not something a caller can
    branch on without re-parsing it (667 fix round 1 — see `crop_gate`, the
    one gate this project has that ever passes on absent evidence rather than
    failing, per commands.publish_ready's own stated principle).

    Still exactly a 2-tuple everywhere a 2-tuple is expected —
    `ok, detail = crop_gate(...)`, `checks[k][0]`, `for k, (ok, why) in
    checks.items()` — every existing caller of every OTHER gate in this file
    is unaffected; `.verified` is additional, not a replacement for the
    2-tuple contract those callers already rely on.

    THE TRAP (667 fix round 2, reviewer-found): `json.dumps` has no hook for
    a tuple SUBCLASS — it serialises any tuple, this one included, as a
    plain `[ok, detail]` list. `.verified` is gone, silently, with no
    exception raised anywhere: `json.dumps(GateStatus(True, "x", False))`
    returns `'[true, "x"]'`, not an error. Pinned in
    tests/test_reports_gate.py so this stays a documented limitation rather
    than something the next caller discovers by losing data. A caller that
    needs `.verified` in a JSON payload (`commands.cmd_publishready`'s
    `--json` output is the one that exists) must read the attribute
    explicitly (`getattr(v, "verified", None)`, since every OTHER gate's
    plain tuple has no such attribute at all) and put it in the dict itself
    — never `json.dumps` the object directly.
    """
    def __new__(cls, ok: bool, detail: str, verified: bool):
        self = super().__new__(cls, (ok, detail))
        self.verified = verified
        return self

#: fix round 1 (reviewer-found) — `inkconvert.identifiers()` tries its EQ
#: pattern FIRST and returns as soon as it matches ANYTHING, by design (its
#: own docstring: "no existing report's pairing can change"). A residuals.tex
#: with plain rows AND a Corrected section never falls through to the
#: pattern that reads `\ident{ID (was)}` / `(now)`, because the plain rows
#: already satisfied the first one — on johnston that returned 35 of 43
#: identifiers and silently dropped all 8 corrected ones, so an unmeasured,
#: non-straddling equation shown only in Corrected passed coverage.
#:
#: This gate does not need "the one true pairing order" `identifiers()`
#: exists to guarantee — it only needs the SET of identifiers a report
#: SHOWS, from every form at once. Built from `_IDENT`/`_IDENT_FIND`'s own
#: character classes (HANDOVER-RULES rule 17: a brace class not anchored on
#: the identifier's own shape is unverified on the case that would break
#: it) rather than a new one: braces are allowed BEFORE the digits (an
#: escaped `\_\allowbreak{}` sits there) and excluded AFTER them (a suffix
#: like ` (was)` never contains one), which is what lets the non-greedy
#: prefix stop at the right `EQ\d+` even with `\allowbreak{}` inside it.
#: 644 — same prefixes as `inkconvert._IDENT_FIND`, from the same table
#: (`docops…tiddlywiki.TITLE_SHAPES`), so widening the scheme cannot leave one
#: of the two behind. The character classes are unchanged.
def _ident_any() -> "re.Pattern":
    from ..inkconvert import _REPORT_ROW_KINDS, _prefixes
    return re.compile(r"\\ident\{([^&\n]*?(?:" + _prefixes(_REPORT_ROW_KINDS)
                      + r")\d+[^&\n}]*)\}")


_IDENT_ANY = _ident_any()
_IDENT_SUFFIX = re.compile(r" \((?:was|now|basis)\)$")


def shown_identifiers(tex_text: str) -> set:
    """Every identifier a report.tex SHOWS, from every `\\ident{...}` form at
    once — plain rows, findings rows, and Corrected `(was)`/`(now)` pairs —
    unlike `inkconvert.identifiers()`, which is deliberately single-pattern
    (that contract stays; other callers depend on it, see its docstring).
    """
    from ..inkconvert import clean_ident
    ids = set()
    for m in _IDENT_ANY.finditer(tex_text):
        ident = _IDENT_SUFFIX.sub("", clean_ident(m.group(1)))
        ids.add(ident)
    return ids


def _ink(doc_dir: Path) -> dict:
    p = Path(doc_dir) / "report.ink.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def timestamp_gate(doc_dir) -> tuple:
    doc_dir = Path(doc_dir)
    ink = _ink(doc_dir)
    if not ink:
        return False, "no report.ink.json; %s" % FIX
    ma = ink.get(rt.MEASURED_AGAINST) or {}
    if not ma.get("built_at"):
        return False, "the ink does not say when it was measured; %s" % FIX
    live = rt.model_state(doc_dir)
    same_sha = (ma.get("model_sha256") and live.get("model_sha256")
                and ma["model_sha256"] == live["model_sha256"])
    if same_sha:
        return True, "measured %s against the model on disk" % ma["built_at"]
    try:
        older = int(live.get("model_mtime") or 0) > int(ma.get("model_mtime") or 0)
    except (TypeError, ValueError):
        older = True
    if older:
        return False, ("measured %s, but the model was rebuilt since (model "
                       "mtime %s > measured %s); %s"
                       % (ma["built_at"], live.get("model_mtime"),
                          ma.get("model_mtime"), FIX))
    return True, ("measured %s; model sha differs but is not newer (mtime %s)"
                  % (ma["built_at"], live.get("model_mtime")))


def coverage_gate(doc_dir) -> tuple:
    doc_dir = Path(doc_dir)
    tex = doc_dir / "residuals.tex"
    if not tex.is_file():
        return False, "no residuals.tex to read row identifiers from"
    shown = {i for i in shown_identifiers(tex.read_text(encoding="utf-8", errors="replace"))
             if "_EQ" in i}
    measured = {r.get("id") for r in (_ink(doc_dir).get("rows") or []) if r.get("id")}
    straddle = set()
    mf = doc_dir / rt.ROWS_MANIFEST
    if mf.is_file():
        try:
            straddle = {r["identifier"] for r in
                        (json.loads(mf.read_text(encoding="utf-8")).get("rows") or [])
                        if not r.get("rules_on_one_page", True)}
        except Exception:
            straddle = set()
    gone = sorted((shown - measured) - straddle)
    if gone:
        return False, ("%d equation row(s) shown carry no measurement and do not "
                       "straddle a page: %s" % (len(gone), ", ".join(gone[:8])))
    return True, "%d equation rows shown, all measured (%d straddle)" % (
        len(shown), len(shown & straddle))


def artefacts_gate(doc_dir) -> tuple:
    missing = [f for f in PUBLISHED_FILES
               if not (Path(doc_dir) / f).is_file()
               or (Path(doc_dir) / f).stat().st_size == 0]
    if missing:
        return False, "missing: %s" % ", ".join(missing)
    return True, "all five present"


#: 634 — a genuine xelatex error always has the source line number printed a
#: few lines after it (`l.<N> ...`); a `! ` at the start of a line is not
#: enough by itself. Measured false positive: fong-spivak-seven-sketches'
#: evidence-table.log line 2270 is an Underfull \hbox trace that wraps a
#: row's own text — `yes! \\` — across the line break, leaving `! \\` sitting
#: at column 0 with no `l.N` anywhere near it (the box warning prints `[]`
#: and blank lines instead). A bare `^! ` count would have refused a file
#: that xelatex built clean. Paired within 8 lines catches every real error
#: seen (fong's `\boldsymbol{\operatorname{...}}` failures each print their
#: `l.736` on the third line after the `! `) and none of the wraps.
_TEX_LINENO = re.compile(r"^l\.\d+")


def tex_errors(log_text: str) -> int:
    r"""Count REAL xelatex errors in a .log's text — see the note above
    `_TEX_LINENO` for why a bare `^! ` count is wrong."""
    lines = log_text.splitlines()
    n = 0
    for i, line in enumerate(lines):
        if not line.startswith("! "):
            continue
        if any(_TEX_LINENO.match(l) for l in lines[i + 1:i + 9]):
            n += 1
    return n


def compile_gate(doc_dir) -> tuple:
    bad = []
    for f in PUBLISHED_FILES:
        log = (Path(doc_dir) / f).with_suffix(".log")
        if not log.is_file():
            bad.append("%s: no log" % f)
            continue
        lost = rt.glyphs_dropped(log)
        if lost is not None:
            bad.append("%s: %d dropped" % (f, lost[0]))
        # 634 — a fatal error (e.g. the `\boldsymbol{\operatorname{...}}`
        # class that truncated fong-spivak-invitation to 22 pages and
        # fong-spivak-seven-sketches to 7) can leave the document short with
        # no dropped glyph in sight; this is what would have caught it before
        # the page count did.
        n = tex_errors(log.read_text(encoding="utf-8", errors="replace"))
        if n:
            bad.append("%s: %d xelatex errors remain" % (f, n))
    return (not bad), ("clean" if not bad else "; ".join(bad))


#: back-compat: the name every existing caller/import used before 634.
glyphs_gate = compile_gate


#: 667 — a rung alone cannot answer "is the picture I am looking at the
#: picture this residual was measured on": `budget.CROP_LADDER` says how a
#: crop was ENCODED (scale, quality), never WHICH crop a row was measured
#: against, and 666 measured that a rung difference alone (same aspect ratio,
#: uniformly smaller — 655's re-encoding) is benign on 11 of 11 pairs
#: checked. So this gate is keyed on `crop_sha256` — the sha256 of the SOURCE
#: file in `report-crops/`, which every rung is derived from and which
#: `report_tex.scale_crops` never overwrites (it writes the scaled copy into
#: the separate `report-crops-b/`) — never on the embedded PDF bytes, which a
#: rung change legitimately moves. `rung` is still carried on the row (set
#: by `commands.cmd_inkconvert` at measure time) so a caller can SAY why a
#: displayed crop's bytes differ from the measured one without that being
#: mistaken for a defect.
#:
#: Rows measured before 667 carry no `crop_sha256` at all — absence is not
#: evidence of a mismatch (rule 5: no plausible default for an unknown), so
#: this check passes vacuously on them rather than refusing every document
#: measured before the field existed. That is a DELIBERATE departure from
#: publish_ready's own stated principle ("a check that cannot see its input
#: FAILS rather than passing quietly", commands.py:1624-1628) — every other
#: gate in this file honours it, this one does not, because failing outright
#: would un-publish every document measured before this task. `ok=True`
#: alone cannot say WHICH of the two passes this is, so it does not have to:
#: `GateStatus.verified` carries that, structurally — see out/667.txt for the
#: argument against the principle this departs from, made explicitly rather
#: than left for a reader to rediscover.
def crop_gate(doc_dir, bibkey: str = "", history=None) -> "GateStatus":
    doc_dir = Path(doc_dir)
    ink = _ink(doc_dir)
    rows = ink.get("rows") or []
    if not rows:
        return GateStatus(True, "no measured rows to check", verified=False)
    tagged = [r for r in rows if r.get("crop_sha256")]
    if not tagged:
        return GateStatus(True, "ink carries no crop identity (measured "
                          "before 667)", verified=False)
    crops = doc_dir / "report-crops"
    mismatched = []
    for r in tagged:
        ident = r.get("id") or "?"
        got = rt.crop_sha256(crops, ident, bibkey, history)
        if got is None:
            mismatched.append("%s: crop no longer on disk" % ident)
            continue
        if got != r["crop_sha256"]:
            mismatched.append("%s: crop changed since it was measured "
                              "(measured %s, now %s)"
                              % (ident, str(r["crop_sha256"])[:12], str(got)[:12]))
    if mismatched:
        return GateStatus(False, ("%d row(s) show a crop the ink did not "
                                  "measure: %s" % (len(mismatched),
                                                   "; ".join(mismatched[:8]))),
                          verified=True)
    return GateStatus(True, ("%d row(s) checked, every displayed crop is "
                             "the one measured" % len(tagged)), verified=True)


def checklist(doc_dir, bibkey: str = "", history=None) -> dict:
    doc_dir = Path(doc_dir)
    ink_p = doc_dir / "report.ink.json"
    live = [n for n in ("report.ink.json.REFUSED", "report.ink.json.MISPAIRED")
            if (doc_dir / n).is_file() and ink_p.is_file()
            and (doc_dir / n).stat().st_mtime >= ink_p.stat().st_mtime]
    return {
        "artefacts": artefacts_gate(doc_dir),
        "glyphs": compile_gate(doc_dir),
        "ink": ((ink_p.is_file() and not live),
                "present" if ink_p.is_file() and not live else
                ("%s is newer: the last attempt failed to pair" % live[0]
                 if live else "no report.ink.json")),
        "timestamp": timestamp_gate(doc_dir),
        "coverage": coverage_gate(doc_dir),
        "crop": crop_gate(doc_dir, bibkey=bibkey, history=history),
    }
