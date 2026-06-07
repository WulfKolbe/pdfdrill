"""
Tests for the docops package.

Covers:
  - Document.from_dict round-trip
  - Dehyphenate mutator with the 'one-to-one' compound case
  - PlainText/LLMCompact/TiddlyWiki projectors produce non-empty output
  - Loader rejects mis-typed operators
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import (
    Anchor, Stream, Range, Realization, DocObject, Alignment, Document,
)
from docmodel.modules.page import ingest_lines_json, PageProcessor
from docmodel.modules.paragraph import ParagraphProcessor
from docmodel.modules.header import HeaderProcessor
from docmodel.modules.equation import EquationProcessor
from docmodel.modules.document_flow import DocumentFlowProcessor
from docmodel.modules.document_structure import DocumentStructureProcessor
from docmodel.base_module import ModuleConfig

from docops.base import OperatorConfig
from docops.mutators.dehyphenate import Dehyphenate
from docops.projectors.plaintext import PlainTextProjector
from docops.projectors.llm_compact import LLMCompactProjector
from docops.projectors.tiddlywiki import TiddlyWikiProjector
from docops.loader import load_operators


def _make_module(cls, bibkey="T"):
    cfg = ModuleConfig(title=cls.__name__, classname=cls.__name__)
    return cls(cfg, bibkey)


def _make_op(cls, params=None):
    cfg = OperatorConfig(
        op="mutator" if "mutator" in cls.__module__ else "projector",
        classname=cls.__name__,
        params=params or {},
    )
    return cls(cfg)


def _build_sample_doc(extra_lines=None) -> Document:
    """Build a small Document by running the converter on synthetic lines."""
    doc = Document()
    doc.meta["bibkey"] = "T"
    lines = [
        {"id": "h1c", "type": "text", "text": "Intro",
         "text_display": r"\section*{Intro}"},
        {"id": "h1", "type": "section_header", "children_ids": ["h1c"]},
        {"id": "p1", "type": "text", "text": "Hello world", "text_display": "Hello world"},
        {"id": "eq1", "type": "math", "text": r"\[ a = b \]",
         "text_display": r"\[ a = b \]",
         "region": {"top_left_x": 0, "top_left_y": 0, "width": 1, "height": 1}},
    ]
    if extra_lines:
        lines.extend(extra_lines)
    sample = {"pages": [{"page": 1, "image_id": "i", "lines": lines}]}
    ingest_lines_json(doc, sample)
    for cls in (PageProcessor, HeaderProcessor, EquationProcessor,
                ParagraphProcessor):
        _make_module(cls).process_document(doc)
    _make_module(DocumentFlowProcessor).process_objects(doc)
    _make_module(DocumentStructureProcessor).process_objects(doc)
    return doc


def test_round_trip_via_from_dict():
    doc1 = _build_sample_doc()
    d = doc1.to_dict()
    s = json.dumps(d)               # must serialize cleanly
    doc2 = Document.from_dict(json.loads(s))
    assert len(doc2.streams) == len(doc1.streams)
    assert len(doc2.objects) == len(doc1.objects)
    assert len(doc2.alignments) == len(doc1.alignments)
    # Anchor identity within a stream should be re-established
    for name, s2 in doc2.streams.items():
        for i, anchor in enumerate(s2.anchors):
            assert s2.index_of(anchor) == i


def test_dehyphenate_preserves_one_to_one_compound():
    doc = Document()
    doc.meta["bibkey"] = "T"
    # Two text lines: first ends with 'one-', second starts with 'to-one'
    sample = {"pages": [{"page": 1, "image_id": "i", "lines": [
        {"id": "a", "type": "text", "text": "We define a one-",
         "text_display": "We define a one-"},
        {"id": "b", "type": "text", "text": "to-one correspondence here.",
         "text_display": "to-one correspondence here."},
    ]}]}
    ingest_lines_json(doc, sample)
    _make_module(PageProcessor).process_document(doc)
    _make_module(ParagraphProcessor).process_document(doc)

    para = doc.objects_of_type("Paragraph")[0]
    op = _make_op(Dehyphenate)
    op.apply(doc)
    # The hyphen between 'one' and 'to' MUST be preserved (compound).
    assert para.props["text"] == "We define a one-to-one correspondence here."
    # And the original is kept under text_raw.
    assert "one- to-one" in para.props["text_raw"] or \
           "one-" in para.props["text_raw"]


def test_dehyphenate_joins_soft_break():
    doc = Document()
    doc.meta["bibkey"] = "T"
    # Classic soft hyphen: "in-" + "formation" should join to "information".
    sample = {"pages": [{"page": 1, "image_id": "i", "lines": [
        {"id": "a", "type": "text", "text": "We need more in-",
         "text_display": "We need more in-"},
        {"id": "b", "type": "text", "text": "formation about this.",
         "text_display": "formation about this."},
    ]}]}
    ingest_lines_json(doc, sample)
    _make_module(PageProcessor).process_document(doc)
    _make_module(ParagraphProcessor).process_document(doc)

    para = doc.objects_of_type("Paragraph")[0]
    op = _make_op(Dehyphenate)
    op.apply(doc)
    assert para.props["text"] == "We need more information about this."


def test_plaintext_projector_emits_sections_and_paragraphs():
    doc = _build_sample_doc()
    op = _make_op(PlainTextProjector)
    out = op.project(doc)
    assert "Intro" in out
    assert "Hello world" in out
    assert "[EQ" in out or "EQ" in out


def test_llmcompact_projector_emits_glossary():
    doc = _build_sample_doc(extra_lines=[
        {"id": "f1", "type": "text",
         "text": r"Consider $f(x) = x^2$ as our function.",
         "text_display": r"Consider $f(x) = x^2$ as our function."},
    ])
    op = _make_op(LLMCompactProjector)
    out = op.project(doc)
    assert "## Glossary" in out
    # Equations get E1 placeholders, formulas get F1
    assert "[E1]" in out or "[F1]" in out


def test_llmcompact_emits_yaml_front_matter():
    doc = _build_sample_doc()
    doc.meta["title"] = "EAGer: Entropy-Aware Generation"   # colon → must be quoted
    doc.meta["authors"] = ["Daniel Scalena", "Ahmet Üstün"]
    doc.meta["arxiv_id"] = "2510.11170v2"
    doc.meta["primary_category"] = "cs.LG"
    doc.meta["num_pages"] = 15
    op = _make_op(LLMCompactProjector)
    out = op.project(doc)

    lines = out.splitlines()
    assert lines[0] == "---"                       # front matter opens the document
    close = lines.index("---", 1)                  # and closes before the body
    fm = "\n".join(lines[1:close])
    # valid YAML that round-trips the metadata (the colon in title is quoted)
    import yaml
    meta = yaml.safe_load(fm)
    assert meta["title"] == "EAGer: Entropy-Aware Generation"
    assert "Daniel Scalena" in meta["author"]
    assert meta["arxiv_id"] == "2510.11170v2"
    assert meta["bibkey"] == "T"
    assert meta["pages"] == 15
    assert "cs.LG" in meta["tags"] and "pdfdrill" in meta["tags"]
    assert meta["generator"] == "pdfdrill"
    assert meta["sections"] >= 1 and meta["equations"] >= 1   # status counts
    assert "Intro" in out                          # the body still follows the header


def test_llmcompact_bilayer_emits_both_layers():
    # when prose objects carry a `<field>_source` backup (model translated in
    # place), the projector emits a translation layer + a source layer + a toggle.
    doc = _build_sample_doc()
    para = doc.objects_of_type("Paragraph")[0]
    para.props["text_source"] = para.props["text"]      # original
    para.props["text"] = "Hallo Welt"                   # "translation"
    op = _make_op(LLMCompactProjector,
                  {"bilayer": True, "source_lang": "DE", "target_lang": "EN-US"})
    out = op.project(doc)
    assert '<div class="seg trans" lang="EN-US">' in out
    assert '<div class="seg source" lang="DE">' in out
    assert "Hallo Welt" in out                           # translation layer
    assert "Hello world" in out                          # source layer (the backup)
    assert "show-source" in out and "<button" in out     # CSS/JS toggle present


def test_tiddlywiki_projector_round_trips_json():
    doc = _build_sample_doc()
    op = _make_op(TiddlyWikiProjector)
    out = op.project(doc)
    arr = json.loads(out)
    assert isinstance(arr, list) and arr
    types = {t["tags"].split()[0] for t in arr if t.get("tags")}
    # Should include several known tag categories
    assert {"section", "paragraph"} & types


def test_tiddlywiki_inlines_formulas_as_transclusions():
    """Every inline $...$ formula must be replaced by a {{...||FO}} macro
    in the paragraph tiddler's text, not appear as raw $...$."""
    doc = _build_sample_doc(extra_lines=[
        {"id": "f1", "type": "text",
         "text": r"Consider $E$ as the energy and $f(x) = x^2$ as our function.",
         "text_display": r"Consider $E$ as the energy and $f(x) = x^2$ as our function."},
    ])
    # Run the FormulaProcessor so Formula DocObjects exist
    from docmodel.modules.formula import FormulaProcessor
    _make_module(FormulaProcessor).process_document(doc)

    op = _make_op(TiddlyWikiProjector)
    arr = json.loads(op.project(doc))
    bibkey = doc.meta["bibkey"]

    paras = [t for t in arr if "paragraph" in (t.get("tags", ""))]
    # find the one containing the $E$ phrase context
    target = next(p for p in paras if "Consider " in p["text"])
    # Must not contain raw $...$ delimiters anymore
    assert "$E$" not in target["text"], target["text"]
    assert "$f(x)" not in target["text"], target["text"]
    # Must contain transclusion(s) with the FO template
    assert "||FO}}" in target["text"], target["text"]
    # The transclusion title must use the bibkey_FO pattern
    import re as _re
    matches = _re.findall(r"\{\{(" + bibkey + r"_FO\d{4})\|\|FO\}\}", target["text"])
    assert len(matches) >= 2, f"expected 2 FO transclusions, got {matches}"


