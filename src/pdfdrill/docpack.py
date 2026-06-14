#!/usr/bin/env python3
"""docpack.py - lossless, reference-based compaction of a pdfdrill docmodel.

The pdfdrill ``*.docmodel.json`` is a stratified anchored graph:

    meta        small header (bibkey, pages, latex preamble, geometry overrides)
    streams     name -> {name, anchors:[a_xxxxxxxxxxxx], payload:{anchor:obj}}
    objects     [ {id,type,props,realizations,children,parent} ]
    alignments  [ {kind,left,right,props} ]  with left/right = {stream,start,end,...}

Almost all of the bytes are accidental, not essential:

  * ~1900 *character streams* store one ``{"codepoint":"x"}`` dict **and** one
    14-char anchor id **per character** of every dehyphenated paragraph and every
    rendered LaTeX equation.  That single fact is ~75 % of the file.
  * the line stream repeats ``_image_id``, ``pdf_text``, geometry boxes and
    (font_size, confidence, ...) profiles on every one of 5k lines.
  * object/alignment endpoints repeat 14-char anchor ids and stream names.

``pack`` rewrites all of this against shared tables so each unique value is
stored once; ``unpack`` reverses it.  The transform is *value-lossless*:

    unpack(pack(model)) == model          # python equality (key order ignored)

Because the round-trip reproduces the exact docmodel, every downstream pdfdrill
projection (tiddlers / semantic / llm / rulebook / tables ...) regenerates
identically -- just feed the unpacked model to the normal projector pipeline.
See ``project.py`` for projectors that read the packed model directly.

stdlib only.  CLI:

    python docpack.py pack   model.docmodel.json  model.docpack.json [--gz]
    python docpack.py unpack model.docpack.json   roundtrip.docmodel.json
    python docpack.py verify model.docmodel.json            # pack+unpack==orig
"""
from __future__ import annotations

import gzip
import json
import sys
from typing import Any

FORMAT_VERSION = 1

# ---------------------------------------------------------------------------
# small helpers: a value-interning table keyed by canonical JSON
# ---------------------------------------------------------------------------


class Table:
    """Append-only intern table.  ``idx(value)`` returns a stable int id."""

    def __init__(self) -> None:
        self.items: list[Any] = []
        self._index: dict[str, int] = {}

    def idx(self, value: Any) -> int:
        key = json.dumps(value, sort_keys=True, ensure_ascii=False)
        i = self._index.get(key)
        if i is None:
            i = len(self.items)
            self._index[key] = i
            self.items.append(value)
        return i


# Anchor ids are uniformly ``a_`` + 12 lowercase hex (verified).  We store the
# 12 hex chars only; cross-referenced anchors additionally get an int id.
ANCHOR_PREFIX = "a_"
ANCHOR_HEX = 12


def _strip_anchor(a: str) -> str:
    assert a.startswith(ANCHOR_PREFIX) and len(a) == 2 + ANCHOR_HEX, a
    return a[2:]


def _restore_anchor(h: str) -> str:
    return ANCHOR_PREFIX + h


# Field names whose *string* value (or list-of-string value) is interned into
# the shared string table, wherever they occur in props/payloads.
# String fields interned in *line payloads* (here ``id`` is always the 32-hex
# mathpix line id -- never an int).
STR_KEYS = {
    "text", "text_display", "pdf_text", "id", "_image_id", "image_id",
    "bibkey", "content_hash", "title", "target_url", "parent_id", "codepoint",
    "caption",
}
# String fields interned by the *recursive* pass over props/alignments.  ``id``
# is excluded because in nested NLP token tables it is an integer index, which
# would be indistinguishable from an intern reference on the way back.
STR_KEYS_REC = STR_KEYS - {"id"}
STR_LIST_KEYS = {"children_ids", "selected_labels"}

# Profile keys collapsed (per line) into one PROF table reference.
PROF_KEYS = (
    "font_size", "confidence", "confidence_rate",
    "is_printed", "is_handwritten", "conversion_output",
)


# ---------------------------------------------------------------------------
# packing
# ---------------------------------------------------------------------------


