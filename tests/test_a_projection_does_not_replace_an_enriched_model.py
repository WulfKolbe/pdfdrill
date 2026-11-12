r"""`latex` must not throw away a hand correction to improve the model.

MEASURED, 2026-11-12, on the first end-to-end round trip of
`pdfdrill injecttiddlers` (1911.02782, an arXiv document):

    pdfdrill tiddlers --force          277 objects
    edit one formula in the wiki file  latex: ^{1, 2} -> {}^{1, 2}
    pdfdrill injecttiddlers --apply    277 objects, obj_ca8c2d32ed23,
                                       latex={}^{1, 2}, wiki_edit=latex
    pdfdrill latex --force             270 objects, obj_65a56a35fb8b,
                                       latex=^{1, 2}, wiki_edit=None

The correction was gone and the ids had all changed. It was NOT the lazy
rebuild: `_stale_or_absent` was False and `builder_is_current` was True.

It was `_prefer_arxiv_source`. When a model was built from the PDF text layer
and the arXiv e-print is on disk, it rebuilds from the author's `.tex` -- "if
you have LaTeX from arXiv, improve it, don't ignore it" -- and PERSISTS the
result with `save_model`. It consulted no guard, so it replaced a model
carrying enrichments with one built from scratch: every object id regenerated,
every hand correction, refinement and TRANSLATION dropped, and nothing said so.
It is the fifth automatic-rebuild door in this module and the one no guard
covered (the others: `commands.py` 8227, 11010, 18911, 18970).

AN AUTOMATIC IMPROVEMENT DOES NOT OUTRANK A PERSON'S CORRECTION. The author's
source is better than the text layer in general; it is not better than a value
someone fixed by hand, and it cannot contain one. So when the model on disk
carries enrichments, the model on disk wins and the projection says which.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject            # noqa: E402
from pdfdrill import commands as K                        # noqa: E402
from pdfdrill import model_io                             # noqa: E402
from pdfdrill.sidecar import Sidecar                      # noqa: E402


def _doc_on_disk(tmp_path, *, enriched: bool):
    home = tmp_path / "2001.00001"
    home.mkdir(parents=True, exist_ok=True)
    pdf = home / "2001.00001.pdf"
    pdf.write_bytes(b"%PDF-1.7 stub\n%%EOF\n")
    doc = Document()
    doc.meta["bibkey"] = "2001.00001"
    doc.meta["source"] = "text-layer"          # NOT source-built, so the
    doc.add(DocObject(type="Formula", id="f1", props={                # branch is live
        "flow_index": 1, "page": 1, "latex": r"{}^{1, 2}",
        **({"wiki_edit": "latex"} if enriched else {})}))
    sc = Sidecar(pdf)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    mp = sc.blob_dir / "model.docmodel.json"
    model_io.save_model(mp, doc)
    sc.add_fact("MODEL_BUILT")
    sc.save()
    return pdf, Sidecar(pdf), mp, doc


def test_an_enriched_model_is_not_replaced_by_the_authors_source(tmp_path, monkeypatch):
    pdf, sc, mp, doc = _doc_on_disk(tmp_path, enriched=True)
    monkeypatch.setattr(K, "_arxiv_id_for", lambda *a, **k: "2001.00001")
    called = []
    monkeypatch.setattr(K, "_build_arxiv_source_model",
                        lambda *a, **k: called.append(1) or True)
    out = K._prefer_arxiv_source(pdf, sc, "2001.00001", doc, mp)
    assert not called, "it rebuilt from the author's source over an enrichment"
    assert out is doc
    assert out.objects["f1"].props["latex"] == r"{}^{1, 2}"


def test_a_plain_model_is_still_improved_from_the_authors_source(tmp_path, monkeypatch):
    """The behaviour the branch exists for is unchanged: a model built from the
    flawed text layer, with nothing hand-made in it, is still rebuilt from the
    author's `.tex`."""
    pdf, sc, mp, doc = _doc_on_disk(tmp_path, enriched=False)
    monkeypatch.setattr(K, "_arxiv_id_for", lambda *a, **k: "2001.00001")
    called = []
    monkeypatch.setattr(K, "_build_arxiv_source_model",
                        lambda *a, **k: called.append(1) or True)
    K._prefer_arxiv_source(pdf, sc, "2001.00001", doc, mp)
    assert called, "the author's source is no longer preferred at all"


def test_the_refusal_is_recorded_where_the_command_can_report_it(tmp_path, monkeypatch):
    """Silence is the defect. The projection carries on with the right model,
    and the reason is available to say."""
    pdf, sc, mp, doc = _doc_on_disk(tmp_path, enriched=True)
    monkeypatch.setattr(K, "_arxiv_id_for", lambda *a, **k: "2001.00001")
    called = []
    monkeypatch.setattr(K, "_build_arxiv_source_model",
                        lambda *a, **k: called.append(1) or True)
    K._prefer_arxiv_source(pdf, sc, "2001.00001", doc, mp)
    assert not called
    note = doc.meta.get("arxiv_source_refused", "")
    assert "enrichment" in str(note).lower(), note


def test_a_translated_model_is_covered_by_the_same_guard(tmp_path, monkeypatch):
    """The worst case, and the reason this is not a formula-only concern: on a
    translated arXiv document the same branch would have dropped every
    translated field."""
    pdf, sc, mp, doc = _doc_on_disk(tmp_path, enriched=False)
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "flow_index": 2, "page": 1, "text": "Correlation",
        "text_source": "Korrelation"}))
    model_io.save_model(mp, doc)
    monkeypatch.setattr(K, "_arxiv_id_for", lambda *a, **k: "2001.00001")
    called = []
    monkeypatch.setattr(K, "_build_arxiv_source_model",
                        lambda *a, **k: called.append(1) or True)
    out = K._prefer_arxiv_source(pdf, sc, "2001.00001", doc, mp)
    assert not called, (
        "it rebuilt from the author's source over a TRANSLATION -- the stub "
        "cannot raise to prove this, because the function swallows every "
        "exception, so the call itself is what is counted")
    assert out.objects["p1"].props["text_source"] == "Korrelation"
