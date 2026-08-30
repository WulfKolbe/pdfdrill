#!/usr/bin/env python3
"""Build an inkdrill-comparable fixture from the local DaTikZ-V4 Arrow cache.

Reads the shards directly — no network, no re-download. Emits, per row:
  <out>/tikz/<id>.tex        the author's tikz_code, wrapped ONLY if bare
  <out>/png/<id>.png         the dataset's own render (448x448)
  <out>/manifest.json        id, source, caption, vlm_description, paths

The two images per row are what a report compares: our compile of the
code against the dataset's render of the same code. Neither is a scan,
so this measures the renderer, not a reading.
"""
from __future__ import annotations
import argparse, io, json, re, sys
from pathlib import Path

STANDALONE = (
    "\\documentclass[border=2pt,tikz]{standalone}\n"
    "\\usepackage{amsmath,amssymb,amsfonts}\n"
    "\\usepackage{pgfplots}\\pgfplotsset{compat=newest}\n"
    "\\usetikzlibrary{arrows.meta,positioning,calc,shapes,patterns,decorations.pathmorphing,matrix,cd}\n"
    "\\begin{document}\n%s\n\\end{document}\n"
)

def declared_splits(root: Path) -> dict | None:
    """The splits `dataset_info.json` DECLARES, which is authoritative.

    Inferring a split from a filename is a guess that happens to be right
    here; the builder writes the answer next to the shards. 359 measured one
    `train` split by reading the dataset card, and this confirms it from the
    cache: train, 427,753 examples, 25 shards.
    """
    for info in sorted(root.rglob("dataset_info.json")):
        try:
            d = json.loads(info.read_text(encoding="utf-8"))
        except Exception:
            continue
        sp = d.get("splits") or {}
        if sp:
            return {k: {"num_examples": v.get("num_examples"),
                        "shards": len(v.get("shard_lengths") or [])}
                    for k, v in sp.items()}
    return None


def find_shards(root: Path) -> dict[str, list[Path]]:
    """Group Arrow shards by split, taken from the FILENAME.

    HF writes `<name>-<split>-NNNNN-of-NNNNN.arrow`, so the split is a field
    in the name rather than something to search the whole path for. Matching
    "test" anywhere in the path — as an rglob over *.parquet with a substring
    test does — would label every shard `test` under a directory that happens
    to contain that word.
    """
    splits: dict[str, list[Path]] = {}
    pat = re.compile(r"-(?P<split>[a-z]+)-\d+-of-\d+\.arrow$")
    for p in sorted(root.rglob("*.arrow")):
        m = pat.search(p.name)
        splits.setdefault(m.group("split") if m else "unsplit", []).append(p)
    return splits

def rows(files: list[Path], limit: int):
    """Stream records out of the Arrow shards.

    `memory_map` so a 500 MB shard is not read into RAM, and so a small limit
    touches only the first shard. HF writes either the streaming or the file
    format depending on version, so `open_stream` is tried and `open_file`
    used on failure rather than assuming which one is on disk.
    """
    import pyarrow as pa
    seen = 0
    for f in files:
        with pa.memory_map(str(f), "rb") as src:
            try:
                reader = pa.ipc.open_stream(src)
            except pa.ArrowInvalid:
                src.seek(0)
                reader = pa.ipc.open_file(src)
            batches = (reader if hasattr(reader, "__iter__")
                       else (reader.get_batch(i)
                             for i in range(reader.num_record_batches)))
            for batch in batches:
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

    declared = declared_splits(a.root)
    if declared:
        print("dataset_info.json declares: " + ", ".join(
            f"{k} ({v['num_examples']} examples, {v['shards']} shards)"
            for k, v in sorted(declared.items())))
    else:
        print("no dataset_info.json found — splits inferred from filenames only")
    splits = find_shards(a.root)
    if not splits:
        print(f"no .arrow shards under {a.root}", file=sys.stderr)
        return 1
    print("splits found on disk: " + ", ".join(
        f"{k} ({len(v)} shards)" for k, v in sorted(splits.items())))
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
        # 366 — WRAP ONLY IF BARE. DaTikZ-V4 stores a COMPLETE document in
        # `tikz_code`: every one of the first 100 rows begins
        # \documentclass[tikz]{standalone}. Wrapping that put a
        # \documentclass inside \begin{document} and 0 of 100 compiled --
        # a measurement of the wrapper, not of the code or the preamble.
        tex.write_text(code if "\\documentclass" in code
                       else STANDALONE % code, encoding="utf-8")

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
