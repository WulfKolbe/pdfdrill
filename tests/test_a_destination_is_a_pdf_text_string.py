r"""T-0073 — a NUL byte in `<doc>.glyphs.md`, and where it comes from.

conceptdrill found NUL bytes in three of the five physics papers of its
`kb-sets/physics-5.txt` fixture: s41586-022-04731-z 11,717, s41467-023-39995-0
449, s42005-020-0326-2 243; sciadv.aax7163 and s41598-023-32128-z are clean.
A NUL in a `.md` is a writer defect, so the first question is which writer.

IT IS NOT GLYPH TEXT. Every NUL arrives inside a Markdown link target —
`[<sup>9</sup>](#þÿ\x00S\x00p\x00r\x00i\x00n\x00g\x00e\x00r...)`. `þÿ` is
U+00FE U+00FF, which is the two bytes FE FF read one byte at a time, and FE FF
is the UTF-16BE byte-order mark. So the bytes are a PDF *text string* and the
reader decoded them as Latin-1: every ASCII character of a UTF-16BE string
keeps its NUL high byte, and the BOM becomes two printable letters.

ISO 32000-1 7.9.2.2 states the rule: a PDF text string is PDFDocEncoded, OR
UTF-16BE with a leading BOM. `pdfminer.utils.decode_text` implements exactly
that, and `_page_links` does not use it — it calls `dest.decode("latin1")`
(and the same for `uri`).

That also explains the split in the fixture. All three affected documents write
their destinations in UTF-16BE with a BOM (93, 85 and 60 of them, all bytes);
s41598-023-32128-z has 47 byte destinations with NO BOM, so Latin-1 happened
to agree with PDFDocEncoding on them, and sciadv.aax7163 has no destinations at
all. The defect is not "these three documents are odd" — it is "a BOM is not
read", and two of the five documents simply never present one.

THE QUIETER HALF. `LinkNode.citekey` is `dest[5:]` when `dest` starts with
`cite.` — the author's own BibTeX key, which the page itself does not carry.
Mis-decoded, a UTF-16BE `cite.polly` spells `þÿ\x00c\x00i\x00t\x00e\x00.…`, so
the prefix never matches and the key is silently dropped. The NUL is the
visible symptom; a lost citation key is the expensive one.

The hermetic fixture here is 752 bytes of PDF carrying one Link annotation
whose `/Dest` is `<FEFF0063006900740065002E0070006F006C006C0079>` — the
UTF-16BE spelling of `cite.polly`. It needs no library and no network.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pdfreader.docmodel_six import _dest_name, _page_links   # noqa: E402

#: The destination both fixtures name, chosen so `citekey` is also in play.
DEST = "cite.polly"


# ── the hermetic fixture ─────────────────────────────────────────────────────

def _minimal_pdf(dest_obj: bytes) -> bytes:
    """One page, one glyph, one Link annotation whose /Dest is `dest_obj`.

    `dest_obj` is written into the annotation verbatim, so a caller can pass
    either a hex string object (`<FEFF…>`) or a literal one (`(cite.polly)`)
    and compare what the reader makes of each.
    """
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
         b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> "
         b"/Annots [6 0 R] >>"),
        b"<< /Length 44 >>\nstream\nBT /F1 12 Tf 20 100 Td (22) Tj ET\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        (b"<< /Type /Annot /Subtype /Link /Rect [18 96 40 112] "
         b"/Border [0 0 0] /Dest " + dest_obj + b" >>"),
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, xref))
    return bytes(out)


def _utf16be_hex(text: str) -> bytes:
    """`<FEFF…>` — the text as a UTF-16BE PDF string object, BOM first."""
    return b"<" + (b"\xfe\xff" + text.encode("utf-16be")).hex().upper().encode() + b">"


def _one_link(tmp_path: Path, dest_obj: bytes, name: str):
    pdf = tmp_path / name
    pdf.write_bytes(_minimal_pdf(dest_obj))
    found = _page_links(str(pdf), None)
    assert sorted(found) == [1], f"expected one page of links, got {sorted(found)}"
    assert len(found[1]) == 1, f"expected one link, got {len(found[1])}"
    return found[1][0]


# ── the rule itself ──────────────────────────────────────────────────────────

def test_a_utf16be_destination_decodes_to_its_own_name(tmp_path):
    """The BOM says UTF-16BE, so `cite.polly` must come back as `cite.polly`."""
    link = _one_link(tmp_path, _utf16be_hex(DEST), "utf16dest.pdf")
    assert link.dest == DEST


def test_a_utf16be_destination_carries_no_nul(tmp_path):
    """The symptom conceptdrill saw, at the point where it enters.

    Latin-1 keeps every high byte, so a ten-character name arrives with ten
    NULs in it and `þÿ` in front.
    """
    link = _one_link(tmp_path, _utf16be_hex(DEST), "utf16dest.pdf")
    assert "\x00" not in (link.dest or ""), repr(link.dest)
    assert "￾" not in (link.dest or "")
    assert not (link.dest or "").startswith("þÿ"), repr(link.dest)


def test_a_utf16be_destination_still_yields_its_bibtex_key(tmp_path):
    """The quieter half: `citekey` is the author's own key, or nothing."""
    link = _one_link(tmp_path, _utf16be_hex(DEST), "utf16dest.pdf")
    assert link.citekey == "polly"


