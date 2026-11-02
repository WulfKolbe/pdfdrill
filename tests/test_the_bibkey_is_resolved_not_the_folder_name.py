r"""Defect 516 — THE BIBKEY IS RESOLVED, NOT THE FOLDER NAME.

T-0116 pre-start item 2. The shape, verbatim, from this session's own harness:
an ingest script asked `titles_by_id(doc, <folder name>)` for the map it needed
to join 126 pix2text readings onto report rows. A report row id IS the tiddler
title, `<sanitised bibkey>_EQ0001`, so the join is a plain string match — and
the folder name is not the bibkey. `titles_by_id` returned a COMPLETE map under
the wrong prefix, every row missed, the script printed `row_id with no object:
5` and EXITED 0. The run was then analysed as if it had joined.

Nothing in the call could fail. That is the whole defect: a wrong bibkey is not
a wrong-looking argument, it is a well-formed one, and the only evidence is a
count nobody is required to read.

The repo already knows this. `report_tex.resolve_bibkey` exists for it and
carries the history — 404 inferred the bibkey from `blob_dir.name`, 463 read it
off the tiddlers FILENAME, and 462 renamed nine documents' bibkeys WITHOUT
renaming their folders, which is why a folder name cannot stand in for one. The
knowledge was written down and the next caller re-derived the bug anyway.

So the guard goes where the mistake is made, not where it is noticed: a
Document carries its own bibkey in `doc.meta["bibkey"]`, and asking for titles
under a different one is defect 516 by construction. `titles_by_id` now refuses
it and names both keys. A Document that carries no bibkey is unaffected —
`resolve_transclusions` is called module-level with no Document at all.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from docmodel.core import Document, DocObject, Realization    # noqa: E402
from docops.projectors.tiddlywiki import titles_by_id         # noqa: E402

#: What `resolve_bibkey` would return for the document.
RESOLVED = "2001.04425"
#: What the folder happens to be called. 462 renamed nine bibkeys and left the
#: folders alone, so this is the normal state of the library, not a contrivance.
FOLDER = "fong-spivak-seven-sketches"


def _doc(bibkey: str | None = RESOLVED, n: int = 3) -> Document:
    """A Document with `n` display Equations, in flow order."""
    doc = Document()
    if bibkey is not None:
        doc.meta["bibkey"] = bibkey
    mp = doc.ensure_stream("mathpix_lines")
    for i in range(n):
        anchor = mp.append(text=f"x_{i} = {i}", _page=1, _line_index=i,
                           type="math")
        eq = DocObject(type="Equation", props={
            "latex": f"x_{i} = {i}", "page": 1, "flow_index": i})
        eq.add_realization(Realization(stream="mathpix_lines", start=anchor,
                                       end=anchor, role="surface"))
        doc.add(eq)
    return doc


# ── the trap itself, before any guard can help ───────────────────────────────

def test_a_join_on_the_folder_name_matches_nothing():
    """Why a wrong bibkey is invisible: the map is complete and wrong.

    This is what the harness saw. `titles_by_id` under the folder name returns
    exactly as many entries as under the resolved key — same ids, same count,
    same shape — and not one of its titles is a row id. A consumer counting
    rows out of the join gets zero and nothing raises.
    """
    doc = _doc()
    right = titles_by_id(doc, RESOLVED)
    # the call that caused the defect, made against a document with no bibkey
    # so the guard cannot mask what the old code did
    wrong = titles_by_id(_doc(bibkey=None), FOLDER)

    assert len(wrong) == len(right) > 0
    row_ids = set(right.values())
    assert row_ids == {f"{RESOLVED}_EQ{i:04d}" for i in (1, 2, 3)}, row_ids
    assert not row_ids & set(wrong.values()), "the join would have matched"


# ── the guard ────────────────────────────────────────────────────────────────

def test_titles_by_id_refuses_a_bibkey_the_document_does_not_carry():
    """The document knows its own bibkey, so the folder name is refusable."""
    doc = _doc()
    with pytest.raises(ValueError) as exc:
        titles_by_id(doc, FOLDER)
    msg = str(exc.value)
    assert FOLDER in msg and RESOLVED in msg, msg


def test_titles_by_id_accepts_the_documents_own_bibkey():
    doc = _doc()
    titles = titles_by_id(doc, RESOLVED)
    assert set(titles.values()) == {f"{RESOLVED}_EQ{i:04d}" for i in (1, 2, 3)}


def test_titles_by_id_still_serves_a_document_with_no_bibkey():
    """`resolve_transclusions` is called with no Document at all, and
    fixtures across the suite build Documents without `meta["bibkey"]`. A
    document that names no key cannot contradict one."""
    titles = titles_by_id(_doc(bibkey=None), "whatever")
    assert set(titles.values()) == {f"whatever_EQ{i:04d}" for i in (1, 2, 3)}


def test_the_refusal_names_the_resolver_that_answers_it():
    """A refusal that does not say what to do instead gets worked around."""
    with pytest.raises(ValueError) as exc:
        titles_by_id(_doc(), FOLDER)
    assert "resolve_bibkey" in str(exc.value), str(exc.value)
