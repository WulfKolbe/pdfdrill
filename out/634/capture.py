#!/usr/bin/env python3
"""634 fix round 1 — capture the two command outputs, NAMING THE PDF.

    python3 capture.py <document folder>

WHY THIS IS A SCRIPT AND NOT TWO SHELL REDIRECTIONS. Round 0 captured with

    pdfdrill model --ledger $DOC/*.pdf > $DOC/out/634/model-ledger.txt

and EVERY PUBLISHED DOCUMENT FOLDER HOLDS SIX PDFs: the document itself plus
`evidence-formula.pdf`, `evidence-equation.pdf`, `evidence-image.pdf`,
`evidence-table.pdf`, `report.pdf` and `residuals.pdf`, all written by earlier
tasks. The glob sorts `evidence-equation.pdf` first, so both captures were of
the wrong document — and because that document had no model, `--ledger` (which
then rebuilt when stale) chained into MathPix and BOUGHT an 8-page extraction.

So this script:
  * derives the document PDF from the FOLDER NAME and nothing else,
  * REFUSES any of the six non-document names outright, by name,
  * refuses if more than one candidate is passed,
  * runs the two commands with that one explicit path,
  * and holds each capture's FIRST LINE to naming the document, through the
    same `taskout` rule that now guards INSPECT.txt — so a capture of the
    wrong document cannot be written here either.

`--ledger` is read-only since this fix and REFUSES a stale or absent model, so
this script can no longer cause a build or a spend even if pointed wrongly.
"""
import subprocess
import sys
from pathlib import Path


def _repo() -> Path:
    for cand in Path(__file__).resolve().parents:
        if (cand / "src" / "docmodel" / "ledger.py").is_file():
            return cand
    return Path("/home/wkolbe/MX/PDFDRILL")


REPO = _repo()
sys.path.insert(0, str(REPO / "src"))

from pdfdrill import taskout                          # noqa: E402

#: PDFs that live BESIDE a document and are never the document. Named, so the
#: refusal is a sentence and not a silent glob ordering.
NOT_THE_DOCUMENT = ("evidence-formula.pdf", "evidence-equation.pdf",
                    "evidence-image.pdf", "evidence-table.pdf",
                    "report.pdf", "residuals.pdf")

CAPTURES = [
    ("model-ledger.txt", ["model", "--ledger"], "the 634 claim ledger"),
    ("conserve.txt", ["conserve"], "646's conservation audit, the other "
                                   "instrument in the cross-check"),
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
    out = docdir / "out" / "634"
    out.mkdir(parents=True, exist_ok=True)
    name = pdf.stem

    entries = []
    for fname, args, reason in CAPTURES:
        cmd = [str(REPO / "pdfdrill")] + args + [str(pdf)]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           env={**__import__("os").environ,
                                "PDFDRILL_NO_PREFLIGHT": "1",
                                "PYTHONDONTWRITEBYTECODE": "1"})
        text = r.stdout + (("\n" + r.stderr) if r.stderr.strip() else "")
        (out / fname).write_text(text, encoding="utf-8")
        first = text.splitlines()[0] if text.splitlines() else ""
        ok = name in taskout._names_in(first)
        print(f"{'OK  ' if ok else 'WRONG'} {fname}: rc={r.returncode}  {first[:90]}")
        if not ok:
            raise SystemExit(f"REFUSED: {fname}'s first line does not NAME "
                             f"{name}: {first[:120]!r}")
        entries.append((out / fname, reason, name))

    for extra, reason in (("script.py", "the census"),
                          ("capture.py", "this capture"),
                          ("ledger.json", "the full ledger"),
                          ("result.json", "the numbers + the cross-check"),
                          ("report.txt", "format_ledger at limit 60"),
                          ("rebuild.log", "model --force + the 22-step drill"),
                          ("INSPECT.txt.prose", "")):
        p = out / extra
        if p.exists() and extra != "INSPECT.txt.prose":
            entries.append((p, reason))
    for p, reason in ((docdir / "model.docmodel.json", "the rebuilt model"),
                      (docdir / "model.docpack.json", "the packed sidecar")):
        if p.exists():
            entries.append((p, reason))

    res = taskout.inspect_list(docdir, "634", entries)
    # INSPECT.txt is `taskout`'s contract — one absolute path per line, nothing
    # else, because drillui's scanner reads it. The prose a PERSON wants goes
    # beside it rather than into it; putting sentences in INSPECT.txt would
    # break the scanner, and dropping the prose would lose the reasons.
    (out / "INSPECT-NOTES.txt").write_text(_notes(name, res), encoding="utf-8")
    print()
    print(taskout.inspect_report(res))
    if res["failed"]:
        raise SystemExit("REFUSED: a path in INSPECT.txt is a promise.")
    return 0


