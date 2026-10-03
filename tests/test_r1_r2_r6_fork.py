"""R1/R2/R6 — one patch, a reliability flag, and which pdfminer ran.

Three change requests against the vendored fork, each pinned to a failure that
is silent without it.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfreader import build_identity                          # noqa: E402
from pdfreader.texmap import synthesised_name, untrusted_name  # noqa: E402


# --------------------------------------------------------------------------
# R2 — a name that is a number is not a name.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "uni0028",   # CMR10's '(' — the font calls it `parenleft`
    "u1D465",    # CMMI10's '𝑥' — the font calls it `x`
    "x65",       # hex 65 = 'e'
    "g12", "cid7", "CID7", "index44", "glyph3",
])
def test_a_codepoint_restated_is_flagged(name):
    assert synthesised_name(name) is True


@pytest.mark.parametrize("name", [
    "parenleft", "summationdisplay", "space", "x", "A", "alpha",
    "radical", "braceleftbig", None, "",
])
def test_a_real_font_name_is_not_flagged(name):
    assert synthesised_name(name) is False


def test_the_flag_does_not_gate():
    """R2 asks for a RELIABILITY FLAG. `untrusted_name` is the function that
    abstains — it suppresses LaTeX and defers the span keeping the region.
    Conflating the two would drop ~148,000 glyphs whose `text` is perfectly
    good, on the grounds that their NAME adds nothing."""
    assert synthesised_name("uni0028") is True
    # …and the abstain path is unmoved by it: a Unicode-derived name in an
    # ordinary text font is not a StandardEncoding fallback.
    assert untrusted_name("ABCDEF+CMR10", "uni0028") is False


def test_it_separates_two_real_documents():
    """Measured: sigma26-078 carries 0 synthesised names of 3,946 glyphs, and
    one Z-Library book carries 136,897 of 138,337 (99.0%). Before the flag
    those two readings looked alike — both had a `glyphname` on every glyph."""
    good = ["parenleft", "x", "summationdisplay", "alpha"]
    bad = ["uni0031", "uni0032", "uni2119", "u1D465"]
    assert sum(synthesised_name(n) for n in good) == 0
    assert sum(synthesised_name(n) for n in bad) == len(bad)


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
