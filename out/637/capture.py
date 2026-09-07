#!/usr/bin/env python3
"""637 — capture the command outputs and write INSPECT.txt, NAMING THE PDF.

    python3 capture.py <document folder>

WHY THIS IS A SCRIPT AND NOT THREE SHELL REDIRECTIONS: 634's round 0 captured
with `pdfdrill conserve $DOC/*.pdf`, and EVERY PUBLISHED DOCUMENT FOLDER HOLDS
SIX PDFs — the document plus `evidence-formula.pdf`, `evidence-equation.pdf`,
`evidence-image.pdf`, `evidence-table.pdf`, `report.pdf` and `residuals.pdf`.
The glob sorted `evidence-equation.pdf` first, both captures were of the wrong
document, and the model rebuild that followed BOUGHT an 8-page MathPix
extraction nobody asked for.

So this script, like 634's: derives the document PDF from the FOLDER NAME and
never globs, refuses the six by name, refuses more than one argument, and holds
each capture's FIRST LINE to NAMING the document through `taskout`'s `expect`.
"""
import os
import subprocess
import sys
from pathlib import Path


def _repo() -> Path:
    for cand in Path(__file__).resolve().parents:
        if (cand / "src" / "docmodel" / "footnote_extent.py").is_file():
            return cand
    return Path("/home/wkolbe/MX/PDFDRILL")


REPO = _repo()
sys.path.insert(0, str(REPO / "src"))

from pdfdrill import taskout                          # noqa: E402

#: PDFs that live BESIDE a document and are never the document.
NOT_THE_DOCUMENT = ("evidence-formula.pdf", "evidence-equation.pdf",
                    "evidence-image.pdf", "evidence-table.pdf",
                    "report.pdf", "residuals.pdf")

CAPTURES = [
    ("conserve.after.txt", ["conserve"],
     "646's conservation audit on the deduplicated model — the pairs, the "
     "unclaimed and the doubly-claimed anchors, and 637's adoption line"),
    ("model-ledger.after.txt", ["model", "--ledger"],
     "634's claim ledger on the deduplicated model — read-only, refuses a "
     "stale model"),
]

#: Everything else this task wrote beside the document, with the reason.
ARTEFACTS = [
    ("script.py", "the census, runnable from here or from the repo"),
    ("capture.py", "this capture"),
    ("result.control.json", "the census of the CONTROL model (this tree with "
                            "637 stashed, rebuilt in the harness order)"),
    ("result.after.json", "the census of the model 637 built"),
    ("drill_control.txt", "the control's 22-step drill, rc 0"),
    ("drill_after.txt", "the after's 22-step drill, rc 0"),
    ("latex_control.txt", "`pdfdrill latex --force --compile`, control"),
    ("latex_after.txt", "`pdfdrill latex --force --compile`, after"),
    ("page8.png", "page 8 of the projected PDF, AFTER — read"),
    ("page8-before.png", "page 8 of the CONTROL PDF — read"),
    ("crop-page8-foot.png", "the page-8 foot, AFTER: footnotes 3 and 4 once each"),
    ("crop-page8-foot-before.png",
     "the page-8 foot, CONTROL: footnotes 3 and 4 TWICE each"),
]


def document_pdf(docdir: Path) -> Path:
    """The document's own PDF: `<folder>/<folder name>.pdf`, checked."""
    pdf = docdir / (docdir.name + ".pdf")
    if pdf.name in NOT_THE_DOCUMENT:
        raise SystemExit(f"REFUSED: {pdf.name} is an artefact that lives beside "
                         f"a document, not a document.")
    if not pdf.is_file():
        raise SystemExit(f"REFUSED: {pdf} does not exist. This script derives "
                         f"the PDF from the folder name and never globs.")
    return pdf


