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


# --------------------------------------------------------------------------- #
#  …and no copy of the WRONG instruction may come back.
#
#  905n fixed six places that said the token is "the last line of SKILL.md".
#  The literal last line is the END marker, so every one of them produced
#  "✗ preflight NOT attested: wrong token". A seventh survived in `doctor` —
#  the command a stuck user runs FIRST — and was found by an auditing session,
#  not by this file, because the tests above only read the SKILL. The
#  instruction lives in Python strings and in the docs, so that is where it has
#  to be checked.
# --------------------------------------------------------------------------- #
_ROOT = Path(__file__).resolve().parents[1]

#: Files that TEACH the gate. Anything here may mention the last line only to
#: say what it is NOT.
_TEACHING = [
    _ROOT / "src" / "pdfdrill" / "preflight.py",
    _ROOT / "src" / "pdfdrill" / "cli.py",
    _ROOT / "src" / "pdfdrill" / "commands.py",
    _ROOT / "QUICKSTART.md",
    _ROOT / "README.md",
    _ROOT / "bootstrap.sh",
    _ROOT / ".claude" / "skills" / "pdfdrill" / "commands.yaml",
]

#: The phrases that make an occurrence a CORRECTION rather than an instruction.
_DISAMBIGUATORS = (
    "not the token", "returns the marker", "returns that marker",
    "gives the marker", "gives you the", "gives that comment",
    "is the marker", "not an HTML comment", "just above", "just before",
    "above the END", "directly below", "is the line", "is NOT the token",
    "hands over the marker",
)

#: Phrases that make a line about the GATE rather than about some other text.
_GATE_WORDS = ("SKILL", "token", "TOKEN", "preflight", "DRILL-", "--ack")


def test_no_file_tells_the_reader_to_take_the_token_from_the_last_line():
    bad = []
    for path in _TEACHING:
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if "last line" not in line and "tail -1" not in line:
                continue
            if not any(w in line for w in _GATE_WORDS):
                continue            # a last line of something else entirely
            # Whitespace-normalised: the correct wording wraps, and
            # "…is not\n    an HTML comment" must still read as one phrase.
            window = " ".join(" ".join(lines[max(0, i - 2):i + 3]).split())
            if any(d in window for d in _DISAMBIGUATORS):
                continue            # says what the last line is NOT
            bad.append(f"{path.name}:{i + 1}: {line.strip()[:110]}")
    assert not bad, (
        "these point the reader at the last line of the SKILL, which is the "
        "END marker, so the ack is refused:\n  " + "\n  ".join(bad))


def test_both_copies_of_the_skill_yield_the_same_token():
    """pdfdrill hashes its BUNDLED copy; QUICKSTART tells the reader to `tail`
    the repo copy. While they are byte-identical that is fine, and the day
    skillsync regenerates one and not the other, the documented instruction
    starts handing over a token `--ack` rejects — with no way to see why."""
    tokens = {p.name + " @ " + str(p.parent.relative_to(_ROOT)):
              pf.compute_token(t) for p, t in _texts()}
    assert len(set(tokens.values())) == 1, (
        "the two SKILL copies hash differently, so one of them cannot attest: "
        + repr(tokens))
    assert set(tokens.values()) == {pf.expected_token()}


def test_preflight_says_where_the_skill_is():
    """Finding H: the command promised the path and never printed it."""
    import sys
    sys.path.insert(0, str(_ROOT / "src"))
    from pdfdrill import cli
    out = cli._do_preflight([])
    sk = pf.skill_path()
    assert sk is not None, "pdfdrill cannot find its own SKILL.md"
    assert str(sk) in out, (
        "`pdfdrill preflight` does not say where the SKILL is, so a reader who "
        "attests from the wrong copy gets 'wrong token' and no path:\n" + out)


def test_quickstart_only_promises_what_preflight_prints():
    """The defect was a doc and a command disagreeing; both sides are checked."""
    q = (_ROOT / "QUICKSTART.md").read_text(encoding="utf-8")
    if "where the SKILL is" not in q:
        return                      # the promise was removed instead — fine
    import sys
    sys.path.insert(0, str(_ROOT / "src"))
    from pdfdrill import cli
    assert str(pf.skill_path()) in cli._do_preflight([]), (
        "QUICKSTART promises `pdfdrill preflight` prints where the SKILL is")