class Packer:
    def __init__(self) -> None:
        self.STR = Table()
        self.BOX = Table()     # cnt corner lists
        self.REG = Table()     # region dicts
        self.GEOM = Table()    # _geom dicts (pdf_text already interned)
        self.PROF = Table()    # (font_size, confidence, ...) profiles
        self.SNAME = Table()   # stream names used in refs
        self.OTYPE = Table()   # object types
        self.AKIND = Table()   # alignment kinds
        self.ROLE = Table()    # realization roles
        self.ANC = Table()     # cross-referenced anchor ids (a_ stripped)

    # -- string interning helpers ------------------------------------------
    def _intern_strs(self, obj: Any) -> Any:
        """Recursively replace known string fields with STR indices."""
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if k in STR_KEYS_REC and isinstance(v, str):
                    out[k] = self.STR.idx(v)
                elif k in STR_LIST_KEYS and isinstance(v, list):
                    out[k] = [self.STR.idx(e) if isinstance(e, str) else self._intern_strs(e) for e in v]
                else:
                    out[k] = self._intern_strs(v)
            return out
        if isinstance(obj, list):
            return [self._intern_strs(e) for e in obj]
        return obj

    def _anc(self, a: str | None) -> int | None:
        return None if a is None else self.ANC.idx(_strip_anchor(a))

    def _ref(self, ref: dict) -> dict:
        out = dict(ref)
        if "stream" in out and out["stream"] is not None:
            out["stream"] = self.SNAME.idx(out["stream"])
        if "start" in out:
            out["start"] = self._anc(out["start"])
        if "end" in out:
            out["end"] = self._anc(out["end"])
        if out.get("props"):
            out["props"] = self._intern_strs(out["props"])
        return out

    # -- line payload packing ----------------------------------------------
    def _pack_line(self, line: dict) -> dict:
        out: dict[str, Any] = {}
        prof = {}
        for k, v in line.items():
            if k == "cnt":
                out["cnt"] = self.BOX.idx(v)
            elif k == "region":
                out["region"] = self.REG.idx(v)
            elif k == "_geom":
                out["_geom"] = self.GEOM.idx(self._intern_strs(v))
            elif k in PROF_KEYS:
                prof[k] = v
            elif k in STR_KEYS and isinstance(v, str):
                out[k] = self.STR.idx(v)
            elif k in STR_LIST_KEYS and isinstance(v, list):
                out[k] = [self.STR.idx(e) if isinstance(e, str) else e for e in v]
            else:
                out[k] = self._intern_strs(v)
        # record which profile keys were present, so unpack restores exactly
        out["_prof"] = [self.PROF.idx(prof), sorted(prof.keys())]
        return out

    # -- stream packing -----------------------------------------------------
    def _pack_stream(self, s: dict) -> dict:
        anchors = s["anchors"]
        payload = s["payload"]
        ah = "".join(_strip_anchor(a) for a in anchors)
        vals = [payload[a] for a in anchors]
        is_char = bool(vals) and all(
            isinstance(v, dict) and set(v.keys()) == {"codepoint"} and len(v["codepoint"]) == 1
            for v in vals
        )
        if is_char:
            return {"k": "c", "ah": ah, "t": "".join(v["codepoint"] for v in vals)}
        return {"k": "p", "ah": ah, "p": [self._pack_line(v) for v in vals]}

    # -- top level ----------------------------------------------------------
    def pack(self, model: dict) -> dict:
        streams = {name: self._pack_stream(s) for name, s in model["streams"].items()}

        objects = []
        for o in model["objects"]:
            po = {
                "id": self.STR.idx(o["id"]),
                "type": self.OTYPE.idx(o["type"]),
                "props": self._intern_strs(o.get("props", {})),
                "realizations": [self._pack_realization(r) for r in o.get("realizations", [])],
                "children": [self.STR.idx(c) for c in o.get("children", [])],
                "parent": None if o.get("parent") is None else self.STR.idx(o["parent"]),
            }
            objects.append(po)

        alignments = []
        for a in model["alignments"]:
            alignments.append({
                "kind": self.AKIND.idx(a["kind"]),
                "left": self._ref(a["left"]),
                "right": self._ref(a["right"]),
                "props": self._intern_strs(a.get("props", {})),
            })

        return {
            "docpack": FORMAT_VERSION,
            "meta": model["meta"],
            "tables": {
                "STR": self.STR.items, "BOX": self.BOX.items, "REG": self.REG.items,
                "GEOM": self.GEOM.items, "PROF": self.PROF.items, "SNAME": self.SNAME.items,
                "OTYPE": self.OTYPE.items, "AKIND": self.AKIND.items, "ROLE": self.ROLE.items,
                "ANC": self.ANC.items,
            },
            "streams": streams,
            "objects": objects,
            "alignments": alignments,
        }

    def _pack_realization(self, r: dict) -> dict:
        out = dict(r)
        out["stream"] = self.SNAME.idx(r["stream"])
        if "start" in out:
            out["start"] = self._anc(out["start"])
        if "end" in out:
            out["end"] = self._anc(out["end"])
        if "role" in out:
            out["role"] = self.ROLE.idx(out["role"])
        if out.get("props"):
            out["props"] = self._intern_strs(out["props"])
        return out


# ---------------------------------------------------------------------------
# unpacking
# ---------------------------------------------------------------------------


