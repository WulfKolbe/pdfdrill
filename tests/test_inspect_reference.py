"""A resolved bibliography entry is an element of the inspect page.

`collect_elements` skipped Document, Reference and Citation together, as
objects without a place on a page. That is true of Document and it is not true
of a Reference: `add_reference_objects` gives each one a `surface` realization
spanning its printed lines, so geometry is derivable. Measured on WDorg4, the
21 entries resolve to real boxes:

    #1 page=169 bbox={'x': 143, 'y': 525, 'w': 1200, 'h': 72}

The whole enriched record — 21 references, all with BibTeX — was in the model,
the tiddlers and `status`, and invisible in the inspector.

Citation stays excluded for now (148 more boxes on this book, deliberately not
turned on yet).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import docinspect


def _model(objs, lines):
    return {"streams": {"mathpix_lines": {
                "name": "mathpix_lines",
                "anchors": [a for a, _ in lines],
                "payload": {a: p for a, p in lines}}},
            "objects": objs,
            "meta": {"bibkey": "T",
                     "pages": [{"page": 1, "page_width": 1000, "page_height": 1400}]}}


def _collect(model):
    els, _pages = docinspect.collect_elements(
        model, docinspect.build_stream_index(model))
    return els


_LINES = [("a1", {"type": "text", "text": "[1] B. HEIM: Elementarstrukturen.",
                  "_page": 1, "region": {"top_left_x": 10, "top_left_y": 20,
                                         "width": 500, "height": 30}})]


def _ref(**props):
    base = {"citekey": "heim1989", "number": 1, "year": "1989",
            "author": "B. HEIM", "raw_text": "[1] B. HEIM: Elementarstrukturen.",
            "entry_type": "book"}
    base.update(props)
    return {"id": "r1", "type": "Reference", "props": base,
            "realizations": [{"stream": "mathpix_lines", "start": "a1",
                              "end": "a1", "role": "surface"}]}


def test_a_reference_is_an_element_with_a_box_on_its_page():
    els = _collect(_model([_ref()], _LINES))
    refs = [e for e in els if e["type"] == "Reference"]
    assert len(refs) == 1
    assert refs[0]["page"] == 1
    assert refs[0]["bbox"] and refs[0]["bbox"]["w"] > 0


def test_the_bibtex_travels_to_the_client():
    bib = "@book{heim1989,\n  title = {Elementarstrukturen der Materie}\n}"
    els = _collect(_model([_ref(bibtex=bib)], _LINES))
    ref = next(e for e in els if e["type"] == "Reference")
    assert ref["props"]["bibtex"] == bib
    assert ref["props"]["citekey"] == "heim1989"


def test_a_document_object_is_still_not_an_element():
    """It genuinely has no place on a page."""
    doc = {"id": "d", "type": "Document", "props": {}, "realizations": []}
    els = _collect(_model([doc, _ref()], _LINES))
    assert [e["type"] for e in els] == ["Reference"]


def test_a_citation_is_still_excluded():
    """Not yet: 148 more boxes on a 174-page book is a separate decision."""
    cit = {"id": "c", "type": "Citation", "props": {"text": "[1]"},
           "realizations": [{"stream": "mathpix_lines", "start": "a1",
                             "end": "a1", "role": "surface"}]}
    els = _collect(_model([cit, _ref()], _LINES))
    assert [e["type"] for e in els] == ["Reference"]


def test_a_reference_is_inspectable_not_blob_layer():
    from pdfdrill.ink_view import is_structure
    assert is_structure("Reference", {}) is True


def test_the_inspector_pane_shows_the_bibtex_record():
    """Runs the SHIPPED page: builds a document with one enriched reference,
    clicks it, and reads what lands in the inspector pane. A string match on
    the source would only confirm my own spelling."""
    import shutil
    import pytest as _pytest

    if shutil.which("node") is None:
        _pytest.skip("node not installed")
    from test_docinspect_page_run import _boot

    bib = "@book{heim1989,\n  title = {Elementarstrukturen der Materie}\n}"
    model = _model([_ref(bibtex=bib, bibfetched=True)], _LINES)
    model["alignments"] = []
    out = _boot(model, body="""
      const ref = EL.find(e => e.type === 'Reference');
      OUT.found = !!ref;
      select(ref.id);
      const pane = document.getElementById('inspBody');
      OUT.pane = pane.allText();
      /* the FORMATTED block, not the generic scalar-props dump: without a
       * type renderer the record still appears, squashed onto one key/value
       * line, so reading the pane text alone cannot tell the two apart. */
      OUT.blocks = pane.querySelectorAll('.latexsrc').map(n => n.allText());
      OUT.tree = document.getElementById('tree').allText();
    """)
    assert out["found"], "the Reference never reached the client"
    assert any("@book{heim1989" in b for b in out["blocks"]), \
        "the BibTeX is not in a formatted block"
    assert "Elementarstrukturen der Materie" in out["pane"]
    assert out["pane"].count("@book{heim1989") == 1, "the record is shown twice"
    assert "heim1989" in out["pane"]                 # the citekey
    assert "B. HEIM" in out["tree"]                  # and it is a tree row


def test_an_unenriched_reference_says_so_instead_of_showing_an_empty_pane():
    import shutil
    import pytest as _pytest

    if shutil.which("node") is None:
        _pytest.skip("node not installed")
    from test_docinspect_page_run import _boot

    model = _model([_ref()], _LINES)                 # no bibtex
    model["alignments"] = []
    out = _boot(model, body="""
      select(EL.find(e => e.type === 'Reference').id);
      OUT.pane = document.getElementById('inspBody').allText();
    """)
    assert "bibfetch" in out["pane"]
