"""I-D) ADF producer tests — all offline (no scanner, no paper).

Covers the parts the proposal says must be right before hardware is involved:
device resolution (the airscan:eN index is NOT stable), duplex sheet pairing,
the non-destructive blank policy, and duplex skew fusion.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pdfdrill.scandrill.manifest import Manifest, PENDING, REMOVED_BLANK
from pdfdrill.scandrill.producers import adf
from pdfdrill.scandrill.tools import DEFAULT as DEFAULT_TOOLS, SideSkew


# ---- device resolution ----------------------------------------------------------

# The REAL `scanimage -L` output on this machine: a misbehaving backend spews
# binary noise on stdout before the device line. The parser must survive it.
NOISY_REAL_OUTPUT = (
    b"\x8b\x1d\x93\xcf\x00\xa5\xff\xfe\x9c\x00\x01\x02"
    b"device `hpaio:/net/HP_OfficeJet_Pro_8730?ip=192.168.178.120' "
    b"is a Hewlett-Packard HP_OfficeJet_Pro_8730 all-in-one\n"
)


def test_list_devices_survives_binary_noise(monkeypatch):
    class FakeProc:
        stdout = NOISY_REAL_OUTPUT
        stderr = b""
        returncode = 0

    monkeypatch.setattr(adf.subprocess, "run", lambda *a, **k: FakeProc())
    devs = adf.list_devices()
    assert devs == [
        ("hpaio:/net/HP_OfficeJet_Pro_8730?ip=192.168.178.120",
         "Hewlett-Packard HP_OfficeJet_Pro_8730 all-in-one"),
    ]


def test_explicit_device_wins_without_enumerating(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not enumerate when --device is given")

    monkeypatch.setattr(adf.subprocess, "run", boom)
    assert adf.resolve_device("airscan:e9:Whatever") == "airscan:e9:Whatever"


# The REAL enumeration of this printer (verified live 2026-07-15): it offers all
# four backends at once, listed with escl BEFORE airscan.
REAL_DEVICES = [
    ("hpaio:/net/HP_OfficeJet_Pro_8730?ip=192.168.178.120",
     "Hewlett-Packard HP_OfficeJet_Pro_8730 all-in-one"),
    ("hpaio:/net/officejet_pro_8730?ip=192.168.178.120&queue=false",
     "Hewlett-Packard officejet_pro_8730 all-in-one"),
    ("escl:https://192.168.178.120:443",
     "HP OfficeJet Pro 8730 [FAED2B] platen,adf scanner"),
    ("airscan:e0:HP OfficeJet Pro 8730 [FAED2B]",
     "eSCL HP OfficeJet Pro 8730 [FAED2B] ip=192.168.178.120"),
]


def test_resolve_prefers_airscan_despite_list_order(monkeypatch):
    """airscan is the backend the tested scripts target, so it must win even
    though escl/hpaio appear earlier in the real `scanimage -L` output."""
    monkeypatch.setattr(adf, "list_devices", lambda **k: REAL_DEVICES)
    assert adf.resolve_device() == "airscan:e0:HP OfficeJet Pro 8730 [FAED2B]"


def test_resolve_prefers_escl_over_hpaio(monkeypatch):
    monkeypatch.setattr(adf, "list_devices",
                        lambda **k: [d for d in REAL_DEVICES if not d[0].startswith("airscan:")])
    assert adf.resolve_device() == "escl:https://192.168.178.120:443"


def test_resolve_falls_back_to_only_device(monkeypatch):
    """Today only hpaio enumerates — resolution must still succeed."""
    monkeypatch.setattr(adf, "list_devices", lambda **k: [
        ("hpaio:/net/HP_OfficeJet_Pro_8730?ip=192.168.178.120", "HP OfficeJet Pro 8730"),
    ])
    assert adf.resolve_device() == "hpaio:/net/HP_OfficeJet_Pro_8730?ip=192.168.178.120"


def test_resolve_raises_with_no_devices(monkeypatch):
    monkeypatch.setattr(adf, "list_devices", lambda **k: [])
    with pytest.raises(adf.ScannerError):
        adf.resolve_device()


# ---- sheet pairing --------------------------------------------------------------

def test_pair_sheets_duplex_and_odd_trailing():
    files = [Path(f"raw_{i}.png") for i in range(1, 6)]  # 5 pages = 2.5 sheets
    sheets = adf.pair_sheets(files)
    assert sheets == [
        (Path("raw_1.png"), Path("raw_2.png")),
        (Path("raw_3.png"), Path("raw_4.png")),
        (Path("raw_5.png"), None),          # odd trailing page = front, no back
    ]


# ---- the non-destructive blank policy -------------------------------------------

def _page(blank: bool, size=(600, 850)) -> Image.Image:
    arr = np.full((size[1], size[0], 3), 255, dtype=np.uint8)
    if not blank:
        arr[100:300, 100:400] = 20
    return Image.fromarray(arr, "RGB")


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    d = tmp_path / "raw"
    d.mkdir()
    # sheet1: printed front, blank back;  sheet2: printed front, printed back
    _page(False).save(d / "raw_1.png")
    _page(True).save(d / "raw_2.png")
    _page(False).save(d / "raw_3.png")
    _page(False).save(d / "raw_4.png")
    return d


def test_blank_back_recorded_not_deleted(raw_dir: Path):
    m = Manifest(job="adf", created="2026-07-15T00:00:00+02:00")
    pages = adf.ingest_raw_dir(m, raw_dir, device="hpaio:/net/x", rel_to=raw_dir)

    assert len(pages) == 4, "every scanned side must appear in the manifest"
    statuses = [p.status for p in pages]
    assert statuses == [PENDING, REMOVED_BLANK, PENDING, PENDING]

    # the blank page still EXISTS on disk and in the manifest (scanp.sh would rm it)
    assert (raw_dir / "raw_2.png").exists()
    blank = pages[1]
    assert blank.sha256 and blank.blank_mean > 0.999
    # ...but it is excluded from the PDF
    assert len(m.kept_pages()) == 3


def test_sheet_side_provenance(raw_dir: Path):
    m = Manifest(job="adf", created="2026-07-15T00:00:00+02:00")
    pages = adf.ingest_raw_dir(m, raw_dir, device="hpaio:/net/x", rel_to=raw_dir)
    got = [(p.origin["sheet"], p.origin["side"]) for p in pages]
    assert got == [(1, "front"), (1, "back"), (2, "front"), (2, "back")]
    assert all(p.origin["kind"] == "adf" for p in pages)
    # the RESOLVED device is recorded, so the job survives an index shuffle
    assert all(p.origin["device"] == "hpaio:/net/x" for p in pages)


def test_simplex_mode_treats_every_page_as_a_sheet(raw_dir: Path):
    m = Manifest(job="adf", created="2026-07-15T00:00:00+02:00")
    pages = adf.ingest_raw_dir(m, raw_dir, device="d", rel_to=raw_dir, duplex=False)
    assert [p.origin["side"] for p in pages] == ["front"] * 4
    assert [p.origin["sheet"] for p in pages] == [1, 2, 3, 4]


def test_group_sheets_reassembles_triples(raw_dir: Path):
    m = Manifest(job="adf", created="2026-07-15T00:00:00+02:00")
    pages = adf.ingest_raw_dir(m, raw_dir, device="d", rel_to=raw_dir)
    groups = adf.group_sheets(pages)
    assert [(n, f is not None, b is not None) for n, f, b in groups] == [
        (1, True, True), (2, True, True)
    ]


# ---- duplex skew fusion (wired to BlobTracker's real deskew.fuse_duplex) --------

pytestmark_bt = pytest.mark.skipif(
    DEFAULT_TOOLS._blobtracker() is None,
    reason="BlobTracker not available",
)


@pytestmark_bt
def test_fuse_sheet_derives_sparse_back_from_front():
    """A near-empty back page carries no signal; the physical model supplies it:
    angle(back) == -angle(front). This is the case scanp.sh cannot handle."""
    front = SideSkew(angle_deg=1.7, method="blob", confidence=0.9, n_support=12)
    back = SideSkew(angle_deg=None, method="none", confidence=0.0)  # sparse back
    fused = DEFAULT_TOOLS.fuse_sheet(front, back)
    assert fused.source == "front"
    assert fused.front_correction_deg == pytest.approx(1.7)
    assert fused.back_correction_deg == pytest.approx(-1.7)


@pytestmark_bt
def test_fuse_sheet_derives_front_from_back():
    front = SideSkew(angle_deg=None, method="none", confidence=0.0)
    back = SideSkew(angle_deg=-2.4, method="blob", confidence=0.8, n_support=9)
    fused = DEFAULT_TOOLS.fuse_sheet(front, back)
    assert fused.source == "back"
    assert fused.front_correction_deg == pytest.approx(2.4)
    assert fused.back_correction_deg == pytest.approx(-2.4)


@pytestmark_bt
def test_fuse_sheet_confidence_weighted_average_when_both_agree():
    """Two confident sides are independent samples of ONE physical tilt, so they
    are averaged by confidence — not merely kept."""
    front = SideSkew(angle_deg=1.5, method="blob", confidence=1.0, n_support=20)
    back = SideSkew(angle_deg=-1.7, method="blob", confidence=1.0, n_support=20)
    fused = DEFAULT_TOOLS.fuse_sheet(front, back)
    assert fused.source == "both"
    # theta_f = 1.5, theta_b = -(-1.7) = 1.7 -> equal weights -> 1.6
    assert fused.sheet_angle_deg == pytest.approx(1.6)
    assert fused.disagreement_deg == pytest.approx(0.2)


@pytestmark_bt
def test_fuse_sheet_flags_disagreement_and_trusts_stronger_side():
    front = SideSkew(angle_deg=1.5, method="blob", confidence=0.9, n_support=20)
    back = SideSkew(angle_deg=5.0, method="hough", confidence=0.2, n_support=5)
    fused = DEFAULT_TOOLS.fuse_sheet(front, back)   # theta_b = -5.0, |1.5-(-5)|=6.5
    assert "disagree" in fused.source
    assert fused.sheet_angle_deg == pytest.approx(1.5)  # the confident side wins
    assert fused.disagreement_deg == pytest.approx(6.5)


@pytestmark_bt
def test_fuse_sheet_none_when_neither_side_measurable():
    fused = DEFAULT_TOOLS.fuse_sheet(SideSkew(), SideSkew())
    assert fused.source == "none"
    assert fused.sheet_angle_deg is None


# ---- end-to-end skew wiring on a synthetically skewed page ----------------------

@pytestmark_bt
def test_measure_skew_recovers_a_known_angle(tmp_path: Path):
    """A ruled page rotated by a known angle must come back with that angle,
    recorded (never applied), with the back derived from the front."""
    raw = tmp_path / "raw"
    raw.mkdir()
    angle = 2.0

    # a page with strong horizontal rules — the blob fast path's ideal input
    arr = np.full((1100, 850), 255, dtype=np.uint8)
    for y in range(150, 950, 80):
        arr[y:y + 3, 80:770] = 0
    page = Image.fromarray(arr, "L")
    # PIL rotate: positive = counter-clockwise, matching the tools' convention
    page.rotate(angle, resample=Image.BILINEAR, fillcolor=255).save(raw / "raw_1.png")
    Image.fromarray(np.full((1100, 850), 255, dtype=np.uint8), "L").save(raw / "raw_2.png")

    m = Manifest(job="skew", created="2026-07-15T00:00:00+02:00")
    pages = adf.ingest_raw_dir(m, raw, device="d", rel_to=raw)
    n = adf.measure_skew(pages, job_dir=raw)
    assert n >= 1

    front, back = pages[0], pages[1]
    assert front.skew_deg == pytest.approx(angle, abs=0.35), \
        f"expected ~{angle}, got {front.skew_deg} via {front.extra.get('skew_method')}"
    # the blank back is derived from the front, sign-flipped
    assert back.skew_deg == pytest.approx(-front.skew_deg)
    assert front.extra["skew_source"] == "front"
    # recorded, NOT applied — rotation is lossy and opt-in
    assert front.skew_applied is False


def _ruled_page(angle: float = 0.0, size=(850, 1100)) -> Image.Image:
    """A page of strong horizontal rules — the blob fast path's ideal input."""
    arr = np.full((size[1], size[0]), 255, dtype=np.uint8)
    for y in range(150, size[1] - 150, 80):
        arr[y:y + 3, 80:size[0] - 80] = 0
    im = Image.fromarray(arr, "L")
    if angle:
        # PIL positive = counter-clockwise, the tools' convention
        im = im.rotate(angle, resample=Image.BILINEAR, fillcolor=255)
    return im


