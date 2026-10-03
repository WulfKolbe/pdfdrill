r"""R2 — a reliability flag for numbered pseudo-names, against psred's fixtures.

CR-pdfminer-single-version R2. The measured defect class is pdfTeX's Type 3 /
PK bitmap fonts, whose `/Differences` names are `a44`, `a97`, `a111`. The fork
returns them faithfully as `glyphname`, so a caller receives something shaped
like an answer that names nothing. psred had to filter them or its "never
guess" test failed.

The acceptance criterion is a pair of real documents, and it is a pair for a
reason — one of them is the trap:

    fixtures/lang/text_t1.pdf   125 glyphs, ALL pseudo-names  -> 0 reliable
    fixtures/t1.pdf             233 glyphs, real CM names     -> all reliable

`t1.pdf` contains REAL glyphs named `a` (21 of them) and `g` (9). A rule
written as `[a-z]\d*` rather than `[a-z]\d+` passes the first document and
fails the second, which is exactly why the criterion names both.

These fixtures live in the psred repo, so the tests skip rather than fail when
it is not checked out beside this one.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfreader.texmap import glyphname_reliable                # noqa: E402

PSRED = Path.home() / "psred"
ALL_PSEUDO = PSRED / "fixtures" / "lang" / "text_t1.pdf"
ALL_REAL = PSRED / "fixtures" / "t1.pdf"
CFF = PSRED / "fixtures" / "cff" / "t1_cff.pdf"


def _glyphs(pdf: Path):
    """[(glyphname, fontname)] for every LTChar, read with layout analysis OFF.

    `laparams=None` matters: pdfminer's layout analysis reorders glyphs, and
    this reads the character stream, not a reading order.
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar, LTContainer

    def walk(o):
        if isinstance(o, LTChar):
            yield o
        if isinstance(o, LTContainer):
            for c in o:
                yield from walk(c)

    out = []
    for page in extract_pages(str(pdf), laparams=None):
        for ch in walk(page):
            out.append((ch.glyphname, ch.fontname))
    return out


def _require(pdf: Path):
    if not pdf.exists():
        pytest.skip(f"psred fixture not checked out: {pdf}")
    pytest.importorskip("pdfminer.high_level")


def test_the_pseudo_name_fixture_has_no_reliable_name():
    """`text_t1.pdf` -> 0 reliable. Every name is a pdfTeX bitmap-font index."""
    _require(ALL_PSEUDO)
    glyphs = _glyphs(ALL_PSEUDO)
    assert len(glyphs) == 125, f"fixture changed: {len(glyphs)} glyphs"
    reliable = [(n, f) for n, f in glyphs if glyphname_reliable(n, f)]
    assert reliable == [], (
        "%d name(s) accepted that carry no identity: %s"
        % (len(reliable), reliable[:5]))


def test_the_real_font_fixture_keeps_every_name():
    """`t1.pdf` -> all reliable. THE TRAP: it contains real glyphs named `a`
    and `g`, so a rule that distrusts a bare letter fails here."""
    _require(ALL_REAL)
    glyphs = _glyphs(ALL_REAL)
    assert len(glyphs) == 233, f"fixture changed: {len(glyphs)} glyphs"
    rejected = [(n, f) for n, f in glyphs if not glyphname_reliable(n, f)]
    assert rejected == [], (
        "%d real font name(s) rejected: %s" % (len(rejected), rejected[:5]))
    # and the trap is actually present, or the test proves nothing
    names = {n for n, _ in glyphs}
    assert "a" in names and "g" in names, (
        "the fixture no longer contains the bare-letter names this guards")


def test_the_cff_fixture_behaves_like_the_type1_one():
    """The patch covers CFF (Type 1C) too — same document, same names."""
    _require(CFF)
    rejected = [(n, f) for n, f in _glyphs(CFF) if not glyphname_reliable(n, f)]
    assert rejected == [], rejected[:5]


def test_zapfdingbats_keeps_its_own_numbered_names():
    """`a1`…`a191` are ZapfDingbats' REAL names, so the same string means
    opposite things depending on the font. Exempted by font name rather than
    silently mis-flagged — stated here because no fixture covers it."""
    assert glyphname_reliable("a44", "ABCDEF+ZapfDingbats") is True
    assert glyphname_reliable("a44", "ABCDEF+CMR10") is False


