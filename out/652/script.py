"""652 evidence — `pdfdrill status --html` on penev_A and
SteerableWaveletFramesBasedontheRieszTransform.

Run from EACH document's own folder (the proof objects `_stale_or_absent`
checks record their input paths relative to the cwd the model was built
from — an orthogonal, pre-existing property of `proofs.py`, not something
this task changes), so the model reads as fresh and the conservation/ledger
numbers actually compute instead of reporting "stale".

    cd ~/pdfdrill-library/<doc> && PDFDRILL_NO_PREFLIGHT=1 \
        /home/wkolbe/MX/PDFDRILL/pdfdrill status --html <doc>.pdf

Then this script re-derives, independently in Python, the same three
conservation numbers + the gate report + the artefact-link check, and
writes them next to the page as data/INSPECT for a reader to compare
against the page's own prose (rule 19/20).
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/wkolbe/MX/PDFDRILL/src")

from pdfdrill import commands as C, taskout
from docops.conserve import conserve, classify_unreachable, gate, format_gate_report

DOCS = [
    ("penev_A", Path.home() / "pdfdrill-library/penev_A/penev_A.pdf"),
    ("SteerableWaveletFramesBasedontheRieszTransform",
     Path.home() / "pdfdrill-library/SteerableWaveletFramesBasedontheRieszTransform"
     / "SteerableWaveletFramesBasedontheRieszTransform.pdf"),
]

report = {}
for bibkey, pdf in DOCS:
    sc = C.Sidecar(pdf)
    model_path = C._model_path(sc)
    stale = C._stale_or_absent(sc, model_path, C._lines_json_path(pdf))
    doc = C.load_model(model_path)
    res = conserve(doc)
    cls = classify_unreachable(res["reachability"])
    from docops.conserve import load_baseline
    g = gate(doc, res=res, baseline=load_baseline())

    html_path = sc.blob_dir / f"{bibkey}.status.html"
    text = html_path.read_text(encoding="utf-8")
    hrefs = re.findall(r'href="([^"]+)"', text)
    dead = [h for h in hrefs if not (html_path.parent / h).is_file()]

    report[bibkey] = {
        "pdf": str(pdf),
        "model_stale_at_check_time": stale,
        "conserve_counts": res["counts"],
        "classify_unreachable": cls,
        "gate_passed": g["passed"],
        "gate_report": format_gate_report(g),
        "status_html": str(html_path),
        "n_hrefs": len(hrefs),
        "dead_hrefs": dead,
    }
    print(f"=== {bibkey} ===")
    print(f"  model_stale_at_check_time: {stale}")
    print(f"  conserve counts: {res['counts']}")
    print(f"  gate passed: {g['passed']}")
    print(f"  {len(hrefs)} hrefs on the page, {len(dead)} dead")

for bibkey, pdf in DOCS:
    docdir = pdf.parent
    taskout.save_script(docdir, 652, Path(__file__).read_text(encoding="utf-8")
                        if False else open(sys.argv[0]).read())
    taskout.save_json(docdir, 652, "report", report[bibkey])
    r = report[bibkey]
    entries = [
        (r["status_html"], "the state page itself — open it to see the "
         "verdict, layers, artefact links, conservation/ledger numbers",
         bibkey),
    ]
    ins = taskout.inspect_list(docdir, 652, entries)
    print(taskout.inspect_report(ins))
