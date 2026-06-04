"""
Ordered-stack segmentation (pdfdrill.continuity_scorer). Vendored from the
reviewed prototype with two bug fixes + the DataMatrix tracking-code two-level
model + the commercial provenance (sender=publisher, receiver=new field).

Tested here:
  * the original fixture still segments + names correctly;
  * BUG #1: a LEADING QR separator's payload now names the first document;
  * BUG #3: a body `1/2` does NOT get read as a page number (only banded/keyworded);
  * tracking codes: same trailing batch ⇒ one mailing (hard outer group), a
    different batch on an adjacent page ⇒ a hard boundary;
  * provenance: a document projects to a BibTeX-like record carrying publisher
    (=sender) and a `receiver` field.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import continuity_scorer as cs
from pdfdrill.continuity_scorer import PageFeatures, segment, parse_page_number, to_bibtex


def test_fixture_segments_and_names():
    res = segment(cs._fixture(), threshold=0.5)
    assert [tuple(d["pages"]) for d in res["documents"]] == [(1, 2), (3,), (4, 5, 6), (8,)]
    assert res["n_separators_dropped"] == 1


def test_bug1_leading_separator_payload_names_first_doc():
    pages = [
        PageFeatures(1, is_separator=True,
                     qr_payload={"type": "offer", "sender": "Lead AG", "date": "2024-01-01"}),
        PageFeatures(2, text="Angebot Lead AG preise konditionen", sender="Lead AG"),
    ]
    res = segment(pages)
    assert res["n_separators_dropped"] == 1
    doc = res["documents"][0]
    assert doc["pages"] == [2]
    assert doc["naming_evidence"]["source"] == "qr"        # payload, not OCR guesswork
    assert doc["naming_evidence"]["sender"] == "Lead AG"


def test_bug3_body_fraction_is_not_a_page_number():
    # "1/2" in body prose must NOT be parsed as a page number...
    assert parse_page_number("nimm 1/2 Tasse Mehl", allow_bare=False) is None
    # ...but a banded/keyworded one still is.
    assert parse_page_number("1/2", allow_bare=True) == (1, 2)
    assert parse_page_number("Seite 1/2") == (1, 2)
    assert parse_page_number("Seite 2 von 6") == (2, 6)


def test_tracking_codes_two_level_mailing_and_boundary():
    # three pages, shared trailing batch → one mailing (hard outer group)
    same = ["07411400030000000000000000000130151000000000",
            "07412400000000000000000000000130151000000000",
            "07413360000000000000000000000130151000000000"]
    pages = [PageFeatures(i + 1, text=f"content page {i+1} prose continues here",
                          tracking_code=c) for i, c in enumerate(same)]
    res = segment(pages)
    mids = {d["mailing"] for d in res["documents"]}
    assert len(mids) == 1                                  # all one mailing
    # a different batch on an adjacent page forces a boundary
    pages2 = [PageFeatures(1, text="aaa", tracking_code="11111000000000000000batchAAAAAAAA"),
              PageFeatures(2, text="aaa", tracking_code="22222000000000000000batchBBBBBBBB")]
    res2 = segment(pages2)
    assert res2["n_documents"] == 2
    assert any(g.get("mailing_boundary") for g in res2["gaps"])


def test_commercial_provenance_bibtex_has_publisher_and_receiver():
    doc = {"sender": "AOK Rheinland/Hamburg", "receiver": "Alexander Kolbe",
           "doctype": "reminder", "date": "20260527", "doc_number": "D990775288",
           "author": "Kompetenzteam Beiträge"}
    bib = to_bibtex(doc, key="aok2026")
    assert "@" in bib and "aok2026" in bib
    assert "AOK Rheinland/Hamburg" in bib                  # publisher = sender
    assert "receiver" in bib and "Alexander Kolbe" in bib  # the NEW explicit field
    assert "2026" in bib


if __name__ == "__main__":
    for fn in (test_fixture_segments_and_names, test_bug1_leading_separator_payload_names_first_doc,
               test_bug3_body_fraction_is_not_a_page_number,
               test_tracking_codes_two_level_mailing_and_boundary,
               test_commercial_provenance_bibtex_has_publisher_and_receiver):
        fn(); print("PASS", fn.__name__)
    print("\nAll tests passed.")
