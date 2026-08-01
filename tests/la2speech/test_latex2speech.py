"""Test suite for latex2speech.

Every test is independent and named. Unit tests (U*) need no node; integration
tests (I*) need node_modules/speech-rule-engine + sre_bridge.js under SRE_DIR
and are reported as SKIP if that is absent.

Run:  python3 test_latex2speech.py [--sre-dir ./sre]
"""

from __future__ import annotations

import os
import sys

# vendored into pdfdrill: import from the package, not a sibling directory
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "src"))

from pdfdrill.la2speech import latexproject as lp  # noqa: E402
from pdfdrill.la2speech import tiddlerpipe as tp  # noqa: E402
from pdfdrill.la2speech import projections as pj  # noqa: E402
from pdfdrill.la2speech.latex2speech import (  # noqa: E402
    LatexSpeaker, MathMLError, NullSpeechBackend, SRESpeechBackend, Segment,
    SpeechError, clean_math, latex_to_mathml, normalize_whitespace, segment,
)

SRE_DIR = os.environ.get("SRE_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "sre"))

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + ((" -- " + detail) if detail and not cond else ""))
    return bool(cond)


def skip(name, why):
    RESULTS.append((name, None, why))
    print("SKIP " + name + " -- " + why)


# ==========================================================================
# U -- segmentation
# ==========================================================================

def U01_segment_inline_dollar():
    s = segment(r"let $x^2$ be", strip_preamble=False)
    check("U01_segment_inline_dollar",
          [(g.kind, g.text.strip(), g.display) for g in s]
          == [("text", "let", False), ("math", "x^2", False), ("text", "be", False)],
          repr(s))


def U02_segment_display_dollar():
    s = segment(r"a $$x=1$$ b", strip_preamble=False)
    check("U02_segment_display_dollar",
          len(s) == 3 and s[1].kind == "math" and s[1].display is True and s[1].text == "x=1",
          repr(s))


def U03_segment_paren_and_bracket():
    s = segment(r"a \(u\) b \[v\] c", strip_preamble=False)
    math = [(g.text, g.display) for g in s if g.kind == "math"]
    check("U03_segment_paren_and_bracket", math == [("u", False), ("v", True)], repr(s))


def U04_segment_math_environment():
    s = segment(r"pre \begin{equation}E=mc^2\end{equation} post", strip_preamble=False)
    m = [g for g in s if g.kind == "math"]
    check("U04_segment_math_environment",
          len(m) == 1 and m[0].display is True and "E=mc^2" in m[0].text, repr(s))


def U05_segment_escaped_dollar_is_text():
    s = segment(r"costs \$5 today", strip_preamble=False)
    check("U05_segment_escaped_dollar_is_text",
          all(g.kind == "text" for g in s), repr(s))


def U06_segment_comment_stripped():
    s = segment("keep % drop $x$\nnext", strip_preamble=False)
    joined = "".join(g.text for g in s)
    check("U06_segment_comment_stripped",
          "drop" not in joined and all(g.kind == "text" for g in s), repr(s))


def U07_segment_escaped_percent_kept():
    s = segment(r"50\% off", strip_preamble=False)
    check("U07_segment_escaped_percent_kept",
          r"\%" in "".join(g.text for g in s), repr(s))


def U08_segment_verbatim_not_scanned():
    s = segment("a \\begin{verbatim}$not math$\\end{verbatim} b", strip_preamble=False)
    kinds = [g.kind for g in s]
    check("U08_segment_verbatim_not_scanned",
          "math" not in kinds and kinds.count("verbatim") == 1
          and [g.text for g in s if g.kind == "verbatim"] == ["$not math$"], repr(s))


def U27_segment_verb_inline():
    s = segment(r"use \verb|$x$| here", strip_preamble=False)
    check("U27_segment_verb_inline",
          [(g.kind, g.text) for g in s if g.kind != "text"] == [("verbatim", "$x$")], repr(s))


def U28_verbatim_survives_to_output():
    sp = LatexSpeaker(NullSpeechBackend(), verbatim_mode="raw")
    out = sp.speak("a \\begin{verbatim}KEEPME\\end{verbatim} b", strip_preamble=False)
    check("U28_verbatim_survives_to_output", "KEEPME" in out, repr(out))


def U29_verbatim_skip_mode():
    sp = LatexSpeaker(NullSpeechBackend(), verbatim_mode="skip")
    out = sp.speak("a \\begin{verbatim}DROPME\\end{verbatim} b", strip_preamble=False)
    check("U29_verbatim_skip_mode", "DROPME" not in out and "a" in out, repr(out))


def U30_verbatim_announce_mode():
    sp = LatexSpeaker(NullSpeechBackend(), verbatim_mode="announce")
    out = sp.speak("\\begin{verbatim}X\\end{verbatim}", strip_preamble=False)
    check("U30_verbatim_announce_mode",
          "Begin code." in out and "End code." in out and "X" in out, repr(out))


def U31_section_sign_is_spoken():
    sp = LatexSpeaker(NullSpeechBackend())
    out = sp.speak(r"\section{Intro} text", strip_preamble=False)
    check("U31_section_sign_is_spoken",
          "\u00a7" not in out and "Section" in out and "INTRO" in out.upper(), repr(out))


def U32_nbsp_becomes_space():
    sp = LatexSpeaker(NullSpeechBackend())
    out = sp.speak("Fig.~1 shows", strip_preamble=False)
    check("U32_nbsp_becomes_space", "\u00a0" not in out and "Fig. 1" in out, repr(out))


def U09_segment_preamble_stripped():
    doc = ("\\documentclass{article}\n\\usepackage{amsmath}\n"
           "\\begin{document}\nbody $x$\n\\end{document}\n")
    s = segment(doc, strip_preamble=True)
    joined = "".join(g.text for g in s)
    check("U09_segment_preamble_stripped",
          "usepackage" not in joined and "body" in joined, repr(joined))


