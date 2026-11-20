"""The documented test command must RUN on the documented install.

    bash bootstrap.sh && pip install -e .
    PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q -p no:cacheprovider

An auditing session (finding C) ran exactly that and got `exit 2` at
COLLECTION: four `tests/scandrill/*.py` files imported `pikepdf`/`img2pdf` at
module level, so the WHOLE suite refused to start. Worse, every suite number
quoted here until then — 5,765 and friends — had come from a fully-equipped
development machine and had never been measured on the install the README
documents.

Fixing the four collection errors exposed the rest of the same class: 24 tests
that FAILED for a missing optional extra instead of skipping. A failure and an
absent extra look identical in a summary line, so a base install could not tell
a broken build from an unconfigured one.

This file is the gate. It is deliberately static — it cannot run the suite
twice — and it checks the one property that caused both halves: a test that
touches a module the base install does not ship must say so itself.

MEASURED, not assumed: `BASE_PROVIDES` is what `pip list` reports inside a
fresh venv after `pip install -r requirements.txt && pip install -e .` (2026-10-21).
`pillow` and `pyyaml` are in an extra AND arrive anyway — pillow through
pdfplumber, PyYAML as a base dependency — so a test may import them freely.
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Import names a base install HAS, whatever an extra also claims.
BASE_PROVIDES = frozenset({
    "numpy", "PIL", "yaml", "pdfminer", "pdfplumber", "pydantic", "pypdf",
    "pypdfium2", "cryptography", "charset_normalizer", "pytest",
})

#: Import names a base install does NOT have. From pyproject's
#: `optional-dependencies` minus BASE_PROVIDES, plus the three detector packages
#: that live in a separate interpreter entirely (PDFDRILL_YOLO_PYTHON).
EXTRA_ONLY = frozenset({
    "blake3", "cv2", "dateparser", "doclayout_yolo", "email_validator",
    "enchant", "img2pdf", "langdetect", "latex2mathml",
    "latex2sympy2_extended", "lingua", "networkx", "onnxruntime",
    "phonenumbers", "pikepdf", "price_parser", "probablepeople", "pylatexenc",
    "pyvips", "rapidfuzz", "scipy", "spylls", "stanza", "sympy", "torch",
    "ultralytics", "usaddress", "zxingcpp",
})


def _guards(text: str) -> set:
    """Module names this file declares it may do without."""
    return (set(re.findall(r'importorskip\(\s*["\']([\w.]+)', text))
            | set(re.findall(r'find_spec\(\s*["\']([\w.]+)', text))
            | set(re.findall(r'skipif.*?["\']([\w.]+)', text)))


def _guarded_by_try(tree: ast.AST) -> set:
    r"""Module names imported inside a `try` that catches an import failure.

    This is a DECLARATION, and a stronger one than `importorskip`: the module
    is optional and the code carries a fallback, so on a base install the
    test still RUNS rather than skipping. Neither failure this file exists to
    catch can happen -- it cannot stop collection and it cannot fail as if
    the code were broken.

    Added for `tests/_pagecheck_pinned.py`, which is a pinned copy of the
    board's measuring script and guards `rapidfuzz` exactly this way, with a
    pure-Python Levenshtein beside it. Patching the pin to drop the import
    would make the suite measure something the board does not.
    """
    out: set = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        catches = False
        for h in node.handlers:
            if h.type is None:                      # bare except
                catches = True
                break
            names = ([h.type] if not isinstance(h.type, ast.Tuple)
                     else list(h.type.elts))
            for nm in names:
                if isinstance(nm, ast.Name) and nm.id in (
                        "ImportError", "ModuleNotFoundError", "Exception"):
                    catches = True
        if not catches:
            continue
        for stmt in node.body:
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Import):
                    for a in sub.names:
                        out.add(a.name.split(".")[0])
                elif isinstance(sub, ast.ImportFrom) and sub.module:
                    out.add(sub.module.split(".")[0])
    return out


def _imported(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name.split(".")[0], node.lineno
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module.split(".")[0], node.lineno


def test_no_test_imports_an_extra_it_has_not_declared():
    """THE WHOLE CLASS, in one assertion. At module level this is a COLLECTION
    ERROR that stops the suite; inside a test body it is a FAILURE that looks
    like a defect. Either way the fix is the same sentence: say what you need."""
    offenders = []
    for path in sorted(ROOT.glob("tests/**/*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue                      # a fixture of broken source, not a test
        guarded = _guards(text) | _guarded_by_try(tree)
        for mod, line in _imported(tree):
            if mod in EXTRA_ONLY and mod not in guarded:
                offenders.append(
                    f"{path.relative_to(ROOT)}:{line}: imports {mod!r} with no "
                    f"importorskip/skipif for it")
    assert not offenders, (
        "on the documented install these either stop collection or fail as if "
        "the code were broken:\n  " + "\n  ".join(offenders))


def test_the_extras_list_this_file_checks_is_still_the_real_one():
    """If a new extra is added to pyproject, this gate has to learn about it —
    otherwise it goes on passing while covering less than it says."""
    pj = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"^\[project\.optional-dependencies\](.*?)^\[",
                      pj, re.S | re.M)
    assert block, "no optional-dependencies block in pyproject.toml"
    pkgs = {re.split(r"[<>=!\[;\s]", r, maxsplit=1)[0].strip().lower()
            for r in re.findall(r'"([^"]+)"', block.group(1))}
    pkgs = {p.replace("-", "_") for p in pkgs if p}
    #: pip name -> import name, only where they differ.
    alias = {"pillow": "PIL", "pyyaml": "yaml", "opencv_python_headless": "cv2",
             "opencv_python": "cv2", "pyenchant": "enchant",
             "lingua_language_detector": "lingua", "zxing_cpp": "zxingcpp",
             "beautifulsoup4": "bs4", "python_docx": "docx"}
    imports = {alias.get(p, p) for p in pkgs}
    unknown = imports - EXTRA_ONLY - BASE_PROVIDES
    assert not unknown, (
        "pyproject declares extras this gate does not classify — add each to "
        "EXTRA_ONLY (a base install lacks it) or BASE_PROVIDES (it arrives "
        "anyway, and say how): " + repr(sorted(unknown)))


def test_the_claimed_suite_numbers_name_the_install_they_came_from():
    """The second half of finding C: a count with no install beside it is not a
    measurement. CLAUDE.md documents the test command, so it carries the
    numbers."""
    txt = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "base install" in txt.lower(), (
        "CLAUDE.md does not say which install its suite numbers were measured "
        "on — the numbers quoted here for months came from a machine with "
        "every extra and were never checked against `bootstrap.sh` + "
        "`pip install -e .`")


def test_a_try_except_importerror_counts_as_declaring_it():
    """The guard added for the pinned pagecheck, asserted both ways so the
    gate cannot be loosened by accident."""
    guarded = ast.parse(
        "try:\n    import rapidfuzz\nexcept ImportError:\n    rapidfuzz = None\n")
    assert _guarded_by_try(guarded) == {"rapidfuzz"}

    bare = ast.parse("import rapidfuzz\n")
    assert _guarded_by_try(bare) == set(), \
        "an unguarded import must still be an offence"

    wrong_handler = ast.parse(
        "try:\n    import rapidfuzz\nexcept ValueError:\n    pass\n")
    assert _guarded_by_try(wrong_handler) == set(), \
        "a handler that does not catch an import failure is no guard"

    from_form = ast.parse(
        "try:\n    from rapidfuzz.distance import Levenshtein\n"
        "except ImportError:\n    Levenshtein = None\n")
    assert _guarded_by_try(from_form) == {"rapidfuzz"}


def test_the_pinned_pagecheck_is_what_made_that_guard_necessary():
    """A regression pin on the real file: it imports an extra and guards it."""
    path = ROOT / "tests" / "_pagecheck_pinned.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {m for m, _ in _imported(tree)}
    assert "rapidfuzz" in imported, "the pin no longer imports rapidfuzz"
    assert "rapidfuzz" in _guarded_by_try(tree), \
        "the pin imports rapidfuzz WITHOUT a guard — the base install breaks"
