r"""
839 — THE FOLDER'S NAME IS NOT THE LAYOUT.

`plan_relocation` and `find_docs` both answered "is this document already
migrated?" by asking whether its parent folder is named after it. That is a
proxy, and it came apart on three documents moved in from ~/Downloads: each
was `<stem>/<stem>.pdf`, correctly named, and each still had
`<stem>.pdf.drill/` and `<stem>.pdf.drill.json` inside it.

pdfdrill looks for `<stem>.drill.json`. So `status` answered "No information
gathered yet" for documents carrying a model, tiddlers, a semantic graph and a
rulebook — 31 to 83 files of work — and `relocate`, the one command whose job
is exactly this migration, skipped them as done.

The canonical layout has neither legacy name (its sidecar is `X.drill.json`,
with no `.pdf` in it), so the test is unambiguous and costs two stat calls.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.relocate import (                                # noqa: E402
    find_docs, legacy_remnants, plan_relocation)

PDF = b"%PDF-1.7 not-a-real-pdf\n%%EOF\n"


def _canonical(lib: Path, stem: str) -> Path:
    d = lib / stem
    d.mkdir(parents=True)
    (d / f"{stem}.pdf").write_bytes(PDF)
    (d / f"{stem}.drill.json").write_text("{}", encoding="utf-8")
    return d / f"{stem}.pdf"


def _half_migrated(lib: Path, stem: str) -> Path:
    """Named right, laid out wrong — the shape that was skipped."""
    d = lib / stem
    d.mkdir(parents=True)
    pdf = d / f"{stem}.pdf"
    pdf.write_bytes(PDF)
    (d / f"{stem}.pdf.drill.json").write_text('{"facts": []}', encoding="utf-8")
    blob = d / f"{stem}.pdf.drill"
    blob.mkdir()
    (blob / "model.docmodel.json").write_text("{}", encoding="utf-8")
    (blob / f"{stem}.tiddlers.json").write_text("[]", encoding="utf-8")
    return pdf


def test_a_canonical_doc_is_still_left_alone(tmp_path):
    """The 3,000 folders already migrated must not be touched."""
    pdf = _canonical(tmp_path, "paper")
    assert legacy_remnants(pdf) is False
    assert plan_relocation(pdf, tmp_path) == []
    assert find_docs(tmp_path) == []


def test_a_half_migrated_doc_is_recognised(tmp_path):
    pdf = _half_migrated(tmp_path, "paper")
    assert legacy_remnants(pdf) is True
    assert find_docs(tmp_path) == [pdf.resolve()]


def test_its_plan_flattens_in_place_and_never_moves_the_pdf(tmp_path):
    """The PDF is already where it belongs. A plan that 'moved' it to itself
    would be a self-move, and the only safe thing to do with one is skip it —
    better not to plan it."""
    pdf = _half_migrated(tmp_path, "paper")
    plan = plan_relocation(pdf, tmp_path)
    assert plan, "a half-migrated doc must have a plan"
    assert all(s != d for s, d in plan), [(str(s), str(d)) for s, d in plan if s == d]
    assert pdf not in [s for s, _ in plan], "the PDF itself must not move"
    dsts = {d.name for _, d in plan}
    assert "paper.drill.json" in dsts, "the sidecar must lose its .pdf infix"
    assert "model.docmodel.json" in dsts, "the blob must be flattened out"
    assert "paper.tiddlers.json" in dsts


def test_the_sidecar_rename_is_what_makes_the_work_visible(tmp_path):
    """`<stem>.pdf.drill.json` is invisible to every reader; `<stem>.drill.json`
    is the one pdfdrill opens."""
    pdf = _half_migrated(tmp_path, "paper")
    src = {s.name for s, _ in plan_relocation(pdf, tmp_path)}
    assert "paper.pdf.drill.json" in src


def test_an_unfoldered_doc_still_migrates_the_old_way(tmp_path):
    """The original case must keep working: a loose PDF moves into
    `<library>/<stem>/`."""
    lib = tmp_path / "lib"
    lib.mkdir()
    pdf = lib / "loose.pdf"
    pdf.write_bytes(PDF)
    (lib / "loose.pdf.drill.json").write_text("{}", encoding="utf-8")
    plan = plan_relocation(pdf, lib)
    assert (pdf, lib / "loose" / "loose.pdf") in plan
