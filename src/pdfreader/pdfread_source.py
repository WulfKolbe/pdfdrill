r"""The build's reads, taken from pdfread's records instead of pdfminer's pass.

T-0174: `pdfread records FILE` (pdf2mmd3, C) writes per page the glyph, path
and image records pdfminer's interpreter and `inkboxes` produce, bit-equal
(contract: ~/drillgroup/contracts/pdfread-records.md). This module turns
them into exactly what `docmodel_six.build` takes from its own pass:

    pairs   (layout, stream order, ink records) per page, as
            `_pages_with_order(..., ink=...)` yields them
    links   `_page_links`
    bands   `_line_bands`
    crop    `_cropboxes`

The layout is pdfminer's own: the records become LTChar / LTLine / LTRect /
LTCurve / LTImage-in-LTFigure objects, added to an LTPage in drawing order,
and `LTPage.analyze(LAParams())` groups them -- the same code the default
path runs, so the text boxes, their order and the walk index the build sees
are pdfminer's. Only the interpretation (content streams, fonts, programs)
is replaced, and that is the reader's cost.

Selected by PDFDRILL_READER=pdfread; the binary is $PDFREAD or `pdfread` on
PATH. pdfminer stays the default and the twin. Tested against pdf2mmd3
bed59ed (TESTED_WITH).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

TESTED_WITH = "bed59ed"
_NO_OUTLINE = "the font program states no outline for this name"


class ReaderUnavailable(RuntimeError):
    """pdfread could not deliver records for this document."""


def wanted() -> bool:
    return os.environ.get("PDFDRILL_READER", "").strip().lower() == "pdfread"


def binary() -> str | None:
    b = os.environ.get("PDFREAD") or "pdfread"
    if os.sep in b:
        return b if os.access(b, os.X_OK) else None
    return shutil.which(b)


_IDENT: dict = {}


def identity() -> str:
    """`pdfread bin:<sha256, 12>` of the binary that would run.

    pdfread states no version of its own, and a commit cannot be read off a
    binary; its content can. Cached per (path, mtime, size).
    """
    import hashlib
    exe = binary()
    if exe is None:
        return "pdfread missing"
    st = os.stat(exe)
    key = (exe, st.st_mtime_ns, st.st_size)
    if key not in _IDENT:
        h = hashlib.sha256()
        with open(exe, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        _IDENT[key] = "pdfread bin:" + h.hexdigest()[:12]
    return _IDENT[key]


def pdfminer_identity() -> str:
    try:
        import pdfminer
        return "pdfminer " + str(pdfminer.__version__)
    except Exception:                                        # noqa: BLE001
        return "pdfminer"


def _runs(pages):
    """Contiguous 1-based ranges for 0-based page indices."""
    ps = sorted(set(int(p) + 1 for p in pages))
    out, start, prev = [], None, None
    for p in ps:
        if start is None:
            start = prev = p
        elif p == prev + 1:
            prev = p
        else:
            out.append((start, prev))
            start = prev = p
    if start is not None:
        out.append((start, prev))
    return out


def _records(path: str, pages):
    exe = binary()
    if exe is None:
        raise ReaderUnavailable("pdfread not found ($PDFREAD or PATH)")
    calls = [[exe, "records", path]] if pages is None else [
        [exe, "records", path, "--pages", f"{a}-{b}"] for a, b in _runs(pages)]
    for argv in calls:
        r = subprocess.run(argv, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
        if r.returncode != 0:
            raise ReaderUnavailable(
                f"pdfread exit {r.returncode}: "
                + r.stderr.decode("utf-8", "replace").strip()[:200])
        for line in r.stdout.splitlines():
            if line:
                yield json.loads(line)


class _GState:
    """What the build reads of `LTChar.graphicstate`: the fill colour."""
    __slots__ = ("ncolor",)

    def __init__(self, ncolor):
        self.ncolor = ncolor


def _bbox(o, b):
    x0, y0, x1, y1 = b
    o.x0, o.y0, o.x1, o.y1 = x0, y0, x1, y1
    o.width, o.height = x1 - x0, y1 - y0
    o.bbox = (x0, y0, x1, y1)


def _char(r):
    from pdfminer.layout import LTChar, glyphname_reliable
    c = LTChar.__new__(LTChar)
    c._text = r["text"]
    c.matrix = tuple(r["matrix"])
    c.fontname = r["font"]
    c.cid = r["cid"]
    c.glyphname = r["glyphname"]
    c.glyphname_reliable = glyphname_reliable(c.glyphname, c.fontname)
    # the build's interpreter carries Tr into forms (b9596a58): its
    # LTChar.render_mode is the standard's, which pdfread names _pdf
    c.render_mode = r["render_mode_pdf"]
    c.fontsize = r["tf"]
    c.scaling = r["scaling"]
    c.rise = r["rise"]
    c.ncs = None
    c.graphicstate = _GState(r.get("fill_raw"))
    c.adv = r["adv"]
    c.upright = r["upright"]
    _bbox(c, r["bbox"])
    c.size = r["size"]
    return c


def _path(r):
    from pdfminer.layout import LTCurve, LTLine, LTRect
    cls = {"line": LTLine, "rect": LTRect}.get(r["kind"], LTCurve)
    o = cls.__new__(cls)
    _bbox(o, r["bbox"])
    o.pts = None
    o.linewidth = r["linewidth"]
    o.stroke = r["stroke"]
    o.fill = r["fill"]
    o.evenodd = r["evenodd"]
    o.stroking_color = r.get("stroke_raw")
    o.non_stroking_color = r.get("fill_raw")
    o.original_path = None
    o.dashing_style = None
    return o


def _image(r):
    """pdfminer wraps every image (XObject or inline) in its own LTFigure."""
    from pdfminer.layout import LTFigure, LTImage
    f = LTFigure.__new__(LTFigure)
    f.name, f.matrix, f.groups, f._objs = None, None, None, []
    _bbox(f, r["bbox"])
    im = LTImage.__new__(LTImage)
    _bbox(im, r["bbox"])
    im.name, im.stream = None, None
    im.srcsize = (r.get("width"), r.get("height"))
    im.imagemask = None
    im.bits = r.get("bpc")
    im.colorspace = [r.get("colorspace")]
    f._objs.append(im)
    return f


def _page_box(rec):
    from pdfminer.utils import apply_matrix_rect
    x0, y0, x1, y1 = rec["mediabox"]
    rot = rec.get("rotate", 0)
    if rot == 90:
        ctm = (0, -1, 1, 0, -y0, x1)
    elif rot == 180:
        ctm = (-1, 0, 0, -1, x1, y1)
    elif rot == 270:
        ctm = (0, 1, -1, 0, y1, -x0)
    else:
        ctm = (1, 0, 0, 1, -x0, -y0)
    a0, b0, a1, b1 = apply_matrix_rect(ctm, (x0, y0, x1, y1))
    return (0, 0, abs(a0 - a1), abs(b0 - b1))


def read(path: str, pages, ink: bool):
    """{pairs, links, bands, crop} from pdfread, or ReaderUnavailable."""
    from pdfminer.layout import LAParams, LTPage
    from pdfreader.docmodel_six import LinkNode

    pairs, links, bands, crop = [], {}, {}, {}
    page = seen = recs = stack = None
    pageno, gi = 0, 0
    for r in _records(path, pages):
        t = r.get("t")
        if t == "page":
            pageno += 1
            pno = r["page"]
            page = LTPage(pageno, _page_box(r))
            stack = [page]
            seen, recs, gi = {}, ([] if ink else None), 0
            cb = r.get("cropbox") or r["mediabox"]
            crop[pno] = tuple(float(v) for v in cb)
            found = []
            for lk in r.get("links") or []:
                rect = lk["rect"]
                found.append(LinkNode(
                    rect=(min(rect[0], rect[2]), min(rect[1], rect[3]),
                          max(rect[0], rect[2]), max(rect[1], rect[3])),
                    uri=lk.get("uri"),
                    dest=_dest(lk.get("dest"))))
            if found:
                links[pno] = found
            ys = sorted({round(y, 2) for y in r.get("line_starts") or []},
                        reverse=True)
            bands[pno] = [0.5 * (a + b) for a, b in zip(ys, ys[1:])]
        elif t == "glyph":
            c = _char(r)
            stack[-1].add(c)
            key = (round(c.matrix[4], 1), round(c.matrix[5], 1), c._text)
            if key not in seen:
                seen[key] = gi
            gi += 1
            if recs is not None:
                ib = r.get("ink")
                why = None if ib else r.get("ink_why")
                if why == _NO_OUTLINE and r.get("ink_name"):
                    # inkboxes names the glyph in this one reason
                    why = f"the font program states no outline for {r['ink_name']!r}"
                recs.append({
                    "ink_reason": why,
                    "name": r.get("ink_name"),
                    "font": c.fontname.split("+")[-1],
                    "ink": tuple(ib) if ib else None,
                    "pdfminer": c.bbox,
                    "size": c.size,
                    "base": c.matrix[5],
                    "cid": c.cid,
                    "render_mode": c.render_mode,
                })
        elif t == "path":
            stack[-1].add(_path(r))
        elif t == "image":
            stack[-1].add(_image(r))
        elif t == "form":
            from pdfminer.layout import LTFigure
            f = LTFigure.__new__(LTFigure)
            f.name, f.matrix, f.groups, f._objs = (
                r.get("name"), tuple(r.get("matrix") or ()), None, [])
            _bbox(f, r.get("bbox") or (0, 0, 0, 0))
            stack[-1].add(f)
            stack.append(f)
        elif t == "form_end":
            stack.pop()
        elif t == "end":
            page.analyze(LAParams())
            pairs.append((page, seen, recs) if ink else (page, seen))
    return {"pairs": pairs, "links": links, "bands": bands, "crop": crop}


def _dest(d):
    """`docmodel_six._dest_text`'s form: the name, or [page, x, y] as JSON."""
    if d is None or isinstance(d, str):
        return d

    def num(v):
        if v is None or isinstance(v, bool):
            return v
        return int(v) if float(v).is_integer() else float(v)

    return json.dumps([d[0]] + [num(v) for v in d[1:3]])