class Unpacker:
    def __init__(self, packed: dict) -> None:
        t = packed["tables"]
        self.STR = t["STR"]; self.BOX = t["BOX"]; self.REG = t["REG"]
        self.GEOM = t["GEOM"]; self.PROF = t["PROF"]; self.SNAME = t["SNAME"]
        self.OTYPE = t["OTYPE"]; self.AKIND = t["AKIND"]; self.ROLE = t["ROLE"]
        self.ANC = t["ANC"]
        self.packed = packed

    def _de_strs(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if k in STR_KEYS_REC and isinstance(v, int):
                    out[k] = self.STR[v]
                elif k in STR_LIST_KEYS and isinstance(v, list):
                    out[k] = [self.STR[e] if isinstance(e, int) else self._de_strs(e) for e in v]
                else:
                    out[k] = self._de_strs(v)
            return out
        if isinstance(obj, list):
            return [self._de_strs(e) for e in obj]
        return obj

    def _anc(self, i: int | None) -> str | None:
        return None if i is None else _restore_anchor(self.ANC[i])

    def _ref(self, ref: dict) -> dict:
        out = dict(ref)
        if "stream" in out and out["stream"] is not None:
            out["stream"] = self.SNAME[out["stream"]]
        if "start" in out:
            out["start"] = self._anc(out["start"])
        if "end" in out:
            out["end"] = self._anc(out["end"])
        if out.get("props"):
            out["props"] = self._de_strs(out["props"])
        return out

    def _de_geom(self, i: int) -> dict:
        return self._de_strs(self.GEOM[i])

    def _unpack_line(self, pl: dict) -> dict:
        out: dict[str, Any] = {}
        for k, v in pl.items():
            if k == "_prof":
                idx, keys = v
                prof = self.PROF[idx]
                for pk in keys:
                    out[pk] = prof[pk]
            elif k == "cnt":
                out["cnt"] = self.BOX[v]
            elif k == "region":
                out["region"] = self.REG[v]
            elif k == "_geom":
                out["_geom"] = self._de_geom(v)
            elif k in STR_KEYS and isinstance(v, int):
                out[k] = self.STR[v]
            elif k in STR_LIST_KEYS and isinstance(v, list):
                out[k] = [self.STR[e] if isinstance(e, int) else e for e in v]
            else:
                out[k] = self._de_strs(v)
        return out

    def _anchors_from_hex(self, ah: str) -> list[str]:
        return [_restore_anchor(ah[i:i + ANCHOR_HEX]) for i in range(0, len(ah), ANCHOR_HEX)]

    def _unpack_stream(self, name: str, s: dict) -> dict:
        anchors = self._anchors_from_hex(s["ah"])
        if s["k"] == "c":
            payload = {a: {"codepoint": c} for a, c in zip(anchors, s["t"])}
        else:
            payload = {a: self._unpack_line(v) for a, v in zip(anchors, s["p"])}
        return {"name": name, "anchors": anchors, "payload": payload}

    def _unpack_realization(self, r: dict) -> dict:
        out = dict(r)
        out["stream"] = self.SNAME[r["stream"]]
        if "start" in out:
            out["start"] = self._anc(out["start"])
        if "end" in out:
            out["end"] = self._anc(out["end"])
        if "role" in out:
            out["role"] = self.ROLE[out["role"]]
        if out.get("props"):
            out["props"] = self._de_strs(out["props"])
        return out

    def unpack(self) -> dict:
        p = self.packed
        streams = {name: self._unpack_stream(name, s) for name, s in p["streams"].items()}
        objects = []
        for o in p["objects"]:
            objects.append({
                "id": self.STR[o["id"]],
                "type": self.OTYPE[o["type"]],
                "props": self._de_strs(o.get("props", {})),
                "realizations": [self._unpack_realization(r) for r in o.get("realizations", [])],
                "children": [self.STR[c] for c in o.get("children", [])],
                "parent": None if o.get("parent") is None else self.STR[o["parent"]],
            })
        alignments = []
        for a in p["alignments"]:
            alignments.append({
                "kind": self.AKIND[a["kind"]],
                "left": self._ref(a["left"]),
                "right": self._ref(a["right"]),
                "props": self._de_strs(a.get("props", {})),
            })
        return {"meta": p["meta"], "streams": streams, "objects": objects, "alignments": alignments}


# ---------------------------------------------------------------------------
# public API + CLI
# ---------------------------------------------------------------------------


def pack(model: dict) -> dict:
    return Packer().pack(model)


def unpack(packed: dict) -> dict:
    return Unpacker(packed).unpack()


def _load(path: str) -> dict:
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _dump(obj: dict, path: str) -> int:
    op = gzip.open if path.endswith(".gz") else open
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    with op(path, "wt", encoding="utf-8") as f:
        f.write(data)
    import os as _os
    return _os.path.getsize(path)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == "pack":
        src, dst = argv[1], argv[2]
        gz = "--gz" in argv[3:]
        if gz and not dst.endswith(".gz"):
            dst += ".gz"
        model = _load(src)
        packed = pack(model)
        n = _dump(packed, dst)
        # sanity round-trip
        assert unpack(packed) == model, "round-trip mismatch!"
        print(f"packed {src} -> {dst}  ({n:,} bytes, round-trip verified)")
    elif cmd == "unpack":
        src, dst = argv[1], argv[2]
        packed = _load(src)
        model = unpack(packed)
        n = _dump(model, dst)
        print(f"unpacked {src} -> {dst}  ({n:,} bytes)")
    elif cmd == "verify":
        src = argv[1]
        model = _load(src)
        packed = pack(model)
        ok = unpack(packed) == model
        print("round-trip:", "OK" if ok else "MISMATCH")
        return 0 if ok else 2
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
