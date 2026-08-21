"""068 — a shaded equation box must be detected, not excluded by name."""
from PIL import Image, ImageDraw

from pdfdrill.shading import SHADED_AT, is_shaded, midgrey_fraction


def _crop(tmp_path, name, bg, ink=0):
    """A crop with `bg` background and a little ink on it."""
    im = Image.new("L", (200, 60), bg)
    ImageDraw.Draw(im).rectangle([10, 10, 60, 40], fill=ink)
    p = tmp_path / name
    im.save(p)
    return p


def test_white_crop_is_clean(tmp_path):
    p = _crop(tmp_path, "white.png", 255)
    assert midgrey_fraction(p) < 0.1 and not is_shaded(p)


def test_grey_box_is_detected(tmp_path):
    """217 is the background 1211.3375's shaded equations actually carry."""
    p = _crop(tmp_path, "grey.png", 217)
    assert midgrey_fraction(p) > 0.8 and is_shaded(p)


def test_a_dense_black_equation_is_not_mistaken_for_shading(tmp_path):
    """Ink is < 150 and paper > 245; neither counts. A crop that is mostly
    ink must not read as shaded, or every heavy display equation would."""
    im = Image.new("L", (200, 60), 255)
    ImageDraw.Draw(im).rectangle([0, 0, 170, 55], fill=20)
    p = tmp_path / "dense.png"
    im.save(p)
    assert not is_shaded(p)


def test_threshold_sits_between_the_two_measured_populations():
    """Measured on the corpus: shaded >= 0.884, everything else <= 0.225.
    The cut must stay inside that void, not at the edge of either."""
    assert 0.225 < SHADED_AT < 0.884


def test_unreadable_file_is_not_reported_as_shaded(tmp_path):
    bad = tmp_path / "nope.jpg"
    bad.write_text("not an image")
    assert not is_shaded(bad)
