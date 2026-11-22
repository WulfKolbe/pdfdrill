r"""A model the author's LaTeX already improved is not rebuilt from scratch.

T-0156. `_prefer_arxiv_source` rebuilds a model from the author's e-print
when the model is not source-built. It asked `meta["source"]` — which
`_prefer_arxiv_source` itself sets to "latex-source" ONLY WHEN THAT FIELD WAS
EMPTY. So a model that `cmd_model`'s merged build had already enriched with
the author's figures and tables still read "mathpix", and was rebuilt here
from scratch, throwing that work away.

MEASURED ON 2102.08145, fresh copies at both commits:

    before the guard   4 \includegraphics, 1 tikzpicture, 5 tabular
                       6 Diagram and 5 Table objects
    after the rebuild  0, 0, 3
                       5 Diagram and 3 Table objects

The three objects lost carried `added_by: "latex"` — the author's own figure
and two tables, added by the merged build. AND THE ERROR COUNT FELL, 30 to 3,
because the content that was failing had gone. An error count cannot be read
without counting content beside it, which is why the audit runner now reports
`\includegraphics`, `tikzpicture`, `tabular` and `equation` per document.

So the question is not what the label says but whether the author's LaTeX has
already been used on this model. If it has, there is nothing to gain and a
merge to lose.
"""
import pytest

from docmodel import DocObject, Document


def _refuses(doc):
    """The guard's condition, as `_prefer_arxiv_source` applies it."""
    return any((o.props or {}).get("added_by") == "latex"
               for o in doc.objects.values())


def test_a_model_carrying_the_authors_figures_is_not_rebuilt():
    doc = Document()
    doc.add(DocObject(type="Diagram",
                      props={"added_by": "latex", "latex_original": "..."}))
    assert _refuses(doc)


@pytest.mark.parametrize("kind", ["Diagram", "Table", "Equation", "Algorithm"])
def test_any_source_added_object_is_enough(kind):
    doc = Document()
    doc.add(DocObject(type=kind, props={"added_by": "latex"}))
    assert _refuses(doc)


def test_a_reading_built_model_is_still_rebuilt():
    doc = Document()
    doc.add(DocObject(type="Paragraph", props={"text": "a paragraph"}))
    doc.add(DocObject(type="Diagram", props={"image_id": "x"}))
    assert not _refuses(doc)


def test_another_passs_addition_does_not_count():
    """`added_by` names the pass. Only the author's LaTeX matters here —
    `heading_promote` and `footnote_cleanup` write it too."""
    doc = Document()
    doc.add(DocObject(type="Section", props={"added_by": "heading_promote"}))
    doc.add(DocObject(type="Footnote", props={"added_by": "footnote_cleanup"}))
    assert not _refuses(doc)


def test_the_guard_is_in_the_source_chooser():
    import inspect

    from pdfdrill import commands
    src = inspect.getsource(commands._prefer_arxiv_source)
    assert 'added_by") == "latex"' in src, (
        "the rebuild must refuse a model the author's LaTeX already improved")


def test_the_label_alone_was_not_enough():
    """`meta['source']` is set only when EMPTY, so it cannot say this."""
    import inspect

    from pdfdrill import commands
    src = inspect.getsource(commands._prefer_arxiv_source)
    assert 'if not str(reloaded.meta.get("source") or ""):' in src, (
        "the label is still only set when empty — which is why the content "
        "check exists beside it")
