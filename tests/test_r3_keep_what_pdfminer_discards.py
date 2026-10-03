r"""R3 — keep what pdfminer throws away: the font dict, and fontsize/scaling/rise.

CR-pdfminer-single-version R3. Two things stock pdfminer receives, uses and
drops, each of which cost psred a defect:

  * `spec`, the font's own PDF dictionary. Dropped, so `/Differences` and the
    embedded font program under `/FontDescriptor` (`/FontFile*`) cannot be
    reached from the font object. psred subclassed `PDFResourceManager.get_font`
    to get at it — and that does not run for a font resolved before the
    subclass is installed, so its /Differences source silently never fired.

  * `fontsize`, `scaling`, `rise` on `LTChar`. Consumed to compute `adv`,
    `bbox` and `upright`, then unreachable. BOTH ways of recovering them are
    traps, which is why the CR calls them pitfalls:
      - `matrix` does not contain the font size.
      - `size` is taken and means the glyph box's width or height.
      - `scaling` is ALREADY `Tz / 100` when `render_char` receives it, so
        dividing again gives x extents 100x too narrow (featjudge F10).

These run against the BUILT fork in `vendor/.pdfmm-venv`, not the interpreter
running the suite: the live pdfminer is deliberately left alone while a corpus
pass is using it. They skip when the venv is absent.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VENV_PY = ROOT / "vendor" / ".pdfmm-venv" / "bin" / "python"
PSRED = Path.home() / "psred"
T1 = PSRED / "fixtures" / "t1.pdf"
PSEUDO = PSRED / "fixtures" / "lang" / "text_t1.pdf"

PROBE = r'''
import json, sys
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar, LTContainer
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import PDFPageAggregator
from pdfminer.pdftypes import resolve1

pdf = sys.argv[1]

def walk(o):
    if isinstance(o, LTChar):
        yield o
    if isinstance(o, LTContainer):
        for c in o:
            yield from walk(c)

chars = [c for p in extract_pages(pdf, laparams=None) for c in walk(p)]
out = {"n": len(chars), "chars": [], "fonts": []}
for c in chars[:400]:
    out["chars"].append({
        "fontsize": getattr(c, "fontsize", None),
        "scaling": getattr(c, "scaling", None),
        "rise": getattr(c, "rise", None),
        "size": c.size,
        "matrix": list(c.matrix),
        "adv": c.adv,
        "width": c.width,
    })

rm = PDFResourceManager()
it = PDFPageInterpreter(rm, PDFPageAggregator(rm, laparams=None))
with open(pdf, "rb") as fh:
    for page in PDFPage.get_pages(fh):
        it.process_page(page)
        break
for f in rm._cached_fonts.values():
    spec = getattr(f, "spec", None)
    desc = resolve1(spec.get("FontDescriptor")) if spec else None
    enc = resolve1(spec.get("Encoding")) if spec else None
    diffs = resolve1(enc.get("Differences")) if isinstance(enc, dict) else None
    out["fonts"].append({
        "fontname": f.fontname,
        "has_spec": spec is not None,
        "spec_keys": sorted(map(str, spec or {})),
        "fontfile": sorted(k for k in map(str, desc or {}) if k.startswith("FontFile")),
        "n_differences": len(diffs) if diffs else 0,
    })
print(json.dumps(out))
'''


def _probe(pdf: Path) -> dict:
    if not VENV_PY.exists():
        pytest.skip(f"fork venv not built: {VENV_PY} (run vendor/install-pdfminer-fork.sh)")
    if not pdf.exists():
        pytest.skip(f"psred fixture not checked out: {pdf}")
    r = subprocess.run([str(VENV_PY), "-c", PROBE, str(pdf)],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def t1():
    return _probe(T1)


# --------------------------------------------------------------------------
# R3b — the three per-character values.
# --------------------------------------------------------------------------

def test_the_three_values_are_kept(t1):
    for c in t1["chars"]:
        assert c["fontsize"] is not None, "LTChar.fontsize is gone"
        assert c["scaling"] is not None, "LTChar.scaling is gone"
        assert c["rise"] is not None, "LTChar.rise is gone"


def test_fontsize_is_the_font_size_and_varies(t1):
    """A constant would mean the field is picking up something else. t1.pdf
    sets four sizes (CMBX12, CMR10, CMR7, CMMI10)."""
    sizes = {round(c["fontsize"], 4) for c in t1["chars"]}
    assert len(sizes) >= 3, sizes
    assert all(s > 0 for s in sizes)


def test_the_matrix_does_not_carry_the_font_size(t1):
    """PITFALL 1, stated by the CR and checked here rather than believed: the
    text matrix is (1, 0, 0, 1, tx, ty) on ordinary text, so a consumer
    deriving a size from it reads 1.0 whatever the type is set at."""
    scaled = [c for c in t1["chars"] if abs(c["matrix"][0] - 1.0) > 1e-9]
    assert not scaled, "fixture no longer demonstrates the pitfall"
    assert {round(c["fontsize"], 4) for c in t1["chars"]} != {1.0}


def test_size_is_a_different_quantity_and_looks_right(t1):
    """PITFALL 2. `LTChar.size` is the glyph box's width or height. On this
    fixture it happens to EQUAL the font size, which is exactly why reaching
    for it is dangerous — the mistake does not announce itself."""
    same = sum(1 for c in t1["chars"]
               if abs(c["size"] - c["fontsize"]) < 0.01)
    assert same > 0, (
        "the fixture no longer shows `size` coinciding with `fontsize`; the "
        "trap this documents is that the two agree often enough to be trusted")


def test_scaling_is_already_divided_by_a_hundred(t1):
    """PITFALL 3, the one that cost psred 100x-too-narrow extents (featjudge
    F10). `PDFTextDevice.render_string` does `textstate.scaling * 0.01`, so
    what reaches LTChar is the FACTOR, not the PDF `Tz` percentage. An
    unscaled document reads 1.0 here and would read 100 if it were raw Tz."""
    vals = {round(c["scaling"], 6) for c in t1["chars"]}
    assert vals == {1.0}, vals
    assert 100.0 not in vals, "this is raw Tz, not the already-scaled factor"


def test_adv_is_consistent_with_the_kept_values(t1):
    """`adv = textwidth * fontsize * scaling` in the constructor. If the kept
    fields were some other quantity, this identity would not hold."""
    ok = 0
    for c in t1["chars"]:
        if c["fontsize"] and c["adv"]:
            implied = c["adv"] / (c["fontsize"] * c["scaling"])
            assert 0 < implied < 2, implied        # a plausible text width
            ok += 1
    assert ok > 50, ok


# --------------------------------------------------------------------------
# R3a — the font dictionary.
# --------------------------------------------------------------------------

def test_the_font_dictionary_is_reachable(t1):
    assert t1["fonts"], "no fonts resolved"
    for f in t1["fonts"]:
        assert f["has_spec"], f["fontname"]
        assert f["spec_keys"], f["fontname"]


def test_the_embedded_font_program_is_reachable(t1):
    """The point of keeping the dict: `/FontFile*` lives under
    `/FontDescriptor`, and without the spec there is no route to it from the
    font object at all."""
    with_program = [f for f in t1["fonts"] if f["fontfile"]]
    assert with_program, (
        "no embedded font program reachable; /FontFile* is what the ink-box "
        "work (R4) reads")


def test_differences_are_reachable_on_the_font_that_has_them():
    """`text_t1.pdf` is the pdfTeX bitmap-font fixture: 122 `/Differences`
    entries, the `a44`/`a97` names R2 flags. Unreachable before R3."""
    data = _probe(PSEUDO)
    diffs = max(f["n_differences"] for f in data["fonts"])
    assert diffs > 100, data["fonts"]


def test_the_default_is_immutable_and_shared():
    """`PDFFont.spec` defaults to a MappingProxyType, so a font that never
    received a spec cannot have one written into the class by accident."""
    if not VENV_PY.exists():
        pytest.skip("fork venv not built")
    r = subprocess.run(
        [str(VENV_PY), "-c",
         "from pdfminer.pdffont import PDFFont;"
         "import types;"
         "print(type(PDFFont.spec).__name__, len(PDFFont.spec))"],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    kind, n = r.stdout.split()
    assert kind == "mappingproxy", kind
    assert n == "0", n


# --------------------------------------------------------------------------
# The CR's other acceptance condition: the byte-identical regression holds.
# --------------------------------------------------------------------------

#: sha256 over every PRE-EXISTING LTChar field across the four psred fixtures,
#: measured with the pre-R3 fork and again with the post-R3 one: identical.
#: R3 only ADDS attributes, so nothing a consumer already read may move.
EXISTING_SURFACE_SHA = "c656cdd65c66c8eeb5bd08f9877ee0540bb924eef919674f227ad90bb50818e2"
SURFACE_RECORDS = 942

SURFACE_PROBE = r'''
import hashlib, json, sys
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar, LTContainer
def walk(o):
    if isinstance(o, LTChar):
        yield o
    if isinstance(o, LTContainer):
        for c in o:
            yield from walk(c)
rows = []
for pdf in sys.argv[1:]:
    for p in extract_pages(pdf, laparams=None):
        for c in walk(p):
            rows.append([pdf.split("/")[-1], c.get_text(), c.glyphname, c.fontname,
                         [round(v, 6) for v in c.bbox], round(c.adv, 6),
                         [round(v, 6) for v in c.matrix], c.cid, c.render_mode,
                         round(c.size, 6), c.upright])
print(len(rows), hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest())
'''

FIXTURES = [
    PSRED / "fixtures" / "t1.pdf",
    PSRED / "fixtures" / "cff" / "t1_cff.pdf",
    PSRED / "fixtures" / "lang" / "text_t1.pdf",
    PSRED / "playground" / "featjudge" / "fixtures" / "plain.pdf",
]


def test_the_existing_ltchar_surface_is_byte_identical():
    """R3 ADDS fields. Everything a consumer could already read — text,
    glyphname, fontname, bbox, adv, matrix, cid, render_mode, size, upright —
    must be unchanged, and this is the hash that says so.

    It was taken twice: once from the pre-R3 fork (the live interpreter at the
    time) and once from the rebuilt one. They matched. A future change to the
    patch that moves any of these fails here, which is the whole point —
    'additive' is a statement about the diff, this is a statement about the
    OUTPUT."""
    if not VENV_PY.exists():
        pytest.skip("fork venv not built")
    missing = [f for f in FIXTURES if not f.exists()]
    if missing:
        pytest.skip(f"psred fixtures not checked out: {missing[0]}")
    r = subprocess.run([str(VENV_PY), "-c", SURFACE_PROBE] + [str(f) for f in FIXTURES],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    n, sha = r.stdout.split()
    assert int(n) == SURFACE_RECORDS, (
        f"{n} LTChar records, expected {SURFACE_RECORDS} — the fixtures or the "
        f"reader changed, so the hash below proves nothing until that is "
        f"explained")
    assert sha == EXISTING_SURFACE_SHA, (
        "the pre-existing LTChar surface MOVED. R3 is supposed to add fields "
        "and change nothing; something here changed what an existing consumer "
        "reads.")
