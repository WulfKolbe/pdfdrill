"""Evidence = every object of one kind, unbounded, six columns. Lookup, not
reading matter. No ink, no legend, no findings, no cell-rect marks."""
from __future__ import annotations

from pathlib import Path

from .. import report_tex as rt
from . import KINDS
from . import html as H
from . import tex as T

OUTPUT = "evidence-%s.%s"
FORMATS = ("html", "pdf")


def ordered(rows: list, kind: str) -> list:
    if kind != "equation":
        return list(rows)
    return sorted(rows, key=lambda r: (r.confidence if r.confidence is not None
                                       else 2.0))


def build(rows_by_kind: dict, kind: str, fmt: str, *, doc_dir, pdf, bibkey,
          history, px2mm, paper, landscape, compile_pdf) -> dict:
    if kind not in KINDS:
        raise ValueError("kind must be one of %s, not %r" % (", ".join(KINDS), kind))
    if fmt not in FORMATS:
        raise ValueError("format must be html or pdf, not %r" % fmt)
    doc_dir = Path(doc_dir)
    rows = ordered(rows_by_kind.get(kind, []), kind)
    title = "%s: %s evidence" % (bibkey, kind)
    if fmt == "html":
        out = doc_dir / (OUTPUT % (kind, "html"))
        out.write_text(H.render_page(rows, kind, title=title, doc_dir=doc_dir,
                                     meta_lines=("%d rows" % len(rows),)),
                       encoding="utf-8")
        return {"out": out, "rows": len(rows), "pages": None, "errors": 0,
                "demoted": 0}
    widths = T.widths_for(paper, landscape, with_image=True)
    body = T.render_table(rows, kind, widths=widths, out_dir=doc_dir,
                          px2mm=px2mm, bibkey=bibkey, history=history)
    tex_path = doc_dir / (OUTPUT % (kind, "tex"))
    tex_path.write_text(T.document(body, paper=paper, landscape=landscape,
                                   pages=None, title=title), encoding="utf-8")
    res = {"out": tex_path.with_suffix(".pdf"), "rows": len(rows),
           "pages": None, "errors": 0, "demoted": 0}
    if compile_pdf:
        c = rt.compile_fixpoint(tex_path)
        if c is not None:
            res["pages"], res["errors"], res["demoted"] = c
    return res
