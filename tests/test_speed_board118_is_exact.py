r"""SPEED (EXACT), board 118: each speedup is held to the code it replaced.

The three born pages slowest on board 118 spent their time in fontTools'
per-byte eexec decryption, in `equation_number`'s re-join of every line
suffix, and in `_group_lines`' scans of every row. The replacements must give
identical results; the board's 24 born readings were byte-identical, and
these tests keep the reference beside each.
"""
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

pytest.importorskip("fontTools")
from pdfreader import inkboxes, project_mmd  # noqa: E402


def test_the_fast_eexec_equals_fonttools():
    from fontTools.misc import eexec
    inkboxes._fast_eexec()
    ref = inkboxes._EEXEC_ORIGINAL
    assert ref is not None and eexec.decrypt is inkboxes._eexec_decrypt
    rnd = random.Random(20261128)
    for n in (0, 1, 4, 257, 4096):
        for key in (55665, 4330, 0, 65535, 70001):
            data = bytes(rnd.randrange(256) for _ in range(n))
            assert inkboxes._eexec_decrypt(data, key) == ref(data, key)
    # fontTools' own documented example
    assert inkboxes._eexec_decrypt(b"\0\0asdadads asds\265", 12321) == (
        b"0d\nh\x15\xe8\xc4\xb2\x15\x1d\x108\x1a<6\xa1", 36142)


class _G:
    def __init__(self, text, x0, x1, size=10.0):
        self.text, self.rect, self.size = text, (x0, 0.0, x1, size), size


class _L:
    def __init__(self, glyphs):
        self.glyphs = glyphs


def _reference(line, right, left=None):
    """`equation_number` as it was before the early stop (the suffix walk)."""
    gs = sorted((g for g in line.glyphs if g.text.strip()), key=lambda g: g.rect[0])
    if len(gs) < 3:
        return []
    whole = "".join(g.text for g in gs).strip()
    if project_mmd._EQ_TAG.match(whole) and gs[-1].rect[2] >= right - 2.0 * max(
            (g.size for g in gs), default=10.0):
        return list(gs)
    size = max(g.size for g in gs)
    if left is not None and gs[0].rect[0] <= left + 0.5 * size:
        for i in range(1, len(gs) - 1):
            if gs[i].text.strip() != ")":
                continue
            head = gs[:i + 1]
            if (project_mmd._EQ_TAG.match("".join(g.text for g in head).strip())
                    and gs[i + 1].rect[0] - gs[i].rect[2] >= 3.0 * size):
                return head
            break
    for i in range(len(gs) - 1, 0, -1):
        run = gs[i:]
        if not project_mmd._EQ_TAG.match("".join(g.text for g in run).strip()):
            continue
        if run[-1].rect[2] < right - 2.0 * size:
            return []
        gap = run[0].rect[0] - gs[i - 1].rect[2]
        prev = gs[i - 1]
        applies = (prev.text or "").strip().isalpha()
        flush = run[-1].rect[2] >= right - 0.5 * size
        if gap < (0.6 * size if (flush and not applies) else 3.0 * size):
            return []
        return run
    return []


def test_the_equation_number_early_stop_equals_the_suffix_walk():
    rnd = random.Random(118)
    alphabet = list("()0123456789.ab xyz=+-  \\") + ["(1", "2)", "ab", "x(", "α"]
    for _ in range(4000):
        n = rnd.randrange(1, 14)
        x, gs = 0.0, []
        for _k in range(n):
            w = rnd.choice((2.0, 5.0, 31.0))
            gs.append(_G(rnd.choice(alphabet), x, x + 5.0))
            x += 5.0 + w
        right = x + rnd.choice((-20.0, 0.0, 3.0))
        left = rnd.choice((None, 0.0))
        line = _L(gs)
        got = project_mmd.equation_number(line, right, left)
        assert [id(g) for g in got] == [id(g) for g in _reference(line, right, left)]
