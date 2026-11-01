"""T-0113 — nothing THIS repo installs, builds or runs may create a dot-named
directory in the checkout. Owner, 2026-10-30 and 2026-10-31, as house rules:
"NO HIDDEN FILES, NO TMP FIELS" and "no files outside the project folder".

SCOPED TO WHAT WE CREATE, deliberately. A blanket "no dot-folder but .git and
.claude" fails on `.github/` and `.devcontainer/`, which MUST be dot-named by
GitHub's and the devcontainer spec's convention, and on `.codegraph/` and
`.superpowers/`, which are third-party tool state this repository does not
produce and cannot move. Those go to the owner as a separate question. What is
ours is: pytest's cache, the patched-pdfminer venv, and that venv's build
directory.

THE LAST TEST IS THE ONE THAT MATTERS. The other four read configuration; that
one runs pytest as a subprocess in a copy of the checkout and looks at what
appeared on disk, because a `cache_dir` setting that a plugin overrides, or a
`-p no:cacheprovider` that only the documented command line passes, would
satisfy every static check and still litter the tree for anyone who types
`pytest`.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Built from parts so that this file's own text does not match the search it
#: performs. The needle is the old hidden name.
OLD_VENV = "." + "pdfmm" + "-venv"
OLD_BUILD = "." + "pdfmm" + "-build"


def _ini_options() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r"^\[tool\.pytest\.ini_options\]\s*$(.*?)(?=^\[|\Z)",
                  text, re.S | re.M)
    return m.group(1) if m else ""


def _no_dot_component(path: str) -> bool:
    """True when no component of `path` begins with a dot."""
    return not any(p.startswith(".") for p in re.split(r"[/\\]", path) if p)


# --------------------------------------------------------------------------
# Configuration: where the three artefacts are declared to go.
# --------------------------------------------------------------------------

def test_pytest_cache_is_configured_out_of_the_checkout_root():
    """`.pytest_cache/` appeared in the checkout root because nothing said
    where else to put it. The documented command line passes
    `-p no:cacheprovider`, but a bare `pytest` does not, and the owner's rule
    is about the tree, not about one command line."""
    ini = _ini_options()
    m = re.search(r"^\s*cache_dir\s*=\s*['\"]([^'\"]+)['\"]", ini, re.M)
    assert m, ("pyproject.toml [tool.pytest.ini_options] must set cache_dir; "
               "it currently reads:\n%s" % ini)
    cache = m.group(1)
    assert _no_dot_component(cache), "cache_dir is still dot-named: %r" % cache
    assert cache.startswith("work/"), (
        "cache_dir must live under the visible, git-ignored work/ tree, "
        "not %r" % cache)


def test_the_fork_installer_defaults_to_visible_directories():
    """`vendor/install-pdfminer-fork.sh` defaulted its venv to
    `$HERE/.pdfmm-venv` and its build directory to `$HERE/.pdfmm-build`."""
    sh = (ROOT / "vendor" / "install-pdfminer-fork.sh").read_text(encoding="utf-8")
    for var in ("VENV", "BUILD"):
        m = re.search(r'^%s=(?:"([^"]*)"|(\S+))' % var, sh, re.M)
        assert m, "%s= default not found in the installer" % var
        val = m.group(1) or m.group(2)
        assert _no_dot_component(val), "%s default is still hidden: %r" % (var, val)
        assert "work/" in val, (
            "%s must default under the visible work/ tree, not %r" % (var, val))


def test_the_pdfreader_installer_defaults_to_a_visible_directory():
    sh = (ROOT / "src" / "pdfreader" / "install.sh").read_text(encoding="utf-8")
    # EVERY assignment, not the first: this installer sets VENV in both arms
    # of an if/else (inside the repository, and extracted standalone), and
    # checking only one of them would let the other stay hidden.
    vals = re.findall(r'^\s*VENV="([^"]*)"', sh, re.M)
    assert vals, "no VENV= assignment found in src/pdfreader/install.sh"
    for val in vals:
        assert _no_dot_component(val), "a VENV default is still hidden: %r" % val
        assert "work/pdfmm-venv" in val, "unexpected VENV default: %r" % val


#: Files allowed to name the old hidden paths, each with the reason. An
#: allow-list rather than a pattern, because every clever pattern I tried
#: either let a real reader through or banned an honest record. A NEW file
#: using the old name still fails this test, which is the point.
_MAY_NAME_THE_OLD_PATH = {
    ".gitignore":
        "keeps ignoring the pre-T-0113 names so a stale copy on someone's "
        "machine does not suddenly appear as untracked",
    "src/pdfreader/.gitignore":
        "same, for this subtree, plus a note about how git matches a symlink "
        "that was once committed in place of the directory",
    "tests/test_pdfminer_fork_is_additive.py":
        "its tree-walk filter keeps skipping the old names, so a stale copy "
        "cannot make the test report a second patch file",
    "vendor/install-pdfminer-fork.sh":
        "one comment recording what the defaults used to be and why they moved",
}


def test_no_file_in_the_tree_still_names_the_hidden_venv():
    """THE HALF-DONE RENAME GUARD. The default lived in two installers and was
    hard-coded in four test files, four pdfreader modules and a README — nine
    readers besides the scripts. Moving the default alone would leave every one
    of them pointing at a path that no longer exists, and because those tests
    SKIP when the venv is absent (`pytest.skip("fork venv not built")`) the
    loss would be silent: 21 fork tests stop running and the suite still says
    PASSED."""
    # `--others --exclude-standard` as well as the index, because the INDEX IS
    # NOT THE TREE. The first version of this test asked plain `git ls-files`,
    # which lists only what is already staged or committed — so `tests/
    # forkvenv.py`, the very file this change adds, was invisible to it for
    # every run that passed, and became visible one `git add -A` before the
    # commit. The coordinator's audit found it in a fresh clone: 1 failed, 6
    # passed, on a tree my own run had called green. A guard whose input is the
    # index gives every new file a free pass until the moment nobody re-runs it.
    out = subprocess.run(["git", "ls-files", "--cached", "--others",
                          "--exclude-standard"],
                         cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    me = Path(__file__).name
    offenders = []
    for rel in out.stdout.splitlines():
        # Prose is exempt. `vendor/README.md` narrates the 2026-09-29 incident
        # in which a deleted ~/Downloads/pdf2mmd took the venv beside
        # ~/pdf2mmd with it, and the directory HAD that name then; rewriting
        # the record to match a later rename would make the history wrong.
        # What this guard is for is readers that RESOLVE a path.
        if (not rel or Path(rel).name == me or rel.endswith(".md")
                or rel in _MAY_NAME_THE_OLD_PATH):
            continue
        p = ROOT / rel
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        if OLD_VENV in text or OLD_BUILD in text:
            offenders.append(rel)
    assert not offenders, (
        "%d file(s) in the working tree still name the hidden venv/build "
        "directory, so the rename is half done: %s"
        % (len(offenders), ", ".join(offenders[:12])))


def test_the_allow_list_does_not_rot():
    """Every exemption must still be needed. An allow-list that keeps entries
    for files that no longer mention the path is how the next rename gets a
    free pass."""
    stale = []
    for rel in _MAY_NAME_THE_OLD_PATH:
        p = ROOT / rel
        if not p.exists():
            stale.append("%s (gone)" % rel)
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if OLD_VENV not in text and OLD_BUILD not in text:
            stale.append("%s (no longer mentions it)" % rel)
    assert not stale, "remove these exemptions: %s" % ", ".join(stale)


# --------------------------------------------------------------------------
# The measurement: run pytest and look at the tree.
# --------------------------------------------------------------------------

def test_a_bare_pytest_run_creates_no_hidden_directory(tmp_path):
    """Runs `pytest` with NO flags of ours, on a throwaway test file, with this
    repository's own pyproject as the configuration — and then lists the
    dot-named directories that appeared."""
    work = tmp_path / "checkout"
    work.mkdir()
    shutil.copy(ROOT / "pyproject.toml", work / "pyproject.toml")
    (work / "tests").mkdir()
    (work / "tests" / "test_trivial.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8")

    before = {p.name for p in work.iterdir() if p.is_dir()}
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"],
                       cwd=work, capture_output=True, text=True, timeout=300,
                       env=env)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    after = {p.name for p in work.iterdir() if p.is_dir()}
    appeared = sorted(n for n in (after - before) if n.startswith("."))
    assert not appeared, (
        "a bare `pytest` created %s in the checkout root; cache_dir in "
        "pyproject.toml must point under work/" % appeared)


def test_no_installer_defaults_a_venv_under_src():
    """`src/` is source. A 315 MB site-packages tree under it would be walked
    by `tests/test_no_ocr_engine.py`, which greps `(ROOT/"src").rglob("*.py")`
    for an OCR engine's argv head — so a venv there fails that test with a
    finding from a third-party package, which is a wrong answer about this
    repository. The subtree installer therefore builds into the repository's
    own work/ tree when it is inside the repository, and only falls back to
    `$HERE/work` when extracted standalone."""
    sh = (ROOT / "src" / "pdfreader" / "install.sh").read_text(encoding="utf-8")
    m = re.search(r'^\s*VENV="([^"]*\$REPO[^"]*)"', sh, re.M)
    assert m, ("src/pdfreader/install.sh must default VENV under $REPO when it "
               "is inside the repository; found none")
    assert "work/pdfmm-venv" in m.group(1), m.group(1)
    assert "/src/" not in m.group(1), m.group(1)
