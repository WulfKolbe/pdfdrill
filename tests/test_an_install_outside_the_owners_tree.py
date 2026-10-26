"""An install that is not the owner's checkout must still find its own data.

T-0078 (drillgroup). `docmodel/main.py` resolved its module manifest as
`<docmodel>/../config.json`, which is `src/config.json` in this tree and
`site-packages/config.json` in a wheel. `src/config.json` sat at the `src/`
ROOT, outside every package directory, and `[tool.setuptools.package-data]` is
keyed per package — so no key could ever include it, no wheel ever carried it,
and a wheel-installed `pdfdrill model` died on a FileNotFoundError naming a path
with `/../` in it. (Measured by the pdf2mmd2 session; it fails LOUDLY, which is
the one piece of luck here. The 24 manifest entries that load 19 modules are the
file's whole content, so the alternative would have been a model built by no
module at all.)

It is not one file. `package-data` had a single key, `pdfdrill`, so four of the
five packages could not ship a data file at all: the five corpus inventories
`type_contract`/`prop_contract` read, `docops.main`'s default pipeline,
`docops.conserve`'s `--gate` baseline, and `repo_publish`'s three templates
were all absent from every wheel ever built here.

The rule this file enforces: a module that resolves a file against its own
location must have a pattern that ships it.
"""
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