@pytestmark_bt
def test_deskew_sign_is_correct_end_to_end(tmp_path: Path):
    """THE sign test. A page skewed +2° must come back at ~0° after correction.
    A sign error here would double the skew instead of removing it — and would
    still 'pass' any test that only checks that a rotation happened."""
    raw = tmp_path / "raw"
    raw.mkdir()
    _ruled_page(2.0).save(raw / "raw_1.png")
    _ruled_page(0.0).save(raw / "raw_2.png")   # blank-ish back

    m = Manifest(job="sign", created="2026-07-15T00:00:00+02:00")
    pages = adf.ingest_raw_dir(m, raw, device="d", rel_to=raw)
    adf.measure_skew(pages, job_dir=raw)
    front = pages[0]
    assert front.skew_deg == pytest.approx(2.0, abs=0.35)

    n = adf.apply_deskew(pages, job_dir=raw)
    assert n >= 1
    assert front.skew_applied is True
    assert front.extra["raw_src"] == "raw_1.png"
    assert (raw / "raw_1.png").exists(), "raw must be retained"

    # re-measure the DESKEWED output: the residual angle must be ~0
    corrected = raw / front.src
    assert corrected.exists()
    residual = DEFAULT_TOOLS.analyze_side(corrected)
    assert residual.angle_deg == pytest.approx(0.0, abs=0.35), (
        f"residual {residual.angle_deg}° — correction has the WRONG SIGN "
        f"(it would have doubled the skew)"
    )