def test_footnote_marker_not_extracted_as_formula():
    """MathPix renders a footnote-reference superscript as inline math
    \\({ }^{N}\\). FormulaProcessor must NOT turn it into a Formula (it's a
    reference marker), but real math on the same/other lines must survive."""
    from docmodel.modules.formula import FormulaProcessor
    doc = _build_sample_doc(extra_lines=[
        {"id": "fn1", "type": "text",
         "text": r"a footnote here \({ }^{1}\) and another \(4{ }^{2}\)",
         "text_display": r"a footnote here \({ }^{1}\) and another \(4{ }^{2}\)"},
        {"id": "real", "type": "text",
         "text": r"the area is \(6 \times 8 \mathrm{~m}^{2}\) total",
         "text_display": r"the area is \(6 \times 8 \mathrm{~m}^{2}\) total"},
    ])
    _make_module(FormulaProcessor).process_document(doc)
    formulas = [o.props.get("latex") for o in doc.objects.values() if o.type == "Formula"]
    # the two footnote markers must NOT appear as formulas
    assert not any("{ }^" in (f or "") for f in formulas), formulas
    # the genuine m^2 area formula must be present
    assert any("\\times" in (f or "") for f in formulas), formulas


def test_footnote_marker_becomes_FN_transclusion_not_formula():
    """End-to-end: a body footnote ref \\({ }^{1}\\) + a footnote line must
    yield an ||FN transclusion in the paragraph, a Footnote tiddler, and NO
    formula/FOX tiddler for the marker."""
    from docmodel.modules.page import ingest_lines_json, PageProcessor
    from docmodel.modules.footnote import FootnoteProcessor
    from docmodel.modules.formula import FormulaProcessor
    from docmodel.modules.paragraph import ParagraphProcessor
    lines = {"pages": [{"page": 1, "image_id": "i", "lines": [
        {"id": "p1", "type": "text", "text": r"See the note \({ }^{1}\) here."},
        {"id": "fn", "type": "footnote", "text": r"\({ }^{1}\) The footnote body."},
    ]}]}
    doc = Document(); doc.meta["bibkey"] = "T"
    ingest_lines_json(doc, lines)
    for cls in (PageProcessor, FootnoteProcessor, FormulaProcessor, ParagraphProcessor):
        _make_module(cls).process_document(doc)
    arr = json.loads(_make_op(TiddlyWikiProjector).project(doc))
    assert sum(1 for t in arr if "formula" in t.get("tags", "")) == 0
    assert sum(1 for t in arr if "footnote" in t.get("tags", "")) == 1
    para = next(t for t in arr if "paragraph" in t.get("tags", ""))
    assert "||FN}}" in para["text"]
    assert "{ }^{1}" not in para["text"] and "FOX" not in para["text"]


