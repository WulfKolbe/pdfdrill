"""
Heading-residual cleanup (src/pdfdrill/heading_cleanup.py): MathPix returns a
LaTeX sectioning command (\\section*{...}) inside a Paragraph's text, merged
with the following prose. The raw command disturbs semantic analysis. The
cleaner strips the command to its title alone and records kind/refnum on the
object — the title text survives (the \\n\\n split keeps it separate from the
body), the LaTeX command is gone.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from pdfdrill import heading_cleanup as hc


def test_strip_unnumbered_section_residual():
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "\\section*{ALL RIGHTS RESERVED} \n\nA dissertation submitted.",
        "flow_index": 1}))
    n = hc.clean_heading_residuals(doc)
    assert n == 1
    p = doc.objects["p1"].props
    assert p["text"].startswith("ALL RIGHTS RESERVED")
    assert "\\section" not in p["text"]
    assert "A dissertation submitted." in p["text"]        # body preserved
    assert p["kind"] == "section" and p["refnum"] == ""
    assert p["heading_residual_cleaned"] is True


def test_numbered_subsection_sets_refnum():
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "\\subsection{2.3 Cellular Sheaves}\n\nWe define a sheaf.",
        "flow_index": 1}))
    hc.clean_heading_residuals(doc)
    p = doc.objects["p1"].props
    assert p["kind"] == "subsection"
    assert p["refnum"] == "2.3"
    assert p["text"].startswith("Cellular Sheaves")        # number lifted out
    assert "2.3" not in p["text"].split("\n")[0]


def test_non_heading_paragraph_untouched():
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "We use \\section references throughout, e.g. \\(x^2\\).",
        "flow_index": 1}))
    n = hc.clean_heading_residuals(doc)
    assert n == 0                                          # not a LEADING command
    assert "heading_residual_cleaned" not in doc.objects["p1"].props


def test_idempotent():
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "\\chapter*{One}\n\nbody", "flow_index": 1}))
    assert hc.clean_heading_residuals(doc) == 1
    assert hc.clean_heading_residuals(doc) == 0            # no command left


def test_leading_brace_wrapped_residual():
    # MathPix sometimes wraps the command: "{\section*{CONCLUSION}."
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "{\\section*{Annotation}.\n\nThe paper studies X.", "flow_index": 1}))
    assert hc.clean_heading_residuals(doc) == 1
    p = doc.objects["p1"].props
    assert p["text"].startswith("Annotation")
    assert "\\section" not in p["text"]
    assert p["kind"] == "section"


def test_heading_only_paragraph():
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "\\section*{Acknowledgments}", "flow_index": 1}))
    hc.clean_heading_residuals(doc)
    assert doc.objects["p1"].props["text"] == "Acknowledgments"
    assert doc.objects["p1"].props["kind"] == "section"


def test_extract_standalone_footnotetext_paragraph():
    from docmodel.core import Document, DocObject
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "\\footnotetext{\n\\({ }^{1}\\) And almost every page is laced "
                "with side notes.\n}", "page": 3, "flow_index": 1}))
    n = hc.extract_footnote_paragraphs(doc)
    assert n == 1
    fns = doc.objects_of_type("Footnote")
    assert len(fns) == 1
    f = fns[0].props
    assert f["refnum"] == "1"
    assert f["anchor_marker"] == "{ }^{1}"
    assert "side notes" in f["content"] and "\\footnotetext" not in f["content"]
    assert "{ }^{1}" not in f["content"]                 # anchor stripped
    # the standalone footnotetext paragraph is consumed
    assert "p1" not in doc.objects or doc.objects["p1"].type == "Footnote"


def test_extract_footnote_embedded_in_prose_keeps_prose():
    from docmodel.core import Document, DocObject
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "Real prose here. \\footnotetext{\\({ }^{2}\\) the note}", "flow_index": 1}))
    hc.extract_footnote_paragraphs(doc)
    assert "Real prose here." in doc.objects["p1"].props["text"]
    assert "\\footnotetext" not in doc.objects["p1"].props["text"]
    assert any(o.props.get("refnum") == "2" for o in doc.objects_of_type("Footnote"))


def test_extract_footnote_idempotent():
    from docmodel.core import Document, DocObject
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "\\footnotetext{\\({ }^{1}\\) x}", "flow_index": 1}))
    assert hc.extract_footnote_paragraphs(doc) == 1
    assert hc.extract_footnote_paragraphs(doc) == 0


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