def main(argv) -> int:
    if len(argv) != 1:
        raise SystemExit("usage: capture.py <document folder>   (exactly one; "
                         "a glob that expanded to several is the bug this "
                         "script exists to prevent)")
    docdir = Path(argv[0]).resolve()
    pdf = document_pdf(docdir)
    out = docdir / "out" / "637"
    out.mkdir(parents=True, exist_ok=True)
    name = pdf.stem

    entries = []
    for fname, args, reason in CAPTURES:
        cmd = [str(REPO / "pdfdrill")] + args + [str(pdf)]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           env={**os.environ, "PDFDRILL_NO_PREFLIGHT": "1",
                                "PYTHONDONTWRITEBYTECODE": "1"})
        text = r.stdout + (("\n" + r.stderr) if r.stderr.strip() else "")
        (out / fname).write_text(text, encoding="utf-8")
        first = text.splitlines()[0] if text.splitlines() else ""
        ok = name in taskout._names_in(first)
        print(f"{'OK  ' if ok else 'WRONG'} {fname}: rc={r.returncode}  "
              f"{first[:90]}")
        if not ok:
            raise SystemExit(f"REFUSED: {fname}'s first line does not NAME "
                             f"{name}: {first[:120]!r}")
        entries.append((out / fname, reason, name))

    for fname, reason in ARTEFACTS:
        p = out / fname
        if p.exists():
            entries.append((p, reason))
    for fname, reason in ((f"{name}.control.tex",
                           "the CONTROL projection — 96 footnotetext blocks, "
                           "42 openings repeated"),
                          (f"{name}.after.tex",
                           "the AFTER projection — one block per Footnote, "
                           "0 openings repeated"),
                          (f"{name}.after.log", "the xelatex log, after"),
                          ("model.control.docmodel.json",
                           "the CONTROL model, kept so the census can be re-run"),
                          ("model.after.docmodel.json",
                           "the model 637 built")):
        p = out / fname
        if p.exists():
            entries.append((p, reason))
    for p, reason in ((docdir / "model.docmodel.json", "the model on disk"),
                      (docdir / "latex" / f"{name}.tex",
                       "the projection on disk"),
                      (docdir / "latex" / f"{name}.pdf",
                       "the compiled PDF on disk")):
        if p.exists():
            entries.append((p, reason))

    res = taskout.inspect_list(docdir, "637", entries)
    (out / "INSPECT-NOTES.txt").write_text(_notes(name, res), encoding="utf-8")
    print()
    print(taskout.inspect_report(res))
    if res["failed"]:
        raise SystemExit("REFUSED: a path in INSPECT.txt is a promise.")
    return 0


def _notes(name: str, res: dict) -> str:
    L = [f"637 — one \\footnotetext per Footnote object.  EVIDENCE NOTES, {name}",
         "=" * (46 + len(name)), "",
         "INSPECT.txt beside this file is the machine-readable list: one",
         "absolute path per line, every path checked to exist, to be non-empty,",
         "and — for the two command captures — to NAME this document on its",
         "first line (`expect=`, 634 fix round 1). The reasons live here.", ""]
    for a, reason in res["written"]:
        L.append(f"  {a}")
        if reason:
            L.append(f"      {reason}")
    if res["failed"]:
        L += ["", "  NOT LISTED — a path in INSPECT.txt is a promise:"]
        for a, why in res["failed"]:
            L.append(f"  {a}  <-- {why}")
    L += ["",
          "HOW THESE WERE CAPTURED",
          "  `python3 capture.py <document folder>` — it derives the PDF from",
          "  the FOLDER NAME and never globs (634's spend, whose whole cause was",
          "  `$DOC/*.pdf` in a folder holding six PDFs).",
          "",
          "THE TWO REBUILDS, AND WHY THERE WERE TWO",
          "  637 changes what the model HOLDS, so a before/after read off two",
          "  different trees would not be like for like. Both states were built",
          "  here, one at a time, in out/647b.txt's harness order:",
          "      pdfdrill model <pdf> --force",
          "      bash tools/drill_full_sandbox.sh <pdf>      (22/22 steps rc 0)",
          "      pdfdrill latex <pdf> --force --compile",
          "  the CONTROL with `git stash push -- src/` (this tree, 637 removed)",
          "  and the AFTER with it restored. MathPix took the CACHED branch on",
          "  every run — the step table says 'mathpix (cached — no re-upload)'.",
          "  NOTHING WAS RE-PURCHASED and `mathpix --force` was never run.", ""]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
