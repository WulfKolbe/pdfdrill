r"""Rung 0 — the terminal must say WHICH PROGRAM it is running.

THE DEFECT (owner, 2026-11-10)
------------------------------
"I am using some old code because the relevant code is hidden in some branch I
do not see in the terminal."

`~/.local/bin/pdfdrill` is an EDITABLE install: `__editable__.pdfdrill-0.1.0.pth`
puts the working checkout's `src/` on the path, so `pdfdrill` is not a release
— it is whatever is checked out in that one shared directory at the moment of
the call. Any session that switches branch there silently changes the program
the owner is testing.

Measured that day: at 10:35 the owner's drillui ran `t-0131-two-column-
paragraph-assembly` (f4adc3a7), a branch created forty minutes earlier by
another session, while `main` stood at 588aeb8c. Nothing on screen said so.
`pdfdrill doctor` — the command whose whole job is to report the state of the
installation — reported system tools, Python deps and API keys, and not one
word about which code they would run. The commit was already read in three
places (`buildstamp.py`, `callog.py`, `report_tex.py`) and written into
ARTIFACTS, where it is found afterwards by someone auditing a result, never at
the prompt by the person about to trust one.

WHY THE ENTRY POINT IS THE FIRST FIELD
--------------------------------------
Branch and commit describe a directory. They are worth nothing unless the
program being run is loaded FROM that directory, and with an editable install
that is exactly the thing nobody checks. drillui printed two different banners
nine hours apart — "via installed: ~user/.local/bin/pdfdrill" and "via
python -m pdfdrill (PYTHONPATH=.../src)" — which look like two different
programs and are the same files. So the test that matters asserts the reported
entry point IS the module Python actually imported, not that some path exists.

A CHECKOUT IS NOT GUARANTEED
----------------------------
A released tarball, a Docker layer and a fresh `pip install` have no `.git`.
Every field therefore has a defined answer when git cannot be consulted, and
the identity still names the entry point — which is always knowable. A field
that is unknown says so; it never silently reads as its reassuring value.
"""
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from pdfdrill import codeidentity as ci


REPO = Path(__file__).resolve().parent.parent


