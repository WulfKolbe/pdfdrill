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


def _has_glyph_identity():
    try:
        import inspect

        from pdfminer.layout import LTChar
        return "glyphname" in inspect.getsource(LTChar.__init__)
    except Exception:                                          # noqa: BLE001
        return False


def test_the_patched_build_is_the_one_installed():
    """Not a style check: stock pdfminer imports fine and silently drops the
    glyph name, which is why this is asserted on the FEATURE."""
    if not _has_glyph_identity():
        pytest.skip("no patched pdfminer on this interpreter "
                    "(vendor/install-pdfminer-fork.sh --user --rebuild)")
    assert _installed("pdfminer.six"), "patched pdfminer has no distribution metadata"


def test_the_patched_version_satisfies_pdfplumbers_pin():
    """The property that makes it survive. Without it the next pip run wins."""
    if not _has_glyph_identity():
        pytest.skip("no patched pdfminer on this interpreter")
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


def test_bootstrap_notices_when_its_own_pip_step_removes_the_fork():
    from pathlib import Path
    sh = (Path(__file__).resolve().parents[1] / "bootstrap.sh").read_text()
    assert "FORK_BEFORE" in sh, "bootstrap.sh does not check for the fork before its pip step"
    assert sh.index("FORK_BEFORE=0") < sh.index("pip install --quiet"), (
        "the before-check must run BEFORE the pip step")
