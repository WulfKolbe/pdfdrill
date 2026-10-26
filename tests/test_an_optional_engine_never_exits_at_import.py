"""An optional engine that is missing must raise, never exit the process.

THE DEFECT, measured by a peer session (2026-10-26) and reproduced here.
`src/pdfreader/out/langdetect.py` is a SUBPROCESS TOOL: `lstlang.py` runs it
under another interpreter because `whats_that_code` wants google-re2, lxml,
pygments, pyrankvote and a tree-sitter binary, none of which belong in this
install. When its import failed it printed `{"__error__": …}` and called
`sys.exit(0)` — correct for a tool speaking JSON over a pipe, and fatal for
anything that merely IMPORTS it. Two facts turned that into 33 failures:

  * the file was named after a PyPI package this project declares in its
    `lang` extra, so once `src/pdfreader/out` reached `sys.path` (which
    `test_table.py`'s collection did — see
    `test_a_bare_pytest_is_the_documented_suite.py`) `import langdetect`
    found the TOOL, not the package;
  * `SystemExit` derives from `BaseException`, not `Exception`, so
    `features.extract_language`'s `except Exception` around
    `from langdetect import …` could not catch it. The guard that exists
    precisely to make a missing engine harmless was stepped over:

        {"__error__": "No module named 'whats_that_code'"}
        ESCAPED the guard: SystemExit: SystemExit(0)

    and `language_of()` — which is documented to ALWAYS answer, falling back
    to stopwords — killed its caller instead.

So three things are asserted here, each of which was false:
  1. no module under `src/` is named after a distribution we declare, so
     nothing of ours can be picked up in place of a real package;
  2. no module under `src/` exits the process because an import failed —
     a tool's refusal belongs in `main()`, under `__main__`;
  3. the language guard holds even when `langdetect` is importable and exits
     at import time, because an engine's absence may not be fatal.
"""
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

#: Distribution name -> the name you `import`. Only the ones that differ.
IMPORT_NAME = {
    "pdfminer.six": "pdfminer", "pillow": "PIL", "pyyaml": "yaml",
    "opencv-python-headless": "cv2", "opencv-python": "cv2",
    "lingua-language-detector": "lingua", "python-dateutil": "dateutil",
    "beautifulsoup4": "bs4", "charset-normalizer": "charset_normalizer",
    "doclayout-yolo": "doclayout_yolo", "email-validator": "email_validator",
    "pyenchant": "enchant", "latex2sympy2-extended": "latex2sympy2_extended",
    "price-parser": "price_parser", "pdf2image": "pdf2image",
}


def _declared_imports() -> set:
    """Every import name pyproject declares, base requirements and extras."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # Comments first: an apostrophe in prose pairs with the next quote and
    # swallows half a list (measured in T-0078's package-data reader).
    text = re.sub(r"#[^\n]*", "", text)
    names = set()
    for raw in re.findall(r'["\']([A-Za-z][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?'
                          r'\s*[<>=!~]=[^"\']*["\']', text):
        dist = raw.strip().lower()
        names.add(IMPORT_NAME.get(dist, dist.replace("-", "_")))
    return names


def _top_level_modules() -> dict:
    """Name -> path for every module under src/ that an `import <name>` could
    reach, i.e. every .py file and every directory, at any depth: a directory
    reaches sys.path the moment pytest or a script puts it there."""
    out = {}
    for p in SRC.rglob("*"):
        if "__pycache__" in p.parts:
            continue
        if p.is_file() and p.suffix == ".py" and p.stem != "__init__":
            out.setdefault(p.stem, p)
        elif p.is_dir():
            out.setdefault(p.name, p)
    return out


def test_no_module_under_src_is_named_after_a_dependency():
    """A file of ours whose name is a package's name is a loaded gun: it fires
    whenever its directory reaches sys.path before site-packages."""
    declared = _declared_imports()
    assert "langdetect" in declared, (
        "the lang extra no longer declares langdetect — this test's premise "
        "is gone, check what it should assert now")
    clashes = sorted(f"{name} ({path.relative_to(ROOT)})"
                     for name, path in _top_level_modules().items()
                     if name in declared)
    assert not clashes, (
        "these shadow a declared dependency once their directory is on "
        "sys.path: " + ", ".join(clashes))


def _module_level_exit_in_an_import_handler(path: Path):
    """Lines where a module-level `try:` around an import ends in a process
    exit. Not a style check: this is the shape that defeats a caller's
    `except Exception`, because `SystemExit` is a `BaseException`."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    bad = []
    for node in tree.body:                         # module level only
        if not isinstance(node, ast.Try):
            continue
        if not any(isinstance(n, (ast.Import, ast.ImportFrom))
                   for n in ast.walk(node) if isinstance(n, ast.AST)):
            continue
        for handler in node.handlers:
            for n in ast.walk(handler):
                if isinstance(n, ast.Raise) and "SystemExit" in ast.dump(n):
                    bad.append(n.lineno)
                if (isinstance(n, ast.Call) and
                        ast.dump(n.func).find("'exit'") >= 0):
                    bad.append(n.lineno)
    return sorted(set(bad))


