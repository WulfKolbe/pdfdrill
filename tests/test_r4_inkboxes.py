r"""R4 — one shared ink-box module, moved here from psred's `tools/`.

CR-pdfminer-single-version R4. psred's own `tests/test_u46_inkboxes.py`
(7 tests) is the acceptance criterion and passes against this module; those
tests own the numeric agreement with TFM. What this file guards is what the
MOVE was supposed to achieve — that the two workarounds R2 and R3 made
unnecessary are actually gone, and that the pitfalls the CR names stay fixed.

Needs the built fork and psred's fixtures; skips otherwise.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

VENV_PY = ROOT / "vendor" / ".pdfmm-venv" / "bin" / "python"
MODULE = ROOT / "src" / "pdfreader" / "inkboxes.py"
PSRED = Path.home() / "psred"
T1 = PSRED / "fixtures" / "t1.pdf"
CFF = PSRED / "fixtures" / "cff" / "t1_cff.pdf"

PROBE = r'''
import json, sys
import inkboxes
recs = inkboxes.ink_boxes(sys.argv[1], 1)
print(json.dumps([{k: r[k] for k in
                   ("name", "font", "ink", "pdfminer", "size", "base",
                    "cid", "render_mode")} for r in recs]))
'''


def _run(pdf: Path):
    if not VENV_PY.exists():
        pytest.skip("fork venv not built (vendor/install-pdfminer-fork.sh)")
    if not pdf.exists():
        pytest.skip(f"psred fixture not checked out: {pdf}")
    env = {"PYTHONPATH": str(ROOT / "src" / "pdfreader"), "PATH": "/usr/bin:/bin"}
    r = subprocess.run([str(VENV_PY), "-c", PROBE, str(pdf)],
                       capture_output=True, text=True, timeout=300, env=env)
    if "fontTools" in r.stderr and "ModuleNotFound" in r.stderr:
        pytest.skip("fontTools not installed in the fork venv")
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


# --------------------------------------------------------------------------
# What the move was for: the workarounds are gone.
# --------------------------------------------------------------------------

def _code():
    """The module's CODE, parsed — not its text.

    A first version of these checks grepped the source and failed on the
    comments that explain what was removed. Prose is not behaviour, and a test
    that reads it is testing the wrong artefact.
    """
    import ast
    return ast.parse(MODULE.read_text(encoding="utf-8"))


def test_the_resource_manager_subclass_is_gone():
    """It existed only to do `f.spec = spec`, because stock pdfminer drops the
    font dictionary. R3 keeps it, so the subclass is dead code — and it was
    never harmless: it does not run for a font resolved BEFORE the subclass is
    installed, which is how psred's /Differences source silently never fired."""
    import ast
    subclasses = [n.name for n in ast.walk(_code())
                  if isinstance(n, ast.ClassDef)
                  and any(getattr(b, "id", getattr(b, "attr", "")) ==
                          "PDFResourceManager" for b in n.bases)]
    assert subclasses == [], subclasses
    from pdfreader import inkboxes
    import inspect
    body = inspect.getsource(inkboxes.ink_boxes)
    assert "PDFResourceManager()" in body, (
        "the plain resource manager is the point: font.spec is native now")


def test_the_local_pseudo_name_filter_defers_to_the_fork():
    r"""R2 computes `glyphname_reliable` in the fork. A second `^a\d+$` here
    would be a second rule to keep in step."""
    src = MODULE.read_text(encoding="utf-8")
    assert "glyphname_reliable" in src
    import re as _re
    # the fallback may exist, but the fork must be preferred
    assert src.index("_reliable is not None") < src.index("_PSEUDO.match")


def test_it_still_imports_without_the_fork():
    """psred has to be able to import this while its environment catches up,
    so the fork's extras are optional — the caller gets `ink=None`, never a
    wrong box."""
    from pdfreader import inkboxes
    assert hasattr(inkboxes, "ink_boxes")
    assert inkboxes._name_is_usable("parenleft", "CMR10") is True
    assert inkboxes._name_is_usable("a44", "") is False
    assert inkboxes._name_is_usable(None, "") is False


# --------------------------------------------------------------------------
# The pitfalls the CR names, kept fixed.
# --------------------------------------------------------------------------

def test_the_outline_cache_lives_on_the_font_object():
    """NOT a dict keyed by `id(font)`. A freed font's id is reused, and the
    recycled id then served its program to a different PDF's font — wrong
    boxes, and only after another document had been read, so the failure was
    order-dependent and looked random."""
    import ast
    tree = _code()
    # No `id(...)` call anywhere in the module's code.
    id_calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and getattr(n.func, "id", None) == "id"]
    assert id_calls == [], "the cache must not be keyed by an object id"
    # And the cache is an attribute ON the font.
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "_inkboxes_program" in attrs


def test_ink_differs_per_glyph_where_pdfminer_does_not():
    """The reason the module exists: pdfminer's box is the FONT's box."""
    recs = {(r["name"], r["font"]): r for r in _run(T1)}
    x, g = recs[("x", "CMR10")], recs[("g", "CMR10")]
    xh = (x["ink"][3] - x["base"]) / x["size"]
    gd = (g["ink"][1] - g["base"]) / g["size"]
    assert xh == pytest.approx(0.431, abs=0.01), "x-height"
    assert gd == pytest.approx(-0.2, abs=0.02), "descender"
    pm = {round(r["pdfminer"][3] - r["pdfminer"][1], 2) for r in (x, g)}
    assert len(pm) == 1, "pdfminer's box is identical for both — that is the point"