@pytestmark_bt
def test_back_side_is_not_measured_but_takes_negative_front(tmp_path: Path):
    """ADF convention: fronts are measured, backs take -front. The back must be
    marked 'skipped', not independently estimated."""
    raw = tmp_path / "raw"
    raw.mkdir()
    _ruled_page(1.5).save(raw / "raw_1.png")          # front: measurable
    _ruled_page(-3.0).save(raw / "raw_2.png")         # back: content, but IGNORED

    m = Manifest(job="conv", created="2026-07-15T00:00:00+02:00")
    pages = adf.ingest_raw_dir(m, raw, device="d", rel_to=raw)
    adf.measure_skew(pages, job_dir=raw)
    front, back = pages

    assert front.extra["skew_method"] in ("blob", "hough")
    assert back.extra["skew_method"] == "skipped", "back must not be measured"
    # back angle is derived, NOT its own -3.0 measurement
    assert back.skew_deg == pytest.approx(-front.skew_deg)
    assert front.extra["skew_source"] == "front"


@pytestmark_bt
def test_back_measured_as_fallback_when_front_unusable(tmp_path: Path):
    """A blank front with a printed back must still get corrected — there is no
    front angle to negate, so the back is measured and the front derived."""
    raw = tmp_path / "raw"
    raw.mkdir()
    Image.fromarray(np.full((1100, 850), 255, dtype=np.uint8), "L").save(raw / "raw_1.png")
    _ruled_page(1.5).save(raw / "raw_2.png")

    m = Manifest(job="fb", created="2026-07-15T00:00:00+02:00")
    pages = adf.ingest_raw_dir(m, raw, device="d", rel_to=raw)
    adf.measure_skew(pages, job_dir=raw)
    front, back = pages

    assert front.status == REMOVED_BLANK
    assert back.extra["skew_method"] in ("blob", "hough"), "back measured as fallback"
    assert back.extra["skew_source"] == "back"
    assert back.skew_deg == pytest.approx(1.5, abs=0.35)


