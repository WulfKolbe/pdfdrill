"""GLYPHDRILL3 as a TOOL: a scan's pixels -> text, free, on the CPU (T-0157/B8).

WHAT IT ADDS THAT PDFDRILL DOES NOT HAVE. A scan with no text layer and no
author's source had, on a keyless install, only the geometry lane: boxes with a
type and NO WORDS (`docs/LANES.md` lane 5). `gd3` reads the words from the
page's own pixels, with no GPU and no key — but its compiled-in fonts read no
scan, so a scanned document is read with ITS OWN DICTIONARY, learned once from
five of its pages read by any reader. With the local Ollama host (6c41432d)
those five pages are free too, so the whole document costs five pages of a
local model and then nothing.

    1  gd3-learn pick PDF         the five pages to have read
    2  <sidecar>/gd3/<sha>.trees  already learned -> step 5
    3  read those five pages      pdfdrill's own model lane, local and free
    4  gd3-learn learn            -o <sidecar>/gd3/<sha>.trees
    5  gd3 --refs <sha>.trees     the reading of every page

THE PATHS ARE ALL EXPLICIT, which is the point. `glyphdrill3`, the wrapper
shipped with that tree, caches a learned dictionary in `$here/build/docrefs`
and would write into GLYPHDRILL3; T-0145 (the owner, 2026-11-14) says read
that tree only. So this module calls `build/gd3` and `tools/gd3-learn`
directly, with `-o` and `--refs` pointing into the DOCUMENT's sidecar, and
sets `TMPDIR` into pdfdrill's own `work/run-files` for the ghostscript children
those tools spawn.

WHERE THE TREE IS, and why there is no default. `glyphdrill3` on PATH is a
declaration, the same one poppler and ghostscript make; the config key
`glyphdrill3_home` is the other. There is deliberately NO fallback to
`~/GLYPHDRILL3`: a tool found at a guessed path makes the lane's availability —
and every measurement that depends on it — an accident of which machine ran it,
which is the defect 6c41432d had to be corrected for.

A dictionary is a fact about ONE document (gd3 refuses any other PDF with exit
4), so it lives in that document's sidecar, keyed by the PDF's sha256, beside
the reading it was learned from. A dictionary gd3-learn REJECTS (its labels too
weak, exit 3) is remembered as `<sha>.rejected`, so a second run does not spend
five pages to be told the same thing.

Pure stdlib; the tools are subprocesses, like poppler's.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from . import config
from .env import get

#: How many pages `gd3-learn pick` is asked for — its own default, named here
#: because the budget note in PROTOCOL.md is written in fives.
LEARN_PAGES = 5
#: `gd3-learn pick` renders every page through the band stage; `gd3 lines`
#: reads every page. Both are minutes on a long document, not seconds.
TIMEOUT = 3600.0


def home() -> "Path | None":
    """The GLYPHDRILL3 tree, or None when none is declared."""
    env = get("PDFDRILL_GLYPHDRILL3", "")
    if env:
        p = Path(env).expanduser()
        return p if (p / "build").is_dir() or p.is_dir() else None
    found = shutil.which("glyphdrill3")
    if found:
        # the wrapper sits in the tree's root; follow a symlink first
        return Path(os.path.realpath(found)).parent
    cfg = str(config.get("glyphdrill3_home", "") or "")
    if cfg:
        p = Path(cfg).expanduser()
        return p if p.is_dir() else None
    return None


def binary() -> "Path | None":
    h = home()
    if h is None:
        return None
    b = h / "build" / "gd3"
    return b if b.is_file() and os.access(b, os.X_OK) else None


def learn_tool() -> "Path | None":
    h = home()
    if h is None:
        return None
    t = h / "tools" / "gd3-learn"
    return t if t.is_file() else None


def version() -> str:
    """The tree's own commit, for the artefact and for `doctor`, or "" when the
    tree is not a git work tree of its own.

    IT MUST BE THAT TREE'S COMMIT AND NOBODY ELSE'S. Measured: a `git archive`
    export of GLYPHDRILL3 unpacked under pdfdrill's `work/run-files` reported
    `ddb6c448` — PDFDRILL's HEAD, because git walked up out of the export and
    found this repository. A provenance string naming the wrong repository is
    worse than none at all: it would be written into readings and reports as
    the version that read the page. So the toplevel must BE the declared tree.
    """
    h = home()
    if h is None:
        return ""
    try:
        top = subprocess.run(["git", "-C", str(h), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10)
        if top.returncode != 0:
            return ""
        if Path((top.stdout or "").strip()).resolve() != Path(h).resolve():
            return ""                      # h is inside SOMEBODY ELSE's repo
        out = subprocess.run(["git", "-C", str(h), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return (out.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def available() -> bool:
    return binary() is not None and learn_tool() is not None


def why_unavailable() -> str:
    """Grounded absence: what was looked for and where."""
    h = home()
    if h is None:
        return ("GLYPHDRILL3 is not declared: put `glyphdrill3` on PATH, or set "
                "`glyphdrill3_home` with `pdfdrill config` (or "
                "PDFDRILL_GLYPHDRILL3 for one run). There is no default path on "
                "purpose — a tool found at a guessed location makes a lane's "
                "availability an accident of the machine.")
    if binary() is None:
        return (f"{h}/build/gd3 is missing or not executable — run `make` in "
                f"that tree (one Makefile in the root, DESIGN D-6).")
    if learn_tool() is None:
        return f"{h}/tools/gd3-learn is missing: that tree is incomplete."
    return ""


def tidy(msg: str, trees: Path) -> str:
    """`gd3-learn`'s own line, fit to be read in a report: without its name
    repeated (the caller prints it) and with the temporary `-o` path it was
    given replaced by the dictionary's real name. A report that quotes an
    internal `.part` path tells the reader to look for a file that is gone."""
    t = (msg or "").strip()
    for pre in ("gd3-learn: ",):
        if t.startswith(pre):
            t = t[len(pre):]
    part = str(trees.with_suffix(".part"))
    return t.replace(part, trees.name).replace(str(trees), trees.name)


def sha256(pdf: Path) -> str:
    h = hashlib.sha256()
    with open(pdf, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def doc_dir(blob_dir: Path) -> Path:
    """Where this document's dictionary and its teacher reading live."""
    d = Path(blob_dir) / "gd3"
    d.mkdir(parents=True, exist_ok=True)
    return d


