#!/usr/bin/env python3
"""391 — the recovery prompt on MathPix rescue crops.

390 counted 20,833 rectangles MathPix cropped and handed back untranscribed.
This sends a sample of them through the same prompt 392 measured, compiles
each reply against the same fixed preamble, and scores it against the crop by
ink.

WHAT THIS CANNOT DO, and 392 is why it is run first: a rescue has no
reference. The distance here is the reply against MathPix's own crop, which
is a PICTURE of the region, not the author's code. 392 measured the same
prompt where the answer IS known, so a distance here can be read against that
distribution instead of against nothing.
"""
import argparse, io, json, pathlib, random, sys, tempfile, time, zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(pathlib.Path.home() / "inkdrill"))
from pdfdrill import refine as rf                              # noqa: E402
from recover_prompt import SYSTEM, PROMPT, wrap                # noqa: E402
from datikz_recover392 import compare, render                  # noqa: E402

LIB = pathlib.Path.home() / "pdfdrill-library"


def sample(n, seed, min_kb):
    """One crop from each of n DIFFERENT documents.

    Per document, not per crop: 52 archives hold more than 100 rescues each,
    and a uniform draw over 20,833 would take most of the sample from a
    handful of books. The question is how the prompt does on the population,
    not on whoever has the most figures.
    """
    rng = random.Random(seed)
    zips = sorted(LIB.glob("*/*.tex.zip"))
    rng.shuffle(zips)
    out = []
    for z in zips:
        if len(out) >= n:
            break
        try:
            with zipfile.ZipFile(z) as f:
                imgs = [i for i in f.infolist()
                        if "/images/" in i.filename
                        and i.filename.lower().endswith((".jpg", ".jpeg", ".png"))
                        and "image-not-found" not in i.filename
                        and i.file_size >= min_kb * 1024]
                if not imgs:
                    continue
                pick = rng.choice(imgs)
                out.append({"doc": z.parent.name, "zip": str(z),
                            "member": pick.filename, "bytes": pick.file_size,
                            "data": f.read(pick.filename)})
        except Exception:
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=20)
    ap.add_argument("--seed", type=int, default=391)
    ap.add_argument("--min-kb", type=int, default=15,
                    help="skip tiny crops: a 2 KB strip is a rule or a "
                         "page number, not a figure worth a model call")
    ap.add_argument("--max-tokens", type=int, default=16000)
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--out", default=str(ROOT / "out" / "391.json"))
    a = ap.parse_args()

    picks = sample(a.rows, a.seed, a.min_kb)
    work = pathlib.Path(tempfile.mkdtemp(prefix="rescue391-"))
    print("  sampled %d crops from %d documents" % (len(picks), len({p["doc"] for p in picks})))
    out = []
    for i, p in enumerate(picks, 1):
        stem = "R%02d" % i
        raw = work / (stem + pathlib.Path(p["member"]).suffix)
        raw.write_bytes(p["data"])
        # MathPix ships JPEG; inkdrill reads PNG only. `magick`, not the
        # deprecated `convert` (ImageMagick v7).
        crop = work / (stem + "_crop.png")
        import subprocess as _sp
        _sp.run(["magick", str(raw), "-background", "white", "-alpha", "remove",
                 "-alpha", "off", "PNG24:" + str(crop)], capture_output=True)
        if not crop.is_file():
            out.append({"n": i, "doc": p["doc"], "outcome": "crop unreadable",
                        "member": p["member"].rsplit("/", 1)[-1]})
            print("  %2d %-28s CROP UNREADABLE" % (i, p["doc"][:28]), flush=True)
            continue
        rec = {"n": i, "doc": p["doc"], "member": p["member"].rsplit("/", 1)[-1],
               "crop_bytes": p["bytes"]}
        t0 = time.time()
        txt, fin, err = rf._novita_chat(
            PROMPT, system=SYSTEM, model=rf.NOVITA_MODEL,
            max_tokens=a.max_tokens, timeout=a.timeout, crop=[crop])
        rec["seconds"] = round(time.time() - t0, 1)
        rec["finish"], rec["error"] = fin, err
        rec["reply_chars"] = len(txt or "")
        if not (txt or "").strip():
            rec["outcome"] = "empty reply"
            out.append(rec); print("  %2d %-28s EMPTY finish=%s" % (i, p["doc"][:28], fin), flush=True)
            continue
        (work / (stem + ".reply")).write_text(txt, encoding="utf-8")
        got, cerr, engine = render(wrap(txt), work, stem + "_model")
        rec["engine"] = engine
        if got is None:
            rec["outcome"] = "did not compile"
            rec["compile_error"] = cerr
            out.append(rec); print("  %2d %-28s NOCOMPILE %s" % (i, p["doc"][:28], cerr[:50]), flush=True)
            continue
        d, cd, fl, lm, lc = compare(got, crop)
        rec.update({"outcome": "compiled", "distance": d, "comp_delta": cd,
                    "flag": fl, "model_five": lm, "crop_five": lc,
                    "render": str(got)})
        out.append(rec)
        print("  %2d %-28s d=%-5d %-10s model %3d comps / crop %3d (%.0fs)"
              % (i, p["doc"][:28], d, fl, lm[0], lc[0], rec["seconds"]), flush=True)
    pathlib.Path(a.out).write_text(json.dumps(
        {"rows": out, "max_tokens": a.max_tokens, "model": rf.NOVITA_MODEL,
         "seed": a.seed, "min_kb": a.min_kb, "work": str(work)},
        indent=1), encoding="utf-8")
    print("wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
