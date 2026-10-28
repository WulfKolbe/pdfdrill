"""The patched pdfminer must still be here after the next `pip install`.

P1 (auditing session, 2026-10-20): `bash bootstrap.sh`, `pip install -e .` and
CoCalc's `tools/imageserver/install.sh` each REMOVED the glyph-identity fork.
Nothing in pdfdrill asks for that — our own pin is `pdfminer.six>=20221105`.
pdfPLUMBER pins `pdfminer.six==<release>` EXACTLY; pip resolves that pin, the
fork's setuptools-scm version (`20260108.dev6+ga18de2a9c`) does not equal the
release, and stock pdfminer is installed over the patch. The install looks
clean and `LTChar.glyphname` is gone, which is how it survived three sessions.

Measured in two throwaway venvs: the scm-versioned wheel is REPLACED by
`pip install pdfplumber` (glyph identity gone); a wheel versioned
`20260107+glyphid.g<sha>` is KEPT (a PEP 440 local segment satisfies `==`).

This test does not build anything. It asserts the INSTALLED state has the
property that makes the fork survive — the property whose absence was P1.
"""
import re
from pathlib import Path

import pytest


def _installed(dist):
    import importlib.metadata as md
    try:
        return md.version(dist)
    except Exception:                                          # noqa: BLE001
        return None


def _pdfplumber_pin():
    """The exact pdfminer release pdfplumber pins, or None."""
    import importlib.metadata as md
    try:
        reqs = md.requires("pdfplumber") or []
    except Exception:                                          # noqa: BLE001
        return None
    for r in reqs:
        m = re.match(r"\s*pdfminer\.six\s*==\s*([^\s,;]+)", r)
        if m:
            return m.group(1)
    return None


#: WHERE THE INSTALLER IS NAMED. Every skip below says this, because "3 failed"
#: and "the fork was never built" are the same summary line otherwise.
INSTALLER = "bash vendor/install-pdfminer-fork.sh --user --rebuild"


def fork_missing(*features) -> list:
    """Which of `features` the loaded pdfminer lacks — asked of the module.

    Thin wrapper over `pdfreader.build_identity.missing`, which is the ONE
    place that answers this; a second copy of the rule here is how the two
    drift apart (the repo already carries
    `test_the_package_helper_does_not_duplicate_the_rule` for the same
    reason). Default `glyph_identity`: `LTChar.glyphname`, the feature whose
    absence P1 was about.
    """
    from pdfreader import build_identity
    return build_identity.missing(*(features or ("glyph_identity",)))


def requires_fork(*features):
    """A skipif for a test that reads an attribute only the fork adds.

    Used by `test_r2_glyphname_reliable.py` (`LTChar.glyphname`),
    `test_docmodel_six.py` and `test_runin_heading.py` (`LTChar.invisible`,
    read by `docmodel_six.py:2936`). On a base install those seven tests
    raised `AttributeError` and read exactly like broken code; the fix is not
    to install the fork everywhere, it is to say which tool is missing.
    """
    absent = fork_missing(*features)
    return pytest.mark.skipif(
        bool(absent),
        reason="this pdfminer has no %s — %s" % (", ".join(absent) or "?",
                                                 INSTALLER))


def _has_glyph_identity():
    return not fork_missing("glyph_identity")


def test_the_patched_build_is_the_one_installed():
    """FAILS when the fork is absent. It used to SKIP, which is the whole
    problem: a missing fork is a broken install, and a suite that skips past it
    reports green on an installation whose glyph-identity features silently
    return nothing. An audit found exactly that — the documented install ended
    with stock pdfminer and this file said nothing. Stock pdfminer imports fine
    and drops the glyph name, so the assertion is on the FEATURE, not the import.
    """
    assert _has_glyph_identity(), (
        "this interpreter has stock pdfminer, not the glyph-identity fork: "
        "`LTChar.glyphname` is absent, so docmodel_six and the born-digital "
        "reader silently lose every glyph name. `bash bootstrap.sh` now builds "
        "it, or run `bash vendor/install-pdfminer-fork.sh --here --rebuild` "
        "(use --here inside a venv; --user cannot work there).")
    assert _installed("pdfminer.six"), "patched pdfminer has no distribution metadata"


