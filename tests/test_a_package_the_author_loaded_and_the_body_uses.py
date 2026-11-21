r"""A package comes across only when the author loaded it AND the body uses it.

T-0156. arxiv.2402.03975 emits `\interval` 19 times and `\labelcref` 16, both
undefined because we keep our own preamble. MEASURED on that document's own
projected .tex, two xelatex passes each, a PDF produced in every case:

    baseline                     131
    + \usepackage{interval}      112      -19, no new error class
    + \usepackage{cleveref}      125       -6, and a NEW class appears
    + both                       106

BOTH CONDITIONS ARE REQUIRED. The author's own preamble must load the package
— a bare `\interval` could be anyone's macro, and the author's `\usepackage`
is what says whose it is — and the body this projector just wrote must emit one
of its commands, so the preamble stays what this document needs. Same
body-first order `graphics_preamble` and `_theorem_preamble` already use, for
the same reason: only the body knows what it emitted.

`cleveref` IS DELIBERATELY ABSENT, and that is the finding the table records.
It defines `\labelcref`, taking 46 of the 64 undefined control sequences down
to 27 — and then RUNS, resolving labels the projection does not emit, so
`Missing \endcsname` rises 43 -> 49 and `Extra \endcsname` appears 6 times
where there were none. A package can be installed, load cleanly, and still
make things worse by executing against content we do not have. That is a
different failure from `amsaddr`'s, which needed the author's document class
and cost this very document its PDF when variant B loaded the author's whole
package list. Both are why this is a named table and not a rule over every
`\usepackage` the author wrote.

`cleveref` waits for the `\label`/`\ref` work — the owner's fifth requirement —
not for a preamble line.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

P = pytest.importorskip("docops.projectors.latex_pipeline")
L = pytest.importorskip("docops.projectors.latex")


class _Doc:
    def __init__(self, standalone):
        self.meta = {"latex_preamble": {"standalone": standalone}}


AUTHOR = "\n".join([r"\usepackage{interval}", r"\usepackage{cleveref}",
                    r"\usepackage{amsaddr}"])


def test_it_loads_when_both_conditions_hold():
    got = P.author_package_preamble(_Doc(AUTHOR), r"x \interval{0}{1} y")
    assert got == r"\usepackage{interval}"


def test_it_does_not_load_when_the_body_never_uses_it():
    assert P.author_package_preamble(_Doc(AUTHOR), "plain prose") == ""


def test_it_does_not_load_when_the_author_did_not():
    r"""The author's `\usepackage` is what says whose `\interval` it is."""
    doc = _Doc(r"\usepackage{amsmath}")
    assert P.author_package_preamble(doc, r"x \interval{0}{1}") == ""


def test_a_command_that_merely_starts_the_same_does_not_count():
    r"""`\intervals` is not `\interval`; the lookahead is what separates
    them."""
    got = P.author_package_preamble(_Doc(AUTHOR), r"x \intervalfoo{0} y")
    assert got == ""


def test_cleveref_is_not_in_the_table():
    """Measured: it lowers the undefined count and introduces `Extra
    \\endcsname` x6 by resolving labels the projection does not emit."""
    assert "cleveref" not in P._AUTHOR_PACKAGES
    got = P.author_package_preamble(_Doc(AUTHOR),
                                    r"\labelcref{a} and \interval{0}{1}")
    assert got == r"\usepackage{interval}"
    assert "cleveref" not in got


def test_amsaddr_is_not_in_the_table():
    """It assumes an AMS document class and cost this document its PDF when
    variant B loaded the author's whole package list."""
    assert "amsaddr" not in P._AUTHOR_PACKAGES


def test_a_package_the_default_preamble_already_loads_is_not_repeated():
    r"""A second `\usepackage` with different options is an "Option clash",
    not a no-op."""
    doc = _Doc(r"\usepackage{graphicx}")
    saved = dict(P._AUTHOR_PACKAGES)
    P._AUTHOR_PACKAGES["graphicx"] = (r"\includegraphics",)
    try:
        got = P.author_package_preamble(doc, r"\includegraphics{x.png}")
        assert got == ""
        assert "graphicx" in L._DEFAULT_PREAMBLE
    finally:
        P._AUTHOR_PACKAGES.clear()
        P._AUTHOR_PACKAGES.update(saved)


def test_no_captured_preamble_means_nothing_is_loaded():
    """A model built from a reading has no author preamble at all, and must be
    left exactly as it was."""
    class Bare:
        meta = {}
    assert P.author_package_preamble(Bare(), r"\interval{0}{1}") == ""
    assert P.author_package_preamble(_Doc(""), r"\interval{0}{1}") == ""


def test_the_table_is_one_entry_with_a_measurement_behind_it():
    """A guard against the table growing by assumption: every entry here is
    supposed to carry its own before/after, and the docstring holds them."""
    assert list(P._AUTHOR_PACKAGES) == ["interval"]
    assert P._AUTHOR_PACKAGES["interval"] == (r"\interval",)
