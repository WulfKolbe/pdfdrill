"""290 — generate docs/layers/PROPS.md from the corpus and the source.

Never hand-edited. Two inputs, both generated:

    src/docmodel/corpus_props.json   a walk of every model.docmodel.json —
                                     which prop, on which object type, how often
    src/docmodel/props_code.json     tools/propscan.py — readers, writers and
                                     mentions across src/**/*.py

Run after either changes:  python3 tools/propstable.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from docmodel.prop_contract import NO_READER_REASON        # noqa: E402

CORPUS = ROOT / "src" / "docmodel" / "corpus_props.json"
CODE = ROOT / "src" / "docmodel" / "props_code.json"
DEST = ROOT / "docs" / "layers" / "PROPS.md"

#: writer file -> the command a reader would run. Derived from the module, not
#: guessed: these are the modules that construct DocObjects.
_COMMAND = {
    "docmodel/modules/": "pdfdrill model",
    "pdfdrill/latex_source.py": "pdfdrill injectlatex",
    "pdfdrill/refine.py": "pdfdrill refine",
    "pdfdrill/heading_cleanup.py": "pdfdrill clean",
    "pdfdrill/classify.py": "pdfdrill translate / classify",
    "pdfdrill/bibliography.py": "pdfdrill bibliography",
    "pdfdrill/annotations.py": "pdfdrill links",
    "pdfdrill/rectoverso.py": "pdfdrill pageside",
    "pdfdrill/table_structure.py": "pdfdrill tables",
    "pdfdrill/svg.py": "pdfdrill svg",
    "pdfdrill/la2speech": "pdfdrill speech",
    "semantic/": "pdfdrill semantic",
}


def command_for(files: list) -> str:
    hits = []
    for f in files:
        for frag, cmd in _COMMAND.items():
            if f.startswith(frag) and cmd not in hits:
                hits.append(cmd)
    return ", ".join(hits) if hits else "—"


def main() -> int:
    cp = json.loads(CORPUS.read_text(encoding="utf-8"))
    cc = json.loads(CODE.read_text(encoding="utf-8"))
    props, prov = cp["props"], cp["_provenance"]
    readers, writers = cc["readers"], cc["writers"]
    mentions = cc.get("mentions", {})

    totals: dict = {}
    on_types: dict = {}
    for t, ps in props.items():
        for p, v in ps.items():
            totals[p] = totals.get(p, 0) + v["n"]
            on_types.setdefault(p, []).append(t)

    L = ["# Props table",
         "",
         "**Generated — do not edit.** `python3 tools/propstable.py` rebuilds it from",
         "`src/docmodel/corpus_props.json` (a walk of the corpus) and",
         "`src/docmodel/props_code.json` (`tools/propscan.py` over `src/**/*.py`).",
         "",
         "Two checks in `docmodel.prop_contract` hold it, the same pair that holds the",
         "type contract: every prop in the corpus must appear here with a reader or an",
         "explicit reason (`table_violations`), and every prop here must occur in the",
         "corpus (`table_not_in_corpus`).",
         "",
         "> **Read this before writing anything that reads a prop.** The recurring",
         "> failure is not a missing prop, it is a prop that exists, is written, and is",
         "> read by nothing — `subtype` on 1,239,021 lines, `list_item` in 882",
         "> documents. A reader column of `—` with a reason beside it is not a gap to",
         "> fill blindly; it is a fact somebody measured.",
         "",
         "## The pairs — a wrong choice here compiles silently",
         "",
         "| pair | which to use |",
         "|---|---|",
         "| `latex` / `latex_original` | `latex` and `latex_code` are macro-EXPANDED; `latex_original` keeps the author's macros. Renderers compile the expanded one and need no author preamble to resolve macros (289). |",
         "| `latex_pretail` / `trailing_punct` | `trailing_punct` is punctuation printed after the maths, set BESIDE it (025). `latex_pretail` is maths belonging to the following prose. Neither goes back into `latex`. |",
         "| `latex_refined` | a VERIFIED refinement in a twin prop; `latex` is never overwritten (232). Reading `latex` alone ignores every accepted repair (233). |",
         "",
         "## Every prop",
         "",
         "%d props over %d object types, from %s." % (
             len(totals), len(props), prov.get("scanned", "the corpus")),
         "",
         "| prop | objects | on types | written by | read by |",
         "|---|---:|---|---|---|"]

    for p in sorted(totals, key=lambda x: (-totals[x], x)):
        ts = on_types[p]
        tcol = ", ".join(sorted(ts)) if len(ts) <= 3 else "%d types" % len(ts)
        w = command_for(writers.get(p, [])) or "—"
        rs = readers.get(p, [])
        if rs:
            r = ", ".join("`%s`" % x for x in rs[:3])
            if len(rs) > 3:
                r += " +%d" % (len(rs) - 3)
        else:
            reason = NO_READER_REASON.get(p, "")
            note = ""
            if mentions.get(p):
                note = " (mentioned in %d file%s)" % (
                    len(mentions[p]), "" if len(mentions[p]) == 1 else "s")
            r = "**—** %s%s" % (reason or "NO REASON GIVEN", note)
        L.append("| `%s` | %s | %s | %s | %s |"
                 % (p, "{:,}".format(totals[p]), tcol, w, r))

    L += ["", "## Object types", "",
          "| type | objects | props |", "|---|---:|---:|"]
    for t, n in sorted(cp["object_counts"].items(), key=lambda r: -r[1]):
        L.append("| `%s` | %s | %d |" % (t, "{:,}".format(n), len(props.get(t, {}))))
    L.append("")

    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text("\n".join(L), encoding="utf-8")
    print("wrote %s — %d props, %d object types"
          % (DEST.relative_to(ROOT), len(totals), len(props)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
