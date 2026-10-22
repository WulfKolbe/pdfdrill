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
        guarded = _guards(text)
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
