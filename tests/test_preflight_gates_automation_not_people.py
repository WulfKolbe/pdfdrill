r"""The preflight gate applies to an automated caller, not to a person typing.

OWNER'S DECISION, 2026-11-10, asked three times and answered on the third:
"Gate only non-interactive callers."

WHAT THE GATE IS FOR, in its own words: "pdfdrill output looks authoritative,
so using it without the usage rules produces silently-WRONG results." That risk
is an LLM or a script driving 170 commands from a half-read SKILL. It is not a
person who typed one command and is about to read the answer themselves.

WHAT IT COST. The attestation is per working directory, so the owner had to run
`pdfdrill preflight --ack <TOKEN>` again in every new folder — and the owner's
stated requirement for these tests was "no path, prefixes, or complex command
lines". `pdfdrill md 2209.02970` exited 2 for them, which is how two OWNER-TESTS
lines sat at NOT RUN and `pdfdrill acceptance` exited 3.

WHY `stdin.isatty()` IS THE RIGHT DISCRIMINATOR HERE, measured rather than
assumed:

  * the owner in a shell          stdin IS a tty      -> not gated
  * this session's own probe      stdin is NOT a tty  -> gated (correct: an
                                                        agent is exactly the
                                                        caller the gate is for)
  * drillui                       already exempt       -> `drillui_chat.py:81`
                                                        sets PDFDRILL_NO_PREFLIGHT=1,
                                                        so the front end the
                                                        owner actually uses was
                                                        never the problem

That last fact is why a tty test works at all. drillui pipes BOTH streams, so if
it had relied on the gate this test would be wrong — the first version of this
reasoning assumed it did, and checking `drillui_chat.py` is what corrected it.

STDIN ONLY, not stdin AND stdout: `pdfdrill md 2209.02970 | less` is still a
person at a terminal, and requiring stdout to be a tty would re-gate them the
moment they piped the output.

THE HOLE, STATED. An automated caller that runs with a tty on stdin — an agent
harness using a pty — is not gated. It is a narrower hole than the one the
owner was living with, and the env override (`PDFDRILL_NO_PREFLIGHT=1`) and the
attestation both still exist, but it is a hole and it is not hidden.
"""
import sys

import pytest

from pdfdrill import preflight


GATED = "md"          # a build/extract command
OPEN = "doctor"       # in preflight.EXEMPT


@pytest.fixture(autouse=True)
def _unattested(monkeypatch, tmp_path):
    """A working directory with no attestation, and enforcement on — the state
    in which the gate has anything to say."""
    monkeypatch.setattr(preflight, "is_attested", lambda: False)
    monkeypatch.setattr(preflight, "enforced", lambda: True)


def _set_tty(monkeypatch, value: bool):
    class _S:
        def isatty(self):
            return value
    monkeypatch.setattr(sys, "stdin", _S())


def test_a_person_at_a_terminal_is_not_gated(monkeypatch):
    """The owner typing one command. This is the whole change."""
    _set_tty(monkeypatch, True)
    assert preflight.blocks(GATED, []) is False


def test_an_automated_caller_is_still_gated(monkeypatch):
    """An LLM or a script: no tty, no attestation, build command -> refused.
    The gate's reason for existing is unchanged."""
    _set_tty(monkeypatch, False)
    assert preflight.blocks(GATED, []) is True


def test_an_open_command_is_never_gated_either_way(monkeypatch):
    """`EXEMPT` still decides first: a read-only command is open to everyone."""
    for tty in (True, False):
        _set_tty(monkeypatch, tty)
        assert preflight.blocks(OPEN, []) is False


def test_the_attestation_still_works_for_automation(monkeypatch):
    """An automated caller that HAS read the SKILL and acked is not punished for
    being automated — the attestation remains the way through."""
    _set_tty(monkeypatch, False)
    monkeypatch.setattr(preflight, "is_attested", lambda: True)
    assert preflight.blocks(GATED, []) is False


def test_the_env_override_still_works(monkeypatch):
    """`PDFDRILL_NO_PREFLIGHT=1` is how drillui and CI already run
    (drillui_chat.py:81). It must keep working, or this change breaks the front
    end the owner uses."""
    _set_tty(monkeypatch, False)
    monkeypatch.setattr(preflight, "enforced", lambda: False)
    assert preflight.blocks(GATED, []) is False


def test_interactive_reads_stdin_not_stdout(monkeypatch):
    """`pdfdrill md 2209.02970 | less` is still a person. Requiring stdout to be
    a tty would re-gate the owner the moment they piped the output."""
    _set_tty(monkeypatch, True)

    class _Piped:
        def isatty(self):
            return False
    monkeypatch.setattr(sys, "stdout", _Piped())
    assert preflight.interactive() is True
    assert preflight.blocks(GATED, []) is False


def test_a_broken_stdin_is_treated_as_automation(monkeypatch):
    """Fail CLOSED. If `isatty` raises — a detached process, a closed handle —
    the answer is "not a person", so the gate stays on. A guard that opens on
    an error is not a guard."""
    class _Broken:
        def isatty(self):
            raise OSError("no stdin")
    monkeypatch.setattr(sys, "stdin", _Broken())
    assert preflight.interactive() is False
    assert preflight.blocks(GATED, []) is True
