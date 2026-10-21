# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# Ported from psred (github.com/WulfKolbe/psred), psred/tfm.py at origin/master 344c27d.
# Kept as close to the original as its new home allows; changes are marked "pdf2mmd2:".
"""tfm - TeX font metrics for a glyph, from the local TeX installation.

CONTRACT
    metrics(font_base, glyph_name) -> dict(wd, ht, dp, ic) in em, or None
        font_base   PDF BaseFont, e.g. 'SCNYPU+CMMI10' (subset prefix ignored)
        glyph_name  as geometry reports it (Differences name or Latin-1 char)
    name -> TeX code through the Type 1 font's own encoding (kpsewhich
    <font>.pfb, 'dup N /name put'); code -> metrics through tftopl <font>.tfm.
    None when the font, the name or the code is not found (never a guess).
The fonts in `fontmetrics` (155: Computer Modern, AMS, txfonts, pxfonts
and their kin) are answered from code; any other font needs kpsewhich +
tftopl (TeX Live), without them it gets None.
"""
from __future__ import annotations

import functools, re, shutil, subprocess

ASCII = {"+": "plus", "=": "equal", "(": "parenleft", ")": "parenright", "[": "bracketleft",
         "]": "bracketright", ",": "comma", ".": "period", "<": "less", ">": "greater",
         "/": "slash", "-": "hyphen", ";": "semicolon", ":": "colon", "!": "exclam", "|": "bar"}
_DIG = {str(i): n for i, n in enumerate("zero one two three four five six seven eight nine".split())}


def _file(font_base):
    return (font_base or "").split("+")[-1].lower()


@functools.lru_cache(maxsize=None)
def _encoding(font):
    if not shutil.which("kpsewhich"):
        return {}
    for ext in (".pfb", ".pfa"):
        p = subprocess.run(["kpsewhich", font + ext], capture_output=True, text=True).stdout.strip()
        if p:
            raw = open(p, "rb").read()
            # FIRST occurrence wins: CM Type 1 encodings repeat glyphs at codes
            # above 160 (cmex10: bracketleftbigg at 20 AND 183); the TFM only
            # has 0-127, so the later code made the lookup fail
            enc = {}
            for c, n in re.findall(rb"dup (\d+) ?/([A-Za-z0-9.]+) put", raw):
                enc.setdefault(n.decode(), int(c))
            return enc
    return {}


@functools.lru_cache(maxsize=None)
def _chars(font):
    if not shutil.which("tftopl"):
        return {}
    p = subprocess.run(["kpsewhich", font + ".tfm"], capture_output=True, text=True).stdout.strip()
    if not p:
        return {}
    pl = subprocess.run(["tftopl", p], capture_output=True, text=True).stdout
    out = {}
    for blk in re.split(r"\n\(CHARACTER ", pl)[1:]:
        head, body = blk.split("\n", 1)
        kind, val = head.split()[:2]
        code = ord(val) if kind == "C" else int(val, 8) if kind == "O" else int(val)
        m = {k.lower(): float(v) for k, v in re.findall(r"\(CHAR(WD|HT|DP|IC) R (-?[\d.]+)\)", body)}
        out[code] = dict(wd=m.get("wd", 0.0), ht=m.get("ht", 0.0), dp=m.get("dp", 0.0), ic=m.get("ic", 0.0))
    return out


# pdf2mmd2: kpsewhich and tftopl cost about 0.1 s per call and every worker
# process would pay it for every font, so a font's two tables are kept in a
# file under the cache folder (PDF2MMD2_CACHE, default ~/.cache/pdf2mmd2).
@functools.lru_cache(maxsize=None)
def _table(font):
    # pdf2mmd2 (T-0038): the fonts pdf2mmd2 meets are tables in code; only a
    # font outside them asks the TeX installation (and the cache below)
    from .fontmetrics import table
    known = table(font)
    if known is not None:
        return known
    import json
    import os
    from pathlib import Path
    cache = Path(os.environ.get("PDF2MMD2_CACHE",
                                Path.home() / ".cache" / "pdf2mmd2")) / "tfm"
    path = cache / f"{font}.json"
    try:
        stored = json.loads(path.read_text())
        return stored["enc"], {int(k): v for k, v in stored["chars"].items()}
    except (OSError, ValueError, KeyError):
        pass
    enc, chars = _encoding(font), _chars(font)
    try:
        cache.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"enc": enc, "chars": chars}))
        os.replace(tmp, path)
    except OSError:
        pass
    return enc, chars


def metrics(font_base, glyph_name):
    f = _file(font_base)
    enc, chars = _table(f)
    name = ASCII.get(glyph_name, _DIG.get(glyph_name, glyph_name))
    code = enc.get(name)
    if code is None:
        return None
    return chars.get(code)
