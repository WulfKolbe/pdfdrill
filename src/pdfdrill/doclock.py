"""297 — one writer per document, enforced by O_EXCL.

Every build command writes fixed names beside the PDF: `report.tex`,
`report.aux`, `report.pdf`, `<stem>.docmodel.json`, `report.regions.ink.json`.
Two processes on one document do not collide loudly — they interleave. The
expensive case is LaTeX: a shared `.aux` means pass 2 of one build reads the
cross-references pass 1 of ANOTHER build wrote. It compiles, it produces a PDF,
and every `\\ref` points at a different document's equation numbers. It
succeeds, and it is wrong — the same class as the header row `compare` could
not see (293) and the `A_eq_B` branch that never fired.

So the second process refuses. `os.open(O_CREAT|O_EXCL)` is the only primitive
here that is atomic on every filesystem worth using; a `path.exists()` check
followed by a write is not a lock, it is a race with a comment.

Two behaviours the naive version gets wrong:

**A crash must not brick the document.** A killed process leaves its lock file
behind forever. So the holder records pid AND hostname, and a lock whose pid is
dead ON THIS HOST is broken automatically. A lock from another host is never
broken — we cannot see that machine's process table, and guessing costs exactly
what the lock was bought to prevent.

**Nesting must not deadlock.** `--ensure` runs the prerequisite chain inside one
process, so `reporttex` can call `model` while already holding the document. A
re-entrant acquisition by the same process is a pass-through, not a second lock.
"""

from __future__ import annotations

import errno
import json
import os
import socket
import sys
import time
from contextlib import contextmanager
from pathlib import Path

#: The lock sits beside the PDF and is named after it, so one document is one
#: lock however many artifacts it owns. A dotfile: it is machine state, not a
#: build product, and it must not turn up in the library's file census.
LOCK_SUFFIX = ".lock"


class DocumentBusy(RuntimeError):
    """Another process is writing this document. Never raised for our own."""


def lock_path(pdf: Path) -> Path:
    pdf = Path(pdf)
    return pdf.parent / ("." + pdf.name + LOCK_SUFFIX)


#: Paths this process holds, so a nested acquisition is recognised as ours.
#: Values are the depth, because the inner `with` must not release the outer.
_HELD: dict[str, int] = {}


