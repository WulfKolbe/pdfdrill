r"""THE TEST THE CHANGE REQUEST ASKS FOR: the fork changes no other function.

`test_pdfminer_fork_is_additive.py` proves the patch REMOVES nothing
(+461 / -0). That is a weaker claim than it reads as, and the repository
leaned on it as though it were the safety property. A patch can delete
nothing and still change behaviour, by adding lines INSIDE a function that
already exists — and this one does, in `PDFDevice.__init__`,
`PDFTextDevice.render_string`, `LTChar.__init__`,
`PDFLayoutAnalyzer.render_char`, `Type1FontHeaderParser.__init__`,
`Type1FontHeaderParser.get_encoding`, `PDFSimpleFont.__init__` and
`PDFType1Font.__init__`.

WHAT THIS FILE CAN AND CANNOT PROVE. It reads the patch, not a built
environment, so it runs anywhere — and a unified diff does not always name the
function a hunk lands in. `get_encoding`'s hunk begins mid-body with only
`class Type1FontHeaderParser` in its `@@` trailer. So the footprint is frozen
by (file, hunk context, lines added) rather than by function name, and the
behavioural claims below are checked on the added TEXT, which the patch does
carry in full.

THE THREE PROPERTIES THAT MAKE IT SAFE for the 33 files under `src/` that
import pdfminer:

  1. The FOOTPRINT is frozen. Any change to where, or how much, the fork
     touches fails here and has to be re-justified, instead of 33 callers
     finding out one defect at a time.
  2. Every added line binds a name the fork itself introduces. A line that
     reassigned an EXISTING attribute could change what a caller already
     reads; none does.
  3. Every parameter added to an existing signature has a DEFAULT, so callers
     that do not pass it are unaffected — `LTChar` is public API and gains
     `cid: int = -1, render_mode: int = 0`.

AND ONE CORRECTION. `vendor/README.md`, the integration spec and the
additivity test all said `get_encoding` "is not touched". It IS touched: the
body gains `self._cid2name[cid] = cast(str, name)`. What is true, and is what
the safety argument actually needs, is narrower — that line fills a NEW
private dict and leaves the RETURNED mapping alone, so the Unicode channel
every existing caller reads is unchanged. "Untouched" and
"behaviour-preserving" are different claims and only the second was ever true.
"""
import re
from pathlib import Path

import pytest

PATCH = Path(__file__).resolve().parents[1] / "vendor" / "pdfminer-glyph-identity.patch"

#: The fork's footprint: (file, `@@` context, lines added). Frozen.
#:
#: UPDATED DELIBERATELY FOR R3 (CR-pdfminer-single-version), which is the only
#: way this set may ever change. R3 keeps what pdfminer discards — the font's
#: own dictionary, and the per-character fontsize/scaling/rise — so:
#:
#:     LTChar hunk            16 -> 37   the three fields and why they matter
#:     PDFFont class attrs    21 -> 36   `spec` immutable default
#:     PDFSimpleFont          new, +1    self.spec = spec
#:     PDFCIDFont             new, +4    self.spec = spec (the other root)
#:
#: Nothing else moved: no new file, no new class, and the gate printed exactly
#: that before this list was edited — which is what the freeze is for. A
#: future change that cannot be explained in these terms is a change that
#: UPDATED AGAIN FOR R2's LTChar FLAG, and the gate confined it to ONE file:
#:
#:     layout.py, no class context     new, +1    `import re`
#:     layout.py, before LTChar        new, +42   the predicate
#:     LTChar hunk                    37 -> 43    self.glyphname_reliable
#:
#: pdffont.py, pdfdevice.py, converter.py and encodingdb.py are untouched by
#: R2, which is what makes it a small change rather than a claim that it is.
#:
#: UPDATED FOR 878, a defect R2 ITSELF introduced and the corpus found:
#: `LTChar.__init__` now calls `glyphname_reliable` INSIDE pdfminer, earlier
#: than the normalisation in `docmodel_six`, so a font program stating its
#: names as BYTES reached a str regex and stopped the read. Decoded where the
#: name becomes an attribute (+12 in LTChar), and the predicate made total
#: (+2). Confined to layout.py, as R2 was.
#:
#: needs re-reading, not a list that needs updating.
EXPECTED_FOOTPRINT = {
    ("pdfminer/converter.py", "class PDFLayoutAnalyzer(PDFTextDevice):", 2),
    ("pdfminer/encodingdb.py", "class EncodingDB:", 7),
    ("pdfminer/encodingdb.py", "class EncodingDB:", 8),
    ("pdfminer/encodingdb.py", "class EncodingDB:", 38),
    ("pdfminer/layout.py", "", 1),
    ("pdfminer/layout.py", "class LTAnno(LTItem, LTText):", 44),
    ("pdfminer/layout.py", "class LTChar(LTComponent, LTText):", 12),
    ("pdfminer/layout.py", "class LTChar(LTComponent, LTText):", 55),
    ("pdfminer/pdfdevice.py", "class PDFDevice:", 10),
    ("pdfminer/pdfdevice.py", "class PDFTextDevice(PDFDevice):", 1),
    ("pdfminer/pdffont.py", "FontWidthDict = dict[int | str, float]", 36),
    ("pdfminer/pdffont.py", "class PDFCIDFont(PDFFont):", 4),
    ("pdfminer/pdffont.py", "class PDFFont:", 14),
    ("pdfminer/pdffont.py", "class PDFSimpleFont(PDFFont):", 1),
    ("pdfminer/pdffont.py", "class PDFSimpleFont(PDFFont):", 16),
    ("pdfminer/pdffont.py", "class PDFType1Font(PDFSimpleFont):", 1),
    ("pdfminer/pdffont.py", "class Type1FontHeaderParser(PSStackParser[int]):", 1),
    ("pdfminer/pdffont.py", "class Type1FontHeaderParser(PSStackParser[int]):", 16),
    ("pdfminer/pdffont.py", "import logging", 1),
}

