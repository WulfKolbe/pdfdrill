r"""
SPEED (EXACT): the font-name predicates (`family_of`, `is_italic`,
`is_bold`, `is_small_caps`, `is_monospace`, `is_sans_serif`) ran their
regexes on every call: 754 k `is_monospace` searches alone for 72 board
pages. They are cached per name. `is_monospace` and `is_sans_serif` also
read the document's measured monospace set, so `set_measured_monospace`
clears their answers. The 24 born board pages' lines.json are
byte-identical.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import texmap as T


def test_a_new_measurement_changes_a_cached_answer():
    name = "ABCDEF+PublisherFontXYZ"
    T.set_measured_monospace(set())
    assert T.is_monospace(name) is False
    assert T.is_sans_serif(name) is False
    T.set_measured_monospace({"PublisherFontXYZ"})
    try:
        assert T.is_monospace(name) is True
    finally:
        T.set_measured_monospace(set())
    assert T.is_monospace(name) is False


def test_cached_answers_equal_fresh_ones():
    for f in ("ABC+CMBX10", "HffcmrYvygwvTimes-Roman", "ABC+LMRoman12-Italic",
              "PxfrfpSFSS0900", "ABC+NimbusRomNo9L-Medi", "QtxpctLqshvdMTMI"):
        for fn in (T.family_of, T.is_italic, T.is_bold, T.is_small_caps):
            assert fn(f) == fn.__wrapped__(f), (fn.__name__, f)
