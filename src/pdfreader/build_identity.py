"""R6 — WHICH pdfminer PRODUCED THIS OUTPUT.

Every artefact in this project already records the git revision that made it
(`provenance.identity()`), and that was enough while the reader was the only
variable. It is not enough now: the reader's answers depend on a PATCHED
pdfminer, and the patch is applied at install time into a venv or a user
site-packages that git knows nothing about. Two machines on the same commit
can emit different glyph names — which is exactly how ser7 ran 784 for a week
while this machine ran 820, one directory level down.

The failure this prevents is specific and silent. Stock pdfminer answers
"what Unicode is this cid" and drops the entry when it cannot; the fork adds
the twin question, cid -> PostScript glyph name. A machine that quietly ran
STOCK pdfminer would still produce a full `equations.json` — every `text`
present, every region right — with `glyphname` null or synthesised
throughout. Nothing in the output said which pdfminer wrote it, so the
difference between a reading worth measuring and one that lost its glyph
identity was invisible after the fact.

So the output says: the version string, whether the fork's surface is
actually present (asked of the loaded module, not of a file on disk), and the
sha256 of the patch that defines it.
"""
from __future__ import annotations

import functools
import hashlib
from pathlib import Path

#: The ONE patch (R1). Named relative to this file so there is no second path
#: convention to drift from.
PATCH = Path(__file__).resolve().parents[2] / "vendor" / "pdfminer-glyph-identity.patch"


def patch_sha256() -> str | None:
    try:
        return hashlib.sha256(PATCH.read_bytes()).hexdigest()
    except OSError:
        return None


@functools.lru_cache(maxsize=1)
def identity() -> dict:
    """{pdfminer, fork_present, patch_sha256, patch, path} for the LOADED module.

    `fork_present` is asked of the imported class, not inferred from a version
    string or the presence of a file: the question is what this process is
    actually running, and an installer that exited 0 is not an answer.
    """
    out: dict = {"pdfminer": None, "fork_present": False,
                 "patch": PATCH.name, "patch_sha256": patch_sha256(),
                 "path": None}
    try:
        import inspect

        import pdfminer
        from pdfminer.encodingdb import EncodingDB
        out["pdfminer"] = getattr(pdfminer, "__version__", None)
        out["path"] = str(Path(inspect.getfile(pdfminer)).parent)
        # The fork's own addition — "the twin of get_encoding".
        out["fork_present"] = hasattr(EncodingDB, "get_encoding_names")
    except Exception as e:                                   # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def summary() -> str:
    d = identity()
    return ("pdfminer %s, fork %s, patch %s"
            % (d.get("pdfminer") or "?",
               "present" if d.get("fork_present") else "ABSENT",
               (d.get("patch_sha256") or "?")[:12]))
