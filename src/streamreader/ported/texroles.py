# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# Ported from psred (github.com/WulfKolbe/psred), playground/featjudge/featjudge/texroles.py at origin/master 56cf8f6.
# Kept as close to the original as its new home allows; changes are marked "pdf2mmd2:".
"""texroles - relation truth from TeX's noad tree, independent of encoding.py.

CONTRACT
    colour_of(i) -> (r, g, b): id 1..65535 as rgb (i//256/255, i%256/255, 1)
    id_of(colour) -> int or None: inverse; None unless b == 1 and id > 0
    build(latex, workdir) -> dict(
        glyphs  [dict(text, x0, base, id)]  from the coloured PDF (pdfminer)
        roles   {id: dict(role, base, char, fam, style)}  from texroles.lua:
                role in plain | sup | sub | lim-over | lim-under | in-<rel>;
                fstyle: Appendix G style D D' T T' S S' SS SS' (cramping
                tracked: sup C-up, sub C-down, fraction 15a, radicand and
                \\overline C', \\underline C); style = its size name;
                nuc (only on the last char of a nucleus that has scripts):
                char | list | box | op | rad | acc; \\\\underline, \\\\overline and \\\\vcenter
                nuclei are 'box' (Rules 8-10 rebox them) (Rule 18a: only 'char'
                starts from u = v = 0);
                cls: TeX's declared atom class (ord op bin rel open close
                punct inner) of a single-char nucleus - before Rules 5/6;
                \\overline etc. count as ord (Rule 16); None otherwise;
                the FIRST char of a script group carries the relation, its
                base is the LAST char of the nucleus; other chars of the group
                get in-<rel>. Limits: op noad with \\limits, or display style
                with display-limits (TeX's default for sums), else sup/sub.
        truth   [dict(rel, base, script)] for every role in REL with a base,
                kept only when base AND script reach the PDF (amsmath typesets
                aligned cells twice; the measuring pass never ships)
        layout_identical, layout_max_dev  layout_compare against an
                uncoloured lualatex run of the same source
        pdf     the coloured PDF)
      The formula is set as '\\[ latex \\]' with amsmath, amssymb.
      RuntimeError when either run produces no PDF, or when the texroles
      callback reported an error (LuaTeX logs it as a warning and goes on).
    layout_compare(a, b) -> (same, max_dev): same glyph texts (as
      multisets) and, glyphs paired in sorted (text, x, y) order, every
      |dx| + |dy| <= LAYOUT_TOL (0.01 pt: the colour switches make LuaTeX
      split text runs differently, which changes PDF number rounding; measured
      on 71 of 100 real formulas, all <= 0.01).
    Box nuclei (\\mathop{lim}, \\text): their glyphs get ids too (role plain;
      base of scripts = the box's last glyph). Empty nucleus ({}^{x}): the
      script keeps its role with base None - recorded, never in `truth`.
    score(ids, roles, truth, pred) -> dict(found, missing, group, spurious, empty_base,
        missed=[dict(rel, base, script) as glyph indices], spurious_list)
      ids[k] = TeX id of glyph k (None if uncoloured); pred = encoding
      relations over the same glyph list. found: a truth relation predicted
      exactly; group: a prediction whose script is an in-<rel> char of a group
      with the same base and rel; empty_base: a prediction whose script TeX
      gave no base; spurious: every other prediction.
"""
import os, subprocess

REL = ("sup", "sub", "lim-over", "lim-under")
LAYOUT_TOL = 0.01
LUA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "texroles.lua")
_PRE = "\\documentclass{article}\\usepackage{amsmath,amssymb}\\pagestyle{empty}\n"


