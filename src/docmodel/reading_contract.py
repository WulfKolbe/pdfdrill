"""The reading contract (reading/1) as code reads it.

The contract itself is DATA and lives in drillgroup, shared by every reader
(glyphdrill, pdf2mmd2, Gemma, pdfdrill). This module is the one place in
pdfdrill that loads it, so there is never a private second list of line
types: the failure T-0107 exists to prevent is two projects disagreeing
about what `formula` means while both believe they are conformant.

RESOLUTION ORDER for the contract file, first hit wins:

  1. `$PDFDRILL_READING_CONTRACT`, a path -- how a test or another checkout
     points at a specific copy;
  2. `~/drillgroup/contracts/reading-types.json`, the shared original;
  3. `docs/contracts/reading-types.json` in this checkout, the draft this
     repository measured and the fallback while the coordinator reviews it.

`contract_path()` says which one answered, and every caller that reports to
a human prints it -- a conformance verdict against an unnamed contract is
not a verdict.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

#: candidate 3, relative to this file: src/docmodel/ -> repo root
_IN_REPO = Path(__file__).resolve().parents[2] / "docs/contracts/reading-types.json"
_SHARED = Path.home() / "drillgroup/contracts/reading-types.json"


class ContractMissing(FileNotFoundError):
    """No contract file was found. The caller must say so, never assume."""


def contract_path() -> Path:
    env = os.environ.get("PDFDRILL_READING_CONTRACT")
    if env:
        p = Path(env).expanduser()
        if not p.is_file():
            raise ContractMissing(
                "PDFDRILL_READING_CONTRACT names %s, which is not a file. "
                "An unreadable contract is not an empty contract." % p)
        return p
    for p in (_SHARED, _IN_REPO):
        if p.is_file():
            return p
    raise ContractMissing(
        "no reading contract found: tried $PDFDRILL_READING_CONTRACT, %s "
        "and %s" % (_SHARED, _IN_REPO))


def load_contract() -> dict:
    """The contract as a dict, with `path` added so a caller can name it."""
    p = contract_path()
    d = json.loads(p.read_text(encoding="utf-8"))
    d["path"] = str(p)
    return d


def type_names() -> list:
    return [t["name"] for t in load_contract()["types"]]


def status_of(name: str) -> "str | None":
    """"read", "declared-only", or None when the contract does not list it."""
    for t in load_contract()["types"]:
        if t["name"] == name:
            return t.get("status")
    return None


def unknown_types(observed) -> list:
    """The observed type names the contract does not list, in the order seen.

    DECLARED-ONLY IS NOT UNKNOWN. A type the contract lists as unread is
    accounted for -- the contract says, in writing, that nothing reads it.
    Unknown means the contract has never seen the name at all, which is the
    case that must reach a human: a reader inventing a name, or MathPix
    adding a type. Conflating the two would make the gate fire on the seven
    declared-only types for ever and be switched off within a week.

    Duplicates collapse to the first occurrence so a 3,000-line file does
    not report the same new type 3,000 times.
    """
    known = set(type_names())
    out, seen = [], set()
    for name in observed:
        if name in known or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def declared_line_types(type_contract_module) -> list:
    """The line types pdfdrill itself declares, read off `type_contract`.

    Taken from its CLAIMED and IGNORED maps, which are keyed by line type.
    Passed in rather than imported so the caller decides whether a missing
    module is a skip or a failure.
    """
    names = set()
    for attr in ("CLAIMED", "IGNORED"):
        d = getattr(type_contract_module, attr, None)
        if isinstance(d, dict):
            names.update(k for k in d if isinstance(k, str))
    return sorted(names)
