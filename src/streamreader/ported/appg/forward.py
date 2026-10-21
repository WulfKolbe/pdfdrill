# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# Ported from psred (github.com/WulfKolbe/psred), playground/featjudge/featjudge/appg/forward.py at origin/master 56cf8f6.
"""L2 - Appendix G forward rules as pure functions (TeX pt in, pt out).

Styles are 'D', "D'", 'T', "T'", 'S', "S'", 'SS', "SS'" (D > D' > ... > SS').
P is L0's params.load() dict (sigma/xi per size).

CONTRACT (Appendix G, current text; rule ids as in the rule book)
    size(C) -> 'text' | 'script' | 'scriptscript'    (which \\textfont2 etc. sigma comes from)
    cramp(C) = C'; is_cramped(C); up(C) = C-up (superscript style); down(C) = (C-up)'
    num(C), den(C): Rule 15a - numerator T (T') if C is D (D'), else C-up;
                    denominator T' if C > T, else C-down
    rule18(nuc, sup, sub, C, P) -> dict(u, v, steps)
      nuc = dict(char=bool, h, d)    the translated nucleus (char: a character box)
      sup / sub = dict(h, d) or None the script boxes
      u = superscript shift up (None if no sup), v = subscript shift down (None if no sub)
      18a: u = v = 0 for a character nucleus, else u = h - q, v = d + r with
           q = sigma_18 of size(up(C)), r = sigma_19 of size(down(C))
      18b (sub only): v = max(v, sigma_16, h(sub) - 4/5 |sigma_5|)
      18c: u = max(u, p, d(sup) + 1/4 |sigma_5|), p = sigma_13 if C = D,
           sigma_15 if C is cramped, sigma_14 otherwise
      18d: sup only -> u; both: v = max(v, sigma_17)
      18e: theta = xi_8; if (u - d(sup)) - (h(sub) - v) < 4 theta, set v so the
           gap is 4 theta; psi = 4/5 |sigma_5| - (u - d(sup)); psi > 0 -> u += psi, v -= psi
      sigma/xi are those of size(C) (the atom's style), except q, r (18a).
      steps: the sub-rules that set the final values, e.g. ['18a', '18c', '18e'].
    rule18_x(w, ic, sup, sub) -> dict(sup=dx or None, sub=dx or None), pt from
      the character nucleus's origin (Rules 17 and 18f, char nucleus): with no
      subscript the italic correction ic is a kern after the char, so a lone
      sup starts at w + ic; a sub starts at w; with both, the sup is shifted
      right by ic inside the script vbox: w + ic.
"""
STYLES = ("D", "D'", "T", "T'", "S", "S'", "SS", "SS'")


def rank(C):
    return len(STYLES) - STYLES.index(C)          # D highest


def gt(a, b):
    return rank(a) > rank(b)


def size(C):
    return "text" if C[0] in "DT" else "script" if C in ("S", "S'") else "scriptscript"


def is_cramped(C):
    return C.endswith("'")


def cramp(C):
    return C if is_cramped(C) else C + "'"


def up(C):
    base = {"D": "S", "T": "S", "S": "SS", "SS": "SS"}[C.rstrip("'")]
    return base + ("'" if is_cramped(C) else "")


def down(C):
    return cramp(up(C))


def num(C):
    if C in ("D", "D'"):
        return "T" + C[1:]
    return up(C)


def den(C):
    return "T'" if gt(C, "T") else down(C)


def rule18(nuc, sup, sub, C, P):
    s, x8 = P["sigma"][size(C)], P["xi"][size(C)][8]
    steps = ["18a"]
    if nuc["char"]:
        u = v = 0.0
    else:
        u = nuc["h"] - P["sigma"][size(up(C))][18]
        v = nuc["d"] + P["sigma"][size(down(C))][19]
    if sup is None:
        if sub is None:
            return dict(u=None, v=None, steps=[])
        v2 = max(v, s[16], sub["h"] - 0.8 * abs(s[5]))
        return dict(u=None, v=v2, steps=steps + ["18b"] if v2 != v else steps)
    p = s[13] if C == "D" else s[15] if is_cramped(C) else s[14]
    u2 = max(u, p, sup["d"] + 0.25 * abs(s[5]))
    if u2 != u:
        steps.append("18c")
    u = u2
    if sub is None:
        return dict(u=u, v=None, steps=steps)
    v2 = max(v, s[17])
    if v2 != v:
        steps.append("18d")
    v = v2
    if (u - sup["d"]) - (sub["h"] - v) < 4 * x8:
        v = 4 * x8 - (u - sup["d"]) + sub["h"]
        psi = 0.8 * abs(s[5]) - (u - sup["d"])
        if psi > 0:
            u, v = u + psi, v - psi
        steps.append("18e")
    return dict(u=u, v=v, steps=steps)


def rule18_x(w, ic, sup, sub):
    return dict(sup=(w + ic) if sup else None, sub=w if sub else None)
