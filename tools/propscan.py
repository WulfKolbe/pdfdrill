"""290 — derive prop READERS and WRITERS from the source, never by hand.

A reader is `props.get("x")` / `props["x"]` / `.props.get("x")`; a writer is a
key in a `props={...}` literal or a `props["x"] = ...` assignment. Both are
approximations of what the code does, and that is stated rather than implied:
a prop reached through a variable key is invisible here, which is exactly the
blind spot out/237b hit when a dispatcher's `getattr` made three functions look
dead. What the scan CAN see it reports precisely; what it cannot, it does not
claim.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

_READ = re.compile(r"""props(?:\s*\)\s*|\s*)?\.get\(\s*["']([A-Za-z_][\w]*)["']"""
                   r"""|props\[\s*["']([A-Za-z_][\w]*)["']\s*\]""")
_ASSIGN = re.compile(r"""props\[\s*["']([A-Za-z_][\w]*)["']\s*\]\s*=""")
_SETDEFAULT = re.compile(r"""props\.setdefault\(\s*["']([A-Za-z_][\w]*)["']""")
#: a key inside a `props={...}` / `props = {...}` literal
_PROPS_LIT = re.compile(r"props\s*=\s*\{")
_KEY = re.compile(r"""["']([A-Za-z_][\w]*)["']\s*:""")


def _literal_keys(text: str, start: int) -> list:
    """Keys of the brace-balanced dict literal beginning at `start`."""
    depth, i = 0, start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return _KEY.findall(text[start:i + 1])
        i += 1
    return []


def scan(src: Path = SRC, known: "set | None" = None) -> dict:
    """readers / writers / mentions.

    `mentions` is the third tier and it exists because the first two lie by
    omission. `latex_refined` is written through a CONSTANT
    (`REFINED_FIELD = "latex_refined"`), `page_before_repair` through
    `props.setdefault`, and `text_source` is tested by membership in a tuple of
    prose keys — all three read as 0 readers and 0 writers to a pattern that
    only knows `props.get("x")`. A prop with a mention and no reader is weaker
    evidence than a reader, and it is not the same thing as untouched.
    """
    readers = defaultdict(set)
    writers = defaultdict(set)
    mentions = defaultdict(set)
    for py in sorted(src.rglob("*.py")):
        rel = str(py.relative_to(src))
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in _READ.finditer(text):
            name = m.group(1) or m.group(2)
            readers[name].add(rel)
        for m in _ASSIGN.finditer(text):
            writers[m.group(1)].add(rel)
        for m in _SETDEFAULT.finditer(text):
            writers[m.group(1)].add(rel)
        if known:
            for name in known:
                if ('"%s"' % name) in text or ("'%s'" % name) in text:
                    mentions[name].add(rel)
        for m in _PROPS_LIT.finditer(text):
            for k in _literal_keys(text, m.end() - 1):
                writers[k].add(rel)
    return {"readers": {k: sorted(v) for k, v in sorted(readers.items())},
            "writers": {k: sorted(v) for k, v in sorted(writers.items())},
            "mentions": {k: sorted(v) for k, v in sorted(mentions.items())}}


if __name__ == "__main__":
    corpus = SRC / "docmodel" / "corpus_props.json"
    known = set()
    if corpus.is_file():
        cp = json.loads(corpus.read_text(encoding="utf-8"))["props"]
        known = {p for t in cp for p in cp[t]}
    out = scan(known=known)
    dest = SRC / "docmodel" / "props_code.json"
    dest.write_text(json.dumps(
        {"_provenance": {
            "method": "regex over src/**/*.py: readers are props.get(\"x\") or "
                      "props[\"x\"]; writers are props[\"x\"]= and keys of a "
                      "props={...} literal. A prop reached through a VARIABLE "
                      "key is invisible to this scan and is not claimed either "
                      "way.",
            "files": len(list(SRC.rglob("*.py"))),
            "task": "290"},
         **out}, indent=1), encoding="utf-8")
    print("readers %d, writers %d, mentions %d -> %s"
          % (len(out["readers"]), len(out["writers"]),
             len(out["mentions"]), dest.name))
