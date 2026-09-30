"""Tests for the pdfdrill docmodel projection.

The shape is four sections and the separation is the point: an object never
holds text, it holds ANCHOR RANGES into a stream. That is what lets two
sources describe the same object without either being rewritten.
"""
import docmodel_six as D
import docpack
from texmap import project


def _page(page_no=1, texts=("hello world", "second line")):
    page = D.PageNode(page=page_no, rect=(0, 0, 612, 792))
    lines = []
    for i, t in enumerate(texts):
        gl = []
        x = 50.0
        y = 700.0 - i * 12.0
        for c in t:
            gl.append(D.GlyphNode(
                id=f"g{page_no}-{i}-{x}", page=page_no,
                rect=(x, y, x + 5.0, y + 10.0), text=c, cid=0,
                glyphname=None, fontname="ABC+Helv", family="text",
                size=10.0, tex=project("text", None),
                matrix=(10.0, 0, 0, 10.0, x, y)))
            x += 5.0
        lines.append(D.LineNode(id=f"p{page_no}l{i}", page=page_no,
                                rect=(50.0, y, x, y + 10.0),
                                type="text", glyphs=gl))
    page.lines = lines
    return page


class TestShape:
    def test_four_sections(self):
        dm = docpack.to_docmodel([_page()], bibkey="x")
        assert list(dm) == ["meta", "streams", "objects", "alignments"]

    def test_meta_records_the_build(self):
        dm = docpack.to_docmodel([_page()], bibkey="x", source_path="/a/b.pdf")
        assert dm["meta"]["bibkey"] == "x"
        assert dm["meta"]["source_path"] == "/a/b.pdf"
        assert dm["meta"]["build"]["version"] == docpack.VERSION
        assert dm["meta"]["pages"][0]["page"] == 1

    def test_the_stream_carries_anchored_payload(self):
        dm = docpack.to_docmodel([_page()], bibkey="x")
        st = dm["streams"][docpack.STREAM]
        assert st["name"] == docpack.STREAM
        assert len(st["anchors"]) == 2
        assert set(st["anchors"]) == set(st["payload"])

    def test_payload_keeps_the_mathpix_line_shape(self):
        dm = docpack.to_docmodel([_page()], bibkey="x")
        rec = next(iter(dm["streams"][docpack.STREAM]["payload"].values()))
        for key in ("region", "cnt", "text", "font_size", "confidence",
                    "line", "column", "is_printed"):
            assert key in rec, key
        for key in ("_page", "_line_index", "_image_id", "_geom"):
            assert key in rec, key


class TestObjectsPointIntoStreams:
    def test_an_object_holds_no_text(self):
        dm = docpack.to_docmodel([_page()], bibkey="x")
        for obj in dm["objects"]:
            assert "text" not in obj["props"], obj

    def test_realizations_are_anchor_ranges(self):
        dm = docpack.to_docmodel([_page()], bibkey="x")
        anchors = set(dm["streams"][docpack.STREAM]["anchors"])
        for obj in dm["objects"]:
            for r in obj["realizations"]:
                assert r["stream"] == docpack.STREAM
                assert r["start"] in anchors and r["end"] in anchors

    def test_a_page_object_covers_its_lines(self):
        dm = docpack.to_docmodel([_page()], bibkey="x")
        page = next(o for o in dm["objects"] if o["type"] == "Page")
        st = dm["streams"][docpack.STREAM]["anchors"]
        r = page["realizations"][0]
        assert r["start"] == st[0] and r["end"] == st[-1]

    def test_children_and_parents_agree(self):
        dm = docpack.to_docmodel([_page()], bibkey="x")
        by_id = {o["id"]: o for o in dm["objects"]}
        for obj in dm["objects"]:
            if obj["parent"]:
                assert obj["id"] in by_id[obj["parent"]]["children"]

    def test_no_unearned_structure(self):
        """No Section or TableCell objects: nothing in the model identifies
        them, and inventing them would put unsupported structure into a file
        whose purpose is to record what is known."""
        dm = docpack.to_docmodel([_page()], bibkey="x")
        kinds = {o["type"] for o in dm["objects"]}
        assert not (kinds & {"Section", "TableCell", "TableRow"})


class TestStableIds:
    def test_the_same_document_yields_the_same_anchors(self):
        """Content-addressed: a diff between two runs shows what changed,
        not a renumbering."""
        a = docpack.to_docmodel([_page()], bibkey="x")
        b = docpack.to_docmodel([_page()], bibkey="x")
        assert (a["streams"][docpack.STREAM]["anchors"]
                == b["streams"][docpack.STREAM]["anchors"])

    def test_different_content_yields_different_anchors(self):
        a = docpack.to_docmodel([_page(texts=("one", "two"))], bibkey="x")
        b = docpack.to_docmodel([_page(texts=("one", "three"))], bibkey="x")
        assert (a["streams"][docpack.STREAM]["anchors"]
                != b["streams"][docpack.STREAM]["anchors"])

    def test_identical_lines_still_get_distinct_anchors(self):
        dm = docpack.to_docmodel([_page(texts=("same", "same"))], bibkey="x")
        st = dm["streams"][docpack.STREAM]
        assert len(st["anchors"]) == len(set(st["anchors"])) == 2


class TestSerialisable:
    def test_it_round_trips_through_json(self):
        import json
        dm = docpack.to_docmodel([_page(), _page(2)], bibkey="x")
        assert json.loads(json.dumps(dm)) == dm
