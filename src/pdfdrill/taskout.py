r"""525 — where a task's evidence lives.

THE RULE. Nothing runs in a scratchpad except intermediates that can be
recreated on demand. Every measurement writes its script and its result
beside the document it measured, in the library, and the report names those
paths.

447 established this for LLM calls — every prompt and every reply kept
beside the document — and it was never generalised to measurements. The
cost of not generalising it, audited in out/525.txt: of the last twenty
tasks, nine left no script anywhere at all, five left one only in a
session-local `/tmp` scratchpad, and exactly one committed its data.

WHY BESIDE THE DOCUMENT AND NOT IN THE REPO. The repo is public and the
library is deny-by-default git — its `.gitignore` opens with `/*`, so a
path under `<document>/out/` cannot be committed by accident. Measurements
quote copyrighted text; reports about them do not. This puts the evidence
where the document is and keeps it out of the public tree.

WHAT A READER GETS. `<document>/out/<NNN>/` holds `script.py` — the exact
source that ran — and whatever data it produced. Re-running `script.py`
reproduces the numbers, which is the property no prose report has.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

#: corpus-wide measurements have no single document; they live at the root
#: of the library, under the same `out/<NNN>/` shape.
LIBRARY = Path.home() / "pdfdrill-library"

_TASK = re.compile(r"^\d{3,4}[a-z]?$")


def task_dir(target: "Path | str | None", task: "str | int",
             create: bool = True) -> Path:
    r"""`<target>/out/<task>/`. `target=None` means the library root.

    A corpus scan measures no one document, so it writes to
    `~/pdfdrill-library/out/<task>/` rather than picking a document
    arbitrarily — an arbitrary choice is how evidence gets lost.
    """
    t = str(task)
    if not _TASK.match(t):
        raise ValueError("task must look like 517 or 517b, got %r" % (task,))
    base = LIBRARY if target is None else Path(target)
    if base.is_file():
        base = base.parent
    d = base / "out" / t
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def save_script(target, task, source: str, name: str = "script.py") -> Path:
    """Write the exact source that ran. This is the reproducible part."""
    p = task_dir(target, task) / name
    p.write_text(source, encoding="utf-8")
    return p


def _write(p: Path, text: str) -> Path:
    r"""Write UTF-8, surviving unpaired surrogates.

    504's lesson, and it bit this module on its first corpus run: 18 library
    folders carry CP1252 bytes that arrive as lone surrogates (`\udce8`), and
    `write_text` raises on them. A census that dies on one filename is a
    census with an unknown hole, so the byte is replaced and the file is
    written rather than the run being lost.
    """
    p.write_bytes(text.encode("utf-8", "replace"))
    return p


def save_json(target, task, name: str, obj) -> Path:
    p = task_dir(target, task) / (name if name.endswith(".json")
                                  else name + ".json")
    return _write(p, json.dumps(obj, indent=1, ensure_ascii=False,
                                default=str))


def save_text(target, task, name: str, text: str) -> Path:
    return _write(task_dir(target, task) / name, text)


def paths(target, task) -> list:
    """Every file the task left, for the report to NAME rather than describe."""
    d = task_dir(target, task, create=False)
    return sorted(p for p in d.glob("*") if p.is_file()) if d.is_dir() else []


def report_lines(target, task) -> str:
    """The block a report pastes so the paths are in the record, not the chat."""
    ps = paths(target, task)
    if not ps:
        return "  (nothing written — this task left nothing inspectable)"
    return "\n".join("  %s  (%d bytes)" % (p, p.stat().st_size) for p in ps)


#: 543 — the file a PERSON opens. 525 put the script and the data beside the
#: document, which made a run re-runnable; neither is inspectable. A person
#: opens a PDF, an HTML page, an image or a log.
INSPECT_FILE = "INSPECT.txt"


def inspect_list(target, task, entries) -> dict:
    r"""Write `INSPECT.txt` — one absolute path per line, nothing else.

    `entries` is [(path, reason)] or [(path, reason, expect)]. The reason does
    NOT go in the file: the file is read by drillui's scanner, and the report
    carries the reasons.

    `expect` — 634 fix round 1 — is a string (or list of strings) the file's
    FIRST LINE must NAME, and it exists because existence is not enough. A capture of `pdfdrill model --ledger` and `pdfdrill conserve` was
    taken with a `*.pdf` GLOB in a document folder holding six PDFs
    (`evidence-formula.pdf`, `evidence-equation.pdf`, `evidence-image.pdf`,
    `evidence-table.pdf`, `report.pdf`, `residuals.pdf` sit beside the
    document in every published folder). The glob matched
    `evidence-equation.pdf`; both captures were of the WRONG DOCUMENT, both
    existed, both were non-empty, and INSPECT.txt certified them as the
    document's own. Every command whose output names its subject on line one
    can now be held to it, and a file that names something else is NOT
    written — it goes to `failed` like a missing path, because a path that
    describes another document is a broken promise in the same way.

    NAMES, NOT CONTAINS. The wrong capture's real first line was
    `Uploading /home/wkolbe/pdfdrill-library/penev_A/evidence-equation.pdf...`
    — which CONTAINS "penev_A", inside the folder path. A substring test
    passes it, so the first version of this check would not have caught the
    defect it was written for. The rule is therefore: the first line names X
    when some WHITESPACE-SEPARATED TOKEN of it, minus surrounding punctuation
    and minus any extension, IS X — and a token holding a path separator is
    not a name (`conserve penev_A: NOT CONSERVED` and `CLAIM LEDGER — penev_A
    (stream mathpix_lines)` name it; a path mentioning the folder does not).
    A command that identifies its subject only by full path cannot be checked
    this way, and should not pass `expect` rather than being given a weaker
    rule.

    A PATH IN THAT FILE IS A PROMISE. 408 established that presenting an
    unreachable path is only half of reachable, so every path is checked for
    existence and for a non-zero size before it is written, and one that
    fails is NOT written — it is returned under `failed` for the report to
    say so. A list that quietly contains a dead path is worse than a short
    list.

    Returns {"path", "written" [(abs, reason)], "failed" [(abs, why)],
             "whitespace" [abs]}.

    `whitespace` is the paths that exist and are non-empty but contain a
    space. They are written, because the file is line-based and a line is
    unambiguous — but drillui's scanner splits on whitespace, so it cannot
    open them. Roughly half this library's folder names contain spaces
    ("Geometric, Algebraic and Topological Methods ..."), so this is not an
    edge case and it is named rather than silently dropped.
    """
    d = task_dir(target, task)
    written, failed, spacey = [], [], []
    for item in entries:
        p, reason, expect = _entry(item)
        ap = Path(p).resolve()
        if not ap.exists():
            failed.append((str(ap), "does not exist"))
            continue
        if ap.is_file() and ap.stat().st_size == 0:
            failed.append((str(ap), "exists but is empty"))
            continue
        if expect:
            missing = _first_line_missing(ap, expect)
            if missing is not None:
                failed.append((str(ap), missing))
                continue
        written.append((str(ap), reason))
        if " " in str(ap) or "\t" in str(ap):
            spacey.append(str(ap))
    out = d / INSPECT_FILE
    out.write_bytes(("\n".join(a for a, _ in written) + "\n")
                    .encode("utf-8", "replace"))
    return {"path": str(out), "written": written, "failed": failed,
            "whitespace": spacey}


def _entry(item):
    """(path, reason, expect) from a bare path, a 2-tuple or a 3-tuple."""
    if not isinstance(item, (tuple, list)):
        return item, "", None
    if len(item) >= 3:
        return item[0], item[1], item[2]
    if len(item) == 2:
        return item[0], item[1], None
    return item[0], "", None


#: How much of a file to read when checking its first line. Bounded so a
#: 1.7 MB lines.json listed by mistake costs a read of 8 KB, not of all of it.
_FIRST_LINE_BYTES = 8192


def _first_line_missing(ap: Path, expect) -> "str | None":
    """None when the file's first line names everything `expect` asks for;
    otherwise the sentence `failed` should carry.

    Read as bytes and decoded with `errors="replace"` for the same reason
    `_write` encodes that way: 18 library folders carry CP1252 bytes, and a
    check that raises on one of them is a check with an unknown hole.
    """
    wants = [expect] if isinstance(expect, str) else list(expect)
    try:
        with ap.open("rb") as f:
            head = f.read(_FIRST_LINE_BYTES)
    except OSError as exc:
        return f"could not be read to check its first line ({exc})"
    first = head.decode("utf-8", "replace").splitlines()
    first = first[0] if first else ""
    names = _names_in(first)
    absent = [w for w in wants if w not in names]
    if not absent:
        return None
    return ("first line does not name %s — it reads %r. A file that describes "
            "another document is a broken promise, not a present path."
            % (", ".join(repr(a) for a in absent), first[:120]))


#: Punctuation a name may be wrapped in on a report's first line
#: (`conserve penev_A:`, `— penev_A`, `(penev_A)`).
_EDGE = " \t.,:;()[]{}<>\"'`—–-"


def _names_in(line: str) -> set:
    """The set of things this line NAMES: whitespace tokens, minus surrounding
    punctuation, minus any extension — and never a token holding a path
    separator, because mentioning a folder is not naming the document."""
    out = set()
    for tok in line.split():
        if "/" in tok or "\\" in tok:
            continue                       # a path mentions; it does not name
        t = tok.strip(_EDGE)
        if not t:
            continue
        out.add(t)
        if "." in t:
            out.add(t.split(".", 1)[0])    # `penev_A.tex` names `penev_A`
    return out


def inspect_report(result: dict) -> str:
    """The printed block: every path with the one line saying what it is for."""
    lines = ["INSPECT — %s" % result["path"], ""]
    for a, reason in result["written"]:
        lines.append("  %s" % a)
        if reason:
            lines.append("      %s" % reason)
    if result["failed"]:
        lines.append("")
        lines.append("  NOT LISTED — a path in INSPECT.txt is a promise:")
        for a, why in result["failed"]:
            lines.append("  %s  <-- %s" % (a, why))
    if result["whitespace"]:
        lines.append("")
        lines.append("  %d path(s) contain a space: correct in this file, but "
                     "drillui's scanner splits on whitespace and cannot open "
                     "them." % len(result["whitespace"]))
    return "\n".join(lines)