@pytestmark_bt
def test_half_empty_page_skips_the_calculation(tmp_path: Path):
    """A half-empty page has enough ink to keep but too little to trust: the
    estimate must be SKIPPED (method='sparse'), not attempted."""
    from pdfdrill.scandrill.config import Config
    cfg = Config(skew_min_ink_area=10_000_000)   # force everything to look sparse

    raw = tmp_path / "raw"
    raw.mkdir()
    _ruled_page(1.5).save(raw / "raw_1.png")
    _ruled_page(0.0).save(raw / "raw_2.png")

    a = DEFAULT_TOOLS.analyze_side(raw / "raw_1.png", cfg)
    assert a.is_blank is False, "sparse is not blank — the page is kept"
    assert a.method == "sparse"
    assert a.angle_deg is None, "no angle may be guessed from a half-empty page"


def test_deskew_skips_below_min_skew_floor(tmp_path: Path):
    """Rotation is lossy: below the min_skew floor a no-op beats a resample."""
    from pdfdrill.scandrill.config import Config
    raw = tmp_path / "raw"
    raw.mkdir()
    _ruled_page(0.0).save(raw / "raw_1.png")

    m = Manifest(job="floor", created="2026-07-15T00:00:00+02:00")
    pages = adf.ingest_raw_dir(m, raw, device="d", rel_to=raw)
    pages[0].skew_deg = 0.05          # below the 0.2° floor
    n = adf.apply_deskew(pages, job_dir=raw, cfg=Config())
    assert n == 0
    assert pages[0].skew_applied is False
    assert "floor" in pages[0].extra["deskew"]
    assert pages[0].src == "raw_1.png", "src must still point at the untouched raw"


