"""
bibtex for an arXiv source (test finding): it emitted @article with
publisher=pdfTeX-1.40.25 (the PDF PRODUCER — wrong) and omitted the arXiv
eprint/archivePrefix/primaryClass. Fix: never put the producer in `publisher`,
and emit the canonical @misc arXiv form.
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import pdfinfo_layers as P


def test_producer_is_not_publisher():
    bib = P.derive_bibtex({"producer": "pdfTeX-1.40.25", "title": "T",
                           "author": "A", "pages": 10})
    assert bib.get("publisher", "") != "pdfTeX-1.40.25"
    assert "pdfTeX" not in P.bibtex_to_string(bib)


def test_bibtex_string_emits_arxiv_misc_form():
    bib = {"entry_type": "misc", "citekey": "huh2024", "title": "Deep Nets",
           "author": "M. Huh", "year": "2024", "eprint": "2405.07987",
           "archive_prefix": "arXiv", "primary_class": "cs.LG",
           "publisher": "", "pages": 0}
    s = P.bibtex_to_string(bib)
    norm = " ".join(s.split())                # spacing-insensitive
    assert s.startswith("@misc{huh2024,")
    assert "eprint" in s and "{2405.07987}" in s
    assert "archivePrefix = {arXiv}" in norm
    assert "primaryClass = {cs.LG}" in norm
    assert "publisher" not in s               # no bogus producer/publisher
    assert "arxiv_id" not in s                # not the non-standard raw field


def test_augment_sets_arxiv_misc_form_offline():
    from pdfdrill import commands as C
    ev = {"source_arxiv_id": "2405.07987", "arxiv_title": "Deep Nets",
          "arxiv_authors": ["M. Huh", "A. Ng"],
          "arxiv_primary_category": "cs.LG"}
    class SC:
        def get_evidence(self, k, d=None): return ev.get(k, d)
        def set_evidence(self, *a): pass
    bib = {"entry_type": "misc", "citekey": "x", "title": "", "author": "",
           "year": "", "publisher": "pdfTeX-1.40.25", "pages": 5}
    C._augment_bibtex(bib, Path("2405.07987.pdf"), SC())
    assert bib["entry_type"] == "misc"
    assert bib["eprint"] == "2405.07987"
    assert bib["archive_prefix"] == "arXiv"
    assert bib["primary_class"] == "cs.LG"
    assert bib.get("publisher", "") == ""     # producer cleared
    assert bib["author"] == "M. Huh and A. Ng"


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try: t(); print(f"PASS {name}")
        except AssertionError as e: failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e: failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed: print(f"\n{len(failed)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} passed.")
