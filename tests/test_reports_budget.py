# tests/test_reports_budget.py — 655
from pathlib import Path

import pdfdrill.reports.budget as B


def _real_jpg(path: Path, w=100, h=100, quality=95):
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), color=(120, 60, 30)).save(path, "JPEG",
                                                        quality=quality)


def test_under_budget_selects_full_scale_and_copies_nothing(tmp_path):
    _real_jpg(tmp_path / "A.jpg")
    _real_jpg(tmp_path / "B.jpg")
    expect = sum((tmp_path / n).stat().st_size for n in ("A.jpg", "B.jpg"))
    scale, quality, total, over = B.choose_rung(tmp_path, ["A", "B"],
                                                budget_mb=20.0)
    assert (scale, quality, over) == (1.0, None, False)
    # 655 item 4 — the predicted total for rung 1.0 IS today's actual bytes,
    # never a re-encode.
    assert total == expect


def test_no_files_found_is_trivially_under_budget(tmp_path):
    assert B.choose_rung(tmp_path, ["missing"], budget_mb=1.0) == (1.0, None, 0, False)


def test_over_budget_selects_first_fitting_rung_not_smallest(tmp_path, monkeypatch):
    """Each successive ladder rung is given a KNOWN, decreasing size, so the
    test can assert exactly WHICH rung wins (the first that fits) rather
    than merely that some rung under budget was picked."""
    # rung 1.0's predicted size is the file's ACTUAL bytes on disk, never a
    # re-encode (item 4) -- padded past every faked ladder size below so
    # rung 1.0 itself is rejected and the ladder is walked for real.
    (tmp_path / "A.jpg").write_bytes(b"\xff\xd8" + b"0" * 1_000_000)
    sizes_by_scale = {0.85: 900_000, 0.70: 700_000, 0.60: 500_000,
                      0.50: 300_000, 0.42: 100_000}
    monkeypatch.setattr(B, "_encoded_size",
                        lambda path, scale, quality: sizes_by_scale[scale])
    # Budget under the real (tiny) on-disk size, so rung 1.0 is rejected and
    # the ladder above is walked; and under 0.85/0.70's faked sizes, so the
    # first fitting rung is 0.60, not the smallest (0.42).
    budget_mb = 600_000 / (1024 * 1024)
    scale, quality, total, over = B.choose_rung(tmp_path, ["A"],
                                                budget_mb=budget_mb)
    assert (scale, quality, total, over) == (0.60, 72, 500_000, False)


def test_floor_reached_reports_over_budget(tmp_path, monkeypatch):
    _real_jpg(tmp_path / "A.jpg")
    monkeypatch.setattr(B, "_encoded_size", lambda path, scale, quality: 10**9)
    budget_mb = ((tmp_path / "A.jpg").stat().st_size - 1) / (1024 * 1024)
    scale, quality, total, over = B.choose_rung(tmp_path, ["A"],
                                                budget_mb=budget_mb)
    assert (scale, quality) == B.CROP_LADDER[-1]
    assert over is True


def test_mb_is_decimal_not_binary(tmp_path):
    """655 review round 1, finding 1 -- this codebase's "MB" is 1,000,000
    bytes (gilmore's 115,427,118-byte evidence-formula.pdf reads as "115.4
    MB" only under /1e6), never 1024*1024. A budget of 20MB must reject a
    file at 20,500,000 bytes (over decimal, under binary MiB) and accept
    one at 19,500,000 (under both)."""
    assert B._bytes_for_mb(20.0) == 20_000_000
    assert round(B._mb_for_bytes(20_000_000), 6) == 20.0
    # 20,500,000 bytes: over the decimal 20MB budget, under the binary
    # 20 MiB (20,971,520) one -- exactly the gap the review caught. With an
    # EMPTY ladder, rung 1.0 is the only rung that could possibly be
    # accepted; it must NOT be here.
    (tmp_path / "A.jpg").write_bytes(b"0" * 20_500_000)
    scale, quality, total, over = B.choose_rung(tmp_path, ["A"], budget_mb=20.0,
                                                ladder=())
    assert scale != 1.0                        # rung 1.0 correctly rejected
    assert total == 20_500_000 and over is True   # no ladder rung to fall back to
    (tmp_path / "B.jpg").write_bytes(b"0" * 19_500_000)
    scale, quality, total, over = B.choose_rung(tmp_path, ["B"], budget_mb=20.0)
    assert (scale, over) == (1.0, False)


def test_check_artifact_under_and_over_budget(tmp_path):
    (tmp_path / "small.pdf").write_bytes(b"0" * 19_000_000)
    (tmp_path / "big.pdf").write_bytes(b"0" * 21_000_000)
    assert B.check_artifact(tmp_path / "small.pdf", budget_mb=20.0) == (19_000_000, False)
    size, over = B.check_artifact(tmp_path / "big.pdf", budget_mb=20.0)
    assert size == 21_000_000 and over is True


def test_check_artifact_missing_file_is_not_over_budget(tmp_path):
    assert B.check_artifact(tmp_path / "nope.pdf", budget_mb=20.0) == (0, False)


def test_encoded_size_failure_is_printed(tmp_path, capsys):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not a jpeg")
    size = B._encoded_size(bad, 0.5, 70)
    assert size == bad.stat().st_size          # conservative fallback, unchanged
    assert "could not be re-encoded" in capsys.readouterr().out


def test_search_never_writes_to_disk(tmp_path, monkeypatch):
    """The ladder WALK must not touch the filesystem -- only the winning
    rung, written later by report_tex.scale_crops, does."""
    _real_jpg(tmp_path / "A.jpg")
    budget_mb = ((tmp_path / "A.jpg").stat().st_size - 1) / (1024 * 1024)
    before = sorted(p.name for p in tmp_path.iterdir())
    B.choose_rung(tmp_path, ["A"], budget_mb=budget_mb)
    after = sorted(p.name for p in tmp_path.iterdir())
    assert before == after == ["A.jpg"]
