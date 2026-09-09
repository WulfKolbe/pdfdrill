# tests/test_scale_crops.py — 655: wiring report_tex.scale_crops
from pathlib import Path

from pdfdrill.report_tex import scale_crops


def _real_jpg(path: Path, w=100, h=100, color=(120, 60, 30)):
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), color=color).save(path, "JPEG", quality=95)


def test_scale_crops_returns_original_pixel_width(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    _real_jpg(src / "A.jpg", w=300, h=200)
    widths = scale_crops(src, dst, ["A"], scale=0.5, quality=70)
    assert widths == {"A": 300}
    from PIL import Image
    with Image.open(dst / "A.jpg") as im:
        assert im.size == (150, 100)          # the FILE is smaller...
    # ...but the returned width is the ORIGINAL, for crop_cell to set the
    # physical size from (655 item 5 / report_tex.py:713-717).


def test_scale_crops_never_touches_the_source(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    _real_jpg(src / "A.jpg", w=300, h=200)
    before = (src / "A.jpg").read_bytes()
    scale_crops(src, dst, ["A"], scale=0.5, quality=70)
    assert (src / "A.jpg").read_bytes() == before


def test_scale_crops_force_bypasses_the_mtime_cache(tmp_path):
    """Without `force`, a destination newer than the source is left alone —
    fine when the rung has not changed. `force=True` (what `reports.budget`
    always passes) must re-encode anyway, so a rebuild that picked a
    DIFFERENT rung than last time cannot silently serve the old one."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    _real_jpg(src / "A.jpg", w=300, h=200)
    scale_crops(src, dst, ["A"], scale=0.85, quality=75)
    from PIL import Image
    with Image.open(dst / "A.jpg") as im:
        size_085 = im.size
    # Same call, smaller rung, force=False: mtime cache skips the re-encode.
    scale_crops(src, dst, ["A"], scale=0.42, quality=70, force=False)
    with Image.open(dst / "A.jpg") as im:
        assert im.size == size_085             # STALE — the cache bug
    # force=True re-encodes regardless of mtime.
    scale_crops(src, dst, ["A"], scale=0.42, quality=70, force=True)
    with Image.open(dst / "A.jpg") as im:
        assert im.size != size_085              # fresh, the requested rung
