#!/usr/bin/env python3
r"""lstscore — read the listing gold set back and score it.

The peer of `canon.py`. `canon` exists because a reading can be RIGHT and
spelled differently; the same is true of a listing, and in three specific
ways that are the page's doing rather than the reader's:

  LINE NUMBERS   `numbers=left` prints them, so the page really does begin
                 each line with `1 `, `2 `. Reading them is correct; counting
                 them as a difference is not.
  escapechar     `escapechar=@` marks LaTeX inside the listing --
                 `@\label{fig:x}@` -- which never reaches the page at all.
                 It is in the gold and cannot be in any reading.
  WRAPPING       `breaklines=true` wraps a long line, and the page shows the
                 wrapped form. A reader of the PAGE must reproduce that.
  FENCE INFO     ```` ```python ```` names the language on the fence, which
                 is markdown, not a line of code. Counting it cost 15
                 listings their exact score the day the reader started
                 emitting it -- a measurement that moved because the
                 SCORER had not been told.
  COMMON INDENT  59 of the 291 gold bodies are indented as a whole inside
                 the author's source -- every line begins with the same 2,
                 4 or 5 spaces. The page cannot show that as an indent: it
                 becomes the block's LEFT EDGE, and a reader measuring
                 indent against that edge reads 0 for every line and is
                 right to. Indentation is RELATIVE structure, so both
                 sides are dedented before it is compared. 5 listings were
                 scoring 0 of 28, 0 of 22, 0 of 25 on this alone.

INDENTATION IS NOT IN THAT LIST. Leading whitespace is content -- in Python
it is the block structure -- so it is compared, and reported separately so a
loss cannot hide inside a high score. What IS dedented first is the indent
the whole block shares, which is the page's left margin, not structure.

    python3 lstscore.py            # the whole set
    python3 lstscore.py --limit 20
"""
import argparse
import difflib
import glob
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

GOLD = Path(os.environ.get("PDF2MMD_LSTGOLD",
                           Path.home() / "pdfdrill-library" / "lstgold"))
CODE = Path(os.environ.get("PDF2MMD_CODE", Path(__file__).resolve().parent.parent))
PY = CODE / ".pdfmm-venv" / "bin" / "python"

_LST = re.compile(r"\\begin\{lstlisting\}(?:\[([^\]]*)\])?\n(.*?)\\end\{lstlisting\}", re.S)
_ESCAPE = re.compile(r"escapechar\s*=\s*(.)")
_NUMBERS = re.compile(r"numbers\s*=\s*left")


def gold_body(tex: str) -> "tuple[str, str]":
    """(the listing body, its options) from a gold file."""
    m = _LST.search(tex)
    return (m.group(2), m.group(1) or "") if m else ("", "")


def strip_escapes(body: str, tex: str) -> str:
    r"""Remove `escapechar` regions: LaTeX that never reaches the page."""
    for ch in _ESCAPE.findall(tex):
        body = re.sub(re.escape(ch) + r".*?" + re.escape(ch), "", body, flags=re.S)
    return body


def strip_numbers(lines: list, tex: str) -> list:
    """Drop a leading line number where the listing asked for one.

    A BLANK code line is numbered too, and then the number is the whole of
    what the page shows on that row. `rows()` has already dropped the blank
    line from the gold, so the reading's numbered blank must go as well --
    otherwise a listing with two blank lines can never score 1.00 no matter
    how exactly it was read.
    """
    if not _NUMBERS.search(tex):
        return lines
    out = [re.sub(r"^\s*\d+(\s|$)", "", x) for x in lines]
    return [x for x in out if x.strip()]


def rows(text: str) -> list:
    return [x for x in text.split("\n") if x.strip()]


def dedent(lines: list) -> list:
    """Drop the indent every line shares -- it is a margin, not structure."""
    if not lines:
        return lines
    common = min(len(x) - len(x.lstrip()) for x in lines)
    return [x[common:] for x in lines] if common else lines


