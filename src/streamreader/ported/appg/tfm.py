# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# Ported from psred (github.com/WulfKolbe/psred), playground/featjudge/featjudge/appg/tfm.py at origin/master 56cf8f6.
# Copied from the appg package of the parallel Appendix-G chat (tests T02/T09 there;
# featjudge change: load() split into load(path) + loads(bytes) - see loads();
# tfm_vs_luatex test here). Source: appg-appendix-g.tar.gz, 2026-10-13.
"""tfm.py — read a TFM file exactly as TeX does (tex.web §539–576).

Interface contract
------------------
    load(path, size_sp=None) -> Font
        size_sp: the at-size in scaled points; None = design size.
    Font.design_size_sp : int
    Font.size_sp        : int
    Font.param[k]       : int, k = 1..np (param[1] slant is the raw TeX value, others in sp)
    Font.chars[c]       : Char for every existing code c
    Char fields         : code, width, height, depth, italic (sp, as TeX stores them)
                          tag ('none'|'lig'|'list'|'ext'), next (successor code or None),
                          ext (dict top/mid/bot/rep, None for absent pieces) or None
    Font.ligkern(c)     : list of (next_char, ('kern', sp) | ('lig', op, rem)) for code c
No hidden state; pure function of the file bytes and size.
"""
from dataclasses import dataclass, field
import struct

TAGS = ("none", "lig", "list", "ext")


@dataclass
class Char:
    code: int
    width: int
    height: int
    depth: int
    italic: int
    tag: str
    next: int | None = None
    ext: dict | None = None


@dataclass
class Font:
    name: str
    design_size_sp: int
    size_sp: int
    param: dict = field(default_factory=dict)
    chars: dict = field(default_factory=dict)
    _lk: list = field(default_factory=list, repr=False)
    _kern: list = field(default_factory=list, repr=False)
    _ci: dict = field(default_factory=dict, repr=False)

    def ligkern(self, c):
        """Lig/kern program for char c (tex.web §545, §557)."""
        rem = self._ci.get(c)
        if rem is None or self.chars[c].tag != "lig":
            return []
        a = rem
        s, n, op, r = self._lk[a]
        if s > 128:
            a = 256 * op + r
        out = []
        while True:
            s, n, op, r = self._lk[a]
            if s <= 128:
                if op >= 128:
                    out.append((n, ("kern", self._kern[256 * (op - 128) + r])))
                else:
                    out.append((n, ("lig", op, r)))
            if s >= 128:
                break
            a += s + 1
        return out


def _scaler(z):
    """tex.web §572: returns function fix_word bytes -> scaled."""
    alpha = 16
    while z >= 0o40000000:
        z //= 2
        alpha += alpha
    beta = 256 // alpha
    alpha *= z

    def sw(a, b, c, d):
        v = (((d * z) // 256 + c * z) // 256 + b * z) // beta
        if a == 0:
            return v
        if a == 255:
            return v - alpha
        raise ValueError("bad TFM fix_word")
    return sw


def load(path, size_sp=None):
    return loads(open(path, "rb").read(), size_sp, name=path)


def loads(data, size_sp=None, name=""):
    """Added in featjudge (the only change to the copied file): parse TFM bytes."""
    path = name
    lf, lh, bc, ec, nw, nh, nd, ni, nl, nk, ne, np_ = struct.unpack(">12H", data[:24])
    words = [data[4 * i:4 * i + 4] for i in range(lf)]
    p = 6
    header = words[p:p + lh]; p += lh
    ci = words[p:p + ec - bc + 1]; p += ec - bc + 1
    W = words[p:p + nw]; p += nw
    H = words[p:p + nh]; p += nh
    D = words[p:p + nd]; p += nd
    I = words[p:p + ni]; p += ni
    LK = [tuple(w) for w in words[p:p + nl]]; p += nl
    K = words[p:p + nk]; p += nk
    E = [tuple(w) for w in words[p:p + ne]]; p += ne
    P = words[p:p + np_]

    # design size (tex.web §568): fix_word in units of 2^-20 pt -> sp: z = dsize div 16
    a, b, c, d = header[1]
    z_design = ((a * 256 + b) * 256 + c) * 16 + d // 16
    z = z_design if size_sp is None else size_sp
    sw = _scaler(z)
    f = Font(name=path.rsplit("/", 1)[-1], design_size_sp=z_design, size_sp=z)
    f._lk = LK
    f._kern = [sw(*k) for k in K]
    width = [sw(*w) for w in W]; height = [sw(*w) for w in H]
    depth = [sw(*w) for w in D]; italic = [sw(*w) for w in I]
    for i, w in enumerate(ci):
        wi, hd, it, rem = w
        if wi == 0:
            continue                                  # char does not exist
        code = bc + i
        tag = TAGS[it & 3]
        ch = Char(code, width[wi], height[hd >> 4], depth[hd & 15], italic[it >> 2], tag)
        if tag == "list":
            ch.next = rem
        elif tag == "ext":
            t, m, bo, r = E[rem]
            ch.ext = {"top": t or None, "mid": m or None, "bot": bo or None, "rep": r}
        f.chars[code] = ch
        f._ci[code] = rem
    # parameters (tex.web §575): param 1 (slant) is not scaled
    for k, w in enumerate(P, start=1):
        if k == 1:                                    # slant: pure number, §575
            a, b, c, d = w
            v = a - 256 if a > 127 else a
            v = (v * 256 + b) * 256 + c
            f.param[1] = v * 16 + d // 16
        else:
            f.param[k] = sw(*w)
    return f