def _notes(name: str, res: dict) -> str:
    L = [f"634 — the claim ledger.  EVIDENCE NOTES, {name}",
         "=" * (36 + len(name)), "",
         "INSPECT.txt beside this file is the machine-readable list: one",
         "absolute path per line, every path checked to exist, to be non-empty,",
         "and — since fix round 1 — to NAME this document on its first line.",
         "The reasons live here.", ""]
    for a, reason in res["written"]:
        L.append(f"  {a}")
        if reason:
            L.append(f"      {reason}")
    if res["failed"]:
        L.append("")
        L.append("  NOT LISTED — a path in INSPECT.txt is a promise:")
        for a, why in res["failed"]:
            L.append(f"  {a}  <-- {why}")
    L += ["",
          "HOW THESE WERE CAPTURED",
          "  `python3 capture.py <document folder>` — it derives the PDF from",
          "  the FOLDER NAME and never globs. Round 0 used `$DOC/*.pdf` in a",
          "  folder holding six PDFs (the document plus evidence-formula.pdf,",
          "  evidence-equation.pdf, evidence-image.pdf, evidence-table.pdf,",
          "  report.pdf and residuals.pdf) and captured the wrong document.",
          "",
          "THE REBUILD, AND WHY THERE WAS ONE",
          "  The ledger records ATTRIBUTION at build time and attribution cannot",
          "  be recovered from a finished model — on penev_A 1271 of 1448 objects",
          "  carry no `added_by` at all. The models on disk (636's rebuild) had no",
          "  ledger, so both documents were rebuilt in out/647b.txt's harness",
          "  order, one at a time: `pdfdrill model --force` then",
          "  `bash tools/drill_full_sandbox.sh`, 22/22 steps rc 0, MathPix CACHED",
          "  (`DRILL_MATHPIX_NO_FORCE=1`; the step table says 'mathpix (cached —",
          "  no re-upload)'). It reproduced the previous state exactly.",
          ""]
    acc = Path(res["path"]).parent / "accidental"
    if acc.is_dir():
        L += ["WHAT IS IN accidental/, AND WHY IT IS NOT BESIDE THE DOCUMENT",
              "  Round 0's wrong-PDF capture ran `--ledger` on evidence-equation.pdf,",
              "  which had no model. `--ledger` then rebuilt when stale, so it",
              "  chained cmd_model -> cmd_mathpix and BOUGHT an 8-page MathPix",
              "  extraction. Nobody asked for one. The artefacts it produced are",
              "  kept (they were paid for) but moved out of the document folder,",
              "  where `status` and every glob would otherwise find them and treat",
              "  them as this document's:", ""]
        for f in sorted(p.name for p in acc.iterdir()):
            L.append(f"    accidental/{f}")
        L += ["",
              "  `model --ledger` is now READ-ONLY: it refuses a stale or absent",
              "  model and names the `pdfdrill model <pdf>` that fixes it, and",
              "  `cli._do_model` routes it before `cmd_model` so no write lock is",
              "  taken and no code path from it to a build exists.", ""]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
