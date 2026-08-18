"""P8 modeldiff + P9 edit_source — every re-run edit must be signed.

modeldiff lists, per changed object, the changed fields with old/new values
plus the evidence path and source tag; a changed object with no evidence path
lands in UNEVIDENCED and is counted separately.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.commands import cmd_modeldiff, _edit_source
from pdfdrill.sidecar import Sidecar


def _write(tmp, name, objects):
    p = Path(tmp) / name
    p.write_text(json.dumps({"meta": {}, "streams": [], "objects": objects}))
    return p


def test_modeldiff_buckets_evidenced_vs_unevidenced():
    with tempfile.TemporaryDirectory() as d:
        old = _write(d, "old.json", [
            {"id": "eq1", "type": "Equation", "props": {"latex": "a=b"}},
            {"id": "eq2", "type": "Equation", "props": {"latex": "c=d"}},
            {"id": "eq3", "type": "Equation", "props": {"latex": "e=f"}},
            {"id": "gone", "type": "Formula", "props": {}},
        ])
        new = _write(d, "new.json", [
            # evidenced by the tailsplit twin
            {"id": "eq1", "type": "Equation",
             "props": {"latex": "a=b'", "latex_pretail": "a=b"}},
            # evidenced by a P9-stamped realization carrying the new value
            {"id": "eq2", "type": "Equation", "props": {"latex": "c=d'"},
             "realizations": [{"stream": "snip", "role": "latex_candidate",
                               "provenance": "snip",
                               "props": {"latex": "c=d'",
                                         "edit_source": {"run": 3,
                                                         "at": "2026-08-18",
                                                         "cdn_url": "u"}}}]},
            # nobody signed this edit
            {"id": "eq3", "type": "Equation", "props": {"latex": "e=g"}},
            {"id": "fresh", "type": "MathTail", "props": {}},
        ])
        out = cmd_modeldiff(old, new)
    assert "3 changed" in out and "1 added" in out and "1 removed" in out
    assert "1 UNEVIDENCED" in out
    assert "props.latex_pretail" in out                    # twin path
    assert "edit_source(run 3" in out                      # P9 stamp path
    assert "eq3" in out.split("edits nobody signed")[1]    # the unsigned edit
    assert "fresh (MathTail)" in out and "gone (Formula)" in out


def test_edit_source_stamps_run_index_and_timestamp():
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        sc = Sidecar(pdf)
        s1 = _edit_source(sc, "https://cdn.mathpix.com/x.jpg")
        s2 = _edit_source(sc)
    assert s1["run"] == 1 and s2["run"] == 2               # per-doc counter
    assert s1["cdn_url"].startswith("https://cdn.")
    assert "cdn_url" not in s2                             # no URL, no field
    assert s1["at"][:2] == "20" and "T" in s1["at"]        # ISO timestamp
