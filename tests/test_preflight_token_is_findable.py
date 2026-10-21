"""The token must be findable by the instruction the SKILL itself gives.

Found by an auditing session: 905m put the literal string `PREFLIGHT-TOKEN:END`
into a SKILL table row while explaining where the token is, so the SKILL then
contained the marker TWICE and `grep -B1 PREFLIGHT-TOKEN:END` returned the
table row instead of the token. A doc that explains a marker by quoting it
breaks the marker. Describe it; do not quote it.
"""
from pathlib import Path

from pdfdrill import preflight as pf

_SKILLS = [
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "pdfdrill" / "SKILL.md",
    Path(__file__).resolve().parents[1] / "src" / "pdfdrill" / "skill" / "SKILL.md",
]


def _texts():
    return [(p, p.read_text(encoding="utf-8")) for p in _SKILLS if p.is_file()]


def test_the_end_marker_appears_exactly_once():
    for p, text in _texts():
        n = text.count(pf.TOKEN_END)
        assert n == 1, f"{p.name}: end marker appears {n}x — a reader keyed on it finds the wrong line"


def test_the_begin_marker_appears_exactly_once():
    for p, text in _texts():
        n = text.count(pf.TOKEN_BEGIN)
        assert n == 1, f"{p.name}: begin marker appears {n}x"


def test_grep_b1_on_the_marker_yields_the_token():
    """The shape the audit used, and the shape a reader naturally reaches for."""
    for p, text in _texts():
        lines = text.splitlines()
        idx = [i for i, l in enumerate(lines) if pf.TOKEN_END in l]
        assert len(idx) == 1, f"{p.name}: {len(idx)} candidate markers"
        assert lines[idx[0] - 1].strip() == pf.expected_token(), (
            f"{p.name}: the line above the marker is not the token")


def test_tail_2_head_1_yields_the_token():
    """The instruction the SKILL prints about itself."""
    for p, text in _texts():
        tail2 = text.rstrip().splitlines()[-2:]
        assert tail2[0].strip() == pf.expected_token(), f"{p.name}: tail -2|head -1 is not the token"


def test_the_last_non_comment_line_is_the_token():
    """The wording the SKILL now uses, checked against the file."""
    for p, text in _texts():
        for line in reversed(text.rstrip().splitlines()):
            if line.strip().startswith("<!--"):
                continue
            assert line.strip() == pf.expected_token(), (
                f"{p.name}: last non-comment line is {line.strip()[:40]!r}, not the token")
            break
