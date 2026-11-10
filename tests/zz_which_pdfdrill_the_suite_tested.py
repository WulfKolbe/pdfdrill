"""Which tree did this suite actually test? Answered, not assumed.

A test file that does not insert its own `src` imports whatever is already
importable. In a WORKTREE that means the suite tests the worktree's code
only because some EARLIER file inserted that path first -- an accident of
alphabetical ordering, not a property of the run. Measured 2026-11-04:
`tests/test_geometry_signature.py` has no path insert, and run first in a
worktree it imports `pdfdrill` from the MAIN CHECKOUT instead, silently;
every assertion in that run then describes a tree nobody is editing.

This file sorts last, so it reports the answer for the run that just
happened rather than trying to fix the ordering. A suite whose result does
not say which code it measured is the project's own recurring failure --
the thing that verifies not verifying the thing that runs -- applied to the
suite itself.
"""
import pathlib


def test_the_suite_tested_the_tree_it_lives_in():
    import pdfdrill.report_tex as rt
    here = pathlib.Path(__file__).resolve().parents[1]
    got = pathlib.Path(rt.__file__).resolve()
    assert str(got).startswith(str(here)), (
        "the suite imported %s, which is NOT under the tree being tested "
        "(%s). Every result in this run describes the other tree." % (got, here))
