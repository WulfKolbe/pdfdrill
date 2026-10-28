# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Inline and display decisions against a colour twin.

A colour twin is the same paper typeset twice from its LaTeX source: once
as it is, once with every inline formula red and every display blue
(psred featjudge `twin.py`). Where both runs set a glyph in the same place,
its colour says what it is: inline mathematics, display mathematics, or
text. That is truth by construction, independent of any reading.

Our reading is run on the plain PDF, and what the formula module took each
glyph for is held against the colours.

    pdf2mmd2-twin <library folder name | source archive>...
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from . import assign, bboxlayout, glyphlayout, glyphs, mathtex, runner
from .bboxlayout import PX_PER_PT
from .modules import formulas
from .ported import oracle_colour, regions, twin

LABELS = ("text", "inline", "display")


def build(source, work) -> tuple[Path, Path]:
    """(plain, colour) PDFs built from a source archive (zip, arXiv tar)."""
    plain, colour = twin.build(str(source), str(work))
    return Path(plain), Path(colour)


def built(work) -> tuple[Path, Path] | None:
    """The (plain, colour) PDFs of a twin built earlier in `work`, or None.
    The main PDF is the one beside the .tex that holds \\begin{document};
    a source tree can hold figure PDFs too."""
    found = []
    for variant in ("plain", "colour"):
        mains = [p for p in sorted((Path(work) / variant).rglob("*.tex"))
                 if "\\begin{document}" in p.read_text("latin-1")
                 and p.with_suffix(".pdf").is_file()]
        if len(mains) != 1:
            return None
        found.append(mains[0].with_suffix(".pdf"))
    return found[0], found[1]


def truth(plain, colour) -> dict:
    labels, coverage = oracle_colour.twin_labels(str(plain), str(colour))
    return dict(labels=labels, coverage=coverage,
                same_layout=oracle_colour.same_layout(str(plain), str(colour)),
                counts=Counter(labels.values()),
                # glyphs the paper itself colours (links, headings): the
                # twin cannot say what they are, and that is no layout fault
                coloured=oracle_colour.coloured_keys(
                    oracle_colour._chars(str(plain))))


def ours(plain) -> list[dict]:
    """One dict per inked glyph of the plain PDF: page, x0, x1, base, size
    (PDF points, y upward, as the twin's keys are) and our label: 'text',
    'inline', 'display', or 'number' for a glyph of an equation number."""
    plain = Path(plain)
    total = runner.page_count(plain)
    pages = (None if runner.DEFAULT_READER == "glyphs"
             else bboxlayout.read_pages_tsv(plain, 1, total, "twin"))
    out = []
    k = PX_PER_PT
    for n, rec in enumerate(glyphs.read_pages(plain, 1, total)):
        page = (glyphlayout.page_from_glyphs("twin", rec) if pages is None
                else pages[n])
        g = rec.glyphs
        own = assign.by_text(page["lines"], g,
                             assign.owners(page["lines"], g))
        label = formulas.labels(page, rec, own)
        numbers = {i for i, ln in enumerate(page["lines"])
                   if ln["type"] == "equation_number"}
        top = rec.points[1]
        for i in range(g.n):
            if g.text[i].strip():
                out.append(dict(page=rec.page, x0=g.x0[i] / k, x1=g.x1[i] / k,
                                base=top - g.base[i] / k, size=g.size[i],
                                label="number" if own[i] in numbers
                                else label[i],
                                mathfont=bool(mathtex.font_class(
                                    g.fonts[g.font[i]]))))
    return out


def tabulate(mine: list[dict], labels: dict,
             coloured: set | None = None) -> dict:
    """Our glyph labels against the twin's, on the pages where every glyph
    has truth. A page on which the two runs broke a line differently has
    glyphs with no counterpart; scoring the rest of it would count against
    a layout, not against the truth (featjudge scores the same way)."""
    joined: dict[int, list] = {}
    missing: Counter = Counter()
    skipped = 0
    for g in mine:
        want = oracle_colour.label_of(labels, g["page"], g["x0"], g["base"])
        if want is None and coloured and oracle_colour.label_of(
                {key: True for key in coloured}, g["page"], g["x0"],
                g["base"]):
            skipped += 1                    # coloured by the paper itself
            continue
        if want is None:
            missing[g["page"]] += 1
        joined.setdefault(g["page"], []).append((want, g))
    table: Counter = Counter()
    numbers: Counter = Counter()
    # mathematics in a mathematics font, and mathematics set in a font that
    # also sets the text ("$100$"), which no reader can tell from text
    by_font = {"math": {"truth": 0, "found": 0},
               "text": {"truth": 0, "found": 0}}
    true_display, our_display = [], []
    scored = 0
    for page, pairs in joined.items():
        if missing[page]:
            continue
        scored += 1
        for want, g in pairs:
            if g["label"] == "number":
                # An equation number is set inside the display, so the twin
                # colours it as one. It is text LaTeX generates and is its
                # own line here: counted apart, not as a missed display.
                numbers[want] += 1
                continue
            table[(want, g["label"])] += 1
            if want != "text":
                kind = by_font["math" if g.get("mathfont") else "text"]
                kind["truth"] += 1
                kind["found"] += g["label"] != "text"
            if want == "display":
                true_display.append(g)
            if g["label"] == "display":
                our_display.append(g)
    tax = regions.taxonomy(regions.regions(our_display),
                           regions.regions(true_display))
    # Inline formulas as wholes: a run of glyphs the twin colours inline,
    # consecutive in the stream. One with no glyph from a mathematics font
    # ("$100$", a variable set in the text italic) shows nothing a font
    # could be asked about.
    formulas_ = dict(total=0, font_visible=0, visible_found=0,
                     visible_exact=0, font_invisible=0, invisible_found=0)
    for page, pairs in joined.items():
        if missing[page]:
            continue
        run: list = []
        for want, g in pairs + [(None, None)]:
            if want == "inline" and g["label"] != "number":
                run.append(g)
                continue
            if run:
                taken = sum(r["label"] == "inline" for r in run)
                formulas_["total"] += 1
                if any(r.get("mathfont") for r in run):
                    formulas_["font_visible"] += 1
                    formulas_["visible_found"] += taken > 0
                    formulas_["visible_exact"] += taken == len(run)
                else:
                    formulas_["font_invisible"] += 1
                    formulas_["invisible_found"] += taken > 0
                run = []
    return dict(glyphs=table, labelled=sum(table.values()),
                inline_formulas=formulas_,
                unjoined=sum(missing.values()), numbers=dict(numbers),
                by_font=by_font,
                coloured_by_the_paper=skipped,
                pages=len(joined), pages_scored=scored,
                # a class that resets \everymath leaves the twin uncoloured
                valid=any(v != "text" for v in labels.values()),
                displays=dict(counts=dict(tax["counts"]),
                              truth=len(tax["gt"]), ours=len(tax["pred"])))


