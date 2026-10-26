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
