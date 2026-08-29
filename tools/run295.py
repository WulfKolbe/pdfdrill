#!/usr/bin/env python3
"""295 — the unattended corpus pass: region LaTeX compiled standalone.

One document at a time, `reporttex --render-regions --compile`, then the
outcome is READ from disk rather than scraped from the console note (which
prints only the first two failures). One JSON per document under out/295/, one
commit per document, so an interruption loses one document rather than the run.

Order: the 22 documents the github.io reports folder publishes come FIRST, so
the site can be updated while the rest of the corpus is still running.

The ink measurement (`regionink`) is NOT part of this pass. Its page detection
costs 127s per document before any measurement happens, and 296 — which reads
this output — asks about region COMPILE failures, not ink distances. Every row
here records whether the document became ink-eligible, so the measurement can
run later against the subset it actually applies to.
"""
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIB = pathlib.Path(os.environ.get("PDFDRILL_LIBRARY", pathlib.Path.home() / "pdfdrill-library"))
SITE = pathlib.Path.home() / "pdfdrill.github.io" / "reports"
OUT = ROOT / "out" / "295"
PER_DOC_TIMEOUT = 900
PUSH_EVERY = int(os.environ.get("RUN295_PUSH_EVERY", "10"))


#: The site publishes 10 books under a short bibkey while the library holds
#: them under their full Z-Library title, so a name match finds 12 of 22. The
#: map is written out rather than guessed by fuzzy matching: two Fong/Spivak
#: titles and two Lyche titles differ only in wording, and a near-match would
#: silently publish the wrong book.
SITE_ALIAS = {
 "cardona-qft-methods": "Geometric, Algebraic and Topological Methods for Quantum Field Theory (Alexander Cardona (ed.) etc.) (Z-Library)",
 "fong-spivak-invitation": "An Invitation to Applied Category Theory Seven Sketches In Compositionality (Brendan Fong, David I. Spivak) (Z-Library)",
 "fong-spivak-seven-sketches": "Seven Sketches in Composability An invitation to applied category theory (Brendan Fong, David I. Spivak) (Z-Library)",
 "gilmore-lie-groups": "Lie Groups, Physics and Geometry - An Intro for Physicists, Engineers and Chemists - R. Gilmore (",
 "johnston-linear-matrix-algebra": "Introduction to Linear and Matrix Algebra (Nathaniel Johnston) (Z-Library)",
 "kohlhase-omdoc": "OMDoc \u2013 An Open Markup Format for Mathematical Documents [version 1.2] Foreword by Allan Bundy (Michael Kohlhase (auth.)) (Z-Library)",
 "lyche-numerical-linear-algebra": "Numerical Linear Algebra and Matrix Factorizations (Tom Lyche) (Z-Library)",
 "mielke-geometrodynamics": "Geometrodynamics of Gauge Fields On the Geometry of Yang-Mills and Gravitational Gauge Theories (Eckehard W. Mielke) (Z-Library)",
 "voloshin-hypergraph": "Introduction to Graph and Hypergraph Theory (Vitaly I. Voloshin) (Z-Library)",
}


def population():
    """Documents with a docmodel; the site's own first, then the rest."""
    docs = {}
    for d in sorted(LIB.iterdir()):
        if not d.is_dir() or d.name == "reports":
            continue
        try:
            if not any(d.glob("*.docmodel.json")):
                continue
            pdfs = [p for p in d.glob("*.pdf") if p.name != "report.pdf"]
        except OSError:
            continue
        if pdfs:
            docs[d.name] = pdfs[0]
    site = []
    for n in sorted(p.name for p in SITE.iterdir() if p.is_dir()):
        target = SITE_ALIAS.get(n, n)
        if target in docs and target not in site:
            site.append(target)
    rest = [n for n in docs if n not in set(site)]
    return [(n, docs[n]) for n in site + sorted(rest)], len(site)


def last_table_cols(tex: pathlib.Path):
    try:
        s = tex.read_text(errors="replace")
    except OSError:
        return []
    return [ln.count("p{") for ln in s.splitlines() if "\\begin{longtable}" in ln]


