# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""pdf2mmd2-drillcheck — does pdfdrill accept what pdf2mmd2 writes?

For each document: build a folder laid out like one in ~/pdfdrill-library
(folder name = document name, <name>.pdf inside), write our <name>.lines.json
beside the PDF, run `pdfdrill model` and `pdfdrill md` on it, and report how
many objects pdfdrill built. The folders stay in --work for inspection, for
example with the drillui bridge.

A document is a PDF path or a folder name under --root.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import runner, warmup

_BUILT = re.compile(r"Built unified model: (\d+) objects? \(([^)]*)\)")
_MD = re.compile(r"Markdown file: (\S.*?\.md)\b")


def objects_built(said: str) -> tuple[int, str] | None:
    m = _BUILT.search(said)
    return (int(m.group(1)), m.group(2)) if m else None


def _pdfdrill(home: Path, command: str, pdf: Path) -> tuple[int, str]:
    env = dict(os.environ, PYTHONPATH=str(home / "src"),
               PDFDRILL_NO_PREFLIGHT="1", PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run([sys.executable, "-m", "pdfdrill", command,
                           pdf.name], cwd=pdf.parent, env=env,
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def check(pdf: Path, work: Path, home: Path | None = None,
          reader: str = "tsv") -> dict:
    home = home or Path(os.environ.get("PDFDRILL_HOME",
                                       Path.home() / "MX" / "PDFDRILL"))
    name = Path(pdf).stem
    folder = Path(work).resolve() / name
    folder.mkdir(parents=True, exist_ok=True)
    copy = folder / f"{name}.pdf"
    shutil.copyfile(pdf, copy)
    # pdfdrill's own artefacts from an earlier check would be reused. In a
    # folder named after its document pdfdrill writes them beside the PDF.
    for stale in ("model.docmodel.json", f"{name}.drill.json", f"{name}.md"):
        (folder / stale).unlink(missing_ok=True)

    res: dict = {"doc": name, "folder": str(folder), "ok": False}
    run = runner.run(copy, folder, reader=reader, pretty=True)
    lines_json = run["lines_json"]
    ours = lines_json.read_bytes()
    res.update(pages=run["pages"], lines=run["lines"])

    code, said = _pdfdrill(home, "model", copy)
    built = objects_built(said)
    res["lines_json_kept"] = lines_json.read_bytes() == ours
    if code != 0 or built is None or "Traceback" in said:
        res["error"] = "pdfdrill model: " + (said.strip().splitlines() or
                                             [f"exit {code}"])[-1]
        return res
    res["objects"], res["kinds"] = built
    if not res["lines_json_kept"]:
        res["error"] = "pdfdrill replaced our lines.json with its own reading"
        return res

    code, said = _pdfdrill(home, "md", copy)
    m = _MD.search(said)
    # pdfdrill names the file relative to the folder's parent
    md = next((c for c in ((folder.parent / m.group(1), folder / m.group(1))
                           if m else ()) if c.is_file()), None)
    if code != 0 or md is None:
        res["error"] = "pdfdrill md: " + (said.strip().splitlines() or
                                          [f"exit {code}"])[-1]
        return res
    res["markdown"] = str(md)
    res["markdown_words"] = len(md.read_text("utf-8").split())
    res["ok"] = True
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="pdf2mmd2-drillcheck", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docs", nargs="+",
                    help="PDF path, or folder name under --root")
    ap.add_argument("--root", default=str(Path.home() / "pdfdrill-library"),
                    help="library holding <name>/<name>.pdf")
    ap.add_argument("--work", default="out/drillcheck",
                    help="where the library-style folders are built")
    ap.add_argument("--pdfdrill", default=os.environ.get(
        "PDFDRILL_HOME", str(Path.home() / "MX" / "PDFDRILL")),
        help="pdfdrill checkout")
    ap.add_argument("--warmup", choices=sorted(runner.READERS),
                    default="tsv")
    args = ap.parse_args(argv)

    root, work, home = Path(args.root), Path(args.work), Path(args.pdfdrill)
    if root.resolve() in [work.resolve(), *work.resolve().parents]:
        print(f"pdf2mmd2-drillcheck: --work {work} is inside the library; "
              f"refusing to write there", file=sys.stderr)
        return 2
    if not (home / "src" / "pdfdrill").is_dir():
        print(f"pdf2mmd2-drillcheck: no pdfdrill checkout at {home}",
              file=sys.stderr)
        return 2
    pdfs = []
    for doc in args.docs:
        pdf = Path(doc) if Path(doc).is_file() else root / doc / f"{doc}.pdf"
        if not pdf.is_file():
            print(f"pdf2mmd2-drillcheck: no PDF for {doc!r} (looked for "
                  f"{pdf})", file=sys.stderr)
            return 2
        pdfs.append(pdf)

    failed = 0
    for pdf in pdfs:
        try:
            res = check(pdf, work, home, reader=args.warmup)
        except (warmup.WarmupError, runner.OverwriteError, OSError) as e:
            res = {"doc": pdf.stem, "ok": False, "error": str(e),
                   "folder": str(work / pdf.stem)}
        if res["ok"]:
            print(f"OK    {res['doc']}: {res['pages']} pages, "
                  f"{res['lines']} lines -> pdfdrill built "
                  f"{res['objects']} objects ({res['kinds']}); "
                  f"markdown {res['markdown_words']} words")
            print(f"      {res['markdown']}")
        else:
            failed += 1
            print(f"FAIL  {res['doc']}: {res['error']}")
        print(f"      folder: {res['folder']}")
    print(f"\n{len(pdfs) - failed} of {len(pdfs)} accepted by pdfdrill")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
