"""404 — the whole ink chain as ONE command, with a preflight that spends nothing.

WHY THIS EXISTS. Producing an ink-updated report took six steps in a fixed
order, and every one of them had a way to look like it worked:

  - `reporttex` without `--no-legend` stamps phase=reading, so the measurement
    taken against it is refused later by `publishready` with a message about a
    build you have already replaced (400). The flag was not in the manifest,
    `--help` or SKILL.md, so the first phase was unreachable from the
    documented surface.
  - `inkconvert` refuses to overwrite, so a second run silently reports the
    FIRST measurement's numbers (396: I compared a file against itself and got
    100% agreement, which was the only answer that test could give).
  - measuring a report that already carries bullets contaminates the thing
    being measured, and nothing stops you.
  - the intermediates are 66 MB a page, uncompressed.

None of that is a hard problem. All of it is order and hygiene, which is what
a command is for. `--no-legend` becomes internal here: the operator never
passes it, so it cannot be forgotten.

PREFLIGHT SPENDS NOTHING. It reads what is on disk and makes at most ONE
network request — a single crop probe, because expiry is per pdf_id and not
per crop (401 measured that: 22 of 22 published documents alive on one probe
each, five-crop samples agreeing, and the one dead document failing 107 of
107). If a paid step would be needed it says so and stops. It never runs one.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

#: 388 — measured on an A3 page at 600 dpi through the real subprocess.
SECONDS_PER_PAGE = 4.6
#: 66 MB at 600 dpi + 17 MB at 300 dpi, and the pair is deleted as each page's
#: compare finishes, so this is a HIGH-WATER mark and not a total.
MB_PER_PAGE_PEAK = 84


class Refused(Exception):
    """Preflight said no. Nothing has been spent and nothing has been written."""


def _probe(url: str, timeout: float = 20.0) -> int | str:
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(url.replace("\\&", "&"), timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:                       # noqa: BLE001 — reported, not raised
        return type(e).__name__


def preflight(pdf: Path, doc_dir: Path, *, probe: bool = True,
              probe_timeout: float = 20.0) -> dict:
    """Everything that can be known before anything is spent.

    Returns {"ok": bool, "checks": [(name, ok, detail)], "plan": {...}}.
    Every check NAMES what it looked at, and a check that cannot see its input
    fails rather than passing quietly — the rule `publishready` already
    follows, for the reason 826 gives: a test that cannot succeed reads exactly
    like a test that found nothing.
    """
    from . import inkmeasure as im
    from . import report_tex as rt

    checks: list[tuple[str, bool, str]] = []
    plan: dict = {}

    model = doc_dir / "model.docmodel.json"
    checks.append(("model", model.is_file(), str(model) if model.is_file()
                   else "no model.docmodel.json — run `pdfdrill model` first"))

    # NAMED FOR THIS DOCUMENT, not any *.lines.json in the directory. A flat
    # folder like ~/Downloads holds dozens, and the first glob hit was another
    # document's file entirely — a check that passes on someone else's
    # evidence is worse than one that fails.
    stem = pdf.stem
    lines = [q for q in (doc_dir / ("%s.lines.json" % stem),
                         pdf.parent / ("%s.lines.json" % stem)) if q.is_file()]
    checks.append(("lines.json", bool(lines),
                   str(lines[0]) if lines else
                   "no %s.lines.json beside the pdf or in the drill dir" % stem))

    # geometry — the px2mm the scan column is sized from
    geom = False
    if model.is_file():
        try:
            meta = json.loads(model.read_text(errors="replace")).get("meta", {})
            geom = bool(meta.get("pages"))
        except Exception:
            geom = False
    checks.append(("geometry", geom,
                   "page geometry on the model" if geom else
                   "the model carries no page geometry"))

    # THE SCAN COLUMN. Three ways to have one, in cost order: crops already on
    # disk, a CDN that still serves them, or a local pyramid. One probe decides
    # the middle case (401).
    # Crops are named <bibkey>_EQnnnn.jpg and report-crops/ is SHARED when
    # several documents sit in one folder, so count this document's own.
    bibkey = ""
    if model.is_file():
        try:
            bibkey = (json.loads(model.read_text(errors="replace"))
                      .get("meta", {}).get("bibkey") or "")
        except Exception:
            bibkey = ""
    crops = pdf.parent / "report-crops"
    if crops.is_dir():
        pat = "%s_*.jpg" % rt.sanitize_title(bibkey) if bibkey else "*.jpg"
        n_crops = len(list(crops.glob(pat)))
    else:
        n_crops = 0
    pyramid = (doc_dir / "viewer" / "manifest.json").is_file()
    scan_ok, scan_why = False, ""
    if n_crops:
        scan_ok, scan_why = True, "%d crops already on disk in %s" % (n_crops, crops)
    else:
        url = _first_cdn_url(model)
        if url is None:
            scan_ok, scan_why = (pyramid,
                                 "no cdn_url on the model; local pyramid present"
                                 if pyramid else
                                 "no crops, no cdn_url on the model, no pyramid")
        elif not probe:
            # 405 — a corpus sweep must not spend a 20 s network timeout per
            # document. With the probe off the scan column is UNKNOWN, and
            # unknown is reported as unknown: a sweep that silently assumed
            # 200 would report a corpus ready that nobody had checked.
            scan_ok, scan_why = (pyramid,
                                 "not probed (--no-probe); a local pyramid is "
                                 "present, so the CDN is not needed"
                                 if pyramid else
                                 "not probed (--no-probe) and no crops or "
                                 "pyramid on disk — run without --no-probe to "
                                 "decide this document")
        else:
            st = _probe(url, probe_timeout)
            if st == 200:
                scan_ok, scan_why = True, "CDN probe returned 200 (one probe: expiry is per pdf_id, 401)"
            elif pyramid:
                scan_ok = True
                scan_why = ("CDN probe returned %s — dead — but a local pyramid "
                            "is present; set PDFDRILL_CDN_BASE to serve it" % st)
            else:
                scan_why = ("CDN probe returned %s and there is no local pyramid. "
                            "Run `pdfdrill pyramid` then `pdfdrill imageserve "
                            "--background` and set PDFDRILL_CDN_BASE." % st)
    checks.append(("scan column", scan_ok, scan_why))
    plan["crops_on_disk"] = n_crops

    # NO PAID STEP. Never spend without being asked.
    paid: list[str] = []
    if not lines:
        paid.append("mathpix")
    if not n_crops and not scan_ok:
        paid.append("cdncrops")
    checks.append(("no paid step required", not paid,
                   "nothing paid is needed" if not paid else
                   "would need %s — stopping. Run it yourself if you mean to "
                   "spend." % ", ".join(paid)))

    # THE TABLE. Ordinal and column count must agree (320).
    tbl_ok, tbl_why = False, ""
    try:
        t = im.equations_table(doc_dir)
        plan["rows"] = int(t.get("rows") or 0)
        plan["columns"] = int(t.get("columns") or 0)
        plan["header"] = "every" if t.get("endhead") else "first"
        tbl_ok = bool(plan["rows"]) and bool(plan["columns"])
        tbl_why = ("equations table: ordinal 1, %d columns, %d rows, header=%s"
                   % (plan["columns"], plan["rows"], plan["header"]))
    except Exception as e:                        # MeasureRefused and friends
        tbl_why = "%s: %s" % (type(e).__name__, str(e)[:140])
    checks.append(("table ordinal/columns", tbl_ok, tbl_why))

    # DISK, at the high-water mark rather than the total.
    pages = _report_pages(doc_dir)
    plan["report_pages"] = pages
    free_mb = shutil.disk_usage(doc_dir if doc_dir.is_dir() else pdf.parent).free // (1024 * 1024)
    need = MB_PER_PAGE_PEAK * 2
    checks.append(("disk", free_mb > need,
                   "%d MB free; the PGM pair for one page peaks at ~%d MB and "
                   "is deleted as that page's compare finishes"
                   % (free_mb, MB_PER_PAGE_PEAK)))

    if plan.get("rows"):
        est_pages = pages or max(1, plan["rows"] // 4)
        plan["seconds"] = int(est_pages * SECONDS_PER_PAGE)
    return {"ok": all(ok for _, ok, _ in checks), "checks": checks, "plan": plan}


def _first_cdn_url(model: Path) -> str | None:
    if not model.is_file():
        return None
    try:
        m = json.loads(model.read_text(errors="replace"))
    except Exception:
        return None
    for o in m.get("objects", []):
        u = (o.get("props") or {}).get("cdn_url")
        if u:
            return u
    return None


def _report_pages(doc_dir: Path) -> int:
    """Pages of the LAST built report, if there is one. 0 when unknown —
    which is a legitimate answer before the first build, not an error."""
    st = doc_dir / "report.build.json"
    if st.is_file():
        try:
            return int(json.loads(st.read_text()).get("pages") or 0)
        except Exception:
            return 0
    return 0


def fresh_ink(doc_dir: Path) -> bool:
    """True when report.ink.json post-dates the measure-phase build.

    The resume condition. Compares against the SURVIVING phase=measure stamp,
    not against report.build.json — the latter is overwritten by the reading
    build and would make every finished document look resumable.
    """
    ink = doc_dir / "report.ink.json"
    stamp = doc_dir / "report.build.measure.json"
    if not ink.is_file() or not stamp.is_file():
        return False
    return ink.stat().st_mtime >= stamp.stat().st_mtime