def run(name, pdf):
    row = {"doc": name, "pdf": pdf.name}
    t0 = time.time()
    env = dict(os.environ, PDFDRILL_NO_PREFLIGHT="1", PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run(
            [sys.executable, "-m", "pdfdrill", "reporttex", str(pdf),
             "--render-regions", "--compile"],
            cwd=ROOT, env=dict(env, PYTHONPATH=str(ROOT / "src")),
            capture_output=True, text=True, timeout=PER_DOC_TIMEOUT)
        row["rc"] = p.returncode
        row["stdout_tail"] = (p.stdout or "").strip().split("\n")[-1][:300]
        if p.returncode != 0:
            row["error"] = (p.stderr or p.stdout or "").strip()[-300:]
    except subprocess.TimeoutExpired:
        row["rc"] = -1
        row["error"] = "timeout after %ds" % PER_DOC_TIMEOUT
    row["seconds"] = round(time.time() - t0, 1)

    d = pdf.parent
    oc = d / "standalone-regions" / "_outcomes.json"
    if oc.is_file():
        try:
            row["regions"] = json.loads(oc.read_text(errors="replace"))
        except Exception as exc:
            row["regions"] = {"unreadable": str(exc)[:80]}
    man = d / "report.regions.json"
    if man.is_file():
        try:
            rows = json.loads(man.read_text(errors="replace")).get("rows") or []
            row["manifest_rows"] = len(rows)
            # The manifest writes real booleans. An older one wrote the STRINGS
            # "True"/"False", and comparing against the string form counted 0
            # for every document while looking like a finding.
            def _t(v):
                return v is True or (isinstance(v, str) and v.lower() == "true")
            row["with_latex"] = sum(1 for r in rows if _t(r.get("has_latex")))
            row["duplicated"] = sum(1 for r in rows if _t(r.get("duplicated")))
        except Exception:
            pass
    specs = last_table_cols(d / "report.tex")
    row["table_cols"] = specs
    # ink-eligible: regionink selects the region table by column count, so it
    # needs a 6-column table that is the last one AND the only one (0707.4470
    # has two, because ink adoption widens the equation table to 6 as well).
    row["six_col_tables"] = specs.count(6)
    row["region_table_cols"] = specs[-1] if specs else None
    # Ink adoption widens the EQUATION table to 6 columns too, so on an adopted
    # report the region table is no longer identifiable by column count alone.
    # Recorded as data rather than collapsed into a False: the count is what
    # 281/296 need in order to pick a different discriminator.
    row["ink_selectable"] = bool(specs) and specs[-1] == 6 and specs.count(6) == 1
    return row


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    docs, nsite = population()
    print("population: %d documents (%d from the site, first)" % (len(docs), nsite),
          flush=True)
    done = skipped = 0
    since_push = 0
    for i, (name, pdf) in enumerate(docs, 1):
        dest = OUT / ("%s.json" % name.replace("/", "_"))
        if dest.is_file():
            skipped += 1
            continue
        row = run(name, pdf)
        # A lock refusal is not a measurement of the document, it is a
        # statement about another process. Writing it would make the failure
        # permanent, since the run resumes on the presence of this file.
        if "DocumentBusy" in (row.get("error") or ""):
            print("[%4d/%4d] %-34s LOCKED by another process - left for a re-run"
                  % (i, len(docs), name[:34]), flush=True)
            continue
        dest.write_text(json.dumps(row, indent=1, ensure_ascii=False),
                        encoding="utf-8")
        done += 1
        since_push += 1
        subprocess.run(["git", "add", str(dest)], cwd=ROOT,
                       capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m",
                        "295: %s (%d regions, %d failed, %.0fs)"
                        % (name, (row.get("regions") or {}).get("rendered", 0)
                           + (row.get("regions") or {}).get("failed", 0),
                           (row.get("regions") or {}).get("failed", 0),
                           row["seconds"])],
                       cwd=ROOT, capture_output=True)
        if since_push >= PUSH_EVERY:
            subprocess.run(["git", "push", "-q", "origin", "HEAD"],
                           cwd=ROOT, capture_output=True, timeout=300)
            since_push = 0
        print("[%4d/%4d] %-34s %5.1fs  regions=%s failed=%s selectable=%s"
              % (i, len(docs), name[:34], row["seconds"],
                 (row.get("regions") or {}).get("rendered", "-"),
                 (row.get("regions") or {}).get("failed", "-"),
                 row["ink_selectable"]), flush=True)
    subprocess.run(["git", "push", "-q", "origin", "HEAD"], cwd=ROOT,
                   capture_output=True, timeout=300)
    print("done: %d built, %d already present" % (done, skipped), flush=True)


if __name__ == "__main__":
    main()
