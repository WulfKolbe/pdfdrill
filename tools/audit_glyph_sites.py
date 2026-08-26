"""out/223 — check every escape site against the font ACTUALLY selected there.

_COVERED is DejaVu Sans Mono's coverage, and the rescue it authorises,
\\ifmmode\\text{C}\\else C\\fi, selects a different font at each of the three
places a report puts text:

    column 0  \\ident{...}  = \\texttt{\\tiny ...}      -> MONO
    column 3  {\\ttfamily\\footnotesize ...}           -> MONO
    column 4  \\FitMath{$\\displaystyle ...$}          -> MATH; \\text{} inside
                                                        it -> MAIN; and
                                                        \\text{...} SPANS
                                                        inside the math are
                                                        text mode again
    everything else                                   -> MAIN (serif)

Three passes:

  SITES   walk every corpus report.tex, and for each non-ASCII occurrence
          record (code point, context) plus the declaration it carries under
          two regimes -- the one in that file's own preamble, and the one
          unicode_decls emits today.

  PROBE   for every (code point, declaration form, context) triple that
          occurs, compile one line under that declaration in that context and
          read the log. The model is then a measured lookup table with no
          inference in it. An earlier version predicted the math outcome from
          "is it a letter" and got 20 of 99 wrong: xelatex does not treat CJK
          ideographs as letters and treats combining marks differently again.

  ANSWER  pass A validates the table against each build's own report.log
          (98.3% of 1,101 documents agree exactly); pass B reports the corpus
          under the current check.

Run: PYTHONPATH=src python3 tools/audit_glyph_sites.py <library-dir> <out.json>
"""
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from pdfdrill import report_tex as rt

ROW = re.compile(r"\\\\\s*\\hline\s*$")
AMP = re.compile(r"(?<!\\)&")
MATHSPAN = re.compile(r"\$\\displaystyle (.*)\$", re.S)
DECL = re.compile(r"^\\newunicodechar\{(.)\}\{(.*)\}$")
LOST = re.compile(r"Missing character: There is no (.+?) "
                  r"\((?:U\+([0-9A-Fa-f]+)|\"([0-9A-Fa-f]+))\)")
MONO_COLS = (0, 3)

#: inside $...$ these set their argument in TEXT mode, on the main font
TEXT_IN_MATH = re.compile(
    r"\\(?:text|textrm|textnormal|textit|textbf|mbox|operatorname)\s*\{")

FORMS = {
    "none": None,
    "ambient": r"\newunicodechar{%(c)s}{\ifmmode\text{%(c)s}\else %(c)s\fi}",
    "amb_rm": r"\newunicodechar{%(c)s}{\ifmmode\text{%(c)s}\else{\rmfamily %(c)s}\fi}",
    "tt": r"\newunicodechar{%(c)s}{\ifmmode\text{\ttfamily %(c)s}\else{\ttfamily %(c)s}\fi}",
    "fbnew_cjk": r"\newunicodechar{%(c)s}{\ifmmode\text{{\fbcjk %(c)s}}\else{\fbcjk %(c)s}\fi}",
    "fbold_cjk": r"\newunicodechar{%(c)s}{{\fbcjk %(c)s}}",
    "fbnew_beng": r"\newunicodechar{%(c)s}{\ifmmode\text{{\fbbeng %(c)s}}\else{\fbbeng %(c)s}\fi}",
    "fbold_beng": r"\newunicodechar{%(c)s}{{\fbbeng %(c)s}}",
    "fbnew_math": r"\newunicodechar{%(c)s}{\ifmmode\text{{\fbmath %(c)s}}\else{\fbmath %(c)s}\fi}",
    "fbold_math": r"\newunicodechar{%(c)s}{{\fbmath %(c)s}}",
}
CTX = {"mono": r"{\ttfamily %s}", "main": r"{\rmfamily %s}",
       "math": r"$\displaystyle %s$"}


def form_of(body_tex):
    if body_tex.startswith(r"\ensuremath") or body_tex.startswith(r"\textbf{[U+"):
        return "ok"
    for fam in ("cjk", "beng", "math"):
        if "\\fb" + fam in body_tex:
            return ("fbnew_" if r"\ifmmode" in body_tex else "fbold_") + fam
    if r"\ttfamily" in body_tex:
        return "tt"
    if r"\rmfamily" in body_tex:
        return "amb_rm"
    if body_tex.startswith(r"\ifmmode\text{"):
        return "ambient"
    return "ok"


def text_spans(s):
    out = []
    for m in TEXT_IN_MATH.finditer(s):
        i = m.end()
        depth, j = 1, i
        while j < len(s) and depth:
            if s[j] == "{" and s[j - 1] != "\\":
                depth += 1
            elif s[j] == "}" and s[j - 1] != "\\":
                depth -= 1
            j += 1
        out.append((i, j - 1))
    return out


def sites(text):
    for line in text.split("\n"):
        if not ROW.search(line):
            for ch in line:
                if ord(ch) > 127:
                    yield ord(ch), "main"
            continue
        for i, col in enumerate(AMP.split(line)):
            default = "mono" if i in MONO_COLS else "main"
            m = MATHSPAN.search(col)
            if not m:
                for ch in col:
                    if ord(ch) > 127:
                        yield ord(ch), default
                continue
            a, b = m.span(1)
            inner = [(a + x, a + y) for x, y in text_spans(m.group(1))]
            for j, ch in enumerate(col):
                if ord(ch) <= 127:
                    continue
                if not (a <= j < b):
                    yield ord(ch), default
                elif any(x <= j < y for x, y in inner):
                    yield ord(ch), "main"
                else:
                    yield ord(ch), "math"