def U10_segment_preamble_kept_when_asked():
    doc = "\\documentclass{article}\n\\begin{document}\nbody\n\\end{document}\n"
    joined = "".join(g.text for g in segment(doc, strip_preamble=False))
    check("U10_segment_preamble_kept_when_asked", "documentclass" in joined, repr(joined))


def U11_segment_unterminated_dollar_is_text():
    s = segment(r"an unclosed $x + y", strip_preamble=False)
    check("U11_segment_unterminated_dollar_is_text",
          all(g.kind == "text" for g in s), repr(s))


def U12_segment_multiple_inline():
    s = segment(r"$a$ and $b$ and $c$", strip_preamble=False)
    check("U12_segment_multiple_inline",
          [g.text for g in s if g.kind == "math"] == ["a", "b", "c"], repr(s))


def U13_segment_text_lossless():
    src = "Alpha beta.\n\nGamma delta \\emph{x} end."
    joined = "".join(g.text for g in segment(src, strip_preamble=False))
    check("U13_segment_text_lossless", joined == src, repr(joined))


# ==========================================================================
# U -- cleaning / MathML
# ==========================================================================

def U14_clean_math_drops_label():
    out = clean_math(r"E=mc^2 \label{eq:e}")
    check("U14_clean_math_drops_label", "label" not in out, out)


def U15_clean_math_drops_nonumber():
    out = clean_math(r"x=1 \nonumber")
    check("U15_clean_math_drops_nonumber", "nonumber" not in out, out)


def U16_clean_math_starifies_align():
    out = clean_math(r"\begin{align}a&=b\end{align}")
    check("U16_clean_math_starifies_align",
          r"\begin{align*}" in out and r"\end{align*}" in out, out)


def U17_clean_math_leaves_starred_alone():
    out = clean_math(r"\begin{align*}a&=b\end{align*}")
    check("U17_clean_math_leaves_starred_alone", "align**" not in out, out)


def U18_latex_to_mathml_basic():
    m = latex_to_mathml(r"\frac{a}{b}")
    check("U18_latex_to_mathml_basic",
          m.startswith("<math") and "<mfrac>" in m, m[:80])


def U19_latex_to_mathml_display_attr():
    m = latex_to_mathml(r"x", display=True)
    check("U19_latex_to_mathml_display_attr", 'display="block"' in m, m[:80])


def U20_latex_to_mathml_empty_raises():
    try:
        latex_to_mathml("   ")
        check("U20_latex_to_mathml_empty_raises", False, "no exception")
    except MathMLError:
        check("U20_latex_to_mathml_empty_raises", True)


def U33_mspace_is_stripped():
    m = latex_to_mathml(r"\qquad \Re(s)")
    check("U33_mspace_is_stripped", "<mspace" not in m, m[:120])


def U21_normalize_whitespace_keeps_paragraphs():
    out = normalize_whitespace("a  \n\n\n\n  b   c")
    check("U21_normalize_whitespace_keeps_paragraphs", out == "a\n\nb c", repr(out))


# ==========================================================================
# U -- driver with NullSpeechBackend (no node needed)
# ==========================================================================

def U22_null_backend_document():
    sp = LatexSpeaker(NullSpeechBackend())
    out = sp.speak(r"let $x$ be", strip_preamble=False)
    check("U22_null_backend_document", "[math]" in out and "let" in out, repr(out))


def U23_on_error_placeholder():
    sp = LatexSpeaker(NullSpeechBackend(), on_error="placeholder")
    out = sp.speak_math("")
    check("U23_on_error_placeholder",
          out == "[unspoken math]" and len(sp.errors) == 1, repr(out))


def U24_on_error_raw():
    sp = LatexSpeaker(NullSpeechBackend(), on_error="raw")
    check("U24_on_error_raw", sp.speak_math("") == "", repr(sp.errors))


def U25_on_error_raise():
    sp = LatexSpeaker(NullSpeechBackend(), on_error="raise")
    try:
        sp.speak_math("")
        check("U25_on_error_raise", False, "no exception")
    except MathMLError:
        check("U25_on_error_raise", True)


def U26_text_run_is_detexed():
    sp = LatexSpeaker(NullSpeechBackend())
    out = sp.speak(r"\emph{hello} \& goodbye", strip_preamble=False)
    check("U26_text_run_is_detexed",
          "hello" in out and "emph" not in out, repr(out))


# ==========================================================================
# I -- integration with Speech Rule Engine
# ==========================================================================

def _sre_available():
    return os.path.isfile(os.path.join(SRE_DIR, "sre_bridge.js")) and \
           os.path.isdir(os.path.join(SRE_DIR, "node_modules", "speech-rule-engine"))


def I01_sre_clearspeak_fraction(be):
    out = be.speak(latex_to_mathml(r"\frac{a}{b}"))
    check("I01_sre_clearspeak_fraction", out.strip() == "a over b", repr(out))


def I02_sre_clearspeak_sqrt(be):
    out = be.speak(latex_to_mathml(r"\sqrt{x^2+1}"))
    check("I02_sre_clearspeak_sqrt",
          "square root" in out and "squared" in out, repr(out))


def I03_sre_process_is_reused(be):
    be.speak(latex_to_mathml("a"))
    pid1 = be._proc.pid
    be.speak(latex_to_mathml("b"))
    check("I03_sre_process_is_reused", be._proc.pid == pid1, "pid changed")


def I04_sre_malformed_mathml_raises(be):
    try:
        be.speak("<math><unclosed>")
        check("I04_sre_malformed_mathml_raises", False, "no exception")
    except SpeechError:
        check("I04_sre_malformed_mathml_raises", True)


def I05_sre_survives_after_error(be):
    out = be.speak(latex_to_mathml(r"\frac{a}{b}"))
    check("I05_sre_survives_after_error", out.strip() == "a over b", repr(out))


def I06_sre_mathspeak_brief():
    be = SRESpeechBackend(SRE_DIR, domain="mathspeak", style="brief")
    try:
        out = be.speak(latex_to_mathml(r"\frac{a}{b}"))
        check("I06_sre_mathspeak_brief",
              out.strip() == "StartFrac a Over b EndFrac", repr(out))
    finally:
        be.close()


