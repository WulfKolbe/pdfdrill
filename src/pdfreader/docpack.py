"""docpack - project our model into the pdfdrill docmodel shape.

The pdfdrill docmodel is four sections, and the separation is the point:

    meta        what was read, by what, when
    streams     named sequences of ANCHORED payload -- the evidence
    objects     abstract document objects that POINT INTO streams
    alignments  typed relations between anchor ranges in two streams

An object never holds text. It holds `realizations`: [start, end] anchor
ranges in a named stream, each with a role. That is what lets two sources
describe the same object without either one being rewritten -- a paragraph
can be realized in `pdfminer_lines` and in `mathpix_lines` at once, and an
alignment records how the two relate.

This module emits one stream, `pdfminer_lines`, carrying our line records in
the MathPix line shape, plus the objects our model can justify: Page,
Paragraph, Formula, Diagram, Listing, TableRow. It does NOT invent structure
it cannot support -- there are no Section or TableCell objects here, because
nothing in our model identifies them yet.

Anchor ids are content-addressed: the same document read twice produces the
same ids, so a diff between two runs shows what changed rather than
renumbering everything.

CONTRACT
    to_docmodel(pages, bibkey, source_path) -> dict
        The four sections, JSON-serialisable.
    anchor_id(payload) -> str
        Stable id for a payload record.
"""
from __future__ import annotations

import datetime
import hashlib
import json

import docmodel_six as docmodel

VERSION = "0.1.0"
STREAM = "pdfminer_lines"


def anchor_id(payload: dict) -> str:
    """A stable, content-addressed anchor id.

    Derived from the payload, so re-reading the same document yields the same
    ids. Sequential numbering would make every diff between two runs look
    like a total rewrite.
    """
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "a_" + hashlib.blake2b(blob.encode("utf-8"),
                                  digest_size=6).hexdigest()


def object_id(kind: str, key: str) -> str:
    return "obj_" + hashlib.blake2b(f"{kind}:{key}".encode("utf-8"),
                                    digest_size=6).hexdigest()


def _realization(start: str, end: str, role: str, **props) -> dict:
    return {"stream": STREAM, "start": start, "end": end,
            "role": role, "props": props}


def to_docmodel(pages: list["docmodel.PageNode"],
                bibkey: str = "pdfdrill",
                source_path: str = "",
                px_per_pt: float = docmodel.PX_PER_PT) -> dict:
    """Project the page model into the four-section docmodel."""
    lines_json = docmodel.to_lines_json(pages, px_per_pt=px_per_pt,
                                        doc_id=bibkey)

    anchors: list[str] = []
    payload: dict[str, dict] = {}
    per_page: dict[int, list[str]] = {}

    for page in lines_json["pages"]:
        pno = page["page"]
        per_page[pno] = []
        for idx, line in enumerate(page["lines"]):
            # A CONTAINER IS NOT CONTENT. `to_lines_json` emits one `column`
            # record per text column, holding the lines rather than saying
            # anything itself. Anchoring it makes it an object, and pdfdrill's
            # SidenoteProcessor claims any `column` with text children — which
            # is how the two text columns of a paper became 18 "Sidenote"
            # objects whose bodies are ordinary prose. The nesting belongs in
            # parent_id/children_ids, which every content line already carries.
            if line.get("type") == "column":
                continue
            record = dict(line)
            record["_page"] = pno
            record["_line_index"] = idx
            record["_image_id"] = page["image_id"]
            record["_geom"] = _geom(line, page)
            aid = anchor_id(record)
            if aid in payload:                 # identical lines do occur
                aid = anchor_id({**record, "_dup": len(anchors)})
            anchors.append(aid)
            payload[aid] = record
            per_page[pno].append(aid)

    objects: list[dict] = []
    for page, model_page in zip(lines_json["pages"], pages):
        pno = page["page"]
        ids = per_page[pno]
        if not ids:
            continue
        page_obj = object_id("Page", f"{bibkey}:{pno}")
        objects.append({
            "id": page_obj,
            "type": "Page",
            "props": {
                "page_number": pno,
                "image_id": page["image_id"],
                "page_height": page["page_height"],
                "page_width": page["page_width"],
                "languages_detected": [],
                "is_blank": False,
                "bibkey": bibkey,
            },
            "realizations": [_realization(ids[0], ids[-1], "surface")],
            "children": [],
            "parent": None,
        })
        objects.extend(_page_objects(page, model_page, ids, page_obj, bibkey))

    for obj in objects:
        if obj["parent"]:
            for other in objects:
                if other["id"] == obj["parent"]:
                    other["children"].append(obj["id"])
                    break

    return {
        "meta": {
            "bibkey": bibkey,
            "source_path": source_path,
            "source": "pdfminer-docmodel",
            "build": {
                "version": VERSION,
                "at": datetime.datetime.now(
                    datetime.timezone.utc).isoformat(timespec="seconds"),
            },
            "pages": [
                {"page": p["page"], "image_id": p["image_id"],
                 "page_height": p["page_height"],
                 "page_width": p["page_width"],
                 "languages_detected": []}
                for p in lines_json["pages"]
            ],
        },
        "streams": {
            STREAM: {"name": STREAM, "anchors": anchors, "payload": payload},
        },
        "objects": objects,
        # Empty by construction: alignments relate TWO streams, and we emit
        # one. A merge against a MathPix export fills this in -- see
        # mathpix_merge, which already resolves our regions against theirs.
        "alignments": [],
    }