def test_unmatched_footnote_ref_becomes_superscript_not_raw_latex():
    """A body footnote ref \\({ }^{31}\\) whose footnote MathPix didn't capture
    must NOT leak as raw \\({ }^{N}\\); it renders as <sup>31</sup>. A matched
    ref still becomes ||FN, and real-math { }^{-1} inside a formula survives."""
    from docmodel.modules.page import ingest_lines_json, PageProcessor
    from docmodel.modules.footnote import FootnoteProcessor
    from docmodel.modules.formula import FormulaProcessor
    from docmodel.modules.paragraph import ParagraphProcessor
    lines = {"pages": [{"page": 1, "image_id": "i", "lines": [
        {"id": "p1", "type": "text",
         "text": r"Smolin \({ }^{31}\) and the tensor \(x_{0}{ }^{-1} g_{ik}\) here."},
    ]}]}
    doc = Document(); doc.meta["bibkey"] = "T"
    ingest_lines_json(doc, lines)
    for cls in (PageProcessor, FootnoteProcessor, FormulaProcessor, ParagraphProcessor):
        _make_module(cls).process_document(doc)
    arr = json.loads(_make_op(TiddlyWikiProjector).project(doc))
    para = next(t for t in arr if "paragraph" in t.get("tags", ""))
    assert "<sup>31</sup>" in para["text"]            # unmatched ref -> superscript
    assert "\\({ }^{31}\\)" not in para["text"]       # no leaked empty-base LaTeX
    # the real tensor formula x_0{ }^{-1} g_ik is a Formula, transcluded as ||FO
    assert "||FO}}" in para["text"]
    forms = [o.props.get("latex", "") for o in doc.objects.values() if o.type == "Formula"]
    assert any("{ }^{-1}" in f for f in forms)        # real math kept