def test_deskew_refuses_absurd_angle(tmp_path: Path):
    from pdfdrill.scandrill.config import Config
    raw = tmp_path / "raw"
    raw.mkdir()
    _ruled_page(0.0).save(raw / "raw_1.png")
    m = Manifest(job="absurd", created="2026-07-15T00:00:00+02:00")
    pages = adf.ingest_raw_dir(m, raw, device="d", rel_to=raw)
    pages[0].skew_deg = 42.0          # beyond max_skew_deg=8
    n = adf.apply_deskew(pages, job_dir=raw, cfg=Config())
    assert n == 0 and pages[0].skew_applied is False
    assert "exceeds" in pages[0].extra["deskew"]


def test_deskew_never_rotates_blank_pages(tmp_path: Path):
    from pdfdrill.scandrill.config import Config
    raw = tmp_path / "raw"
    raw.mkdir()
    Image.fromarray(np.full((1100, 850), 255, dtype=np.uint8), "L").save(raw / "raw_1.png")
    m = Manifest(job="blankrot", created="2026-07-15T00:00:00+02:00")
    pages = adf.ingest_raw_dir(m, raw, device="d", rel_to=raw)
    pages[0].skew_deg = 2.0
    assert pages[0].status == REMOVED_BLANK
    assert adf.apply_deskew(pages, job_dir=raw, cfg=Config()) == 0


