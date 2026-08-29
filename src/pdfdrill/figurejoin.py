r"""301 — scoring the figure join against a known answer before trusting it.

Six documents keep a MathPix tex.zip unpacked inside `texsrc/`. Its
`\includegraphics` calls name the region 5-tuple directly, so for those
documents the regions are stated rather than inferred. That makes them the only
place where a join from the AUTHOR's figure files to MathPix's regions can be
checked instead of assumed.

The ground truth here is NOT the order — using order to check an order-based
join would be circular, and would report the join's own assumption back as its
accuracy. It is the CAPTION: MathPix OCRs the caption the author wrote, so a
caption is content both sides carry independently. Where a distinctive run of
caption words appears beside exactly one region, that pair is known.

Coverage of a ground truth may be partial; its correctness may not. A caption
that matches two regions establishes nothing and is recorded as unanchored, not
resolved by preferring the nearer one — that preference is 282's defect, which
is what a low-confidence join does when nobody checks.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import texgraphics as tg

#: Caption words needed before a match counts. "figure 1" and "results" recur;
#: a run this long recurring by chance in one document is unlikely, and the
#: cost of being wrong here is a ground truth that certifies a broken join.
MIN_ANCHOR_TOKENS = 5

_INPUT = re.compile(r"\\(?:input|include)\s*\{([^}]*)\}")
_DOCCLASS = re.compile(r"\\documentclass")


def main_tex(src_dir: Path, texs: list) -> "Path | None":
    """The file carrying \\documentclass — the root of the input graph."""
    for t in texs:
        try:
            head = t.read_text(encoding="utf-8", errors="replace")[:4000]
        except OSError:
            continue
        if _DOCCLASS.search(head):
            return t
    return None


def document_order(src_dir: Path) -> list:
    r"""Author inclusions in the order the DOCUMENT includes them.

    Following `\input`/`\include` from the root rather than sorting filenames:
    `chapters/four_tufte.tex` sorts before `chapters/one_tufte.tex`, and a join
    built on that order would be wrong from its first pair.
    """
    src_dir = Path(src_dir)
    texs = [p for p in sorted(src_dir.rglob("*.tex"))
            if p.is_file() and not tg.is_texzip_tex(p, src_dir)]
    root = main_tex(src_dir, texs)
    if root is None:
        return _flat(src_dir, texs)
    out, seen = [], set()

    def walk(t: Path):
        if t in seen or not t.is_file():
            return
        seen.add(t)
        try:
            text = t.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        body = tg._COMMENT.sub("", text)
        caps = tg.captions(body)
        events = []
        for m in tg._INCLUDE.finditer(body):
            events.append((m.start(), "img", None))
        for m in _INPUT.finditer(body):
            events.append((m.start(), "input", m.group(1)))
        calls = tg.calls(text, source=str(t.relative_to(src_dir)))
        ci = 0
        for pos, kind, arg in sorted(events):
            if kind == "img":
                if ci < len(calls):
                    out.append(calls[ci])
                    ci += 1
            else:
                child = _resolve_input(src_dir, t, arg)
                if child:
                    walk(child)
    walk(root)
    if not out:                                   # no \input graph reached them
        return _flat(src_dir, texs)
    return out


def _flat(src_dir: Path, texs: list) -> list:
    out = []
    for t in texs:
        try:
            out.extend(tg.calls(t.read_text(encoding="utf-8", errors="replace"),
                                source=str(t.relative_to(src_dir))))
        except OSError:
            pass
    return out


def _resolve_input(src_dir: Path, parent: Path, arg: str) -> "Path | None":
    arg = (arg or "").strip().replace('"', "")
    for base in (parent.parent, src_dir):
        for cand in (base / arg, base / (arg + ".tex")):
            if cand.is_file():
                return cand
    return None


def mathpix_regions(src_dir: Path) -> list:
    r"""MathPix's own inclusions, in the order its reconstruction states them."""
    src_dir = Path(src_dir)
    out = []
    for t in sorted(src_dir.rglob("*.tex")):
        if not (t.is_file() and tg.is_texzip_tex(t, src_dir)):
            continue
        try:
            text = t.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for c in tg.calls(text, source=str(t.relative_to(src_dir))):
            c["region"] = tg.region_tuple(c["file"])
            if c["region"]:
                out.append(c)
    return out