def test_tiddlywiki_emits_formula_tiddlers():
    """For every Formula DocObject we expect a corresponding tiddler with
    the same title that the paragraph transclusion targets."""
    doc = _build_sample_doc(extra_lines=[
        {"id": "f1", "type": "text",
         "text": r"With $E = mc^2$ as our reference.",
         "text_display": r"With $E = mc^2$ as our reference."},
    ])
    from docmodel.modules.formula import FormulaProcessor
    _make_module(FormulaProcessor).process_document(doc)

    op = _make_op(TiddlyWikiProjector)
    arr = json.loads(op.project(doc))
    bibkey = doc.meta["bibkey"]

    formula_tiddlers = [t for t in arr if "formula" in (t.get("tags", ""))]
    assert formula_tiddlers, "no formula tiddlers emitted"
    # The formula tiddler must carry the !!latex field
    f = formula_tiddlers[0]
    assert "latex" in f and f["latex"], f
    # The transclusion's target title must match a real tiddler title.
    paras = [t for t in arr if "paragraph" in (t.get("tags", ""))]
    para = next(p for p in paras if "{{" + bibkey + "_FO" in p["text"])
    import re as _re
    ph_title = _re.search(r"\{\{(" + bibkey + r"_FO\d{4})\|\|FO\}\}",
                          para["text"]).group(1)
    titles = {t["title"] for t in arr}
    assert ph_title in titles, f"transclusion target {ph_title} has no tiddler"