@pytestmark_bt
def test_topology_arbitrates_blankness(tmp_path: Path):
    """The blob ink-area check overrides the grayscale-mean prefilter."""
    raw = tmp_path / "raw"
    raw.mkdir()
    arr = np.full((1100, 850), 255, dtype=np.uint8)
    arr[400:500, 200:600] = 10
    Image.fromarray(arr, "L").save(raw / "raw_1.png")
    Image.fromarray(np.full((1100, 850), 255, dtype=np.uint8), "L").save(raw / "raw_2.png")

    m = Manifest(job="blank", created="2026-07-15T00:00:00+02:00")
    pages = adf.ingest_raw_dir(m, raw, device="d", rel_to=raw)
    adf.measure_skew(pages, job_dir=raw)

    assert pages[0].status == PENDING and pages[0].extra["blank_by_blobs"] is False
    assert pages[1].status == REMOVED_BLANK and pages[1].extra["blank_by_blobs"] is True
    assert pages[0].extra["ink_area"] > 0


def test_raw_batch_files_ignores_the_deskew_output_dir(tmp_path):
    """The raw batch is FLAT: raw_%d.png sit directly in raw/, while deskewed
    copies land in raw/proc/ (cfg.deskew_dir). iter_images rglobs, so without a
    depth guard `raw_1_deskewed.png` matches `raw_*.png` and is re-ingested as a
    fresh SIDE — which double-counts pages and, worse, deskews an already-rotated
    image a second time (unrecorded pixel damage; rule 3 says rotation is the only
    pixel-touching step AND it is recorded).

    Found by re-running an acquisition with --from-dir on a raw/ that had already
    been deskewed: 4 sides became 6, and proc/raw_1_deskewed_deskewed.png appeared.
    """
    from pdfdrill.scandrill.producers import adf

    for i in (1, 2, 3, 4):
        (tmp_path / f"raw_{i}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    proc = tmp_path / "proc"
    proc.mkdir()
    for i in (1, 2):
        (proc / f"raw_{i}_deskewed.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    files = adf.raw_batch_files(tmp_path)
    assert [f.name for f in files] == ["raw_1.png", "raw_2.png",
                                       "raw_3.png", "raw_4.png"]
    assert not any("proc" in f.parts for f in files)


# ── orientation (cardinal 90/180/270) — doc-level OSD vote ────────────────────

def test_decide_orientation_unanimous_180():
    """The reported case: a whole stack fed upside down. All non-blank pages read
    180°, so the doc rotates 180 even though per-page OSD confidence is LOW —
    agreement across pages is the robust signal, not one page's confidence."""
    readings = [(180, 11.5), (180, 8.0), (180, 14.5), (None, None)]  # last = blank
    deg, agree, total = adf.decide_orientation(readings)
    assert deg == 180 and agree == 3 and total == 3


def test_decide_orientation_upright_is_zero():
    readings = [(0, 12.0), (0, 9.0), (0, 6.0)]
    deg, agree, total = adf.decide_orientation(readings)
    assert deg == 0


def test_decide_orientation_no_majority_keeps_upright():
    """A split vote (no cardinal wins > half) must NOT rotate — a wrong flip is
    worse than leaving it, since raw/ orientation is recoverable anyway."""
    readings = [(180, 10.0), (0, 10.0), (90, 10.0)]     # 3-way tie
    deg, _agree, _total = adf.decide_orientation(readings)
    assert deg == 0


def test_decide_orientation_bare_majority_wins():
    readings = [(180, 9.0), (180, 8.0), (0, 20.0)]      # 2 of 3 agree on 180
    deg, agree, total = adf.decide_orientation(readings)
    assert deg == 180 and agree == 2 and total == 3


def test_decide_orientation_empty_is_zero():
    assert adf.decide_orientation([]) == (0, 0, 0)
    assert adf.decide_orientation([(None, None)]) == (0, 0, 0)


def test_measure_orientation_records_doc_decision(tmp_path):
    """OSD each non-blank page, vote, and stamp the DOC-level orientation on every
    kept page (blanks don't vote and aren't stamped). No pixels touched here —
    measure only, mirroring measure_skew."""
    from pdfdrill.scandrill.manifest import Page

    class FakeTools:
        def __init__(self, table): self.table = table
        def detect_orientation(self, image, timeout=30.0):
            return self.table.get(Path(image).name)

    pages = [Page(seq=1, src="raw_1.png"),
             Page(seq=2, src="raw_2.png"),
             Page(seq=3, src="raw_3.png"),
             Page(seq=4, src="raw_4.png", status=REMOVED_BLANK)]
    for p in (pages[0], pages[1], pages[2]):
        (tmp_path / p.src).write_bytes(b"x")
    tools = FakeTools({"raw_1.png": (180, 11.0), "raw_2.png": (180, 8.0),
                       "raw_3.png": (180, 14.0)})   # raw_4 blank → not queried
    total = adf.measure_orientation(pages, job_dir=tmp_path, tools=tools)
    assert total == 3
    for p in pages[:3]:
        assert p.extra["orientation_deg"] == 180
        assert p.extra["orientation_votes"] == "3/3"
    assert "orientation_deg" not in pages[3].extra           # blank untouched


def test_measure_orientation_split_stays_upright(tmp_path):
    from pdfdrill.scandrill.manifest import Page

    class FakeTools:
        def detect_orientation(self, image, timeout=30.0):
            return {"a.png": (180, 10.0), "b.png": (0, 10.0),
                    "c.png": (90, 10.0)}.get(Path(image).name)

    pages = [Page(seq=i, src=f"{c}.png") for i, c in enumerate("abc", 1)]
    for p in pages:
        (tmp_path / p.src).write_bytes(b"x")
    adf.measure_orientation(pages, job_dir=tmp_path, tools=FakeTools())
    assert all(p.extra["orientation_deg"] == 0 for p in pages)   # no majority


class _CapTools:
    """Captures the angle apply_deskew asks rotate_image for (no real pixels)."""
    def __init__(self): self.angles = []
    def rotate_image(self, src, dst, angle, **k):
        self.angles.append(round(float(angle), 3)); Path(dst).write_bytes(b"x")
        return True


def _kept_page(tmp_path, *, skew=None, orient=None):
    from pdfdrill.scandrill.manifest import Page
    (tmp_path / "raw_1.png").write_bytes(b"x")
    p = Page(seq=1, src="raw_1.png")
    p.skew_deg = skew
    if orient is not None:
        p.extra["orientation_deg"] = orient
    return p


def test_apply_deskew_orientation_bypasses_the_skew_floor(tmp_path):
    """A 180° misfeed with NO usable skew must still be rotated — orientation is a
    cardinal correction, not a skew angle, so the min-skew 'don't bother' floor
    does not gate it."""
    t = _CapTools()
    p = _kept_page(tmp_path, skew=None, orient=180)
    n = adf.apply_deskew([p], job_dir=tmp_path, tools=t)
    assert n == 1 and t.angles == [180.0]
    assert p.extra["orientation_applied"] == 180 and p.skew_applied is True


def test_apply_deskew_folds_orientation_and_fine_skew_into_one_rotation(tmp_path):
    """One resample, not two: the cardinal flip and the sub-degree deskew are
    summed and applied together."""
    t = _CapTools()
    p = _kept_page(tmp_path, skew=3.0, orient=180)
    adf.apply_deskew([p], job_dir=tmp_path, tools=t)
    assert t.angles == [183.0]


def test_apply_deskew_below_floor_skew_still_dropped_when_upright(tmp_path):
    """Existing behavior unchanged: upright page, sub-floor skew → no rotation."""
    t = _CapTools()
    p = _kept_page(tmp_path, skew=0.05, orient=0)
    n = adf.apply_deskew([p], job_dir=tmp_path, tools=t)
    assert n == 0 and t.angles == []


def test_apply_deskew_plain_skew_unchanged_without_orientation(tmp_path):
    """No orientation recorded at all (old models) → pure deskew, as before."""
    t = _CapTools()
    p = _kept_page(tmp_path, skew=3.0, orient=None)
    adf.apply_deskew([p], job_dir=tmp_path, tools=t)
    assert t.angles == [3.0]
