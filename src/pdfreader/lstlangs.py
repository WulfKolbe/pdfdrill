#!/usr/bin/env python3
r"""lstlangs — the keyword lists `listings` itself ships, read out.

781e — ASK THE PACKAGE THAT PAINTED THE PAGE.

`keywordstyle` colours a word if and only if that word is in the keyword
list of the language the author named. So the coloured words on a page are
a SUBSET of one language's declared keywords, and which language that is
can be looked up rather than guessed. listings ships 97 of them in
`lstlang1-3.sty` and `lstmisc.sty`:

    \lst@definelanguage[ANSI]{C}{morekeywords={auto,break,case,char,...

The precedent is `texmap.MATHABX`, which reads `mathabx.dcl` for the same
reason: the producer's own declaration outranks anything inferred from
what the glyph looks like.

It lives here and not in `out/` because it is a READER capability, not a
measurement: the same move `texmap` makes with `mathabx.dcl`.

This is NOT a general language detector. It answers a narrower question --
"which listings language would colour exactly these words?" -- and abstains
when the answer is not unique. A listing whose keywords were never coloured
leaves it nothing to work with, and it says so.

    python3 lstlangs.py --build   # write lstlangs.json beside this file
    python3 lstlangs.py for,float,int,while
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TABLE = HERE / "lstlangs.json"
TEXMF = Path("/usr/share/texmf-dist/tex/latex/listings")

_DEF = re.compile(r"\\lst@definelanguage(?:\[([^\]]*)\])?\{([^}]*)\}")
_KW = re.compile(r"(?:more)?keywords(?:=\[\d+\])?\s*=?\s*\{")


def _balanced(text: str, i: int) -> str:
    """The `{...}` group starting at `i`, braces counted."""
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    return ""


def _words(group: str) -> set:
    out = set()
    for w in re.split(r"[,\s]+", group.strip("{}")):
        w = w.strip().strip("%")
        # A keyword list may carry TeX: `\#include`, `{$}`. Keep what a
        # reader could actually see as a word on the page.
        w = re.sub(r"^\\+", "", w)
        if w and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.#+-]*", w):
            out.add(w)
    return out


def build(texmf: Path = TEXMF) -> dict:
    out: dict = {}
    for f in sorted(texmf.glob("lstlang*.sty")) + [texmf / "lstmisc.sty"]:
        if not f.is_file():
            continue
        t = f.read_text(encoding="utf-8", errors="replace")
        marks = [(m.start(), m.group(1) or "", m.group(2))
                 for m in _DEF.finditer(t)]
        for k, (pos, dialect, name) in enumerate(marks):
            end = marks[k + 1][0] if k + 1 < len(marks) else len(t)
            body = t[pos:end]
            words: set = set()
            for m in _KW.finditer(body):
                words |= _words(_balanced(body, m.end() - 1))
            if not words:
                continue
            key = name.lower()
            out.setdefault(key, set())
            out[key] |= words
    return {k: sorted(v) for k, v in out.items() if len(v) >= 4}


def rank(observed, table: dict, top: int = 5) -> list:
    """Languages whose keyword list COVERS the observed words, best first.

    Coverage, not overlap: every coloured word must be a keyword of the
    language, because listings could not have coloured it otherwise. Ties
    are broken by the SMALLER keyword list -- a language that declares 400
    words covers everything and says nothing.
    """
    obs = {w.lower() for w in observed if w}
    if not obs:
        return []
    out = []
    for name, words in table.items():
        w = {x.lower() for x in words}
        hit = len(obs & w)
        out.append((hit / len(obs), -len(w), name, hit, len(obs)))
    out.sort(reverse=True)
    return [(n, c, h, t) for c, _s, n, h, t in out[:top]]


def load() -> dict:
    if TABLE.is_file():
        return json.loads(TABLE.read_text())
    return build()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("words", nargs="?", default="")
    A = ap.parse_args()
    if A.build:
        t = build()
        TABLE.write_text(json.dumps(t, indent=0, sort_keys=True))
        print("%d languages, %d keywords, -> %s"
              % (len(t), sum(len(v) for v in t.values()), TABLE.name))
        return
    if not A.words:
        ap.error("give a comma-separated word list, or --build")
    for name, cov, hit, tot in rank(A.words.split(","), load()):
        print("   %-16s covers %d/%d  %.0f%%" % (name, hit, tot, 100 * cov))


if __name__ == "__main__":
    main()
