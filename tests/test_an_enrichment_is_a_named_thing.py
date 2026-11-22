r"""An enrichment is a named thing, not a suffix — and the model it replaces is kept.

T-0156. `_prefer_arxiv_source` decides whether to rebuild a model from the
author's LaTeX. It refused whenever ANY object prop had a key ENDING IN
`_source` with a non-empty value, as the mark of a translation a rebuild
cannot reproduce.

OF THE 26 SUCH PROP NAMES IN THE CODEBASE, EXACTLY ONE is an enrichment —
`edit_source` — and `model_enrichments` already counts it. The other 25 are
PROVENANCE: `ref_source` ("bib", "citation", "text" — where an entry came
from), `text_source`, `scan_source`, `caption_source` and the rest, every one
reproducible by a rebuild.

Measured over the eight audit e-prints BEFORE the change: SIX were refused
with nothing to protect — 0 real enrichments each, refused solely because
their References carry a provenance label (11 to 101 of them). Only
1503.00301 holds real enrichments (72), and its refusal is right.

AND THE TRANSLATION IT MEANT TO PROTECT HAS A REAL TEST, which is why this is
not a deletion. `docops.language.is_translated` asks `twins()`: only the named
PROSE_FIELDS, and only where the `_source` twin IS A SECOND LANGUAGE.
`heading_cleanup.is_translated` states the rule and the reason — "
Materialization writes an identical twin, so mere presence is not enough."

THE REBUILD OVERWRITES A MODEL THE OWNER OWNS, and `model_io.save_model` keeps
no previous copy: its writes are atomic, so a killed process never truncates
the file, but a completed one replaces it. The rollback is kept beside it,
named with the build that wrote it.
"""
import json

import pytest

from docmodel import DocObject, Document
from docops import language


def test_a_real_second_language_twin_is_a_translation():
    doc = Document()
    doc.add(DocObject(type="Paragraph",
                      props={"text": "Hallo Welt", "text_source": "Hello world"}))
    assert language.is_translated(doc)


def test_a_provenance_label_is_not_a_translation():
    """`ref_source` is where an entry came from, not a second language."""
    doc = Document()
    doc.add(DocObject(type="Reference", props={"ref_source": "bib"}))
    assert not language.is_translated(doc)


def test_an_identical_twin_is_not_a_translation():
    """Materialization writes an identical twin; mere presence is not enough."""
    doc = Document()
    doc.add(DocObject(type="Paragraph",
                      props={"text": "Hello", "text_source": "Hello"}))
    assert not language.is_translated(doc)


@pytest.mark.parametrize("prop", ["ref_source", "text_source", "scan_source",
                                  "caption_source", "model_source",
                                  "refnum_origin"])
def test_no_provenance_prop_alone_refuses_the_rebuild(prop):
    doc = Document()
    doc.add(DocObject(type="Paragraph", props={prop: "something"}))
    assert not language.is_translated(doc)


def test_edit_source_is_in_the_explicit_list():
    """The one `*_source` prop that IS an enrichment is already named."""
    from pdfdrill.commands import ENRICHMENT_MARKERS
    assert "edit_source" in ENRICHMENT_MARKERS


# ------------------------------------------------------- the kept rollback

def test_the_previous_model_is_kept_before_a_rebuild(tmp_path):
    from pdfdrill.commands import _keep_model_rollback

    p = tmp_path / "model.docmodel.json"
    p.write_text(json.dumps({"meta": {"build": {"sha": "7b372f06cf625e"}},
                             "objects": []}), encoding="utf-8")
    kept = _keep_model_rollback(p)
    assert kept is not None and kept.exists()
    assert "7b372f06cf62" in kept.name, kept.name
    assert kept.name.endswith(".bak.json")
    assert json.loads(kept.read_text(encoding="utf-8"))["meta"]["build"]["sha"] \
        == "7b372f06cf625e"


def test_one_rollback_per_build_not_per_run(tmp_path):
    from pdfdrill.commands import _keep_model_rollback

    p = tmp_path / "model.docmodel.json"
    p.write_text(json.dumps({"meta": {"build": {"sha": "abc123"}}}),
                 encoding="utf-8")
    first = _keep_model_rollback(p)
    p.write_text(json.dumps({"meta": {"build": {"sha": "abc123"}},
                             "changed": True}), encoding="utf-8")
    assert _keep_model_rollback(p) == first
    # the FIRST model is what is kept, not the later one
    assert "changed" not in json.loads(first.read_text(encoding="utf-8"))


def test_a_model_with_no_build_stamp_is_still_kept(tmp_path):
    from pdfdrill.commands import _keep_model_rollback

    p = tmp_path / "model.docmodel.json"
    p.write_text("{}", encoding="utf-8")
    kept = _keep_model_rollback(p)
    assert kept is not None and kept.exists()


def test_nothing_to_keep_is_not_an_error(tmp_path):
    from pdfdrill.commands import _keep_model_rollback
    assert _keep_model_rollback(tmp_path / "absent.json") is None
