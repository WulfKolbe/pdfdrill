#!/usr/bin/env python3
"""Build an inkdrill-comparable fixture from a local DaTikZ-V4 parquet set.

Reads parquet directly — no network, no datasets cache. Emits, per row:
  <out>/tikz/<id>.tex        the author's tikz_code, wrapped standalone
  <out>/png/<id>.png         the dataset's own render (448x448)
  <out>/manifest.json        id, source, caption, vlm_description, paths

The two images per row are what a report compares: our compile of the
code against the dataset's render of the same code. Neither is a scan,
so this measures the renderer, not a reading.
"""
from __future__ import annotations
import argparse, io, json, sys
from pathlib import Path

STANDALONE = (
    "\\documentclass[border=2pt,tikz]{standalone}\n"
    "\\usepackage{amsmath,amssymb,amsfonts}\n"
    "\\usepackage{pgfplots}\\pgfplotsset{compat=newest}\n"
    "\\usetikzlibrary{arrows.meta,positioning,calc,shapes,patterns,decorations.pathmorphing,matrix,cd}\n"
    "\\begin{document}\n%s\n\\end{document}\n"
)

def find_parquet(root: Path) -> dict[str, list[Path]]:
    """Group parquet files by split, inferred from path. Reports what it finds."""
    splits: dict[str, list[Path]] = {}
    for p in sorted(root.rglob("*.parquet")):
        low = str(p).lower()
        split = "test" if "test" in low else "train" if "train" in low else "unsplit"
        splits.setdefault(split, []).append(p)
    return splits

def rows(files: list[Path], limit: int):
    import pyarrow.parquet as pq
    seen = 0
    for f in files:
        pf = pq.ParquetFile(f)
        for batch in pf.iter_batches(batch_size=64):
            for rec in batch.to_pylist():
                yield rec
                seen += 1
                if seen >= limit:
                    return

def png_bytes(cell) -> bytes | None:
    """HF Image feature stores {'bytes':..., 'path':...}; tolerate raw bytes."""
    if isinstance(cell, dict):
        return cell.get("bytes")
    if isinstance(cell, (bytes, bytearray)):
        return bytes(cell)
    return None

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path.home() / "Downloads")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--split", default="train")
    ap.add_argument("--limit", type=int, required=True)
    a = ap.parse_args()

    splits = find_parquet(a.root)
    if not splits:
        print(f"no parquet under {a.root}", file=sys.stderr)
        return 1
    print("splits found: " + ", ".join(
        f"{k} ({len(v)} files)" for k, v in sorted(splits.items())))
    if a.split not in splits:
        print(f"split {a.split!r} absent", file=sys.stderr)
        return 1

    (a.out / "tikz").mkdir(parents=True, exist_ok=True)
    (a.out / "png").mkdir(parents=True, exist_ok=True)
    manifest, no_png, no_code = [], 0, 0

    for i, rec in enumerate(rows(splits[a.split], a.limit)):
        rid = f"DTZ{i:05d}"
        code = rec.get("tikz_code") or ""
        if not code.strip():
            no_code += 1
            continue
        tex = a.out / "tikz" / f"{rid}.tex"
        tex.write_text(STANDALONE % code, encoding="utf-8")

        raw = png_bytes(rec.get("png_image"))
        png = a.out / "png" / f"{rid}.png"
        if raw:
            png.write_bytes(raw)
        else:
            no_png += 1

        manifest.append({
            "id": rid,
            "source": rec.get("source"),
            "file_id": rec.get("file_id"),
            "caption": rec.get("caption"),
            "vlm_description": rec.get("vlm_description"),
            "tex": str(tex.relative_to(a.out)),
            "png": str(png.relative_to(a.out)) if raw else None,
        })

    (a.out / "manifest.json").write_text(
        json.dumps({"split": a.split, "rows": manifest}, indent=1), encoding="utf-8")
    print(f"rows written {len(manifest)}, no png {no_png}, empty code {no_code}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