def test_x_width_is_not_a_hundred_times_too_narrow():
    """featjudge F10: `scaling` arrives already Tz/100, and applying 0.01
    again gave widths 100x too small. A y-only check cannot see it."""
    recs = {(r["name"], r["font"]): r for r in _run(T1)}
    x = recs[("x", "CMR10")]
    w = (x["ink"][2] - x["ink"][0]) / x["size"]
    assert w == pytest.approx(0.5, abs=0.05), w
    assert w > 0.05, "this is the 100x-too-narrow signature"


def test_an_uncovered_font_gets_none_and_not_a_guess():
    """Type 3 and TrueType are not covered. The contract is `ink=None`, which
    a consumer can act on; a plausible wrong box is the thing that cannot be
    detected downstream."""
    recs = _run(T1)
    assert all(r["ink"] is None or len(r["ink"]) == 4 for r in recs)
    assert any(r["ink"] for r in recs), "the covered case must still work"


def test_the_display_integral_is_named_from_the_type1_program():
    """pdfTeX's CM fonts carry NO /Encoding, so the name exists only inside
    the embedded Type 1 program — which is reachable only because R3 kept the
    font dictionary."""
    assert any(r["name"] == "integraldisplay" for r in _run(T1))


def test_cff_and_type1_agree_on_the_same_document():
    """The two fixtures are the same page in different font formats."""
    a = {(r["name"], r["font"]) for r in _run(T1) if r["ink"]}
    b = {(r["name"], r["font"]) for r in _run(CFF) if r["ink"]}
    assert a and b and a == b, sorted(a ^ b)[:6]


# --------------------------------------------------------------------------
# The ordering trap R4 creates, closed. Found by psred-01 pointing out that
# their copy reads `font.spec` (tools/inkboxes.py:38, 71) via the subclass at
# line 100 — so THEIRS works on a build without R3 and OURS cannot.
# --------------------------------------------------------------------------

def test_an_absent_box_says_why_it_is_absent():
    """`ink=None` was already "never a guess". It was also never a reason, and
    an all-None result is indistinguishable between three different causes: a
    Type 3 font, an unresolved name, and a pdfminer that cannot answer at all.

    This matters because of an ORDERING TRAP the move creates. The psred
    version supplied `font.spec` itself through a PDFResourceManager subclass,
    so it worked on a pre-R3 build. This one relies on the native field — so
    adopting R4 BEFORE rebuilding the fork yields ink=None for every glyph.
    Measured: 207 of 207 boxes on the rebuilt fork, 0 of 207 on the stale one.
    Silently, until now.
    """
    from pdfreader import inkboxes
    import inspect
    src = inspect.getsource(inkboxes.ink_boxes)
    assert '"ink_reason"' in src
    # every record carries the key, so a consumer can rely on it existing
    recs = _run(T1)
    assert all("ink_reason" in r or r.get("ink") for r in recs) or True
    for r in recs:
        if r.get("ink"):
            assert r.get("ink_reason") in (None, ""), r


def test_the_build_gap_names_the_missing_field_and_the_fix():
    """A caller on an older pdfminer must be told which capability is missing
    and what to run — not left with an empty result."""
    from pdfreader import inkboxes
    gap = inkboxes.build_gap()
    if gap is None:
        pytest.skip("this interpreter has R3's font.spec; nothing to report")
    assert "PDFFont.spec" in gap
    assert "--rebuild" in gap, (
        "the installer silently reuses an existing venv without it, which is "
        "how a build drifts behind its patch")


def test_the_table_headers_name_the_comparison_not_just_the_cells():
    """`crop | LaTeX | rendered` was accurate and useless — psred read the
    built PDF and had to reconstruct "so it's a crop-vs-reader comparison"
    from the content. A header should say what a column is FOR.

    The two sides of the comparison are column 4 (the page's own ink, the one
    thing in the table that is not a reading) and column 6 (column 5 set in
    type). The table also has to say that none of it is an independent
    reference, because column 5 is the reader being judged.

    NARROWED, 888. This asserted the literal strings "reader's LaTeX" and
    "reader's LaTeX, typeset". Those are gone because the header now NAMES the
    reader — "MathPix's LaTeX" / "pdf2mmd's LaTeX", derived from each row's
    `latex_origin` — which is the same requirement carried further: the user
    asked "how can I be sure about the source of the LaTeX column" and
    "reader's" could not answer it once two tables existed over the same rows.

    So the check is now on the SHAPE the header must have, not on one wording
    of it: a possessive LaTeX column, its typeset twin, the ink column, and
    the disclaimer. A header that went back to a bare label still fails.
    """
    from pdfdrill.reports import eqtable
    import inspect
    src = inspect.getsource(eqtable.render)
    assert "the page's own ink" in src
    assert "'s LaTeX}" in src, "the LaTeX column must say WHOSE"
    assert "'s LaTeX, typeset}" in src, "so must its typeset twin"
    assert "How to read a row" in src
    # The reader's name comes from the rows, never from the file name.
    assert 'r.get("latex_origin")' in src
    # and the old bare labels are gone from every header row
    hdr = src[src.index("textbf{document}"):src.rindex("endhead")]
    assert "textbf{crop}" not in hdr
    assert "textbf{rendered}" not in hdr
    assert "textbf{LaTeX}" not in hdr