def _payload(op: str) -> dict:
    return {"pid": os.getpid(), "host": socket.gethostname(), "op": op,
            "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "argv": " ".join(sys.argv[:4])}


def _alive(pid: int) -> bool:
    """Is this pid running on THIS host? PermissionError means yes-but-not-ours."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True                       # cannot tell: assume the holder lives
    return True


def read_holder(pdf: Path) -> dict | None:
    """The recorded holder of `pdf`, or None when the document is free."""
    return _read_raw(lock_path(pdf))


def _stale(holder: dict) -> bool:
    return (holder.get("host") == socket.gethostname()
            and int(holder.get("pid") or 0) > 0
            and not _alive(int(holder["pid"])))


def _acquire(p: Path, op: str) -> None:
    body = json.dumps(_payload(op)).encode("utf-8")
    for attempt in (0, 1):
        try:
            fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            pass
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                pass
            else:
                raise
        else:
            try:
                os.write(fd, body)
            finally:
                os.close(fd)
            return
        holder = _read_raw(p)
        if attempt == 0 and holder and _stale(holder):
            try:
                os.unlink(str(p))         # its process is gone; take it over
            except OSError:
                pass
            continue
        h = holder or {}
        raise DocumentBusy(
            "another pdfdrill is writing this document: %s (pid %s on %s, "
            "started %s). Refusing rather than interleaving — a shared .aux "
            "produces a PDF built from the other build's cross-references, "
            "which compiles and is wrong. If that process is gone, delete %s."
            % (h.get("op", "?"), h.get("pid", "?"), h.get("host", "?"),
               h.get("started", "?"), p))


def _read_raw(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        # A truncated lock (killed between create and write) still means HELD.
        # Reporting it as free is the one error that defeats the whole file.
        return {"pid": 0, "host": "?", "op": "?", "started": "?", "argv": "?"}


#: errnos that mean "this directory cannot be written by anyone", so there is
#: nothing to serialise. A read-only location fails the BUILD on its own terms
#: a moment later; failing it here, on the lock, would only disguise the cause.
_UNWRITABLE = (errno.EACCES, errno.EPERM, errno.EROFS)


@contextmanager
def hold(pdf: Path, op: str):
    """Exclusive write access to `pdf`'s artifacts for the body's duration.

    Re-entrant within one process. Releases only the lock it created, checked
    by pid — so a stale break that handed the document to someone else is never
    undone by the loser's `finally`.
    """
    p = lock_path(pdf)
    key = str(p.resolve() if p.parent.is_dir() else p)
    if key in _HELD:                      # ours already (an --ensure chain)
        _HELD[key] += 1
        try:
            yield p
        finally:
            _HELD[key] -= 1
            if _HELD[key] <= 0:
                _HELD.pop(key, None)
        return
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        _acquire(p, op)
    except OSError as exc:
        if exc.errno not in _UNWRITABLE:
            raise
        yield p                            # unwritable dir: nothing to guard
        return
    _HELD[key] = 1
    try:
        yield p
    finally:
        _HELD.pop(key, None)
        h = _read_raw(p)
        if h and int(h.get("pid") or -1) == os.getpid():
            try:
                os.unlink(str(p))
            except OSError:
                pass


def writer(op: str):
    """Decorate a command whose first argument is the PDF it writes.

    Applied at the handler, not inside it, so the lock spans EVERY write the
    command makes — including the ones a future edit adds. A guard placed
    around one write protects that write; a guard placed around the command
    protects the document.
    """
    import functools

    def deco(fn):
        @functools.wraps(fn)
        def inner(pdf, *a, **kw):
            pdf = ensure_doc_folder(pdf)
            with hold(Path(pdf), op):
                return fn(pdf, *a, **kw)
        return inner
    return deco


#: 830 — pdfdrill's own PDFs, which are never a reason to promote a folder.
#: 856 — the SPLIT PARTS are our output too. `evidence-[a-z]+` admits
#: `evidence-formula` and nothing else, so `evidence-formula-01.pdf` read as a
#: second document and 854 would have promoted it into its own folder — the
#: defect 854 had just closed, walked straight back into by a new file name.
#: Caught before any part was built, because inkdrill asked for the naming
#: convention first. `-\d+` and `-part\d+` are both admitted, since their glob
#: accepts either and the choice should not be able to reintroduce this.
_GENERATED_PDF = __import__("re").compile(
    r"^(report|B|residuals|formula-report|compare"
    r"|evidence-[a-z]+(?:-(?:part)?\d+)?)\.pdf$|"
    r"\.(formelregister|beamer)\.pdf$", __import__("re").I)


def _has_a_second_document(pdf) -> bool:
    """Is there another document PDF beside this one?"""
    try:
        for sib in pdf.parent.glob("*.pdf"):
            if sib == pdf or not sib.is_file():
                continue
            if _GENERATED_PDF.search(sib.name):
                continue
            return True
    except OSError:
        pass
    return False


#: The last relocation `ensure_doc_folder` performed, for the CLI and the
#: verdict to resolve a path the handler moved. A module global because the
#: move happens inside the write decorator, several frames below anything that
#: prints or assesses — the same shape as `sources._LAST_ADOPTION`.
_LAST_MOVE: "tuple[Path, Path] | None" = None


def last_move() -> "tuple[Path, Path] | None":
    """(from, to) of the last relocation this process performed, or None."""
    return _LAST_MOVE


def reset_last_move() -> None:
    global _LAST_MOVE
    _LAST_MOVE = None


def current_path(pdf) -> "Path":
    """Where `pdf` IS now, after any relocation this process performed.

    Answers from the published move, never by probing the filesystem for a
    `<stem>/<stem>.pdf` that might belong to another document entirely.
    """
    p = Path(pdf)
    mv = _LAST_MOVE
    if mv is not None:
        try:
            if Path(mv[0]).resolve() == p.resolve():
                return Path(mv[1])
        except OSError:
            if str(mv[0]) == str(p):
                return Path(mv[1])
    return p


#: [moves, left]: the last automatic filing's (src, dst) moves, and the
#: same-stem files it left where they were because pdfdrill did not write them.
_LAST_FILING: list = [[], []]


def last_filing():
    """(moves, left) of the last `ensure_doc_folder` that moved anything."""
    return _LAST_FILING[0], _LAST_FILING[1]


def ensure_doc_folder(pdf):
    """Give a loose PDF its own folder before anything writes beside it.

    830 — EVERY BUILD COMMAND WRITES FIXED NAMES. `report.pdf`,
    `evidence-equation.pdf`, `residuals.pdf`, `model.docmodel.json` are the
    same names for every document, so two PDFs drilled in one directory do not
    collide occasionally — they collide always, and the second silently
    overwrites the first's reports. The library never showed this because its
    documents already live in `<stem>/<stem>.pdf`; a working directory like
    ~/Downloads is where it bites.

    The move is `relocate`'s phase 1 pointed at the PDF's OWN parent, not at
    the configured library: same planner, so the PDF, its sidecar, the
    flattened `X.pdf.drill/` blobs and every `X.*` sibling travel together. A
    `.lines.json` left behind is worse than no move at all — the next build
    would not find the MathPix conversion it is supposed to read.

    Already self-contained (`<stem>/<stem>.pdf`) is a no-op, which is every
    document in the library. `PDFDRILL_NO_AUTOFOLDER=1` disables it for a
    caller that manages its own layout.
    """
    import os
    p = Path(pdf).resolve()
    if os.environ.get("PDFDRILL_NO_AUTOFOLDER"):
        return pdf
    if not p.is_file() or p.parent.name == p.stem:
        return pdf
    # ONLY WHERE A COLLISION IS POSSIBLE — a directory holding one document is
    # already that document's folder, and moving it buys nothing while
    # surprising every caller that expects its artefacts beside the path it
    # passed. The collision needs a SECOND document: `doc_dir = pdf.parent`
    # (commands.py) sends `evidence-<kind>.pdf` and `residuals.pdf` there
    # under names that are the same for every document.
    #
    # pdfdrill's OWN output is not a second document. `report.pdf`,
    # `evidence-*.pdf`, `residuals.pdf` and `B.pdf` are artefacts of the
    # document already there; counting them would make the first build
    # promote the folder it had just written into.
    # 854 — AND NEVER PROMOTE OUR OWN OUTPUT. `_has_a_second_document` asks
    # whether the SIBLINGS are artefacts; nothing asked whether the SUBJECT is.
    # So writing `evidence-formula.pdf` into a folder that also holds the
    # document promoted the artefact: `0902.0431/evidence-formula/
    # evidence-formula.pdf` plus an empty sidecar, and the next build wrote a
    # fresh flat one beside it, leaving the first orphaned where a reader was
    # still looking. Measured: 2,667 such nested folders across the library,
    # nine in 0902.0431 alone (`report/` 32 MB, `B/` 38.8 MB), every sidecar
    # with `facts: []` because nothing ever drilled them.
    #
    # The 09-17 damage predates this function, so it was not the cause — but it
    # reproduced here on the first try, so it was the next cause.
    if _GENERATED_PDF.search(p.name):
        return pdf
    if not _has_a_second_document(p):
        return pdf
    target = p.parent / p.stem
    if target.exists() and not target.is_dir():
        return pdf                       # a FILE of that name: leave well alone
    try:
        from .relocate import apply_relocation, LAST_MOVES
        # P11 — ONLY WHAT PDFDRILL WROTE. The planner takes every `X.*`
        # sibling for `relocate`, which a user asks for; filed automatically,
        # it moved a session's `lib_3f.out` beside `lib_3f.pdf`, and would
        # have moved an owner's `X.tex`. Foreign siblings stay, and are named.
        apply_relocation(p, p.parent, owned_only=True)
        import glob as _g
        _LAST_FILING[:] = [list(LAST_MOVES),
                           sorted(x for x in p.parent.glob(_g.escape(p.stem) + ".*")
                                  if x.is_file())]
    except Exception:                                        # noqa: BLE001
        return pdf                       # never fail a command over tidiness
    # A Path, not a str: the handlers take `.stem`/`.parent` off this value,
    # and `pdf` arrives as a Path from every caller. Returning a string here
    # failed 122 tests with `'str' object has no attribute 'stem'`.
    moved = target / p.name
    if not moved.is_file():
        return pdf
    # A MOVE THE USER DID NOT ASK FOR MUST BE PUBLISHED, and for the same
    # reason `sources.adopt_into_doc_folder` publishes `_LAST_ADOPTION` (the
    # 2026-10-22 audit): the caller cannot find what the handler wrote.
    #
    # THE DEFECT THIS FIXES. This function runs inside `@_writes`, so it moves
    # the document AFTER the CLI resolved the path and BEFORE the handler. In
    #
    #     pdf = _pdf(args)
    #     return _with_verdict(cmd_md(pdf, ...), pdf, md=True)
    #
    # `cmd_md` receives the moved path and writes its sidecar in the new
    # self-contained layout, while `_with_verdict` still holds the ORIGINAL
    # path and builds a Sidecar for the legacy layout — an empty one. Measured,
    # installed entry point, two PDFs in one folder:
    #
    #     Extracted 2963 words of Markdown across 3 pages ...
    #     pdfdrill verdict: NOT REACHED — text: no reading
    #
    # One document, two possible sidecars, resolved twice with different
    # answers. `blob_dir_for`'s own docstring warned of the shape one level
    # down ("every ad-hoc scan that walked DIRECTORIES ... reads one
    # document's sidecar against the other's model").
    #
    # So the layout is resolved ONCE, here, where the move happens, and every
    # later reader asks `current_path` instead of the filesystem. Looking in
    # both places would be a heuristic over a wrong resolution.
    global _LAST_MOVE
    _LAST_MOVE = (p, moved)
    return moved