def _geom(line: dict, page: dict) -> dict:
    """Normalised geometry, as the reference export carries it."""
    w = max(page["page_width"], 1)
    h = max(page["page_height"], 1)
    r = line["region"]
    return {
        "x0_norm": round(r["top_left_x"] / w, 4),
        "x1_norm": round((r["top_left_x"] + r["width"]) / w, 4),
        "y_norm": round(r["top_left_y"] / h, 4),
        "indent_norm": round(r["top_left_x"] / w, 4),
    }


def _page_objects(page: dict, model_page, ids: list[str],
                  page_obj: str, bibkey: str) -> list[dict]:
    """Objects our model can justify, and no others.

    A Paragraph is a run of consecutive text lines; a Formula is a line
    carrying mathematics; a Listing is a run of verbatim lines; a Diagram is
    a detected region. There are no Section or TableCell objects because
    nothing in our model identifies them -- inventing them would put
    unearned structure in a file whose whole purpose is to say what is known.
    """
    out: list[dict] = []
    run: list[int] = []
    run_kind = None

    def kind_of(i: int) -> str:
        line = model_page.lines[i]
        if line.verbatim:
            return "Listing"
        if any(sp.kind == "math" for sp in line.spans):
            return "Formula"
        return "Paragraph"

    def flush():
        if not run:
            return
        key = f"{bibkey}:{page['page']}:{run[0]}-{run[-1]}"
        out.append({
            "id": object_id(run_kind, key),
            "type": run_kind,
            "props": {"page_number": page["page"], "bibkey": bibkey},
            "realizations": [_realization(ids[run[0]], ids[run[-1]], "body")],
            "children": [],
            "parent": page_obj,
        })
        run.clear()

    for i in range(min(len(ids), len(model_page.lines))):
        kind = kind_of(i)
        if kind != run_kind:
            flush()
            run_kind = kind
        run.append(i)
    flush()

    for n, rect in enumerate(model_page.diagrams):
        out.append({
            "id": object_id("Diagram", f"{bibkey}:{page['page']}:{n}"),
            "type": "Diagram",
            "props": {
                "page_number": page["page"],
                "bibkey": bibkey,
                "region": docmodel._px_region(rect, model_page,
                                              docmodel.PX_PER_PT),
            },
            "realizations": [],
            "children": [],
            "parent": page_obj,
        })
    return out
