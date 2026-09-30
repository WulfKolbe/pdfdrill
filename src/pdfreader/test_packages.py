"""Tests for deriving a preamble from the symbols actually used."""
import texpackages as T


class TestPackageDerivation:
    """Mathpix emits LaTeX that does not always compile because the training
    data kept the symbol but not the package defining it. Every symbol we emit
    came from a known FONT, so the package is derivable rather than guessed.
    """

    def test_blackboard_bold_needs_amssymb(self):
        assert "amssymb" in T.packages_for(r"$\mathbb{R}^{n}$")

    def test_fraktur_needs_amsfonts(self):
        assert "amsfonts" in T.packages_for(r"$\mathfrak{g}$")

    def test_script_needs_mathrsfs(self):
        assert "mathrsfs" in T.packages_for(r"$\mathscr{F}$")

    def test_plain_maths_needs_nothing(self):
        """A document with no fraktur must not load amsfonts."""
        assert T.packages_for(r"$\alpha + \sum_{i} x_{i}^{2} = \frac{1}{2}$") == []

    def test_amssymb_pulls_in_amsmath(self):
        pkgs = T.packages_for(r"$\mathbb{Z}$")
        assert pkgs.index("amsmath") < pkgs.index("amssymb")

    def test_slanted_relation_is_amssymb(self):
        assert "amssymb" in T.packages_for(r"$a \leqslant b$")

    def test_order_is_stable(self):
        a = T.packages_for(r"$\mathbb{R} \mathfrak{g} \mathscr{F} \text{x}$")
        b = T.packages_for(r"$\text{x} \mathscr{F} \mathfrak{g} \mathbb{R}$")
        assert a == b


class TestUnknownCommandsAreSurfaced:
    """A command with no known package is a warning, not something to ship."""

    def test_a_made_up_command_is_reported(self):
        assert T.unknown_commands(r"$\notarealcommand{x}$") == {"notarealcommand"}

    def test_plain_tex_is_not_reported(self):
        assert T.unknown_commands(r"$\alpha \sum \frac{1}{2} \widehat{x}$") == set()

    def test_document_structure_is_not_reported(self):
        """A warning that fires on `\\section` tells the reader nothing."""
        assert T.unknown_commands(r"\section{X} \label{y} \hfill \TeX") == set()

    def test_packaged_commands_are_not_reported(self):
        assert T.unknown_commands(r"$\mathbb{R} \leqslant \mathfrak{g}$") == set()


class TestPreambleFromAWorkingCorpus:
    """The package set a working Mathpix-output preamble actually needs."""

    def test_alternative_blackboard_bold(self):
        assert "bbm" in T.packages_for(r"$\mathbbm{1}$")

    def test_bold_maths(self):
        assert "bm" in T.packages_for(r"$\bm{v}$")

    def test_extensible_arrows(self):
        assert "extarrows" in T.packages_for(r"$\xlongequal{f}$")

    def test_struck_through_terms(self):
        assert "cancel" in T.packages_for(r"$\cancelto{0}{x}$")

    def test_mathtools_pulls_in_amsmath_and_follows_it(self):
        pkgs = T.packages_for(r"$a \coloneqq b$")
        assert pkgs.index("amsmath") < pkgs.index("mathtools")

    def test_load_order_is_dependency_correct(self):
        pkgs = T.packages_for(
            r"$\mathbb{R} \mathbbm{1} \bm{v} \coloneqq \mathscr{F}$")
        assert pkgs.index("amsmath") < pkgs.index("amssymb")
        assert pkgs.index("amsmath") < pkgs.index("mathtools")


class TestProvideCommands:
    """Four commands no package reliably defines."""

    def test_only_what_is_used_is_defined(self):
        lines = T.provides_for(r"$A \Perp B$")
        assert len(lines) == 1 and r"\Perp" in lines[0]

    def test_nothing_used_nothing_defined(self):
        assert T.provides_for(r"$\alpha + \beta$") == []

    def test_all_four_are_known(self):
        for cmd in ("Perp", "overparen", "oiint", "longdiv"):
            assert cmd in T.PROVIDE, cmd

    def test_they_are_not_reported_as_unknown(self):
        """A command the preamble defines is not a compile risk."""
        assert T.unknown_commands(
            r"$\Perp \oiint \longdiv{a}{b} \overparen{xy}$") == set()

    def test_providecommand_is_inert_if_already_defined(self):
        """Every body must use \\providecommand, never \\newcommand, so the
        line is harmless when the real definition is present."""
        for body in T.PROVIDE.values():
            assert body.startswith(r"\providecommand")


# --- 733: characters the text font does not have ------------------------------
#
# Prose does not go through `texmap`. A glyph the PDF's ToUnicode names is
# written into the `.tex` as itself, and LaTeX only WARNS when the font lacks
# it -- the character vanishes and the document still builds. Three of the 18
# outside documents lost one this way.

def test_declares_only_what_the_font_lacks():
    lines, pkgs, lost = T.unicode_decls("Ω × ü α")
    assert lines == [r"\newunicodechar{α}{\ensuremath{\alpha}}"]
    assert "newunicodechar" in pkgs
    assert lost == []


def test_renderable_measured_not_assumed():
    # Latin Modern has every Greek CAPITAL and no Greek lowercase. Measured;
    # the asymmetry is why the set is a constant and not a rule.
    assert T.renders_in_text("Ω")
    assert not T.renders_in_text("ω")
    for c in "×÷±∑√∞≈→€…":
        assert T.renders_in_text(c), c


def test_untranslatable_is_reported_not_dropped_silently():
    _, _, lost = T.unicode_decls("a ≪ b")
    assert lost == ["≪"]


def test_private_use_is_not_a_character():
    assert T.is_private_use("")
    assert not T.is_private_use("α")
    text, seen = T.strip_private_use("Windkanal")
    assert text == "Windkanal"
    assert seen == [""]
