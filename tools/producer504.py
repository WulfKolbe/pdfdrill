#!/usr/bin/env python3
r"""504 — a census of the corpus by producer. Reporting only.

Four sources, each answering a different half of "who made this file":

  texsrc/            the author's \documentclass and its options, and the
                     packages loaded — what the AUTHOR chose
  the PDF's fonts    embedded families and their subset tags — what the
                     TOOLCHAIN emitted
  metadata           Producer and Creator — what the toolchain SAYS it is
  the DOI prefix     who published it

A publisher with one document proves nothing; a publisher with fifteen is a
population, so everything below is counted per producer rather than listed.
"""
from __future__ import annotations

import collections
import json
import re
import os
import subprocess
import sys
from pathlib import Path

DOCCLASS = re.compile(r"\\documentclass\s*(\[[^\]]*\])?\s*\{([^}]+)\}")
USEPKG = re.compile(r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")
FONT = re.compile(r"^(\S+)\s+(\S+)", re.M)
SUBSET = re.compile(r"^([A-Z]{6})\+(.+)$")


def from_texsrc(d: Path):
    src = d / "texsrc"
    if not src.is_dir():
        return None
    best = None
    for f in sorted(src.rglob("*.tex"))[:60]:
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = DOCCLASS.search(t)
        if m:
            pkgs = sorted({p.strip() for mm in USEPKG.finditer(t)
                           for p in mm.group(1).split(",") if p.strip()})
            best = {"documentclass": m.group(2).strip(),
                    "options": (m.group(1) or "")[1:-1],
                    "packages": pkgs, "file": f.name}
            break
    return best


def from_pdf_meta(pdf: Path):
    try:
        out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True,
                             text=True, timeout=40).stdout
    except Exception:
        return {}
    g = {}
    for line in out.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            g[k.strip()] = v.strip()
    return {"producer": g.get("Producer", ""), "creator": g.get("Creator", ""),
            "pages": g.get("Pages", "")}


def from_fonts(d: Path, pdf: Path):
    probe = d / "probe-pdffonts.txt"
    txt = ""
    if probe.is_file():
        txt = probe.read_text(encoding="utf-8", errors="replace")
    else:
        try:
            txt = subprocess.run(["pdffonts", str(pdf)], capture_output=True,
                                 text=True, timeout=40).stdout
        except Exception:
            return {}
    fams, subset = set(), 0
    for line in txt.splitlines()[2:]:
        name = line.split()[0] if line.split() else ""
        if not name or name == "name":
            continue
        m = SUBSET.match(name)
        if m:
            subset += 1
            fams.add(m.group(2))
        else:
            fams.add(name)
    return {"font_families": sorted(fams)[:24], "n_families": len(fams),
            "n_subset_tagged": subset}


def doi_prefix(d: Path):
    for f in (d / (d.name + ".drill.json"),):
        if not f.is_file():
            continue
        try:
            j = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            return ""
        blob = json.dumps(j)
        m = re.search(r"10\.(\d{4,9})/", blob)
        if m:
            return "10." + m.group(1)
    m = re.match(r"^(10\.\d{4,9})_", d.name)
    return m.group(1) if m else ""


def safe(s: str) -> str:
    r"""A str that JSON can actually write.

    504 died at the final `json.dump` on '\udcd6': eighteen folder names in
    this corpus are CP1252 bytes, not UTF-8 — 0xF6 for o-umlaut, 0x92 for a
    curly apostrophe, 0xD6 for O-umlaut — and Python surrogate-escapes them on
    read. A lone surrogate is not encodable and json refuses it.

    Replacing them is right; replacing them SILENTLY is not, because a census
    that quietly renames part of its population cannot be joined back to the
    disk. Every substitution is counted and the original bytes are kept.
    """
    try:
        s.encode("utf-8")
        return s
    except UnicodeEncodeError:
        MANGLED.append({"repr": repr(s),
                        "bytes": os.fsencode(s).decode("latin-1")})
        return s.encode("utf-8", "replace").decode("utf-8")


MANGLED: list = []


if __name__ == "__main__":
    lib = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "pdfdrill-library"
    out, n = {}, 0
    for d in sorted(p for p in lib.iterdir() if p.is_dir()):
        pdfs = [p for p in d.glob("*.pdf") if not p.name.startswith("report")]
        if not pdfs:
            continue
        n += 1
        rec = {"doi_prefix": doi_prefix(d)}
        rec.update(from_pdf_meta(pdfs[0]))
        rec.update(from_fonts(d, pdfs[0]) or {})
        tx = from_texsrc(d)
        if tx:
            rec["tex"] = tx
        out[safe(d.name)] = rec
        print("\r%d" % n, end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)
    json.dump({"documents": out,
               "names_not_utf8": len(MANGLED), "mangled": MANGLED},
              sys.stdout, indent=1, ensure_ascii=False)
