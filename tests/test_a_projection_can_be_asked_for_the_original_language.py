r"""A translated model carries both languages; a projection must be able to ask.

OWNER, 2026-11-12: "I need the original German version." And, about the
inspector: "In the reflow view only rendered text is shown via Markdown."

WHAT WAS WRONG. `pdfdrill translate` writes the target language IN PLACE and
keeps the original under `<field>_source`, so every prose object of a translated
model holds both languages. MEASURED: of the repo's 125 commands, not one could
emit the original — `md`'s only flags are `--pages` and `--image-base`,
`latex`'s are `--force`/`--compile`/`--dump-stages`/`--no-transclude`. The one
consumer that could reach the German was the JavaScript inside `docinspect`,
which reads the twin fields itself. So the owner's answer was an HTML inspector
and nothing else: no Markdown, no LaTeX, no PDF, in the language the document
was actually printed in.

THE TWIN RULE IS ONE RULE, AND IT LIVES IN ONE PLACE. An identical twin is NOT
a second language: transclusion materialisation also writes `text_source`, and
counting that would put a language on every materialised paragraph in the
library. `docinspect.element_translations` already knew it. A projector that
learned it separately would be a second opinion about what a language IS, so
both now read `docops.language`.

NOTHING ON DISK IS TOUCHED. The swap happens in an already-loaded Document, for
one projection to read. `model_io.save_model` is the model's only writer, and a
projection that edited the model would be editing the producer's record.
"""
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject          # noqa: E402
from docops import language                            # noqa: E402
from pdfdrill import docinspect, model_io              # noqa: E402


# ── the predicate, which two readers must agree on ──────────────────────────

CASES = [
    ("a real translation", {"text": "Hello", "text_source": "Hallo"}, True),
    ("an identical twin (materialisation)",
     {"text": "Hallo", "text_source": "Hallo"}, False),
    ("a blank source", {"text": "Hello", "text_source": "   "}, False),
    ("no source at all", {"text": "Hello"}, False),
    ("a non-string source", {"text": "Hello", "text_source": 7}, False),
    ("a missing current value", {"text_source": "Hallo"}, False),
]


@pytest.mark.parametrize("why,props,expected", CASES, ids=[c[0] for c in CASES])
def test_the_inspector_and_the_projections_use_one_twin_rule(why, props, expected):
    """If these ever disagree, one surface shows a language switch the other
    denies exists — which is the state the repo was in."""
    assert bool(language.twins(props)) is expected, why
    assert bool(docinspect.element_translations(props)) is expected, (
        why + " — the inspector disagrees with the projections")


# ── the view ────────────────────────────────────────────────────────────────

def _bilingual_doc():
    doc = Document()
    doc.meta["bibkey"] = "doc"
    doc.meta["source_lang"] = "DE"
    doc.meta["translated_lang"] = "EN-US"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "flow_index": 1, "page": 1,
        "text": "Correlation in the Hubbard Model",
        "text_source": "Korrelation im Hubbard Modell"}))
    doc.add(DocObject(type="Section", id="s1", props={
        "flow_index": 2, "page": 1, "level": 1,
        "caption": "Table of Contents", "caption_source": "Inhaltsverzeichnis"}))
    # materialised, NOT translated: identical twin
    doc.add(DocObject(type="Paragraph", id="p2", props={
        "flow_index": 3, "page": 1,
        "text": "see equation 4", "text_source": "see equation 4"}))
    # no twin at all
    doc.add(DocObject(type="Formula", id="f1", props={
        "flow_index": 4, "page": 1, "latex": "E = mc^2"}))
    return doc


def test_the_view_swaps_every_prose_field_that_has_a_twin():
    doc = _bilingual_doc()
    n = language.original_in_place(doc)
    assert n == 2, f"swapped {n} fields, expected text + caption"
    assert doc.objects["p1"].props["text"] == "Korrelation im Hubbard Modell"
    assert doc.objects["s1"].props["caption"] == "Inhaltsverzeichnis"


def test_an_identical_twin_is_left_exactly_as_it_was():
    """A materialised transclusion is not a translation. Swapping it would be
    harmless in value and a lie in the count."""
    doc = _bilingual_doc()
    language.original_in_place(doc)
    assert doc.objects["p2"].props["text"] == "see equation 4"
    assert doc.objects["p2"].props["text_source"] == "see equation 4"


def test_an_object_with_no_twin_is_untouched():
    doc = _bilingual_doc()
    language.original_in_place(doc)
    assert doc.objects["f1"].props == {"flow_index": 4, "page": 1,
                                       "latex": "E = mc^2"}


def test_the_swap_keeps_the_pair_so_it_is_its_own_inverse():
    """After the swap `text_source` holds the TRANSLATION. Applying it twice
    returns the document to where it started, which is what makes it a view
    rather than a destructive edit."""
    doc = _bilingual_doc()
    language.original_in_place(doc)
    assert doc.objects["p1"].props["text_source"] == "Correlation in the Hubbard Model"
    language.original_in_place(doc)
    assert doc.objects["p1"].props["text"] == "Correlation in the Hubbard Model"
    assert doc.objects["p1"].props["text_source"] == "Korrelation im Hubbard Modell"


def test_a_monolingual_document_swaps_nothing_and_says_so():
    doc = Document()
    doc.add(DocObject(type="Paragraph", id="p1", props={"text": "only one language"}))
    assert language.original_in_place(doc) == 0
    assert language.is_translated(doc) is False


def test_the_codes_come_from_the_models_own_record():
    doc = _bilingual_doc()
    assert language.codes(doc.meta) == ("DE", "EN-US")
    assert language.codes({}) == (None, None)


def test_the_model_on_disk_is_never_written(tmp_path):
    """THE EVIDENCE RULE. A projection asked for the original language must not
    leave a mark on the producer's record."""
    mp = tmp_path / "model.docmodel.json"
    model_io.save_model(mp, _bilingual_doc())
    before = hashlib.sha256(mp.read_bytes()).hexdigest()
    doc = model_io.load_model(mp)
    language.original_in_place(doc)
    assert hashlib.sha256(mp.read_bytes()).hexdigest() == before, \
        "the language view wrote to the model file"
