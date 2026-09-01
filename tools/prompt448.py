#!/usr/bin/env python3
"""448 — a revised prompt, measured on 444's exact six rows.

THREE CHANGES, and the reason for each is a measurement rather than a taste.

1. NO MATHS ASSUMPTION. `PROPOSE_PROMPT_C` says "one printed equation" and
   asks for "the LaTeX body". 446 then measured that three of these six rows
   are not equations at all: they are complete floats, `\\begin{figure} \\[ … \\]
   \\caption{…} \\end{figure}`, equation AND caption captured as one object. A
   prompt that calls a figure an equation is asking the model to repair the
   wrong kind of thing.

2. STRUCTURAL CORRECTION IS PERMITTED. The old clause — "prefer the existing
   reading where the image does not contradict it" — is exactly why 444 failed
   on those rows: the model preserved `\\begin{figure}` in every one of six
   proposals, correctly, because a wrapper is invisible in a crop and the
   prompt told it to keep what the image does not contradict. The instruction
   now names the case: a wrapper the crop cannot show is damage, not content.

3. FIGURE SPECIFICITY IS KEPT. Strings, fonts, sizes, positions, directions,
   and the two libraries named, so a TikZ answer is usable rather than
   approximate.

Run against the SAME six rows as 444, so the comparison means something, and
logged beside the document (447) so this one is auditable.
"""
import argparse, json, pathlib, sys, tempfile, time
from pdfdrill import prompts

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pdfdrill import callog                                    # noqa: E402
from pdfdrill import refine as rf                              # noqa: E402
from pdfdrill import report_tex as rt                          # noqa: E402

SYSTEM = (
    "You transcribe a region of a printed page into LaTeX. The region may be "
    "an equation, a diagram, a table, or a mixture of them. You return LaTeX "
    "and nothing else: no prose, no code fence, no explanation."
)

PROMPT = prompts.load("revise-region")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default="Introduction to Linear and Matrix Algebra "
                                     "(Nathaniel Johnston) (Z-Library)")
    ap.add_argument("--out", default=str(ROOT / "out" / "448.json"))
    a = ap.parse_args()
    D = pathlib.Path.home() / "pdfdrill-library" / a.doc
    rows = json.loads((ROOT / "out" / "444.rows.json").read_text())
    w = pathlib.Path(tempfile.mkdtemp(prefix="prompt448-"))
    run_id = callog.open_run(D, "prompt448",
                             script=str(pathlib.Path(__file__).resolve()),
                             note="revised prompt vs 444's two arms, same rows")
    rf.set_call_log(D, run_id)
    print("  run %s" % run_id, flush=True)
    out = []
    for i, r in enumerate(rows, 1):
        crop = D / "report-crops" / ("%s.jpg" % r["title"])
        crop = crop if crop.is_file() else None
        rec = {"short": r["short"], "title": r["title"], "page": r["page"]}
        ref = {}
        if crop:
            import subprocess
            png = w / ("%s_scan.png" % r["short"])
            subprocess.run(["magick", str(crop), "-background", "white",
                            "-alpha", "remove", "PNG24:" + str(png)],
                           capture_output=True)
            if png.is_file():
                try:
                    ref = rf.ink_signature(png)
                except Exception:
                    ref = {}
        base_png, _ = rf.render_latex(r["latex"], w / ("%s_base.png" % i))
        base_sig = rf.ink_signature(base_png) if base_png else {}
        rec["ink_before"] = (rf.ink_distance(base_sig, ref)
                             if base_sig and ref else None)
        t0 = time.time()
        # .replace, not .format: this prompt is full of LaTeX and every brace
        # in it is a brace. `\usetikzlibrary{arrows.meta, positioning}` was
        # read as a format placeholder and raised KeyError('arrows') — a
        # prompt naming the libraries could not be sent BECAUSE it named them.
        prompt = (PROMPT.replace("{conf}", str(r.get("conf") or 0.0))
                        .replace("{latex}", r["latex"]))
        txt, finish, err = rf._novita_chat(
            prompt, system=SYSTEM, model=rf.NOVITA_MODEL,
            max_tokens=rf.PROPOSE_MAX_TOKENS, timeout=600, crop=crop,
            subject=r["short"], arm="revised",
            prompt_name="revise-region")
        prop = rf._clean_proposal(txt) if hasattr(rf, "_clean_proposal") else (txt or "").strip()
        rec["seconds"] = round(time.time() - t0, 1)
        rec["finish"], rec["error"] = finish, err
        rec["proposed"] = (prop or "")[:4000]
        if not (prop or "").strip():
            rec["outcome"] = "no proposal"
        elif not rt.renderable(prop):
            rec["outcome"] = "rejected: renderable() refuses it"
        else:
            png, cerr = rf.render_latex(prop, w / ("%s_rev.png" % i))
            if png is None:
                rec["outcome"] = "rejected: does not compile"
                rec["compile_error"] = cerr[:120]
            else:
                sig = rf.ink_signature(png)
                rec["ink_after"] = rf.ink_distance(sig, ref) if ref else None
                if not ref:
                    rec["outcome"] = "cannot gate: no scan reference"
                elif rec["ink_before"] is None:
                    rec["outcome"] = "accepted: original did not render, this does"
                elif rec["ink_after"] < rec["ink_before"]:
                    rec["outcome"] = "accepted: ink falls"
                else:
                    rec["outcome"] = "rejected: ink does not fall"
        out.append(rec)
        print("  %d %-16s %s" % (i, r["short"], rec["outcome"]), flush=True)
        pathlib.Path(a.out).write_text(json.dumps(out, indent=1))
    acc = sum(1 for r in out if str(r["outcome"]).startswith("accepted"))
    log = callog.close_run(D, run_id, calls=len(out),
                           outcome="%d accepted of %d" % (acc, len(out)))
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1))
    print("wrote %s" % a.out)
    print("evidence %s" % log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