def score(plain, colour) -> dict:
    t = truth(plain, colour)
    return dict(tabulate(ours(plain), t["labels"], t["coloured"]),
                coverage=t["coverage"],
                same_layout=t["same_layout"])


def rates(table) -> dict:
    out = {}
    for label in ("inline", "display"):
        both = table.get((label, label), 0)
        said = sum(v for (_, o), v in table.items() if o == label)
        true = sum(v for (w, _), v in table.items() if w == label)
        out[label] = dict(precision=round(both / said, 4) if said else None,
                          recall=round(both / true, 4) if true else None)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="pdf2mmd2-twin", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docs", nargs="+",
                    help="library folder name (its .tgz is the source), or "
                         "a source archive")
    ap.add_argument("--root", default=str(Path.home() / "pdfdrill-library"))
    ap.add_argument("--work", default="out/twins")
    ap.add_argument("--reuse", action="store_true",
                    help="score a twin built earlier instead of building it "
                         "again")
    ap.add_argument("--json", help="also write all results to this file")
    args = ap.parse_args(argv)
    root, work = Path(args.root), Path(args.work)
    if root.resolve() in [work.resolve(), *work.resolve().parents]:
        print(f"pdf2mmd2-twin: --work {work} is inside the library",
              file=sys.stderr)
        return 2
    results = {}
    pooled: Counter = Counter()
    displays: Counter = Counter()
    inline: Counter = Counter()
    fonts = {"math": {"truth": 0, "found": 0},
             "text": {"truth": 0, "found": 0}}
    for doc in args.docs:
        src = Path(doc)
        name = src.name.split(".")[0] if src.is_file() else doc
        if not src.is_file():
            src = next(iter(sorted((root / doc).glob("*.tgz"))), None)
        if src is None:
            print(f"{doc}: no source archive")
            results[doc] = dict(error="no source archive")
            continue
        try:
            plain, colour = ((args.reuse and built(work / name))
                             or build(src, work / name))
            s = score(plain, colour)
        except Exception as e:                           # noqa: BLE001
            print(f"{name}: {type(e).__name__}: {str(e)[:120]}")
            results[name] = dict(error=f"{type(e).__name__}: {e}")
            continue
        r = rates(s["glyphs"])
        s["rates"] = r
        results[name] = dict(s, glyphs={f"{w}>{o}": v for (w, o), v
                                        in sorted(s["glyphs"].items())})
        if not s["valid"]:
            print(f"{name}: no coloured glyph in the twin - not truth")
            continue
        for key, value in s["glyphs"].items():
            pooled[key] += value
        for key, value in s["displays"]["counts"].items():
            displays[key] += value
        for kind in fonts:
            for key in ("truth", "found"):
                fonts[kind][key] += s["by_font"][kind][key]
        for key, value in s["inline_formulas"].items():
            inline[key] += value
        print(f"{name}: pages scored {s['pages_scored']}/{s['pages']} | "
              f"inline P {r['inline']['precision']} "
              f"R {r['inline']['recall']} | display "
              f"P {r['display']['precision']} R {r['display']['recall']} | "
              f"displays {s['displays']['counts']}")
    if pooled:
        r = rates(pooled)
        print(f"ALL: inline P {r['inline']['precision']} "
              f"R {r['inline']['recall']} | display "
              f"P {r['display']['precision']} R {r['display']['recall']} | "
              f"displays {dict(displays.most_common())}")
        print("ALL: mathematics glyphs found, in mathematics fonts "
              f"{fonts['math']['found']}/{fonts['math']['truth']}, in fonts "
              f"that also set text {fonts['text']['found']}/"
              f"{fonts['text']['truth']}")
        print(f"ALL: inline formulas {dict(inline)}")
        results["ALL"] = dict(rates=r, displays=dict(displays), by_font=fonts,
                              inline_formulas=dict(inline), glyphs={
            f"{w}>{o}": v for (w, o), v in sorted(pooled.items())})
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
