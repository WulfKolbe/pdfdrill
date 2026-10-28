"""ENGINEERING 2d, as a test: the reader produces lines.json, pdfdrill reads it.

The owner, 2026-10-27: "there should be strict separation between tools that
generate lines.json like data and pdfdrill. Therefore pdf2mmd2, glyphdrill and
Gemma should produce lines.json formated output and not interfere with docmodel
data". Read here as a boundary between packages in this repo.

Both directions are checked, because each fails differently:

* reader -> pdfdrill is how the reader stops being a producer. One import of
  `docmodel` inside `src/streamreader/` and the reader can write a document
  model directly; the rule exists to stop exactly that, and it would still pass
  every other test in this suite.
* pdfdrill -> reader is how the boundary turns into a library call. The reader
  is reached by running it and reading the file it wrote, so the only pdfdrill
  file allowed to name it is the one that launches it.

Imports are read from the AST, not by grepping for the word: `src/streamreader`
is 213 modules and the names involved (`mathpix`, `linetypes`, `compare`) exist
on BOTH sides of the boundary, so a text search answers a different question
than the one asked here.
"""
import ast
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
READER = SRC / "streamreader"

#: Everything on pdfdrill's side of the boundary. `pdfreader` is in the list
#: because it is pdfdrill's own 2026-09-30 absorption of pdf2mmd v1 — a second
#: reader, which this one must not call either.
PDFDRILL_SIDE = frozenset({
    "pdfdrill", "docmodel", "docops", "pdfreader", "semantic", "features",
    "mathlayer", "mathgold", "passes", "vocabnet",
})

#: The one file that may name the reader: its installed front door, which runs
#: `streamreader.cli` and stamps the `source` on what it wrote. It is a module
#: beside the package, not inside it, because every file under
#: `src/streamreader/` is byte-identical to pdf2mmd2@5190249 by test.
MAY_LAUNCH_THE_READER = frozenset({"streamreader_entry.py"})


def _imported_roots(path: Path) -> set:
    """The top-level package name of every import in `path`, however spelled."""
    with warnings.catch_warnings():
        # Parsing every module raises each one's own SyntaxWarning (a `\c` in a
        # docstring). They belong to the files, not to this test, and the suite
        # already reports them where they live.
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".", 1)[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:          # relative: inside its own package
                continue
            if node.module:
                roots.add(node.module.split(".", 1)[0])
    return roots


def _reader_modules():
    return sorted(READER.glob("**/*.py"))


def _src_modules():
    return sorted(p for p in SRC.glob("**/*.py")
                  if READER not in p.parents and p.parent != READER
                  and ".egg-info" not in str(p))


def test_the_reader_imports_nothing_from_pdfdrill():
    offenders = {}
    for p in _reader_modules():
        hit = _imported_roots(p) & PDFDRILL_SIDE
        if hit:
            offenders[str(p.relative_to(ROOT))] = sorted(hit)
    assert not offenders, (
        "the reader reaches into pdfdrill, so it is no longer only a producer "
        f"of lines.json: {offenders}")


def test_only_the_entry_point_names_the_reader():
    offenders = {}
    for p in _src_modules():
        if p.name in MAY_LAUNCH_THE_READER and p.parent == SRC:
            continue
        if "streamreader" in _imported_roots(p):
            offenders[str(p.relative_to(ROOT))] = "imports streamreader"
    assert not offenders, (
        "pdfdrill calls the reader as a library instead of running it and "
        f"reading its lines.json: {offenders}")


def test_the_entry_point_does_launch_the_reader():
    """The allowlist above is only safe while the file it names still exists.

    An allowlist whose entries have gone is how a rule keeps passing after the
    thing it governed was renamed away.
    """
    for name in MAY_LAUNCH_THE_READER:
        p = SRC / name
        assert p.is_file(), f"{name} is in the allowlist but not in src/"
        assert "streamreader" in _imported_roots(p), (
            f"{name} is allowed to launch the reader but does not import it")


def test_the_reader_writes_no_docmodel_artifact():
    """"not interfere with docmodel data", checked against the suffix.

    `.docmodel.json` (and its packed `.docpack`) are pdfdrill's artifacts, and
    all model I/O goes through `docmodel.model_io`. The reader naming either
    would mean it had started writing them without importing anything.
    """
    offenders = [str(p.relative_to(ROOT)) for p in _reader_modules()
                 if ".docmodel.json" in p.read_text(encoding="utf-8")
                 or ".docpack" in p.read_text(encoding="utf-8")]
    assert not offenders, f"the reader names a docmodel artifact: {offenders}"
