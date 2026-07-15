#!/usr/bin/env python3
"""Route matrix: build one docmodel per extraction route and tabulate
DocObject counts by type. Routes are lines.json variants found next to the
PDF by naming convention (absent -> column skipped):

  <stem>.tesseract.lines.json   OCR (enriched tesseract, PDFDRILLocr)
  <stem>.mathpix.lines.json     OCR++ (MathPix)  [falls back to
                                <stem>.lines.json when its source!=tesseract]
  <stem>.pdfminer.lines.json    pdfminer (DRILLPDFse)
  <stem>.latex.lines.json       LaTeX gold (source-built)

Usage: python3 tools/route_matrix.py <pdf> [<pdf> ...]
Writes <stem>.route-matrix.md next to each PDF and prints it.
"""
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from docmodel import main as dm_main  # noqa: E402

ROUTES = [("OCR (tesseract)", "{s}.tesseract.lines.json"),
          ("OCR++ (MathPix)", "{s}.mathpix.lines.json"),
          ("pdfminer", "{s}.pdfminer.lines.json"),
          ("LaTeX (gold)", "{s}.latex.lines.json")]


def counts_for(lines_path: Path, bibkey: str) -> Counter:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "model.json"
        dm_main.run(str(lines_path), dm_main.DEFAULT_CONFIG_PATH, bibkey,
                    str(out), [])
        m = json.loads(out.read_text())
    objs = m["objects"]
    objs = objs if isinstance(objs, list) else list(objs.values())
    return Counter(o["type"] for o in objs)


def matrix(pdf: Path) -> str:
    stem = pdf.parent / pdf.stem
    cols, data = [], []
    for label, pattern in ROUTES:
        p = Path(str(pattern).format(s=stem))
        if not p.is_file() and label.startswith("OCR++"):
            fallback = Path(f"{stem}.lines.json")
            if fallback.is_file():
                src = json.loads(fallback.read_text()).get("source")
                if src and src != "tesseract":
                    p = fallback
        if p.is_file():
            try:
                cols.append(label)
                data.append(counts_for(p, pdf.stem))
            except Exception as e:
                data.append(Counter({f"ERROR: {e}": 1}))
    if not cols:
        return f"## {pdf.name}\n\n(no route lines.json found)\n"
    types = sorted({t for c in data for t in c})
    lines = [f"## {pdf.name}", "",
             "| object type | " + " | ".join(cols) + " |",
             "|---|" + "---|" * len(cols)]
    for t in types:
        lines.append(f"| {t} | " +
                     " | ".join(str(c.get(t, "")) for c in data) + " |")
    lines.append("| **total** | " +
                 " | ".join(str(sum(c.values())) for c in data) + " |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        pdf = Path(arg)
        md = matrix(pdf)
        out = pdf.parent / f"{pdf.stem}.route-matrix.md"
        out.write_text(md, encoding="utf-8")
        print(md)
        print(f"[route_matrix] wrote {out}", file=sys.stderr)
