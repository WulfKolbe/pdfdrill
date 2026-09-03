r"""575 — which code produced this artefact.

574 asked a question the corpus could not answer. Seven of twenty-one models
had been built weeks before the other fourteen, and the section total summed
across them — 1458 — was 34% below the truth, with no defect anywhere in the
detection code. The only generation marker a model carried was its file
mtime, and mtime cannot separate "built from committed HEAD" from "built from
an uncommitted tree that later became HEAD": fourteen models timestamped
15:10 were stale against a commit made at 15:13 and had in fact been built
from the tree that commit captured.

So a model now says, in its own metadata, which code wrote it:

    meta["build"]    — stamped once, when the model is constructed from
                       lines.json in `docmodel.main.run`. It is the code that
                       decided the object graph, and it is never overwritten.
    meta["written"]  — stamped on every `model_io.save_model`. It is the code
                       that last touched the file, which after an enrichment
                       pass is not the code that built it.

Both are {sha, dirty, version, at}. `dirty` counts modifications to TRACKED
files only — an untracked scratch file in the working tree does not change
the behaviour of imported code, and treating it as dirty would mark every
build in this repository dirty forever.

THE GUARD. `spread()` takes the models behind a corpus number and reports how
many distinct shas they span. A measurement that spans more than one reports
the spread rather than a single number, because a single number computed
across generations is not a measurement of anything — it is the sum of two
different experiments. `guard_lines()` is the block a report prints when the
spread is not one.

A model built before 575 carries no stamp at all. Those are reported as
`unstamped` and count as their own unknown generation — not folded into the
majority, which would be exactly the silent averaging this module exists to
stop.
"""
from __future__ import annotations

import datetime
import subprocess
from pathlib import Path

#: the repository this code was imported from: src/pdfdrill/ -> src/ -> root
REPO = Path(__file__).resolve().parents[2]

_CACHE: "dict | None" = None


def _git(*args: str) -> "str | None":
    """Run git in REPO, returning stripped stdout, or None on any failure.

    The return code IS checked. 574 lost two runs to `capture_output=True`
    without a return-code check, three times in one session; a stamp that
    silently records a git error as a sha would be worse than no stamp.
    """
    try:
        p = subprocess.run(["git", "-C", str(REPO), *args],
                           capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    return p.stdout.strip()


def version() -> str:
    """The installed pdfdrill version, or the one declared in pyproject."""
    try:
        from importlib.metadata import version as _v
        return _v("pdfdrill")
    except Exception:
        pass
    try:
        for line in (REPO / "pyproject.toml").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return "unknown"


def stamp(refresh: bool = False) -> dict:
    """{sha, dirty, version, at} for the code running right now.

    Cached per process: a sweep that builds twenty-one models shells out to
    git once, not twenty-one times, and every model in that sweep carries the
    same sha even if someone commits mid-run — which is the truth, since they
    all ran the same imported code.
    """
    global _CACHE
    if _CACHE is None or refresh:
        sha = _git("rev-parse", "HEAD")
        # --quiet exits 1 when tracked files differ; None means git failed.
        dirty = None
        if sha is not None:
            porcelain = _git("status", "--porcelain", "--untracked-files=no")
            dirty = bool(porcelain) if porcelain is not None else None
        _CACHE = {"sha": sha, "dirty": dirty, "version": version()}
    out = dict(_CACHE)
    out["at"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    return out


def short(sha: "str | None") -> str:
    return sha[:7] if sha else "unstamped"


def describe(st: "dict | None") -> str:
    """One line naming a stamp, for a report."""
    if not st:
        return "unstamped (built before 575)"
    return "%s%s  v%s  %s" % (short(st.get("sha")),
                              "-dirty" if st.get("dirty") else "",
                              st.get("version", "?"), st.get("at", "?"))


def read_stamp(model_path, which: str = "build") -> "dict | None":
    """The `build` (or `written`) stamp from a model file, without loading it.

    Reads the whole JSON — a model is tens of MB, so callers measuring a
    corpus should prefer passing metas they already hold.
    """
    import json
    try:
        meta = json.loads(Path(model_path).read_text(encoding="utf-8")).get("meta") or {}
    except Exception:
        return None
    st = meta.get(which)
    return st if isinstance(st, dict) else None


def key_of(st: "dict | None") -> str:
    """The generation a stamp belongs to. An unstamped model is its own."""
    if not st or not st.get("sha"):
        return "unstamped"
    return "%s%s" % (st["sha"], "-dirty" if st.get("dirty") else "")


def spread(items) -> dict:
    """Group `(name, stamp)` pairs by generation.

    Returns {"generations": {key: [names]}, "n": int, "one": bool,
             "unstamped": [names], "dirty": [names]}.
    `n` counts `unstamped` as one generation when present, because a model
    with no stamp is not known to belong to any of the others.
    """
    gens: dict[str, list] = {}
    dirty: list = []
    for name, st in items:
        k = key_of(st)
        gens.setdefault(k, []).append(name)
        if st and st.get("dirty"):
            dirty.append(name)
    return {"generations": gens, "n": len(gens), "one": len(gens) == 1,
            "unstamped": sorted(gens.get("unstamped", [])),
            "dirty": sorted(dirty)}


def guard_lines(sp: dict, what: str = "This number") -> list:
    """The block a corpus report prints. Empty when the spread is one."""
    if sp["one"]:
        (k,) = sp["generations"]
        n = len(sp["generations"][k])
        return ["%s is from one build generation: %s (%d document%s)."
                % (what, short(k.split("-")[0]) if k != "unstamped" else k,
                   n, "" if n == 1 else "s")]
    out = ["%s SPANS %d BUILD GENERATIONS and is therefore not a single "
           "number:" % (what, sp["n"])]
    for k, names in sorted(sp["generations"].items(),
                           key=lambda kv: (-len(kv[1]), kv[0])):
        label = k if k == "unstamped" else short(k.split("-")[0]) + (
            "-dirty" if k.endswith("-dirty") else "")
        out.append("  %-20s %3d document%s: %s" % (
            label, len(names), "" if len(names) == 1 else "s",
            ", ".join(sorted(names)[:6]) + (" …" if len(names) > 6 else "")))
    out.append("Report the per-generation figures, or rebuild to one "
               "generation before summing.")
    return out


def require_one(sp: dict, what: str = "This number") -> None:
    """Raise when a measurement spans generations. For code that must not
    emit a cross-generation number at all."""
    if not sp["one"]:
        raise ValueError("\n".join(guard_lines(sp, what)))
