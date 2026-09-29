"""
827 — drillui as a command FILE, not only a keyboard.

Piping a file of commands already worked and nothing had to be built for it:
`input()` reads a pipe as happily as a terminal, and `interactive` was already
`sys.stdin.isatty()`. What did not work was READING the result.

  * A `#` line was sent to the LLM as a question. Against an empty context that
    answered "no document yet", so every comment in a generated file became an
    error in the transcript — and a generated file is mostly comments, because
    that is how you say which document a block belongs to.
  * Nothing echoed the command. `input("\\n? ")` writes its prompt before the
    read, which is right for someone typing and wrong for a pipe: the prompt
    lands above a line it does not belong to, a skipped line leaves a bare `?`,
    and the transcript is a column of prompts with unattributed output under
    them.

No drillui command begins with `#`, so the character was free to take.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAT = ROOT / "tools" / "drillui_chat.py"


def run(script: str, timeout: int = 180) -> str:
    """Feed `script` to the REPL on stdin and return everything it printed."""
    p = subprocess.run([sys.executable, str(CHAT), "--src", "src"],
                       input=script, capture_output=True, text=True,
                       cwd=str(ROOT), timeout=timeout)
    return p.stdout + p.stderr


def test_a_file_of_commands_runs_line_by_line():
    out = run("pwd\npwd\nquit\n")
    assert out.count("? pwd") == 2


def test_a_comment_is_not_a_question():
    """The failure this guards: `#` reached the LLM path and the comment came
    back as 'no document yet'."""
    out = run("# ── the WRAP document ──\npwd\nquit\n")
    assert "the WRAP document" not in out
    assert "no document yet" not in out.split("? pwd")[0].split("Quit:")[-1]
    assert "? pwd" in out


def test_a_blank_line_is_ignored():
    """A blank line must not end the session or reach the LLM. It DOES leave a
    bare `?` behind, and that is the accepted cost of the prompt below."""
    out = run("\n\npwd\nquit\n")
    assert "? pwd" in out


def test_the_prompt_is_written_even_over_a_pipe():
    """832 — THE PROMPT IS A PROTOCOL. `drillui_bridge.ts` spawns this REPL
    over a pipe and says so in its own header: "The REPL writes its `\n? `
    prompt to stdout after each turn; we detect that, strip it, and tell the
    client it's its turn to read a line."

    827 made the prompt conditional on `sys.stdin.isatty()` to keep a scripted
    transcript tidy. Over a pipe that wrote no prompt at all, the bridge never
    saw a turn, and the browser sat at "connecting…" with the bridge up and
    listening. Cosmetics must not outrank a protocol.
    """
    out = run("pwd\nquit\n")
    assert "\n? " in out, "the bridge detects this exact string; without it no turn is announced"
    assert out.count("? ") >= 2, "one prompt per turn"


def test_each_command_is_echoed_above_its_output():
    """Anchored on what `pwd` PRINTS, not on the first `/home` in the output:
    the startup banner names the PYTHONPATH and matched that first."""
    out = run("pwd\nquit\n")
    after = out.split("? pwd", 1)
    assert len(after) == 2, "the command was not echoed at all"
    assert after[1].lstrip().startswith("/"), \
        "the path pwd printed must follow its echo, not precede it"


def test_the_commands_listing_still_answers():
    """A scripted run must reach the same dispatch a typed one does."""
    out = run("commands\nquit\n")
    assert "inspect" in out and "evidence" in out


def test_quit_ends_the_script():
    out = run("quit\npwd\n")
    assert "? pwd" not in out
