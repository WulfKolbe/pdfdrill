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


def test_heading_plus_prose_splits_into_section_and_prose_only_paragraph():
    """A heading merged with prose: the heading becomes a SECTION and the paragraph
    keeps ONLY the prose (so the inspect box stops at the frame, and an LLM doesn't
    read the heading as body)."""
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "\\section*{ALL RIGHTS RESERVED} \n\nA dissertation submitted.",
        "flow_index": 1}))
    hc.clean_heading_residuals(doc)
    p = doc.objects["p1"].props
    assert p["text"] == "A dissertation submitted."         # prose ONLY, title gone
    assert "\\section" not in p["text"] and "ALL RIGHTS RESERVED" not in p["text"]
    # a Section was promoted for the heading
    secs = [o for o in doc.objects.values() if o.type == "Section"]
    assert any((s.props.get("caption") or "").strip() == "ALL RIGHTS RESERVED"
               and s.props["kind"] == "section" for s in secs)


def test_heading_only_paragraph_becomes_a_section():
    """A paragraph that is JUST a heading (the appendix case 'A. Dataset Split
    Details') becomes a Section and the empty paragraph is dropped."""
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "\\section*{A. Dataset Split Details}", "flow_index": 5,
        "page": 16}))
    hc.clean_heading_residuals(doc)
    assert "p1" not in doc.objects                          # heading-only para dropped
    secs = [o for o in doc.objects.values() if o.type == "Section"]
    s = next(s for s in secs if "Dataset Split Details" in (s.props.get("caption") or ""))
    assert s.props["refnum"] == "A" and s.props["is_appendix"] is True   # appendix letter
    assert s.props["page"] == 16


def test_numbered_subsection_promotes_with_refnum():
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "\\subsection{2.3 Cellular Sheaves}\n\nWe define a sheaf.",
        "flow_index": 1}))
    hc.clean_heading_residuals(doc)
    assert doc.objects["p1"].props["text"] == "We define a sheaf."   # prose only
    s = next(o for o in doc.objects.values() if o.type == "Section")
    assert s.props["kind"] == "subsection" and s.props["refnum"] == "2.3"


def test_no_duplicate_section_when_one_exists():
    """If a Section already exists for the heading, strip the paragraph but do NOT
    promote a duplicate (the tcolorbox case: Section + heading-in-paragraph)."""
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Section", id="s1", props={
        "caption": "Topic Track Writing Prompt", "kind": "section", "flow_index": 4}))
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "\\section*{Topic Track Writing Prompt}\n\nYou are a writer.",
        "flow_index": 5}))
    hc.clean_heading_residuals(doc)
    assert doc.objects["p1"].props["text"] == "You are a writer."
    secs = [o for o in doc.objects.values() if o.type == "Section"
            and (o.props.get("caption") or "") == "Topic Track Writing Prompt"]
    assert len(secs) == 1                                   # no duplicate


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
    # MathPix sometimes wraps the command: "{\section*{Annotation}."
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "{\\section*{Annotation}.\n\nThe paper studies X.", "flow_index": 1}))
    assert hc.clean_heading_residuals(doc) == 1
    assert doc.objects["p1"].props["text"] == "The paper studies X."   # prose only
    assert any(o.type == "Section" and o.props.get("caption") == "Annotation"
               for o in doc.objects.values())


def test_heading_only_paragraph():
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "\\section*{Acknowledgments}", "flow_index": 1}))
    hc.clean_heading_residuals(doc)
    assert "p1" not in doc.objects                     # heading-only → dropped
    assert any(o.type == "Section" and o.props.get("caption") == "Acknowledgments"
               for o in doc.objects.values())


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