def read_back(tex_path: Path, keep: Path | None = None) -> "list | None":
    """Compile the gold file and read the PDF with pdf2mmd."""
    d = Path(tempfile.mkdtemp(prefix="lst-", dir="/tmp/claude-1000"))
    try:
        shutil.copy2(tex_path, d)
        name = tex_path.stem
        subprocess.run(["pdflatex", "-interaction=nonstopmode", "-no-shell-escape",
                        "-output-directory", str(d), str(d / tex_path.name)],
                       capture_output=True, text=True, errors="replace", timeout=180)
        pdf = d / (name + ".pdf")
        if not pdf.exists():
            return None
        subprocess.run([str(PY), str(CODE / "pdf2mmd.py"), str(pdf),
                        "--out", str(d / "md"), "--quiet"],
                       capture_output=True, text=True, errors="replace", timeout=900)
        md = [x for x in (d / "md").glob("*.md") if "fonts" not in x.name]
        if not md:
            return None
        t = md[0].read_text(encoding="utf-8", errors="replace")
        out = []
        for b in re.findall(r"```[^\n]*\n(.*?)```", t, re.S):
            out += rows(b)
        return out
    except Exception:                                      # noqa: BLE001
        return None
    finally:
        shutil.rmtree(d, ignore_errors=True)


def score(tex_path: Path) -> dict:
    tex = tex_path.read_text(encoding="utf-8", errors="replace")
    body, _opts = gold_body(tex)
    want = rows(strip_escapes(body, tex))
    got = read_back(tex_path)
    if got is None:
        return {"id": tex_path.stem, "state": "unreadable"}
    got = strip_numbers(got, tex)
    flat_w = [x.strip() for x in want]
    flat_g = [x.strip() for x in got]
    sm = difflib.SequenceMatcher(None, flat_w, flat_g)
    ratio = sm.ratio()
    # Indentation, compared only on the lines that MATCHED -- which is what
    # this comment has always said and what the code did not do. It zipped
    # the two lists positionally, so one `breaklines=true` wrap threw every
    # later line against the wrong gold line and the rest of the listing
    # scored at chance. lst-278 lost 59 indents that way and lst-203 47,
    # neither of them a reading error: the page shows the wrapped form and
    # the gold holds the source line, exactly as WRAPPING above says.
    ind_w = [len(x) - len(x.lstrip()) for x in dedent(want)]
    ind_g = [len(x) - len(x.lstrip()) for x in dedent(got)]
    pairs = [(i + k, j + k)
             for tag, i, i2, j, _j2 in sm.get_opcodes() if tag == "equal"
             for k in range(i2 - i)]
    n = len(pairs)
    kept = sum(1 for i, j in pairs if ind_w[i] == ind_g[j])
    return {"id": tex_path.stem, "state": "read", "gold": len(want),
            "read": len(got), "text": ratio,
            "indent": (kept / n) if n else 0.0,
            "indented": sum(1 for x in ind_w if x)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--json", default="")
    A = ap.parse_args()
    files = sorted(GOLD.glob("lst-*.tex"))
    if A.limit:
        files = files[:A.limit]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(score, files))
    read = [r for r in res if r["state"] == "read"]
    exact = [r for r in read if r["text"] >= 0.99]
    close = [r for r in read if 0.90 <= r["text"] < 0.99]
    print("listing gold: %d files, %d read back" % (len(res), len(read)))
    print("   text    exact %d   >=90%% %d   below %d"
          % (len(exact), len(close), len(read) - len(exact) - len(close)))
    ind = [r for r in read if r["indented"]]
    if ind:
        print("   indent  kept on %.0f%% of lines, over the %d listing(s) that have any"
              % (100 * sum(r["indent"] for r in ind) / len(ind), len(ind)))
    if A.json:
        import json as _json
        Path(A.json).write_text(_json.dumps(res, indent=1))
    for r in sorted(read, key=lambda r: r["text"])[:8]:
        print("      %-10s gold %3d read %3d  text %.2f  indent %.2f"
              % (r["id"], r["gold"], r["read"], r["text"], r["indent"]))


if __name__ == "__main__":
    main()
