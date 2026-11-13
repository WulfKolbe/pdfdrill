"""Judge a candidate LaTeX against a formula's own scan, by ink.

An arm of the equation cascade (T-0131 rung 3, T-0144's Gemma arms) proposes a
LaTeX string for an equation. The question this module answers is whether that
string RENDERS TO THE SAME INK as the crop cut from the page — not whether it
matches a reference string, because the two rank readers oppositely: measured
on 300 confirmed rows, string-exact put crop-only ahead of pix2text 82.3 % to
66.7 % while ink put pix2text ahead 89.9 % to 73.7 % (T-0131, 2026-11-04). The
string score ignores `\\left/\\right`, spacing, environment names, braces and
`\\operatorname` vs `\\mathrm`; the ink does not.

So: inject the candidate as a `latex_candidate` realization, run the ink chain
with `--render-provenance`, and read the distance the chain measured.

THREE ANSWERS, and the third is the one that needs care:

    exact             distance 0
    differs           the distance itself
    does not compile  the report demoted the row to `\\emph{(not rendered)}`

THE `unrendered` FLAG CANNOT DECIDE THE THIRD, in either direction. Measured on
`wzlxjtu-004_EQ0004` (2026-11-13), four unrelated non-compiling candidates —
`\\nosuchmacrohere`, `\\frac`, `\\begin{array}{c} a & b`,
`\\frac{1}{ \\nosuchmacro{x` — each returned from report.ink.json:

    distance 10, comp_delta 2, flag `weak`, code `W|+2`, rendered TRUE

byte-identical for all four, because what was compared against the crop was
the ITALIC WORDS "(not rendered)" that the xelatex fixpoint had put there in
place of the formula. Left to the flag, a candidate that does not compile
scores a respectable distance of 10 and reads as a NEAR MISS, flattering any
arm that emits garbage. And the flag errs the other way too: a VALID wrong
answer on `wzlxjtu-004_EQ0002` came back `flag: unrendered, rendered: False`
in a batch while the report did not demote it at all, and its distance there,
27, is exactly what it scores alone.

`inkconvert` HAS the class (`FLAG_CODE["unrendered"] = "U"`, added because such
rows "were being classified `component`"), and it does fire — just not
reliably. So the verdict is read from the report's own text, where the
demotion is written out, and the flag only raises a suspicion.

ONE BAD CANDIDATE SPOILS ANOTHER ROW'S VERDICT. With a non-compiling candidate
on EQ0004 and a valid wrong answer on EQ0002 in ONE build, the innocent row
came back wrong — once demoted in the report, once flagged `unrendered`. Judged
alone, each was correct. Hence the registered rule (coordinator, drillgroup
59291f1, 2026-11-13): judge in batches; when a build has demotions, rerun every
suspect row of that build ALONE, and the solo verdict counts. A demoted row is
`does_not_compile`, never a distance.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Iterable

#: `\ident{...}~` — the identifier cell of a report.tex row.
_IDENT = re.compile(r"\\ident\{(.*?)\}~")
#: `_EQnnnn`, the ordinal both id schemes share.
_EQ_TAIL = re.compile(r"_EQ\d+$")

#: The role and the realization stream a candidate is injected as.
ROLE = "latex_candidate"

#: What a demoted row's Rendered cell says.
NOT_RENDERED = "(not rendered)"


def _deescape(ident: str) -> str:
    """Undo the projector's escaping of an identifier inside `\\ident{...}`."""
    out = ident.replace("\\allowbreak{}", "")
    for esc, raw in (("\\_", "_"), ("\\&", "&"), ("\\%", "%"), ("\\#", "#"),
                     ("\\$", "$"), ("\\{", "{"), ("\\}", "}")):
        out = out.replace(esc, raw)
    return out.strip()


