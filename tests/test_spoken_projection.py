"""
`pdfdrill spoken` — the LLM INPUT text: prose with math replaced by its spoken form.

The end of the chain (expandmath -> speech engine -> here). A downstream consumer
that has no UI can only emit JSON; this makes the same text READABLE so it can be
diffed against that consumer's input instead of guessed at.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from pdfdrill import commands as C


def _doc(spoken=None):
    d = Document(); d.meta["bibkey"] = "K"
    d.add(DocObject(type="Formula", props={
        "latex": "f(x)", "flow_index": 1, **({"spoken": spoken} if spoken else {})}))
    d.add(DocObject(type="Paragraph", props={
        "text": "Let {{K_FO0001||FO}} denote it.", "flow_index": 2}))
    return d


def _run(tmp_path, monkeypatch, doc, **kw):
    pdf = tmp_path / "K.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
    mp = tmp_path / "m.json"; mp.write_text("{}")
    monkeypatch.setattr(C, "load_model", lambda p: doc)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    monkeypatch.setattr(C, "_model_path", lambda sc: mp)
    monkeypatch.setattr(C, "resolve_bibkey", lambda *a, **k: "K")
    return C.cmd_spoken(pdf, **kw)


def test_spoken_form_is_substituted_into_the_prose(tmp_path, monkeypatch):
    out = _run(tmp_path, monkeypatch, _doc(spoken="f of x"), to_stdout=True)
    assert out.strip() == "Let f of x denote it."
    assert "{{" not in out                       # no marker survives


def test_missing_spoken_is_VISIBLE_not_silently_dropped(tmp_path, monkeypatch):
    """An unspoken formula is a HOLE in the LLM's input. Seeing which ones are
    missing is the whole point of reading this projection."""
    out = _run(tmp_path, monkeypatch, _doc(), to_stdout=True)
    assert "⟨f(x)⟩" in out                       # falls back to the LaTeX, marked
    assert "{{" not in out


def test_fallback_modes(tmp_path, monkeypatch):
    assert "⟨no spoken: K_FO0001⟩" in _run(
        tmp_path, monkeypatch, _doc(), fallback="mark", to_stdout=True)
    # `drop` reproduces what a naive consumer effectively does — the math vanishes
    dropped = _run(tmp_path, monkeypatch, _doc(), fallback="drop", to_stdout=True)
    assert "Let  denote it." in dropped and "f(x)" not in dropped


def test_json_reports_the_gap_count(tmp_path, monkeypatch):
    p = json.loads(_run(tmp_path, monkeypatch, _doc(), as_json=True, to_stdout=True))
    assert p["counts"]["missing_spoken"] == 1
    assert p["counts"]["spoken_substituted"] == 0
    assert p["counts"]["unknown_markers"] == 0
    p2 = json.loads(_run(tmp_path, monkeypatch, _doc(spoken="f of x"), as_json=True,
                        to_stdout=True))
    assert p2["counts"]["spoken_substituted"] == 1
    assert p2["counts"]["missing_spoken"] == 0


def test_marker_pointing_at_nothing_is_flagged(tmp_path, monkeypatch):
    """A dangling marker is a real defect in the text — it must be named, not
    quietly rendered as empty."""
    d = Document(); d.meta["bibkey"] = "K"
    d.add(DocObject(type="Paragraph", props={
        "text": "see {{K_FO9999||FO}} here", "flow_index": 1}))
    out = _run(tmp_path, monkeypatch, d, to_stdout=True)
    assert "⟨unknown formula: K_FO9999⟩" in out
    p = json.loads(_run(tmp_path, monkeypatch, d, as_json=True, to_stdout=True))
    assert p["counts"]["unknown_markers"] == 1


def _doc_inline(spoken=None):
    """A MathPix-shaped model: math sits INLINE in the prose as `\\(…\\)`,
    there are no `{{…||FO}}` markers at all."""
    d = Document(); d.meta["bibkey"] = "K"
    p = {"latex": r"\Phi_{local}", "flow_index": 1}
    if spoken:
        p["spoken"] = spoken
    d.add(DocObject(type="Formula", props=p))
    d.add(DocObject(type="Paragraph", props={
        "text": r"where \(\Phi_{local}\) decays fast.", "flow_index": 2}))
    return d


def test_raw_inline_math_is_substituted_too(tmp_path, monkeypatch):
    """The cgr_88 case: a MathPix model keeps math inline, so a marker-only
    substitution silently did NOTHING and every formula stayed as LaTeX."""
    out = _run(tmp_path, monkeypatch, _doc_inline(spoken="Phi sub local"),
               to_stdout=True)
    assert "where Phi sub local decays fast." in out
    assert "\\(" not in out


def test_inline_math_matches_on_normalised_latex(tmp_path, monkeypatch):
    """Whitespace differences between the object's latex and the inline span
    must not defeat the lookup."""
    d = Document(); d.meta["bibkey"] = "K"
    d.add(DocObject(type="Formula", props={
        "latex": r"\Phi_{local}", "spoken": "Phi sub local", "flow_index": 1}))
    d.add(DocObject(type="Paragraph", props={
        "text": r"see \(\Phi_{local} \) here", "flow_index": 2}))
    assert "see Phi sub local here" in _run(tmp_path, monkeypatch, d, to_stdout=True)


def test_display_math_is_not_eaten_by_the_inline_rule(tmp_path, monkeypatch):
    """`$$…$$` must not be chewed by the single-`$` branch."""
    d = Document(); d.meta["bibkey"] = "K"
    d.add(DocObject(type="Paragraph", props={
        "text": "before $$E=mc^2$$ after", "flow_index": 1}))
    out = _run(tmp_path, monkeypatch, d, to_stdout=True)
    assert "$$E=mc^2$$" in out


def test_default_writes_a_file_instead_of_flooding_the_terminal(tmp_path, monkeypatch):
    """39k characters dumped to a terminal scrolls the answer away. Every other
    projection writes a file and reports the path — which is also what the UI
    turns into a clickable, saveable Output."""
    msg = _run(tmp_path, monkeypatch, _doc(spoken="f of x"),
               out=str(tmp_path / "s.txt"))
    assert "wrote" in msg and "preview:" in msg
    assert "--print" in msg                      # the escape hatch is advertised
    assert (tmp_path / "s.txt").read_text().strip() == "Let f of x denote it."
