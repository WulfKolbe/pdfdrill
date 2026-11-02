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


def pdfdrill_only_types() -> list:
    """Line types pdfdrill DECLARES but MathPix never emits.

    The contract describes two vocabularies, not one. `type_names()` is
    MathPix's; this is the remainder pdfdrill's own readers use. Measured, not
    asserted: a name is here only if `type_contract` declares it and no
    MathPix file in the library carries it.

    The distinction exists because the drift gate conflated the two lists in
    its first version. It compared pdfdrill's 38 declared types against
    MathPix's and would have failed for ever on `rotated_text`, which is
    pdfdrill's and correct. A gate that cannot be satisfied gets deleted.

    Returns NAMES, like `type_names()`, so the two are usable together. The
    full records -- measured line count, where they were seen, meaning -- are
    in `load_contract()["pdfdrill_only_types"]`.
    """
    return [t["name"] if isinstance(t, dict) else t
            for t in (load_contract().get("pdfdrill_only_types") or [])]


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
    # BOTH vocabularies count as known: MathPix's types and the ones pdfdrill
    # declares for its own readers (see pdfdrill_only_types).
    known = set(type_names()) | set(pdfdrill_only_types())
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


# --------------------------------------------------------------------------- #
#  Which reader wrote this file
# --------------------------------------------------------------------------- #
#  THE ONE IMPLEMENTATION. `tools/reading-contract/measure.py` imports it and
#  `pdfdrill lines-check` calls it, because two copies of a producer rule is
#  exactly how the contract's first version came to describe pdfdrill's own
#  output back to us (contract 1a): the rule read `source` at the top level
#  only, and 34 files of ours that declare it per PAGE were filed as MathPix.
#
#  The order matters and is documented in contracts/reading.md 1.

#: Page-level keys only OUR writers emit, and the writer that emits them.
#: Established by reading the writers on 2026-11-02, not by assumption:
#: docmodel_six.to_lines_json lines 4444-4455.
OURS_PAGE = {"px_per_pt": "pdfminer-docmodel", "diagrams": "pdfminer-docmodel",
             "fills": "pdfminer-docmodel", "links": "pdfminer-docmodel"}
#: Line-level keys only our writers emit (docmodel_six 4485-4524).
OURS_LINE = {"gaps": "pdfminer-docmodel", "rules": "pdfminer-docmodel",
             "deferred_glyphs": "pdfminer-docmodel",
             "complete": "pdfminer-docmodel", "_i": "pdfminer-docmodel"}



def rel(path) -> str:
    """The library-relative path, safe to put in JSON.

    Some library folder names carry bytes that are not valid UTF-8; Python
    surfaces them as lone surrogates, which `json.dumps` accepts and
    `write_text(encoding="utf-8")` then refuses -- leaving a 0-byte
    measured.json and a coverage run that dies on it. Replacing them here
    keeps the name readable and the file writable.
    """
    return (str(path.relative_to(LIB))
            .encode("utf-8", "replace").decode("utf-8"))


def producer_of(doc, pages):
    """Return the producer class, and the evidence that decided it."""
    # 1. the top-level declaration (defect 846 put it there)
    src = doc.get("source") if isinstance(doc, dict) else None
    if src:
        return "reader:%s" % src, "top-level source"
    # 2. a page-level declaration: our pre-846 shape, and the only place a
    #    merged reading can say it carries pages from two readers
    page_srcs = {pg.get("source") for pg in pages
                 if isinstance(pg, dict) and pg.get("source")}
    if len(page_srcs) == 1:
        return "reader:%s" % page_srcs.pop(), "page-level source"
    if len(page_srcs) > 1:
        return "merged:%s" % "+".join(sorted(page_srcs)), "page-level source (several)"
    # 3./4. signatures, page then line
    gemma = False
    for pg in pages:
        if not isinstance(pg, dict):
            continue
        if "furniture_retyped" in pg or pg.get("image_id") == "":
            gemma = True
        for k, owner in OURS_PAGE.items():
            if k in pg:
                return "reader:%s" % owner, "page field %s" % k
        for ln in (pg.get("lines") or [])[:200]:
            if not isinstance(ln, dict):
                continue
            for k, owner in OURS_LINE.items():
                if k in ln:
                    return "reader:%s" % owner, "line field %s" % k
    if gemma:
        return "reader:gemma", 'image_id "" / furniture_retyped'
    # 5. MathPix proper — split by API vintage, because the newer one carries
    #    fields the contract must not attribute to the classic export
    newer = any(isinstance(pg, dict) and isinstance(pg.get("page_confidence"), dict)
                for pg in pages)
    marked = any(("is_printed" in ln or "confidence" in ln)
                 for pg in pages[:3] if isinstance(pg, dict)
                 for ln in (pg.get("lines") or [])[:50] if isinstance(ln, dict))
    if newer:
        return "mathpix-newer", "page_confidence dict"
    if marked:
        return "mathpix-classic", "is_printed/confidence, no reader signature"
    # 6. nothing declared, nothing recognisable
    return "unknown-shape", "no declaration, no marker"
