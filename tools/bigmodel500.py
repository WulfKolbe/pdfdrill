#!/usr/bin/env python3
r"""500 — why 1511.08771's model is 4.96 GB, counted without parsing it.

`json.loads` on this file costs 16.4 GB of resident memory and did not finish
its object loop in twenty minutes (499). So this streams: a chunked read with
a carry-over window, counting `"type": "X"` and hashing every `"latex"` value.
Nothing is held but the counters and a set of digests.
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
import sys
from pathlib import Path

CHUNK = 64 << 20
TYPE = re.compile(rb'"type"\s*:\s*"([A-Za-z]+)"')
#: a JSON string value for one of the content keys, with escapes left intact
VAL = re.compile(rb'"(latex|latex_code|text)"\s*:\s*"((?:[^"\\]|\\.)*)"')
OVERLAP = 4096


def stream(path: Path):
    types = collections.Counter()
    vals = collections.Counter()          # key -> total occurrences
    seen = {"latex": set(), "latex_code": set(), "text": set()}
    total = 0
    with path.open("rb") as fh:
        carry = b""
        while True:
            buf = fh.read(CHUNK)
            if not buf:
                break
            total += len(buf)
            data = carry + buf
            for m in TYPE.finditer(data):
                types[m.group(1).decode()] += 1
            for m in VAL.finditer(data):
                k = m.group(1).decode()
                vals[k] += 1
                seen[k].add(hashlib.blake2b(m.group(2), digest_size=8).digest())
            carry = data[-OVERLAP:]
            print("\r  %.2f GB read" % (total / 1e9), end="", file=sys.stderr,
                  flush=True)
    print(file=sys.stderr)
    return types, vals, {k: len(v) for k, v in seen.items()}, total


if __name__ == "__main__":
    p = Path(sys.argv[1])
    types, vals, distinct, total = stream(p)
    json.dump({"file": str(p), "bytes": total,
               "objects_by_type": dict(types.most_common()),
               "value_occurrences": dict(vals),
               "distinct_values": distinct},
              sys.stdout, indent=1)
