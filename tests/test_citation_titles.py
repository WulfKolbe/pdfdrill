"""One citekey must produce ONE tiddler title, wherever it is computed.

Three places derived it independently and disagreed:

  latex_source._transclude_cites  bakes {{<bibkey>_REF_<key>||CIT}} into the
                                  paragraph text at build time, stripping every
                                  non-alphanumeric  -> _REF_knnwithlime
  the projector's Reference title same stripping     -> _REF_knnwithlime
  the projector's PLACEHOLDER     keeps _ and -,
  (for a citekey with no          non-word -> "_"    -> 2209.00445v3_knn_with_lime
   Reference behind it)

The first two agree, so a citation resolves only once a bibliography exists. A
document with citations but no References — which is the normal state before
`bibsource` runs — gets placeholders under a name no marker points at, and every
citation link dangles: 46 of 46 on 2209.00445v3.

The underscore-stripped form is also the worse name: `knnwithlime` for a citekey
the author wrote `knn_with_lime`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.citekeys import citation_title, safe_citekey


def test_underscores_and_hyphens_survive():
    assert safe_citekey("knn_with_lime") == "knn_with_lime"
    assert safe_citekey("smith-2020") == "smith-2020"


def test_unsafe_characters_become_underscores_not_nothing():
    assert safe_citekey("van der Berg:2019") == "van_der_Berg_2019"
    assert safe_citekey("a/b\\c") == "a_b_c"


def test_empty_key_falls_back_to_the_ordinal():
    assert safe_citekey("") == ""
    assert citation_title("K", "", index=7) == "K_REF_7"


def test_one_title_for_one_key():
    assert citation_title("2209.00445v3", "knn_with_lime") == \
        "2209.00445v3_REF_knn_with_lime"


def test_all_three_producers_agree():
    """The regression, stated directly."""
    import re
    from docops.projectors import tiddlywiki as tw
    from pdfdrill import latex_source as ls

    bibkey, key = "2209.00445v3", "knn_with_lime"
    baked = ls._transclude_cites(r"text \cite{knn_with_lime} more", bibkey)
    target = re.search(r"\{\{([^}|]+)\|\|CIT\}\}", baked).group(1)
    assert target == citation_title(bibkey, key), baked
    assert tw.reference_title(bibkey, key, 0) == target
    assert tw.citation_placeholder_title(bibkey, key) == target


def test_no_citation_link_dangles_when_the_bibliography_is_missing():
    """END-TO-END invariant, not a unit agreement check.

    My first tests asserted that the three title producers return equal strings
    for one key. That is weaker than the property that actually matters, and it
    would pass even if a fourth producer appeared. This builds the failing
    document — Citations present, References absent, which is every document
    before `bibsource` runs — projects it, and asserts the projector's own
    integrity report finds nothing dangling.

    Against the pre-fix code this fails with 1 dangling CIT target, which is the
    2209.00445v3 defect (46 of 46) reproduced in the suite.
    """
    import json as _json
    from docmodel.core import Document, DocObject
    from docops.base import OperatorConfig
    from docops.projectors.tiddlywiki import TiddlyWikiProjector, tiddler_integrity

    doc = Document()
    doc.meta["bibkey"] = "K"
    doc.add(DocObject(type="Section", props={"caption": "Related work",
                                             "level": 1, "flow_index": 1}))
    doc.add(DocObject(type="Citation", props={"citekey": "knn_with_lime",
                                              "flow_index": 2}))
    doc.add(DocObject(type="Paragraph", props={
        "text": "As shown in {{K_REF_knn_with_lime||CIT}} this works.",
        "flow_index": 3}))

    proj = TiddlyWikiProjector(OperatorConfig(op="projector", classname="TiddlyWikiProjector"))
    tiddlers = _json.loads(proj.project(doc))
    report = tiddler_integrity(tiddlers)
    assert not report.get("dangling"), report["dangling"]

    titles = {t["title"] for t in tiddlers}
    assert "K_REF_knn_with_lime" in titles, sorted(titles)
    # This document has NO Reference object at all for "knn_with_lime" -- the
    # ONE case (639) where the projector's own placeholder must still fire.
    assert proj.counters.get("citation_placeholders_fired", 0) == 1


def test_stub_reference_becomes_ref_tiddler_with_stub_field():
    """639 -- the model (010) now creates a stub Reference for every cited
    key at first Citation. The projector must emit THAT object as the REF
    tiddler (same title, plus a `stub` field) instead of falling back to
    its own placeholder mechanism -- the placeholder fires only for a
    citekey with NO Reference object behind it at all, which does not
    happen here."""
    import json as _json
    from docmodel.core import Document, DocObject
    from docops.base import OperatorConfig
    from docops.projectors.tiddlywiki import TiddlyWikiProjector, tiddler_integrity

    doc = Document()
    doc.meta["bibkey"] = "K"
    doc.add(DocObject(type="Citation", props={"citekey": "smith2020", "flow_index": 1}))
    doc.add(DocObject(type="Reference", props={
        "citekey": "smith2020", "stub": True, "ref_source": "citation"}))
    doc.add(DocObject(type="Paragraph", props={
        "text": "As shown in {{K_REF_smith2020||CIT}} this works.",
        "flow_index": 2}))

    proj = TiddlyWikiProjector(OperatorConfig(op="projector", classname="TiddlyWikiProjector"))
    tiddlers = _json.loads(proj.project(doc))
    report = tiddler_integrity(tiddlers)
    assert not report.get("dangling"), report["dangling"]

    ref_tiddlers = [t for t in tiddlers if t.get("title") == "K_REF_smith2020"]
    assert len(ref_tiddlers) == 1, tiddlers
    t = ref_tiddlers[0]
    assert t.get("stub") == "true", t
    tags = t.get("tags") or ""
    assert "reference" in tags and "stub" in tags, t
    # Never tagged `bibentry`/`bibtex` -- those mean a real, TS-consumable
    # entry, and a stub is neither.
    assert "bibentry" not in tags and "bibtex" not in tags, t
    # A stub must be VISIBLY unresolved, not an entry that LOOKS filled
    # (`{{||CIT}} ` with no body reads exactly like a filled reference with
    # blank fields).
    assert "Reference not yet resolved" in t.get("text", ""), t
    assert "smith2020" in t.get("text", ""), t

    # The projector's OWN placeholder must NOT have fired -- a Reference
    # object (a stub, but a Reference) already exists for this key.
    assert proj.counters.get("citation_placeholders_fired", 0) == 0
    assert not any("Citation placeholder for" in (x.get("text") or "") for x in tiddlers)


def test_filled_reference_still_projects_as_before_stub_unaffected():
    """639 -- the stub-honesty fix (tags `reference stub`, a visible
    unresolved body) must be SCOPED to stubs; a filled Reference keeps its
    pre-639 shape (`reference bibentry bibtex`, raw_text as the body, no
    `stub` field) exactly as `test_bibliography.py` and the TiddlyWiki
    consumer (updateBibentries.ts) already expect."""
    import json as _json
    from docmodel.core import Document, DocObject
    from docops.base import OperatorConfig
    from docops.projectors.tiddlywiki import TiddlyWikiProjector

    doc = Document()
    doc.meta["bibkey"] = "K"
    doc.add(DocObject(type="Reference", props={
        "citekey": "smith2020", "author": "Smith, J.", "year": "2020",
        "raw_text": "Smith, J. (2020). A Study."}))

    proj = TiddlyWikiProjector(OperatorConfig(op="projector", classname="TiddlyWikiProjector"))
    tiddlers = _json.loads(proj.project(doc))
    t = next(x for x in tiddlers if x.get("title") == "K_REF_smith2020")
    assert "stub" not in t, t
    tags = t.get("tags") or ""
    assert "bibentry" in tags and "bibtex" in tags, t
    assert t.get("text") == "{{||CIT}} Smith, J. (2020). A Study.", t


def test_cmd_tiddlers_reports_placeholder_fires():
    """639 -- the projector's own placeholder mechanism should fire for NONE
    of a document's cited keys once the model stubs every one (010); when it
    still does (a citekey with no Reference object at all), `pdfdrill
    tiddlers`'s own report must say so rather than silently degrading."""
    import tempfile
    from pathlib import Path as _Path
    from pdfdrill import commands as K, model_io
    from pdfdrill.sidecar import Sidecar
    from docmodel.core import Document, DocObject

    doc = Document()
    doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Citation", props={"citekey": "orphan2020", "flow_index": 1}))
    doc.add(DocObject(type="Paragraph", props={
        "text": "As shown in {{T_REF_orphan2020||CIT}} this works.", "flow_index": 2}))

    with tempfile.TemporaryDirectory() as d:
        d = _Path(d)
        pdf = d / "t.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        sc = Sidecar(pdf)
        model_io.save_model(K._model_path(sc), doc)
        sc.add_fact(K.MODEL_BUILT)
        sc.add_fact(K.BIBLIOGRAPHY_BUILT)   # skip the auto-bibliography chain
        sc.save()

        out = K.cmd_tiddlers(pdf)
        assert "1 citation placeholder(s) fired" in out, out

    # Contrast: a document whose citekey DOES have a (stub) Reference must
    # report ZERO fires -- no note at all in the message.
    doc2 = Document()
    doc2.meta["bibkey"] = "T"
    doc2.add(DocObject(type="Citation", props={"citekey": "resolved2020", "flow_index": 1}))
    doc2.add(DocObject(type="Reference", props={
        "citekey": "resolved2020", "stub": True, "ref_source": "citation"}))
    doc2.add(DocObject(type="Paragraph", props={
        "text": "As shown in {{T_REF_resolved2020||CIT}} this works.", "flow_index": 2}))

    with tempfile.TemporaryDirectory() as d:
        d = _Path(d)
        pdf = d / "t.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        sc = Sidecar(pdf)
        model_io.save_model(K._model_path(sc), doc2)
        sc.add_fact(K.MODEL_BUILT)
        sc.add_fact(K.BIBLIOGRAPHY_BUILT)
        sc.save()

        out2 = K.cmd_tiddlers(pdf)
        assert "citation placeholder" not in out2, out2
