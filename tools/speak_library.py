#!/usr/bin/env python3
"""
speak_library — run `expandmath` + `speak` over every drilled document.

Fills `spoken` on every Formula/Equation in the library, so a consumer can read
the LLM-input text (`pdfdrill spoken`) without having to drive pdfdrill itself.

RESUMABLE by construction: `speak` skips objects that already carry `spoken`, so
re-running after an interrupt costs only the model load. Nothing is recomputed.

    python3 tools/speak_library.py [--lib DIR] [--limit N] [--dry-run]

Progress goes to stdout one line per document; a failure is recorded and the run
continues — one unreadable model must not stop the other 353.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PDFDRILL_NO_PREFLIGHT": "1"}


def math_state(model: Path) -> tuple[int, int]:
    """(math objects, of which already spoken) — read from JSON, no model load."""
    try:
        d = json.loads(model.read_text(encoding="utf-8", errors="replace"))
    except Exception:                                    # noqa: BLE001
        return (0, 0)
    objs = d.get("objects") or {}
    it = objs.values() if isinstance(objs, dict) else objs
    f = [o for o in it if o.get("type") in ("Formula", "Equation")]
    spoken = sum(1 for o in f if (o.get("props") or {}).get("spoken"))
    return (len(f), spoken)


def find_doc(model: Path) -> Path | None:
    """The PDF/markdown a model belongs to, for either library layout:
    `<lib>/<stem>/model.docmodel.json` or `<x>.pdf.drill/model.docmodel.json`."""
    d = model.parent
    if d.name.endswith(".drill"):                        # <x>.pdf.drill/
        cand = d.parent / d.name[:-len(".drill")]
        if cand.exists():
            return cand
    for ext in (".pdf", ".md"):                          # <lib>/<stem>/<stem>.pdf
        cand = d / (d.name + ext)
        if cand.exists():
            return cand
    hits = sorted(d.glob("*.pdf")) or sorted(d.glob("*.md"))
    return hits[0] if hits else None


def run(cmd: list[str], timeout: int) -> tuple[bool, str]:
    try:
        r = subprocess.run([sys.executable, "-m", "pdfdrill", *cmd], env=ENV,
                           capture_output=True, text=True, timeout=timeout,
                           cwd=str(ROOT))
        return (r.returncode == 0, (r.stdout or r.stderr or "").strip())
    except subprocess.TimeoutExpired:
        return (False, f"timeout after {timeout}s")
    except Exception as e:                               # noqa: BLE001
        return (False, str(e))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default=str(Path.home() / "pdfdrill-library"))
    ap.add_argument("--limit", type=int, default=0, help="only N documents")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--respeak", action="store_true",
                    help="re-render EVERY formula (after a speech-cleaning "
                         "change), not only the ones still missing")
    a = ap.parse_args()

    models = sorted(Path(a.lib).rglob("model.docmodel.json"))
    work = []
    for m in models:
        total, spoken = math_state(m)
        if total and (a.respeak or spoken < total):
            work.append((m, total, spoken))
    work.sort(key=lambda t: t[1] - t[2])                 # cheapest first: early wins
    if a.limit:
        work = work[:a.limit]

    print(f"{len(models)} model(s); {len(work)} need speech "
          f"({sum(t - s for _, t, s in work)} formulas)", flush=True)
    if a.dry_run:
        return 0

    t0 = time.monotonic()
    ok = failed = skipped = 0
    done_formulas = 0
    for i, (m, total, spoken) in enumerate(work, 1):
        doc = find_doc(m)
        name = m.parent.name[:52]
        if doc is None:
            skipped += 1
            print(f"[{i}/{len(work)}] SKIP  {name} — no source file", flush=True)
            continue
        # expandmath first: the engine has no macro table, so an unexpanded
        # macro would be spoken as its letters. Failure here is not fatal.
        run(["expandmath", str(doc)], timeout=900)
        good, msg = run(["speak", str(doc)] + (["--force"] if a.respeak else []),
                        timeout=3600)
        after_total, after_spoken = math_state(m)
        gained = after_spoken - spoken
        done_formulas += max(gained, 0)
        if good and after_spoken >= after_total:
            ok += 1
            tag = "OK   "
        elif gained > 0 or (a.respeak and after_spoken):
            ok += 1
            tag = "PART "
        else:
            failed += 1
            tag = "FAIL "
        rate = done_formulas / max(time.monotonic() - t0, 1e-6)
        print(f"[{i}/{len(work)}] {tag} {name}: {after_spoken}/{after_total} "
              f"(+{gained})  {rate:.0f} f/s"
              + ("" if good else f"  — {msg.splitlines()[0][:90]}"), flush=True)

    dt = time.monotonic() - t0
    print(f"\ndone in {dt/60:.1f} min — {ok} ok, {failed} failed, {skipped} skipped, "
          f"{done_formulas} formulas spoken", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
