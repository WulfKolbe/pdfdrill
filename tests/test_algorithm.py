"""086 — algorithm floats and pseudocode bodies become Algorithm objects."""
from docmodel.algorithm import parse_algorithms, to_docobjects

FLOAT = """\\begin{algorithm}
\\caption{Gradient descent}\\label{alg:gd}
\\begin{algorithmic}[1]
\\State $x \\gets 0$
\\For{$i=1$ to $n$}
\\State $x \\gets x - \\eta g$
\\EndFor
\\end{algorithmic}
\\end{algorithm}
"""


def test_a_float_wrapping_a_body_is_ONE_object_not_two():
    """Emitting both would double-count every algorithm in the corpus."""
    got = list(parse_algorithms(FLOAT, "m.tex"))
    assert len(got) == 1
    assert got[0].floated is True and got[0].kind == "algorithm"


def test_caption_and_label_are_taken_from_inside_the_float():
    a = list(parse_algorithms(FLOAT))[0]
    assert a.caption == "Gradient descent" and a.label == "alg:gd"


def test_steps_are_counted_because_a_pseudocode_line_is_a_macro():
    a = list(parse_algorithms(FLOAT))[0]
    assert a.steps == 4          # State, For, State, EndFor


def test_a_bare_algorithmic_body_is_its_own_object():
    src = "\\begin{algorithmic}\n\\State x\n\\end{algorithmic}\n"
    got = list(parse_algorithms(src))
    assert len(got) == 1 and got[0].kind == "algorithmic"
    assert got[0].floated is False and got[0].caption == ""


def test_nested_floats_do_not_end_at_the_first_end():
    src = ("\\begin{algorithm}\n\\caption{outer}\n\\begin{algorithm}\n"
           "\\caption{inner}\n\\end{algorithm}\nTAIL\n\\end{algorithm}\n")
    got = list(parse_algorithms(src))
    assert "TAIL" in got[0].body, got[0].body


def test_unterminated_float_yields_nothing():
    assert list(parse_algorithms("\\begin{algorithm}\n\\caption{x}\n")) == []


def test_objects_are_typed_Algorithm_not_CodeListing():
    o = to_docobjects(parse_algorithms(FLOAT), "kb")[0]
    assert o.type == "Algorithm"
    assert o.props["env"] == "algorithm" and o.props["bibkey"] == "kb"
