"""821 — figures get a LOCAL crop, so the LaTeX carries \\includegraphics.

Measured on four Krentsel papers before this: MathPix's own `.tex` carried 42
`\\includegraphics` and ours carried 0 — not a projector defect, `_figure_env`
emits a graphic only for a crop that is ON DISK, because naming a missing file
fails the whole compile. Nothing had rendered one.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_render_crops_covers_figures_not_only_tables():
    """`render_crops` was already parameterised by `kinds` and called with the
    default `("_TAB",)`, so every Picture and Diagram waited on the CDN. Across
    160 corpus documents, 13,968 `_PIC` and 976 `_DIA` tiddlers carry a region —
    recoverable from the PDF with no network, and unlike a CDN crop it cannot
    expire."""
    from pdfdrill.reports.crops import KINDS_ALL

    # 824 — the RESOLVED kinds, not the literals. This used to grep each call
    # site for `"_PIC"` and `"_DIA"`, which tested the spelling rather than the
    # coverage: passing the generated `KINDS_ALL` widens the kinds further
    # (it adds `_EQ` and `_FO`) and removed the literals, so the letter of the
    # assertion failed while its intent was more satisfied than before.
    # KINDS_ALL is built from the title scheme's own prefixes, so a kind added
    # there is covered here without anyone editing a tuple.
    assert {"_PIC", "_DIA", "_TAB"} <= set(KINDS_ALL), KINDS_ALL

    src = (Path(__file__).resolve().parents[1]
           / "src" / "pdfdrill" / "commands.py").read_text()
    lines = src.split("\n")
    calls = [ln for ln in lines if "rt.render_crops(" in ln]
    assert calls, "render_crops is no longer called"
    for i, ln in enumerate(lines):
        if "rt.render_crops(" not in ln:
            continue
        window = "\n".join(lines[i:i + 3])
        covers = ('"_PIC"' in window and '"_DIA"' in window) or "_CROP_KINDS" in window
        assert covers, ("this call site renders neither figures nor the full "
                        f"kind set:\n{window}")


def test_a_uri_is_not_a_picture():
    """`render_crops` skipped on the uri alone ("the CDN has it"), and MathPix
    crop URLs EXPIRE — measured 2026-09-27, a months-old conversion answers HTTP
    500 while two recent ones answer 200. A tiddler whose fetch failed was
    skipped here too and ended with no crop at all. The condition is whether the
    FILE is missing."""
    src = (Path(__file__).resolve().parents[1]
           / "src" / "pdfdrill" / "report_tex.py").read_text()
    body = src.split("def render_crops(", 1)[1].split("\ndef ", 1)[0]
    # the GUARD, not the docstring that also mentions the field
    guards = [ln.strip() for ln in body.split("\n")
              if "canonical_uri" in ln and ln.strip().startswith("if ")]
    assert guards, "the uri guard is gone entirely"
    assert all("have and" in g for g in guards), (
        f"the uri skip must require that the file is already there: {guards}")


def test_the_count_names_what_it_rendered():
    """It counted `_TAB` only and said "of N table crops" — a false statement
    once figures were rendered too (three Diagram crops reported as tables)."""
    src = (Path(__file__).resolve().parents[1]
           / "src" / "pdfdrill" / "commands.py").read_text()
    assert "table/figure crops" in src
    assert "n_local" in src


# ── the real documents ───────────────────────────────────────────────────────

_LIB = Path.home() / "pdfdrill-library"
_PAPERS = {"arxiv.2609.12039": 3, "arxiv.2607.22944": 4,
           "arxiv.2607.16387": 20, "arxiv.2605.23109": 15}


@pytest.mark.skipif(not (_LIB / "arxiv.2609.12039" / "latex").is_dir(),
                    reason="corpus documents not drilled")
@pytest.mark.parametrize("doc,want", sorted(_PAPERS.items()))
def test_the_latex_reaches_mathpix_parity_on_figures(doc, want):
    """MathPix's own .tex carries exactly this many `\\includegraphics` on each
    of these papers; ours now carries the same — inside `figure` environments
    with a `\\label`, which MathPix's has none of."""
    tex = _LIB / doc / "latex" / f"{doc}.tex"
    if not tex.is_file():
        pytest.skip(f"{doc} not projected")
    body = tex.read_text(encoding="utf-8", errors="replace")
    assert body.count("\\includegraphics") == want
    assert body.count("\\label{fig:") == want


@pytest.mark.skipif(not (_LIB / "arxiv.2609.12039" / "report-crops").is_dir(),
                    reason="crops not rendered")
def test_a_figure_crop_is_a_real_image_on_disk():
    crops = sorted((_LIB / "arxiv.2609.12039" / "report-crops").glob("*_DIA_*.jpg"))
    assert crops, "no diagram crops were rendered"
    for c in crops:
        assert c.stat().st_size > 500, f"{c.name} is a stub"
        assert c.read_bytes()[:2] == b"\xff\xd8", f"{c.name} is not a JPEG"
