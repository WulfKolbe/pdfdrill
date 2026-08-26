"""Regenerate the coverage range constants in src/pdfdrill/report_tex.py.

The report's rescue machinery decides where a character can go by asking which
font has it. Those answers are stored as ranges in report_tex because runtime
must not depend on fontTools or on a font being installed. This script is where
they come FROM, so they can be re-derived on another machine instead of being
trusted because they are already in the file.

    _COVERED_RANGES     DejaVu Sans Mono            (the \ttfamily columns)
    _MONO_ONLY_RANGES   mono minus DejaVu Serif     (221b: \text{} lands in
                                                     serif, so these need the
                                                     escape to name mono)
    _MAIN_ONLY_RANGES   serif minus mono            (223: the other half, so a
                                                     declaration can name serif)
    _FB_CJK_RANGES      Noto Sans CJK JP, CJK blocks
    _FB_BENG_RANGES     Noto Sans Bengali, Bengali block

COVERAGE, NOT BLOCKS. Every range here is read from a cmap. A block test would
route a character to a font that may not have it, which turns a dropped glyph
into a dropped glyph with an extra step.

Run: python3 tools/build_font_ranges.py [--check]
--check compares against what report_tex currently holds and exits non-zero on
any difference, which is what CI would want.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

#: (constant, fontconfig family, style, [(lo, hi) blocks to restrict to])
FONTS = [
    ("_COVERED_RANGES",   "DejaVu Sans Mono", "Book",    None),
    ("_FB_CJK_RANGES",    "Noto Sans CJK JP", "Regular",
     [(0x2E80, 0x2FDF), (0x2FF0, 0x2FFB), (0x3000, 0x303F), (0x3040, 0x30FF),
      (0x31C0, 0x31EF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
      (0xFE30, 0xFE4F), (0xFF00, 0xFF65)]),
    ("_FB_BENG_RANGES",   "Noto Sans Bengali", "Regular", [(0x0980, 0x09FF)]),
]


def font_file(family: str, style: str) -> str:
    out = subprocess.run(["fc-list", "--format=%{file}\t%{family}\t%{style}\n"],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        f, fam, st = parts
        if family in [x.strip() for x in fam.split(",")] and \
           style in [x.strip() for x in st.split(",")]:
            return f
    raise SystemExit("font not installed: %s %s" % (family, style))


def coverage(path: str) -> set:
    from fontTools.ttLib import TTFont
    t = TTFont(path, fontNumber=0, lazy=True)
    s = set()
    for tb in t["cmap"].tables:
        s |= set(tb.cmap.keys())
    return s


def ranges(points) -> list:
    out = []
    for c in sorted(points):
        if out and c == out[-1][1] + 1:
            out[-1][1] = c
        else:
            out.append([c, c])
    return [tuple(r) for r in out]


def fmt(name, rs, per=4) -> str:
    body = "\n".join(
        "    " + " ".join("(0x%04X, 0x%04X)," % (a, b) for a, b in rs[i:i + per])
        for i in range(0, len(rs), per))
    return "%s = (\n%s\n)" % (name, body)


def main():
    mono = coverage(font_file("DejaVu Sans Mono", "Book"))
    serif = coverage(font_file("DejaVu Serif", "Book"))
    built = {}
    for const, fam, style, blocks in FONTS:
        cov = coverage(font_file(fam, style))
        if blocks:
            cov = {c for c in cov if any(lo <= c <= hi for lo, hi in blocks)}
        built[const] = ranges(cov)
    built["_MONO_ONLY_RANGES"] = ranges(c for c in mono
                                        if c > 0xFF and c not in serif)
    built["_MAIN_ONLY_RANGES"] = ranges(c for c in serif
                                        if c > 0xFF and c not in mono)

    if "--check" not in sys.argv:
        for k in ("_COVERED_RANGES", "_FB_CJK_RANGES", "_FB_BENG_RANGES",
                  "_MONO_ONLY_RANGES", "_MAIN_ONLY_RANGES"):
            print(fmt(k, built[k]))
            print()
        return 0

    from pdfdrill import report_tex as rt
    bad = 0
    for k, v in built.items():
        have = tuple(tuple(x) for x in getattr(rt, k))
        want = tuple(v)
        n_have = sum(b - a + 1 for a, b in have)
        n_want = sum(b - a + 1 for a, b in want)
        mark = "OK " if have == want else "DIFF"
        if have != want:
            bad += 1
        print(f"  {mark} {k:20s} in file {len(have):4d} ranges / "
              f"{n_have:6d} points   measured {len(want):4d} / {n_want:6d}")
    print("MATCH" if not bad else "%d constant(s) differ" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
