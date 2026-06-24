"""Semantic-compiler seed: a general FRONTMATTER object detected across input
FORMATS via per-(object,format) CELLS, concluding to ONE uniform BibTeX-like
record.

The unification under test (the user's rule):
  * LaTeX `\author` ≡ commercial-letter `sender` ≡ invoice `issuer`  → BibTeX author
  * a letter's RECIPIENT is the only genre-specific addition → a `recipient` field
    (NOT an address entity per author).

Architecture under test:
  * one OBJECT module (frontmatter) owns the schema + the conclusion,
  * one FORMAT module per surface (latex / text),
  * one CELL per (object, format) does the detection — the slot a LEAN grammar
    will later generate. Registries are keyed by kind / format / (kind,format).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


LATEX = r"""
\documentclass{article}
\title{Auto-Encoding Variational Bayes}
\author{Diederik P. Kingma \and Max Welling}
\date{December 2013}
\begin{document}
\maketitle
Body text here.
"""

LETTER = """Finanzamt Köln-Süd
Postfach 12 34, 50667 Köln

Herrn
Wulf Kolbe
Musterstraße 5
51515 Kürten

23. Juni 2026

Sehr geehrter Herr Kolbe,
anbei Ihr Steuerbescheid.
"""


def test_registry_has_frontmatter_cells_for_both_formats():
    from semantic.frontend import contract as C
    assert C.get_object("frontmatter") is not None
    assert C.get_cell("frontmatter", "latex") is not None
    assert C.get_cell("frontmatter", "text") is not None


def test_detect_latex_frontmatter():
    from semantic.frontend import detect
    fms = detect(LATEX, fmt="latex", kind="frontmatter")
    assert len(fms) == 1
    fm = fms[0]
    assert fm.kind == "frontmatter" and fm.format == "latex"
    f = fm.fields
    assert f["genre"] == "article"
    assert f["title"] == "Auto-Encoding Variational Bayes"
    names = [a["name"] for a in f["agents"] if a["role"] == "author"]
    assert names == ["Diederik P. Kingma", "Max Welling"]
    assert "2013" in (f.get("date") or "")


def test_detect_letter_frontmatter_sender_is_author():
    from semantic.frontend import detect
    fms = detect(LETTER, fmt="text", kind="frontmatter")
    assert len(fms) == 1
    f = fms[0].fields
    assert f["genre"] == "letter"
    senders = [a["name"] for a in f["agents"] if a["role"] == "sender"]
    assert senders and "Finanzamt" in senders[0]
    recips = [r["name"] for r in f["recipients"]]
    assert any("Wulf Kolbe" in (r or "") for r in recips)


def test_conclude_latex_to_bibtex_author_record():
    from semantic.frontend import detect, to_bibtex
    fm = detect(LATEX, fmt="latex", kind="frontmatter")[0]
    rec = to_bibtex(fm)
    assert rec["entrytype"] == "article"
    assert "Kingma" in rec["author"] and "Welling" in rec["author"]
    assert rec["title"] == "Auto-Encoding Variational Bayes"
    assert "recipient" not in rec            # a paper has no recipient


def test_conclude_letter_to_bibtex_sender_is_author_recipient_is_field():
    from semantic.frontend import detect, to_bibtex
    fm = detect(LETTER, fmt="text", kind="frontmatter")[0]
    rec = to_bibtex(fm)
    # the SENDER becomes the BibTeX author (the unification) ...
    assert "Finanzamt" in rec["author"]
    # ... and the RECIPIENT is a new field, not an author / address entity.
    assert "Wulf Kolbe" in rec["recipient"]
    assert rec["entrytype"] in ("letter", "misc")


if __name__ == "__main__":
    for fn in [test_registry_has_frontmatter_cells_for_both_formats,
               test_detect_latex_frontmatter,
               test_detect_letter_frontmatter_sender_is_author,
               test_conclude_latex_to_bibtex_author_record,
               test_conclude_letter_to_bibtex_sender_is_author_recipient_is_field]:
        fn(); print("PASS", fn.__name__)
    print("\nAll tests passed.")
