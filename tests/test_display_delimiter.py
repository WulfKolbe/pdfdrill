"""483/485 — float furniture and stray closers, so the delimiter gate can anchor."""
import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import report_tex as rt


# ---- 483: the stray closing brace -----------------------------------------

def test_a_stray_closer_after_the_display_no_longer_blocks_the_strip():
    """mielke EQ0190/EQ0453, both at confidence 1.000. MathPix's lines.json
    reads '\\[\\n…\\n\\]' — the trailing brace is ours."""
    v = r"\[ L_{a b}^{(\star)}:=\frac{1}{2} \varepsilon_{a b c d} L^{c d} . \] }"
    assert rt.renderable(v) == r"L_{a b}^{(\star)}:=\frac{1}{2} \varepsilon_{a b c d} L^{c d} ."


def test_only_UNMATCHED_closers_are_dropped():
    assert rt._drop_stray_closers(r"\frac{1}{2}") == r"\frac{1}{2}"
    assert rt._drop_stray_closers(r"\[ a \] }") == r"\[ a \]"
    assert rt._drop_stray_closers(r"\[ a \] } }") == r"\[ a \]"
    # a closer that IS matched stays, however the value ends
    assert rt._drop_stray_closers(r"\sqrt{x}") == r"\sqrt{x}"


def test_escaped_braces_do_not_count_as_closers():
    assert rt._drop_stray_closers(r"\{ a \}") == r"\{ a \}"


def test_a_value_with_too_FEW_closers_is_left_alone():
    """Unbalanced the other way is a different defect and not this one's."""
    assert rt._drop_stray_closers(r"\frac{1}{2") == r"\frac{1}{2"


# ---- 485: the float furniture ---------------------------------------------

def test_a_caption_between_the_float_and_the_display_is_dropped():
    v = (r"\begin{figure} \captionsetup{labelformat=empty} "
         r"\caption{Table 2. Standard algebraic identities} \[ a=b \]")
    assert rt.renderable(v) == "a=b"


def test_furniture_is_only_furniture_when_a_display_follows():
    """A value that IS a caption is a caption. The guard is the `\\[`."""
    v = r"\caption{just a caption, no display here}"
    assert rt._drop_leading_furniture(v) == v


def test_a_caption_carrying_nested_braces_is_matched_by_counting():
    v = r"\caption{Table \textbf{2}. See \emph{also} {this}} \[ x \]"
    assert rt._drop_leading_furniture(v).strip() == r"\[ x \]"


def test_an_unbalanced_caption_is_left_alone_rather_than_guessed_at():
    v = r"\caption{Table 2. unterminated \[ x \]"
    assert rt._drop_leading_furniture(v) == v


def test_bare_furniture_commands_take_no_argument():
    assert rt._drop_leading_furniture(r"\centering \[ x \]").strip() == r"\[ x \]"
    assert rt._drop_leading_furniture(r"\centering").strip() == r"\centering"


def test_the_two_run_before_the_delimiter_gate_not_after():
    """Both exist so the leading-\\[ / trailing-\\] strip can ANCHOR; running
    them after it would leave the delimiter mid-string and refuse the row."""
    assert rt.renderable(r"\centering \[ y=mx+c \] }") == "y=mx+c"


# ---- what must NOT change --------------------------------------------------

def test_an_ordinary_value_is_untouched():
    assert rt.renderable("x^2 + y^2") == "x^2 + y^2"


def test_a_delimiter_that_is_still_mid_string_is_still_refused():
    """Two displays in one value is a segmentation defect, not this repair's."""
    assert rt.renderable(r"\[ a \] and \[ b \]") == ""


def test_a_balanced_float_is_still_refused_and_is_485s_remaining_work():
    """`\\begin{figure} \\[ … \\] \\caption{…} \\end{figure}` — the furniture is
    TRAILING here and 446's opener rule correctly leaves a balanced
    environment alone. 7 rows corpus-wide; extracting the display from a
    complete float is a different repair."""
    v = r"\begin{figure} \[ a=b \] \caption{c} \end{figure}"
    assert rt.renderable(v) == ""
