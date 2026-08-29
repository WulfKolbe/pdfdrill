#!/usr/bin/env python3
"""332 — the clean gold set: the author's own commutative diagrams, rendered.

Every `\\begin{tikzcd}...\\end{tikzcd}` in 2004.05631v1's source, compiled
standalone with the author's own preamble. The correct source is known by
CONSTRUCTION — it is the source — so nothing has to be joined to anything.
That is the whole point: 301 measured the alternative, pairing an author
figure to a MathPix crop, at 0 matched of 8 known pairs.

A measurement harness for one document, so it lives in tools/ rather than
becoming a command: it establishes a reference set, it is not a capability a
document can be asked for.
"""
import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfdrill import texgraphics as tg                    # noqa: E402
from pdfdrill import region_standalone as rs              # noqa: E402
from pdfdrill import latex_source as ls                   # noqa: E402

DOC = pathlib.Path.home() / "pdfdrill-library" / "2004.05631v1"
SRC = DOC / "texsrc"
OUT = DOC / "goldcd"
BEGIN = re.compile(r"\\begin\{tikzcd\}")


def environments(text: str):
    r"""Every tikzcd environment, brace-matched on \begin/\end so a nested
    one is taken with its parent rather than torn in half."""
    out = []
    for m in BEGIN.finditer(text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            b = text.find("\\begin{tikzcd}", i)
            e = text.find("\\end{tikzcd}", i)
            if e < 0:
                break
            if 0 <= b < e:
                depth += 1
                i = b + 14
            else:
                depth -= 1
                i = e + 12
        if not depth:
            out.append(text[m.start():i])
    return out


def main():
    authored = [p for p in sorted(SRC.rglob("*.tex"))
                if not tg.is_texzip_tex(p, SRC)]
    root = next((p for p in authored
                 if "\\documentclass" in p.read_text(errors="replace")[:4000]),
                None)
    pre = ""
    if root is not None:
        try:
            # EXPAND \input FIRST. thesis.tex is 393 chars of preamble with 3
            # \newcommand; the macros live in chapters/preamble_tufte.tex,
            # 4,010 chars with 16, reached only through \input. Extracting from
            # the root alone produced 17 "Undefined control sequence" failures
            # out of 23 -- the author's own macros, missing because the file
            # defining them was never opened.
            whole = ls.expand_inputs(str(root), str(SRC))
            pre = ls.standalone_preamble(whole)
        except Exception as exc:                            # noqa: BLE001
            print("  preamble extraction failed: %s" % exc, flush=True)
    print("  author preamble: %d chars from %s"
          % (len(pre), root.name if root else "NONE"), flush=True)

    items = []
    for t in authored:
        s = t.read_text(errors="replace")
        for k, env in enumerate(environments(s), 1):
            items.append({"ident": "CD_%s_%03d" % (t.stem[:12], k),
                          "source": str(t.relative_to(SRC)),
                          "latex": env})
    print("  tikzcd environments: %d" % len(items), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    ok, failed = [], []
    for i, it in enumerate(items, 1):
        png, err = rs.render(it["ident"], it["latex"], OUT,
                             author_preamble=pre, graphics_dir=SRC,
                             texinputs=SRC)
        if png is None:
            it["error"] = (err or "?")[:160]
            failed.append(it)
        else:
            it["png"] = str(pathlib.Path(png).relative_to(DOC))
            ok.append(it)
        print("  [%3d/%3d] %-26s %s" % (i, len(items), it["ident"],
                                        "ok" if png else it.get("error", "")[:60]),
              flush=True)
    (ROOT / "out" / "332.json").write_text(json.dumps(
        {"document": DOC.name, "environments": len(items),
         "compiled": len(ok), "failed": len(failed),
         "items": ok, "failures": failed}, indent=1, ensure_ascii=False))
    print("\n  compiled %d, failed %d" % (len(ok), len(failed)), flush=True)


if __name__ == "__main__":
    main()
