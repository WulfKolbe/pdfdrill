r"""`add` discarded what `model` said, including a refusal.

OWNER, 2026-11-12, in drillui:

    ❯ add BH2.pdf
      adding BH2.pdf … (reuses an existing drill; only builds if new)
      context: BH2.pdf (1 document) — ask away.

Those three lines are everything the REPL said. Underneath, `pdfdrill model`
ran on the document and its output went nowhere — `do_add` called `_run` and
dropped the return value — so the line about reusing an existing drill was the
only account of what happened, whatever happened. On that document a rebuild
discarded 818 bilingual paragraphs.

The model guard now refuses that rebuild
(`test_an_automatic_rebuild_does_not_discard_a_translation`), but a refusal the
front end swallows is a guard the reader cannot see working. `add` prints it.

Only the refusal: the ordinary reuse line stays quiet, because `add` on five
documents would otherwise print five paragraphs nobody asked for.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import drillui_chat as DC                                     # noqa: E402

REFUSAL = ("Refusing to rebuild: this document is translated (EN-US) and the "
           "model is rebuilt from lines.json …\n"
           "  • NOTHING ASKED FOR THIS REBUILD — it was automatic")


def _added(tmp_path, monkeypatch, says: str):
    monkeypatch.setattr(DC, "_run", lambda *a, **k: says)
    pdf = tmp_path / "BOOK.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    DC.do_add(["pdfdrill"], {}, str(pdf), [], None, 60.0)


def test_a_refusal_reaches_the_reader(tmp_path, monkeypatch, capsys):
    _added(tmp_path, monkeypatch, REFUSAL)
    out = capsys.readouterr().out
    assert "Refusing to rebuild" in out
    assert "NOTHING ASKED FOR THIS REBUILD" in out


def test_the_document_is_still_added(tmp_path, monkeypatch, capsys):
    """The refusal is news, not a failure: the model on disk is intact and the
    document is usable, so the context must still open."""
    _added(tmp_path, monkeypatch, REFUSAL)
    out = capsys.readouterr().out
    assert "1 document" in out


def test_an_ordinary_reuse_stays_quiet(tmp_path, monkeypatch, capsys):
    """`add` of several documents must not print a paragraph each."""
    _added(tmp_path, monkeypatch, "BOOK.pdf: model already built (no-op).")
    out = capsys.readouterr().out
    assert "no-op" not in out
