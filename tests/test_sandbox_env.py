"""
`PDFDRILL_SANDBOX=1` — answer as a KEYLESS install does.

The work ships to a sandbox that starts with no keys; the machine it is built
on has seven. Every lane decision is therefore a different decision on the two
machines, and the only way to check the one that matters is to be able to ask
for it. Under the switch every credential reads empty and `.env` is never read.
Nothing else changes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import env


def test_sandbox_is_off_by_default(monkeypatch):
    monkeypatch.delenv(env.SANDBOX_ENV, raising=False)
    assert env.sandbox() is False


def test_sandbox_reads_the_live_variable(monkeypatch):
    """Not a module constant: it must be settable per command."""
    monkeypatch.delenv(env.SANDBOX_ENV, raising=False)
    assert env.sandbox() is False
    monkeypatch.setenv(env.SANDBOX_ENV, "1")
    assert env.sandbox() is True


def test_an_explicit_off_value_is_off(monkeypatch):
    for off in ("", "0", "false", "no"):
        monkeypatch.setenv(env.SANDBOX_ENV, off)
        assert env.sandbox() is False, off


def test_every_credential_reads_empty_under_the_sandbox(monkeypatch):
    for name in env.CREDENTIAL_NAMES:
        monkeypatch.setenv(name, "a-real-looking-key")
    monkeypatch.setenv(env.SANDBOX_ENV, "1")
    for name in env.CREDENTIAL_NAMES:
        assert env.get(name) == "", name


def test_the_budget_still_works_under_the_sandbox(monkeypatch):
    """A budget of nothing is not the same as no budget: the metered lane's
    guard must keep working when the keys are gone, or the sandbox cannot be
    used to check what the guard does."""
    monkeypatch.setenv("PDFDRILL_OCR_BUDGET_EUR", "9.72")
    monkeypatch.setenv(env.SANDBOX_ENV, "1")
    assert env.get("PDFDRILL_OCR_BUDGET_EUR") == "9.72"


def test_the_budget_variable_is_not_a_credential():
    """Named explicitly rather than matched by shape, so a variable ABOUT a
    paid route is not mistaken for a key to one."""
    assert "PDFDRILL_OCR_BUDGET_EUR" not in env.CREDENTIAL_NAMES
    assert "MATHPIX_APP_KEY" in env.CREDENTIAL_NAMES
    assert "MAKORA_API_KEY" in env.CREDENTIAL_NAMES


def test_credentials_come_back_when_the_switch_is_off(monkeypatch):
    monkeypatch.setenv("MAKORA_API_KEY", "k")
    monkeypatch.setenv(env.SANDBOX_ENV, "1")
    assert env.get("MAKORA_API_KEY") == ""
    monkeypatch.delenv(env.SANDBOX_ENV)
    assert env.get("MAKORA_API_KEY") == "k"


def test_mathpix_creds_are_unavailable_under_the_sandbox(monkeypatch):
    from pdfdrill import mathpix_creds
    monkeypatch.setenv("MATHPIX_APP_ID", "i")
    monkeypatch.setenv("MATHPIX_APP_KEY", "k")
    assert mathpix_creds.available() is True
    monkeypatch.setenv(env.SANDBOX_ENV, "1")
    assert mathpix_creds.available() is False
