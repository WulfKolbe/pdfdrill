"""
Book TOC layer (src/pdfdrill/booktoc.py): a greppable table of contents whose
printed page numbers are aligned to PDF page numbers via the front-matter
offset. The offset is recovered by matching TOC titles to the model's Section
objects (which carry the real PDF page) — robust to any amount of front matter.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import booktoc as bt


def test_parse_entries_drops_fragments_and_splits_number():
    raw = ["A Note to the Reader  ..... 5", "A Note to the Reader", "..... 5",
           "1.1 Formal Concepts  ..... 11", "1.1 Formal Concepts", "..... 11",
           "Bibliography  ..... 133"]
    ents = bt.parse_toc_entries(raw)
    assert len(ents) == 3                                  # fragments dropped
    e = {x["title"]: x for x in ents}
    assert e["Formal Concepts"]["number"] == "1.1"
    assert e["Formal Concepts"]["printed_page"] == 11
    assert e["A Note to the Reader"]["number"] == ""      # unnumbered front matter
    assert e["Bibliography"]["printed_page"] == 133


def test_offset_zero_when_printed_equals_pdf():
    ents = [{"title": "Formal Concepts", "number": "1.1", "printed_page": 11},
            {"title": "Density Operators", "number": "2.3", "printed_page": 37}]
    secs = [{"caption": "1.1 Formal Concepts", "page": 11},
            {"caption": "2.3 Density Operators", "page": 37}]
    off, conf, pairs = bt.compute_offset(ents, secs)
    assert off == 0 and conf == 1.0 and len(pairs) == 2


def test_offset_positive_with_frontmatter():
    # printed page 1 sits on PDF page 13 -> offset +12
    ents = [{"title": "Introduction", "number": "1", "printed_page": 1},
            {"title": "Methods", "number": "2", "printed_page": 20}]
    secs = [{"caption": "1 Introduction", "page": 13},
            {"caption": "2 Methods", "page": 32}]
    off, conf, _ = bt.compute_offset(ents, secs)
    assert off == 12 and conf == 1.0


def test_align_uses_matched_section_page_else_offset():
    ents = [{"title": "Introduction", "number": "1", "printed_page": 1},
            {"title": "Deep Topic", "number": "3", "printed_page": 50}]   # no section
    secs = [{"caption": "1 Introduction", "page": 13}]
    aligned = bt.align_toc(ents, secs)
    a = {x["title"]: x for x in aligned}
    assert a["Introduction"]["pdf_page"] == 13 and a["Introduction"]["exact"] is True
    assert a["Deep Topic"]["pdf_page"] == 62 and a["Deep Topic"]["exact"] is False  # 50+12


def test_render_is_greppable():
    aligned = [{"number": "2.3", "title": "Density Operators", "printed_page": 37,
                "pdf_page": 49, "exact": True}]
    txt = bt.render_toc(aligned, offset=12, bibkey="T")
    # one line an LLM can grep: title present, printed + pdf both shown
    line = [l for l in txt.splitlines() if "Density Operators" in l][0]
    assert "2.3" in line and "Density Operators" in line
    assert "37" in line and "49" in line
    assert "offset" in txt.lower()                         # header explains alignment


def test_render_grep_yields_pdf_page():
    aligned = [{"number": "5.2", "title": "Free Completions", "printed_page": 113,
                "pdf_page": 113, "exact": True}]
    txt = bt.render_toc(aligned, offset=0, bibkey="T")
    hit = [l for l in txt.splitlines() if "Free Completions" in l][0]
    import re
    m = re.search(r"pdf\s*(\d+)", hit)
    assert m and int(m.group(1)) == 113


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
