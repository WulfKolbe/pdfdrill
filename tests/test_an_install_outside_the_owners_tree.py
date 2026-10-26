"""An install that is not the owner's checkout must load the owner's checkout's
code, config and nothing else — and a default must never silently supply it.

T-0078 (drillgroup), from two findings made the same day:

  * `docmodel/main.py` resolved its module manifest as
    `<docmodel>/../config.json`, which is `src/config.json` in this tree and
    `site-packages/config.json` in a wheel. `src/config.json` sits at the `src/`
    ROOT, outside every package directory, and `[tool.setuptools.package-data]`
    is keyed per package — so no key could ever include it, no wheel ever
    carried it, and a wheel-installed `pdfdrill model` died on a
    `FileNotFoundError` naming a path with `/../` in it. (Measured by the
    pdf2mmd2 session; it fails LOUDLY, which is the one piece of luck here. The
    24 manifest entries that load 19 modules are the file's whole content, so
    the alternative would have been a model built by no module at all.)

  * Three modules defaulted a path to `~/MX/PDFDRILL`. A default that names one
    machine's checkout is not a default: on any other machine it points at
    nothing, and on THIS machine it points at the owner's tree even when the
    code under test is a different clone — so a test of the clone measures the
    owner's tree and passes for the wrong reason.

The rule this file enforces: a path that locates pdfdrill's OWN source, repo
root or manifest is derived from `__file__` — the code that is actually running
— with an environment variable as the only override. `Path.home()` never
appears in that chain.
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


# ---------------------------------------------------------------------------
# The module manifest must travel with the package that reads it.
# ---------------------------------------------------------------------------

def test_the_module_manifest_lives_inside_the_package_that_reads_it():
    assert (SRC / "docmodel" / "config.json").is_file(), (
        "docmodel/config.json is missing: the manifest `docmodel.loader` reads "
        "must be INSIDE the package, because a wheel ships package data and "
        "nothing else")
    assert not (SRC / "config.json").exists(), (
        "src/config.json still exists. It is outside every package directory, "
        "so `[tool.setuptools.package-data]` — which is keyed per package — "
        "cannot ship it; two copies of the manifest is also how the two "
        "disagree later")


def test_package_data_ships_the_module_manifest():
    """A file inside the package still needs a package-data key, or `pip
    install` puts the .py files in site-packages and leaves the .json behind."""
    txt = (ROOT / "pyproject.toml").read_text()
    block = re.search(r"^\[tool\.setuptools\.package-data\](.*?)(?=^\[|\Z)",
                      txt, re.S | re.M)
    assert block, "no [tool.setuptools.package-data] block in pyproject.toml"
    docmodel = re.search(r"^docmodel\s*=\s*\[(.*?)\]", block.group(1), re.S | re.M)
    assert docmodel, (
        "package-data has no `docmodel` key: the manifest would not be in the "
        "wheel even though it is inside the package")
    assert "config.json" in docmodel.group(1), (
        "the `docmodel` package-data key does not name config.json")


def test_the_default_manifest_path_does_not_climb_out_of_the_package():
    """THE CASE BUILT TO FAIL. `<docmodel>/../config.json` resolves inside this
    tree and nowhere else; the `/../` is the whole defect, visible in the
    FileNotFoundError a wheel produced."""
    from docmodel import main as dm
    p = Path(dm.DEFAULT_CONFIG_PATH)
    assert ".." not in p.parts, (
        f"DEFAULT_CONFIG_PATH climbs out of the package: {dm.DEFAULT_CONFIG_PATH}")
    assert p.is_file(), f"DEFAULT_CONFIG_PATH names no file: {p}"
    import docmodel
    pkg = Path(docmodel.__path__[0]).resolve()
    assert pkg in p.resolve().parents, (
        f"the manifest is not inside the docmodel package: {p} vs {pkg}")


def test_the_manifest_still_loads_all_nineteen_modules():
    """The count a `model` run prints. 24 entries, 19 of them
    `application/python` — the rest are disabled by type, which is how a module
    is switched off here. A manifest that loaded 18 would still build a model,
    and the only visible difference would be missing content."""
    from docmodel.loader import load_config, load_modules
    from docmodel.main import DEFAULT_CONFIG_PATH
    entries = load_config(DEFAULT_CONFIG_PATH)
    assert len(entries) == 24, f"manifest has {len(entries)} entries, expected 24"
    assert len(load_modules(entries, "T0078")) == 19


# ---------------------------------------------------------------------------
# The shrinking baseline: nothing under src/ may default to ~/MX/PDFDRILL.
# ---------------------------------------------------------------------------

#: Every file under `src/` still permitted to name the owner's checkout.
#: THIS LIST MAY ONLY SHRINK. It is not a style rule: each entry that leaves it
#: is one place where a clone stopped silently reading the owner's tree.
#:
#: The one survivor is the verbatim text of a prompt sent to a model in July
#: 2026 (466: a prompt lives in a file and is never edited to suit later code —
#: its sha256 is recorded beside every call that used it). It is data about a
#: past run, not a path this code resolves.
MAY_NAME_THE_OWNERS_CHECKOUT = frozenset({
    "pdfdrill/prompts_data/2026-07-15-ocr-integration-prompt.md",
})

_OWNERS_TREE = re.compile(r"MX/PDFDRILL|Path\.home\(\)\s*/\s*['\"]MX")


def _src_files():
    for p in sorted(SRC.rglob("*")):
        if not p.is_file() or p.suffix not in (".py", ".md", ".toml", ".sh", ".json"):
            continue
        if "egg-info" in p.parts or "__pycache__" in p.parts:
            continue
        yield p


def test_no_file_under_src_names_the_owners_checkout():
    named = {str(p.relative_to(SRC)) for p in _src_files()
             if _OWNERS_TREE.search(p.read_text(encoding="utf-8", errors="replace"))}
    new = named - MAY_NAME_THE_OWNERS_CHECKOUT
    assert not new, (
        "these files default or point into the owner's checkout: "
        + ", ".join(sorted(new))
        + " — derive the path from __file__ (the code that is running) and keep "
          "the environment variable as the only override")
    assert named == MAY_NAME_THE_OWNERS_CHECKOUT, (
        "the baseline no longer matches: " + ", ".join(
            sorted(MAY_NAME_THE_OWNERS_CHECKOUT - named))
        + " no longer names it, so remove it from MAY_NAME_THE_OWNERS_CHECKOUT "
          "(the list may only shrink, and it shrinks by being edited)")


# ---------------------------------------------------------------------------
# The three defaults, each checked where it is written.
# ---------------------------------------------------------------------------

def _assign(path: Path, name: str) -> str:
    """The source text of a module-level assignment, or of the default of the
    keyword/attribute `name`. Static, because importing `pdfreader.out.canon`
    runs a `sys.path.insert` at import time — the very thing under test."""
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(name)}\s*=\s*(.*?)(?=^\S|\Z)", text, re.S | re.M)
    assert m, f"{path.name} has no assignment to {name}"
    return m.group(1)


SELF_LOCATING = ("PDFDRILL_SRC must stay an explicit override, but its default "
                 "has to be the checkout this file belongs to — `__file__` — "
                 "never a home tree")


def test_the_out_scripts_fall_back_to_their_own_checkout():
    """`src/pdfreader/out/{canon,eqtable_716}.py` each insert a pdfdrill `src`
    on `sys.path`. They are NOT packaged (`packages.find` does not include
    `pdfreader*`), so they always run from a checkout — and the checkout they
    must use is the one they are in."""
    for name in ("canon.py", "eqtable_716.py"):
        p = SRC / "pdfreader" / "out" / name
        text = p.read_text(encoding="utf-8")
        expr = next((l for l in text.splitlines() if l.startswith("_SRC = ")), None)
        assert expr, f"{name}: nothing resolves PDFDRILL_SRC any more"
        assert "PDFDRILL_SRC" in expr, f"{name}: the override is gone"
        assert "__file__" in expr, f"{name}: {SELF_LOCATING}"
        assert "home()" not in expr, f"{name}: {SELF_LOCATING}"
        assert "raise SystemExit" in text, (
            f"{name}: with no home-tree fallback left, a copy of this file that "
            f"lives in another repository must be TOLD to set PDFDRILL_SRC, not "
            f"fail later on an ImportError")


def test_pdfdrill_home_defaults_to_this_checkout():
    """`scandrill.tools.Tools` probes `<pdfdrill_home>/pdfdrill` and
    `<pdfdrill_home>/src/pdfdrill/sidecar.py` to report what is reachable. With
    `~/MX/PDFDRILL` as the default, that report described the owner's tree from
    inside any other clone."""
    from pdfdrill.scandrill import tools as T
    t = T.Tools()
    assert t.pdfdrill_home == ROOT, (
        f"PDFDRILL_HOME defaulted to {t.pdfdrill_home}, not to the checkout "
        f"this code is in ({ROOT})")


def test_pdfdrill_home_does_not_follow_the_home_directory(monkeypatch, tmp_path):
    """THE CASE BUILT TO FAIL, and the reason the assertion above is not enough:
    `~/MX/PDFDRILL` EXPANDS to this checkout on the owner's machine, so the test
    passes there while the defect is fully present. Move `$HOME` and the default
    must not move with it."""
    from pdfdrill.scandrill import tools as T
    monkeypatch.delenv("PDFDRILL_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert T.Tools().pdfdrill_home == ROOT, (
        "the default followed $HOME, so it is a home-tree path and not the "
        "checkout this code is in")


def test_pdfdrill_home_is_still_overridable(monkeypatch, tmp_path):
    from pdfdrill.scandrill import tools as T
    monkeypatch.setenv("PDFDRILL_HOME", str(tmp_path))
    assert T.Tools().pdfdrill_home == tmp_path


def test_the_yolo_interpreter_candidates_name_no_foreign_checkout():
    """The detector venv is an EXTERNAL tool and its candidate list is a machine
    layout, so `~/Gemma4/.venv-yolo` stays. `~/MX/PDFDRILL/.venv-yolo` does not:
    a venv beside the project means beside THIS project."""
    from pdfdrill import yololayout as Y
    src = (SRC / "pdfdrill" / "yololayout.py").read_text(encoding="utf-8")
    block = re.search(r"INTERPRETER_CANDIDATES = \((.*?)\)\n", src, re.S)
    assert block, "INTERPRETER_CANDIDATES is gone"
    # STATIC, for the reason the $HOME test above exists: on the owner's machine
    # the derived path and the old literal are the SAME STRING, so only the
    # source can tell a derived default from a hard-coded one.
    assert "__file__" in block.group(1), (
        "no candidate is derived from this file's location, so a clone looks for "
        "its venv somewhere else")
    assert "MX/PDFDRILL" not in block.group(1), (
        f"a candidate is still written as a literal path into the owner's "
        f"checkout: {block.group(1)}")
    assert any(str(ROOT) in str(Path(c).expanduser())
               for c in Y.INTERPRETER_CANDIDATES), (
        "the list no longer looks for a venv beside this checkout at all")


def test_nothing_in_src_is_syntactically_broken_by_the_rewrite():
    """Cheap, and it is the failure mode of a mechanical path edit."""
    for p in _src_files():
        if p.suffix == ".py":
            ast.parse(p.read_text(encoding="utf-8", errors="replace"), filename=str(p))


# ---------------------------------------------------------------------------
# The general form of the manifest defect: read beside the module, ship beside
# the module.
# ---------------------------------------------------------------------------

#: The packages `[tool.setuptools.packages.find]` includes.
PACKAGES = ("pdfdrill", "docmodel", "docops", "features", "semantic", "vocabnet")

_BESIDE_ME = re.compile(
    r'Path\(__file__\)\.with_name\(\s*["\']([^"\']+)["\']'
    r'|os\.path\.join\(\s*os\.path\.dirname\(__file__\)\s*,\s*["\']([^"\']+)["\']'
    r'|Path\(__file__\)\.(?:resolve\(\)\.)?parent\s*/\s*["\']([^"\']+)["\']')


def _package_data() -> dict:
    txt = (ROOT / "pyproject.toml").read_text()
    block = re.search(r"^\[tool\.setuptools\.package-data\](.*?)(?=^\[|\Z)",
                      txt, re.S | re.M)
    assert block
    # Comments first: an apostrophe in prose ("the rig's config") pairs with the
    # next quote and swallows half the list. Measured — it hid `prompts_data/*`
    # and reported 19 shipped prompts as missing.
    body = re.sub(r"#[^\n]*", "", block.group(1))
    return {m.group(1): re.findall(r'["\']([^"\']+)["\']', m.group(2))
            for m in re.finditer(r"^(\w+)\s*=\s*\[(.*?)\]", body, re.S | re.M)}


def _read_beside_their_module():
    """{(package, name): first file that reads it} for every non-.py path a
    module resolves against its OWN location."""
    out = {}
    for pkg in PACKAGES:
        for p in sorted((SRC / pkg).rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            for m in _BESIDE_ME.finditer(p.read_text(encoding="utf-8",
                                                     errors="replace")):
                name = m.group(1) or m.group(2) or m.group(3)
                if not name or name.endswith(".py"):
                    continue
                target = p.parent / name
                if not target.exists():       # a path it WRITES, not reads
                    continue
                # A module may name the DIRECTORY and index into it (
                # `repo_publish` does, through `_TMPL`), so a directory stands
                # for the data files in it. `.py` files are shipped by
                # `packages.find`, not by package-data.
                files = ([target] if target.is_file() else
                         [f for f in sorted(target.rglob("*"))
                          if f.is_file() and f.suffix != ".py"
                          and "__pycache__" not in f.parts])
                for f in files:
                    out.setdefault((pkg, str(f.relative_to(SRC / pkg))), p)
    return out


def test_every_file_a_module_reads_beside_itself_is_in_the_wheel():
    """The general form of the defect T-0078 was opened for.

    `docmodel.main` read its module manifest with `Path(__file__)` and the
    manifest was in no wheel; `pdfdrill.repo_publish` reads three templates the
    same way and they were in no wheel either; `docops.main` and
    `docops.conserve` read two more. `package-data` had one key, `pdfdrill`, so
    four of the five packages could not ship a data file at all.

    This is the invariant, not the list: a module that resolves a file against
    its own location must have a pattern that ships it. A new one fails here
    rather than in a FileNotFoundError on someone else's machine.
    """
    import fnmatch
    data = _package_data()
    missing = []
    for (pkg, rel), reader in sorted(_read_beside_their_module().items()):
        pats = data.get(pkg, [])
        if not any(fnmatch.fnmatch(rel, pat) for pat in pats):
            missing.append(f"{pkg}/{rel} (read by {reader.relative_to(ROOT)})")
    assert not missing, (
        "read beside the module, absent from the wheel:\n  "
        + "\n  ".join(missing)
        + "\nadd a pattern under [tool.setuptools.package-data]")