def unrendered_ids(report_tex: Path) -> set[str]:
    """The identifiers whose Rendered cell is `\\emph{(not rendered)}`.

    This is the authoritative "did not compile" signal — see the module
    docstring for why the `unrendered` flag is not.
    """
    if not report_tex.is_file():
        return set()
    out: set[str] = set()
    for line in report_tex.read_text(errors="replace").splitlines():
        if NOT_RENDERED not in line:
            continue
        m = _IDENT.search(line)
        if m:
            out.add(_deescape(m.group(1)))
    return out


def object_for_row(titles_by_id: Callable, sanitize: Callable, doc,
                   bibkey: str, row_id: str, *,
                   allow_ordinal_fallback: bool = False) -> "str | None":
    """The object id a cascade `row_id` names, trying all three spellings.

    THE ROW ID AND THE TITLE ARE SPELLED DIFFERENTLY and matching them raw
    loses every document whose name carries punctuation. An arm builds
    `<folder name>_EQnnnn` from the RAW folder name; this project's titles are
    SANITISED (spaces and punctuation become underscores). For an arXiv id the
    two are identical, which is why a raw match looks fine on a sample of
    papers and then loses the books: measured 2026-11-03, 199 of 233 documents
    joined raw, and the 34 that did not held 15,394 of 22,385 rows — 69 % of
    the work, reported as "the join matched 0 of N rows".

        arm      : Algebraic Number Theory (DISCRETE ...) (Z-Library)_EQ0001
        project  : Algebraic_Number_Theory__DISCRETE_..._Z-Library__EQ0001

    The third spelling is for the renamed-stem case (defect 516): the model's
    bibkey is the RESOLVED key, so its titles read `<bibkey>_EQnnnn` while the
    arm built `<folder name>_EQnnnn`. It is a PREFIX substitution on the shared
    ordinal, applied only when both spellings above have failed and the id ends
    in `_EQ<digits>`, so it can never override a match the document's own
    naming produced.

    IT IS OFF BY DEFAULT, because it is a guess and it matches ACROSS
    DOCUMENTS. `someotherdoc_EQ0001` ends in `_EQ0001`, so the substitution
    turns it into this document's first equation and judges it there —
    measured, distance 8, reported as a result. One candidates file shared
    across the documents an arm covers is the intended use, so with the
    fallback on by default every document would silently judge every other
    document's rows against its own equations.

    Turn it on only for a document KNOWN to have been renamed, and only with a
    candidates file that belongs to it.
    """
    titles = titles_by_id(doc, bibkey)
    id_for = {sanitize(t): i for i, t in titles.items()}
    for key in (row_id, sanitize(row_id)):
        if key in id_for:
            return id_for[key]
    tail = _EQ_TAIL.search(row_id) if allow_ordinal_fallback else None
    if tail:
        cand = sanitize(bibkey) + tail.group(0)
        if cand in id_for:
            return id_for[cand]
    return None


def inject(doc, bibkey: str, rows: Iterable[dict], provenance: str, *,
           titles_by_id: Callable, sanitize: Callable, realization_cls,
           allow_ordinal_fallback: bool = False) -> tuple[int, list[str], dict]:
    """Put each candidate on the object its `row_id` names.

    Replaces any realization this provenance already left, so a second pass
    measures the candidate it was given and not the one before it. Returns
    (injected, row_ids with no object, title -> row_id alias for the report).
    """
    injected, missing, alias = 0, [], {}
    titles = titles_by_id(doc, bibkey)
    for r in rows:
        rid = str(r.get("row_id") or "")
        oid = object_for_row(titles_by_id, sanitize, doc, bibkey, rid,
                             allow_ordinal_fallback=allow_ordinal_fallback)
        if oid is None:
            missing.append(rid)
            continue
        obj = doc.objects[oid]
        alias[sanitize(titles.get(oid, ""))] = rid
        obj.realizations = [x for x in obj.realizations
                            if not (getattr(x, "role", "") == ROLE
                                    and getattr(x, "provenance", "") == provenance)]
        obj.add_realization(realization_cls(
            stream=provenance, role=ROLE, provenance=provenance, score=None,
            props={"latex": r.get("latex") or "",
                   "reader": str(r.get("reader") or provenance)}))
        injected += 1
    return injected, missing, alias


