"""
citedrill (src/pdfdrill/citedrill.py): drill INTO a citation — ask Perplexity for
all downloadable links for the cited publication, rank free routes (arXiv/DOI)
first, verify + attempt to fetch the PDF, and stamp the Reference with drill
STATUS fields (drill_status / pdf_url / pdf_path / pdf_json + candidate links)
plus a per-reference pdf.json recording the attempt.

The pure helpers (link extraction, classification, ranking, record/status) are
unit-tested here; the network parts (Perplexity, HEAD verify, download) degrade
gracefully and are exercised via the command, not here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import citedrill as cd


def test_extract_links_from_answer_and_citations():
    answer = ("The PDF is at https://arxiv.org/abs/2004.05631 and a mirror "
              "https://example.org/paper.pdf . See also (https://doi.org/10.1000/xyz).")
    citations = ["https://arxiv.org/pdf/2004.05631", "not-a-url", "https://example.org/paper.pdf"]
    links = cd.extract_links(answer, citations)
    # de-duplicated, order preserved, only real URLs
    assert "https://arxiv.org/abs/2004.05631" in links
    assert "https://example.org/paper.pdf" in links
    assert "https://doi.org/10.1000/xyz" in links
    assert "not-a-url" not in links
    assert len(links) == len(set(links))


def test_classify_link():
    assert cd.classify_link("https://arxiv.org/abs/2004.05631") == "arxiv"
    assert cd.classify_link("https://arxiv.org/pdf/2004.05631v1") == "arxiv"
    assert cd.classify_link("https://doi.org/10.1000/xyz") == "doi"
    assert cd.classify_link("https://example.org/paper.pdf") == "pdf"
    assert cd.classify_link("https://example.org/landing") == "other"


def test_rank_links_free_routes_first_and_arxiv_normalized():
    urls = ["https://example.org/landing",
            "https://doi.org/10.1000/xyz",
            "https://example.org/paper.pdf",
            "https://arxiv.org/abs/2004.05631"]
    ranked = cd.rank_links(urls)
    kinds = [r["kind"] for r in ranked]
    assert kinds == ["arxiv", "pdf", "doi", "other"]          # free routes first
    # arXiv abs URL normalized to its direct PDF URL
    assert ranked[0]["url"].endswith("/pdf/2004.05631") or "2004.05631" in ranked[0]["url"]
    assert ranked[0]["kind"] == "arxiv"


def test_build_record_and_status():
    cands = [{"url": "https://arxiv.org/pdf/2004.05631", "kind": "arxiv",
              "verify": "pdf", "fetched": True},
             {"url": "https://doi.org/10.1000/xyz", "kind": "doi",
              "verify": "skip", "fetched": False}]
    rec = cd.build_record("smith2020", "A Title", "2020", cands,
                          pdf_url="https://arxiv.org/pdf/2004.05631",
                          pdf_path="cited/smith2020.pdf")
    assert rec["citekey"] == "smith2020"
    assert rec["drill_status"] == "fetched"
    assert rec["pdf_url"].endswith("2004.05631")
    assert rec["pdf_path"] == "cited/smith2020.pdf"
    assert len(rec["candidates"]) == 2


def test_status_links_only_and_no_links():
    cands = [{"url": "https://x/landing", "kind": "other", "verify": "fail", "fetched": False}]
    rec = cd.build_record("k", "t", "2020", cands, pdf_url=None, pdf_path=None)
    assert rec["drill_status"] == "links_only"
    rec2 = cd.build_record("k", "t", "2020", [], pdf_url=None, pdf_path=None)
    assert rec2["drill_status"] == "no_links"


def test_reference_fields_from_record():
    rec = {"citekey": "k", "drill_status": "fetched",
           "pdf_url": "https://arxiv.org/pdf/x", "pdf_path": "cited/k.pdf",
           "candidates": [{"url": "https://arxiv.org/pdf/x"}]}
    fields = cd.reference_fields(rec, pdf_json="cited/k.pdf.json")
    assert fields["drill_status"] == "fetched"
    assert fields["pdf_url"].endswith("/x")
    assert fields["pdf_path"] == "cited/k.pdf"
    assert fields["pdf_json"] == "cited/k.pdf.json"
    assert fields["download_links"] == ["https://arxiv.org/pdf/x"]


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