#: Names the fork introduces. An added line may bind these and nothing else.
NEW_NAMES = {
    "textstate_render", "_cid2name", "cid2name", "cid", "glyphname",
    "render_mode", "invisible", "get_encoding_names", "get_glyphnames",
    "to_glyphname", "_is_symbolic", "MappingProxyType",
    "std2name", "mac2name", "win2name", "pdf2name", "name_encodings",
    # R3 — kept rather than discarded. `spec` is the font's own PDF
    # dictionary; `fontsize`/`scaling`/`rise` are the three values LTChar was
    # handed and dropped.
    "spec", "fontsize", "scaling", "rise",
    # R2's LTChar flag and the predicate behind it.
    "glyphname_reliable", "_PSEUDO_GLYPHNAME", "_DINGBAT_FONT",
    "_gn",          # 878 — the decoded glyph name, local to LTChar.__init__
}

_HDR = ("--- ", "+++ ", "diff --git", "index ", "new file", "deleted file",
        "similarity ", "rename ")
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@ ?(.*)")
#: `self.X = ...` and `X = ...` are different questions: the first asks
#: whether the CLASS already has an attribute X, the second whether the
#: function already has a local X. Conflating them made
#: `self.fontsize = fontsize` read as a reassignment of stock pdfminer's
#: local `fontsize`, which it is not.
_BIND_ATTR = re.compile(r"^\s*self\.([A-Za-z_]\w*)\s*(?::[^=]*)?=(?!=)")
_BIND_LOCAL = re.compile(r"^\s*([A-Za-z_]\w*)\s*(?::[^=]*)?=(?!=)")


def _hunks():
    """[(file, context, [(kind, text), ...])]. File headers are NOT content —
    counting their leading '-' as deletions is five false positives here."""
    out, cur, lines = [], None, None
    for line in PATCH.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("+++ b/"):
            cur, lines = line[6:], None
            continue
        if line.startswith(_HDR):
            continue
        m = _HUNK.match(line)
        if m:
            lines = []
            out.append((cur, m.group(1).strip(), lines))
            continue
        if lines is None or line.startswith("\\"):
            continue
        if line[:1] in "+- ":
            lines.append((line[0], line[1:]))
    return [h for h in out if h[0] and not h[0].startswith("tests/")]


@pytest.fixture(scope="module")
def hunks():
    if not PATCH.exists():                                   # pragma: no cover
        pytest.skip("vendored patch not present")
    return _hunks()