def _git(*args: str) -> str:
    r = subprocess.run(["git", "-C", str(REPO), *args],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def _in_checkout() -> bool:
    return bool(_git("rev-parse", "--git-dir"))


# ---------------------------------------------------------------------------
# identity() — the five fields
# ---------------------------------------------------------------------------

def test_identity_reports_all_five_fields():
    """Five fields, always present. A caller may not have to guess which of
    them this build happens to support."""
    ident = ci.identity()
    for key in ("entry_point", "branch", "commit", "tree", "upstream"):
        assert key in ident, f"identity() does not report {key!r}"


def test_the_entry_point_is_the_module_python_actually_imported():
    """THE assertion the editable install needs: not "a path exists" but "this
    is the code that will run". An editable install can point anywhere, and
    both of drillui's banners resolved to the same files while reading like
    two different programs."""
    ident = ci.identity()
    reported = Path(ident["entry_point"]).resolve()
    actual = Path(importlib.util.find_spec("pdfdrill").origin).resolve()
    assert reported == actual, (
        f"doctor would name {reported}, Python imports {actual}")
    assert reported.is_file()


def test_the_commit_is_head_of_the_checkout_that_holds_the_code():
    """The commit must be read from the directory the ENTRY POINT lives in, not
    from the process's cwd. `pdfdrill` is run from the document's folder — the
    library, ~/Downloads — and a cwd-relative `git rev-parse` there reports
    another repository's HEAD, or nothing, and would have reported `main` while
    the code was a branch."""
    if not _in_checkout():
        pytest.skip("not a git checkout (released tarball / installed wheel)")
    assert ci.identity()["commit"].startswith(_git("rev-parse", "--short=12", "HEAD"))


def test_the_branch_is_the_branch_of_that_checkout():
    if not _in_checkout():
        pytest.skip("not a git checkout")
    assert ci.identity()["branch"] == (_git("branch", "--show-current") or "(detached)")


def test_a_dirty_tree_is_never_reported_as_clean(tmp_path):
    """`tree` exists to answer "is the code on disk the code this commit names".
    An uncommitted edit is the one state where the commit is a LIE, so it is the
    one state that must not be silently rounded off."""
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "a.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "one"], cwd=repo, check=True)
    assert ci.tree_state(repo) == "clean"
    (repo / "a.py").write_text("x = 2\n")
    assert ci.tree_state(repo) == "dirty"
    # an untracked file is also a difference from the commit
    (repo / "b.py").write_text("y = 1\n")
    assert ci.tree_state(repo) == "dirty"


def test_no_field_is_blank_or_silently_true_outside_a_checkout(tmp_path):
    """Outside a checkout every git answer is UNKNOWN and says so. The failure
    this forbids is a build with no `.git` reporting `tree: clean` and
    `upstream: ancestor`, which are the reassuring values and are not known."""
    ident = ci.identity(root=tmp_path)           # a directory with no .git
    assert ident["branch"] == "(not a git checkout)"
    assert ident["commit"] == "(unknown)"
    assert ident["tree"] == "(unknown)"
    assert ident["upstream"] == "(unknown)"
    assert ident["entry_point"]                  # still knowable, still reported


# ---------------------------------------------------------------------------
# the upstream field — "is the fix I was promised in the code I run?"
# ---------------------------------------------------------------------------

def test_upstream_says_when_the_commit_is_not_on_origin_main(monkeypatch):
    """The field that would have told the owner, in one line, that their test
    was running a branch: 588aeb8c was `main`, f4adc3a7 was not on it."""
    # A clone with no `origin/main` to compare against cannot say, and must not
    # answer "on": `rev-parse --verify origin/main` printing nothing is the
    # whole of that case.
    monkeypatch.setattr(ci, "_git", lambda root, *a: "" if a[:2] == (
        "rev-parse", "--verify") else "x")
    monkeypatch.setattr(ci, "_git_ok", lambda root, *a: True)
    assert ci.upstream_state(REPO, "deadbeef") == "(unknown)"

    # origin/main exists; now the verdict is the `--is-ancestor` exit code, and
    # ONLY that. `_git` must keep answering so `is_checkout` stays true —
    # stubbing it to "" tests a tree with no git, which is a different case.
    monkeypatch.setattr(ci, "_git", lambda root, *a: "x")
    monkeypatch.setattr(ci, "_git_ok",
                        lambda root, *a: a[:2] != ("merge-base", "--is-ancestor"))
    assert ci.upstream_state(REPO, "deadbeef") == "not on origin/main"
    monkeypatch.setattr(ci, "_git_ok", lambda root, *a: True)
    assert ci.upstream_state(REPO, "deadbeef") == "on origin/main"


# ---------------------------------------------------------------------------
# doctor must print it — the command the owner actually types
# ---------------------------------------------------------------------------

def test_doctor_prints_the_code_identity():
    """A helper nobody calls fixes nothing. `doctor` is the command whose job is
    to report the installation, so the identity belongs in its output."""
    from pdfdrill import commands as C
    out = C.cmd_doctor()
    assert "Code:" in out, "doctor has no Code: section"
    for label in ("entry point:", "branch:", "commit:", "tree:", "origin/main:"):
        assert label in out, f"doctor does not print {label!r}"
    # and the values are the real ones, not placeholders
    ident = ci.identity()
    assert ident["entry_point"] in out
    assert ident["commit"] in out


def test_the_identity_is_one_block_near_the_top_of_doctor():
    """It is read before a decision, not found after one. Two of today's
    failures were the owner acting on output they had already scrolled past."""
    from pdfdrill import commands as C
    out = C.cmd_doctor()
    head = out.splitlines()[:14]
    assert any("Code:" in ln for ln in head), (
        "Code: is not in the first 14 lines of doctor's report")


def test_identity_line_is_short_enough_for_a_banner():
    """drillui prints one line, not a report. `identity_line()` is that line."""
    line = ci.identity_line()
    assert "\n" not in line
    assert len(line) <= 200
    if _in_checkout():
        assert _git("rev-parse", "--short=12", "HEAD")[:8] in line


def test_commit_is_a_hex_sha_or_the_unknown_marker():
    c = ci.identity()["commit"]
    assert c == "(unknown)" or re.fullmatch(r"[0-9a-f]{7,40}", c), c


# ---------------------------------------------------------------------------
# T-0136 item 2 — the one-line banner every command prints
# ---------------------------------------------------------------------------

def test_the_banner_names_branch_commit_and_date_and_no_path():
    """The owner's form: `pdfdrill main 588aeb8c 2026-11-03`.

    No path, because the owner asked for lines with "no paths, prefixes, or
    complex command lines" and this is the line they read first. The resolved
    entry point stays in `doctor`'s block, where it answers the editable-install
    question in full.
    """
    b = ci.banner()
    assert "\n" not in b
    assert b.startswith("pdfdrill ")
    assert "/" not in b, f"the banner carries a path: {b}"
    if _in_checkout():
        parts = b.split()
        assert parts[1] == (_git("branch", "--show-current") or "(detached)")
        assert _git("rev-parse", "--short=12", "HEAD").startswith(parts[2])
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[3]), parts


