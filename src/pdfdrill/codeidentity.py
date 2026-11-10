r"""Which program is this? — the five fields every pdfdrill run can state.

THE DEFECT (owner, 2026-11-10)
------------------------------
"I am using some old code because the relevant code is hidden in some branch I
do not see in the terminal."

`pdfdrill` is normally an EDITABLE install: a `__editable__.pdfdrill-*.pth`
puts the working checkout's `src/` on the path. So the console script is not a
release — it is whatever is checked out in that directory at the moment of the
call, and any session that switches branch there changes the program the owner
is testing, silently. Measured that morning: the owner's drillui ran a branch
created forty minutes earlier by another session while `main` stood six commits
behind an already-accepted stack, and nothing on screen said so.

The commit was already read by `buildstamp`, `callog` and `report_tex` — and
written into ARTIFACTS, where an auditor finds it afterwards, never at the
prompt by the person about to trust the output. This module is the same fact,
answered before the run instead of after it.

WHY THE ENTRY POINT IS THE FIRST FIELD
--------------------------------------
Branch, commit and tree describe a DIRECTORY. They mean nothing unless the code
being run was loaded from that directory, which is exactly what an editable
install makes uncertain. drillui printed "via installed: ~/.local/bin/pdfdrill"
and "via python -m pdfdrill (PYTHONPATH=.../src)" nine hours apart: two banners
that read like different programs and resolve to the same files. So the entry
point is reported as the resolved file of the imported package, and the git
questions are asked OF THAT FILE'S directory — never of the process's cwd,
which for pdfdrill is the document's folder (the library, ~/Downloads) and
would answer for another repository or for none.

UNKNOWN IS A VALUE
------------------
A released tarball, a wheel and a Docker layer have no `.git`. Each field then
reports `(unknown)` rather than its reassuring default: a build that cannot
check its tree must not print `clean`, and one that cannot reach `origin/main`
must not print that it is on it. `(unknown)` is a fact; `clean` would be a
guess wearing the clothes of a measurement.
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

#: Field order as `doctor` prints it. The entry point leads because it is the
#: one field that is always knowable and the one that validates the rest.
FIELDS = ("entry_point", "branch", "commit", "tree", "upstream")

_UNKNOWN = "(unknown)"
_NO_GIT = "(not a git checkout)"


def _git(root: Path, *args: str) -> str:
    """`git -C root …` stdout, or "" when git fails or is absent.

    Never raises: an identity that can crash is worse than one that says it
    does not know, because it would take down `doctor` — the command people run
    precisely when something is already wrong.
    """
    try:
        r = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True, timeout=10)
    except Exception:                                   # noqa: BLE001
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def _git_ok(root: Path, *args: str) -> bool:
    """True when `git -C root …` exits 0. For the predicates (`--is-ancestor`)
    that answer by exit code and print nothing, where "" is not an answer."""
    try:
        r = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True, timeout=10)
    except Exception:                                   # noqa: BLE001
        return False
    return r.returncode == 0


def entry_point() -> str:
    """The file Python would import as `pdfdrill`, resolved.

    Asked of the import system rather than of `__file__`, so it reports the
    package that WILL run even when this module was reached some other way.
    """
    spec = importlib.util.find_spec("pdfdrill")
    if spec is None or not spec.origin:
        return str(Path(__file__).resolve())
    return str(Path(spec.origin).resolve())


def code_root(entry: str | None = None) -> Path:
    """The directory whose git state describes the code being run: the checkout
    that holds the entry point, NOT the cwd."""
    p = Path(entry or entry_point()).resolve()
    return p.parent


def is_checkout(root: Path) -> bool:
    return bool(_git(root, "rev-parse", "--git-dir"))


def tree_state(root: Path) -> str:
    """`clean`, `dirty` or `(unknown)`.

    An uncommitted edit is the one state in which the commit is a LIE about the
    code on disk, so it is the one state that must never be rounded off.
    Untracked files count: a new module that changes behaviour is a difference
    from the commit even though git is not tracking it yet.
    """
    if not is_checkout(root):
        return _UNKNOWN
    # --porcelain prints one line per difference, untracked included.
    out = _git(root, "status", "--porcelain")
    if out:
        return "dirty"
    # Distinguish "no differences" from "the command failed and printed
    # nothing", which would otherwise both read as clean.
    return "clean" if _git_ok(root, "status", "--porcelain") else _UNKNOWN


def upstream_state(root: Path, commit: str) -> str:
    """Is this commit on `origin/main`? — "is the fix I was promised in the code
    I run?", in one field.

    `on origin/main` / `not on origin/main` / `(unknown)`. Unknown covers a
    clone with no remote, a fetch that has never run, and a tree with no git:
    all three are "cannot say", and saying "on" there is the failure this field
    exists to prevent.
    """
    if not commit or commit == _UNKNOWN or not is_checkout(root):
        return _UNKNOWN
    if not _git(root, "rev-parse", "--verify", "--quiet", "origin/main"):
        return _UNKNOWN
    if _git_ok(root, "merge-base", "--is-ancestor", commit, "origin/main"):
        return "on origin/main"
    return "not on origin/main"


def identity(root: Path | None = None) -> dict:
    """The five fields, as a dict. Every key in `FIELDS` is always present.

    `root` overrides the directory the git questions are asked of; it exists for
    the tests and for a caller that knows better. The entry point is reported
    either way, because it is knowable without git.
    """
    entry = entry_point()
    r = Path(root) if root is not None else code_root(entry)
    if not is_checkout(r):
        return {"entry_point": entry, "branch": _NO_GIT, "commit": _UNKNOWN,
                "tree": _UNKNOWN, "upstream": _UNKNOWN}
    commit = _git(r, "rev-parse", "--short=12", "HEAD") or _UNKNOWN
    branch = _git(r, "branch", "--show-current") or "(detached)"
    return {"entry_point": entry, "branch": branch, "commit": commit,
            "tree": tree_state(r), "upstream": upstream_state(r, commit)}


def commit_date(root: Path | None = None) -> str:
    """HEAD's commit date as YYYY-MM-DD, or `(unknown)`.

    The DATE is in the banner because a commit hash does not tell a person
    whether they are running this morning's code or last week's, and that was
    the owner's question. Author date would describe when the change was
    written; `%cd` describes the commit as it sits on this branch, which is what
    "which code is this" means.
    """
    r = Path(root) if root is not None else code_root()
    return _git(r, "log", "-1", "--format=%cd", "--date=short") or _UNKNOWN


def banner(root: Path | None = None) -> str:
    """The one line every command prints first: `pdfdrill main 588aeb8c 2026-11-03`.

    NO PATH. The owner asked for output with "no paths, prefixes, or complex
    command lines", and this is the line they read before trusting anything
    else; the resolved entry point stays in `doctor`'s block, where the
    editable-install question is answered in full.

    `MODIFIED` and `NOT ON MAIN` are appended ONLY when true, so neither is
    decoration. `MODIFIED` says the commit named is not what is on disk.
    `NOT ON MAIN` is the one that was missing at 10:35 on 2026-11-10: the
    owner's terminal was running a branch another session had created, and
    nothing said so.
    """
    i = identity(root)
    if i["commit"] == _UNKNOWN:
        return "pdfdrill (no commit recorded — not a git checkout)"
    out = f"pdfdrill {i['branch']} {i['commit'][:8]} {commit_date(root)}"
    if i["tree"] == "dirty":
        out += " MODIFIED"
    if i["upstream"] == "not on origin/main":
        out += " NOT ON MAIN"
    return out


def identity_line(root: Path | None = None) -> str:
    """One line with the entry point too, for a caller that wants the full
    answer on one line (drillui's startup prints a banner, not a report)."""
    i = identity(root)
    return (f"{i['branch']} {i['commit']} ({i['tree']}, {i['upstream']}) "
            f"— {i['entry_point']}")[:200]


def identity_report(root: Path | None = None) -> list[str]:
    """The `Code:` block `doctor` prints, as lines."""
    i = identity(root)
    return [
        "Code:",
        f"  entry point: {i['entry_point']}",
        f"  branch:      {i['branch']}",
        f"  commit:      {i['commit']}",
        f"  tree:        {i['tree']}",
        f"  origin/main: {i['upstream']}",
    ]
