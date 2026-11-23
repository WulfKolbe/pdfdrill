"""Run the external per-page INK JUDGE and read its verdict.

`verdict.assess` answers "is this reading complete?" from the model's own
object counts. That cannot see whether the reading is the same INK as the page,
so every verdict line has ended "ink: not judged" since the module was written.
This supplies the other half when, and only when, a judge is configured.

NOT the same thing as `inkjudge`, which judges ONE candidate LaTeX string for
ONE formula inside the equation cascade. This judges a reading against a page.

WHERE THE JUDGE COMES FROM, and why no path is written down here: inkdrill is
not a dependency of pdfdrill, and a fresh clone must build and test without
it (group rule 7). So the path comes from the operator —

    PDFDRILL_JUDGE=/path/to/inkcmp-judge          (first)
    config key `judge`                            (then)
    nothing                                       (then "ink: not judged")

— and an entry that does not resolve to an executable FILE is the same as no
entry, because a stale path in a config is otherwise indistinguishable from a
judge that found nothing.

WHY THIS REPORTS COUNTS AND NOT A RESIDUAL. The residual is the BOARD's
statistic, computed in drillgroup `scripts/board_run.py`:

    orig = page_chars or (glyphs + unpaired_A);   den = orig + rules_a
    residual = (glyph + (orig - glyphs) + unpaired_B
                + rules_missing + rules_invented) / den

Four separate owner decisions live in that denominator — rule ink counts on
both sides of the division; a glyph in a face TeX cannot set stays in the
denominator (2026-11-22, correcting 2026-11-21); the denominator is the PAGE's
glyph count and not the reading's, because a reading that drops 97% of a page
otherwise shrinks its own denominator and scores two orders of magnitude
better than it is (1511.08771 p2709); and a status that is not OK has no
residual at all. Reimplementing that here would be a second source of truth
that can silently disagree with the board.

It is also unnecessary. The verdict asks whether ANYTHING faulted, and
`residual > 0` holds exactly when that NUMERATOR is non-zero — a plain sum of
raw judge counts with no denominator in it. So this quotes the judge's own
counts and leaves the ratio to the board, which owns it.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple, Optional

from . import config as _cfg

#: The judge rasterizes and compiles, so one page is not instant. Measured by
#: the board on a scan page: `SCAN_TIMEOUT = 900` for the scan route, after a
#: reading was found that makes pdflatex spin forever (inkdrill-10,
#: 2026-11-21). Same budget here, per page.
TIMEOUT = 900

#: The judge's own statuses. Only OK carries a measurement; the other three say
#: the page could not be measured, which is NOT the same as measured clean.
OK = "OK"


def judge_path() -> "Optional[Path]":
    """The configured ink judge, or None. See the module docstring."""
    for raw in (os.environ.get("PDFDRILL_JUDGE"),
                _cfg.get("judge")):
        if not raw:
            continue
        p = Path(str(raw)).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return p
    return None


def parse(text: str) -> dict:
    """The judge's `JUDGE1`/`SCAN1` counts, its page glyph count and its STATUS.

    Shapes taken from the judge itself (inkdrill `judge.py`) and read the same
    way the board reads them, so the two cannot drift apart in their parsing:
    the LAST `JUDGE1 ` line wins, the counts are space-separated key/value
    pairs, `STATUS` is its own line, and the page's own glyph count comes from
    the `# page N: ... A chars NNNN` header rather than from the counts.
    """
    out: dict = {"status": "", "page_chars": 0}
    line = next((l for l in reversed(text.splitlines())
                 if l.startswith("JUDGE1 ")), None)
    scan = next((l for l in reversed(text.splitlines())
                 if l.startswith("SCAN1 ")), None)
    for l in reversed(text.splitlines()):
        if l.startswith("STATUS "):
            out["status"] = l.split(None, 1)[1].strip()
            break
    for l in text.splitlines():
        if l.startswith("# page "):
            m = re.search(r"A chars (\d+)", l)
            if m:
                out["page_chars"] = int(m.group(1))
            break
    src = line or scan
    if src is None:
        return out
    out["route"] = "scan" if (scan is not None and line is None) else "glyph"
    f = src.split()[1:]
    for j in range(0, len(f) - 1, 2):
        try:
            out[f[j]] = (float(f[j + 1]) if f[j] in ("residual", "scan")
                         else int(f[j + 1]))
        except ValueError:
            out[f[j]] = f[j + 1]
    return out


def _n(d: dict, *names: str) -> int:
    """The judge prints some counts under two spellings (`unpaired_B` and
    `b_unpaired`). Take whichever is there rather than assume one."""
    for n in names:
        v = d.get(n)
        if isinstance(v, (int, float)):
            return int(v)
    return 0


def faults(d: dict) -> "Optional[int]":
    """How much ink this page got WRONG, MISSED or INVENTED — or None when the
    judge did not measure the page.

    This is exactly the numerator of the board's residual (see the module
    docstring), and nothing else:

        glyph              ink drawn with the wrong shape
        page_chars-glyphs  the page's own glyphs the reading never paired
        unpaired_B         glyphs the reading drew where the page has none
        rules_missing      a fraction bar or overline the reading did not draw
        rules_invented     ...and one it drew where the page has no rule

    STYLE FINDINGS ARE NOT IN IT, because they are not in the board's residual
    either: a letter set upright that the page sets italic is the same ink in
    the wrong face, and the board reports it as `style_rate` beside the
    residual rather than inside it.

    None, not 0, for a status that is not OK. `FONT_UNMAPPED`, `NOT_COMPILED`
    and `NO_TEXT` mean the page was not measured; reporting that as "0 faults"
    would turn an absence of evidence into a pass, which is the whole failure
    class the verdict exists to prevent.
    """
    if d.get("status") != OK:
        return None
    if "glyphs" not in d and "scan" not in d and "residual" not in d:
        return None
    if d.get("route") == "scan":
        # The scan route reports its own residual and is NOT comparable with a
        # glyph-route one (board_run `_scan1`). For a yes/no gate only its sign
        # is needed, and that is comparable.
        r = d.get("residual", d.get("scan"))
        return None if r is None else (1 if float(r) > 0 else 0)
    paired = _n(d, "glyphs")
    orig = d.get("page_chars") or (paired + _n(d, "unpaired_A", "a_unpaired"))
    if not orig:
        return None
    return (_n(d, "glyph")
            + max(orig - paired, 0)
            + _n(d, "unpaired_B", "b_unpaired")
            + _n(d, "rules_missing")
            + _n(d, "rules_invented"))


def detail(d: dict) -> str:
    """The fault counts in the judge's own terms, for the verdict line.

    THE SCAN ROUTE'S RESIDUAL IS QUOTED, the glyph route's is not, and the
    difference is who computes it. `SCAN1` carries `residual` as a field the
    JUDGE calculated, so repeating it is quotation. The glyph residual exists
    nowhere in the judge's output -- the board builds it in `board_run.py`
    from these counts -- so printing one here would be a second
    implementation. Measured on BH1 p113:

        SCAN1 comps 1510 holes 286 invented 386 lines 44 lines_judged 44
              missing 116 not_set 0 rendered 1856 unplaced 0 residual 0.521854
    """
    if d.get("route") == "scan":
        r = d.get("residual", d.get("scan"))
        parts = [f"scan residual {float(r):.4f}"] if r is not None else []
        for key, word in (("missing", "missing"), ("invented", "invented"),
                          ("holes", "hole mismatch(es)")):
            if _n(d, key):
                parts.append(f"{_n(d, key)} {word}")
        if _n(d, "comps"):
            parts.append(f"of {_n(d, 'comps')} component(s)")
        return ", ".join(parts)
    paired = _n(d, "glyphs")
    orig = d.get("page_chars") or (paired + _n(d, "unpaired_A", "a_unpaired"))
    parts = []
    if _n(d, "glyph"):
        parts.append(f"{_n(d, 'glyph')} wrong")
    if max(orig - paired, 0):
        parts.append(f"{orig - paired} unread")
    if _n(d, "unpaired_B", "b_unpaired"):
        parts.append(f"{_n(d, 'unpaired_B', 'b_unpaired')} invented")
    if _n(d, "rules_missing") or _n(d, "rules_invented"):
        parts.append(f"{_n(d, 'rules_missing')}/{_n(d, 'rules_invented')} rule")
    return ", ".join(parts)


class Ink(NamedTuple):
    """What the judge found, as the verdict needs it."""
    pages_judged: int
    pages: int
    faults: "Optional[int]"
    page: int                 # the page that faulted, or 0
    detail: str
    status: str = OK
    route: str = "glyph"

    def line(self) -> str:
        if self.faults is None:
            st = f" ({self.status})" if self.status else ""
            return f"ink: not judged{st}"
        if not self.faults:
            return f"ink: clean on {self.pages_judged} page(s)"
        tail = (f"; judged {self.pages_judged} of {self.pages} page(s)"
                if self.pages_judged < self.pages else "")
        # THE SCAN ROUTE HAS NO COUNT OF FINDINGS, only a residual, so it must
        # not borrow the word. `faults` reduces it to a SIGN for this gate
        # (see the module docstring), and the first version of this line
        # printed that sign as "1 finding(s)" on BH1 p113 -- which reads as
        # exactly one finding on a page whose scan residual is 0.5219.
        if self.route == "scan":
            d = f" — {self.detail}" if self.detail else ""
            return f"ink: the scan route faulted on page {self.page}{d}{tail}"
        d = f" ({self.detail})" if self.detail else ""
        return f"ink: {self.faults} finding(s) on page {self.page}{d}{tail}"


def judge_document(pdf: Path, lines_json: Path, pages: int, *,
                   route: str = "glyph", work: "Optional[Path]" = None,
                   judge: "Optional[Path]" = None) -> "Optional[Ink]":
    """Judge the document's pages in order, STOPPING at the first that faults.

    One faulted page settles the verdict — it is already DEGRADED and no later
    page can change that — so the walk stops there. That is why the line says
    how many pages were judged: a run that stopped at page 1 of 400 must not
    read as a clean sweep. A clean document is judged in full, which is the
    honest cost of saying "clean".

    Returns None when there is no judge configured or nothing to judge, so the
    caller keeps today's "ink: not judged".
    """
    exe = judge or judge_path()
    if exe is None or not Path(lines_json).is_file() or pages < 1:
        return None
    work = Path(work or (Path(pdf).parent / "judge"))
    last_status = ""
    judged = 0
    for pno in range(1, pages + 1):
        wd = work / f"p{pno:04d}"
        try:
            wd.mkdir(parents=True, exist_ok=True)
            p = subprocess.run(
                [sys.executable, str(exe), str(pdf), str(pno),
                 str(lines_json), "--work", str(wd), "--route", route],
                capture_output=True, text=True, timeout=TIMEOUT)
        except (OSError, subprocess.TimeoutExpired):
            return Ink(judged, pages, None, pno, "", "JUDGE DID NOT RUN",
                       route)
        # KEEP WHAT IT SAID. The verdict quotes two or three numbers out of a
        # page of output, and the rest is the evidence for them -- the BLIND
        # line that states what the route cannot see, the per-finding rows,
        # the STATUS. The board caches it the same way (`board_run.run_scan`,
        # `judge.out`), so a disagreement between the two can be read rather
        # than re-run.
        try:
            (wd / "judge.out").write_text(
                p.stdout + ("\n--- stderr ---\n" + p.stderr if p.stderr else ""),
                encoding="utf-8")
        except OSError:
            pass
        d = parse(p.stdout)
        last_status = d.get("status") or last_status
        n = faults(d)
        if n is None:
            # not measured on this page: keep walking, because another page
            # may be measurable, but never report it as clean.
            continue
        judged += 1
        if n:
            return Ink(judged, pages, n, pno, detail(d),
                       d.get("status", OK), d.get("route", route))
    if not judged:
        return Ink(0, pages, None, 1, "", last_status or "NOT MEASURED", route)
    return Ink(judged, pages, 0, 0, "", OK, route)
