r"""An automatic rebuild is still a rebuild, and must obey the same guard.

OWNER, 2026-11-12, in drillui, on the 400-page German book BH2:

    ❯ add BH2.pdf
      adding BH2.pdf … (reuses an existing drill; only builds if new)

That message is what the REPL prints; what pdfdrill did underneath was rebuild
the model — 69,125,067 bytes to 58,354,019 — and throw away the 818 bilingual
paragraphs of a document whose sidecar still says `translated_count: 818`,
`source_lang: DE`, `translated_lang: EN-US`. The German original of every
paragraph was in `model.docmodel.json` as a `text_source` twin; afterwards the
file held none. Nothing asked for a rebuild and nothing reported one.

HOW THE GUARD WAS BYPASSED. `cmd_model` computed the refusal correctly:

    blocked = model_rebuild_blocked(TRANSLATED in sc.facts, …)
    if blocked and force:          # ← force ONLY
        return blocked

and then, forty lines later, rebuilt anyway whenever `stale` was true. `stale`
is not only "lines.json is newer": since 2026-10-30 it is also "the
model-BUILDING code changed" (`buildstamp.builder_key`, the owner's lazy-rebuild
decision). Commit 36932e05 added a docmodel module, so EVERY model in a
3,235-folder library became builder-stale in one commit, and `add` runs `model`
on every document in context. The first touch of a translated document after
that commit destroyed its translation.

`model_rebuild_blocked`'s docstring already recorded three such losses in one
week, "each time recovered only because a backup happened to exist". The guard
watched the door marked --force; this one opens by itself.

THE RULE. A rebuild that would REPLACE an existing model consults the guard,
whoever asked for it — the user, `--ensure`, or a builder-key change. A FIRST
build destroys nothing and is never blocked.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import buildstamp                               # noqa: E402
from pdfdrill.commands import cmd_model                       # noqa: E402

#: A PDF that exists is all `cmd_model` needs here: the guard answers before
#: anything reads the document.
FILES = Path(__file__).resolve().parents[1] / "tests" / "files"


def _a_document(tmp_path, *, translated: bool, enriched: bool = False,
                builder: str = "0000deadbeef") -> tuple[Path, Path]:
    """A drilled document whose model was built by OTHER code (hence stale).

    Self-contained layout (`<stem>/<stem>.pdf`), so the sidecar and the model
    sit beside the PDF exactly as they do in the library.
    """
    doc = tmp_path / "BOOK"
    doc.mkdir()
    pdf = doc / "BOOK.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    props = {"text": "the translation", "text_source": "das Original"} \
        if translated else {"text": "prose"}
    if enriched:
        props["trailing_punct"] = "."
    model = doc / "model.docmodel.json"
    model.write_text(json.dumps({
        "meta": {"bibkey": "BOOK",
                 "build": {"sha": "old", "dirty": False, "version": "0.1.0",
                           "builder": builder, "at": "2026-10-23T10:17:00+02:00"}},
        "objects": [{"id": "o1", "type": "Paragraph", "props": props,
                     "realizations": []}],
        "streams": {},
    }), encoding="utf-8")
    facts = ["MODEL_BUILT"] + (["TRANSLATED"] if translated else [])
    evidence = {"model_path": "model.docmodel.json", "bibkey": "BOOK"}
    if translated:
        evidence.update({"translated_lang": "EN-US", "source_lang": "DE",
                         "translated_count": 818})
    (doc / "BOOK.drill.json").write_text(json.dumps({
        "pdf": "BOOK.pdf", "facts": facts, "evidence": evidence}),
        encoding="utf-8")
    return pdf, model


def test_the_model_is_builder_stale_so_the_case_is_what_it_claims():
    """The fixture's premise, asserted rather than assumed: with a current
    builder key nothing would rebuild and the test would pass vacuously."""
    assert buildstamp.builder_key() != "0000deadbeef"


def test_an_automatic_rebuild_of_a_translated_model_is_refused(tmp_path):
    pdf, model = _a_document(tmp_path, translated=True)
    before = model.read_bytes()
    out = str(cmd_model(pdf))
    assert "Refusing to rebuild" in out, out
    assert model.read_bytes() == before, "the translated model was overwritten"


def test_the_refusal_says_nobody_asked_for_it(tmp_path):
    """A refusal out of nowhere, on a command that never mentioned a rebuild,
    is its own confusion — it must name the automatic trigger."""
    pdf, _ = _a_document(tmp_path, translated=True)
    out = str(cmd_model(pdf))
    assert "NOTHING ASKED FOR THIS REBUILD" in out
    assert "built by 0000dea, now" in out, out
    assert "untouched and still in use" in out


def test_the_override_still_lets_it_through(tmp_path):
    """The owner must keep a way to rebuild deliberately. This one reaches the
    build, so it is enough that the refusal is gone."""
    pdf, _ = _a_document(tmp_path, translated=True)
    out = str(cmd_model(pdf, force_discard_translation=True))
    assert "Refusing to rebuild" not in out


def test_an_automatic_rebuild_over_enrichments_is_refused_too(tmp_path):
    """431's guard had the same `force`-only wiring. BH2 carried 19
    `trailing_punct` edits as well as the translation."""
    pdf, model = _a_document(tmp_path, translated=False, enriched=True)
    before = model.read_bytes()
    out = str(cmd_model(pdf))
    assert "trailing_punct" in out and "NOTHING ASKED" in out, out
    assert model.read_bytes() == before


def test_a_clean_model_is_still_rebuilt_automatically(tmp_path):
    """The lazy rebuild must keep working where there is nothing to lose — the
    owner asked for it, and a guard that blocks every stale model would turn a
    docmodel commit into a corpus-wide freeze."""
    pdf, _ = _a_document(tmp_path, translated=False)
    out = str(cmd_model(pdf))
    assert "Refusing to rebuild" not in out
    assert "NOTHING ASKED" not in out


def test_a_first_build_is_never_blocked(tmp_path):
    """No model on disk means nothing to destroy. A document with no model must
    not be refused because its sidecar claims a translation."""
    pdf, model = _a_document(tmp_path, translated=True)
    model.unlink()
    out = str(cmd_model(pdf))
    assert "Refusing to rebuild" not in out

