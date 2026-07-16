"""
drillui `scan` — acquire paper from the ADF and drop it straight into the chat
context.

pdfdrill does NOT learn to scan: SCANDRILL already drives `scanimage` (ADF duplex
@300dpi, deskew measured+applied, raw/ retained). `scan` is the two-command chain
`adf` -> `assemble`, whose PDF is then handed to the existing `do_add`.

Two rules are LOCKED here because breaking either is silent, not loud:

* **No `--ocr`.** An OCR text layer makes pdfdrill's `route` read the scan as
  born-digital and send it to pdfminer instead of the vision lane (SCANDRILL
  brief section 3, "add --ocr only for humans"). The underlay is a HUMAN
  deliverable and is added separately -- never on the path feeding pdfdrill.
* **The job name is a TIMESTAMP, and that is correct.** A job names an
  ACQUISITION EVENT (one stack through the feeder), which really is identified by
  when it happened. It is NOT the document prefix: one ADF stack is typically
  several documents, so the per-document `sender-date-type` bibkey can only be
  derived after segmentation, downstream.
"""
import datetime as dt
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

_spec = importlib.util.spec_from_file_location(
    "drillui_chat", REPO / "tools" / "drillui_chat.py")
dc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dc)


def test_job_name_is_a_timestamped_acquisition_event():
    """Correct use of a timestamp: it names WHEN paper went through the feeder."""
    name = dc.scan_job_name(dt.datetime(2026, 7, 16, 14, 30))
    assert name == "scan-20260716-1430"


def test_chain_is_adf_then_assemble_and_never_passes_ocr(tmp_path):
    """The brief's section 3 guard, structural: --ocr cannot appear on this path."""
    cmds = dc.scan_commands("/home/u/SCANDRILL", "scan-20260716-1430", tmp_path)
    assert len(cmds) == 2, cmds
    adf, assemble = cmds

    assert adf[:4] == [sys.executable, "-m", "scandrill.cli", "adf"]
    assert "--job" in adf and "scan-20260716-1430" in adf
    # A LIVE acquisition: --from-dir would ingest an existing batch instead.
    assert "--from-dir" not in adf

    assert assemble[:4] == [sys.executable, "-m", "scandrill.cli", "assemble"]
    assert str(tmp_path / "scan-20260716-1430.pdf") in assemble

    for c in cmds:
        assert "--ocr" not in c, f"--ocr must never reach pdfdrill's route: {c}"


def test_assemble_job_dir_is_the_RAW_dir_not_the_job_dir(tmp_path):
    """Found by a live scan, not by unit tests: `adf` writes sides to
    <job>.job/raw/ and records manifest paths REL_TO that raw dir, so `assemble`
    must resolve against raw/ — the brief's known-good line passes `--job-dir
    <raw_dir>` for exactly this reason. Passing <job>.job/ makes assemble look for
    proc/raw_1_deskewed.png instead of raw/proc/raw_1_deskewed.png and die with
    'kept page images missing'."""
    adf, assemble = dc.scan_commands("/home/u/SCANDRILL", "j", tmp_path)
    raw = str(tmp_path / "j.job" / "raw")

    assert assemble[assemble.index("--job-dir") + 1] == raw
    # adf still owns the job dir itself (raw/ is created underneath it).
    assert adf[adf.index("--job-dir") + 1] == str(tmp_path / "j.job")


def test_chain_keeps_deskew_and_never_deletes(tmp_path):
    """SCANDRILL's rules 2+3: deskew is ON by default, nothing is destroyed."""
    adf, _ = dc.scan_commands("/home/u/SCANDRILL", "j", tmp_path)
    assert "--no-skew" not in adf and "--no-deskew" not in adf


def test_simplex_is_passed_through(tmp_path):
    adf, _ = dc.scan_commands("/home/u/SCANDRILL", "j", tmp_path, simplex=True)
    assert "--simplex" in adf


def test_scandrill_env_puts_the_package_on_pythonpath():
    """scandrill is NOT on PATH; it is importable from its checkout."""
    env = dc.scandrill_env({"PATH": "/usr/bin"}, "/home/u/SCANDRILL")
    assert env["PYTHONPATH"].startswith("/home/u/SCANDRILL")
    assert env["PATH"] == "/usr/bin"          # inherited, not clobbered


def test_scandrill_home_prefers_env_then_default(tmp_path, monkeypatch):
    home = tmp_path / "SC"
    (home / "scandrill").mkdir(parents=True)
    (home / "scandrill" / "cli.py").write_text("")
    monkeypatch.setenv("SCANDRILL_HOME", str(home))
    assert dc.scandrill_home() == str(home)

    monkeypatch.delenv("SCANDRILL_HOME")
    monkeypatch.setattr(dc, "_DEFAULT_SCANDRILL", home)
    assert dc.scandrill_home() == str(home)


def test_scandrill_home_is_none_when_absent(tmp_path, monkeypatch):
    """Absent -> a clear message, never a traceback."""
    monkeypatch.delenv("SCANDRILL_HOME", raising=False)
    monkeypatch.setattr(dc, "_DEFAULT_SCANDRILL", tmp_path / "nope")
    assert dc.scandrill_home() is None


def test_do_scan_hands_the_assembled_pdf_to_add(tmp_path, monkeypatch):
    """End of the chain: the PDF enters the chat context via the existing add."""
    ran: list = []
    pdf = tmp_path / "scan-20260716-1430.pdf"

    def fake_run(argv, env, timeout=180.0):
        ran.append(argv)
        pdf.write_bytes(b"%PDF-1.4")          # assemble produces the projection
        return "ok"

    added: list = []

    def fake_add(base, env, newdoc, docs, combined, timeout, store_dir=""):
        added.append(newdoc)
        return newdoc, None

    monkeypatch.setattr(dc, "_run", fake_run)
    monkeypatch.setattr(dc, "do_add", fake_add)
    monkeypatch.setattr(dc, "scandrill_home", lambda: "/home/u/SCANDRILL")
    monkeypatch.setattr(dc, "scan_job_name",
                        lambda now=None: "scan-20260716-1430")

    target, combined = dc.do_scan([], {}, "", [], None, 60.0, str(tmp_path))
    assert len(ran) == 2, "adf then assemble"
    assert added == [str(pdf)]
    assert target == str(pdf)


def test_do_scan_without_scandrill_is_graceful(tmp_path, monkeypatch):
    monkeypatch.setattr(dc, "scandrill_home", lambda: None)
    docs: list = []
    target, combined = dc.do_scan([], {}, "", docs, None, 60.0, str(tmp_path))
    assert target is None and docs == []       # context unchanged, no raise