def colour_of(i):
    return ((i // 256) / 255, (i % 256) / 255, 1.0)


def id_of(c):
    if not isinstance(c, (tuple, list)) or len(c) != 3 or abs(c[2] - 1.0) > 1e-3:
        return None
    i = round(c[0] * 255) * 256 + round(c[1] * 255)
    return i or None


def _run(tex, d, stem):
    open(os.path.join(d, stem + ".tex"), "w").write(tex)
    subprocess.run(["lualatex", "-interaction=nonstopmode", stem + ".tex"], cwd=d,
                   capture_output=True, timeout=120)
    pdf = os.path.join(d, stem + ".pdf")
    if not os.path.exists(pdf):
        raise RuntimeError(f"no PDF; see {os.path.join(d, stem + '.log')}")
    return pdf


def build(latex, workdir):
    from . import oracle_colour as O
    os.makedirs(workdir, exist_ok=True)
    body = "\\begin{document}\n\\[ %s \\]\n\\end{document}\n" % latex
    rp = os.path.join(workdir, "roles.txt")
    for f in ("c.pdf", "p.pdf", "roles.txt"):
        if os.path.exists(os.path.join(workdir, f)):
            os.remove(os.path.join(workdir, f))
    c = _run(_PRE + "\\directlua{dofile('%s')}\n\\AtEndDocument{\\directlua{fj_texroles_write('%s')}}\n"
             # pdf2mmd2: the roles file is named relative to the run's
             # working directory; this TeX Live refuses Lua an absolute
             # output path (openout_any = p)
             % (LUA, "roles.txt") + body, workdir, "c")
    log = open(os.path.join(workdir, "c.log"), errors="replace").read()
    if "(mlist to hlist): error" in log:            # LuaTeX reports callback errors as warnings
        raise RuntimeError(f"texroles.lua failed; see {os.path.join(workdir, 'c.log')}")
    p = _run(_PRE + body, workdir, "p")
    C, P = O._chars(c), O._chars(p)
    roles = {}
    if os.path.exists(rp):
        for line in open(rp):
            i, role, base, ch, fam, style, fs, nuc, cls = line.rstrip("\n").split("\t")
            roles[int(i)] = dict(role=role, base=None if base == "nil" else int(base),
                                 char=int(ch), fam=int(fam), style=style,
                                 fstyle=None if fs == "-" else fs, nuc=None if nuc == "-" else nuc,
                                 cls=None if cls == "-" else cls)
    same, dev = layout_compare(C, P)
    glyphs = [dict(text=t, x0=x, base=y, id=id_of(col)) for _, x, y, t, col in C]
    shipped = {g["id"] for g in glyphs if g["id"]}
    truth = [dict(rel=r["role"], base=r["base"], script=i) for i, r in roles.items()
             if r["role"] in REL and r["base"] is not None and r["base"] in shipped and i in shipped]
    return dict(glyphs=glyphs, roles=roles, truth=truth, layout_identical=same, layout_max_dev=dev, pdf=c)


def score(ids, roles, truth, pred):
    idx = {i: k for k, i in enumerate(ids) if i}
    want = {(t["rel"], idx.get(t["base"]), idx.get(t["script"])) for t in truth}
    got = {(r["rel"], r["a"], r["b"]) for r in pred}
    found = want & got
    out = dict(found=len(found), missing=0, group=0, spurious=0, empty_base=0, missed=[], spurious_list=[])
    for rel, a, b in sorted(want - got, key=str):
        out["missing"] += 1
        out["missed"].append(dict(rel=rel, base=a, script=b))
    for rel, a, b in got - want:
        rb = roles.get(ids[b]) if isinstance(b, int) and b < len(ids) and ids[b] else None
        if rb and (rb["role"] in REL or rb["role"].startswith("in-")) and rb["base"] is None:
            out["empty_base"] += 1                    # TeX had no base: not spurious
        elif rb and rb["role"] == "in-" + rel and isinstance(a, int) and rb["base"] == ids[a]:
            out["group"] += 1
        else:
            out["spurious"] += 1
            out["spurious_list"].append(dict(rel=rel, a=a, b=b))
    return out


def layout_compare(a, b):
    if len(a) != len(b):
        return False, float("inf")
    A = sorted((t, x, y) for _, x, y, t, _ in a)
    B = sorted((t, x, y) for _, x, y, t, _ in b)
    if [t for t, _, _ in A] != [t for t, _, _ in B]:
        return False, float("inf")
    dev = max((abs(p[1] - q[1]) + abs(p[2] - q[2]) for p, q in zip(A, B)), default=0.0)
    return dev <= LAYOUT_TOL + 1e-9, dev
