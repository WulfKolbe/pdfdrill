"""Runtime prompts, loaded from files rather than embedded in Python (466).

A prompt that lives in a Python string literal has no identity. Two runs can
be recorded in full — 447 already writes every prompt and reply beside the
document — and still not be comparable, because nothing says whether the
prompt was the same one. A filename and a hash say it.

CONVENTION (already in use for task prompts):

    docs/prompts/YYYY-MM-DD-<name>-prompt.md

The date is the date the prompt was WRITTEN, not the day it was moved here.
Everything after the first line that is exactly `---` is the prompt body; the
prose above it is provenance and does not reach any model. A file with no
such line is entirely body, which is how the task prompts already work
(`docs/PROMPT_FOR_CLAUDE_AI.md` separates the two the same way).

THE HASH IS OF THE BODY, NOT THE FILE. Editing the provenance header must not
read as "the prompt changed", and the body is what was sent.

WHERE THEY ARE FOUND, in order:

  1. $PDFDRILL_PROMPTS                — an override, for an experiment
  2. <repo>/docs/prompts/             — canonical; an edit takes effect at once
  3. <package>/prompts_data/          — the bundled copy, for an installed
                                        wheel where there is no project root
                                        to search upward to

`tools/promptsync.py` copies 2 into 3 and `tests/test_prompts.py` fails on
drift, which is the arrangement `skill/` already uses.

There is deliberately NO fallback to an embedded string. A prompt that cannot
be found raises; a run that silently used a different prompt is the failure
this module exists to prevent.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

SUFFIX = "-prompt.md"
#: YYYY-MM-DD-<name>-prompt.md
FILENAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)" + re.escape(SUFFIX) + r"$")
SEPARATOR = "---"


class PromptMissing(FileNotFoundError):
    """No file for this prompt name, in any search directory."""


def search_dirs() -> "list[Path]":
    out = []
    env = os.environ.get("PDFDRILL_PROMPTS")
    if env:
        out.append(Path(env))
    # src/pdfdrill/prompts.py -> repo root
    out.append(Path(__file__).resolve().parents[2] / "docs" / "prompts")
    out.append(Path(__file__).resolve().parent / "prompts_data")
    return out


def find(name: str) -> Path:
    """The file for `name`, ignoring the date prefix. Raises PromptMissing."""
    tail = f"-{name}{SUFFIX}"
    for d in search_dirs():
        if not d.is_dir():
            continue
        hits = sorted(p for p in d.glob("*" + SUFFIX)
                      if p.name.endswith(tail))
        if hits:
            # newest date wins, so a revision is a new file and the old one
            # stays readable rather than being overwritten
            return hits[-1]
    raise PromptMissing(
        "no prompt %r in %s" % (name, ", ".join(str(d) for d in search_dirs())))


def split_body(text: str) -> str:
    """The part below the first `---` line, or the whole text if there is none."""
    lines = text.splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if ln.strip() == SEPARATOR:
            return "".join(lines[i + 1:]).lstrip("\n")
    return text


_cache: dict = {}


def load(name: str) -> str:
    """The prompt body for `name`. Cached; raises PromptMissing."""
    if name not in _cache:
        p = find(name)
        _cache[name] = (p, split_body(p.read_text(encoding="utf-8")))
    return _cache[name][1]


def identity(name: str) -> dict:
    """{'prompt_file', 'prompt_sha256'} — what a call log records (466).

    The filename alone would not survive an edit in place; the hash alone
    would not say which prompt it was. Both, or the pair is not an identity.
    """
    load(name)
    p, body = _cache[name]
    return {"prompt_file": p.name,
            "prompt_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()}


def names() -> "list[str]":
    """Every prompt name available, deduplicated across the search path."""
    out: dict = {}
    for d in search_dirs():
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*" + SUFFIX)):
            m = FILENAME.match(p.name)
            if m:
                out.setdefault(m.group(2), p)
    return sorted(out)