def I07_sre_nemeth_braille():
    be = SRESpeechBackend(SRE_DIR, locale="nemeth", modality="braille", domain="default")
    try:
        out = be.speak(latex_to_mathml(r"\frac{a}{b}"))
        check("I07_sre_nemeth_braille", out.strip() == "\u2839\u2801\u280c\u2803\u283c", repr(out))
    finally:
        be.close()


def I08_sre_simplespeak_fallback_is_defined():
    d, s = SRESpeechBackend.SIMPLESPEAK_FALLBACK
    be = SRESpeechBackend(SRE_DIR, domain=d, style=s)
    try:
        out = be.speak(latex_to_mathml(r"\frac{a}{b}"))
        check("I08_sre_simplespeak_fallback_is_defined", bool(out.strip()), repr(out))
    finally:
        be.close()


def I09_document_end_to_end(be):
    doc = (r"\documentclass{article}\begin{document}" "\n"
           r"The energy is $E=mc^2$, and" "\n"
           r"\begin{equation}\int_0^1 x\,dx=\frac{1}{2}\label{eq:half}\end{equation}" "\n"
           r"follows." "\n"
           r"\end{document}")
    sp = LatexSpeaker(be)
    out = normalize_whitespace(sp.speak(doc))
    ok = ("E equals m c squared" in out
          and "integral from 0 to 1" in out
          and "label" not in out
          and "follows" in out
          and not sp.errors)
    check("I09_document_end_to_end", ok, repr(out) + " errors=" + repr(sp.errors))


def I10_display_equation_gets_own_line(be):
    sp = LatexSpeaker(be)
    out = sp.speak(r"a \[x=1\] b", strip_preamble=False)
    check("I10_display_equation_gets_own_line",
          "\n" in out and "x equals 1" in out, repr(out))


def I11_align_has_no_equation_numbers(be):
    sp = LatexSpeaker(be)
    out = sp.speak_math(r"\begin{align}a&=b\\c&=d\end{align}", display=True)
    check("I11_align_has_no_equation_numbers",
          "open paren 1 close paren" not in out and "Line 1" in out, repr(out))


def I12_matrix(be):
    out = be.speak(latex_to_mathml(r"\begin{pmatrix}a&b\\c&d\end{pmatrix}"))
    check("I12_matrix", "2 by 2 matrix" in out, repr(out))


def I13_greek_and_operators(be):
    out = be.speak(latex_to_mathml(r"\alpha\le\beta"))
    check("I13_greek_and_operators",
          "alpha" in out and "beta" in out and "less than or equal" in out, repr(out))


def I15_no_empty_from_spacing(be):
    from pdfdrill.la2speech.latex2speech import latex_to_mathml as ltm
    out = be.speak(ltm(r"\int_0^1 x\,dx \qquad y"))
    check("I15_no_empty_from_spacing", "empty" not in out, repr(out))


def I14_unicode_output_is_clean(be):
    out = be.speak(latex_to_mathml(r"\pi\approx 3.14159"))
    check("I14_unicode_output_is_clean",
          "pi" in out and "3.14159" in out and "&#x" not in out, repr(out))


# ==========================================================================
# runner
# ==========================================================================

# ==========================================================================
# U -- projection: macro expansion + identifier protection
# ==========================================================================

def U34_harvest_macros_arity_and_default():
    t = lp.harvest_macros(
        r"\newcommand{\A}[1]{x#1}"
        r"\newcommand{\B}[2][d]{#1#2}"
        r"\renewcommand\C{z}")
    check("U34_harvest_macros_arity_and_default",
          (t.get("A").nargs, t.get("A").body) == (1, "x#1")
          and (t.get("B").nargs, t.get("B").default) == (2, "d")
          and (t.get("C").nargs, t.get("C").body) == (0, "z"),
          repr(t.defs))


def U35_readrecordarray_is_recognised():
    """The form gummi.tex uses; the old _READARRAY regex missed it entirely."""
    check("U35_readrecordarray_is_recognised",
          lp.find_array_macro(r"\readrecordarray{formulas.dat}\FO")
          == ("FO", "formulas.dat"),
          repr(lp.find_array_macro(r"\readrecordarray{formulas.dat}\FO")))


def U36_readarray_and_readdef_still_work():
    check("U36_readarray_and_readdef_still_work",
          lp.find_array_macro(r"\readarray{\data}{\FO}")[0] == "FO"
          and lp.find_array_macro(r"\readdef{f.dat}{\GG}") == ("GG", "f.dat"))


def U37_array_index_is_one_based():
    arr = lp.ArrayRef(macro="FO", entries=("first", "second", "third"))
    check("U37_array_index_is_one_based",
          lp.expand(r"\FO[2]", array=arr) == "second",
          repr(lp.expand(r"\FO[2]", array=arr)))


def U38_array_index_out_of_range_warns():
    arr = lp.ArrayRef(macro="FO", entries=("only",))
    w = []
    out = lp.expand(r"\FO[7]", array=arr, warnings=w)
    check("U38_array_index_out_of_range_warns",
          out == r"\FO[7]" and len(w) == 1, repr((out, w)))


def U39_macro_args_substituted():
    t = lp.harvest_macros(r"\newcommand{\pair}[2]{#1+#2}")
    check("U39_macro_args_substituted",
          lp.expand(r"\pair{a}{b}", t) == "a+b",
          repr(lp.expand(r"\pair{a}{b}", t)))


def U40_optional_arg_default_used():
    t = lp.harvest_macros(r"\newcommand{\p}[2][9]{#1-#2}")
    check("U40_optional_arg_default_used",
          lp.expand(r"\p{b}", t) == "9-b" and lp.expand(r"\p[3]{b}", t) == "3-b",
          repr((lp.expand(r"\p{b}", t), lp.expand(r"\p[3]{b}", t))))


