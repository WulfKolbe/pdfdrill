"""`fonts --force` must refresh BOTH font caches.

`fonts` and `fonts_layer` are two views of the same pdffonts output, cached
independently and — until now — written exactly once, ever. So a change to the
font CLASSIFIER (adding OpenSymbol to the math-font hints, say) does not reach a
document that was analysed before it: the structured layer keeps its stale
is_math flags, is_math_bearing keeps answering False, and the math-bearing gate
stays silent on a paper full of formulas.

Refreshing one and leaving the other is the same failure one step later, so
force clears both together.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.commands import _invalidate_font_caches, FONTS_KNOWN, FONTS_LAYER_KNOWN


class _FakeSidecar:
    def __init__(self, facts):
        self._f = set(facts)
        self.saved = False

    @property
    def facts(self):
        return set(self._f)

    def remove_fact(self, f):
        self._f.discard(f)

    def save(self):
        self.saved = True


def test_force_clears_both_font_caches():
    sc = _FakeSidecar({FONTS_KNOWN, FONTS_LAYER_KNOWN, "SIZE_KNOWN"})
    _invalidate_font_caches(sc)
    assert FONTS_KNOWN not in sc.facts
    assert FONTS_LAYER_KNOWN not in sc.facts, "the structured layer holds is_math"
    assert "SIZE_KNOWN" in sc.facts, "unrelated layers must not be dropped"


def test_invalidation_is_safe_when_nothing_is_cached():
    sc = _FakeSidecar(set())
    _invalidate_font_caches(sc)
    assert sc.facts == set()