def test_tiddlywiki_inlines_citations():
    """Citations of the form [Smith2020] in body text must become
    {{bibkey_Smith2020||CIT}} in the paragraph tiddler."""
    doc = Document()
    doc.meta["bibkey"] = "T"
    sample = {"pages": [{"page": 1, "image_id": "i", "lines": [
        {"id": "p1", "type": "text",
         "text": "As shown in [Smith2020] this works.",
         "text_display": "As shown in [Smith2020] this works."},
    ]}]}
    ingest_lines_json(doc, sample)
    _make_module(PageProcessor).process_document(doc)
    from docmodel.modules.citation import CitationProcessor
    _make_module(CitationProcessor).process_document(doc)
    _make_module(ParagraphProcessor).process_document(doc)

    op = _make_op(TiddlyWikiProjector)
    arr = json.loads(op.project(doc))
    para = next(t for t in arr if "paragraph" in (t.get("tags", "")))
    assert "[Smith2020]" not in para["text"], para["text"]
    assert "{{T_Smith2020||CIT}}" in para["text"], para["text"]
    # A citation placeholder tiddler must exist.
    titles = {t["title"] for t in arr}
    assert "T_Smith2020" in titles


def test_compressed_tiddlers_basic_shape():
    """The compressed projector emits %%%%-delimited records of <title>\\n<body>,
    preserves transclusions in paragraph bodies, and renders formula bodies as
    raw LaTeX wrapped in $ or $$."""
    doc = _build_sample_doc(extra_lines=[
        {"id": "f1", "type": "text",
         "text": r"Energy $E = mc^2$ defines mass-equivalence.",
         "text_display": r"Energy $E = mc^2$ defines mass-equivalence."},
    ])
    from docmodel.modules.formula import FormulaProcessor
    _make_module(FormulaProcessor).process_document(doc)

    from docops.projectors.compressed_tiddlers import CompressedTiddlersProjector
    op = _make_op(CompressedTiddlersProjector)
    out = op.project(doc)

    # Records are separated by %%%% on their own line.
    records = [r for r in out.split("%%%%\n") if r.strip()]
    assert records, "no records emitted"

    # Each record should start with a title line (no whitespace, no |).
    for r in records[:5]:
        first_line = r.split("\n", 1)[0]
        assert first_line.strip() != ""
        assert "|" not in first_line

    # Paragraph body must contain the {{...||FO}} transclusion macro.
    para_record = next(
        r for r in records
        if r.startswith("T_PARA_") and "Energy" in r
    )
    assert "||FO}}" in para_record
    # The raw $E = mc^2$ should NOT survive in the paragraph body.
    assert "$E = mc^2$" not in para_record

    # A formula record exists and its body is `$...$`.
    fo_record = next(r for r in records if r.startswith("T_FO"))
    body = fo_record.split("\n", 1)[1].strip()
    assert body.startswith("$") and body.endswith("$")
    assert "mc^{2}" in body or "mc^2" in body or "E = m" in body

    # Page tiddlers excluded by default.
    assert not any(r.startswith("T_PAGE_") for r in records)


def test_compressed_tiddlers_respects_include_kinds():
    """include_kinds in params should restrict output to those tiddler kinds."""
    doc = _build_sample_doc()
    from docops.projectors.compressed_tiddlers import CompressedTiddlersProjector
    op = _make_op(CompressedTiddlersProjector,
                  params={"include_kinds": ["paragraph"]})
    out = op.project(doc)
    records = [r for r in out.split("%%%%\n") if r.strip()]
    for r in records:
        first_line = r.split("\n", 1)[0]
        # all surviving records should be paragraph tiddlers
        assert first_line.startswith("T_PARA_"), first_line