def U41_unknown_macros_pass_through():
    """\\alpha must survive: latex2mathml knows it, this module must not eat it."""
    t = lp.harvest_macros(r"\newcommand{\A}{x}")
    check("U41_unknown_macros_pass_through",
          lp.expand(r"\alpha\A\sum", t) == r"\alpha x\sum",
          repr(lp.expand(r"\alpha\A\sum", t)))


def U42_recursive_definition_terminates():
    t = lp.MacroTable({"a": lp.MacroDef("a", 0, r"\a")})
    w = []
    out = lp.expand(r"\a", t, max_depth=8, warnings=w)
    check("U42_recursive_definition_terminates",
          out == r"\a" and any("depth cap" in x for x in w), repr((out, w)))


def U43_newcommand_body_not_expanded_in_place():
    """A definition is a template, not a use: expanding it destroys the macro."""
    src = r"\newcommand{\E}[1]{\ensuremath{\FO[#1]}}"
    arr = lp.ArrayRef(macro="FO", entries=("one", "two"))
    w = []
    out = lp.expand(src, lp.harvest_macros(src), arr, warnings=w,
                    fix_ensuremath=False)
    check("U43_newcommand_body_not_expanded_in_place",
          out == src and not w, repr((out, w)))


def U44_ensuremath_becomes_math_in_prose_only():
    check("U44_ensuremath_becomes_math_in_prose_only",
          lp.expand(r"see \ensuremath{x}") == "see $x$"
          and lp.expand(r"\begin{equation}\ensuremath{x}\end{equation}")
              == r"\begin{equation}x\end{equation}",
          repr((lp.expand(r"see \ensuremath{x}"),
                lp.expand(r"\begin{equation}\ensuremath{x}\end{equation}"))))


def U45_protect_uppercase_and_lowercase_rules():
    check("U45_protect_uppercase_and_lowercase_rules",
          lp.protect_identifiers(r"AVERAGE_{s \in siblings(c,p)}")
          == r"\text{AVERAGE}_{s \in \text{siblings}(c,p)}",
          repr(lp.protect_identifiers(r"AVERAGE_{s \in siblings(c,p)}")))


def U46_protect_leaves_products_and_macros_alone():
    """xy is a product, dx a differential, \\alpha and \\left macro names."""
    untouched = [r"\alpha\beta", r"\sin x", "dx", "xy", "abc",
                 r"\left( x \right)", r"\text{already}"]
    bad = [s for s in untouched if lp.protect_identifiers(s) != s]
    check("U46_protect_leaves_products_and_macros_alone", not bad, repr(bad))


def U47_protect_splits_on_non_letters():
    check("U47_protect_splits_on_non_letters",
          lp.protect_identifiers(r"TF\cdot IDF") == r"\text{TF}\cdot \text{IDF}",
          repr(lp.protect_identifiers(r"TF\cdot IDF")))


def U48_not_identifier_exclusion():
    check("U48_not_identifier_exclusion",
          lp.protect_identifiers("AB + CD", exclude={"AB"}) == r"AB + \text{CD}",
          repr(lp.protect_identifiers("AB + CD", exclude={"AB"})))


