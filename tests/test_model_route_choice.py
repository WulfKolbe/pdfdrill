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


# --------------------------------------------------------------------------
# `--no-source` — suppress the author-LaTeX lanes — 809.
# --------------------------------------------------------------------------

def test_the_merged_route_is_skipped_when_the_source_is_suppressed():
    """On arXiv, `model` prefers the gold e-print: better structure, and the
    right default. But then the reader's LINE TYPES never become objects — the
    source supplies Section/Table/Formula and the classifier is consulted only
    for geometry. Comparing readers, or measuring a change to one, needs the
    source out of the way, and renaming the file to hide its id is a trick, not
    a flag.

    Measured on 2510.04618, same PDF, same lines.json:
        default      358 objects   source='latex'
        --no-source  439 objects   source='pdfminer-docmodel'
                                   43 Section, 7 Table, 108 Equation
    """
    from pdfdrill.commands import prefers_merged_route
    # the decision the flag has to be able to override
    assert prefers_merged_route(lines_exists=True, lines_source="pdfminer-docmodel",
                                is_arxiv=True, mathpix=False)


def test_the_flag_reaches_cmd_model():
    """A flag that exists only in a signature is not an override, it is a dead
    end (431). This asserts the CLI can set it."""
    import inspect
    from pdfdrill.commands import cmd_model
    from pdfdrill import cli
    assert "no_source" in inspect.signature(cmd_model).parameters
    src = inspect.getsource(cli._do_model)
    assert "--no-source" in src and "no_source=" in src


def test_it_is_declared_in_the_manifest():
    """A capability the manifest cannot see is invisible to `steps`, `--ensure`
    and the generated help (audit A4)."""
    from pdfdrill import planner
    model = next(c for c in planner.load_manifest()["commands"]
                 if c["name"] == "model")
    assert any(f.get("flag") == "--no-source" for f in model.get("flags") or [])
