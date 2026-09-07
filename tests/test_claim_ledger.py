"""634 — the claim ledger: every module records the anchors it consumed.

The pipeline is ADDITIVE, so nothing in it can say that a region was claimed
by nobody or that a line was claimed twice. Both are already true on the real
documents and both are invisible. This is the measurement, not the fix: the
ledger adds no object, removes none, and changes no prop.

THE BLOCK/INLINE RULE, which every test here rests on:
  a claim is a `surface` Realization on `mathpix_lines`;
  it is a BLOCK claim when it carries no sub-anchor offset/length — the object
  consumed the whole line;
  it is an INLINE claim when it does — a Formula living inside a line is
  NESTING, not a second consumption;
  it is a CONTAINER claim when the object's type is in `CONTAINER_TYPES`
  (`Page`), whose range spans its page by construction. Containers are
  recorded and reported, never counted: 646 measured that counting them makes
  every anchor doubly claimed and the measure says nothing.
The user's two counts — claimed 0 times, claimed more than once — are about
BLOCK claims alone.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel import ledger as L
from docmodel.base_module import ModuleConfig
from docmodel.core import Document, DocObject, Realization
from docmodel.modules.footnote import FootnoteProcessor
from docmodel.modules.page import ingest_lines_json, PageProcessor
from docmodel.modules.paragraph import ParagraphProcessor
from docops.conserve import anchor_claims
from pdfdrill.model_io import load_model, save_model


# ---------------------------------------------------------------- fixtures

@pytest.fixture(autouse=True)
def _no_inherited_recorder():
    """The recorder is PROCESS-GLOBAL by design — `pdfdrill.cli` switches it on
    for the whole command and `docmodel.main.run` for the whole build, because
    the claims of a build have to outlive the loop that made them. In a test
    session that means one test can inherit another's recorder, which is how
    this fixture came to exist: run alone the ledger read `unattributed`, run
    after the CLI tests it read `test_claim_ledger`. Each test starts from a
    known state and leaves one."""
    L.reset()
    yield
    L.reset()


def _module(cls):
    return cls(ModuleConfig(classname=cls.__name__), bibkey="T", flags={})


def _lines_doc(lines):
    doc = Document()
    doc.meta["bibkey"] = "T"
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "i",
                                       "lines": lines}]})
    return doc


def _fixture():
    """Three lines. l0 claimed by a Section, l1 by a Paragraph AND a Footnote
    (the doubly-claimed class), l2 by nobody (the TOC-region class)."""
    doc = Document()
    doc.meta["bibkey"] = "T"
    mp = doc.ensure_stream("mathpix_lines")
    l0 = mp.append(text="1 Introduction", _page=1, _line_index=0,
                   type="section_header")
    l1 = mp.append(text="Body text.3 A footnote.", _page=1, _line_index=1,
                   type="text")
    l2 = mp.append(text="1 Introduction .... 3", _page=2, _line_index=2,
                   type="toc")

    sec = DocObject(type="Section", props={"caption": "Introduction"})
    sec.add_realization(Realization(stream="mathpix_lines", start=l0, end=l0))
    doc.add(sec)

    par = DocObject(type="Paragraph", props={"text": "Body text."})
    par.add_realization(Realization(stream="mathpix_lines", start=l1, end=l1))
    doc.add(par)

    fn = DocObject(type="Footnote", props={"content": "A footnote.",
                                           "added_by": "footnote_cleanup"})
    fn.add_realization(Realization(stream="mathpix_lines", start=l1, end=l1))
    doc.add(fn)
    return doc, (l0, l1, l2)


def _led(doc):
    return L.materialize(doc)


# ------------------------------------------------- the two counts, and the sum

def test_two_modules_claiming_one_line_make_that_anchor_multi_claimed():
    doc, (l0, l1, l2) = _fixture()
    led = _led(doc)
    assert led["counts"]["claimed_multi"] == 1
    entry = led["multi"][0]
    assert entry["anchor"] == l1.id
    # `added_by` names the pass that made the Footnote; the Paragraph of this
    # hand-built fixture was attached with the recorder off, so it reads
    # `unattributed` rather than being guessed at from its type.
    assert entry["modules"] == ["footnote_cleanup", "unattributed"], entry
    assert entry["types"] == ["Footnote", "Paragraph"]
    assert led["module_pairs"] == {"footnote_cleanup+unattributed": 1}


def test_the_three_counts_sum_to_the_stream_length():
    doc, _ = _fixture()
    led = _led(doc)
    c = led["counts"]
    assert led["total"] == 3
    assert c["claimed_0"] + c["claimed_1"] + c["claimed_multi"] == led["total"]
    assert c["claimed_0"] == 1 and c["claimed_1"] == 1 and c["claimed_multi"] == 1


def test_a_formula_inline_on_that_line_is_an_inline_claim_not_a_block_claim():
    """The rule the user's counts depend on: a Formula INSIDE a line is
    nesting. Adding one must not turn a 1-claim anchor into a 2-claim one."""
    doc, (l0, l1, l2) = _fixture()
    before = _led(doc)["counts"]["claimed_multi"]
    fo = DocObject(type="Formula", props={"latex": "x"})
    fo.add_realization(Realization(stream="mathpix_lines", start=l0, end=l0,
                                   props={"offset": 2, "length": 1}))
    doc.add(fo)
    led = _led(doc)
    assert led["counts"]["claimed_multi"] == before
    assert led["counts"]["inline_claims"] == 1
    assert led["counts"]["claimed_0"] + led["counts"]["claimed_1"] \
        + led["counts"]["claimed_multi"] == led["total"]


def test_a_page_container_is_recorded_but_claims_nothing():
    """646's ruling, adopted here so the two instruments are comparable: a
    Page's realization spans its whole page by construction. Counted, every
    anchor would be doubly claimed and the measure would say nothing."""
    doc, (l0, l1, l2) = _fixture()
    pg = DocObject(type="Page", props={"page": 1})
    pg.add_realization(Realization(stream="mathpix_lines", start=l0, end=l1))
    doc.add(pg)
    led = _led(doc)
    assert led["counts"]["container_claims"] == 2
    assert led["counts"]["claimed_0"] == 1        # l2 is still claimed by nobody
    assert led["counts"]["claimed_multi"] == 1    # l1 only, not l0
    assert led["containers_excluded"] == ["Page"]


# ------------------------------------------------------------ the 0-claim regions

def test_zero_claim_anchors_are_grouped_by_line_type_and_by_page():
    """The user's 'the TOC region was claimed by nobody' — visible only when
    the 0-claim anchors are grouped by the MathPix line type."""
    doc, _ = _fixture()
    led = _led(doc)
    assert led["zero_by_line_type"] == {"toc": 1}
    assert led["zero_by_page"] == {"2": 1}
    assert led["zero"][0]["line_type"] == "toc"


# --------------------------------------------------- the recorder names the module

def test_the_recorder_names_the_module_that_attached_the_realization():
    """The reason the ledger is recorded at build time rather than derived: on
    the real documents 1271 of 1448 objects carry NO `added_by`, so the
    document alone cannot say which module consumed a line. The claim is
    recorded at the one place every realization is attached
    (`DocObject.add_realization`)."""
    doc = _lines_doc([
        {"id": "h", "type": "text", "text": "Body text of a paragraph."},
        {"id": "fn", "type": "footnote",
         "text": r"\footnotetext{\({ }^{3}\) a footnote body.}"},
    ])
    L.reset()
    with L.recording():
        _module(PageProcessor).process_document(doc)
        _module(ParagraphProcessor).process_document(doc)
        _module(FootnoteProcessor).process_document(doc)
    led = _led(doc)
    assert "paragraph" in led["by_module"], led["by_module"]
    assert "footnote" in led["by_module"], led["by_module"]
    assert led["by_module_container"].get("page"), led["by_module_container"]
    L.reset()


def test_the_recorder_is_process_global_and_survives_the_loop_that_set_it():
    """`docmodel.main.run` switches recording on and never off: `cmd_model`
    runs `heading_cleanup` AFTER the build returns and saves the result, so a
    recording scoped to the module loop would be discarded before anything
    could store it."""
    L.reset()
    with L.recording():
        doc, _ = _fixture()
    # left the block; the store still holds what was recorded inside it
    assert L.recorded()
    led = _led(doc)
    assert "test_claim_ledger" in led["by_module"], led["by_module"]
    assert led["recorded"] is True


def test_nothing_is_recorded_while_the_recorder_is_off():
    """Off by default: the hook costs a bool test and records nothing, so a
    process that loads a thousand models does not accumulate a ledger."""
    L.reset()
    doc, _ = _fixture()
    assert L.recorded() == {}
    assert _led(doc)["recorded"] is False


# ------------------------------------------------------------------ round trip

def _roundtrip(doc, tmp_path):
    p = Path(tmp_path) / "model.docmodel.json"
    save_model(p, doc)
    return load_model(p), p


def test_the_ledger_survives_the_round_trip(tmp_path):
    """rule 7 / test_model_write_roundtrip's convention: assert on what
    survives the real writer and reader, not on the object in memory."""
    doc = _lines_doc([
        {"id": "h", "type": "text", "text": "Body text of a paragraph."},
    ])
    L.reset()
    with L.recording():
        _module(PageProcessor).process_document(doc)
        _module(ParagraphProcessor).process_document(doc)
    back, _ = _roundtrip(doc, tmp_path)
    L.reset()                       # the reader must not need the recorder
    stored = back.meta.get("ledger")
    assert stored is not None
    assert stored["counts"]["claimed_0"] == _led(doc)["counts"]["claimed_0"]
    # and the ATTRIBUTION survives, so a later command's save still names the
    # module that made the claim in the FIRST process.
    assert "paragraph" in _led(back)["by_module"], _led(back)["by_module"]


def test_the_ledger_is_json_safe_and_carries_no_live_objects(tmp_path):
    doc, _ = _fixture()
    back, p = _roundtrip(doc, tmp_path)
    import json
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(raw["meta"]["ledger"]["counts"]["claimed_0"], int)


# ------------------------------------------------------- the conserve cross-check

def test_the_ledger_and_conserve_agree_on_the_zero_and_multi_counts():
    """646 derives claims from the realizations after the fact; 634 records
    them at build time. Two instruments, one surface — they must agree, or the
    difference is a finding about one of them."""
    doc, (l0, l1, l2) = _fixture()
    fo = DocObject(type="Formula", props={"latex": "x"})
    fo.add_realization(Realization(stream="mathpix_lines", start=l0, end=l0,
                                   props={"offset": 2, "length": 1}))
    doc.add(fo)
    pg = DocObject(type="Page", props={"page": 1})
    pg.add_realization(Realization(stream="mathpix_lines", start=l0, end=l1))
    doc.add(pg)

    led = L.materialize(doc)
    cons = anchor_claims(doc)
    assert led["counts"]["claimed_0"] == len(cons["unclaimed"])
    assert led["counts"]["claimed_multi"] == len(cons["doubly_claimed"])
    assert led["counts"]["inline_claims"] == cons["inline_skipped"]
    assert [e["anchor"] for e in led["zero"]] == \
        [e["anchor"] for e in cons["unclaimed"]]
    assert [e["anchor"] for e in led["multi"]] == \
        [e["anchor"] for e in cons["doubly_claimed"]]


# ------------------------------------------------------------- no behaviour change

def test_the_ledger_adds_no_object_and_changes_no_prop():
    doc = _lines_doc([
        {"id": "h", "type": "text", "text": "Body text of a paragraph."},
        {"id": "fn", "type": "footnote",
         "text": r"\footnotetext{\({ }^{3}\) a footnote body.}"},
    ])
    L.reset()
    _module(PageProcessor).process_document(doc)
    _module(ParagraphProcessor).process_document(doc)
    _module(FootnoteProcessor).process_document(doc)
    off = sorted((o.type, tuple(sorted(o.props))) for o in doc.objects.values())

    doc2 = _lines_doc([
        {"id": "h", "type": "text", "text": "Body text of a paragraph."},
        {"id": "fn", "type": "footnote",
         "text": r"\footnotetext{\({ }^{3}\) a footnote body.}"},
    ])
    with L.recording():
        _module(PageProcessor).process_document(doc2)
        _module(ParagraphProcessor).process_document(doc2)
        _module(FootnoteProcessor).process_document(doc2)
    on = sorted((o.type, tuple(sorted(o.props))) for o in doc2.objects.values())
    L.reset()
    assert off == on
    assert len(doc.objects) == len(doc2.objects)


# ------------------------------------------------------------------ the report

def test_the_report_names_the_counts_the_sum_and_the_module_pairs():
    doc, _ = _fixture()
    text = L.format_ledger(_led(doc))
    assert "claimed 0 times" in text
    assert "claimed more than once" in text
    assert "0 + 1 + >1" in text
    assert "BLOCK CLAIMS BY MODULE" in text
    assert "toc" in text                     # the 0-claim region, by line type


def test_the_report_says_the_block_inline_rule_out_loud():
    doc, _ = _fixture()
    text = L.format_ledger(_led(doc))
    assert "inline" in text.lower() and "block" in text.lower()


def test_a_mismatched_sum_is_printed_as_a_mismatch_not_hidden():
    """rule 11: a checker that can only print OK has not been tested."""
    doc, _ = _fixture()
    led = _led(doc)
    led["counts"]["claimed_1"] += 1              # corrupt it on purpose
    assert "MISMATCH" in L.format_ledger(led)


# ------------------------------------- FIX ROUND 1: --ledger is READ-ONLY

def test_ledger_refuses_a_missing_model_and_names_the_command(tmp_path):
    """The defect: `--ledger` rebuilt "only if stale", so running it on a PDF
    with no model chained cmd_model -> cmd_mathpix and BOUGHT an 8-page
    extraction. A command that reports on what exists must not be able to
    create it."""
    from pdfdrill.commands import model_ledger
    pdf = tmp_path / "nothing.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    out = model_ledger(pdf)
    assert out.startswith("REFUSED")
    assert "has no model" in out
    assert f"pdfdrill model {pdf}" in out
    assert "SPEND MONEY" in out
    # NOTHING THAT COSTS OR PERSISTS A MODEL was written. The document's
    # sidecar may appear — every command opens one, `size` and `status`
    # included — so the assertion names the artefacts that matter instead of
    # claiming a directory stayed empty, which would pass here only because
    # this stub is not a real PDF the probe can read.
    made = {p.name for p in tmp_path.rglob("*")}
    for costly in ("model.docmodel.json", "model.docpack.json",
                   "nothing.lines.json", "nothing.tex.zip", "nothing.md"):
        assert costly not in made, costly


def test_no_path_from_the_ledger_flag_to_a_build_or_a_purchase():
    """Pinned as source, because the failure was a CALL CHAIN and no fixture
    reproduces a MathPix purchase. `model_ledger` must not reach `cmd_model`,
    `cmd_mathpix` or `save_model`, and `cli._do_model` must route `--ledger`
    before it calls `cmd_model` at all."""
    import inspect
    from pdfdrill import cli
    from pdfdrill.commands import model_ledger
    body = inspect.getsource(model_ledger)
    for forbidden in ("cmd_model(", "cmd_mathpix(", "save_model("):
        assert forbidden not in body, forbidden
    src = inspect.getsource(cli._do_model)
    assert src.index("model_ledger(") < src.index("return cmd_model("), src


def test_the_ledger_flag_is_a_read_only_form_for_the_preflight_gate():
    """A read must not be gated by the attestation that exists to stop spends
    — and the bare `model` build must stay gated."""
    from pdfdrill import preflight
    assert preflight.is_read_only_form("model", ["x.pdf", "--ledger"])
    assert not preflight.is_read_only_form("model", ["x.pdf"])
    assert not preflight.is_gated("model", ["x.pdf", "--ledger"])
    assert preflight.is_gated("model", ["x.pdf"])
    assert preflight.is_gated("mathpix", ["x.pdf", "--ledger"])


def test_a_rebuild_forgets_the_previous_documents_claims():
    """The recorder is process-global; a batch building many documents would
    otherwise carry one document's attribution and a sticky overflow into the
    next one's ledger."""
    import inspect
    from pdfdrill.commands import cmd_model
    src = inspect.getsource(cmd_model)
    assert "_ledger_mod.reset()" in src
    assert src.index("_ledger_mod.reset()") < src.index("out = build_model(")
