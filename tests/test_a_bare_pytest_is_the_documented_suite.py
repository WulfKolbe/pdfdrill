"""`python3 -m pytest` and `python3 -m pytest tests/` must be the same suite.

THE DEFECT. `pyproject.toml` set no `testpaths`, so a bare `pytest` from the
repository root walked the whole tree and collected ONE extra file —
`src/pdfreader/out/test_table.py`, 23 tests — that `pytest tests/` never sees.
Measured in this checkout before the fix:

    python3 -m pytest --collect-only -q           5955 tests
    python3 -m pytest --collect-only -q tests/    5932 tests
    src/pdfreader/out/test_table.py alone           23 tests

5955 - 5932 = 23. Two consequences, and the second is the expensive one:

  * the command a newcomer types and the command CLAUDE.md documents measure
    different things, so a suite number means nothing without the command;
  * that file has no `__init__.py` beside it, so pytest's PREPEND import mode
    puts `src/pdfreader/out` FIRST on `sys.path` for the whole session. From
    that moment `import langdetect` resolves to `out/langdetect.py` — a
    subprocess tool that called `sys.exit(0)` at import — instead of the PyPI
    package, in every test collected after it. A peer session measured 33
    failures from that one path insertion and no two runs agreed, because the
    poisoning depends on collection order. See
    `test_an_optional_engine_never_exits_at_import.py` for that half.

So the fix is two halves, and this file holds the first: the documented path
is PINNED in `pyproject.toml`, and no `test_*.py` lives anywhere else — a
test nobody runs is not a test, so `test_table.py` moved into `tests/` rather
than being left where only a hand-typed command found it.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Directories a tree walk must not descend into. `vendor/.pdfmm-venv` holds an
#: installed numpy and scipy, each with thousands of their own test files.
SKIP_DIRS = {".git", "vendor", "node_modules", "__pycache__", ".venv",
             "build", "dist", ".mypy_cache", ".pytest_cache"}


def _ini_options() -> str:
    """The `[tool.pytest.ini_options]` block of pyproject.toml, or ''."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r"^\[tool\.pytest\.ini_options\]\s*$(.*?)(?=^\[|\Z)",
                  text, re.S | re.M)
    return m.group(1) if m else ""


def test_pyproject_pins_the_documented_test_path():
    """`testpaths` is what makes a bare `pytest` mean `pytest tests/`."""
    block = _ini_options()
    assert block, ("pyproject.toml has no [tool.pytest.ini_options]: a bare "
                   "`pytest` walks the whole tree and collects a different "
                   "suite than the documented `pytest tests/`")
    m = re.search(r"^\s*testpaths\s*=\s*(\[[^\]]*\])", block, re.M)
    assert m, "[tool.pytest.ini_options] sets no testpaths"
    paths = re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))
    assert paths == ["tests"], f"testpaths is {paths}, expected ['tests']"


def test_no_test_file_lives_outside_the_tests_directory():
    """A `test_*.py` anywhere else is either never run or run only by a bare
    `pytest` — and, having no package beside it, puts its own directory on
    `sys.path` for everything collected after it."""
    stray = []
    for p in ROOT.rglob("test_*.py"):
        rel = p.relative_to(ROOT)
        if rel.parts[0] == "tests" or SKIP_DIRS & set(rel.parts):
            continue
        stray.append(str(rel))
    assert not stray, (
        "these are collected by a bare `pytest` and not by `pytest tests/`, "
        "and each puts its own directory first on sys.path: " + ", ".join(sorted(stray)))


def test_a_bare_pytest_collects_nothing_outside_the_tests_directory():
    """The behavioural half: run pytest with NO path argument and `tests/`
    ignored. With `testpaths` pinned there is nothing left to collect; without
    it, the tree walk finds whatever `test_*.py` is lying around.

    Collection only — nothing is executed, and the ignore keeps it to about
    20 ms. `--ignore-glob` and not `--ignore`: measured, `--ignore=tests`
    does not suppress a path that came from `testpaths` and collected all
    5959 anyway, which would have made this test pass for the wrong reason."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "--ignore-glob=tests/*", "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin",
             "HOME": str(Path.home())})
    # 5 = "no tests collected", which is the pass. 0 means it found some.
    assert r.returncode == 5, (
        "a bare `pytest` collected tests from outside tests/ "
        f"(exit {r.returncode}):\n{r.stdout[-2000:]}")


def test_the_table_pipeline_tests_came_along_with_their_helper():
    """`test_table.py` moved into `tests/`, and still reads the module under
    test from where it actually lives (`src/pdfreader/out/eqtable_716.py`) —
    the file used to sit beside it and be loaded by `Path(__file__).parent`."""
    moved = ROOT / "tests" / "test_table.py"
    assert moved.is_file(), "tests/test_table.py is missing"
    text = moved.read_text(encoding="utf-8")
    assert "eqtable_716.py" in text
    assert (ROOT / "src" / "pdfreader" / "out" / "eqtable_716.py").is_file()
    # The helper is loaded by path, so the path has to be the one that exists.
    m = re.search(r"_here\s*=\s*(.+)", text)
    assert m, "test_table.py no longer says where it loads the helper from"
    assert "pdfreader" in m.group(1) and "out" in m.group(1), (
        "test_table.py still loads eqtable_716.py from its own directory: " + m.group(1))
