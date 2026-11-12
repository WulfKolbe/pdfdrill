r"""`md --lang original` and `latex --lang original` on a translated model.

OWNER, 2026-11-12: "I need the original German version." And: "In the reflow
view only rendered text is shown via Markdown. You can choose if you show
Markdown, HTML or LaTeX."

A reflow view rendered from a projection is only worth building if the
projection can be asked for the language the reader chose. Before this, it
could not: the translation was the only thing `md` and `latex` could emit, on a
model that held both languages on every prose object.

TWO RULES THIS FILE PINS
------------------------
1. A LANGUAGE-TAGGED FILE NEVER OVERWRITES THE CANONICAL ONE. `<bibkey>.md` is
   the one filename a bought MathPix download also owns, and 41 downloads in
   the library are gone because a projection wrote it. `--lang` writes
   `<bibkey>.<code>.md` and leaves `<bibkey>.md` alone — even when the
   canonical file is OURS, because the caller asked for a language, not for the
   document's one markdown to be replaced.
2. THE MODEL IS NOT TOUCHED. The swap is a view over a loaded Document. The
   file on disk keeps its sha256.
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject          # noqa: E402
from pdfdrill import model_io                          # noqa: E402
from pdfdrill.commands import cmd_latex, cmd_md        # noqa: E402
from pdfdrill.sidecar import Sidecar                   # noqa: E402

GERMAN = "Korrelation im Hubbard Modell"
ENGLISH = "Correlation in the Hubbard Model"


def _translated_doc(*, translated=True):
    doc = Document()
    doc.meta["bibkey"] = "doc"
    doc.meta["num_pages"] = 1
    doc.meta["pages"] = [{"page": 1, "page_width": 1000, "page_height": 1400}]
    if translated:
        doc.meta["source_lang"] = "DE"
        doc.meta["translated_lang"] = "EN-US"
    doc.add(DocObject(type="Section", id="s1", props={
        "flow_index": 1, "page": 1, "level": 1,
        "caption": "Table of Contents" if translated else "Inhaltsverzeichnis",
        **({"caption_source": "Inhaltsverzeichnis"} if translated else {})}))
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "flow_index": 2, "page": 1,
        "text": ENGLISH if translated else GERMAN,
        **({"text_source": GERMAN} if translated else {})}))
    return doc


def _drilled(tmp_path, *, translated=True):
    """A document in the self-contained layout, with a bilingual model."""
    home = tmp_path / "doc"
    home.mkdir(parents=True, exist_ok=True)
    pdf = home / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.7 stub\n%%EOF\n")
    sc = Sidecar(pdf)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    mp = sc.blob_dir / "model.docmodel.json"
    model_io.save_model(mp, _translated_doc(translated=translated))
    sc.set_evidence("pages", 1)
    sc.add_fact("MODEL_BUILT")
    sc.save()
    return pdf, sc, mp


# ── markdown ────────────────────────────────────────────────────────────────

def test_md_lang_original_writes_a_language_tagged_file_with_the_german(tmp_path):
    pdf, sc, _ = _drilled(tmp_path)
    out = cmd_md(pdf, lang="original")
    tagged = sc.blob_dir / "doc.de.md"
    assert tagged.is_file(), out
    body = tagged.read_text(encoding="utf-8")
    assert GERMAN in body, body[:400]
    assert ENGLISH not in body, "the translation leaked into the original-language file"
    assert "Inhaltsverzeichnis" in body, "the caption was not switched"


def test_md_lang_translated_writes_its_own_tagged_file(tmp_path):
    pdf, sc, _ = _drilled(tmp_path)
    cmd_md(pdf, lang="translated")
    tagged = sc.blob_dir / "doc.en-us.md"
    assert tagged.is_file()
    body = tagged.read_text(encoding="utf-8")
    assert ENGLISH in body and GERMAN not in body


def test_the_canonical_markdown_is_never_overwritten(tmp_path):
    """The rule that cost 41 bought MathPix downloads."""
    pdf, sc, _ = _drilled(tmp_path)
    canonical = sc.blob_dir / "doc.md"
    canonical.write_text("# bought from MathPix\n", encoding="utf-8")
    before = hashlib.sha256(canonical.read_bytes()).hexdigest()
    cmd_md(pdf, lang="original")
    assert hashlib.sha256(canonical.read_bytes()).hexdigest() == before, \
        "`md --lang` overwrote the document's one markdown file"


def test_md_names_the_language_and_the_count_it_swapped(tmp_path):
    pdf, _, _ = _drilled(tmp_path)
    out = cmd_md(pdf, lang="original")
    assert "DE" in out, out
    assert "doc.de.md" in out, out
    assert "2" in out, "the number of fields switched is not reported: " + out


def test_md_on_a_monolingual_document_writes_no_language_file(tmp_path):
    """Asking for a language a document does not have must not produce a file
    that claims it."""
    pdf, sc, _ = _drilled(tmp_path, translated=False)
    out = cmd_md(pdf, lang="original")
    assert not list(sc.blob_dir.glob("doc.*.md")), \
        "a language-tagged file was written for a monolingual document"
    assert "one language" in out.lower() or "not translated" in out.lower(), out


def test_the_model_file_keeps_its_sha256(tmp_path):
    pdf, _, mp = _drilled(tmp_path)
    before = hashlib.sha256(mp.read_bytes()).hexdigest()
    cmd_md(pdf, lang="original")
    assert hashlib.sha256(mp.read_bytes()).hexdigest() == before, \
        "the projection wrote to the model"


# ── latex ───────────────────────────────────────────────────────────────────

def test_latex_lang_original_writes_a_language_tagged_tex(tmp_path):
    pdf, sc, _ = _drilled(tmp_path)
    out = cmd_latex(pdf, lang="original")
    tagged = sc.blob_dir / "latex" / "doc.de.tex"
    assert tagged.is_file(), out
    body = tagged.read_text(encoding="utf-8")
    assert GERMAN in body, body[:400]
    assert ENGLISH not in body


def test_latex_leaves_the_canonical_tex_alone(tmp_path):
    pdf, sc, _ = _drilled(tmp_path)
    cmd_latex(pdf)                                   # the canonical projection
    canonical = sc.blob_dir / "latex" / "doc.tex"
    before = hashlib.sha256(canonical.read_bytes()).hexdigest()
    cmd_latex(pdf, lang="original")
    assert hashlib.sha256(canonical.read_bytes()).hexdigest() == before
    assert ENGLISH in canonical.read_text(encoding="utf-8")
