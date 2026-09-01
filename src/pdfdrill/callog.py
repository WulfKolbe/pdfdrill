"""447 — every paid model call, written beside the document it was about.

WHY THIS EXISTS. Three times an artefact someone needed was in a temp folder.
444's finding is a comparison of two prompts — one with the compile error, one
without — and after that run the replies were in the repo and THE PROMPTS WERE
NOT. They were reconstructible from `PROPOSE_PROMPT_C`, my `ERR_LINE` and the
stored `latex`, at one particular commit, if you knew which. That is
reconstruction, not evidence.

A paid call whose prompt and reply are not kept is a measurement that cannot
be repeated. It can only be re-bought.

WHERE IT LANDS. Beside the document, never in a scratchpad:

    <blob_dir>/calls/<run_id>.jsonl

One file per RUN, one JSON object per CALL, appended as the run proceeds so a
run that dies half way still leaves what it already spent. The run id is
`<UTC>-<tool>-<8 hex>`, sortable and unique, and it is returned to the caller
so a report can name the evidence it rests on.

WHAT IS NOT WRITTEN. The API key, obviously — but also nothing is *redacted*
from the prompt or reply, because a redacted prompt is not the prompt that was
sent. If a prompt should not be kept, it should not be sent.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path


def new_run_id(tool: str) -> str:
    """`20260901T144233Z-refine444-1a2b3c4d` — sortable, unique, self-naming."""
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tool)[:32]
    return "%s-%s-%s" % (stamp, safe, uuid.uuid4().hex[:8])


def log_dir(blob_dir) -> Path:
    return Path(blob_dir) / "calls"


def path_for(blob_dir, run_id: str) -> Path:
    return log_dir(blob_dir) / ("%s.jsonl" % run_id)


def open_run(blob_dir, tool: str, *, script: str = "",
             note: str = "", run_id: str = "") -> str:
    """Start a run log and write its HEADER. Returns the run id.

    The header carries the script that ran and the commit it ran at, because
    "which prompt" and "which code built it" are the same question one step
    apart.
    """
    rid = run_id or new_run_id(tool)
    d = log_dir(blob_dir)
    d.mkdir(parents=True, exist_ok=True)
    # 448 — the SCRIPT ITSELF, beside the run, not merely its path. A path
    # rots: the file moves, or is edited the next day, and the record then
    # points at something that is not what ran. The text cannot rot.
    if script and Path(script).is_file():
        try:
            (d / ("%s.script" % rid)).write_text(
                Path(script).read_text(encoding="utf-8", errors="replace"),
                encoding="utf-8")
        except OSError:
            pass
    head = {
        "kind": "run",
        "run_id": rid,
        "tool": tool,
        "script": script,
        "note": note,
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "commit": _commit(),
        "pid": os.getpid(),
    }
    with path_for(blob_dir, rid).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(head, ensure_ascii=False) + "\n")
    return rid


def log_call(blob_dir, run_id: str, *, prompt: str, system: str, reply: str,
             model: str = "", max_tokens=None, finish: str = "",
             error: str = "", seconds=None, images=(), subject: str = "",
             arm: str = "", prompt_name: str = "",
             extra: dict | None = None) -> None:
    """One call, VERBATIM. Appended immediately, never buffered.

    `arm` is the field 444 needed and did not have: two calls about the same
    subject differing by one line of prompt are only a comparison if the
    record says which was which.

    `prompt_name` (466) names the FILE the prompt came from, and the record
    gets its `prompt_file` and `prompt_sha256` beside the text. The verbatim
    prompt is already here; what it did not have is identity. Two runs whose
    prompt bytes happen to match are the same experiment only if they were
    the same prompt, and two whose bytes differ are a comparison only if the
    record says which prompt each was. An unknown name is recorded as such
    rather than raising — a call log must never be the thing that fails a
    paid call.
    """
    rec = {
        "kind": "call",
        "run_id": run_id,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "subject": subject,
        "arm": arm,
        "model": model,
        "max_tokens": max_tokens,
        "seconds": seconds,
        "finish": finish,
        "error": error,
        "system": system,
        "prompt": prompt,
        "reply": reply,
        "images": [str(x) for x in (images or ())],
    }
    if prompt_name:
        rec["prompt_name"] = prompt_name
        try:
            from . import prompts as _p
            rec.update(_p.identity(prompt_name))
        except Exception as exc:                      # never fail a paid call
            rec["prompt_file"] = ""
            rec["prompt_sha256"] = ""
            rec["prompt_identity_error"] = "%s: %s" % (type(exc).__name__, exc)
    if extra:
        rec["extra"] = extra
    with path_for(blob_dir, run_id).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def close_run(blob_dir, run_id: str, *, calls: int = 0,
              outcome: str = "", extra: dict | None = None) -> Path:
    """Write the footer and return the file. A run without one died."""
    rec = {"kind": "end", "run_id": run_id, "calls": calls,
           "outcome": outcome,
           "ended": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if extra:
        rec["extra"] = extra
    p = path_for(blob_dir, run_id)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return p


def read_run(path) -> list:
    """Every record in a run log, in order."""
    out = []
    p = Path(path)
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def runs_for(blob_dir) -> list:
    """Every run log beside this document, newest last."""
    d = log_dir(blob_dir)
    return sorted(d.glob("*.jsonl")) if d.is_dir() else []


def _commit() -> str:
    import subprocess
    try:
        r = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"],
                           cwd=str(Path(__file__).resolve().parents[2]),
                           capture_output=True, text=True, timeout=10)
        return (r.stdout or "").strip()
    except Exception:
        return ""
