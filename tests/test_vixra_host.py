r"""viXra as a known host — 806.

805 found fourteen library folders holding viXra e-prints. They worked, because
the generic http lane downloads any URL, but they arrived unlabelled: nothing in
the sidecar said which archive, so `status` and `route` could not say either.

viXra is NOT arXiv with a different name, and the three differences are the
whole content of this file:

  1. ITS IDS COLLIDE. `YYMM.NNNN` is viXra's shape for every year and arXiv's
     shape up to 1412. A bare id names both archives and neither, so viXra is
     recognised from a URL or an explicit `viXra:` token only. Guessing would
     swap one archive's paper for another's, which is exactly the failure 804
     exists to prevent.
  2. ITS PDF URL NEEDS THE VERSION. Measured against vixra.org:
     `/pdf/1702.0234.pdf` -> 404, `/pdf/1702.0234v1.pdf` -> 200. arXiv serves
     the unversioned form; viXra does not.
  3. IT HAS NO LATEX SOURCE. viXra hosts the PDF its author uploaded and has no
     e-print endpoint. A route that assumes symmetry fetches a 404 and reports
     "no source found", which reads like a missing file rather than an archive
     that never had one.

The abs-page fixture is a real page, captured once, so the parser is tested
offline.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import sources as S

FIXTURE = Path(__file__).with_name("data-vixra-abs-1702.0234.html")


@pytest.fixture
def abs_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


# ---------------------------------------------------------------- the host
class TestTheHost:
    @pytest.mark.parametrize("url", [
        "https://vixra.org/abs/1702.0234",
        "https://vixra.org/pdf/1702.0234v1.pdf",
        "http://www.vixra.org/abs/2505.0100",
    ])
    def test_a_vixra_url_is_a_known_host(self, url):
        assert S.known_host(url) == "vixra"

    def test_arxiv_is_still_arxiv(self):
        assert S.known_host("https://arxiv.org/abs/2609.24972") == "arxiv"
        assert S.known_host("https://export.arxiv.org/abs/2609.24972") == "arxiv"

    def test_an_unrelated_host_is_still_unknown(self):
        assert S.known_host("https://example.com/paper.pdf") is None


# ------------------------------------------------------------------- the id
class TestTheId:
    @pytest.mark.parametrize("text,want", [
        ("https://vixra.org/abs/1702.0234", "1702.0234"),
        ("https://vixra.org/pdf/1702.0234v1.pdf", "1702.0234v1"),
        ("viXra:1702.0234", "1702.0234"),
        ("vixra:2505.0100v1", "2505.0100v1"),
    ])
    def test_a_url_or_an_explicit_token_resolves(self, text, want):
        assert S.parse_vixra_id(text) == want

    @pytest.mark.parametrize("bare", ["1702.0234", "2505.0100v1", "1412.1234"])
    def test_a_BARE_id_is_never_read_as_vixra(self, bare):
        """`2505.0100` is a well-formed viXra id AND a well-formed pre-2015
        arXiv id. Nothing in the string says which, and guessing swaps one
        archive's paper for another's."""
        assert S.parse_vixra_id(bare) is None

    def test_an_arxiv_url_is_not_a_vixra_id(self):
        assert S.parse_vixra_id("https://arxiv.org/abs/1702.02340") is None


# ----------------------------------------------------------------- the URLs
class TestTheUrls:
    def test_the_pdf_url_requires_the_version(self):
        """Measured: /pdf/1702.0234.pdf is 404, /pdf/1702.0234v1.pdf is 200.
        An unversioned id therefore has NO pdf url — offering one would be a
        link we know is dead."""
        assert "pdf" not in S.vixra_urls("1702.0234")
        assert S.vixra_urls("1702.0234v1")["pdf"] == \
            "https://vixra.org/pdf/1702.0234v1.pdf"

    def test_the_abs_url_is_unversioned(self):
        """The abs page lists every version of the record."""
        for aid in ("1702.0234", "1702.0234v1", "1702.0234v3"):
            assert S.vixra_urls(aid)["abs"] == "https://vixra.org/abs/1702.0234"

    def test_there_is_no_eprint_url(self):
        """The difference that matters most: arXiv has one, viXra does not."""
        assert "eprint" not in S.vixra_urls("1702.0234v1")
        assert "eprint" in S.arxiv_urls("2609.24972")


# ------------------------------------------------------------ LaTeX source
class TestTheLatexSource:
    def test_vixra_has_none_and_says_why(self):
        why = S.no_latex_source_reason("vixra")
        assert why and "no e-print endpoint" in why
        assert "visionocr" in why, "a refusal should name the route that works"

    def test_arxiv_has_one(self):
        assert S.no_latex_source_reason("arxiv") is None

    def test_the_registry_is_the_single_statement_of_it(self):
        assert S.ARCHIVES_WITH_LATEX_SOURCE == frozenset({"arxiv"})


# -------------------------------------------------------------- the metadata
class TestTheMetadata:
    def test_the_abs_page_yields_the_record(self, abs_html):
        m = S.parse_vixra_abs_html(abs_html)
        assert m["title"].startswith("On the K-Macga Mother Algebras")
        assert m["authors"] == ["Robert Benjamin Easter"]
        assert m["category"] == "Algebra"
        assert len(m["abstract"]) > 500
        assert m["pdf_url"] == "https://vixra.org/pdf/1702.0234v1.pdf"

    def test_the_pdf_url_comes_from_the_page_for_an_unversioned_id(self, abs_html):
        """This is why an unversioned id costs one metadata request: the abs
        page is the only place the current version is written."""
        assert "v1" in S.parse_vixra_abs_html(abs_html)["pdf_url"]

    def test_an_unrelated_page_yields_empties_not_nonsense(self):
        m = S.parse_vixra_abs_html("<html><body><p>nothing here</p></body></html>")
        assert m["title"] == "" and m["authors"] == [] and m["pdf_url"] == ""


# ----------------------------------------------------------------- bibtex
class TestBibtex:
    def test_the_year_comes_from_the_id(self):
        from pdfdrill.commands import _vixra_year
        assert _vixra_year("1702.0234") == "2017"
        assert _vixra_year("2505.0100v1") == "2025"
        assert _vixra_year("0909.0001") == "2009"      # viXra started in 2009
        assert _vixra_year("") == ""

    def test_a_recorded_vixra_id_produces_a_vixra_misc_entry(self, tmp_path, monkeypatch):
        """`archivePrefix = viXra`, so a bibliography says which archive and a
        reader chasing the eprint lands on the right one."""
        from pdfdrill import commands as C, sources as SS
        from pdfdrill.sidecar import Sidecar

        pdf = tmp_path / "1702.0234v1.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%stub\n")
        sc = Sidecar(pdf)
        sc.set_evidence("source_vixra_id", "1702.0234")
        sc.set_evidence("vixra_title", "On the K-Macga Mother Algebras")
        sc.set_evidence("vixra_authors", ["Robert Benjamin Easter"])
        sc.set_evidence("vixra_category", "Algebra")
        sc.save()

        monkeypatch.setattr(SS, "fetch_vixra_metadata",
                            lambda *_a, **_k: (_ for _ in ()).throw(
                                AssertionError("must not hit the network")))
        bib = {"entry_type": "misc", "citekey": "unknown2023"}
        C._augment_bibtex(bib, pdf, Sidecar(pdf))
        assert bib["archive_prefix"] == "viXra"
        assert bib["eprint"] == "1702.0234"
        assert bib["year"] == "2017"
        assert bib["url"] == "https://vixra.org/abs/1702.0234"
        assert bib["author"] == "Robert Benjamin Easter"

    def test_a_vixra_stem_is_never_read_as_an_arxiv_id(self, tmp_path, monkeypatch):
        """`1702.0234` off a filename is ambiguous — and it used to resolve.

        This test found the defect it now guards: `_augment_bibtex` falls back
        to `parse_arxiv_id(pdf.stem)`, which had no shape gate, so a viXra
        e-print named `1702.0234.pdf` was fetched from arXiv as the zero-padded
        `1702.00234` and cited as "Preliminary Design Study of the Hollow
        Electron Lens for LHC" — a real paper, the wrong archive, and a
        bibliography that is simply wrong.
        """
        from pdfdrill import commands as C, sources as SS
        from pdfdrill.sidecar import Sidecar

        monkeypatch.setattr(SS, "fetch_arxiv_metadata",
                            lambda *_a, **_k: (_ for _ in ()).throw(
                                AssertionError("a malformed id must not be fetched")))
        pdf = tmp_path / "1702.0234.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%stub\n")
        bib = {"entry_type": "misc", "citekey": "unknown2023"}
        C._augment_bibtex(bib, pdf, Sidecar(pdf))
        assert bib.get("archive_prefix") != "arXiv"


# ----------------------------------------------------------------- download
class TestResolveInput:
    def test_a_versioned_url_downloads_without_a_metadata_request(self, tmp_path, monkeypatch):
        calls = {"meta": 0, "dl": []}
        monkeypatch.setattr(S, "fetch_vixra_metadata",
                            lambda *_a, **_k: calls.__setitem__("meta", calls["meta"] + 1) or {})
        def fake_dl(url, dest):
            calls["dl"].append(url)
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_bytes(b"%PDF-1.4\n")
            return Path(dest)
        monkeypatch.setattr(S, "download", fake_dl)
        info = S.resolve_input("https://vixra.org/pdf/1702.0234v1.pdf", tmp_path)
        assert info["source"] == "vixra" and info["vixra_id"] == "1702.0234v1"
        assert info["path"] == (tmp_path / "vixra.1702.0234v1"
                        / "vixra.1702.0234v1.pdf")
        assert calls["meta"] == 0, "a versioned id needs no abs-page request"
        assert calls["dl"] == ["https://vixra.org/pdf/1702.0234v1.pdf"]

    def test_an_unversioned_url_asks_the_abs_page_for_the_version(self, tmp_path, monkeypatch):
        monkeypatch.setattr(S, "fetch_vixra_metadata", lambda *_a, **_k: {
            "pdf_url": "https://vixra.org/pdf/1702.0234v1.pdf"})
        seen = []
        def fake_dl(url, dest):
            seen.append(url)
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_bytes(b"%PDF-1.4\n")
            return Path(dest)
        monkeypatch.setattr(S, "download", fake_dl)
        info = S.resolve_input("https://vixra.org/abs/1702.0234", tmp_path)
        assert seen == ["https://vixra.org/pdf/1702.0234v1.pdf"]
        assert info["vixra_id"] == "1702.0234"

    def test_a_vixra_url_with_no_id_refuses_rather_than_guessing(self, tmp_path):
        with pytest.raises(ValueError, match="carries no id"):
            S.resolve_input("https://vixra.org/abs/not-an-id", tmp_path)


# ----------------------------------------------------------------- citations
class TestCitations:
    def test_a_cited_vixra_url_resolves_to_its_pdf(self):
        """A citation carrying a viXra abs link must reach a fetchable PDF, the
        way `citedrill` turns a cited arXiv id into `arxiv_urls(...)['pdf']`."""
        vid = S.parse_vixra_id("see viXra:1702.0234 for the construction")
        assert vid is None, "prose is not a citation target"
        vid = S.parse_vixra_id("https://vixra.org/abs/1702.0234")
        assert S.vixra_urls(vid + "v1")["pdf"].endswith("1702.0234v1.pdf")
