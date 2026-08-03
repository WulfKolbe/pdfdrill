"""
`pdfdrill speak` — la2speech integration: math → speech, stored as `spoken`.

The Python half of la2speech is VENDORED (src/pdfdrill/la2speech). The speech
ENGINE is npm speech-rule-engine — 9.6 MB of JavaScript that belongs in an
install step, so it is looked up, not shipped.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from pdfdrill import commands as C


def test_vendored_package_exposes_the_api_speak_uses():
    """Import must work from INSIDE the package (the intra-package rewiring),
    not only from the original project directory."""
    from pdfdrill.la2speech import (SRESpeechBackend, LatexSpeaker,
                                    normalize_whitespace)
    assert all(callable(x) or isinstance(x, type)
               for x in (SRESpeechBackend, LatexSpeaker, normalize_whitespace))


def test_engine_lookup_order(tmp_path, monkeypatch):
    monkeypatch.delenv("PDFDRILL_SRE_DIR", raising=False)
    fake = tmp_path / "sre"; fake.mkdir()
    monkeypatch.setenv("PDFDRILL_SRE_DIR", str(fake))
    assert C.sre_engine_dir() == fake
    monkeypatch.setenv("PDFDRILL_SRE_DIR", str(tmp_path / "nope"))
    got = C.sre_engine_dir()                    # falls through to the real ones
    assert got is None or got.is_dir()


def _doc(*latex, spoken=None, unresolved=None):
    d = Document(); d.meta["bibkey"] = "K"
    for i, x in enumerate(latex):
        p = {"latex": x, "flow_index": i + 1}
        if spoken:
            p["spoken"] = spoken
        if unresolved:
            p["macros_unresolved"] = unresolved
        d.add(DocObject(type="Formula", props=p))
    return d


class _FakeSpeaker:
    def __init__(self, *a, **k): self.errors = []
    def speak_math(self, tex): return f"SPOKEN<{tex}>"


class _FakeBackend:
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _run(tmp_path, monkeypatch, doc, speaker=None, **kw):
    pdf = tmp_path / "K.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
    mp = tmp_path / "m.json"; mp.write_text("{}")
    saved = {}
    monkeypatch.setattr(C, "sre_engine_dir", lambda: tmp_path)
    monkeypatch.setattr(C, "load_model", lambda p: doc)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    monkeypatch.setattr(C, "_model_path", lambda sc: mp)
    monkeypatch.setattr(C, "save_model", lambda path, d: saved.setdefault("d", d))
    import pdfdrill.la2speech as la
    monkeypatch.setattr(la, "SRESpeechBackend", _FakeBackend, raising=False)
    monkeypatch.setattr(la, "LatexSpeaker", speaker or _FakeSpeaker,
                        raising=False)
    return C.cmd_speak(pdf, **kw), saved.get("d")


def test_stores_spoken_on_the_object(tmp_path, monkeypatch):
    msg, out = _run(tmp_path, monkeypatch, _doc("f(x)"))
    o = [x for x in out.objects.values() if x.type == "Formula"][0]
    assert o.props["spoken"] == "SPOKEN<f(x)>"
    assert o.props["spoken_by"].startswith("la2speech/")
    assert "1 of 1 rendered" in msg
    assert "pdfdrill spoken" in msg              # tells you how to read it


def test_is_idempotent_unless_forced(tmp_path, monkeypatch):
    msg, out = _run(tmp_path, monkeypatch, _doc("f(x)", spoken="already said"))
    assert out is None and "Nothing to speak" in msg and "already carry" in msg
    msg2, out2 = _run(tmp_path, monkeypatch,
                      _doc("f(x)", spoken="already said"), force=True)
    assert out2 is not None
    o = [x for x in out2.objects.values() if x.type == "Formula"][0]
    assert o.props["spoken"] == "SPOKEN<f(x)>"


def test_unresolved_macros_are_warned_about(tmp_path, monkeypatch):
    """The engine has NO macro table, so an unexpanded macro is spoken as its
    letters — the user must be told to run expandmath, not left guessing."""
    msg, _ = _run(tmp_path, monkeypatch,
                  _doc(r"\res(a)", unresolved=["\\res"]))
    assert "macros_unresolved" in msg and "expandmath" in msg


def test_missing_engine_gives_an_actionable_message(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "sre_engine_dir", lambda: None)
    pdf = tmp_path / "K.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
    msg = C.cmd_speak(pdf)
    assert "No speech-rule-engine found" in msg
    assert "setup.sh" in msg and "PDFDRILL_SRE_DIR" in msg


# --- speech-noise stripping (the conceptdrill "backslash" report) -------------

def test_typesetting_noops_never_reach_the_engine():
    """latex2mathml has no macro table, so an unknown control sequence survives
    into the MathML and the engine SPELLS IT OUT — `\\xspace` becomes the words
    "backslash xspace" inside text handed to an LLM. Measured on the reported
    corpus: 578 of 694 offending texts were `\\xspace` alone."""
    from pdfdrill.commands import clean_for_speech as c
    assert c(r"A\xspace B") == "A B"
    assert "\\protect" not in c(r"\protect\independenT{X}{Y}")
    assert c(r"x\vspace{1em}y") == "x y"
    # symbol spacings are left to the engine, which renders them correctly
    assert c(r"\int_0^1 x\,dx") == r"\int_0^1 x\,dx"
    for noop in (r"\allowbreak", r"\relax", r"\displaystyle", r"\noindent"):
        # a separator is required: `\allowbreaky` is a DIFFERENT macro, and the
        # `(?![a-zA-Z])` guard must not strip a prefix of a longer name.
        assert "\\" not in c(f"x{noop} y")
        assert "\\allowbreaky" in c(r"x\allowbreaky")      # guard holds


def test_font_wrappers_are_unwrapped_content_kept():
    from pdfdrill.commands import clean_for_speech as c
    assert c(r"\ensuremath{\mathbb{D}}") == r"\mathbb{D}"
    assert c(r"\textsc{Name} x") == "Name x"
    assert c(r"\textbf{\textit{deep}}") == "deep"          # nested


def test_real_mathematics_is_untouched():
    """The cleaner must not damage the maths — it only removes typesetting."""
    from pdfdrill.commands import clean_for_speech as c
    for keep in (r"\int_0^\infty e^{-x^2}\,dx", r"\frac{a}{b}",
                 r"\sum_{i=1}^n x_i", r"w_+,w_- \in \mathbb{R}"):
        out = c(keep)
        for tok in ("\\int", "\\frac", "\\sum", "\\in", "\\mathbb"):
            if tok in keep:
                assert tok in out, f"{tok} lost from {keep}"
    assert c("") == "" and c("plain") == "plain"


def test_speak_flags_a_rendering_that_still_says_backslash(tmp_path, monkeypatch):
    """A literal "backslash" in the speech means the engine met something it
    cannot render — that text is wrong INPUT for an LLM, so it is recorded on
    the object (`spoken_suspect`) and counted, not merely left visible."""
    class _Say:
        def __init__(self, *a, **k): self.errors = []
        def speak_math(self, tex): return "backslash independenT of x"
    msg, out = _run(tmp_path, monkeypatch, _doc(r"\independenT{X}{Y}"),
                    speaker=_Say)
    o = [x for x in out.objects.values() if x.type == "Formula"][0]
    assert o.props["spoken_suspect"] is True
    assert "spoken_suspect" in msg and "wrong INPUT" in msg


# --- token boundary + unrenderable-macro substitution ------------------------

def test_unwrapping_must_not_glue_onto_a_control_word():
    """Reported by conceptdrill: `\\mid\\ensuremath{M}` came out as `\\midM` —
    a control sequence that was NEVER defined, so a perfectly speakable `\\mid`
    became "backslash midM". Unwrapping must preserve the token boundary."""
    from pdfdrill.commands import clean_for_speech as c
    assert c(r"\mid\ensuremath{M}") == r"\mid{}M"
    assert "midM" not in c(r"L(\ensuremath{D}\mid\ensuremath{M})")
    # no boundary needed when what precedes is not a control word
    assert c(r"a\ensuremath{b}") == "ab"


def test_known_unrenderable_macros_become_speakable_notation():
    """latex2mathml lacks these, so the engine spells them out. Each maps to
    STANDARD notation — never to invented words."""
    from pdfdrill.commands import clean_for_speech as c
    assert r"\perp" in c(r"\independenT")          # ⫫ independence
    assert r"\lfloor" in c(r"\floor{x}")
    assert r"\equiv" in c(r"\triple")
    assert r"\ell" in c(r"\l")


def test_mathpalette_keeps_the_symbol_drops_the_sizing_arg():
    """`\\mathpalette{\\draw}{style}`: the first argument is the thing, the
    second only says how big. The real leak was this whole construct."""
    from pdfdrill.commands import clean_for_speech as c
    out = c(r"X \protect\mathpalette{\protect\independenT}{\perp} N")
    assert "mathpalette" not in out and r"\perp" in out
    assert out.startswith("X") and out.rstrip().endswith("N")


def test_an_unknown_macro_is_left_alone_not_guessed():
    """Anything not in the (small, evidence-driven) table must survive intact —
    the object stays flagged rather than having a meaning invented for it."""
    from pdfdrill.commands import clean_for_speech as c
    assert c(r"\unknownMacro{x}") == r"\unknownMacro{x}"


def test_provisional_bare_text_repair():
    """PROVISIONAL (remove when extraction stops emitting it): `\\text\\mathrm{{Iso}}`
    — a `\\text` with no argument plus doubled braces — is malformed LaTeX from
    the extraction stage. It makes the engine say "backslash mathrm I s o" and
    makes KaTeX raise Undefined control sequence on the same string."""
    from pdfdrill.commands import repair_bare_text as r
    assert r(r"\alpha \in \text\mathrm{{Iso}}") == r"\alpha \in \mathrm{Iso}"
    assert r(r"\text\mathsf{{X}}") == r"\mathsf{X}"
    # valid LaTeX must be untouched
    assert r(r"\text{normal} and \mathrm{ok}") == r"\text{normal} and \mathrm{ok}"
    # a doubled group that is NOT the whole argument carries real grouping
    assert r(r"\mathrm{{a}{b}}") == r"\mathrm{{a}{b}}"


def test_mixed_case_function_name_is_not_spelled_out():
    """`Obj(e)` was spoken "O b j of e": in math mode a letter run is a product.
    la2speech protects all-UPPER (>=2) and all-lower (>=3) runs, so a MIXED-case
    name falls between its rules. `\\operatorname{}` is the right wrapper — it is
    the only one that keeps the application audible ("Obj of e", where
    `\\text{}`/`\\mathrm{}` both give "Obj e")."""
    from pdfdrill.commands import funcnames_to_operatorname as f
    assert f(r"Obj(e)") == r"\operatorname{Obj}(e)"
    assert f(r"Let Obj(c) be") == r"Let \operatorname{Obj}(c) be"
    # leave alone: already a command, a single-letter variable, and the two
    # shapes la2speech already handles
    for keep in (r"\sin(x)", r"f(x)", r"X(y)", r"ABC(x)", r"abc(x)"):
        assert f(keep) == keep, keep
    assert f(r"\operatorname{Obj}(e)") == r"\operatorname{Obj}(e)"   # idempotent


def test_clean_for_speech_reaches_latex_without_a_backslash():
    """Regression: the "no backslash -> return early" shortcut skipped `Obj(e)`
    entirely, so the rule above never ran on the very input it targets."""
    from pdfdrill.commands import clean_for_speech as c
    assert c(r"Obj(e)") == r"\operatorname{Obj}(e)"
