# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# Ported from psred (github.com/WulfKolbe/psred), playground/featjudge/featjudge/space.py at origin/master 344c27d.
# Kept as close to the original as its new home allows; changes are marked "pdf2mmd2:".
# pdf2mmd2: the module docstring is a raw string (it holds \scriptspace).
r"""space - explicit spacing from stream moves minus TeX's automatic glue.

CONTRACT
    CLASSES: ord op bin rel open close punct inner (TeXbook ch. 18).
    glue_mu(left, right, style) -> 0, 3 (thin), 4 (med) or 5 (thick) mu; the
      table's parenthesised entries are 0 in script / scriptscript style; the
      impossible entries ('*') are 0.
    atom_class(char) -> class by character (REL, BIN, PUNCT, OPEN, CLOSE,
      OP sets below), 'ord' otherwise (single character, no context;
      Unicode variation selectors U+FE00..FE0F are ignored: CMEX big operators
      arrive as e.g. '∏' + U+FE02).
    classes(chars) -> atom classes of a formula's top-level atoms in order,
      with TeXbook rules 5 and 6: a bin becomes ord when it is first, follows
      bin/op/rel/open/punct, or precedes rel/close/punct or the end.
    explicit(move, left, right, style, em, after_script=False)
      -> (name, residual): residual = move - glue_mu*em/18 - (0.5 if
      after_script: TeX's default \\scriptspace in pt); name = the nearest of
      CANDIDATES within TOL pt, else 'unknown:<residual>'. All lengths in TeX
      pt; em = quad of the formula's size (font size in TeX pt).
    atom_gaps(glyphs, rels) -> [dict(prev, next, gap, after_script)] between
      consecutive atoms: an atom is a base glyph plus every glyph related to
      it by sup/sub/lim-over/lim-under (rels: encoding relations, a/b =
      indices); atoms ordered by their base's x; gap = next base's x - the
      previous atom's largest x + adv; after_script = the previous atom has a
      sup or sub (TeX adds \scriptspace), limits do not count.
    recover_generated(items, workdir) -> [name] for items (left, cmd, right):
      typesets '$<left><cmd> <right>$' one per page with pdflatex, traces the
      stream (trace.py) and applies `explicit` to the gap before <right>.
"""
import os, subprocess

CLASSES = ("ord", "op", "bin", "rel", "open", "close", "punct", "inner")
_T = """
0   1   (2) (3) 0   0   0   (1)
1   1   *   (3) 0   0   0   (1)
(2) (2) *   *   (2) *   *   (2)
(3) (3) *   0   (3) 0   0   (3)
0   0   *   0   0   0   0   0
0   1   (2) (3) 0   0   0   (1)
(1) (1) *   (1) (1) (1) (1) (1)
(1) 1   (2) (3) (1) 0   (1) (1)
"""
TABLE = {(CLASSES[i], CLASSES[j]): cell
         for i, row in enumerate(l.split() for l in _T.strip().splitlines()) for j, cell in enumerate(row)}
MU = {"0": 0, "1": 3, "2": 4, "3": 5}

REL = set("=<>≤≥≠∈∉⊂⊃⊆⊇→←↦≅∼≈≡⇒⇐⇔:")
BIN = set("+−-×·∗∘±∓∩∪⊕⊗÷")
PUNCT = set(",;")
OPEN = set("([{⟨")
CLOSE = set(")]}⟩!")
OP = set("∑∏∫∮⋃⋂⨁⨂")
CANDIDATES = {"none": 0.0, "\\,": 3 / 18, "\\:": 4 / 18, "\\;": 5 / 18, "\\!": -3 / 18,
              "\\quad": 1.0, "\\qquad": 2.0, "space": 3.33333 / 10}     # in em; 'space' = cmr interword
TOL = 0.05
SCRIPTSPACE = 0.5


def glue_mu(left, right, style):
    cell = TABLE[(left, right)]
    if cell == "*":
        return 0
    if cell.startswith("("):
        return 0 if style.startswith("script") else MU[cell.strip("()")]
    return MU[cell]


def atom_class(c):
    c = "".join(ch for ch in c if not 0xFE00 <= ord(ch) <= 0xFE0F)    # variation selectors
    for cls, s in (("rel", REL), ("bin", BIN), ("punct", PUNCT), ("open", OPEN), ("close", CLOSE), ("op", OP)):
        if c in s:
            return cls
    return "ord"


def classes(chars):
    cl = [atom_class(c) for c in chars]
    for i, c in enumerate(cl):
        if c != "bin":
            continue
        before = cl[i - 1] if i > 0 else None
        after = atom_class(chars[i + 1]) if i + 1 < len(chars) else None
        if before in (None, "bin", "op", "rel", "open", "punct") or after in (None, "rel", "close", "punct"):
            cl[i] = "ord"
    return cl


def explicit(move, left, right, style, em, after_script=False):
    r = move - glue_mu(left, right, style) * em / 18 - (SCRIPTSPACE if after_script else 0.0)
    name, d = min(((n, abs(r - v * em)) for n, v in CANDIDATES.items()), key=lambda t: t[1])
    return (name if d <= TOL else f"unknown:{r:.3f}"), r


def recover_generated(items, workdir):
    from . import trace
    os.makedirs(workdir, exist_ok=True)
    body = "\n\\newpage\n".join(f"${l}{c} {r}$" for l, c, r in items)
    open(os.path.join(workdir, "sp.tex"), "w").write(
        "\\documentclass{article}\\pagestyle{empty}\\begin{document}\n" + body + "\n\\end{document}\n")
    subprocess.run(["pdflatex", "-interaction=nonstopmode", "sp.tex"], cwd=workdir, capture_output=True)
    pdf = os.path.join(workdir, "sp.pdf")
    out = []
    for k, (l, c, r) in enumerate(items, 1):
        gl = [e for e in trace.trace(pdf, k) if e["kind"] == "glyph"]
        a, b = gl[-2], gl[-1]
        em = a["size"] * 72.27 / 72
        cl = classes([g["text"] for g in gl])
        out.append(explicit(b["move_before"] * 72.27 / 72, cl[-2], cl[-1], "text", em)[0])
    return out


def atom_gaps(glyphs, rels):
    member = {r["b"]: r["a"] for r in rels if r["rel"] in ("sup", "sub", "lim-over", "lim-under")}
    scripted = {r["a"] for r in rels if r["rel"] in ("sup", "sub")}
    bases = sorted((i for i in range(len(glyphs)) if i not in member), key=lambda i: glyphs[i]["x"])

    def root(i):
        while i in member:
            i = member[i]
        return i
    end = {}
    for i, g in enumerate(glyphs):
        r = root(i)
        end[r] = max(end.get(r, float("-inf")), g["x"] + g["adv"])
    return [dict(prev=a, next=b, gap=glyphs[b]["x"] - end[a], after_script=a in scripted)
            for a, b in zip(bases, bases[1:])]
