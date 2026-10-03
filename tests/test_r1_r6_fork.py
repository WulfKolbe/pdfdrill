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

def test_the_build_identity_names_the_module_actually_loaded():
    d = build_identity.identity()
    assert "pdfminer" in d and "fork_present" in d
    assert d["patch"] == "pdfminer-glyph-identity.patch"


def test_fork_presence_is_asked_of_the_class_not_a_file():
    """An installer that exited 0 is not an answer, and a version string does
    not say whether the patch took. The question is what THIS process is
    running, so it is asked of the imported class."""
    src = Path(build_identity.__file__).read_text(encoding="utf-8")
    assert "hasattr(EncodingDB" in src
    assert 'get_encoding_names' in src


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
