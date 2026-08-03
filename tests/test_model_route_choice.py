"""Route choice must be a decision about CAPABILITY, not about file presence.

`cmd_model` took the merged (LaTeX structure + pdfminer geometry) route only
`if not lines_path.exists()`. So the FIRST build merged correctly, and every
rebuild afterwards — the lines.json now existing, having been written by that
very build — silently fell through to the lines-only route. Measured on
2209.00445v3: `model --force` turned a 287-object model (85 Paragraph, 73
Formula, 24 Section, 16 Table) into 48 objects with no structure at all.

A file that a route PRODUCES cannot be the condition for choosing that route.
The pdfminer lines.json is the merge's geometry INPUT, not a rival result.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.commands import prefers_merged_route


def test_no_lines_json_yet_and_arxiv_source_merges():
    assert prefers_merged_route(lines_exists=False, lines_source="", is_arxiv=True)


def test_rebuild_over_our_own_pdfminer_lines_still_merges():
    """The regression: the merge wrote these lines itself."""
    assert prefers_merged_route(lines_exists=True, lines_source="pdfminer-chars",
                                is_arxiv=True)
    assert prefers_merged_route(lines_exists=True, lines_source="pdfplumber-chars",
                                is_arxiv=True)


def test_mathpix_lines_win_over_the_merge():
    """MathPix supplies structure AND geometry AND real math — never override it."""
    assert not prefers_merged_route(lines_exists=True, lines_source="",
                                    is_arxiv=True, mathpix=True)


def test_no_arxiv_source_means_no_merge():
    assert not prefers_merged_route(lines_exists=False, lines_source="",
                                    is_arxiv=False)


def test_tesseract_lines_on_an_arxiv_doc_are_an_upgrade_candidate():
    """A tesseract build is the weakest route; gold LaTeX beats it."""
    assert prefers_merged_route(lines_exists=True, lines_source="tesseract",
                                is_arxiv=True)
