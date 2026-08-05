"""
JSON writing that survives a filename which is not valid UTF-8.

A path whose bytes are not valid UTF-8 arrives from the filesystem
surrogate-escaped, and `json.dump(..., ensure_ascii=False)` into a utf-8 stream
cannot encode a lone surrogate. Those paths reach artifact payloads through
`source_path`, `bibkey`, stream names and props, so the write raises and the
document becomes unbuildable by every route — 18 such folders existed in one
library, and each failed its whole rebuild.

`ensure_ascii=True` escapes the surrogate to plain ASCII, which round-trips back
through `json.loads`, so nothing is lost. It is used only as a FALLBACK, leaving
every ordinary artifact byte-for-byte as before (umlauts stay unescaped).
"""
from __future__ import annotations

import json
from typing import Any, TextIO


def dumps(obj: Any, **kw: Any) -> str:
    """`json.dumps` with ensure_ascii=False, falling back to True when the result
    cannot be encoded as UTF-8."""
    kw.setdefault("default", str)
    text = json.dumps(obj, ensure_ascii=False, **kw)
    try:
        text.encode("utf-8")
        return text
    except UnicodeEncodeError:
        return json.dumps(obj, ensure_ascii=True, **kw)


def dump(obj: Any, fp: TextIO, **kw: Any) -> None:
    """`json.dump` with the same fallback. Writes in one go so a failed encode
    cannot leave a half-written file behind."""
    fp.write(dumps(obj, **kw))