def U49_gummi_document_fully_expands():
    """End-to-end on the real document: no \\FO survives outside its definition."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gummi.tex")
    if not os.path.exists(path):
        skip("U49_gummi_document_fully_expands", "gummi.tex not present")
        return
    src = open(path, encoding="utf-8").read()
    w = []
    out = lp.expand(src, lp.harvest_macros(src), lp.resolve_array(src), warnings=w)
    body = out[out.index(r"\begin{document}"):]
    check("U49_gummi_document_fully_expands",
          r"\FO" not in body and r"\Expr" not in body
          and r"\EqExpr" not in body and not w,
          repr((body[:120], w)))


def U77_dollar_inside_text_is_split_not_stripped():
    """A `$` inside `\\text{}` RE-ENTERS math in real LaTeX. latex2mathml emits
    it literally, so `\\text{at $\\Lambda$ rest}` was spoken as "at dollar
    backslash Lambda dollar rest". Stripping the `$` is equally wrong -- it
    leaves \\Lambda in prose, where it renders as a literal backslash."""
    from pdfdrill.la2speech.latex2speech import split_text_math
    got = split_text_math(r"\text{at $\Lambda$ rest}")
    check("U77_dollar_inside_text_is_split_not_stripped",
          got == r"\text{at }\Lambda\text{ rest}", repr(got))


def U78_text_split_handles_edges():
    from pdfdrill.la2speech.latex2speech import split_text_math
    cases = {
        r"\text{$X$}": "X",                                   # nothing but math
        r"\text{plain}": r"\text{plain}",                     # untouched
        r"a \text{u $b_1$ v $c$ w} z": r"a \text{u }b_1\text{ v }c\text{ w} z",
        r"\text{unbalanced $x}": r"\text{unbalanced $x}",     # odd count: leave
        r"\text{cost \$5}": r"\text{cost \$5}",              # escaped dollar
    }
    bad = {k: split_text_math(k) for k, v in cases.items()
           if split_text_math(k) != v}
    check("U78_text_split_handles_edges", not bad, repr(bad))


def U79_clean_math_applies_the_text_split():
    """It must run inside clean_math, not just be available."""
    out = clean_math(r"\text{at $\Lambda$ rest}")
    check("U79_clean_math_applies_the_text_split",
          "$" not in out and r"\Lambda" in out, repr(out))


def U80_multiletter_style_alphabet_becomes_text():
    """latex2mathml emits ONE <mi> PER LETTER for every \\math* command, so a
    multi-letter run is spelled out -- and for \\mathrm each upright letter is
    matched against SRE's SI unit tables, turning \\mathrm{mult} into
    "meters normal u liters tons" (m->meter, l->liter, t->ton)."""
    from pdfdrill.la2speech.latex2speech import normalize_alphabet_runs as n
    check("U80_multiletter_style_alphabet_becomes_text",
          n(r"\mathrm{mult}(x)") == r"\text{mult}(x)"
          and n(r"\mathbf{mult}") == r"\text{mult}"
          and n(r"\mathit{ker}") == r"\text{ker}",
          repr(n(r"\mathrm{mult}(x)")))


def U81_single_letters_and_semantic_alphabets_are_kept():
    """A single letter carries real meaning: \\mathrm{m} in a quantity IS the
    unit metre and \\mathbf{v} IS a vector. And \\mathbb/\\mathfrak encode
    meaning in the VARIANT -- \\mathbb{R} speaks as "the real numbers"."""
    from pdfdrill.la2speech.latex2speech import normalize_alphabet_runs as n
    keep = [r"\mathrm{m}", r"\mathbf{v}", r"\mathbb{R}", r"\mathfrak{g}",
            r"\mathcal{L}", r"\mathbb{RR}", r"\mathfrak{sl}"]
    bad = [k for k in keep if n(k) != k]
    check("U81_single_letters_and_semantic_alphabets_are_kept", not bad, repr(bad))


def U82_clean_math_applies_the_alphabet_rewrite():
    out = clean_math(r"\mathrm{mult}(x)")
    check("U82_clean_math_applies_the_alphabet_rewrite",
          out == r"\text{mult}(x)", repr(out))


# ==========================================================================
# U -- tiddler docmodel projection / import
# ==========================================================================

def U50_harvest_spans_the_whole_docmodel():
    """Definitions live in one tiddler and uses in another."""
    model = [{"title": "Preamble", "text": r"\newcommand{\Q}[1]{q_{#1}}"},
             {"title": "Body", "text": r"see $\Q{3}$"}]
    table, _ = tp.harvest_docmodel(model)
    check("U50_harvest_spans_the_whole_docmodel",
          "Q" in table and lp.expand(r"\Q{3}", table) == "q_{3}",
          repr(table.defs))


def U51_transclusion_inline_pulls_latex():
    idx = {"FO/2": {"title": "FO/2", "latex": "R_{12}"}}
    check("U51_transclusion_inline_pulls_latex",
          tp.resolve_transclusions("a {{FO/2}} b", idx, "inline", "speech")
          == "a $R_{12}$ b",
          repr(tp.resolve_transclusions("a {{FO/2}} b", idx, "inline", "speech")))


def U52_transclusion_cached_pulls_speech_field():
    idx = {"FO/2": {"title": "FO/2", "latex": "R_{12}", "speech": "R sub 12"}}
    check("U52_transclusion_cached_pulls_speech_field",
          tp.resolve_transclusions("a {{FO/2}} b", idx, "cached", "speech")
          == "a R sub 12 b",
          repr(tp.resolve_transclusions("a {{FO/2}} b", idx, "cached", "speech")))


def U53_cached_falls_back_to_latex_and_warns():
    idx = {"FO/2": {"title": "FO/2", "latex": "R_{12}"}}
    w = []
    out = tp.resolve_transclusions("{{FO/2}}", idx, "cached", "speech", w)
    check("U53_cached_falls_back_to_latex_and_warns",
          out == "$R_{12}$" and len(w) == 1, repr((out, w)))


def U54_missing_target_warns_not_raises():
    w = []
    out = tp.resolve_transclusions("{{Nope}}", {}, "inline", "speech", w)
    check("U54_missing_target_warns_not_raises",
          out == "" and "Nope" in w[0], repr((out, w)))


def U55_explicit_field_reference():
    idx = {"FO/2": {"title": "FO/2", "latex": "R_{12}", "speech": "R sub 12"}}
    check("U55_explicit_field_reference",
          tp.resolve_transclusions("{{FO/2!!latex}}", idx, "cached", "speech")
          == "R_{12}")


def U56_hybrid_marker_parsed():
    macro, kv = tp.parse_hybrid(r'FO, latex="E=mc^{2}", speech="energy"')
    check("U56_hybrid_marker_parsed",
          macro == "FO" and kv["latex"] == "E=mc^{2}" and kv["speech"] == "energy",
          repr((macro, kv)))


def U57_hybrid_prefers_embedded_speech():
    src = r'x {{k||FO, latex="E=mc^{2}", speech="energy"}} y'
    check("U57_hybrid_prefers_embedded_speech",
          tp.resolve_transclusions(src, {}, "hybrid", "speech") == "x energy y",
          repr(tp.resolve_transclusions(src, {}, "hybrid", "speech")))


def U58_hybrid_without_speech_falls_back_to_latex():
    src = r'{{k||FO, latex="E=mc^{2}"}}'
    check("U58_hybrid_without_speech_falls_back_to_latex",
          tp.resolve_transclusions(src, {}, "hybrid", "speech") == "$E=mc^{2}$",
          repr(tp.resolve_transclusions(src, {}, "hybrid", "speech")))


def U59_speak_tiddlers_merges_into_source_object():
    model = [{"title": "P", "text": r"let $x$ be", "kind": "text"}]
    sp = LatexSpeaker(NullSpeechBackend())
    tp.speak_tiddlers(model, sp)
    check("U59_speak_tiddlers_merges_into_source_object",
          len(model) == 1 and model[0]["title"] == "P"
          and "speech" in model[0] and "text" in model[0], repr(model))


def U60_bad_mode_rejected():
    try:
        tp.speak_tiddlers([], LatexSpeaker(NullSpeechBackend()), mode="nope")
        check("U60_bad_mode_rejected", False, "no ValueError")
    except ValueError:
        check("U60_bad_mode_rejected", True)


def U68_lone_math_wrapper_stripped_in_every_form():
    """$..$, $$..$$, \\[..\\], \\(..\\) and \\begin{env}..\\end{env} all count."""
    idx = {"F": {"title": "F", "latex": "R_{12}", "speech": "R sub 12"}}
    forms = ["{{F}}", r"$ {{F}} $", r"$$ {{F}} $$", r"\[ {{F}} \]", r"\( {{F}} \)",
             r"\begin{equation}{{F}}\end{equation}"]
    got = [tp.resolve_transclusions(f, idx, "cached", "speech") for f in forms]
    check("U68_lone_math_wrapper_stripped_in_every_form",
          all(g.strip() == "R sub 12" for g in got), repr(got))


def U69_reference_among_operands_falls_back_to_latex():
    """Spoken English is not a valid operand; cached must not splice it in."""
    idx = {"F": {"title": "F", "latex": "R_{12}", "speech": "R sub 12"}}
    got = tp.resolve_transclusions(
        r"\begin{equation}{{F}} + x\end{equation}", idx, "cached", "speech")
    check("U69_reference_among_operands_falls_back_to_latex",
          "R_{12}" in got and "R sub 12" not in got and "$" not in got, repr(got))


def U70_prose_reference_still_uses_speech():
    idx = {"F": {"title": "F", "latex": "R_{12}", "speech": "R sub 12"}}
    check("U70_prose_reference_still_uses_speech",
          tp.resolve_transclusions("Wert {{F}} folgt.", idx, "cached", "speech")
          == "Wert R sub 12 folgt.")


def U75_math_tiddler_recognised_by_real_conventions():
    """Real pdfdrill output tags formulas `formula` and has no `kind` field;
    keying off kind == "math" matched nothing in the whole corpus."""
    latex_only = {"title": "X_FO0001", "latex": "R_{12}", "tags": "formula X"}
    tagged = {"title": "Y", "tags": "formula", "text": "<$latex/>"}
    kinded = {"title": "Z", "kind": "math", "latex": "x"}
    prose = {"title": "P", "tags": "paragraph", "text": "Hallo"}
    got = [tp.is_math_tiddler(t) for t in (latex_only, tagged, kinded, prose)]
    check("U75_math_tiddler_recognised_by_real_conventions",
          got == [True, True, True, False], repr(got))


def U76_math_source_prefers_latex_over_widget_text():
    """`text` holds `<$latex text={{!!latex}}/>`; the `$` opens math mode and the
    widget markup gets spoken. The formula lives in `latex`."""
    t = {"title": "F", "latex": "R_{12}",
         "text": "<$latex text={{!!latex}} displayMode={{!!displayMode}}/>"}
    inline = tp.math_source(t)
    disp = tp.math_source({**t, "displayMode": "true"})
    check("U76_math_source_prefers_latex_over_widget_text",
          inline == "$R_{12}$" and disp == "$$R_{12}$$"
          and tp.math_source({"title": "n"}) == "",
          repr((inline, disp)))


# ==========================================================================
# U -- named projections
# ==========================================================================

def U61_projections_are_registered_by_name():
    check("U61_projections_are_registered_by_name",
          pj.names() == ["docmodel", "latex", "speech", "text"], repr(pj.names()))


def U62_unknown_projection_names_the_known_ones():
    try:
        pj.get("nope")
        check("U62_unknown_projection_names_the_known_ones", False, "no KeyError")
    except KeyError as exc:
        check("U62_unknown_projection_names_the_known_ones",
              "docmodel" in str(exc) and "nope" in str(exc), str(exc))


def U63_projection_declares_reads_and_writes():
    p = pj.get("docmodel")
    check("U63_projection_declares_reads_and_writes",
          p.reads == ".tex" and "tiddler" in p.writes and callable(p.run),
          repr((p.reads, p.writes)))


def U64_docmodel_makes_one_tiddler_per_array_entry():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gummi.tex")
    if not os.path.exists(path):
        skip("U64_docmodel_makes_one_tiddler_per_array_entry", "gummi.tex absent")
        return
    t = pj.project_docmodel(open(path, encoding="utf-8").read())
    math = [x for x in t if x["kind"] == "math"]
    check("U64_docmodel_makes_one_tiddler_per_array_entry",
          len(math) == 11 and math[1] == {"title": "FO/2", "latex": "R_{12}",
                                          "kind": "math"},
          repr(math[:2]))


def U65_docmodel_rewrites_uses_as_transclusions():
    """\FO[n], \Expr{n} and \EqExpr{n} must all become {{FO/n}}, in order."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gummi.tex")
    if not os.path.exists(path):
        skip("U65_docmodel_rewrites_uses_as_transclusions", "gummi.tex absent")
        return
    t = pj.project_docmodel(open(path, encoding="utf-8").read())
    body = " ".join(x.get("text", "") for x in t)
    import re as _re
    check("U65_docmodel_rewrites_uses_as_transclusions",
          _re.findall(r"\{\{FO/(\d+)\}\}", body) == ["2", "5", "4", "1", "2", "5", "4"]
          and "\\FO" not in body,
          repr(_re.findall(r"\{\{FO/(\d+)\}\}", body)))