def test_the_footprint_is_frozen(hunks):
    """Where the fork touches, and how much, may not change silently. This is
    the whole request: a rebase that starts editing another function, or
    editing one of these more deeply, fails here."""
    got = {(f, ctx, sum(1 for k, _ in body if k == "+"))
           for f, ctx, body in hunks}
    assert got == EXPECTED_FOOTPRINT, (
        "the fork's footprint changed.\n  new:  %s\n  gone: %s\n"
        "Re-read the fork's safety argument before accepting this."
        % (sorted(got - EXPECTED_FOOTPRINT), sorted(EXPECTED_FOOTPRINT - got)))


def test_every_added_line_binds_only_a_name_the_fork_introduces(hunks):
    """Property 2. A line inserted into an existing function is safe when it
    creates NEW state; one that reassigns an existing attribute is not."""
    bad = []
    for path, ctx, body in hunks:
        # Added lines that belong to a def the patch ITSELF adds are a new
        # function's own body: its locals are its own business and cannot
        # affect any existing caller. Only lines inserted into code that was
        # already there are governed by this rule. (Each hunk here introduces
        # at most one new def, so "after the first added def" is sufficient —
        # `test_the_footprint_is_frozen` fails if that ever stops holding.)
        in_new_def = False
        for kind, text in body:
            if kind == " ":
                in_new_def = False
                continue
            if kind != "+":
                continue
            s = text.split("#", 1)[0].strip()
            if s.startswith(("def ", "@staticmethod", "@classmethod",
                             "@property", "async def ")):
                in_new_def = True
                continue
            if in_new_def or not s or s.startswith(("class ", "return ", '"""')):
                continue
            m = _BIND_ATTR.match(text) or _BIND_LOCAL.match(text)
            if m and m.group(1) not in NEW_NAMES:
                bad.append((path, ctx[:40], s[:60]))
    assert not bad, "added line binds a name the fork does not introduce: %s" % bad


def test_new_parameters_have_defaults(hunks):
    """Property 3. `LTChar` is public; a new required parameter would break
    every existing construction of one."""
    added = [t for _, _, b in hunks for k, t in b if k == "+"]
    joined = "\n".join(added)
    for param in ("cid: int", "render_mode: int"):
        if param in joined:
            line = next(l for l in added if param in l)
            assert "=" in line, "new parameter without a default: %r" % line
    assert "cid: int = -1" in joined
    assert "render_mode: int = 0" in joined


def test_get_encoding_keeps_its_return_value(hunks):
    """THE CORRECTION. `get_encoding` is modified — the repo said it was not.
    The real property: the added line fills a new private dict and leaves the
    returned mapping alone."""
    line = "self._cid2name[cid] = cast(str, name)"
    added = [t.strip() for _, _, b in hunks for k, t in b if k == "+"]
    assert line in added, (
        "get_encoding's added line is gone or changed; the claim that it is "
        "behaviour-preserving has to be re-made, not assumed")
    for t in added:
        if "_cid2unicode" in t:
            pytest.fail("the fork now writes the Unicode channel: %r" % t)


def test_the_allowlist_is_not_a_loophole(hunks):
    """NEW_NAMES is hand-written, and a hand-written allowlist is exactly how
    a reassignment of an EXISTING attribute would be waved through. So every
    name on it must be one the patch INTRODUCES: it may never appear as a
    binding on a context line, which is stock pdfminer's own code.

    `name_encodings` is the case that prompted this. It binds beside the
    existing `encodings` dict and looks identical in shape; the difference —
    the only difference that matters — is that stock pdfminer has no such
    attribute, and the patch's own context lines prove it.
    """
    context_bindings = set()
    for _, _, body in hunks:
        for kind, text in body:
            if kind != " ":
                continue
            # Only ATTRIBUTE bindings in stock code can be reassigned by an
            # added `self.X = ...`; a stock local named `fontsize` says
            # nothing about whether LTChar has a `.fontsize`.
            m = _BIND_ATTR.match(text)
            if m:
                context_bindings.add(m.group(1))
    leaked = sorted(NEW_NAMES & context_bindings)
    assert not leaked, (
        "these are on the fork's allowlist but stock pdfminer already binds "
        "them, so an added line could be REASSIGNING one: %s" % leaked)


def test_nothing_is_deleted(hunks):
    """Belt and braces with the additivity gate, and parsed correctly: a
    deletion inside an existing function is the one change that cannot be
    made safe by any of the properties above."""
    removed = [t for _, _, b in hunks for k, t in b if k == "-"]
    assert removed == [], removed[:3]
