"""525 — audit: what each of the last twenty tasks left inspectable."""
import sys, json, pathlib, subprocess
sys.path.insert(0, "/home/wkolbe/MX/PDFDRILL/src")
from pdfdrill import taskout

REPO = pathlib.Path("/home/wkolbe/MX/PDFDRILL")
SP = pathlib.Path("/tmp/claude-1000/-home-wkolbe-MX-PDFDRILL/"
                  "ae99387a-8fcf-4b96-b9d9-5dc00cc6f8da/scratchpad")
TASKS = [500,502,503,505,506,507,509,510,511,513,514,515,516,517,518,519,
         520,521,522,523]

rows = []
for n in TASKS:
    tool = sorted(REPO.glob("tools/*%d*.py" % n))
    data = [p for p in REPO.glob("out/*%d*" % n) if p.suffix != ".txt"]
    scratch_py = sorted(SP.glob("*%d*.py" % n))
    scratch_any = sorted(SP.glob("*%d*" % n))
    lib = list(pathlib.Path.home().glob("pdfdrill-library/*/out/%d" % n))
    if tool:
        cls = "A committed script"
    elif scratch_py:
        cls = "B scratchpad script only"
    else:
        cls = "C no script anywhere"
    rows.append({
        "task": n, "class": cls,
        "committed_script": [str(p.relative_to(REPO)) for p in tool],
        "committed_data": [str(p.relative_to(REPO)) for p in data],
        "scratchpad_scripts": [p.name for p in scratch_py],
        "scratchpad_files": len(scratch_any),
        "library_out_dirs": [str(p) for p in lib],
    })

summary = {
    "tasks": len(rows),
    "A_committed_script": sum(1 for r in rows if r["class"].startswith("A")),
    "B_scratchpad_only": sum(1 for r in rows if r["class"].startswith("B")),
    "C_no_script": sum(1 for r in rows if r["class"].startswith("C")),
    "committed_a_data_file": sum(1 for r in rows if r["committed_data"]),
    "wrote_into_library_out": sum(1 for r in rows if r["library_out_dirs"]),
    "scratchpad_files_total": sum(r["scratchpad_files"] for r in rows),
}
taskout.save_script(None, 525, pathlib.Path(__file__).read_text())
taskout.save_json(None, 525, "audit", {"summary": summary, "rows": rows})
print(json.dumps(summary, indent=1))
print("\nwritten:")
print(taskout.report_lines(None, 525))