def U66_docmodel_drops_math_scaffolding_around_a_lone_reference():
    """Left in place, a cached transclusion would be re-spoken as letters."""
    src = (r"\begin{filecontents*}{f.dat}" "\nR_{12}\n"
           r"\end{filecontents*}" "\n"
           r"\readrecordarray{f.dat}\FO" "\n"
           r"\begin{document}" "\n\n"
           r"\begin{equation}\ensuremath{\FO[1]}\end{equation}" "\n\n"
           r"\end{document}")
    t = pj.project_docmodel(src)
    body = [x for x in t if x["kind"] == "text"]
    check("U66_docmodel_drops_math_scaffolding_around_a_lone_reference",
          any(x["text"] == "{{FO/1}}" and x.get("display") for x in body),
          repr([x.get("text") for x in body]))


def U67_latex_projection_expands_and_protects():
    out = pj.project_latex(r"\newcommand{\A}{AVERAGE}$\A_{s}$")
    check("U67_latex_projection_expands_and_protects",
          r"\text{AVERAGE}" in out and r"\A_" not in out, repr(out))


def U71_text_projection_skips_math_tiddlers():
    """Math tiddlers are transcluded into their bodies; emitting them too would
    say every formula twice."""
    model = [{"title": "F", "kind": "math", "speech": "R sub 12"},
             {"title": "P1", "kind": "text", "speech": "Wert R sub 12 folgt."},
             {"title": "P2", "kind": "text", "speech": "Ende."}]
    check("U71_text_projection_skips_math_tiddlers",
          pj.project_text(model) == "Wert R sub 12 folgt.\n\nEnde.",
          repr(pj.project_text(model)))


