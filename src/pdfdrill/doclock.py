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
            with hold(Path(pdf), op):
                return fn(pdf, *a, **kw)
        return inner
    return deco