def read_pass(ink_json: Path, report_tex: Path, alias: dict) -> tuple[dict, set]:
    """The rows the chain measured, and the ones it demoted.

    Only rows the chain says it RENDERED FROM THE PROVENANCE are returned:
    naming a provenance is not rendering it, and a report that rendered none of
    them measured the model's own LaTeX against its own crop — which looks like
    a result and is not one.
    """
    if not ink_json.is_file():
        return {}, set()
    data = json.loads(ink_json.read_text(encoding="utf-8", errors="replace"))
    against = data.get("measured_against") or {}
    rendered = set(against.get("rendered_ids") or [])
    out: dict = {}
    for row in data.get("rows") or []:
        rid = row.get("id")
        if rendered and rid not in rendered:
            continue
        key = alias.get(rid, rid)
        out[key] = {
            "report_id": rid,
            "distance": row.get("distance"),
            "comp_delta": row.get("comp_delta"),
            "flag": row.get("flag"),
            "code": row.get("code"),
            "rendered": row.get("rendered"),
            "crop_sha256": row.get("crop_sha256"),
            "build_commit": against.get("commit"),
            "build_sha256": against.get("sha256"),
            "geometry_sha256": against.get("geometry_sha256"),
            "glyphs_dropped": against.get("glyphs_dropped"),
            "rendered_from_provenance": against.get("rendered_from_provenance"),
        }
    demoted = {alias.get(x, x) for x in unrendered_ids(report_tex)}
    return out, demoted


def suspects(measured: dict, demoted: set) -> set:
    """Rows whose compilation is in doubt after a batch.

    The report's demotions, PLUS anything the `unrendered` flag points at — the
    flag decides nothing, but it is the only other witness, and a row it
    suspects is cheap to re-ask alone.
    """
    out = set(demoted)
    for rid, v in measured.items():
        if v.get("flag") == "unrendered" or v.get("rendered") is False:
            out.add(rid)
    return out


def verdict(v: "dict | None", demoted: bool) -> str:
    if v is None:
        return "not_measured"
    if demoted:
        return "does_not_compile"
    d = v.get("distance")
    if d is None:
        return "not_comparable"
    return "exact" if d == 0 else "differs"


def record(row_id: str, doc_name: str, provenance: str, v: "dict | None", *,
           demoted: bool, batch_demoted: bool, batch_flagged: bool,
           solo_rerun: bool, build_demotions: int, extra: "dict | None" = None
           ) -> dict:
    """One judged row, in the cascade's shape.

    A DEMOTED ROW REPORTS NO DISTANCE. The number the chain produces for it is
    the ink of the words "(not rendered)" against the crop — constant for every
    non-compiling candidate — so publishing it as a distance would read as a
    near miss. It is kept as `placeholder_distance`, named for what it is.
    """
    vd = verdict(v, demoted)
    d = (v or {}).get("distance")
    out = {
        "row_id": row_id, "doc": doc_name, "provenance": provenance,
        "verdict": vd, "exact": vd == "exact",
        "distance": None if vd == "does_not_compile" else d,
        "placeholder_distance": d if vd == "does_not_compile" else None,
        "comp_delta": None if vd == "does_not_compile" else (v or {}).get("comp_delta"),
        "flag": (v or {}).get("flag"), "code": (v or {}).get("code"),
        "demoted_in_report": demoted,
        "batch_demoted": batch_demoted,
        "batch_flag_said_unrendered": batch_flagged,
        "solo_rerun": solo_rerun,
        "build_had_demotions": build_demotions,
        "crop_sha256": (v or {}).get("crop_sha256"),
        "build_commit": (v or {}).get("build_commit"),
        "geometry_sha256": (v or {}).get("geometry_sha256"),
        "glyphs_dropped": (v or {}).get("glyphs_dropped"),
    }
    if extra:
        out.update(extra)
    return out
