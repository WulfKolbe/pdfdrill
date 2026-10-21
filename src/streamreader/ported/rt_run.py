# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# Ported from psred (github.com/WulfKolbe/psred),
# playground/featjudge/tools/rt_run.py at origin/master 344c27d.
# pdf2mmd2: a function and a command instead of a script with fixed paths;
# the glyphs come from our glyph reader, where psred used featjudge's
# synth.extract with pdfdrill's inkboxes.
"""Encoding rules vs TeX's noad-tree truth on psred's round-trip sample
(featjudge F19, F27): 100 display formulas, each typeset by LuaTeX with an
id per maths character, read back from the PDF, and the relations the rules
find scored against the relations TeX built.

    python -m pdf2mmd2.ported.rt_run LO HI OUT.json [SAMPLE.json]
    python -m pdf2mmd2.ported.rt_run --parse LO HI OUT.json [SAMPLE.json]
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from .. import glyphs
from . import adapter, encoding as E, texroles as TR

TOLERANCE = 0.2         # points: our glyph against the same glyph by its id


def _ids(gl: list[dict], tex_glyphs: list[dict]) -> list[int | None]:
    """The TeX id of each of our glyphs: the coloured glyph with the same
    text nearest to it."""
    out = []
    for g in gl:
        best, dist = None, TOLERANCE
        for t in tex_glyphs:
            if t["text"] != g["name"]:
                continue
            d = abs(t["x0"] - g["x0"]) + abs(t["base"] - g["base"])
            if d <= dist:
                best, dist = t["id"], d
        out.append(best)
    return out


def one(latex: str, workdir) -> dict:
    rec: dict = dict(latex=latex)
    try:
        r = TR.build(latex, str(workdir))
    except Exception:                                    # noqa: BLE001
        rec["stage"] = "no pdf"
        return rec
    pg = list(glyphs.read_pages(Path(r["pdf"]), 1, 1, ink=True))[0]
    gl = adapter.encoding_glyphs(pg.glyphs, pg.height)
    ids = _ids(gl, r["glyphs"])
    pred = E.resolve(E.relate(gl), gl)
    s = TR.score(ids, r["roles"], r["truth"], pred)
    hints = []
    for m in s["missed"]:
        a, b = m["base"], m["script"]
        if a is None or b is None:
            hints.append("glyph-not-joined")
        elif m["rel"] in ("sup", "sub"):
            x = E.explain(gl[a], gl[b], m["rel"])
            hints.append(("op:" if E.is_operator(gl[a]) else "")
                         + "+".join(x["failed"]) or "C1")
        else:
            hints.append(m["rel"] + (":no-ink" if not (
                gl[a].get("ink") and gl[b].get("ink")) else ":geometry"))
    rec.update(
        stage="ok",
        ink_none=sum(1 for g in gl if g.get("ink") is None),
        glyph_none=sum(1 for g in gl if g.get("glyph") is None),
        layout_identical=r["layout_identical"], glyphs=len(gl),
        coloured=sum(1 for i in ids if i), truth=len(r["truth"]),
        found=s["found"], missing=s["missing"], group=s["group"],
        spurious=s["spurious"], empty_base=s["empty_base"], hints=hints,
        spurious_rels=[(p["rel"], gl[p["a"]]["name"], gl[p["b"]]["name"])
                       for p in s["spurious_list"]])
    return rec


def run(formulas: list[dict], lo: int, hi: int) -> dict:
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        for k in range(lo, hi):
            d = Path(tmp) / str(k)
            d.mkdir()
            out[k] = one(formulas[k]["latex"], d)
    return out


def totals(results: dict) -> dict:
    ok = [v for v in results.values() if v.get("stage") == "ok"]
    keys = ("truth", "found", "missing", "group", "spurious", "empty_base",
            "glyphs", "coloured", "ink_none")
    out = {k: sum(v[k] for v in ok) for k in keys}
    out.update(formulas=len(results), ok=len(ok),
               perfect=sum(1 for v in ok
                           if v["missing"] == 0 and v["spurious"] == 0))
    return out


# ---- pdf2mmd2: the same sample through the formula PARSER -----------------
#
# The run above scores the relation rules of `encoding`. The page pipeline
# emits LaTeX with psred's `mathparse`, a different implementation. This
# scores that: typeset the formula, read it back, parse it, and compare the
# parse with the source by TeX's own structure (`relcompare`): the same
# characters and the same relations, whatever the spelling.

def parse_one(latex: str, workdir) -> dict:
    from . import mathparse, relcompare
    workdir = Path(workdir)
    rec: dict = dict(latex=latex)
    try:
        built = TR.build(latex, str(workdir / "src"))
        pg = list(glyphs.read_pages(Path(built["pdf"]), 1, 1))[0]
        parsed = mathparse.parse(*adapter.atoms(pg.glyphs, pg.rules))
    except Exception as e:                               # noqa: BLE001
        rec.update(stage="no parse", error=f"{type(e).__name__}: {e}")
        return rec
    rec["parsed"] = parsed
    cmp = relcompare.compare(latex, parsed, str(workdir / "cmp"))
    rec.update(stage="ok", **cmp)
    return rec


def parse_run(formulas: list[dict], lo: int, hi: int) -> dict:
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        for k in range(lo, hi):
            d = Path(tmp) / str(k)
            d.mkdir()
            out[k] = parse_one(formulas[k]["latex"], d)
    return out


_EMPTY_BASE = __import__("re").compile(r"\{\}\s*[\^_]")


def only_empty_base(rec: dict) -> bool:
    """The parse differs from the source only by relations the source wrote
    with an empty base (`{}^{x}`): same characters, no relation missing. On
    the page such a script stands exactly where a script of the glyph before
    it would; TeX's tree is the only place the two differ."""
    return (rec.get("stage") == "ok" and rec["b_compiles"]
            and not rec["equal"] and not rec["chars_only_a"]
            and not rec["chars_only_b"] and not rec["rels_only_a"]
            and bool(_EMPTY_BASE.search(rec["latex"])))


def parse_totals(results: dict) -> dict:
    ok = [v for v in results.values() if v.get("stage") == "ok"]
    return dict(
        formulas=len(results), parsed=len(ok),
        reparse_compiles=sum(1 for v in ok if v["b_compiles"]),
        equal=sum(1 for v in ok if v["equal"]),
        chars_equal=sum(1 for v in ok if v["b_compiles"]
                        and not v["chars_only_a"] and not v["chars_only_b"]),
        rels_equal=sum(1 for v in ok if v["b_compiles"]
                       and not v["rels_only_a"] and not v["rels_only_b"]),
        only_empty_base=sum(1 for v in ok if only_empty_base(v)))


def main(argv: list[str]) -> int:
    parse = argv[:1] == ["--parse"]
    argv = argv[1:] if parse else argv
    lo, hi, dest = int(argv[0]), int(argv[1]), argv[2]
    sample = argv[3] if len(argv) > 3 else (
        Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "psred"
        / "roundtrip_sample.json")
    formulas = json.loads(Path(sample).read_text())["formulas"]
    hi = min(hi, len(formulas))
    results = (parse_run if parse else run)(formulas, lo, hi)
    Path(dest).write_text(json.dumps(results, indent=1))
    print(lo, hi, json.dumps((parse_totals if parse else totals)(results)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
