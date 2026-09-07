"""634 fix round 1 — a path in INSPECT.txt is a promise, and EXISTENCE IS NOT
ENOUGH.

The defect these tests encode, verbatim. The 634 evidence capture ran

    pdfdrill model --ledger $DOC/*.pdf > $DOC/out/634/model-ledger.txt
    pdfdrill conserve        $DOC/*.pdf > $DOC/out/634/conserve.txt

in a folder holding SIX PDFs — every published document folder carries
`evidence-formula.pdf`, `evidence-equation.pdf`, `evidence-image.pdf`,
`evidence-table.pdf`, `report.pdf` and `residuals.pdf` beside the document
itself. The glob matched `evidence-equation.pdf`. Both captures were of the
wrong document. Both existed. Both were non-empty. INSPECT.txt certified them
as the document's own, and 408's existence check could not see it, because
the file it was checking was perfectly real.

So `inspect_list` now takes an optional `expect` and holds the file's FIRST
LINE to it — the line on which `pdfdrill conserve` and `model --ledger` both
name their subject.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import taskout


def _cap(tmp_path, name, first, rest="more output\n"):
    p = tmp_path / name
    p.write_text(first + "\n" + rest, encoding="utf-8")
    return p


def test_a_capture_of_the_wrong_document_is_refused_not_listed(tmp_path):
    """The exact defect, reconstructed from the two real first lines."""
    right = _cap(tmp_path, "conserve.txt", "conserve penev_A: NOT CONSERVED")
    wrong = _cap(tmp_path, "model-ledger.txt",
                 "Uploading /home/x/penev_A/evidence-equation.pdf...")
    res = taskout.inspect_list(tmp_path, "634",
                               [(right, "the conservation audit", "penev_A"),
                                (wrong, "the claim ledger", "penev_A")])
    listed = [a for a, _ in res["written"]]
    assert str(right.resolve()) in listed
    assert str(wrong.resolve()) not in listed
    why = dict(res["failed"])[str(wrong.resolve())]
    assert "first line does not name" in why and "penev_A" in why
    # and the file on disk carries only the path that kept its promise
    assert Path(res["path"]).read_text(encoding="utf-8").strip() == \
        str(right.resolve())


def test_the_right_document_passes_on_a_real_first_line(tmp_path):
    """Rule 11: a check that can only refuse has not been tested. Both real
    commands name their subject on line one, and both must pass."""
    a = _cap(tmp_path, "ledger.txt",
             "CLAIM LEDGER — penev_A  (stream mathpix_lines)")
    b = _cap(tmp_path, "conserve.txt", "conserve penev_A: NOT CONSERVED")
    res = taskout.inspect_list(tmp_path, "634",
                              [(a, "ledger", "penev_A"), (b, "conserve", "penev_A")])
    assert len(res["written"]) == 2 and not res["failed"]


def test_expect_may_ask_for_several_strings(tmp_path):
    a = _cap(tmp_path, "ledger.txt",
             "CLAIM LEDGER — penev_A  (stream mathpix_lines)")
    res = taskout.inspect_list(tmp_path, "634",
                               [(a, "", ["penev_A", "mathpix_lines"])])
    assert len(res["written"]) == 1
    res = taskout.inspect_list(tmp_path, "634",
                               [(a, "", ["penev_A", "latex_source"])])
    assert not res["written"] and "latex_source" in res["failed"][0][1]


def test_entries_without_an_expectation_behave_exactly_as_before(tmp_path):
    """The old two-tuple and bare-path forms must be untouched — every other
    task's call site passes them."""
    a = _cap(tmp_path, "x.txt", "anything at all")
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    res = taskout.inspect_list(tmp_path, "634",
                               [a, (a, "with a reason"), (empty, "empty")])
    assert len(res["written"]) == 2
    assert res["failed"] == [(str(empty.resolve()), "exists but is empty")]


def test_a_missing_file_is_still_reported_as_missing_not_as_a_mismatch(tmp_path):
    res = taskout.inspect_list(tmp_path, "634",
                               [(tmp_path / "nope.txt", "", "penev_A")])
    assert res["failed"][0][1] == "does not exist"


def test_the_first_line_read_is_bounded(tmp_path):
    """A 1.7 MB lines.json listed by mistake must cost a bounded read, not a
    full one."""
    big = tmp_path / "big.json"
    big.write_text("penev_A first line\n" + ("x" * 3_000_000), encoding="utf-8")
    assert taskout._FIRST_LINE_BYTES <= 65536
    res = taskout.inspect_list(tmp_path, "634", [(big, "", "penev_A")])
    assert len(res["written"]) == 1


def test_mentioning_the_folder_in_a_path_is_not_naming_the_document(tmp_path):
    """The REAL first line of the bad capture. It contains "penev_A" — inside
    the path — so a substring test passes it and the check would have been
    written and still not caught the defect it exists for."""
    bad = _cap(tmp_path, "cap.txt",
               "Uploading /home/wkolbe/pdfdrill-library/penev_A/"
               "evidence-equation.pdf...")
    assert "penev_A" in bad.read_text(encoding="utf-8")      # it IS in there
    res = taskout.inspect_list(tmp_path, "634", [(bad, "", "penev_A")])
    assert not res["written"]
    assert "first line does not name" in res["failed"][0][1]


def test_a_name_carrying_an_extension_or_punctuation_still_names(tmp_path):
    for first in ("conserve penev_A: NOT CONSERVED",
                  "CLAIM LEDGER — penev_A  (stream mathpix_lines)",
                  "penev_A.tex compiled, 97 pages",
                  "[penev_A] 1448 objects"):
        p = _cap(tmp_path, "c.txt", first)
        res = taskout.inspect_list(tmp_path, "634", [(p, "", "penev_A")])
        assert len(res["written"]) == 1, first
