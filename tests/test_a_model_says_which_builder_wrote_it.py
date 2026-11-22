r"""A model says which builder wrote it.

T-0156. `meta["source"]` cannot answer that question, and the attempt to read
it as an answer is what this fixes. It names where the READING came from
("mathpix", or whatever the lines.json declares), and `_prefer_arxiv_source`
overloads it as a rebuild-guard that it sets ONLY WHEN EMPTY. So:

  * a model whose structure was merged from the author's LaTeX still reads
    "mathpix" — measured on 2102.08145, whose error count fell 30 to 3 from
    exactly that merge while the field stayed put;
  * and a field set only when empty can never be corrected by a rebuild.

`meta["build"]` already records the COMMIT that decided the object graph,
with the rule in its own comment: "Written once, here, and never overwritten
by a later save: an enrichment pass changes props, not the structure whose
counts a corpus measurement sums." `written_by` adds the builder's NAME under
the same rule — set by every builder, preserved by an edit.

AN EDIT PRESERVES IT AND A BUILDER OVERWRITES IT. 49 of the 50 `save_model`
sites are edits — marking appendix sections, filling a bibliography,
retracting a layer — so clearing the field at each would leave it unknown
almost immediately. A builder sets it unconditionally, which is precisely
what `meta["source"]` could not do.
"""
import json

import pytest

from docmodel import DocObject, Document
from pdfdrill.model_io import load_model, save_model


def _doc():
    d = Document()
    d.add(DocObject(type="Paragraph", props={"text": "a paragraph"}))
    return d


def _meta(path):
    return json.loads(path.read_text(encoding="utf-8"))["meta"]


def test_a_builder_names_itself(tmp_path):
    p = tmp_path / "m.docmodel.json"
    save_model(p, _doc(), writer="lines-json", packed=False)
    assert _meta(p).get("written_by") == "lines-json"


def test_an_edit_preserves_the_builder(tmp_path):
    p = tmp_path / "m.docmodel.json"
    save_model(p, _doc(), writer="lines-json", packed=False)
    save_model(p, load_model(p), packed=False)          # an undeclared edit
    assert _meta(p).get("written_by") == "lines-json"


def test_a_later_builder_overwrites_it(tmp_path):
    """The half `meta["source"]` could not do: it is set only when EMPTY."""
    p = tmp_path / "m.docmodel.json"
    save_model(p, _doc(), writer="lines-json", packed=False)
    save_model(p, load_model(p), writer="latex-source-merge", packed=False)
    assert _meta(p).get("written_by") == "latex-source-merge"


def test_the_commit_is_recorded_beside_the_name(tmp_path):
    p = tmp_path / "m.docmodel.json"
    save_model(p, _doc(), writer="lines-json", packed=False)
    m = _meta(p)
    assert m.get("written_by") == "lines-json"
    assert (m.get("written") or {}).get("sha") or \
        (m.get("written") or {}).get("version"), m.get("written")


@pytest.mark.parametrize("name", ["lines-json", "latex-source",
                                  "latex-source-merge"])
def test_every_builder_name_round_trips(tmp_path, name):
    p = tmp_path / ("%s.docmodel.json" % name.replace("-", "_"))
    save_model(p, _doc(), writer=name, packed=False)
    assert load_model(p).meta.get("written_by") == name


def test_the_three_builders_declare_themselves():
    """The sites that BUILD a model, as opposed to editing one."""
    import inspect

    from pdfdrill import commands
    src = inspect.getsource(commands)
    assert 'writer="latex-source"' in src          # the arXiv source builder
    assert 'writer="latex-source-merge"' in src    # the structure merge

    from docmodel import main as docmain
    assert '"written_by"' in inspect.getsource(docmain)   # the reading builder


def test_source_and_written_by_answer_different_questions(tmp_path):
    """`source` is the READING's origin; `written_by` is the builder's."""
    p = tmp_path / "m.docmodel.json"
    d = _doc()
    d.meta["source"] = "mathpix"
    save_model(p, d, writer="latex-source-merge", packed=False)
    m = _meta(p)
    assert m["source"] == "mathpix"
    assert m["written_by"] == "latex-source-merge"
