#!/usr/bin/env python3
r"""503 — the printed-to-PDF offset, from the PDF itself rather than the model.

493 established that a section path needs three things and has two: the TOC
gives depth and title, and nothing on disk says which PDF page printed page 1
falls on. Deriving it by matching TOC titles to Section captions produced
three votes for 9 against singletons for 20 and 15 — noise.

The PDF knows. Three places, in order of how much they are worth:

  page labels          an exact printed->PDF map, when the publisher set one.
                       Not a derivation at all: /PageLabels says page 13 is
                       printed "1". Front matter in roman is then not a
                       problem but the very thing the map encodes.
  the outline          (title, destination page) pairs from the annotation
                       layer. Matched against the TOC's (title, printed page)
                       it gives one offset per matched entry, and whether
                       those agree is the confidence.
  named destinations   the same, keyed by name rather than by title.

Reports the offset and its confidence, never a path.
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

ENTRY = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+(.{2,120}?)\s*\.{2,}\s*(\d+)\s*$")
ROMAN = re.compile(r"^[ivxlcdm]+$", re.I)


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())[:40]


def toc_entries(model_path: Path):
    try:
        m = json.loads(model_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return []
    out = []
    for o in m["objects"]:
        if o["type"] != "Toc":
            continue
        for e in (o.get("props") or {}).get("entries") or []:
            mt = ENTRY.match(e)
            if mt:
                out.append((mt.group(1), mt.group(2), int(mt.group(3))))
    return out


def probe(pdf: Path, model: Path):
    import pypdf
    r = pypdf.PdfReader(str(pdf))
    res = {"pages": len(r.pages)}
    # 1 — page labels
    try:
        labels = list(r.page_labels)
    except Exception as exc:
        labels = []
        res["page_labels_error"] = "%s: %s" % (type(exc).__name__, exc)
    res["page_labels"] = len(labels)
    if labels:
        arabic = [(i, l) for i, l in enumerate(labels) if str(l).isdigit()]
        roman = [(i, l) for i, l in enumerate(labels) if ROMAN.match(str(l))]
        res["labels_arabic"] = len(arabic)
        res["labels_roman"] = len(roman)
        offs = collections.Counter(i - int(l) + 1 for i, l in arabic)
        res["label_offsets"] = offs.most_common(4)
        res["label_offset_constant"] = len(offs) == 1
    # 2 — the outline
    try:
        flat = []

        def walk(node, depth=0):
            for it in node:
                if isinstance(it, list):
                    walk(it, depth + 1)
                    continue
                try:
                    pg = r.get_destination_page_number(it)
                except Exception:
                    pg = None
                flat.append((depth, str(getattr(it, "title", "")), pg))
        walk(r.outline)
    except Exception as exc:
        flat = []
        res["outline_error"] = "%s: %s" % (type(exc).__name__, exc)
    res["outline_entries"] = len(flat)
    res["outline_with_page"] = sum(1 for _, _, p in flat if p is not None)
    # 3 — outline against the TOC
    toc = toc_entries(model)
    res["toc_parsed"] = len(toc)
    by = {}
    for _d, title, pg in flat:
        if pg is not None and title:
            by.setdefault(norm(title), pg)
    diffs = []
    for _num, title, printed in toc:
        k = norm(title)
        if k in by:
            diffs.append(by[k] - printed + 1)
    res["outline_matched"] = len(diffs)
    c = collections.Counter(diffs)
    res["outline_offsets"] = c.most_common(4)
    if diffs:
        top, n = c.most_common(1)[0]
        res["outline_offset"] = top
        res["outline_agreement"] = round(n / len(diffs), 3)
    try:
        res["named_destinations"] = len(r.named_destinations)
    except Exception:
        res["named_destinations"] = None
    return res


if __name__ == "__main__":
    lib = Path.home() / "pdfdrill-library"
    books = json.loads(Path(sys.argv[1]).read_text()) if len(sys.argv) > 1 else []
    out = {}
    for b in books:
        d = lib / b
        pdfs = [p for p in d.glob("*.pdf") if not p.name.startswith("report")]
        if not pdfs:
            out[b] = {"error": "no pdf"}
            continue
        try:
            out[b] = probe(pdfs[0], d / "model.docmodel.json")
        except Exception as exc:
            out[b] = {"error": "%s: %s" % (type(exc).__name__, exc)}
        print("\r%d/%d" % (len(out), len(books)), end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)
    json.dump(out, sys.stdout, indent=1, ensure_ascii=False)
