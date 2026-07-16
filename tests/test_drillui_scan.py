"""
drillui `scan` — the THIN half.

All acquisition detail lives in pdfdrill (`pdfdrill scan` → tests/test_scan.py,
which drives SCANDRILL as a library). drillui only: runs that command, reads its
--json result, and hands the PDF to the existing do_add. So there is no scanner
logic, no SCANDRILL path, and no argv-building here — that separation IS the
thing worth testing.

Like `add`, `scan` CREATES the document, so it must dispatch before the "no
document yet" guard and work from an empty context.
"""
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

_spec = importlib.util.spec_from_file_location(
    "drillui_chat", REPO / "tools" / "drillui_chat.py")
dc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dc)


def _ok(pdf, **over):
    d = {"job": "scan-20260716-1430", "pdf": str(pdf), "manifest": "m.json",
         "raw_dir": "r", "sides": 4, "kept": 3, "blanks": 1, "deskewed": 3,
         "device": "airscan:e0:TEST"}
    d.update(over)
    return json.dumps(d)


def test_scan_delegates_to_pdfdrill_and_adds_the_pdf(tmp_path, monkeypatch):
    pdf = tmp_path / "scan-20260716-1430.pdf"
    seen: list = []
    added: list = []

    def fake_run(argv, env, timeout=180.0):
        seen.append(argv)
        return _ok(pdf)

    monkeypatch.setattr(dc, "_run", fake_run)
    monkeypatch.setattr(dc, "do_add",
                        lambda base, env, doc, docs, comb, t, store_dir="":
                        (added.append(doc), (doc, None))[1])

    target, _ = dc.do_scan(["pdfdrill"], {}, "", [], None, 60.0, str(tmp_path))

    assert len(seen) == 1, "one pdfdrill call — drillui builds no scanner chain"
    argv = seen[0]
    assert argv[:2] == ["pdfdrill", "scan"] and "--json" in argv
    assert argv[argv.index("--out-dir") + 1] == str(tmp_path)
    assert added == [str(pdf)] and target == str(pdf)


def test_scan_passes_job_and_flags_through(tmp_path, monkeypatch):
    seen: list = []
    monkeypatch.setattr(dc, "_run",
                        lambda a, e, timeout=180.0: (seen.append(a),
                                                     _ok(tmp_path / "x.pdf"))[1])
    monkeypatch.setattr(dc, "do_add",
                        lambda *a, **k: (str(tmp_path / "x.pdf"), None))
    dc.do_scan(["pdfdrill"], {}, "mahnungen --simplex", [], None, 60.0,
               str(tmp_path))
    assert "mahnungen" in seen[0] and "--simplex" in seen[0]


def test_quoted_job_name_is_one_token(tmp_path, monkeypatch):
    """shlex, not .split() — a job name with blanks stays one argument."""
    seen: list = []
    monkeypatch.setattr(dc, "_run",
                        lambda a, e, timeout=180.0: (seen.append(a),
                                                     _ok(tmp_path / "x.pdf"))[1])
    monkeypatch.setattr(dc, "do_add",
                        lambda *a, **k: (str(tmp_path / "x.pdf"), None))
    dc.do_scan(["pdfdrill"], {}, '"AOK Mahnung"', [], None, 60.0, str(tmp_path))
    assert "AOK Mahnung" in seen[0]


def test_scan_failure_leaves_the_context_unchanged(tmp_path, monkeypatch):
    """cmd_scan returns PROSE (e.g. the SCANDRILL install hint) on failure."""
    monkeypatch.setattr(dc, "_run", lambda *a, **k: "scan needs SCANDRILL …")
    docs: list = []
    target, combined = dc.do_scan(["pdfdrill"], {}, "", docs, None, 60.0,
                                  str(tmp_path))
    assert docs == [] and target is None and combined is None


def test_scan_subprocess_error_is_not_fatal(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise OSError("scanner asleep")
    monkeypatch.setattr(dc, "_run", boom)
    docs: list = []
    target, _ = dc.do_scan(["pdfdrill"], {}, "", docs, None, 60.0, str(tmp_path))
    assert target is None and docs == []


def test_scan_is_offered_in_help_and_needs_no_document():
    """It CREATES the document, so it must be reachable from an empty context."""
    assert "scan" in dc._repl_help({})
    src = (REPO / "tools" / "drillui_chat.py").read_text()
    scan_at = src.index('lstrip(":").lower() == "scan"')
    guard_at = src.index("No document yet")
    assert scan_at < guard_at or "or `scan`" in src