def test_the_patched_version_satisfies_pdfplumbers_pin():
    """The property that makes it survive. Without it the next pip run wins."""
    assert _has_glyph_identity(), (
        "no patched pdfminer on this interpreter — see "
        "test_the_patched_build_is_the_one_installed")
    pin = _pdfplumber_pin()
    if pin is None:
        pytest.skip("pdfplumber does not pin pdfminer.six exactly on this install")
    v = _installed("pdfminer.six")
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version
    assert SpecifierSet(f"=={pin}").contains(Version(v)), (
        f"installed pdfminer.six {v} does not satisfy pdfplumber's pdfminer.six=={pin}: "
        f"the next `pip install` that pulls pdfplumber will replace the patched build "
        f"(P1). Rebuild with vendor/install-pdfminer-fork.sh, which versions it "
        f"{pin}+glyphid.g<sha>.")


def test_the_installer_versions_the_build_against_the_pin():
    """The installer must read the pin and set it, not hardcode a release."""
    from pathlib import Path
    sh = (Path(__file__).resolve().parents[1]
          / "vendor" / "install-pdfminer-fork.sh").read_text()
    assert "SETUPTOOLS_SCM_PRETEND_VERSION" in sh, "the build is not versioned against the pin"
    assert "pin_release" in sh, "the pin is hardcoded rather than read from pdfplumber"


def test_the_documented_install_ENDS_with_the_fork_present():
    """Not "restores it if it was there" — that was this test's first mistake.

    905o made bootstrap.sh restore the fork only when FORK_BEFORE=1, i.e. only
    when its own pip step had just removed one already present, and this test
    asserted exactly that mechanism. A fresh clone in a fresh venv never had the
    fork: FORK_BEFORE=0, nothing is built, and the documented install ends with
    stock pdfminer.six and no `LTChar.glyphname`. Everything still imports, so
    the gap is silent. A reviewer found it, not this test, because the test
    encoded the mechanism instead of the requirement.

    The requirement is unconditional: after the documented install the fork is
    there. So assert the SHAPE that delivers it — an unconditional check with a
    build on the failing branch — and never a before/after flag.
    """
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for name in ("bootstrap.sh", "tools/imageserver/install.sh"):
        sh = (root / name).read_text()
        # Comments explain the history; only the LOGIC is the contract.
        logic = "\n".join(l for l in sh.splitlines()
                          if not l.lstrip().startswith("#"))
        assert "install-pdfminer-fork.sh --check" in logic, (
            f"{name}: never checks whether the fork is present")
        assert "--rebuild" in logic, (
            f"{name}: never builds the fork, so a fresh install cannot get it")
        # `pip install --user` REFUSES inside a venv, and the documented install
        # IS a fresh venv, so the mode cannot be hardcoded to --user: that was
        # the second half of this defect, found only by running the real thing.
        assert "FORK_MODE" in logic and "--here" in logic, (
            f"{name}: hardcodes the install mode — inside a venv `--user` "
            f"cannot place the build and the install ends without the fork")
        # The defect was the GATE, not the absence of a build: a flag recording
        # whether the fork existed BEFORE the pip step makes the build
        # conditional on it having been there, which a fresh install never is.
        assert "FORK_BEFORE" not in logic, (
            f"{name}: still gates the build on the fork having been present "
            f"before the pip step — a fresh clone in a fresh venv gets nothing")


def test_the_installer_is_named_where_the_install_is_documented():
    """A reader who follows README's install gets stock pdfminer and no
    glyph identity — seven tests skip and the glyph-name features are quietly
    off. `bootstrap.sh` has ensured the fork since P1, but the README install
    block offered `pip install -e .` alone and never said the fork exists, and
    the fork CANNOT be a requirement: it is a local patch, not a PyPI package,
    so naming it in `pyproject.toml` would break `pip install` everywhere."""
    root = Path(__file__).resolve().parents[1]
    script = "vendor/install-pdfminer-fork.sh"
    assert (root / script).is_file(), f"{script} is gone; this test is stale"
    for name in ("bootstrap.sh", "README.md"):
        text = (root / name).read_text(encoding="utf-8")
        assert script in text, (
            f"{name} does not name {script}, so the documented install ends "
            "with stock pdfminer and says nothing about it")


def test_every_test_that_reads_a_forked_attribute_is_guarded():
    """The three files measured failing on the base install ask `requires_fork`
    first. Static, because the whole point is what happens on a machine this
    suite is not currently running on."""
    here = Path(__file__).resolve().parent
    for name in ("test_r2_glyphname_reliable.py", "test_docmodel_six.py",
                 "test_runin_heading.py"):
        text = (here / name).read_text(encoding="utf-8")
        assert "requires_fork" in text or "fork_missing" in text, (
            f"{name} reads an attribute only the patched pdfminer has and "
            "does not say so: on a base install it fails as if the code were "
            "broken")