def U72_text_projection_drops_unspoken_tiddlers():
    model = [{"title": "A", "kind": "text", "speech": "one"},
             {"title": "B", "kind": "text"},
             {"title": "C", "kind": "text", "speech": "   "}]
    check("U72_text_projection_drops_unspoken_tiddlers",
          pj.project_text(model) == "one", repr(pj.project_text(model)))


def U73_display_math_splits_without_blank_lines():
    """gummi.tex has no blank line before its first equation."""
    src = (r"\begin{document}" "\n"
           r"Vorher $$a=b$$" "\n"
           r"\begin{equation}c=d\end{equation}" "\n"
           r"Nachher." "\n"
           r"\end{document}")
    body = [t for t in pj.project_docmodel(src) if t["kind"] == "text"]
    kinds = [(t["text"].strip()[:12], t.get("display", False)) for t in body]
    check("U73_display_math_splits_without_blank_lines",
          len(body) == 4
          and kinds[0] == ("Vorher", False) and kinds[1][1] is True
          and kinds[2][1] is True and kinds[3] == ("Nachher.", False),
          repr(kinds))


def U74_inline_reference_alone_is_not_display():
    """\\Expr is defined with \\ensuremath: inline even on its own line."""
    src = (r"\begin{filecontents*}{f.dat}" "\nR_{12}\n"
           r"\end{filecontents*}" "\n"
           r"\readrecordarray{f.dat}\FO" "\n"
           r"\newcommand{\Expr}[1]{\ensuremath{\FO[#1]}}" "\n"
           r"\begin{document}" "\n\n" r"\Expr{1}" "\n\n"
           r"\begin{equation}\Expr{1}\end{equation}" "\n\n"
           r"\end{document}")
    body = [t for t in pj.project_docmodel(src) if t["kind"] == "text"]
    check("U74_inline_reference_alone_is_not_display",
          [t.get("display", False) for t in body] == [False, True]
          and all(t["text"] == "{{FO/1}}" for t in body), repr(body))


# ==========================================================================
# I -- projection through the real engine
# ==========================================================================

def I16_identifier_protection_is_spoken_as_a_word(be):
    sp = LatexSpeaker(be)
    got = sp.speak_math(r"AVERAGE_{s \in siblings(c,p)}")
    check("I16_identifier_protection_is_spoken_as_a_word",
          got.startswith("AVERAGE sub s is a member of the siblings of"), repr(got))


def I17_protection_off_still_spells(be):
    sp = LatexSpeaker(be, protect_identifiers=False)
    got = sp.speak_math(r"AVERAGE_{s}")
    check("I17_protection_off_still_spells", got.startswith("A V E R A G"), repr(got))


def I18_gummi_transclusions_are_spoken(be):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gummi.tex")
    if not os.path.exists(path):
        skip("I18_gummi_transclusions_are_spoken", "gummi.tex not present")
        return
    sp = LatexSpeaker(be)
    got = sp.speak(open(path, encoding="utf-8").read())
    check("I18_gummi_transclusions_are_spoken",
          "backslash FO" not in got and "dollar" not in got
          and "R sub 12" in got and "x sub 5" in got, repr(got[-260:]))


def I19_cached_mode_reuses_speech(be):
    """All modes must agree on the text; cached must cost fewer engine calls."""
    import copy
    model = [{"title": "FO/2", "latex": "R_{12}", "kind": "math"},
             {"title": "P1", "text": "a {{FO/2}} b", "kind": "text"},
             {"title": "P2", "text": "c {{FO/2}} d", "kind": "text"}]
    a, b = copy.deepcopy(model), copy.deepcopy(model)
    sa = tp.speak_tiddlers(a, LatexSpeaker(be), mode="inline")
    sb = tp.speak_tiddlers(b, LatexSpeaker(be), mode="cached")
    same = [x["speech"] for x in a] == [x["speech"] for x in b]
    check("I19_cached_mode_reuses_speech",
          same and sb["calls"] < sa["calls"],
          repr((sa["calls"], sb["calls"], [x.get("speech") for x in a],
                [x.get("speech") for x in b])))


def I20_cached_transclusion_is_never_spelled_out(be):
    """Regression: cached speech re-entering math came out "R s u b 12"."""
    import re as _re
    spelled = _re.compile(r"\b[a-z](?: [a-z]){2,}\b")
    forms = ["{{F}}", r"\[ {{F}} \]", r"$ {{F}} $",
             r"\begin{equation}{{F}} + x\end{equation}", "Wert {{F}} folgt."]
    bad = []
    for body in forms:
        model = [{"title": "F", "latex": "R_{12}", "kind": "math"},
                 {"title": "P", "text": body, "kind": "text"}]
        tp.speak_tiddlers(model, LatexSpeaker(be), mode="cached")
        if spelled.search(model[-1]["speech"]):
            bad.append((body, model[-1]["speech"]))
    check("I20_cached_transclusion_is_never_spelled_out", not bad, repr(bad))