def test_modified_and_not_on_main_appear_only_when_true(monkeypatch):
    """Two words that must never be decoration. `MODIFIED` means the commit is
    not what is on disk; `NOT ON MAIN` is the one that would have told the owner
    at 10:35 that their test was running a branch."""
    monkeypatch.setattr(ci, "identity", lambda root=None: {
        "entry_point": "/x/pdfdrill/__init__.py", "branch": "main",
        "commit": "abc123abc123", "tree": "clean", "upstream": "on origin/main"})
    clean = ci.banner()
    assert "MODIFIED" not in clean and "NOT ON MAIN" not in clean

    monkeypatch.setattr(ci, "identity", lambda root=None: {
        "entry_point": "/x/pdfdrill/__init__.py", "branch": "t-something",
        "commit": "abc123abc123", "tree": "dirty",
        "upstream": "not on origin/main"})
    both = ci.banner()
    assert "MODIFIED" in both and "NOT ON MAIN" in both


def test_the_banner_goes_to_stderr_so_stdout_stays_machine_readable(tmp_path):
    """MEASURED, and the reason this is not on stdout: 8 test files in this
    suite call `json.loads` on a pdfdrill command's stdout, and 23 commands take
    `--json`. A banner line printed there would break every one of them, so a
    "first line of every command" on stdout is not available. stderr reaches the
    person at the terminal — both streams land there — and leaves stdout a
    parseable document.
    """
    import subprocess
    import sys as _sys
    env = {"HOME": os.environ.get("HOME", str(tmp_path)),
           "PATH": os.environ.get("PATH", ""),
           "PYTHONPATH": str(REPO / "src"),
           "PDFDRILL_SANDBOX": "1",
           "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([_sys.executable, "-m", "pdfdrill", "config", "--json"],
                       capture_output=True, text=True, env=env,
                       cwd=str(tmp_path), timeout=120)
    assert "pdfdrill " in r.stderr, f"no banner on stderr: {r.stderr[:200]!r}"
    # stdout must still be exactly a JSON document
    json.loads(r.stdout)


def test_every_command_prints_it_not_just_doctor(tmp_path):
    """`doctor` already reported the five fields; the defect was that the owner
    does not run `doctor` before every command. So the banner is in the dispatch
    path, and a cheap read-only command must carry it too."""
    import subprocess
    import sys as _sys
    env = {"HOME": os.environ.get("HOME", str(tmp_path)),
           "PATH": os.environ.get("PATH", ""),
           "PYTHONPATH": str(REPO / "src"),
           "PDFDRILL_SANDBOX": "1",
           "PYTHONDONTWRITEBYTECODE": "1"}
    for argv in (["config"], ["help"]):
        r = subprocess.run([_sys.executable, "-m", "pdfdrill", *argv],
                           capture_output=True, text=True, env=env,
                           cwd=str(tmp_path), timeout=120)
        assert r.stderr.startswith("pdfdrill "), (
            f"`pdfdrill {' '.join(argv)}` printed no banner: {r.stderr[:160]!r}")
