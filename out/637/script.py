#!/usr/bin/env python3
"""637 — the census: one `\\footnotetext` per Footnote object, not two.

    python3 script.py <document folder> [<tex path>]

Runs from either the repo (`out/637/script.py`) or the document's own
`out/637/`. Everything it prints is read off the model on disk and the .tex
beside it; nothing is rebuilt here.
"""
import collections
import json
import re
import sys
from pathlib import Path


def _repo() -> Path:
    for cand in Path(__file__).resolve().parents:
        if (cand / "src" / "docmodel" / "footnote_extent.py").is_file():
            return cand
    return Path("/home/wkolbe/MX/PDFDRILL")


REPO = _repo()
sys.path.insert(0, str(REPO / "src"))

from docmodel import footnote_extent as fx                       # noqa: E402
from docops import conserve as C                                 # noqa: E402
from docops.projectors import footnotes as fnres                 # noqa: E402
from pdfdrill.model_io import load_model                         # noqa: E402


def _line_ids(doc, entries) -> list:
    """The MathPix line id for each ledger entry, by stream INDEX.

    Anchor ids are minted fresh on every build, so a set of them can only ever
    say two rebuilds differ. The MathPix `id` is the document's own name for
    the line and is stable across rebuilds.
    """
    st = doc.streams["mathpix_lines"]
    out = []
    for e in entries:
        i = e.get("index")
        if i is None or i >= len(st.anchors):
            continue
        out.append(str(st.payload[st.anchors[i]].get("id") or f"#{i}"))
    return out


def tex_blocks(tex: str):
    r"""Every `\footnotetext[n]{…}` in the .tex as `(optional, body)`, braces
    balanced — the count the user asks to hold against the object count."""
    out = []
    for m in re.finditer(r"\\footnotetext(\[\d+\])?\{", tex):
        i = m.end() - 1
        depth = 0
        for j in range(i, len(tex)):
            if tex[j] == "{":
                depth += 1
            elif tex[j] == "}":
                depth -= 1
                if depth == 0:
                    out.append((m.group(1), tex[i + 1:j]))
                    break
    return out


def census(docdir: Path, tex_path: Path | None = None) -> dict:
    model = docdir / "model.docmodel.json"
    doc = load_model(model)
    fns = [o for o in doc.objects.values() if o.type == "Footnote"]
    by_creator = collections.Counter(
        o.props.get("added_by") or "footnote(processor)" for o in fns)
    filled = sum(1 for o in fns if o.props.get("filled_by"))
    key = collections.Counter(
        (o.props.get("page"), str(o.props.get("refnum"))) for o in fns)
    dup = {k: v for k, v in key.items() if v > 1}

    res = {
        "objects": len(doc.objects),
        "footnotes": len(fns),
        "footnotes_by_creator": dict(by_creator),
        "footnotes_filled_by_cleanup": filled,
        "page_refnum_pairs_with_more_than_one_object": len(dup),
        "objects_in_those_pairs": sum(dup.values()),
        "meta_footnote_adopted": int(doc.meta.get("footnote_adopted") or 0),
        "meta_footnote_orphan_tail": int(doc.meta.get("footnote_orphan_tail") or 0),
        "meta_footnote_span_not_located":
            int(doc.meta.get("footnote_span_not_located") or 0),
    }

    # every Footnote carries ONE body, and the projector reads exactly it
    roles = collections.Counter(
        tuple(sorted(r.role for r in o.realizations)) for o in fns)
    res["realization_roles"] = {"+".join(k): v for k, v in roles.items()}
    res["footnotes_whose_cleaned_realization_differs_from_content"] = sum(
        1 for o in fns
        if fnres.body_text(o) != str(o.props.get("content") or ""))

    # the maths a body already prints
    res["body_math_folded"] = len(fnres.body_math_ids(doc))

    # conserve — the other instrument
    rep = C.conserve(doc)
    res["conserve"] = {
        "unclaimed": rep["counts"]["unclaimed"],
        "doubly_claimed": rep["counts"]["doubly_claimed"],
        "unreachable_objects": rep["counts"]["unreachable"],
        "pairs": {"+".join(e["types"]): e["count"]
                  for e in rep["anchors"]["pairs"]},
        # BY TYPE, which is the spelling that survives 637: the module LABEL of
        # the cleanup's claim moves when the claim lands on an object the
        # processor made (see the report), the anchors do not.
        "gt1_involving_a_footnote_object": sum(
            e["count"] for e in rep["anchors"]["pairs"]
            if "Footnote" in e["types"]),
    }

    # the ledger — >1-claim anchors a footnote creator is party to
    from docmodel import ledger as L
    view = L.materialize(doc)
    if view is None:
        res["ledger"] = "<no ledger stream on this model>"
    else:
        multi = view["multi"]
        res["ledger"] = {
            "claimed_0": view["counts"]["claimed_0"],
            "claimed_1": view["counts"]["claimed_1"],
            "claimed_multi": view["counts"]["claimed_multi"],
            "block_claims": view["counts"]["block_claims"],
            "inline_claims": view["counts"]["inline_claims"],
            "by_module_pair": dict(collections.Counter(
                "+".join(e["modules"]) for e in multi).most_common()),
            # THE NUMBER THE BRIEF ASKS FOR: anchors claimed more than once
            # where one of the claimants is a FOOTNOTE creator.
            "gt1_involving_a_footnote_creator": sum(
                1 for e in multi
                if any(m.startswith("footnote") for m in e["modules"])),
            "gt1_footnote_plus_footnote": sum(
                1 for e in multi
                if all(m.startswith("footnote") for m in e["modules"])),
            "by_module_footnote": {
                k: v for k, v in view["by_module"].items()
                if k.startswith("footnote") or k == "heading_cleanup"},
            # the LINES themselves, so before/after is SET equality and not two
            # numbers that happen to match. NOT the anchor ids: those are
            # regenerated on every build, so comparing them across two rebuilds
            # can only ever say "different" (measured — it did).
            "gt1_line_ids": sorted(_line_ids(doc, multi)),
            "zero_line_ids": sorted(_line_ids(doc, view["zero"])),
        }

    # the .tex
    tex_path = tex_path or (docdir / "latex" / f"{docdir.name}.tex")
    if tex_path.is_file():
        tex = tex_path.read_text(errors="replace")
        blocks = tex_blocks(tex)
        numbered = [b for b in blocks if b[0]]
        openings = collections.Counter(
            re.sub(r"\s+", " ", b).strip()[:60] for _o, b in blocks)
        repeated = {k: v for k, v in openings.items() if v > 1}
        res["tex"] = {
            "path": str(tex_path),
            "footnotetext_blocks": len(blocks),
            "footnotetext_numbered": len(numbered),
            "footnotetext_bare_from_paragraph_prose": len(blocks) - len(numbered),
            "openings_first_60_chars_repeating": len(repeated),
            "blocks_in_a_repeated_opening": sum(repeated.values()),
            "repeated_openings": sorted(repeated)[:10],
            "footnotemark": len(re.findall(r"\\footnotemark", tex)),
            "footnotemark_numbered": len(re.findall(r"\\footnotemark\[", tex)),
            "marker_spans": len(re.findall(r"\\\(\{ \}\^\{\d+\}\\\)", tex)),
            "any_superscript_empty_base": len(re.findall(r"\{ \}\^\{\d+\}", tex)),
        }
    return res


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    docdir = Path(sys.argv[1]).expanduser().resolve()
    tex = Path(sys.argv[2]).expanduser().resolve() if len(sys.argv) > 2 else None
    out = census(docdir, tex)
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
