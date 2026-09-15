r"""Per-type bracket walk (prototype). Plain and sized delimiters counted per TYPE;
\left. / \right. are typeless. Categories:
  repairable_left_null : \left. … \right X  while a plain X-opener is unmatched   (EQ0393)
  repairable_right_null: \left X … \right.  while a plain X-closer follows unmatched
  sized_type_mismatch  : \left X … \right Y  with X, Y typed and different
  plain_imbalance      : plain opens != plain closes for a type, nothing sized involved
"""
import re
OPEN = {"(": "paren", "[": "brack", r"\{": "brace", r"\lbrace": "brace", r"\lbrack": "brack",
        r"\langle": "angle", r"\lceil": "ceil", r"\lfloor": "floor"}
CLOSE = {")": "paren", "]": "brack", r"\}": "brace", r"\rbrace": "brace", r"\rbrack": "brack",
         r"\rangle": "angle", r"\rceil": "ceil", r"\rfloor": "floor"}
AMBI = {"|": "vert", r"\|": "Vert", r"\vert": "vert", r"\Vert": "Vert"}
SIZE_L = r"\\(?:left|bigl|Bigl|biggl|Biggl)"
SIZE_R = r"\\(?:right|bigr|Bigr|biggr|Biggr)"
DELIM = r"(\\\{|\\\}|\\\||\\(?:lbrace|rbrace|lbrack|rbrack|langle|rangle|lceil|rceil|lfloor|rfloor|vert|Vert)(?![a-zA-Z])|[()\[\]|.])"
TOK = re.compile(r"(%s)\s*%s|(%s)\s*%s|%s|\\text\s*\{[^{}]*\}" % (SIZE_L, DELIM, SIZE_R, DELIM, DELIM))

def walk(lx):
    lx = re.sub(r"\\\\(\[[^\]]*\])?", " ", lx or "")          # row breaks, incl. \\[2pt]
    issues = []
    lr = []                                                  # TeX \left/\right stack: (kind, type, pos)
    plain_open = {}                                          # type -> [positions of unmatched plain openers]
    plain_close_unmatched = {}
    for m in TOK.finditer(lx):
        if m.group(0).startswith("\\text"):
            continue
        if m.group(1):                                       # sized left
            d = m.group(2)
            t = "." if d == "." else OPEN.get(d) or AMBI.get(d) or CLOSE.get(d)
            if m.group(1) == r"\left":
                lr.append((t, m.start(), dict((k, len(v)) for k, v in plain_open.items())))
        elif m.group(3):                                     # sized right
            d = m.group(4)
            t = "." if d == "." else CLOSE.get(d) or AMBI.get(d) or OPEN.get(d)
            if m.group(3) == r"\right":
                if not lr:
                    issues.append(("extra_right", t, m.start())); continue
                lt, lpos, snap = lr.pop()
                if lt == "." and t not in (".", None) and plain_open.get(t):
                    issues.append(("repairable_left_null", t, plain_open[t][-1]))
                    plain_open[t].pop()
                elif lt not in (".", None) and t == "." and t != lt:
                    issues.append(("repairable_right_null?", lt, lpos))
                elif "." not in (lt, t) and lt != t and not ({lt, t} <= {"vert"}):
                    issues.append(("sized_type_mismatch", "%s/%s" % (lt, t), lpos))
        else:
            d = m.group(5)
            if d == ".": continue
            if d in OPEN:
                plain_open.setdefault(OPEN[d], []).append(m.start())
            elif d in CLOSE:
                t = CLOSE[d]
                if plain_open.get(t): plain_open[t].pop()
                else: plain_close_unmatched.setdefault(t, []).append(m.start())
    for t in set(plain_open) | set(plain_close_unmatched):
        o, c = len(plain_open.get(t, [])), len(plain_close_unmatched.get(t, []))
        if o or c:
            issues.append(("plain_imbalance", "%s open%+d close%+d" % (t, o, c), None))
    return issues
