"""LaTeX => PDF => pdf2mmd => LaTeX => PDF => pdf2mmd, and is it a fixed point?

A projection that cannot be re-read is not a projection. The gold listing is
compiled once (gen 1), read, projected, compiled again (gen 2) and read
again: if the two readings differ, the .tex we wrote does not set the page we
read, and the difference names which property was lost.
"""
import difflib, json, os, re, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# THE GOLD, THE INTERPRETER AND THE READER. These were three absolute paths
# into one account, which is three different ways for this script to measure
# nothing: a `lstgold` that is not there, a venv that is not there, and a
# `pdf2mmd.py` from a checkout that may not be the one under test — the exact
# defect T-0078 was opened for. The reader is THIS checkout's (`pdf2mmd.py`
# one level up), under THIS interpreter, unless you say otherwise.
LIB = Path(os.environ.get("PDF2MMD_LIBRARY", Path.home() / "pdfdrill-library"))
GOLD = Path(os.environ.get("PDF2MMD_LSTGOLD", LIB / "lstgold"))
CODE = Path(os.environ.get("PDF2MMD_CODE", Path(__file__).resolve().parents[1]))
PY = os.environ.get("PDF2MMD_PYTHON") or sys.executable
P2M = str(CODE / "pdf2mmd.py")
if not Path(P2M).is_file():
    raise SystemExit("no reader at %s — set $PDF2MMD_CODE to the folder "
                     "holding pdf2mmd.py" % P2M)
if not GOLD.is_dir():
    raise SystemExit("no gold listings at %s — set $PDF2MMD_LSTGOLD (or "
                     "$PDF2MMD_LIBRARY) to your copy" % GOLD)


def latex(src: Path, outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["pdflatex", "-interaction=nonstopmode", "-no-shell-escape",
                    "-output-directory", str(outdir), str(src)],
                   capture_output=True, text=True, errors="replace", timeout=240)
    p = outdir / (src.stem + ".pdf")
    return p if p.exists() and p.stat().st_size > 1000 else None


def read(pdf: Path, out: Path):
    subprocess.run([PY, P2M, str(pdf), "--out", str(out), "--quiet"],
                   capture_output=True, text=True, errors="replace", timeout=900)
    md = [x for x in out.glob("*.md") if "fonts" not in x.name]
    tex = [x for x in out.glob("*.tex")]
    fences = []
    if md:
        t = md[0].read_text(encoding="utf-8", errors="replace")
        for b in re.findall(r"```[^\n]*\n(.*?)```", t, re.S):
            fences += [x for x in b.split("\n") if x.strip()]
    return fences, (tex[0] if tex else None)


def one(tex: Path) -> dict:
    d = Path(tempfile.mkdtemp(prefix="rt-", dir="/tmp/claude-1000"))
    r = {"id": tex.stem}
    try:
        shutil.copy2(tex, d)
        g1 = latex(d / tex.name, d / "g1")
        r["render"] = g1 is not None
        if g1 is None:
            return r
        shutil.copy2(g1, GOLD / "pdf" / (tex.stem + ".pdf"))
        f1, t1 = read(g1, d / "r1")
        r["projected"] = t1 is not None
        r["lines1"] = len(f1)
        if t1 is None:
            return r
        src = t1.read_text(encoding="utf-8", errors="replace")
        r["lstlisting"] = "\\begin{lstlisting}" in src
        g2 = latex(t1, d / "g2")
        r["recompiles"] = g2 is not None
        if g2 is None:
            return r
        shutil.copy2(g2, GOLD / "again" / (tex.stem + ".pdf"))
        f2, _t2 = read(g2, d / "r2")
        r["lines2"] = len(f2)
        r["fixed"] = difflib.SequenceMatcher(None, f1, f2).ratio()
        return r
    except Exception as e:                                  # noqa: BLE001
        r["error"] = str(e)[:80]
        return r
    finally:
        shutil.rmtree(d, ignore_errors=True)


(GOLD / "pdf").mkdir(exist_ok=True)
(GOLD / "again").mkdir(exist_ok=True)
texs = sorted(GOLD.glob("lst-*.tex"))
res = []
with ThreadPoolExecutor(max_workers=6) as ex:
    for i, x in enumerate(ex.map(one, texs), 1):
        res.append(x)
        if i % 50 == 0:
            print("  %d/%d" % (i, len(texs)), file=sys.stderr, flush=True)
json.dump(res, open(GOLD / "roundtrip.json", "w"), indent=1)
n = len(res)
f = lambda k: sum(1 for x in res if x.get(k))
print("gold listings            %d" % n)
print("  rendered to a page     %d" % f("render"))
print("  pdf2mmd projected      %d" % f("projected"))
print("  .tex HAS a listing env %d" % f("lstlisting"))
print("  that .tex recompiles   %d" % f("recompiles"))
fx = [x["fixed"] for x in res if "fixed" in x]
if fx:
    print("  read back the same     %d of %d (mean %.2f)"
          % (sum(1 for x in fx if x >= 0.999), len(fx), sum(fx) / len(fx)))