def test_no_module_under_src_exits_because_an_import_failed():
    """A missing optional engine raises ImportError, which every caller's
    guard already handles. Exiting is not a louder version of that — it is
    uncatchable by anything short of `except BaseException`."""
    offenders = []
    for p in sorted(SRC.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        for line in _module_level_exit_in_an_import_handler(p):
            offenders.append(f"{p.relative_to(ROOT)}:{line}")
    assert not offenders, (
        "these exit the process when an import fails, which no caller's "
        "`except Exception` can catch: " + ", ".join(offenders))


def test_the_code_language_tool_still_speaks_json_over_the_pipe():
    """The rename and the move into `main()` must not change the protocol:
    `lstlang.guess` reads one JSON object from stdout and treats an
    `__error__` key as "no answer", so the tool must still print one."""
    tool = next((p for p in (SRC / "pdfreader" / "out").glob("*.py")
                 if "whats_that_code" in p.read_text(encoding="utf-8",
                                                     errors="replace")), None)
    assert tool is not None, "the code-language tool is gone"
    text = tool.read_text(encoding="utf-8")
    assert "__error__" in text, "the tool no longer reports its own absence"
    assert re.search(r'if __name__ == ["\']__main__["\']', text), (
        f"{tool.name} does its work at import time; a tool's work belongs "
        "in main() under __main__")
    # It runs, with no `whats_that_code` anywhere, and still answers.
    r = subprocess.run([sys.executable, str(tool)], input='{"a": "print(1)"}',
                       capture_output=True, text=True, timeout=120,
                       env={**os.environ, "PYTHONPATH": "",
                            "PYTHONDONTWRITEBYTECODE": "1"})
    assert r.returncode == 0, f"exit {r.returncode}: {r.stderr[-400:]}"
    import json
    out = json.loads(r.stdout or "{}")              # must be ONE json object
    assert isinstance(out, dict)

    # And importing it is harmless — the whole point.
    probe = (f"import importlib.util, sys; "
             f"s = importlib.util.spec_from_file_location('t', {str(tool)!r}); "
             f"m = importlib.util.module_from_spec(s); s.loader.exec_module(m); "
             f"print('imported')")
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0 and "imported" in r.stdout, (
        f"importing {tool.name} exits the importer: "
        f"exit {r.returncode}, {r.stderr[-400:]}")


def test_the_caller_names_a_tool_that_exists():
    """`lstlang.guess` runs the tool by path. A rename that misses this line
    is silent: the subprocess fails, `guess` returns {}, and the language
    stays unknown — which is also what a correct run looks like when the
    interpreter is absent."""
    text = (SRC / "pdfreader" / "out" / "lstlang.py").read_text(encoding="utf-8")
    named = re.findall(r'CODE\s*/\s*["\']out["\']\s*/\s*["\']([^"\']+)["\']', text)
    assert named, "lstlang.py no longer names the tool it runs"
    for name in named:
        assert (SRC / "pdfreader" / "out" / name).is_file(), (
            f"lstlang.py runs src/pdfreader/out/{name}, which does not exist")


def test_the_language_guard_holds_when_langdetect_exits_at_import():
    """THE REGRESSION TEST. `language_of` is documented to always answer. With
    a `langdetect` on the path that exits at import — our own tool was exactly
    that — it must still answer, by falling through to the next engine or the
    stopword heuristic.

    The fake is built here rather than pointed at our tool, because the tool
    has been renamed: what is asserted is the GUARD, not the name."""
    import json
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "langdetect.py").write_text(
            "import json, sys\n"
            "print(json.dumps({'__error__': \"No module named 'whats_that_code'\"}))\n"
            "sys.exit(0)\n", encoding="utf-8")
        probe = (
            "import sys, json\n"
            "sys.path.insert(0, %r)\n"
            "import langdetect  # the exiting shadow, imported on purpose\n"
            % tmp)
        # It must exit BEFORE our code runs, or the premise is not reproduced.
        r = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                           text=True, timeout=120)
        assert "__error__" in r.stdout, (
            "the fake shadow did not even run; this test proves nothing")

        probe = (
            "import sys, json\n"
            "sys.path.insert(0, %r)\n"
            "from features.extract_language import detect_language\n"
            "print(json.dumps(detect_language("
            "'The quick brown fox jumps over the lazy dog and the dog does "
            "not mind it at all, because the fox is a friend of the dog.')))\n"
            % tmp)
        r = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                           text=True, timeout=180)
        assert r.returncode == 0, (
            "a langdetect that exits at import took the caller with it "
            f"(exit {r.returncode}):\n{r.stderr[-1200:]}")
        # Measured before the fix: the exit code is 0 and the LAST LINE is the
        # shadow's own error JSON. `detect_language` never returned, and
        # nothing in the exit status says so — the quiet half of the defect.
        last = (r.stdout.strip().splitlines() or [""])[-1]
        got = json.loads(last or "{}")
        assert "lang" in got, (
            "detect_language did not return: the exiting shadow escaped the "
            f"guard and this is all the process said: {last!r}")
        assert got["lang"] != "und" and got["engine"] != "langdetect", got