_IDENTITY: dict = {}


def identity() -> str:
    """WHICH gd3 learned a dictionary: its commit, or -- for a tree that is
    not a git work tree of its own, such as a `git archive` export -- the
    sha256 of its two programs; plus the sha256 of its data checksums
    (`data/blobmetric/SHA256SUMS`). Audit A08: a dictionary or a refusal
    learned by one gd3 is a fact about THAT gd3, and a new one must learn
    again rather than trust it. Cached per process and tree.
    """
    h = home()
    if h is None:
        return ""
    if str(h) in _IDENTITY:
        return _IDENTITY[str(h)]
    who = version()
    if not who:
        dg = hashlib.sha256()
        for part in (Path(h) / "build" / "gd3", Path(h) / "tools" / "gd3-learn"):
            try:
                with open(part, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        dg.update(chunk)
            except OSError:
                dg.update(b"-")
        who = "x" + dg.hexdigest()[:12]
    try:
        sums = (Path(h) / "data" / "blobmetric" / "SHA256SUMS").read_bytes()
    except OSError:
        sums = b""
    out = hashlib.sha256(f"{who}|".encode() + sums).hexdigest()[:12]
    _IDENTITY[str(h)] = out
    return out


def _key(pdf: Path) -> str:
    """The PDF's sha256 and the identity of the gd3 that learns (A08)."""
    who = identity()
    return f"{sha256(pdf)}.{who}" if who else sha256(pdf)


def trees_path(blob_dir: Path, pdf: Path) -> Path:
    return doc_dir(blob_dir) / f"{_key(pdf)}.trees"


def rejected_path(blob_dir: Path, pdf: Path) -> Path:
    return doc_dir(blob_dir) / f"{_key(pdf)}.rejected"


def self_trees_path(blob_dir: Path, pdf: Path) -> Path:
    """A dictionary the document taught ITSELF (T-0171), kept apart from one
    a teacher taught, so `--self-taught` can never pick up the other kind."""
    return doc_dir(blob_dir) / f"{_key(pdf)}.self.trees"


def self_refused_path(blob_dir: Path, pdf: Path) -> Path:
    """Where a refused SELF-TAUGHT dictionary is remembered (T-0171)."""
    return doc_dir(blob_dir) / f"{_key(pdf)}.self-refused"


def is_self_taught(trees: Path) -> bool:
    """Does this dictionary mark itself `S self-taught` (gd3-learn self)?"""
    try:
        with open(trees, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:                 # the header precedes the records
                if line.startswith("R "):
                    return False
                if line.strip() == "S self-taught":
                    return True
        return False
    except OSError:
        return False


def reading_path(blob_dir: Path, pdf: Path) -> Path:
    """The TEACHER reading: five of this document's pages, in the sidecar.

    The name is the one `gemma_reader.expected_outputs(pdf, out_dir)` writes,
    because there must be ONE naming authority for that file and it is the
    reader's. The folder is per document already, so the stem is enough.
    """
    return doc_dir(blob_dir) / f"{Path(pdf).stem}.lines.json"


def _env() -> dict:
    """The child's environment: TMPDIR inside pdfdrill's own work folder, so
    ghostscript's short-lived files never land in /tmp (owner, 2026-10-30) nor
    in GLYPHDRILL3's tree (T-0145)."""
    e = dict(os.environ)
    scratch = config.scratch_dir()
    scratch.mkdir(parents=True, exist_ok=True)
    e["TMPDIR"] = str(scratch)
    return e


def pick_pages(pdf: Path, *, n: int = LEARN_PAGES) -> list[int]:
    """The pages `gd3-learn` wants read, 1-based, or [] when it names none.

    Its own rule (T-0157 arm D): of the pages with at least 20 band lines, the
    n that together cover most glyph classes — which beat the first five text
    pages 0.9250 to 0.9128 on one document.
    """
    tool = learn_tool()
    if tool is None:
        return []
    try:
        out = subprocess.run([str(tool), "pick", str(pdf), "--n", str(n)],
                             capture_output=True, text=True, timeout=TIMEOUT,
                             env=_env())
    except (OSError, subprocess.SubprocessError):
        return []
    pages = []
    for tok in (out.stdout or "").split():
        if tok.isdigit():
            pages.append(int(tok))
    return pages


def learn(pdf: Path, reading: Path, out: Path) -> tuple:
    """(state, message). `state` is "learned", "rejected" or "failed".

    `rejected` is exit 3: the labels are too weak (gd3-learn's own gate, label
    rate >= 0.40 and leave-one-page-out >= 0.85). It is a MEASUREMENT, not a
    failure — the document is then read with the compiled-in fonts — and it is
    remembered so the five pages are not read again for the same answer.
    """
    tool = learn_tool()
    if tool is None:
        return "failed", why_unavailable()
    part = out.with_suffix(".part")
    try:
        res = subprocess.run([str(tool), "learn", str(pdf), str(reading),
                              "-o", str(part)],
                             capture_output=True, text=True, timeout=TIMEOUT,
                             env=_env())
    except (OSError, subprocess.SubprocessError) as e:
        part.unlink(missing_ok=True)
        return "failed", str(e)
    note = ((res.stderr or "") + (res.stdout or "")).strip().splitlines()
    msg = note[-1] if note else ""
    if res.returncode == 0 and part.is_file():
        part.replace(out)
        return "learned", msg
    part.unlink(missing_ok=True)
    if res.returncode == 3:
        return "rejected", msg
    return "failed", msg or f"gd3-learn exit {res.returncode}"


def learn_self(pdf: Path, out: Path) -> tuple:
    """(state, message): the document's dictionary taught by ITSELF (T-0171).

    `gd3-learn self PDF -o OUT` reads no teacher and touches no network: its
    labels are units inside the language's common words where gd3's classes
    and the born NN prototypes agree, and it writes the dictionary only when
    its own gate passes (>= 800 self-labels, leave-one-page-out >= 0.92, on
    deterministic learning). Exit 0 written; 3 refused ("refused: labels N,
    LOO X"), nothing written; anything else a failure. The dictionary marks
    itself, and the lines gd3 reads with it say `"source": "self-taught"`.
    """
    tool = learn_tool()
    if tool is None:
        return "failed", why_unavailable()
    part = out.with_suffix(".part")
    try:
        res = subprocess.run([str(tool), "self", str(pdf), "-o", str(part)],
                             capture_output=True, text=True, timeout=TIMEOUT,
                             env=_env())
    except (OSError, subprocess.SubprocessError) as e:
        part.unlink(missing_ok=True)
        return "failed", str(e)
    note = ((res.stderr or "") + (res.stdout or "")).strip().splitlines()
    msg = note[-1] if note else ""
    if res.returncode == 0 and part.is_file():
        part.replace(out)
        return "learned", msg
    part.unlink(missing_ok=True)
    if res.returncode == 3:
        return "rejected", msg
    return "failed", msg or f"gd3-learn self exit {res.returncode}"


def lines(pdf: Path, *, refs: "Path | None" = None, image_base: str = "",
          pages: "str | None" = None, extra: "list | None" = None) -> dict:
    """`gd3 lines` as a parsed reading. Raises RuntimeError with the tool's own
    message, which is the only honest thing to report when a tool refuses."""
    b = binary()
    if b is None:
        raise RuntimeError(why_unavailable())
    argv = [str(b)]
    if refs is not None:
        argv += ["--refs", str(refs)]
    argv += ["lines"]
    if image_base:
        argv += ["--image-base", image_base]
    if pages:
        argv += ["--pages", pages]
    argv += list(extra or [])
    argv += [str(pdf)]
    res = subprocess.run(argv, capture_output=True, text=True,
                         timeout=TIMEOUT, env=_env())
    if res.returncode != 0:
        tail = (res.stderr or "").strip().splitlines()
        raise RuntimeError(f"gd3 lines exit {res.returncode}: "
                           f"{tail[-1] if tail else 'no message'}")
    text = (res.stdout or "").strip()
    if not text:
        raise RuntimeError("gd3 lines wrote nothing")
    # one compact JSON document per PDF, one per line
    doc = json.loads(text.splitlines()[0])
    return doc
