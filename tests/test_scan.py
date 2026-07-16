"""
`pdfdrill scan` — acquisition as a pdfdrill command, driving SCANDRILL as a
LIBRARY (import, not subprocess).

pdfdrill owns the integration: it calls scandrill's functions in-process, so
there is no argv to mis-spell, no PYTHONPATH to export, and no shell. SCANDRILL
keeps what it is good at (the fixed rig: ADF duplex @300dpi, deskew measured and
applied, raw/ retained, blank sides recorded rather than deleted).

Two invariants are locked because breaking either fails SILENTLY:

* **OCR is never requested.** `assemble(ocr=False)` is the default; pdfdrill must
  never pass ocr=True on this path. An OCR text layer makes `route` read the scan
  as born-digital and send it down the pdfminer lane instead of the vision lane.
  The searchable underlay is a HUMAN deliverable, produced separately.
* **assemble resolves against the RAW dir.** `ingest_raw_dir(rel_to=raw_dir)`
  records page paths relative to raw/, so assemble must be given raw/ as its
  job_dir. (Found by a live ADF scan: passing the job dir made assemble hunt for
  proc/raw_1_deskewed.png instead of raw/proc/raw_1_deskewed.png.)
"""
import datetime as dt
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import scan as sc


class _Rec:
    """Records every scandrill call instead of touching a scanner."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.assemble_kw = None
        self.ingest_kw = None
        self.deskewed = 0
        self.scanned = None

    def modules(self):
        adf = types.SimpleNamespace(
            resolve_device=lambda *a, **k: "airscan:e0:TEST",
            scan_adf=self._scan_adf,
            ingest_raw_dir=self._ingest,
            measure_skew=lambda pages, **k: len(pages),
            apply_deskew=self._deskew,
            group_sheets=lambda pages: [],
            ScannerError=RuntimeError,
        )
        asm = types.SimpleNamespace(assemble=self._assemble)
        man = types.SimpleNamespace(Manifest=self._manifest)
        cfgm = types.SimpleNamespace(Config=self._cfg)
        return types.SimpleNamespace(adf=adf, assemble=asm, manifest=man,
                                     config=cfgm)

    # -- fakes -------------------------------------------------------------
    def _scan_adf(self, raw_dir, **k):
        self.scanned = Path(raw_dir)
        Path(raw_dir).mkdir(parents=True, exist_ok=True)
        return [Path(raw_dir) / "raw_1.png", Path(raw_dir) / "raw_2.png"]

    def _ingest(self, manifest, raw_dir, **kw):
        self.ingest_kw = kw
        return [object(), object()]

    def _deskew(self, pages, **k):
        self.deskewed = len(pages)
        return len(pages)

    def _assemble(self, manifest, out_pdf, **kw):
        self.assemble_kw = kw
        Path(out_pdf).write_bytes(b"%PDF-1.4")
        return Path(out_pdf)

    class _cfg:
        source, lang, blank_threshold, apply_deskew = "ADF Duplex", "de-DE", 0.999, True
        resolution, device, deskew_dir = 300, None, "proc"

        @classmethod
        def load(cls, *a, **k):
            return cls()

    class _manifest:
        def __init__(self, **kw):
            self.kw = kw

        def kept_pages(self):
            return [object()]

        def save(self, p):
            Path(p).write_text("{}")
            return Path(p)


def test_job_name_is_a_timestamped_acquisition_event():
    """A job names WHEN paper went through the feeder — not what it contains.
    The per-document sender-date-type prefix is derived downstream, after
    segmentation, because one stack is usually several documents."""
    assert sc.job_name(dt.datetime(2026, 7, 16, 14, 30)) == "scan-20260716-1430"


def test_scan_never_requests_ocr(tmp_path, monkeypatch):
    rec = _Rec(tmp_path)
    monkeypatch.setattr(sc, "_scandrill", rec.modules)
    sc.scan(job="j", out_dir=tmp_path)
    assert rec.assemble_kw.get("ocr") in (None, False), \
        "an OCR layer would make route() read the scan as born-digital"


def test_assemble_resolves_against_the_raw_dir(tmp_path, monkeypatch):
    rec = _Rec(tmp_path)
    monkeypatch.setattr(sc, "_scandrill", rec.modules)
    res = sc.scan(job="j", out_dir=tmp_path)
    raw = tmp_path / "j.job" / "raw"
    assert Path(rec.assemble_kw["job_dir"]) == raw
    assert rec.ingest_kw["rel_to"] == raw       # the reason job_dir must be raw/
    assert res.raw_dir == raw


def test_scan_deskews_by_default_and_keeps_raw(tmp_path, monkeypatch):
    rec = _Rec(tmp_path)
    monkeypatch.setattr(sc, "_scandrill", rec.modules)
    res = sc.scan(job="j", out_dir=tmp_path)
    assert rec.deskewed == 2 and res.deskewed == 2
    assert rec.scanned.exists(), "raw/ is retained, never cleaned"


def test_no_deskew_is_honoured(tmp_path, monkeypatch):
    rec = _Rec(tmp_path)
    monkeypatch.setattr(sc, "_scandrill", rec.modules)
    sc.scan(job="j", out_dir=tmp_path, deskew=False)
    assert rec.deskewed == 0


def test_simplex_turns_off_duplex(tmp_path, monkeypatch):
    rec = _Rec(tmp_path)
    monkeypatch.setattr(sc, "_scandrill", rec.modules)
    sc.scan(job="j", out_dir=tmp_path, simplex=True)
    assert rec.ingest_kw["duplex"] is False


def test_from_dir_reingests_without_touching_the_scanner(tmp_path, monkeypatch):
    """Re-run an existing batch: no device resolution, no scan."""
    rec = _Rec(tmp_path)
    monkeypatch.setattr(sc, "_scandrill", rec.modules)
    raw = tmp_path / "existing"
    raw.mkdir()
    res = sc.scan(job="j", out_dir=tmp_path, from_dir=raw)
    assert rec.scanned is None, "must not drive the ADF"
    assert res.raw_dir == raw
    assert Path(rec.assemble_kw["job_dir"]) == raw


def test_result_reports_the_projection(tmp_path, monkeypatch):
    rec = _Rec(tmp_path)
    monkeypatch.setattr(sc, "_scandrill", rec.modules)
    res = sc.scan(job="j", out_dir=tmp_path)
    assert res.pdf == tmp_path / "j.pdf" and res.pdf.exists()
    assert res.manifest == tmp_path / "j.ingest.json"
    assert res.sides == 2 and res.kept == 1
    assert res.blanks == 1, "a blank side is RECORDED, not deleted"


def test_missing_scandrill_is_a_message_not_a_traceback(monkeypatch, tmp_path):
    def boom():
        raise ImportError("No module named 'scandrill'")
    monkeypatch.setattr(sc, "_scandrill", boom)
    assert sc.available() is False
    with pytest.raises(sc.ScanUnavailable) as e:
        sc.scan(job="j", out_dir=tmp_path)
    assert "pip install" in str(e.value)