def test_tiddlywiki_no_raw_inline_math_remains():
    """Cross-line inline math \\(...\\) that wraps from one OCR line to the
    next would be missed by per-line FormulaProcessor offsets. The projector
    must catch the residual and emit synthetic FOX_<hash> tiddlers so that
    NO raw inline math survives in the paragraph tiddler."""
    doc = Document()
    doc.meta["bibkey"] = "T"
    sample = {"pages": [{"page": 1, "image_id": "i", "lines": [
        # \( opens on this line, \) closes on the next
        {"id": "a", "type": "text",
         "text": r"For \(\mathrm{k}=\mathrm{p}",
         "text_display": r"For \(\mathrm{k}=\mathrm{p}"},
        {"id": "b", "type": "text",
         "text": r"\lambda_{(p)}(p, m)\) it holds.",
         "text_display": r"\lambda_{(p)}(p, m)\) it holds."},
    ]}]}
    ingest_lines_json(doc, sample)
    _make_module(PageProcessor).process_document(doc)
    # FormulaProcessor will NOT match this because the open and close are
    # on different lines and it scans per-anchor.
    from docmodel.modules.formula import FormulaProcessor
    _make_module(FormulaProcessor).process_document(doc)
    _make_module(ParagraphProcessor).process_document(doc)

    op = _make_op(TiddlyWikiProjector)
    arr = json.loads(op.project(doc))
    para = next(t for t in arr if "paragraph" in (t.get("tags", "")))
    # No raw \(...\) anywhere in the paragraph tiddler.
    import re as _re
    assert not _re.search(r"\\\([\s\S]+?\\\)", para["text"]), para["text"]
    # A synthetic FOX_<hash> tiddler must exist and be referenced.
    assert "||FO}}" in para["text"]
    fox_titles = [t["title"] for t in arr if t["title"].startswith("T_FOX_")]
    assert fox_titles, "no synthetic FOX tiddler emitted"
    # The synthetic tiddler must carry the joined latex body.
    syn = next(t for t in arr if t["title"] in fox_titles)
    assert r"\mathrm{k}" in syn["latex"] and r"\lambda_" in syn["latex"]


def test_loader_rejects_type_mismatch(tmp_path=None):
    # Declared as projector but the class is a mutator -> should be rejected.
    entries = [
        {"op": "projector", "classname": "Dehyphenate"},
        {"op": "mutator",   "classname": "PlainTextProjector"},
    ]
    ops = load_operators(entries)
    assert ops == []  # nothing valid loaded


def test_end_to_end_with_full_pipeline(tmp_path=None):
    """Loader + Mutator + Projector via the run() function."""
    import tempfile
    from docops.main import save_document, load_document
    doc = _build_sample_doc(extra_lines=[
        {"id": "h2", "type": "text", "text": "needs in-",
         "text_display": "needs in-"},
        {"id": "h3", "type": "text", "text": "formation here.",
         "text_display": "formation here."},
    ])
    with tempfile.TemporaryDirectory() as d:
        in_path = os.path.join(d, "in.docmodel.json")
        save_document(doc, in_path)
        cfg_path = os.path.join(d, "cfg.json")
        with open(cfg_path, "w") as f:
            json.dump([
                {"op": "mutator",   "classname": "Dehyphenate"},
                {"op": "projector", "classname": "PlainTextProjector"},
            ], f)
        # Run the CLI internals
        from docops.main import run
        run(
            in_path=in_path, config_path=cfg_path,
            out_dir=d, base_name="x",
            save_mutated_path=None, debug_names=[],
        )
        with open(os.path.join(d, "x.txt"), "r") as f:
            text = f.read()
        assert "information here" in text  # dehyphenation took effect


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
            import traceback; traceback.print_exc()
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
