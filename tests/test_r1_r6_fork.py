"""R1/R6 — one patch, a reliability flag, and which pdfminer ran.

Three change requests against the vendored fork, each pinned to a failure that
is silent without it.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfreader import build_identity                          # noqa: E402


# R2 now has its own file, `test_r2_glyphname_reliable.py`, which checks it
# against the two psred fixtures the change request names as the acceptance
# criteria. The version that lived here was built from names I happened to
# find in our own corpus (`uni0028`, `u1D465`) and MISSED the measured class
# entirely: pdfTeX bitmap fonts' `a44`/`a97`, which is the whole point of
# the request. Generalising from what was in front of me is the same error
# as the 1,300 px proxy in 866.


# --------------------------------------------------------------------------
# R6 — which pdfminer produced this output.
# --------------------------------------------------------------------------

def test_the_build_identity_uses_psreds_keys():
    """R6 asks for "the same" record psred writes, so the two tools' outputs
    can be compared directly: `{version, glyph_identity_patch}`."""
    d = build_identity.identity()
    assert "version" in d and "glyph_identity_patch" in d
    assert isinstance(d["glyph_identity_patch"], bool)
    assert d["patch"] == "pdfminer-glyph-identity.patch"


def test_one_boolean_can_no_longer_describe_the_patch():
    """THIS MODULE'S OWN FINDING. `glyph_identity_patch` was a fair summary
    when the patch did one thing. R2 and R3 added `glyphname_reliable`,
    `font.spec` and `LTChar.fontsize/scaling/rise`, and the bool cannot see
    the difference — measured on this machine, the live build and the built
    fork BOTH report True and only one can do what R3 and R4 depend on. So a
    `features` map is carried beside it."""
    d = build_identity.identity()
    f = d["features"]
    for k in ("glyph_identity", "font_spec", "char_text_state",
              "glyphname_reliable", "render_mode"):
        assert k in f and isinstance(f[k], bool), k
    # the bool is exactly the original question, unchanged in meaning
    assert d["glyph_identity_patch"] is f["glyph_identity"]


def test_a_build_older_than_the_patch_is_reported():
    """`patch_sha256` names the patch ON DISK; the loaded pdfminer was built
    from whichever patch was current when the installer last ran. Recording
    the first while describing the second is provenance that is worse than
    none — so the gap is reported. It is not hypothetical: the installer
    silently reuses an existing venv without --rebuild, which is how a build
    drifts behind its patch unnoticed."""
    d = build_identity.identity()
    assert isinstance(d["build_behind_patch"], list)
    for name in d["build_behind_patch"]:
        assert d["features"][name] is False, name


def test_feature_presence_is_asked_of_the_loaded_module_not_a_file():
    """An installer that exited 0 is not an answer, and a version string does
    not say whether the patch took. The question is what THIS process is
    running, so it is asked of the imported class."""
    src = Path(build_identity.__file__).read_text(encoding="utf-8")
    assert "hasattr(EncodingDB" in src
    assert "hasattr(PDFFont" in src
    assert "get_encoding_names" in src


def test_the_patch_hash_identifies_the_fork():
    """A rebase onto a newer pdfminer changes the patch; outputs made before
    and after must be distinguishable."""
    sha = build_identity.patch_sha256()
    assert sha and len(sha) == 64
    assert build_identity.PATCH.exists()


def test_the_build_identity_points_at_the_one_patch():
    """R1 and R6 agree on a single path, or R6 reports the hash of a copy
    nobody applies."""
    from tests.test_pdfminer_fork_is_additive import PATCH as GATE_PATCH
    assert build_identity.PATCH == GATE_PATCH
