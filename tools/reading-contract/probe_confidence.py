#!/usr/bin/env python3
"""Is `confidence`'s absence explained by `conversion_output`?

The contract's first draft said MathPix omits `confidence` on container
lines, because `conversion_output` is false there, and offered that as the
reason the field sits near 90% rather than 100%. A 25-file check refuted the
mechanism, so this measures the whole MathPix population instead.

Read only.
"""
import json, sys, time
from collections import Counter
from pathlib import Path

LIB = Path.home() / "pdfdrill-library"
MEAS = Path(sys.argv[1] if len(sys.argv) > 1 else "work/run-files/t0107-v2")
MAX_BYTES = 1_200_000_000
m = json.loads((MEAS / "measured.json").read_text(encoding="utf-8"))

out = {}
for cls in ("mathpix-classic", "mathpix-newer"):
    cross = Counter()          # (confidence present, conversion_output) -> lines
    miss_type = Counter()      # type -> lines missing confidence
    have_type = Counter()      # type -> lines total
    n_files = 0
    # every file of the class, not a sample: the class list is truncated in
    # measured.json for the large producers, so reclassify by the same rule.
    sys.path.insert(0, str(Path("tools/reading-contract").resolve()))
    from measure import producer_of
    t0 = time.time()
    for p in sorted(LIB.glob("*/*.lines.json")):
        try:
            if p.stat().st_size > MAX_BYTES:
                continue
            doc = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:                                    # noqa: BLE001
            continue
        pages = doc.get("pages") if isinstance(doc, dict) else doc
        if not isinstance(pages, list):
            continue
        if producer_of(doc, pages)[0] != cls:
            continue
        n_files += 1
        for pg in pages:
            if not isinstance(pg, dict):
                continue
            for ln in (pg.get("lines") or []):
                if not isinstance(ln, dict):
                    continue
                has = "confidence" in ln
                cross[(has, ln.get("conversion_output"))] += 1
                t = ln.get("type")
                have_type[t] += 1
                if not has:
                    miss_type[t] += 1
    tot = sum(cross.values())
    miss = sum(v for (h, _), v in cross.items() if not h)
    co_false = sum(v for (_, c), v in cross.items() if c is False)
    co_false_with_conf = cross[(True, False)]
    co_true_without_conf = cross[(True is False, True)] + cross[(False, True)]
    out[cls] = {
        "files": n_files, "lines": tot,
        "missing_confidence": miss,
        "missing_pct": round(100.0 * miss / max(1, tot), 2),
        "cross": {str(k): v for k, v in cross.most_common()},
        "conversion_output_false_lines": co_false,
        "conversion_output_false_BUT_confidence_present": co_false_with_conf,
        "conversion_output_true_BUT_confidence_absent": cross[(False, True)],
        "missing_by_type": miss_type.most_common(20),
        "missing_rate_by_type": sorted(
            [[t, miss_type[t], have_type[t],
              round(100.0 * miss_type[t] / max(1, have_type[t]), 1)]
             for t in have_type if miss_type[t]],
            key=lambda r: -r[1])[:20],
        "seconds": round(time.time() - t0),
    }
    print(cls, "files", n_files, "lines", tot, "missing", miss,
          "(%.2f%%)" % out[cls]["missing_pct"], flush=True)

(MEAS / "confidence.json").write_text(json.dumps(out, indent=1, ensure_ascii=False),
                                      encoding="utf-8")
print("wrote", MEAS / "confidence.json")