def test_it_is_a_flag_and_not_a_gate():
    """R2 asks for a reliability flag. `untrusted_name` is the function that
    abstains; this one reports and suppresses nothing."""
    from pdfreader.texmap import untrusted_name
    assert glyphname_reliable("a44", "") is False
    assert untrusted_name("ABCDEF+CMR10", "a44") is False


# --------------------------------------------------------------------------
# R2's second half: the flag ON LTChar, which is what the CR actually proposes.
# Read from the fork, not from a helper that happens to agree with it.
# --------------------------------------------------------------------------

import subprocess                                             # noqa: E402

VENV_PY = Path(__file__).resolve().parents[1] / "vendor" / ".pdfmm-venv" / "bin" / "python"

_LTCHAR_PROBE = r'''
import json, sys
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar, LTContainer
def walk(o):
    if isinstance(o, LTChar):
        yield o
    if isinstance(o, LTContainer):
        for c in o:
            yield from walk(c)
out = []
for pdf in sys.argv[1:]:
    chars = [c for p in extract_pages(pdf, laparams=None) for c in walk(p)]
    out.append({
        "pdf": pdf.split("/")[-1],
        "n": len(chars),
        "reliable": sum(1 for c in chars if c.glyphname_reliable),
        "names": [c.glyphname for c in chars[:5]],
        "text": [c.get_text() for c in chars[:5]],
    })
print(json.dumps(out))
'''


def _ltchar(*pdfs):
    if not VENV_PY.exists():
        pytest.skip(f"fork venv not built: {VENV_PY}")
    for p in pdfs:
        if not Path(p).exists():
            pytest.skip(f"psred fixture not checked out: {p}")
    r = subprocess.run([str(VENV_PY), "-c", _LTCHAR_PROBE, *map(str, pdfs)],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    import json
    return json.loads(r.stdout)


def test_the_flag_is_on_ltchar_and_meets_the_criteria():
    """THE CR's actual proposal: `LTChar.glyphname_reliable`. Computed in the
    fork at read time, so every consumer gets one rule instead of each
    reimplementing it — which is the whole point of a single patched build."""
    got = _ltchar(ALL_PSEUDO, ALL_REAL, CFF)
    by = {d["pdf"]: d for d in got}
    assert by["text_t1.pdf"]["n"] == 125
    assert by["text_t1.pdf"]["reliable"] == 0
    assert by["t1.pdf"]["n"] == 233
    assert by["t1.pdf"]["reliable"] == 233
    assert by["t1_cff.pdf"]["reliable"] == 233


def test_the_raw_name_is_kept(): 
    """"Keep `glyphname` raw" — the flag reports, it does not filter. The
    pseudo-names are still there to be inspected, and `get_text()` is
    untouched."""
    d = _ltchar(ALL_PSEUDO)[0]
    assert all(n and n.startswith("a") for n in d["names"]), d["names"]
    assert any(t.strip() for t in d["text"]), d["text"]


def test_the_package_helper_does_not_duplicate_the_rule():
    """One copy. `texmap.glyphname_reliable` delegates to the fork when it is
    installed; the local body is only a fallback for an environment whose
    pdfminer predates the flag."""
    from pdfreader import texmap
    import inspect
    src = inspect.getsource(texmap.glyphname_reliable)
    assert "_fork_reliable" in src, "the helper must prefer the fork's rule"


def test_the_fallback_agrees_with_the_fork():
    """The fallback cannot quietly drift from the authority it stands in for.
    Both are exercised over the same names and must return the same verdict."""
    if not VENV_PY.exists():
        pytest.skip("fork venv not built")
    from pdfreader import texmap
    names = ["a44", "a97", "a111", "g12", "cid7", "CID7", "index44", "glyph3",
             "uni0028", "u1D465", "parenleft", "a", "g", "one", "x",
             "summationdisplay", "space", "", None]
    probe = ("import json,sys;from pdfminer.layout import glyphname_reliable as f;"
             "print(json.dumps([f(n or None) for n in json.loads(sys.argv[1])]))")
    import json
    r = subprocess.run([str(VENV_PY), "-c", probe, json.dumps(names)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-1000:]
    fork = json.loads(r.stdout)
    local = [texmap._local_reliable(n) for n in names]
    assert fork == local, [
        (n, f, l) for n, f, l in zip(names, fork, local) if f != l]
