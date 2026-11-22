r"""A flag `commands.yaml` declares must not be refused by the CLI.

MEASURED 2026-11-22: sixteen commands rejected their own documented flags.

    $ pdfdrill profile x.pdf --json     -> "`pdfdrill profile` does not know --json"
    $ pdfdrill fonts x.pdf --force      -> "does not know --force"
    $ pdfdrill formulas x.pdf --plain   -> "does not know --plain"

`_pdf(args)` calls `_reject_unknown_flags(args[1:])` on the principle that
"anything the handler did not strip and did not want is unknown", so a
handler must REMOVE its flags before calling `_pdf`. These read the flag
and never strip it:

    return cmd_glyphlines(_pdf(args), force="--force" in args)

so the flag survives into the validator. Put it BEFORE the pdf instead and
`_pdf` reads it as the filename — both orders fail, by two routes.

`commands.yaml` declares the flag, `tools/skillsync.py` generates help that
advertises it, and the CLI refuses it: three sources of truth, and the one
the user meets is the one that says no.

THE VALIDATOR IS RIGHT TO EXIST — its own docstring records why.
`inkreport --render-provenance` was accepted, ignored, exited 0 and
measured the model's own LaTeX instead of the competing provenance, across
929 documents and 85,688 readings: "a plausible number for the wrong
question." It closed that class and broke these sixteen, because the strip
contract it relies on was enforced nowhere. This test is that enforcement.

A NONEXISTENT PDF IS ENOUGH, because `_pdf` validates the flags BEFORE it
resolves the path. So each case costs nothing and the whole surface is
covered.
"""
import pathlib

import pytest
import yaml

from pdfdrill import cli

MANIFEST = pathlib.Path(".claude/skills/pdfdrill/commands.yaml")


def _declared():
    """(command, flag) for every boolean/value flag the manifest declares."""
    raw = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    cmds = raw["commands"] if isinstance(raw, dict) else raw
    out = []
    for c in cmds:
        name = c.get("name")
        if not name or name not in getattr(cli, "HANDLERS", {}):
            continue
        for f in (c.get("flags") or []):
            flag = f.get("flag")
            if flag and flag.startswith("--"):
                out.append((name, flag, f.get("type") or "bool"))
    return out


CASES = _declared()


def test_the_manifest_declares_flags_at_all():
    assert len(CASES) > 50, "the manifest should declare many flags; got %d" % len(CASES)


@pytest.mark.parametrize("cmd,flag,kind", CASES,
                         ids=["%s%s" % (c, f) for c, f, _ in CASES])
def test_a_declared_flag_never_reaches_the_validator(cmd, flag, kind, tmp_path):
    r"""`_pdf` is given the command it is resolving for, and strips that
    command's declared flags itself.

    THE CONTRACT, not the command. An earlier version of this test called
    each handler with the flag; it ran for minutes, because a handler does
    real work, and it put a bare name through `_pdf`'s resolver, which
    handles arXiv ids and URLs — a unit test that can reach the network is
    wrong however fast it is. `_pdf` validates flags BEFORE it resolves
    anything, so an absolute path that does not exist exercises the whole
    contract for nothing.
    """
    missing = str(tmp_path / "nothing.pdf")
    try:
        cli._pdf([missing, flag], cmd=cmd)
    except TypeError as exc:
        # A VACUOUS PASS IS WORSE THAN A FAILURE. The first version of this
        # test swallowed every exception and only inspected the message, so
        # all 365 cases passed while `_pdf` did not take `cmd` at all —
        # `TypeError` carries no "does not know" and the assertion was
        # never reached. That is the `data-id` trap this repo already
        # records: a probe that answers the same on a perfect page and a
        # broken one.
        if "unexpected keyword" in str(exc) or "cmd" in str(exc):
            pytest.fail("`_pdf` does not accept `cmd`, so it cannot strip a "
                        "command's declared flags: %s" % exc)
        raise
    except Exception as exc:                 # noqa: BLE001 — any other failure is fine
        assert "does not know %s" % flag not in str(exc), (
            "`pdfdrill %s` refuses %s, which commands.yaml declares for it"
            % (cmd, flag))


def test_an_UNDECLARED_flag_is_still_refused(tmp_path):
    r"""The validator must keep doing its job. Its reason for existing:
    `inkreport --render-provenance` was accepted, ignored, exited 0 and
    measured the model's own LaTeX instead of the competing provenance
    across 929 documents and 85,688 readings — "a plausible number for the
    wrong question"."""
    with pytest.raises(ValueError) as e:
        cli._pdf([str(tmp_path / "nothing.pdf"), "--nonsense-flag"],
                 cmd="glyphlines")
    assert "does not know --nonsense-flag" in str(e.value)


def test_a_flag_declared_for_ANOTHER_command_is_refused(tmp_path):
    """Stripping is per command, not a global allow-list: `--titles` is
    `docs`'s flag and `glyphlines` must still refuse it."""
    with pytest.raises(ValueError) as e:
        cli._pdf([str(tmp_path / "nothing.pdf"), "--titles"], cmd="glyphlines")
    assert "does not know --titles" in str(e.value)
