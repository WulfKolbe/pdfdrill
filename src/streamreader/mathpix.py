# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""MathPix lines.json vocabulary. The only module that names its keys.

The allow-lists are the keys found in 354 MathPix exports (1.53M lines) of
~/pdfdrill-library. A paragraph is not an element there: it is a run of text
lines whose first `text_display` starts with a blank line and whose
continuations start with a space.
"""
from __future__ import annotations

import hashlib
import json
import re

PAGE_KEYS = frozenset({
    "image_id", "page", "lines", "page_height", "page_width",
    "languages_detected", "parse_status", "fallback_count", "page_confidence",
})
LINE_KEYS = frozenset({
    "cnt", "region", "line", "column", "font_size", "is_printed",
    "is_handwritten", "id", "type", "conversion_output", "text",
    "text_display", "confidence", "confidence_rate", "parent_id",
    "children_ids", "subtype", "selected_labels", "cell_row", "cell_column",
    "cell_row_span", "cell_col_span", "parse_status", "text_confidence",
    "layout_confidence",
})


def image_id(doc_id: str, page: int) -> str:
    return f"{doc_id}-{page:03d}"


def line_id(doc_id: str, page: int, line: int) -> str:
    key = f"{doc_id}/{page}/{line}".encode("utf-8")
    return hashlib.blake2b(key, digest_size=16).hexdigest()


_ESCAPE = re.compile(r"[#$%&]")
_UNESCAPE = re.compile(r"\\([#$%&])")


# control characters but tab and line end, the soft hyphen, the byte
# order mark
_UNSEEN = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u00ad\ufeff]")


def seen(text: str) -> str:
    """`text` without the characters no reader sees: a NUL turns the file
    binary for grep, a soft hyphen hides the word from a search."""
    return _UNSEEN.sub("", text)


def escape(text: str) -> str:
    """MathPix text is LaTeX-flavoured: `# $ % &` carry a backslash, an
    underscore does not (26 exports: 200 escaped against 0 bare for the
    four, 71 bare against 2 escaped for `_`). Characters no reader sees
    are left out."""
    return _ESCAPE.sub(lambda m: "\\" + m.group(0), seen(text))


def plain(text: str) -> str:
    """Undo `escape`."""
    return _UNESCAPE.sub(r"\1", text)


def line(doc_id: str, page: int, line: int, type: str, text: str,
         display: str, box: tuple[int, int, int, int] = (0, 0, 0, 0),
         font_size: int = 0, conversion_output: bool = True,
         parent_id: str | None = None) -> dict:
    """A content line. `box` is (x0, y0, x1, y1) in page pixels; all zero
    when unmeasured."""
    x0, y0, x1, y1 = box
    out = {
        "cnt": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
        "region": {"top_left_x": x0, "top_left_y": y0,
                   "width": x1 - x0, "height": y1 - y0},
        "line": line,
        "column": 0,
        "font_size": font_size,
        "is_printed": True,
        "is_handwritten": False,
        "id": line_id(doc_id, page, line),
        "type": type,
        "conversion_output": conversion_output,
    }
    if parent_id is not None:
        out["parent_id"] = parent_id
    out.update({"text": text, "text_display": display,
                "confidence": 1, "confidence_rate": 1})
    return out


def container(doc_id: str, page: int, line: int, type: str,
              box: tuple[int, int, int, int], font_size: int,
              children_ids: list[str]) -> dict:
    """A line that only groups others: no text, no output of its own."""
    out = globals()["line"](doc_id, page, line, type, "", "", box, font_size,
                            conversion_output=False)
    del out["confidence"], out["confidence_rate"]
    text, display = out.pop("text"), out.pop("text_display")
    out.update({"children_ids": children_ids, "text": text,
                "text_display": display})
    return out


def text_line(doc_id: str, page: int, line: int, text: str,
              starts_paragraph: bool,
              box: tuple[int, int, int, int] = (0, 0, 0, 0),
              font_size: int = 0) -> dict:
    return globals()["line"](
        doc_id, page, line, "text", text,
        ("\n\n" if starts_paragraph else " ") + text, box, font_size)


def page(doc_id: str, page: int, lines: list[dict],
         width: int = 0, height: int = 0) -> dict:
    return {
        "image_id": image_id(doc_id, page),
        "page": page,
        "lines": lines,
        "page_height": height,
        "page_width": width,
        "languages_detected": [],
    }


def page_url(base: str, image_id: str) -> str:
    return f"{base.rstrip('/')}/cropped/{image_id}.jpg"


def written_by_us(data, doc_id: str) -> bool:
    """True when `data` is a lines.json this program wrote for `doc_id`.

    The format has no key to say who wrote a file, so the test is the ids:
    ours are derived from the document name, page and line number, and no
    other writer produces those values.
    """
    try:
        pages = data["pages"]
        if not pages:
            return False
        for pg in pages:
            if pg["image_id"] != image_id(doc_id, pg["page"]):
                return False
            for ln in pg["lines"]:
                return ln["id"] == line_id(doc_id, pg["page"], ln["line"])
        return True
    except (KeyError, TypeError):
        return False


def pretty(data, lines_depth: int = 4) -> str:
    """JSON for reading in an editor: one key per row down to the line
    objects, each of their values on a single row (a `cnt` or `region`
    spread over many rows hides the text between them). `lines_depth` is how
    deep the line objects sit: 4 in a whole lines.json, 2 in one page."""
    def inline(value) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))

    def render(value, depth: int) -> str:
        pad, inner = "  " * depth, "  " * (depth + 1)
        if depth > lines_depth or not value or not isinstance(value,
                                                              (dict, list)):
            return inline(value)
        if isinstance(value, dict):
            rows = [f"{inner}{json.dumps(k)}: {render(v, depth + 1)}"
                    for k, v in value.items()]
            return "{\n" + ",\n".join(rows) + f"\n{pad}}}"
        rows = [inner + render(v, depth + 1) for v in value]
        return "[\n" + ",\n".join(rows) + f"\n{pad}]"

    return render(data, 0) + "\n"