def decls(text, from_file):
    out = {}
    src = text.split("\n") if from_file else rt.unicode_decls(text).split("\n")
    for line in src:
        m = DECL.match(line.strip())
        if m:
            out[ord(m.group(1))] = form_of(m.group(2))
    return out


def probe(triples, workdir):
    by_form = defaultdict(set)
    for cp, form, ctx in triples:
        by_form[form].add((cp, ctx))
    table = {}
    for form, items in sorted(by_form.items()):
        d = [FORMS[form] % {"c": chr(cp)}
             for cp in sorted({c for c, _ in items})] if FORMS[form] else []
        body = ["\\typeout{PROBE %04X %s}%s\\par" % (cp, ctx, CTX[ctx] % chr(cp))
                for cp, ctx in sorted(items)]
        tex = rt.PREAMBLE % {"form": "", "geom": "",
                             "unicode": "\n".join(d), "bbdigits": ""}
        tex += "\n" + "\n".join(body) + "\n\\end{document}\n"
        p = os.path.join(workdir, "probe_%s.tex" % form)
        open(p, "w", encoding="utf-8").write(tex)
        subprocess.run(["xelatex", "-interaction=nonstopmode",
                        os.path.basename(p)], cwd=workdir,
                       capture_output=True, timeout=600)
        cur = None
        for ln in open(p.replace(".tex", ".log"), encoding="utf-8",
                       errors="replace"):
            m = re.match(r"PROBE ([0-9A-F]{4,6}) (\w+)", ln)
            if m:
                cur = (int(m.group(1), 16), m.group(2))
                table.setdefault("%04X|%s|%s" % (cur[0], form, cur[1]), None)
                continue
            if cur and "Missing character" in ln:
                f = re.search(r"in font ([^!\n]*)", ln)
                table["%04X|%s|%s" % (cur[0], form, cur[1])] = \
                    (f.group(1).strip() if f else "unnamed font")
    return table


def main(lib, out_path):
    work = os.path.join(os.path.dirname(os.path.abspath(out_path)), "_probe")
    os.makedirs(work, exist_ok=True)
    docs, triples = {}, set()
    for d in sorted(os.listdir(lib)):
        p = os.path.join(lib, d, "report.tex")
        if not os.path.isfile(p):
            continue
        raw = open(p, encoding="utf-8", errors="replace").read()
        pre, _, body = raw.partition(r"\begin{document}")
        occ = Counter(sites(body))
        inf, cur = decls(pre, True), decls(body, False)
        docs[d] = {"occ": {f"{c}|{x}": n for (c, x), n in occ.items()},
                   "in_file": {str(k): v for k, v in inf.items()},
                   "current": {str(k): v for k, v in cur.items()}}
        for (cp, ctx), _ in occ.items():
            for reg in (inf, cur):
                f = reg.get(cp, "none")
                if f != "ok":
                    triples.add((cp, f, ctx))
    table = probe(sorted(triples), work)

    def bad(rec, regime):
        cps, fonts, ctxs = Counter(), Counter(), Counter()
        for key, n in rec["occ"].items():
            cp, ctx = key.split("|")
            cp = int(cp)
            form = rec[regime].get(str(cp), "none")
            if form == "ok":
                continue
            f = table.get("%04X|%s|%s" % (cp, form, ctx))
            if f:
                cps[cp] += n
                fonts[f.split("/")[0]] += n
                ctxs[(ctx, form)] += n
        return cps, fonts, ctxs

    exact = differ = compared = 0
    for d, rec in docs.items():
        log = os.path.join(lib, d, "report.log")
        tex = os.path.join(lib, d, "report.tex")
        if not os.path.isfile(log) or os.path.getmtime(tex) > os.path.getmtime(log) + 2:
            continue
        compared += 1
        pred = set(bad(rec, "in_file")[0])
        act = {int(u or h, 16) for _, u, h in
               LOST.findall(open(log, encoding="utf-8", errors="replace").read())}
        act = {c for c in act if c > 127}
        exact += (pred == act)
        differ += (pred != act)

    tot = Counter()
    B_cp, B_f, B_ctx, reached = Counter(), Counter(), Counter(), {}
    for d, rec in docs.items():
        for key, n in rec["occ"].items():
            tot[key.split("|")[1]] += n
        cps, fonts, ctxs = bad(rec, "current")
        if cps:
            reached[d] = sum(cps.values())
        B_cp += cps
        B_f += fonts
        B_ctx += ctxs

    res = {"documents": len(docs),
           "validation": {"compared": compared, "exact": exact,
                          "differ": differ},
           "occurrences": dict(tot),
           "on_a_point_the_target_font_lacks": sum(B_cp.values()),
           "documents_reached": len(reached),
           "by_font": B_f.most_common(),
           "by_context": {f"{k[0]}|{k[1]}": v for k, v in B_ctx.most_common()},
           "by_code_point": [["U+%04X" % c, unicodedata.name(chr(c), "?"), n]
                             for c, n in B_cp.most_common(40)],
           "per_doc": dict(sorted(reached.items(), key=lambda x: -x[1]))}
    json.dump(res, open(out_path, "w"), indent=1)
    print(f"documents            : {len(docs)}")
    print(f"validation vs the logs: {exact}/{compared} exact "
          f"({100*exact/compared:.1f}%)")
    print(f"non-ASCII occurrences : {sum(tot.values()):,}  "
          f"(mono {tot['mono']:,} · math {tot['math']:,} · main {tot['main']:,})")
    print(f"ON A MISSING POINT    : {sum(B_cp.values()):,}")
    print(f"documents reached     : {len(reached)}")
    for f, n in B_f.most_common():
        print(f"   {n:6,}  {f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