def test_a_pdfdocencoded_destination_is_unchanged(tmp_path):
    """No BOM means PDFDocEncoding, which agrees with ASCII here.

    This is the case s41598-023-32128-z presents on all 47 of its
    destinations, and it was never broken — so it is the regression this fix
    must not cause.
    """
    link = _one_link(tmp_path, b"(" + DEST.encode("ascii") + b")", "plaindest.pdf")
    assert link.dest == DEST
    assert link.citekey == "polly"


def test_a_destination_names_no_control_character(tmp_path):
    """A fragment identifier cannot carry C0 controls or a stray BOM.

    s41586-022-04731-z does not merely encode in UTF-16BE: it uses the whole
    reference text as the destination name, and those names carry 76 TABs, 76
    CRs and 1,392 embedded U+FEFF. Decoding correctly removes the NULs and
    leaves those, which is the same defect one layer down — a Markdown link
    target with a TAB in it.
    """
    link = _one_link(tmp_path, _utf16be_hex("cite.a\tb\r﻿c"), "ctl.pdf")
    bad = [ch for ch in (link.dest or "") if ord(ch) < 0x20 or ch == "﻿"]
    assert not bad, f"{[hex(ord(c)) for c in bad]} in {link.dest!r}"


# ── the other two shapes the same expression got wrong ───────────────────────

def test_a_name_object_destination_keeps_its_own_name(tmp_path):
    """`/Dest /cite.polly` is a NAME, not a string.

    pdfminer gives it as a `PSLiteral`, whose `str()` is `/'cite.polly'` —
    slash, quotes and all. Measured on 120 of the library's 7,762 PDFs: 1,630
    of 10,956 destinations are name objects, so this shape is commoner than
    the UTF-16 one that exposed the bug, and it costs the BibTeX key.
    """
    link = _one_link(tmp_path, b"/" + DEST.encode("ascii"), "namedest.pdf")
    assert link.dest == DEST
    assert link.citekey == "polly"


def test_an_explicit_destination_has_no_name(tmp_path):
    """`[3 0 R /XYZ 0 792 0]` names a place, not a label.

    941 of the same 10,956 destinations are arrays. `str()` turned each into a
    Python list repr and emitted it as a Markdown anchor. There is no name to
    anchor, and None says so.
    """
    link = _one_link(tmp_path, b"[3 0 R /XYZ 0 792 0]", "arraydest.pdf")
    assert link.dest is None
    assert link.citekey is None


# ── the real documents ───────────────────────────────────────────────────────

_LIB = Path.home() / "pdfdrill-library"

#: conceptdrill's `kb-sets/physics-5.txt`, with the NUL count each document's
#: `.glyphs.md` carried when the defect was reported (2026-11-01).
_PHYSICS_5 = {
    "s41586-022-04731-z": 11717,
    "s41467-023-39995-0": 449,
    "s42005-020-0326-2": 243,
    "sciadv.aax7163": 0,
    "s41598-023-32128-z": 0,
}


def _lib_pdf(name: str) -> Path:
    return _LIB / name / f"{name}.pdf"


@pytest.mark.skipif(not _lib_pdf("s41586-022-04731-z").is_file(),
                    reason="the physics-5 documents are not in the library")
@pytest.mark.parametrize("name", sorted(_PHYSICS_5))
def test_no_destination_in_the_physics_five_carries_a_nul(name):
    """The five documents conceptdrill named, read through `_page_links`.

    Three of them were affected and two were not; after the fix all five must
    read clean, and the two that were already clean must stay that way.
    """
    pdf = _lib_pdf(name)
    if not pdf.is_file():
        pytest.skip(f"{name} is not in the library")
    links = [ln for page in _page_links(str(pdf), None).values() for ln in page]
    dirty = [ln.dest for ln in links if ln.dest and "\x00" in ln.dest]
    assert not dirty, (f"{name}: {len(dirty)} of {len(links)} destinations "
                       f"carry a NUL, e.g. {dirty[0][:40]!r}")


