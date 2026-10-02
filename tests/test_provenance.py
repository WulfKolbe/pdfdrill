r"""
860 — a document's origin read from the DOCUMENT, not from how it arrived.

Provenance was recorded in exactly one place: `cli.py`, at download time, from
the URL. A paper handed to pdfdrill as a FILE therefore had none, and
`_arxiv_id_for`'s only fallback is the filename, which a Google Scholar download
never shapes like an id.

Measured over the library: 239 documents carry `source_arxiv_id`; 585 MORE have
the arXiv stamp in their own page text with nothing recorded. 71% of the arXiv
papers were anonymous to every free route that needs an id.

THE STAMP SUPPLIES WHAT THE FILENAME CANNOT. `0001124.pdf` is a bare number; the
stamp says `arXiv:hep-th/0001124v2`. Guessing the archive from the id's SHAPE is
what put fourteen viXra e-prints in this library labelled as arXiv (805/806), so
an archive prefix read off the page is the difference between a correct citation
and a wrong one.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest                                                  # noqa: E402

from pdfdrill.commands import _ARXIV_STAMP                     # noqa: E402

NEW = "arXiv:2405.08011v1  [cs.DL]  13 May 2024"
OLD = "arXiv:hep-th/0001124v2  18 Feb 2000"


@pytest.mark.parametrize("text,want", [
    (NEW, "2405.08011v1"),
    (OLD, "hep-th/0001124v2"),
    ("arXiv:quant-ph/0008113v1", "quant-ph/0008113v1"),
    ("arXiv:math/0010054v1", "math/0010054v1"),
    ("arXiv: 2007.05300", "2007.05300"),           # a space after the colon
    ("ARXIV:1102.1889V2", "1102.1889V2"),          # shouting
    ("…margin text arXiv:gr-qc/0012035v1 more", "gr-qc/0012035v1"),
])
def test_the_stamp_is_read_in_every_shape_the_corpus_has(text, want):
    m = _ARXIV_STAMP.search(text)
    assert m and m.group(1) == want, (text, m and m.group(1))


def test_the_archive_prefix_is_kept():
    r"""The whole point. `0001124` alone cannot be resolved; `hep-th/0001124`
    can, and guessing the archive from the id shape is defect 805/806."""
    m = _ARXIV_STAMP.search(OLD)
    assert "/" in m.group(1)
    assert m.group(1).startswith("hep-th/")


def test_a_doi_or_a_citation_is_not_a_stamp():
    """It must not fire on prose that merely mentions arXiv."""
    for text in ("see the arXiv listing for details",
                 "doi:10.1145/1145768.1145820",
                 "arXiv preprint, forthcoming",
                 "arXiv:notanid"):
        assert _ARXIV_STAMP.search(text) is None, text


def _doc(tmp_path, name, page_text):
    d = tmp_path / name
    d.mkdir()
    (d / f"{name}.pdf").write_bytes(b"%PDF-1.7\n%%EOF\n")
    (d / "probe-page-text.json").write_text(json.dumps({"pages": [page_text]}),
                                            encoding="utf-8")
    (d / f"{name}.drill.json").write_text(json.dumps({
        "pdf": f"{name}.pdf", "facts": ["SIZE_KNOWN"], "evidence": {},
    }), encoding="utf-8")
    return d / f"{name}.pdf"


def test_an_id_from_a_url_is_never_overwritten_by_a_stamp(tmp_path):
    r"""A stamp is the version arXiv SERVED; the PDF may since have been revised.
    An id read from the URL the file came from is stronger evidence, and a later
    reader must be able to tell which kind of claim it is looking at."""
    from pdfdrill.commands import cmd_provenance
    pdf = _doc(tmp_path, "paper", OLD)
    sc = json.loads((pdf.parent / "paper.drill.json").read_text())
    sc["evidence"] = {"source_arxiv_id": "1234.5678", "source_kind": "arxiv"}
    (pdf.parent / "paper.drill.json").write_text(json.dumps(sc), encoding="utf-8")

    out = cmd_provenance(pdf)
    assert "already carries arXiv:1234.5678" in out
    after = json.loads((pdf.parent / "paper.drill.json").read_text())
    assert after["evidence"]["source_arxiv_id"] == "1234.5678"


def test_a_recovered_id_is_marked_as_coming_from_the_stamp(tmp_path):
    from pdfdrill.commands import cmd_provenance
    pdf = _doc(tmp_path, "0001124", OLD)
    out = cmd_provenance(pdf)
    ev = json.loads((pdf.parent / "0001124.drill.json").read_text())["evidence"]
    assert ev["source_arxiv_id"] == "hep-th/0001124"
    assert ev["source_arxiv_version"] == "hep-th/0001124v2"
    assert ev["source_kind"] == "arxiv"
    assert ev["source_provenance"] == "stamp", \
        "the weaker kind of evidence must say so"
    assert "stamp" in out


def test_no_stamp_claims_nothing_but_records_that_it_looked(tmp_path):
    """Absent is not false: the document is marked as HAVING BEEN CHECKED, so the
    next run does not re-read the same pages to reach the same silence."""
    from pdfdrill.commands import cmd_provenance
    pdf = _doc(tmp_path, "acmpaper", "Proceedings of the 12th Conference")
    out = cmd_provenance(pdf)
    ev = json.loads((pdf.parent / "acmpaper.drill.json").read_text())["evidence"]
    assert "source_arxiv_id" not in ev
    assert ev["source_provenance"] == "none-found"
    assert "Nothing claimed" in out


def test_it_is_in_the_manifest_with_its_prerequisite():
    """A capability not in commands.yaml is invisible to `steps` and
    `--ensure` — audit A4."""
    import yaml
    y = yaml.safe_load((Path(__file__).resolve().parents[1]
                        / ".claude/skills/pdfdrill/commands.yaml")
                       .read_text(encoding="utf-8"))
    e = [c for c in y["commands"] if c["name"] == "provenance"][0]
    assert e["requires"] == ["size"]
    assert e["done_when"] == "fact:PROVENANCE_KNOWN"
    assert e["offline_ok"] is True, "the stamp read costs no network"
    assert "--verify" in {f["flag"] for f in e["flags"]}
