"""
Vendored eqcrop cropper (src/pdfdrill/eqcrop.py): the Pillow-only DZI Pyramid
that assembles a region crop from only the tiles it overlaps. The local
MathPix-free image source (Phase B of the image-server plan).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def test_pyramid_importable():
    # the cropper must import (Pillow-only) so the image server / pdfdrill crops work
    from pdfdrill.eqcrop import Pyramid
    assert hasattr(Pyramid, "crop")


def test_pyramid_crop_from_a_built_dzi(tmp_path=None):
    """Build a tiny DZI with Pillow (one level), then crop a sub-rectangle —
    proves the tile-assembly path end-to-end without pyvips/Ghostscript."""
    try:
        from PIL import Image
    except Exception:
        print("SKIP eqcrop crop (no Pillow)"); return
    import tempfile
    import xml.etree.ElementTree as ET
    from pdfdrill.eqcrop import Pyramid

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        # a 120x80 page as a single-tile DZI level "0" (overlap 0, tile >= image)
        full = Image.new("RGB", (120, 80), (255, 255, 255))
        for x in range(40, 60):                       # a black band at x∈[40,60)
            for y in range(80):
                full.putpixel((x, y), (0, 0, 0))
        dzi = d / "page01.dzi"
        ns = "http://schemas.microsoft.com/deepzoom/2008"
        root = ET.Element(f"{{{ns}}}Image", TileSize="256", Overlap="0", Format="png")
        ET.SubElement(root, f"{{{ns}}}Size", Width="120", Height="80")
        ET.ElementTree(root).write(dzi, xml_declaration=True, encoding="UTF-8")
        files = d / "page01_files" / "0"
        files.mkdir(parents=True)
        full.save(files / "0_0.png")

        crop = Pyramid(str(dzi)).crop(40, 0, 60, 80)  # the black band
        assert crop.size == (20, 80)
        assert crop.getpixel((10, 40)) == (0, 0, 0)   # inside the band → black


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
