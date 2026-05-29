"""
Unit tests for promoting link annotations to first-class Link DocObjects.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject, Realization
from pdfdrill.annotations import add_link_objects, link_xref_alignments


_RECORDS = [
    {"page": 1, "kind": "url",
     "uri": "https://anonymous.4open.science/r/X/",
     "dest_name": "", "dest_page": None,
     "rect": [493.0, 698.0, 520.0, 710.0],
     "anchor_text": "", "context": "...code [] ..."},
    {"page": 8, "kind": "url", "uri": "https://github.com/foo/bar",
     "rect": [100.0, 200.0, 180.0, 212.0], "anchor_text": "here",
     "context": "see [here]"},
    {"page": 2, "kind": "internal", "uri": "", "dest_name": "theorem.1.1",
     "dest_page": 5, "rect": [50.0, 60.0, 90.0, 72.0], "anchor_text": "Thm 1.1"},
    {"page": 3, "kind": "url", "uri": ""},  # empty url -> skipped
]


def test_add_link_objects_creates_nodes_with_region():
    doc = Document()
    created = add_link_objects(doc, _RECORDS)
    assert len(created) == 3                    # empty-url record skipped
    links = [o for o in doc.objects.values() if o.type == "Link"]
    assert len(links) == 3

    code = next(o for o in links if "4open.science" in o.props["uri"])
    assert code.props["page"] == 1
    assert code.props["anchor_text"] == ""      # the invisible code link
    r = code.realizations[0]
    assert r.stream == "links" and r.role == "annotation"
    assert r.region is not None
    assert r.region.space == "pdf_points"
    assert r.region.width == 27.0 and r.region.height == 12.0

    internal = next(o for o in links if o.props["kind"] == "internal")
    assert internal.props["dest_name"] == "theorem.1.1"
    assert internal.props["dest_page"] == 5


def test_links_round_trip():
    doc = Document()
    add_link_objects(doc, _RECORDS)
    doc2 = Document.from_dict(doc.to_dict())
    links = [o for o in doc2.objects.values() if o.type == "Link"]
    assert len(links) == 3
    r = links[0].realizations[0]
    assert r.provenance == "pdfplumber"
    assert r.region is not None and r.region.space == "pdf_points"


def test_xref_alignments_cite_and_page():
    doc = Document()
    mp = doc.ensure_stream("mathpix_lines")
    # a Citation object for foo2023 and a Page 5 object, both with surface ranges
    ca = mp.append(text="[foo2023]", _page=13)
    cit = DocObject(type="Citation", props={"citekey": "foo2023"})
    cit.add_realization(Realization(stream="mathpix_lines", start=ca, end=ca, role="surface"))
    doc.add(cit)
    pa = mp.append(text="page 5 line", _page=5)
    pg = DocObject(type="Page", props={"page_number": 5})
    pg.add_realization(Realization(stream="mathpix_lines", start=pa, end=pa, role="surface"))
    doc.add(pg)

    recs = [
        {"page": 1, "kind": "internal", "uri": "", "dest_name": "cite.foo2023",
         "dest_page": 13, "rect": [1, 2, 3, 4]},
        {"page": 1, "kind": "internal", "uri": "", "dest_name": "theorem.1.1",
         "dest_page": 5, "rect": [1, 2, 3, 4]},
    ]
    created = add_link_objects(doc, recs)
    counts = link_xref_alignments(doc, created)
    assert counts["cites"] == 1                 # cite.foo2023 -> Citation
    assert counts["xrefs"] == 1                 # theorem.1.1 -> Page 5
    kinds = {a.kind for a in doc.alignments}
    assert "cites" in kinds and "xref" in kinds


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__)
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__)
            print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} failed out of {len(tests)}")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
