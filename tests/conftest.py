"""Make `pytest` and `python3 -m pytest` the same command.

`python3 -m pytest` puts the current directory on `sys.path`; the `pytest`
console script does not. Nothing here noticed, because CLAUDE.md documents the
`-m` form -- but six files in this directory import each other
(`from tests.test_publish_ready import …`, `tests/test_r1_r6_fork.py:89`, the
fork guard below), and under the console script every one of them is a
collection ERROR, not a failure:

    $ pytest tests/test_build_stamp.py -q
    ERROR tests/test_build_stamp.py
    !!!!!! Interrupted: 1 error during collection !!!!!!

Measured in this checkout, 2026-10-26. It is the same shape as the defect
`testpaths` fixes one level up: two commands a reader could reasonably type,
and only one of them works. So the repository root goes on `sys.path` here,
once, for every invocation -- `tests` is then importable as a package whichever
way the suite is started.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# AND `src`, FOR THE SAME REASON ONE LEVEL DOWN: WHICH TREE THE SUITE TESTS.
# 406 of the 535 files here insert `src` themselves; the other 129 import
# whatever is already importable. In the main checkout that is the same code
# either way, so nothing noticed. IN A WORKTREE IT IS NOT. Measured
# 2026-11-04, in worktrees/t-0131-decimal-crop-geometry:
#
#     $ pytest tests/test_geometry_signature.py tests/<a file inserting src>
#     -> imported report_tex.py from the MAIN CHECKOUT's src
#     $ pytest tests/<a file inserting src> tests/test_geometry_signature.py
#     -> imported report_tex.py from THIS WORKTREE's src
#
# Whichever file runs FIRST decides, so which code a worktree's suite measures
# is an accident of alphabetical ordering. A run that tests the tree nobody is
# editing can report 6,321 passed and mean nothing -- the project's own
# recurring failure (the thing that verifies not verifying the thing that
# runs) turned on the suite itself. Inserted once, here, so every invocation
# tests the tree it lives in; `tests/zz_which_pdfdrill_the_suite_tested.py`
# asserts afterwards that it did.
SRC = ROOT / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
