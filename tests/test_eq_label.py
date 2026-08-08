"""The author's `\\label{}` must land where consumers actually read.

`injectlatex` parses the LaTeX label and stores it — on a `Realization`. Every
consumer reads `obj.props`, so on the thesis 15 real labels
(`JVertausch`, `KorrelationsFunktion`, …) sat in the file reachable by nobody,
while 0 Equation objects had one. Reported by the drillcheck audit round 3; I
had it as "discarded", which was wrong — stored-but-unreachable is a smaller fix.

Named `eq_label`, not `label`: `Reference.props["label"]` is already the
bibliographic alpha label (`[ASV02]`), a different thing with the same name.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.commands import promote_equation_label


class _Obj:
    def __init__(self, **props):
        self.props = dict(props)


def test_a_label_is_promoted_to_the_props_consumers_read():
    o = _Obj(latex="x=y")
    assert promote_equation_label(o, {"label": "eq:fund", "numbered": True}) is True
    assert o.props["eq_label"] == "eq:fund"


def test_an_unlabelled_equation_gains_nothing():
    o = _Obj(latex="x=y")
    assert promote_equation_label(o, {"label": None, "numbered": True}) is False
    assert "eq_label" not in o.props
    assert promote_equation_label(o, {}) is False


def test_an_existing_label_is_not_overwritten():
    """A second `injectlatex` run, or a source whose match drifted, must not
    silently repoint an anchor other objects may already reference."""
    o = _Obj(latex="x=y", eq_label="eq:first")
    assert promote_equation_label(o, {"label": "eq:second"}) is False
    assert o.props["eq_label"] == "eq:first"


def test_it_never_touches_the_bibliographic_label():
    """`Reference.props['label']` means something else entirely."""
    o = _Obj(latex="x=y", label="ASV02")
    promote_equation_label(o, {"label": "eq:fund"})
    assert o.props["label"] == "ASV02"
    assert o.props["eq_label"] == "eq:fund"


def test_injectlatex_promotes_the_label_it_attaches():
    import inspect
    from pdfdrill import commands
    body = inspect.getsource(commands.cmd_injectlatex)
    assert "promote_equation_label" in body
