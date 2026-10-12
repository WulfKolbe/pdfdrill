r"""901 — A FONT THAT SHIPS NO /Differences IS NOT A FONT WITHOUT NAMES.

`resolve_cid_by_name` is the general route for `(cid:N)` and it needs glyph
names, which it reads from the PDF's /Differences array. A 2000-era dvipdfm
file declares `Encoding /Builtin` and ships no array at all — `pdffonts` on The
TeXbook reports `uni no` for every one of its sixty-odd fonts — so the names
channel is empty and the route silently has nothing to do.

The names are not lost. They are STANDARD, and `texmap.CM_ENCODING` already
holds them, built from 391 (family, cid) pairs measured across 102 documents
with zero disagreements. What was missing was the one line that asks.

What it cost, measured on The TeXbook's own markdown before the fix:

    3,100  (cid:104)/(cid:105)   the angle brackets around EVERY syntax rule
      127  (cid:48)              the style primes D' T' S' SS'
        2  (cid:54)              the \not of the two formulas that use it

and a reader of that markdown reported "missing Greek letters", because what
reaches the eye is `C(cid:48)` where `C'` stood.

The second half is the overstrike: TeX sets `\ne` as `\not` then `=`, two
glyphs at the SAME x. Both halves survive extraction and neither means
anything alone, so `θ ≠ 0` read as `θ = 0` — a formula that is not garbled,
just WRONG, which is the worse failure.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import cid_glyphs
from pdfdrill.commands import _compose_overstrikes, _resolve_glyph


def test_the_standard_cm_names_are_available_when_the_font_states_none():
    names = cid_glyphs.cm_names("ELSGOY+CMSY6")
    assert names.get(48) == "prime"
    assert names.get(54) == "negationslash"
    assert names.get(104) == "angbracketleft"
    assert names.get(105) == "angbracketright"


def test_a_font_outside_the_measured_table_is_refused_not_guessed():
    """No table means `{}`, which leaves the `(cid:N)` standing."""
    assert cid_glyphs.cm_names("ZZZZZZ+FuturaNope") == {}
    assert cid_glyphs.cm_names("") == {}
    c = {"text": "(cid:104)", "font": "ZZZZZZ+FuturaNope"}
    assert _resolve_glyph(c, {}, cid_glyphs) == "(cid:104)"


def test_manfnt_resolves_only_the_codes_the_books_source_names():
    r"""902 — manfnt's table comes from texbook.tex, and is PARTIAL on purpose.

    Documented by the book's own macros: 127 (`\dbend`), 120 (the margin
    triangle, `\char'170`), 88/91 (`\pennytop`/`\pennyedge`) and the seven
    letters of `\def\MF{{\manual META}\-{\manual FONT}}`. Everything else
    manfnt ships — 97-100 and a tail at 104-117, 90 glyphs in The TeXbook —
    the source never names, so it must still come out as a visible `(cid:N)`.
    """
    names = cid_glyphs.cm_names("IJHGTT+manfnt")
    assert names[127] == "dbend" and names[120] == "mantriangle"
    assert names[88] == "pennytop" and names[91] == "pennyedge"
    for undocumented in (97, 98, 99, 100, 113, 117):
        assert undocumented not in names, undocumented
        c = {"text": f"(cid:{undocumented})", "font": "IJHGTT+manfnt"}
        assert _resolve_glyph(c, {}, cid_glyphs) == f"(cid:{undocumented})"


def test_manfnts_codes_do_not_leak_into_cmsy_or_the_other_way():
    """104/105 are CMSY's angle brackets and are NOT manfnt's. The two fonts
    disagree about the same code, which is the whole reason manfnt sat
    unresolved until its codes had a source."""
    assert _resolve_glyph({"text": "(cid:104)", "font": "X+CMSY10"},
                          {}, cid_glyphs) == "⟨"
    assert _resolve_glyph({"text": "(cid:104)", "font": "X+manfnt"},
                          {}, cid_glyphs) == "(cid:104)"
    assert _resolve_glyph({"text": "(cid:127)", "font": "X+CMSY10"},
                          {}, cid_glyphs) == "(cid:127)"


def test_the_two_manfnt_signs_are_stand_ins_and_the_penny_is_not():
    """⚠ and ▶ are CHOSEN substitutes — neither sign has a codepoint. The
    penny pieces are fragments of a drawing, so nothing stands in for them
    and they stay visible."""
    assert _resolve_glyph({"text": "(cid:127)", "font": "X+manfnt"},
                          {}, cid_glyphs) == "⚠"
    assert _resolve_glyph({"text": "(cid:120)", "font": "X+manfnt"},
                          {}, cid_glyphs) == "▶"
    assert cid_glyphs.glyph_name_to_char("pennytop") == ""
    assert cid_glyphs.glyph_name_to_char("pennyedge") == ""


def test_the_metafont_logo_comes_back_as_letters():
    r"""`{\manual META}{\manual FONT}` sets the logo as plain letters in
    manfnt. A one-character glyph name is that character."""
    out = "".join(
        _resolve_glyph({"text": f"(cid:{n})", "font": "X+manfnt"}, {}, cid_glyphs)
        for n in (77, 69, 84, 65, 70, 79, 78, 84))
    assert out == "METAFONT"


def test_the_texbooks_three_lost_symbols_resolve():
    for cid, want in ((48, "′"), (104, "⟨"), (105, "⟩")):
        c = {"text": f"(cid:{cid})", "font": "PTYKKN+CMSY10"}
        assert _resolve_glyph(c, {}, cid_glyphs) == want, cid


def test_the_fonts_own_names_still_win_over_the_standard_table():
    """A font that DOES ship /Differences is the authority on itself."""
    own = {48: "angbracketleft"}
    c = {"text": "(cid:48)", "font": "XXXXXX+CMSY10"}
    assert _resolve_glyph(c, {"CMSY10": own}, cid_glyphs) == "⟨"


def test_a_negation_overstrike_joins_the_character_it_crosses():
    """Measured: both occurrences put the slash and its `=` at an identical x0."""
    chars = [{"text": "θ", "x0": 83.9}, {"text": "̸", "x0": 92.1},
             {"text": "=", "x0": 92.1}, {"text": "0", "x0": 102.9}]
    assert "".join(c["text"] for c in _compose_overstrikes(chars)) == "θ≠0"


def test_a_slash_that_is_not_overstruck_is_left_alone():
    """Same x is the whole rule. A nearby slash is a different character."""
    chars = [{"text": "̸", "x0": 10.0}, {"text": "=", "x0": 25.0}]
    out = _compose_overstrikes(chars)
    assert len(out) == 2 and out[0]["text"] == "̸"


def test_a_pair_unicode_declines_to_compose_is_not_forced():
    """NFC is the authority on what negates. `̸` + a space composes to
    nothing, and inventing a character there would be the silent corruption
    the whole module exists to avoid."""
    chars = [{"text": "̸", "x0": 5.0}, {"text": "q", "x0": 5.0}]
    joined = "".join(c["text"] for c in _compose_overstrikes(chars))
    assert "̸" in joined and "≠" not in joined


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try:
            t()
            print(f"PASS {name}")
        except AssertionError as e:
            failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e:
            failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