@pytest.mark.skipif(not _lib_pdf("s41586-022-04731-z").is_file(),
                    reason="s41586-022-04731-z is not in the library")
def test_the_glyph_markdown_writes_no_nul_in_a_link_target():
    """The writer, end to end, on the worst of the three.

    Page 1 alone carried 29 anchors, 5,064 NULs and 27 TABs. The assertion is
    on the anchors rather than on the whole file, because that is where every
    one of them was.
    """
    from pdfreader import docmodel_six as _dm, project_mmd as _mmd
    pdf = _lib_pdf("s41586-022-04731-z")
    pages = _dm.build(str(pdf), pages=[0])
    md = _mmd.to_markdown(pages, doc_id="s41586-022-04731-z")
    anchors = re.findall(r"\]\(#([^)]*)\)", md)
    assert anchors, "page 1 of this document has 29 link anchors; found none"
    bad = [a for a in anchors
           if any(ord(ch) < 0x20 or ch == "﻿" for ch in a)]
    assert not bad, (f"{len(bad)} of {len(anchors)} anchors carry a control "
                     f"character, e.g. {bad[0][:60]!r}")
    assert "\x00" not in md, f"{md.count(chr(0))} NUL byte(s) in the markdown"


@pytest.mark.skipif(not _lib_pdf("arxiv.1412.6194").is_file(),
                    reason="arxiv.1412.6194 is not in the library")
def test_a_name_object_destination_yields_the_authors_bibtex_key():
    """The arXiv shape, on a real document.

    Page 1 of arxiv.1412.6194 carries 8 link annotations, 7 with a name-object
    destination: `theorem.2.12` and six citations, of which `LL` is cited
    twice. Before the fix every one read `/'cite.LL'` and every `citekey` was
    None.
    """
    pdf = _lib_pdf("arxiv.1412.6194")
    links = [ln for page in _page_links(str(pdf), [0]).values() for ln in page]
    dests = [ln.dest for ln in links if ln.dest]
    assert dests, "page 1 of this document has 7 named destinations"
    assert not [d for d in dests if d.startswith("/") or "'" in d], dests[:4]
    keys = sorted(ln.citekey for ln in links if ln.citekey)
    assert keys == ["DL", "GSh", "LL", "LL", "Litt", "Poonen"], keys


@pytest.mark.skipif(not _lib_pdf("s41586-022-04731-z").is_file(),
                    reason="s41586-022-04731-z is not in the library")
def test_the_fragment_filter_merges_no_two_destinations():
    """Stripping is not injective, so it could make two names one anchor.

    Raised by the coordinator's audit of 3276cf02 and measured rather than
    argued. The 120-PDF sample is VACUOUS for this question — not one of its
    10,015 named destinations carried a C0/C1/DEL/U+FEFF character, so the
    filter removed nothing there and could merge nothing. It fires on
    s41586-022-04731-z, which is the worst case we know of because its
    destination names are whole reference TEXTS: 1,544 characters are removed
    across 93 destinations, and all 93 still map to 93 distinct fragments.

    This is an upper bound on the risk, not a proof it cannot happen: a
    document whose names differ ONLY in stripped characters would collide. The
    assertion is that the one document where the filter does real work does
    not.
    """
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdfparser import PDFParser
    from pdfminer.pdftypes import resolve1

    pdf = _lib_pdf("s41586-022-04731-z")
    frags, dests = [], 0
    with open(pdf, "rb") as fh:
        doc = PDFDocument(PDFParser(fh))
        for page in PDFPage.create_pages(doc):
            raw = resolve1(page.annots) if page.annots else None
            for a in raw or []:
                a = resolve1(a)
                sub = a.get("Subtype")
                if getattr(sub, "name", sub) != "Link":
                    continue
                act = resolve1(a.get("A")) or {}
                d = a.get("Dest") or act.get("D")
                if d is None:
                    continue
                dests += 1
                frag = _dest_name(d)
                if frag is not None:
                    frags.append(frag)
    assert dests == 93, dests
    assert len(frags) == 93, len(frags)
    assert len(set(frags)) == len(frags), (
        f"{len(frags) - len(set(frags))} destination(s) merged into another")
