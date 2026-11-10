r"""`pdfdrill acceptance` — run the owner's own one-line commands and check them.

NOT `selftest`: that verb is TAKEN (`pdfdrill selftest <pdf|dir> [--full]`, a
diagnostic grid that runs the command battery over a given PDF and logs
OK/n-a/ERROR per command). T-0136 asked for `selftest`; redefining a shipped
verb would break it, and CLAUDE.md names reinvention-on-top-of-an-existing-
capability as a recurring failure here (`cmd_tiddlers`, `cmd_okf`). So this is
`acceptance`, which is already this project's word for the thing it does:
CLAUDE.md, "At the end: acceptance is a real command in bash."

OWNER, 2026-11-10: "I have lost more less any trust in the CLIs ... I want to
call basic program code and see the results ... organize tests that does not use
any path, prefixes, or complex command lines."

So every line here is a line the owner can type: a bare command, a bare
document id, no paths, no flags, no environment variables. The suite proves the
code; this proves the PROGRAM — and the gap between those two was the whole of
2026-11-10. The suite was 6,331 green that morning while `add` did not exist,
`md` exceeded drillui's timeout, `steps` and `--ensure` disagreed about one
document, and the owner's terminal silently ran another session's branch. Every
one of those lived outside the suite because nothing in it ran the installed
entry point on a real document from a clean directory.

WHAT A LINE IS CHECKED FOR
--------------------------
`expect` substrings must all appear in the output, `forbid` substrings must not,
and `budget_s` fails a line that returns the right answer too slowly. The budget
is a real check, not a nicety: `pdfdrill md 2209.02970` produced byte-identical
markdown before defect D2 was fixed and took 476.78 s doing it, so drillui
killed it at 180 s and the owner met a timeout. A check on output alone passed
throughout.

NOT RUN IS NOT A PASS
---------------------
A gated line is reported NOT RUN, with the reason, and never silently dropped.
CLAUDE.md's rule 6 says the same for every acceptance run here. An acceptance run that
omits what it cannot do reports a health it has not measured — which is the
failure mode the owner has just spent a day finding in this project.

THE GATE IS DETECTED, NOT ASSUMED
---------------------------------
`preflight.is_gated` / `is_attested` decide per line, so the moment the owner
settles the token question the gated lines start running with no edit here.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

#: The folder selftest runs its commands in. Created beside the caller's cwd,
#: VISIBLE and named — never /tmp, never a dot-name (house rules 2026-10-30).
#: Reused across runs, so repeated runs do not litter (DESIGN.md D-7).
RUN_DIR = "pdfdrill-acceptance"

#: A document every line below names by its BARE ID. pdfdrill resolves it; if
#: the library already holds it nothing is downloaded.
DOC = "2209.02970"

#: One row per line of OWNER-TESTS.md, in its order. `tests/test_acceptance_lines.py`
#: fails if the two drift, so the document the owner reads and the lines that
#: run cannot disagree.
LINES: list[dict] = [
    # --- A. does it run at all -------------------------------------------
    {"id": "A1", "argv": ["doctor"],
     "expect": ["Code:", "entry point:", "branch:", "commit:", "System tools:"],
     "why": "the five identity fields, then the tools"},
    {"id": "A2", "argv": ["config"],
     "expect": ["config file"], "why": "names its own config"},
    {"id": "A3", "argv": ["help"],
     "expect": ["pdfdrill"], "forbid": ["Traceback"],
     "why": "the command list, and no traceback"},
    {"id": "A4", "argv": ["nonsense-command"],
     "expect": ["Unknown command"], "exit": 1,
     "why": "an unknown command is refused, not ignored"},
    # --- B. does it read a document it already has ------------------------
    {"id": "B1", "argv": ["size", DOC], "expect": ["21"],
     "why": "21 pages"},
    {"id": "B2", "argv": ["route", DOC], "expect": [],
     "why": "names a lane"},
    {"id": "B3", "argv": ["steps", "md", DOC],
     "expect": ["prerequisites satisfied"], "forbid": ["model, md"],
     "why": "D3: the bare id must not plan a model rebuild"},
    # `pdfdrill fonts` is a one-line SUMMARY that names math fonts only
    # ("Uses 89 font families. including math fonts (CMMI6, …)") -- D5 in the
    # user-facing command: the CID font that drops 216 glyphs on page 1 does
    # not appear in it. The structured per-font records are `fonts_layer`.
    # BOTH `fonts` and `fonts_layer` print only a SUMMARY, and the only fonts
    # either ever names are the MATH ones ("Math fonts: 6 (CMMI10, …)"). That is
    # D5 seen from the owner's side: no pdfdrill command can tell you this
    # document carries a `CID TrueType / Identity-H` font with `uni no`, which
    # is what predicts the 216 glyphs D1 drops from page 1. So this line checks
    # the count, which is what the program does report and which would move if
    # font reading broke; the gap is recorded in OWNER-TESTS.md §D, unfixed,
    # instead of being left here as a permanently red line.
    {"id": "B4", "argv": ["fonts_layer", DOC], "expect": ["92 font records"],
     "why": "the font records are read (D5: none of them is named)"},
    # --- C. does it produce the output, and quickly -----------------------
    {"id": "C1", "argv": ["md", DOC],
     "expect": ["Markdown"], "budget_s": 10.0,
     "why": "D2: 476.78 s before the fix, 0.95 s after"},
    {"id": "C2", "argv": ["model", DOC], "expect": ["Paragraph"],
     "budget_s": 60.0, "why": "a model with paragraphs"},
]


#: What the preflight gate says when it refuses. Matched in the OUTPUT rather
#: than predicted from `preflight.blocks`, because predicting got A4 wrong: an
#: unknown command is "not exempt" and therefore looks gated, while pdfdrill
#: refuses an unknown command BEFORE the gate and answers "Unknown command" --
#: which is exactly what A4 checks. A runner that predicts the program can be
#: wrong about the program; one that reads its output cannot.
GATE_MARK = "BLOCKED until you attest"


def _gate_reason(out: str, code: int) -> str | None:
    """The reason this line did not really run, read from what it printed."""
    if GATE_MARK in out:
        return ("preflight gate: BLOCKED until a token is attested, per working "
                "directory (owner decision open — OWNER-TESTS.md §D)")
    return None


def _one(exe: list[str], line: dict, cwd: Path) -> dict:
    argv = line["argv"]
    t0 = time.monotonic()
    try:
        r = subprocess.run(exe + argv, cwd=str(cwd), capture_output=True,
                           text=True, timeout=max(line.get("budget_s", 120) * 6, 300))
    except subprocess.TimeoutExpired:
        return {**line, "state": "FAIL", "seconds": time.monotonic() - t0,
                "detail": "timed out"}
    secs = time.monotonic() - t0
    out = (r.stdout or "") + (r.stderr or "")
    why = _gate_reason(out, r.returncode)
    if why:
        return {**line, "state": "NOT RUN", "detail": why, "seconds": secs}

    problems: list[str] = []
    want_exit = line.get("exit", 0)
    if r.returncode != want_exit:
        problems.append(f"exit={r.returncode}, wanted {want_exit}")
    for s in line.get("expect", []):
        if s not in out:
            problems.append(f"missing {s!r}")
    for s in line.get("forbid", []):
        if s in out:
            problems.append(f"present but forbidden: {s!r}")
    budget = line.get("budget_s")
    if budget is not None and secs > budget:
        problems.append(f"took {secs:.2f}s, budget {budget:.0f}s")

    return {**line, "seconds": secs,
            "state": "FAIL" if problems else "pass",
            "detail": "; ".join(problems) or (out.strip().splitlines() or [""])[0][:70]}


def run(args=()) -> str:
    """Run every owner line and report. Non-zero exit if any FAILs."""
    only = [a for a in args if not a.startswith("-")]
    cwd = Path.cwd() / RUN_DIR
    cwd.mkdir(parents=True, exist_ok=True)

    # The INSTALLED entry point when there is one, because that is what the
    # owner types; `python -m` only as a fallback, and the report says which.
    import shutil
    exe = ([shutil.which("pdfdrill")] if shutil.which("pdfdrill")
           else [sys.executable, "-m", "pdfdrill"])
    rows = [_one(exe, ln, cwd) for ln in LINES
            if not only or ln["id"] in only or ln["id"][0] in only]

    width = max(len(r["why"]) for r in rows) if rows else 10
    out = [f"pdfdrill acceptance — the owner's one-line commands",
           f"  entry point : {' '.join(exe)}",
           f"  run in      : {cwd}", ""]
    for r in rows:
        cmd = "pdfdrill " + " ".join(r["argv"])
        out.append(f"  [{r['state']:7s}] {cmd:34s} {r['seconds']:6.2f}s  "
                   f"{r['why']:<{width}}  {r['detail']}")
    n_fail = sum(1 for r in rows if r["state"] == "FAIL")
    n_skip = sum(1 for r in rows if r["state"] == "NOT RUN")
    n_pass = sum(1 for r in rows if r["state"] == "pass")
    out += ["", f"{n_pass} passed, {n_fail} failed, {n_skip} NOT RUN "
                f"(a NOT RUN is not a pass — see OWNER-TESTS.md §D)"]
    text = "\n".join(out)
    # A NOT RUN IS NOT A PASS, AND THE EXIT CODE HAS TO SAY SO (rule 11, and
    # CLAUDE.md rule 6). The report said "2 NOT RUN" in prose while exiting 0,
    # so any script or CI step reading only the status read it as success —
    # which is the precise shape of the failure this whole task exists to end:
    # a green signal over work that was never done. 1 = a line FAILED,
    # 3 = every line that ran passed but some could not run.
    if n_fail:
        from .cli import Report
        return Report(text, exit_code=1)
    if n_skip:
        from .cli import Report
        return Report(text, exit_code=3)
    return text