def _ngrams(tokens: list, n: int) -> set:
    return {" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def anchor(author_caption: str, region_captions: list) -> list:
    """Indices of the regions whose caption shares a distinctive run of words."""
    a = author_caption.split()
    if len(a) < MIN_ANCHOR_TOKENS:
        return []
    want = _ngrams(a, MIN_ANCHOR_TOKENS)
    hits = []
    for i, rc in enumerate(region_captions):
        if want & _ngrams(rc.split(), MIN_ANCHOR_TOKENS):
            hits.append(i)
    return hits


def ground_truth(src_dir: Path) -> dict:
    r"""Author file -> region, where a caption names exactly one region.

    Returns the pairs AND what could not be anchored, because a ground truth
    that hides its own coverage invites the join to be scored on the easy half.
    """
    src_dir = Path(src_dir)
    authors = document_order(src_dir)
    regions = mathpix_regions(src_dir)
    rcaps = [r.get("caption_plain", "") for r in regions]
    pairs, ambiguous, unanchored = [], [], []
    for ai, a in enumerate(authors):
        cap = a.get("caption_plain", "")
        hits = anchor(cap, rcaps)
        if len(hits) == 1:
            pairs.append({"author_index": ai, "file": a["file"],
                          "region": regions[hits[0]]["region"],
                          "region_index": hits[0],
                          "anchor": cap[:70]})
        elif len(hits) > 1:
            ambiguous.append({"author_index": ai, "file": a["file"],
                              "candidates": [regions[h]["region"] for h in hits]})
        else:
            unanchored.append({"author_index": ai, "file": a["file"],
                               "had_caption": bool(cap)})
    # A caption names the FLOAT, not the file. Two subfigures in one figure
    # share a caption and both anchor to the same region, which is two claims
    # on one answer -- not a known pair. Dropping them is the whole discipline
    # here: a ground truth that keeps them would certify a join by letting it
    # be right about a pair nobody actually knows.
    claims = {}
    for pr in pairs:
        claims.setdefault(pr["region_index"], []).append(pr)
    kept, contested = [], []
    for _ri, group in claims.items():
        if len(group) == 1:
            kept.append(group[0])
        else:
            contested.append({"region": group[0]["region"],
                              "claimed_by": [g["file"] for g in group]})
    kept.sort(key=lambda x: x["author_index"])
    return {"authors": len(authors), "regions": len(regions),
            "pairs": kept, "ambiguous": ambiguous,
            "contested": contested, "unanchored": unanchored}


def infer_ordinal(src_dir: Path) -> dict:
    r"""299's join: the k-th author figure is the k-th region.

    This is what "the .tex gives the order and the float" amounts to when no
    other signal is used. It is stated separately so it can be SCORED rather
    than shipped: where the two sequences differ in length, every pair after
    the first difference is a guess, and a guess that returns a value is
    indistinguishable from an answer.
    """
    authors = document_order(src_dir)
    regions = mathpix_regions(src_dir)
    out = {}
    for i, a in enumerate(authors):
        out[i] = regions[i]["region"] if i < len(regions) else None
    return {"map": out, "authors": len(authors), "regions": len(regions),
            "lengths_agree": len(authors) == len(regions)}


def score(truth: dict, inferred: dict) -> dict:
    """Matched / wrong / not-inferred, over the pairs the truth actually knows."""
    m = inferred["map"]
    matched, wrong, missing = [], [], []
    for p in truth["pairs"]:
        got = m.get(p["author_index"])
        if got is None:
            missing.append(p)
        elif tuple(got) == tuple(p["region"]):
            matched.append(p)
        else:
            wrong.append({**p, "inferred": got})
    return {"checkable": len(truth["pairs"]), "matched": len(matched),
            "wrong": len(wrong), "not_inferred": len(missing),
            "wrong_detail": wrong[:10]}
