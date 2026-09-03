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


def save_json(target, task, name: str, obj) -> Path:
    p = task_dir(target, task) / (name if name.endswith(".json")
                                  else name + ".json")
    p.write_text(json.dumps(obj, indent=1, ensure_ascii=False,
                            default=str), encoding="utf-8")
    return p


def save_text(target, task, name: str, text: str) -> Path:
    p = task_dir(target, task) / name
    p.write_text(text, encoding="utf-8")
    return p


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
