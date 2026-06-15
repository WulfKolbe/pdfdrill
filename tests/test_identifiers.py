"""
Front-matter identifier scan (src/pdfdrill/identifiers.py): the frontmatter
window (driven by the booktoc page offset), an ALL-CAPS named-entity pass, and
collecting prose text from the early pages — pure helpers; the command wires
them over DocGraph + the features extractors.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import identifiers as idn


def test_frontmatter_limit():
    assert idn.frontmatter_limit(12) == 12          # real front-matter boundary
    assert idn.frontmatter_limit(0) == idn.DEFAULT_FRONT   # no offset -> default
    assert idn.frontmatter_limit(2) == idn.DEFAULT_FRONT   # tiny -> default floor
    assert idn.frontmatter_limit(99, cap=20) == 20         # capped


def test_caps_entities_multiword():
    out = idn.caps_entities("Published by OXFORD UNIVERSITY PRESS in 2020 by JANE DOE.")
    assert "OXFORD UNIVERSITY PRESS" in out
    assert "JANE DOE" in out


def test_caps_entities_excludes_romans_and_idlabels():
    out = idn.caps_entities("See Chapter II and III. ISBN and DOI and ISSN here.")
    assert out == []                                 # romans + id labels excluded


def test_caps_entities_dedup_and_single_word_threshold():
    out = idn.caps_entities("NASA NASA and a lone OK but BUREAU OF STANDARDS")
    assert out.count("NASA") <= 1                    # deduped
    assert "BUREAU OF STANDARDS" in out
    assert "OK" not in out                           # too short / single short token


def test_collect_frontmatter_text_respects_limit():
    class N:
        def __init__(self, t, page, text): self.type, self.props = t, {"page": page, "text": text}
    nodes = [N("Paragraph", 1, "On the copyright page."),
             N("Paragraph", 3, "Still front matter."),
             N("Paragraph", 40, "Deep in the body.")]
    txt = idn.collect_frontmatter_text(nodes, limit=5)
    assert "copyright page" in txt and "front matter" in txt
    assert "Deep in the body" not in txt


def test_split_author_names():
    # the common title-page byline form: First-Last names, comma/and separated
    out = idn.split_author_names("QINTONG ZHANG, BIN WANG and HAO LIANG")
    assert out == ["Qintong Zhang", "Bin Wang", "Hao Liang"]   # title-cased, split
    out2 = idn.split_author_names("Jane Doe; John Roe & Max Mustermann")
    assert out2 == ["Jane Doe", "John Roe", "Max Mustermann"]
    # comma is the author separator, so a lone initial chunk is dropped
    assert "J." not in idn.split_author_names("Bin Wang, J.")
    # a role label is not a name
    assert idn.split_author_names("EDITED BY") == []


def test_resolve_authors_against_reference():
    cands = ["Qintong Zhang", "Bin Wang", "Hao Liang", "Random Person"]
    ref = ["Qintong Zhang", "Bin Wang", "Victor Shea-Jay Huang", "Hao Liang"]
    res = idn.resolve_authors(cands, ref)
    conf = {r["canonical"] for r in res["resolved"]}
    assert "Qintong Zhang" in conf and "Hao Liang" in conf
    assert "Random Person" in res["unresolved"]
    assert res["confirmed"] >= 3                              # 3 of the ref list found


def test_resolve_authors_tolerates_ocr_typo():
    res = idn.resolve_authors(["Qintong Zhng", "Bin Wnag"],   # OCR typos
                              ["Qintong Zhang", "Bin Wang"])
    assert res["confirmed"] == 2                              # both still resolved
    assert all(r["score"] >= 0.8 for r in res["resolved"])


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
