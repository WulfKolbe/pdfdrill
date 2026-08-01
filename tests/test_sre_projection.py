"""
`pdfdrill sre` — the spoken-math projection (latex2mml → MathML → speech-rule-engine).

The consumer's hard constraint drives the design: **latex2mml expands nothing**.
An unexpanded macro is not an error there — it is silently mis-spoken (`\\res(a)`
is read "res a"). So this projection must hand over macro-free LaTeX and name
every expression it could not make safe.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from pdfdrill import latex_source as ls
from pdfdrill import commands as C


def _blockers(frag: str, macros: dict) -> list[str]:
    out = ls.expand_macros(frag, macros)
    return sorted(set(re.findall(r"\\([A-Za-z]+)", out)) & set(macros))


def test_last_mile_expansion_resolves_what_latex2mml_cannot():
    """The value this pass adds: latex2mml would pass these through verbatim."""
    macros = ls.collect_macros(
        r"\newcommand{\res}[1]{\mathrm{res}(#1)}"
        "\n" r"\newcommand{\dom}{\ensuremath{\mathbb{D}}}", ".")
    assert set(macros) == {"res", "dom"}
    out = ls.expand_macros(r"\res{a} \in \dom", macros)
    assert out == r"\mathrm{res}(a) \in \ensuremath{\mathbb{D}}"
    assert _blockers(r"\res{a} \in \dom", macros) == []


def test_unexpandable_macro_is_flagged_not_passed_through():
    """The real case: `\\res(a)` uses PARENS while the macro takes a braced arg,
    so expansion cannot match and `\\res` survives — latex2mml would speak it
    as 'res a'. It must be reported, never silently emitted as safe."""
    macros = ls.collect_macros(r"\newcommand{\res}[1]{\mathrm{res}(#1)}", ".")
    assert _blockers(r"\res(a) = b", macros) == ["res"]


def _run(tmp_path, monkeypatch, doc, macros, **kw):
    pdf = tmp_path / "K.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(C, "load_model", lambda p: doc)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    monkeypatch.setattr(C, "_model_path", lambda sc: tmp_path / "m.json")
    (tmp_path / "m.json").write_text("{}")
    monkeypatch.setattr(C, "resolve_bibkey", lambda *a, **k: "K")
    monkeypatch.setattr(C, "_document_macros", lambda d, p=None: macros)
    outp = tmp_path / "sre.json"
    C.cmd_sre(pdf, out=str(outp), **kw)
    return json.loads(outp.read_text())


def _doc(*latex):
    d = Document(); d.meta["bibkey"] = "K"
    for i, x in enumerate(latex):
        d.add(DocObject(type="Formula", props={"latex": x, "flow_index": i + 1}))
    return d


def test_projection_expands_and_marks_safe(tmp_path, monkeypatch):
    macros = ls.collect_macros(r"\newcommand{\dom}{\mathbb{D}}", ".")
    p = _run(tmp_path, monkeypatch, _doc(r"x \in \dom"), macros)
    u = p["units"][0]
    assert u["latex_sre"] == r"x \in \mathbb{D}"     # feed THIS
    assert u["expanded_here"] is True and u["safe"] is True
    assert u["blockers"] == []
    assert u["placeholder"] == "{{K_FO0001||FO}}"    # maps back to the object
    assert u["spoken"] is None                       # reserved slot
    assert p["feed_field"] == "latex_sre"
    assert p["counts"] == {"total": 1, "safe": 1, "blocked": 0, "expanded_here": 1}


def test_blocked_unit_is_reported_and_droppable(tmp_path, monkeypatch):
    macros = ls.collect_macros(r"\newcommand{\res}[1]{\mathrm{res}(#1)}", ".")
    doc = _doc(r"\res(a) = b", r"y = 1")
    p = _run(tmp_path, monkeypatch, doc, macros)
    assert p["counts"]["blocked"] == 1 and p["counts"]["safe"] == 1
    bad = [u for u in p["units"] if not u["safe"]][0]
    assert bad["blockers"] == ["\\res"]
    assert "mis-spoken" in p["contract"]
    # --safe-only removes it, so nothing unsafe reaches the engine
    p2 = _run(tmp_path, monkeypatch, doc, macros, safe_only=True)
    assert p2["counts"]["total"] == 1 and all(u["safe"] for u in p2["units"])


def test_no_macro_table_declares_safe_unverified(tmp_path, monkeypatch):
    """Without a macro table NO expansion ran — `safe=true` must not be read as
    a guarantee, and the payload has to say so."""
    p = _run(tmp_path, monkeypatch, _doc(r"\res(a)"), None)
    assert p["macro_table"] == "unavailable"
    assert "UNVERIFIED" in p["macro_table_note"]
    assert "NOT because the LaTeX is" in p["macro_table_note"]
    assert p["units"][0]["expanded_here"] is False


def test_plain_emits_feedable_latex_only(tmp_path, monkeypatch):
    macros = ls.collect_macros(r"\newcommand{\dom}{\mathbb{D}}", ".")
    pdf = tmp_path / "K.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
    doc = _doc(r"x \in \dom", r"y")
    monkeypatch.setattr(C, "load_model", lambda p: doc)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    monkeypatch.setattr(C, "_model_path", lambda sc: tmp_path / "m.json")
    (tmp_path / "m.json").write_text("{}")
    monkeypatch.setattr(C, "resolve_bibkey", lambda *a, **k: "K")
    monkeypatch.setattr(C, "_document_macros", lambda d, p=None: macros)
    out = C.cmd_sre(pdf, plain=True)
    assert out.splitlines() == [r"x \in \mathbb{D}", "y"]
