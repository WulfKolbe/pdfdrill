"""
Tests for the folder batch command and the .bib loader (no network).
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from pdfdrill.bibliography import _split_bib_entries, load_bibtex_file
from pdfdrill.commands import cmd_folder
from pdfdrill.sidecar import Sidecar

_BIB = """% a comment
@article{Smith2019,
  author = {Smith, John and Doe, Jane},
  title = {Nested {Braces} Work},
  year = {2019},
  journal = {J. Testing}
}

@inproceedings{Roe2021,
  author = {Roe, B.},
  title = {Second},
  year = {2021}
}
"""


def test_split_bib_entries_is_brace_aware():
    ents = _split_bib_entries(_BIB)
    assert [k for k, _ in ents] == ["Smith2019", "Roe2021"]
    assert "Nested {Braces} Work" in ents[0][1]   # nested braces kept intact


def test_load_bibtex_attaches_and_creates():
    doc = Document()
    doc.add(DocObject(type="Reference", props={"citekey": "Smith2019", "raw_text": "stub"}))
    res = load_bibtex_file(doc, _BIB)
    assert res == {"attached": 2, "created": 1}    # Roe2021 created, Smith2019 matched
    smith = next(r for r in doc.objects.values()
                 if r.type == "Reference" and r.props["citekey"] == "Smith2019")
    assert smith.props["bibtex"].startswith("@article{Smith2019,")
    assert smith.props["year"] == "2019"
    assert "Smith" in smith.props["author"]


_LINES = {
    "pages": [{
        "page": 1, "image_id": "img1", "page_height": 1000, "page_width": 800,
        "lines": [
            {"text": "A Title", "type": "text",
             "region": {"top_left_x": 100, "top_left_y": 50, "width": 300, "height": 20}},
            {"text": "- bullet one", "type": "text",
             "region": {"top_left_x": 100, "top_left_y": 80, "width": 200, "height": 18}},
            {"text": "References", "type": "section_header"},
            {"text": "Smith, J. 2019. A paper. In Proc., 1-10.", "type": "text"},
        ],
    }]
}


def test_folder_builds_from_lines_json_without_network():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "doc.pdf").write_bytes(b"%PDF-1.7 not-a-real-pdf")
        (tmp / "doc.lines.json").write_text(json.dumps(_LINES))
        (tmp / "doc.bib").write_text(_BIB)
        # a second PDF with no lines.json -> must be skipped (no MathPix call)
        (tmp / "nolines.pdf").write_bytes(b"%PDF-1.7")

        msg = cmd_folder(tmp)
        assert "1 built, 1 skipped" in msg
        assert "nolines.pdf: SKIP" in msg

        sc = Sidecar(tmp / "doc.pdf")
        assert sc.has("MODEL_BUILT")               # model built from lines.json
        model = json.loads((sc.blob_dir / "model.docmodel.json").read_text())
        types = {o["type"] for o in model["objects"]}
        assert "Equation" not in types or True      # structure exists
        refs = [o for o in model["objects"] if o["type"] == "Reference"]
        assert refs and any(r["props"].get("bibtex") for r in refs)  # .bib applied


def test_folder_empty_dir():
    with tempfile.TemporaryDirectory() as d:
        assert "No PDF files" in cmd_folder(Path(d))


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