def main():
    print("=" * 70)
    print("UNIT TESTS (no node required)")
    print("=" * 70)
    for fn in [U01_segment_inline_dollar, U02_segment_display_dollar,
               U03_segment_paren_and_bracket, U04_segment_math_environment,
               U05_segment_escaped_dollar_is_text, U06_segment_comment_stripped,
               U07_segment_escaped_percent_kept, U08_segment_verbatim_not_scanned,
               U09_segment_preamble_stripped, U10_segment_preamble_kept_when_asked,
               U11_segment_unterminated_dollar_is_text, U12_segment_multiple_inline,
               U13_segment_text_lossless, U14_clean_math_drops_label,
               U15_clean_math_drops_nonumber, U16_clean_math_starifies_align,
               U17_clean_math_leaves_starred_alone, U18_latex_to_mathml_basic,
               U19_latex_to_mathml_display_attr, U20_latex_to_mathml_empty_raises,
               U21_normalize_whitespace_keeps_paragraphs, U22_null_backend_document,
               U23_on_error_placeholder, U24_on_error_raw, U25_on_error_raise,
               U26_text_run_is_detexed, U27_segment_verb_inline,
               U28_verbatim_survives_to_output, U29_verbatim_skip_mode,
               U30_verbatim_announce_mode, U31_section_sign_is_spoken,
               U32_nbsp_becomes_space, U33_mspace_is_stripped,
               U34_harvest_macros_arity_and_default,
               U35_readrecordarray_is_recognised,
               U36_readarray_and_readdef_still_work,
               U37_array_index_is_one_based,
               U38_array_index_out_of_range_warns,
               U39_macro_args_substituted, U40_optional_arg_default_used,
               U41_unknown_macros_pass_through,
               U42_recursive_definition_terminates,
               U43_newcommand_body_not_expanded_in_place,
               U44_ensuremath_becomes_math_in_prose_only,
               U45_protect_uppercase_and_lowercase_rules,
               U46_protect_leaves_products_and_macros_alone,
               U47_protect_splits_on_non_letters,
               U48_not_identifier_exclusion,
               U49_gummi_document_fully_expands,
               U50_harvest_spans_the_whole_docmodel,
               U51_transclusion_inline_pulls_latex,
               U52_transclusion_cached_pulls_speech_field,
               U53_cached_falls_back_to_latex_and_warns,
               U54_missing_target_warns_not_raises,
               U55_explicit_field_reference, U56_hybrid_marker_parsed,
               U57_hybrid_prefers_embedded_speech,
               U58_hybrid_without_speech_falls_back_to_latex,
               U59_speak_tiddlers_merges_into_source_object,
               U80_multiletter_style_alphabet_becomes_text,
               U81_single_letters_and_semantic_alphabets_are_kept,
               U82_clean_math_applies_the_alphabet_rewrite,
               U77_dollar_inside_text_is_split_not_stripped,
               U78_text_split_handles_edges,
               U79_clean_math_applies_the_text_split,
               U60_bad_mode_rejected, U61_projections_are_registered_by_name,
               U62_unknown_projection_names_the_known_ones,
               U63_projection_declares_reads_and_writes,
               U64_docmodel_makes_one_tiddler_per_array_entry,
               U65_docmodel_rewrites_uses_as_transclusions,
               U66_docmodel_drops_math_scaffolding_around_a_lone_reference,
               U67_latex_projection_expands_and_protects,
               U68_lone_math_wrapper_stripped_in_every_form,
               U69_reference_among_operands_falls_back_to_latex,
               U70_prose_reference_still_uses_speech,
               U71_text_projection_skips_math_tiddlers,
               U72_text_projection_drops_unspoken_tiddlers,
               U73_display_math_splits_without_blank_lines,
               U74_inline_reference_alone_is_not_display,
               U75_math_tiddler_recognised_by_real_conventions,
               U76_math_source_prefers_latex_over_widget_text]:
        try:
            fn()
        except Exception as exc:
            check(fn.__name__, False, f"EXCEPTION {type(exc).__name__}: {exc}")

    print()
    print("=" * 70)
    print("INTEGRATION TESTS (Speech Rule Engine)")
    print("=" * 70)
    if not _sre_available():
        for n in ["I01_sre_clearspeak_fraction", "I02_sre_clearspeak_sqrt",
                  "I03_sre_process_is_reused", "I04_sre_malformed_mathml_raises",
                  "I05_sre_survives_after_error", "I06_sre_mathspeak_brief",
                  "I07_sre_nemeth_braille", "I08_sre_simplespeak_fallback_is_defined",
                  "I09_document_end_to_end", "I10_display_equation_gets_own_line",
                  "I11_align_has_no_equation_numbers", "I12_matrix",
                  "I13_greek_and_operators", "I14_unicode_output_is_clean",
                  "I16_identifier_protection_is_spoken_as_a_word",
                  "I17_protection_off_still_spells",
                  "I18_gummi_transclusions_are_spoken",
                  "I19_cached_mode_reuses_speech",
                  "I20_cached_transclusion_is_never_spelled_out"]:
            skip(n, f"SRE not found at {SRE_DIR}")
    else:
        be = SRESpeechBackend(SRE_DIR, domain="clearspeak")
        try:
            for fn in [I01_sre_clearspeak_fraction, I02_sre_clearspeak_sqrt,
                       I03_sre_process_is_reused, I04_sre_malformed_mathml_raises,
                       I05_sre_survives_after_error, I09_document_end_to_end,
                       I10_display_equation_gets_own_line,
                       I11_align_has_no_equation_numbers, I12_matrix,
                       I13_greek_and_operators, I14_unicode_output_is_clean,
                       I15_no_empty_from_spacing,
                       I16_identifier_protection_is_spoken_as_a_word,
                       I17_protection_off_still_spells,
                       I18_gummi_transclusions_are_spoken,
                       I19_cached_mode_reuses_speech,
                       I20_cached_transclusion_is_never_spelled_out]:
                try:
                    fn(be)
                except Exception as exc:
                    check(fn.__name__, False, f"EXCEPTION {type(exc).__name__}: {exc}")
        finally:
            be.close()
        for fn in [I06_sre_mathspeak_brief, I07_sre_nemeth_braille,
                   I08_sre_simplespeak_fallback_is_defined]:
            try:
                fn()
            except Exception as exc:
                check(fn.__name__, False, f"EXCEPTION {type(exc).__name__}: {exc}")

    print()
    print("=" * 70)
    p = sum(1 for _, r, _ in RESULTS if r is True)
    f = sum(1 for _, r, _ in RESULTS if r is False)
    s = sum(1 for _, r, _ in RESULTS if r is None)
    print(f"PASSED {p}   FAILED {f}   SKIPPED {s}")
    if f:
        print("\nfailures:")
        for n, r, d in RESULTS:
            if r is False:
                print(f"  {n}: {d}")
    return 1 if f else 0


if __name__ == "__main__":
    raise SystemExit(main())
