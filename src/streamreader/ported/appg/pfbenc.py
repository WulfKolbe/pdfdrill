# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
# Ported from psred (github.com/WulfKolbe/psred), playground/featjudge/featjudge/appg/pfbenc.py at origin/master 56cf8f6.
# Copied unchanged from the appg package of the parallel Appendix-G chat, 2026-10-13.
"""pfb_encoding.py — built-in /Encoding of a Type 1 font (.pfb or .pfa).
Contract: encoding(path) -> {code:int -> glyphname:str}; StandardEncoding fonts return {} (CM fonts all use explicit vectors)."""
import re

def _cleartext(data: bytes) -> str:
    if data[:1] == b"\x80":                       # PFB: segment 1 is cleartext
        n = int.from_bytes(data[2:6], "little")
        return data[6:6 + n].decode("latin-1")
    return data.split(b"eexec")[0].decode("latin-1")

def encoding(path):
    t = _cleartext(open(path, "rb").read())
    return {int(c): n for c, n in re.findall(r"dup\s+(\d+)\s*/(\S+)\s+put", t)}
