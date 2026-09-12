"""673 — inkdrill's formula marks as `pdfdrill marks`, an external tool
called by path, never a code integration.

pdfdrill CONSUMES inkdrill: `tools/formulamarks.py marks <key>` runs as a
subprocess, exactly as `regionink.py`/`refine.ink_signature` already do.
Its own docstring states the contract this module exists to keep: "one
JSON document on stdout, progress on stderr". `subprocess.run(...,
capture_output=True)` already keeps the two in separate buffers — only
`r.stdout` is ever parsed here, and it is parsed BEFORE anything touches
disk. The controller ran this flow by hand on 2026-09-11 with a
throwaway script that merged the two streams (`2>&1` in spirit), and
every marks file it produced gained inkdrill's progress text and then
failed downstream with "Extra data: line 2 column 1" — a defect this
module and its tests exist so nobody reintroduces.

THE KEY. inkdrill's `--library ROOT KEY` opens `ROOT/KEY` literally, so
its key is always the LIBRARY FOLDER NAME. For an arXiv id that is also
pdfdrill's own bibkey (the SITE SLUG published to the tiddler wiki, from
`commands.resolve_bibkey`) because the folder IS named for the id; for a
Z-Library book it is not — `gilmore-lie-groups` (the clean bibkey) vs
"Lie Groups, Physics and Geometry - ... - R. Gilmore (" (the messy
download title inkdrill's own `index.json` and every `marks.json`'s
`bibkey` field actually use). The controller's second 2026-09-11 defect
was resolving every document by the site slug alone: it works for
arXiv ids and finds nothing for books, silently, because a directory
that does not exist looks exactly like a document with no marks. Both
keys are tried here, in the order inkdrill actually uses, and an
ambiguous result (both existing, and different) is refused rather than
picked.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .refine import inkdrill_root, InkUnavailable
from .taskout import LIBRARY

#: Where the controller's by-hand `formulamarks.py run` measurements
#: already live, one folder per document (`<key>/work/`, `<key>/marks.json`),
#: documented in `~/inkdrill-marks/README.md`. `pdfdrill marks` never runs
#: the measurement itself (minutes per book) — only inkdrill's own cheap
#: `marks` re-emit from a finished run.
MARKS_ROOT = Path.home() / "inkdrill-marks"

#: Relative to inkdrill's own checkout (`refine.inkdrill_root()`).
TOOL = "tools/formulamarks.py"


class MarksRefused(Exception):
    """inkdrill refused the document, its stdout was not the one JSON
    document it promises, or the key could not be resolved without
    guessing. No marks.json is written for any of these — a refusal
    must never be reported as success."""


def candidate_keys(pdf: Path, site_key: str) -> list[tuple[str, str]]:
    """[(label, key), ...] to try, library folder name FIRST.

    The folder name is what inkdrill actually keys every document by, so
    it is tried first and, whenever it differs from `site_key`, the site
    slug is tried only second — never instead of it. That order is the
    fix for the second 2026-09-11 defect: the controller's script tried
    the site slug ALONE and first, and it silently found nothing for the
    9 of 20 documents that are books.
    """
    folder_key = Path(pdf).resolve().parent.name
    out = [("library folder name", folder_key)]
    if site_key != folder_key:
        out.append(("pdfdrill bibkey (site slug)", site_key))
    return out


def has_run(marks_root: Path, key: str) -> bool:
    """A finished `formulamarks.py run` sits at `marks_root/key/work/` —
    the one thing `marks` (the cheap re-emit) requires to exist already."""
    return (marks_root / key / "work" / "meta.json").is_file()


def resolve_key(pdf: Path, site_key: str, *,
                marks_root: Path = MARKS_ROOT) -> tuple[str, str]:
    """(key, matched_by): the ONE key with a finished inkdrill run under
    `marks_root`.

    Raises MarksRefused, naming every key tried, when NONE has a
    finished run, and — the never-guess-silently case — when MORE THAN
    ONE does: an ambiguity between the folder name and the site slug is
    never settled by picking one, only by a caller passing `--key`
    explicitly.
    """
    candidates = candidate_keys(pdf, site_key)
    found = [(label, key) for label, key in candidates
             if has_run(marks_root, key)]
    if not found:
        tried = "; ".join(
            f"{label} {key!r} (no {marks_root / key / 'work' / 'meta.json'})"
            for label, key in candidates)
        raise MarksRefused(
            f"no finished inkdrill run for {Path(pdf).name} under "
            f"{marks_root} — tried {tried}")
    if len(found) > 1:
        raise MarksRefused(
            "both the library folder name and pdfdrill's own bibkey "
            f"resolve to a finished run under {marks_root} ("
            + " and ".join(f"{label} {key!r}" for label, key in found)
            + ") — pass --key explicitly rather than have this guess "
              "which one is current")
    label, key = found[0]
    return key, label


#: 673 review, finding 1 — the two files inkdrill's own `_inputs()` reads
#: BEFORE doing anything else (`tools.formulafind.rows(doc/"evidence-
#: formula.tex")`, then `hashlib.sha256((doc/f"{bib}.lines.json").read_bytes())`),
#: mapped to the pdfdrill command that produces each. A document can have a
#: finished `formulamarks.py run` (`has_run()` true) and still be missing
#: either — the run measured against a build that has since had its
#: evidence/model artifacts cleaned, say — and formulamarks.py does not
#: check for them itself: it crashes with an uncaught FileNotFoundError,
#: stdout empty, stderr a raw Python traceback. Checked here so that
#: reachable failure is a clean, typed refusal naming the missing file and
#: its fix, not a truncated stderr fragment.
def _prereq_files(key: str) -> dict[str, str]:
    return {
        "evidence-formula.tex":
            "pdfdrill evidence <pdf> --kind formula (or --all-kinds) --pdf",
        f"{key}.lines.json": "pdfdrill model <pdf>",
    }


def run(key: str, *, marks_root: Path = MARKS_ROOT,
       library: Path = LIBRARY, timeout: float = 120.0) -> dict:
    """Run inkdrill's `tools/formulamarks.py marks <key>` and return the
    parsed JSON — stdout only, parsed before anything is written to disk.

    Raises InkUnavailable when inkdrill (or its formulamarks.py tool) is
    not there at all; MarksRefused when either of the two files inkdrill's
    own `_inputs()` reads before doing anything else is missing from
    `library/key` (see `_prereq_files` — checked here, BEFORE the
    subprocess even starts, because inkdrill does not check for them
    itself and crashes with an uncaught FileNotFoundError instead), or
    when the subprocess produced no parseable JSON on stdout. None of
    these is a traceback and none is a silent skip — all three are typed
    and name what was tried or what is missing.
    """
    root = inkdrill_root()
    tool = root / TOOL
    if not tool.is_file():
        raise InkUnavailable(f"inkdrill's {TOOL} not found at {tool}")
    doc = library / key
    missing = [(name, fix) for name, fix in _prereq_files(key).items()
              if not (doc / name).is_file()]
    if missing:
        detail = "; ".join(f"{name!r} (run `{fix}`)" for name, fix in missing)
        raise MarksRefused(
            f"{doc} is missing what inkdrill's formulamarks.py marks reads "
            f"before doing anything else — it would crash with an uncaught "
            f"FileNotFoundError rather than a clean refusal: {detail}")
    work = marks_root / key / "work"
    cmd = ["python3", str(tool), "marks", key,
          "--library", str(library), "--work", str(work)]
    # capture_output=True keeps stdout and stderr in SEPARATE buffers —
    # this is the one line that must never gain stderr=subprocess.STDOUT.
    # tests/test_inkmarks.py pins both the call shape and the behaviour.
    r = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True,
                       timeout=timeout)
    out = (r.stdout or "").strip()
    if not out:
        raise MarksRefused(
            f"inkdrill's formulamarks.py marks produced no stdout for "
            f"{key!r} (rc={r.returncode}): {(r.stderr or '').strip()[-500:]}")
    try:
        doc = json.loads(out)
    except ValueError as e:
        raise MarksRefused(
            f"inkdrill's stdout for {key!r} was not one JSON document "
            f"({e}); first 200 chars: {out[:200]!r}") from e
    return doc
