"""
Unit tests for the geometry-fusion substrate (pdfdrill.geometry).
No subprocess: parse_tsv is fed canned `pdftotext -tsv` text; fuse runs on a
synthetic Document whose mathpix_lines carry regions.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document
from pdfdrill.geometry import parse_tsv, group_lines, fuse, clear_geometry

_HDR = "level\tpage_num\tpar_num\tblock_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
_TSV = "\n".join([
    _HDR,
    "1\t1\t0\t0\t0\t0\t0\t0\t612\t792\t-1\t",          # page box 612x792 pts
    "5\t1\t1\t1\t1\t1\t100\t50\t40\t12\t96\tHello",      # line 1
    "5\t1\t1\t1\t1\t2\t145\t50\t45\t12\t96\tWorld",
    "5\t1\t1\t1\t2\t1\t150\t70\t60\t12\t96\tIndented",   # line 2 (further right)
])


def test_parse_tsv_words_and_page_dims():
    words, dims = parse_tsv(_TSV)
    assert dims == {1: (612.0, 792.0)}
    assert len(words) == 3
    assert words[0]["text"] == "Hello" and words[0]["x0"] == 100.0


def test_group_lines():
    lines = group_lines(parse_tsv(_TSV)[0])
    assert len(lines) == 2
    assert lines[0]["text"] == "Hello World" and lines[0]["x0"] == 100.0
    assert lines[1]["text"] == "Indented" and lines[1]["x0"] == 150.0


def _synthetic_doc():
    doc = Document()
    doc.meta["pages"] = [{"page": 1, "page_height": 792, "page_width": 612}]
    s = doc.ensure_stream("mathpix_lines")
    s.append(text="Hello World", _page=1,
             region={"top_left_x": 100, "top_left_y": 50, "width": 85, "height": 12})
    s.append(text="Indented", _page=1,
             region={"top_left_x": 150, "top_left_y": 70, "width": 60, "height": 12})
    return doc


def test_fuse_matches_and_annotates_indentation():
    doc = _synthetic_doc()
    words, dims = parse_tsv(_TSV)
    stats = fuse(doc, group_lines(words), dims)

    assert stats["pdf_lines"] == 2
    assert stats["matched"] == 2
    assert stats["mean_sim"] > 0.8                     # text matched well

    mp = doc.stream("mathpix_lines")
    g = [mp.payload[a]["_geom"] for a in mp.anchors]
    # second line is further right -> larger indentation
    assert g[1]["indent_norm"] > g[0]["indent_norm"]
    assert g[0]["sim"] > 0.8

    geo_aligns = [a for a in doc.alignments if a.kind == "geometry"]
    assert len(geo_aligns) == 2
    assert geo_aligns[0].left.stream == "mathpix_lines"
    assert geo_aligns[0].right.stream == "pdf_lines"


def test_fuse_round_trips_and_clears():
    doc = _synthetic_doc()
    words, dims = parse_tsv(_TSV)
    fuse(doc, group_lines(words), dims)

    doc2 = Document.from_dict(doc.to_dict())            # survives serialization
    assert "pdf_lines" in doc2.streams
    assert any(a.kind == "geometry" for a in doc2.alignments)
    assert doc2.stream("mathpix_lines").payload[doc2.stream("mathpix_lines").anchors[1]]["_geom"]["indent_norm"] is not None

    clear_geometry(doc2)
    assert "pdf_lines" not in doc2.streams
    assert not any(a.kind == "geometry" for a in doc2.alignments)
    assert "_geom" not in doc2.stream("mathpix_lines").payload[doc2.stream("mathpix_lines").anchors[0]]


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
