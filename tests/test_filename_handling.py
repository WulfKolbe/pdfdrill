"""
sources.existing_local_path — battle-proven resolution of a LOCAL path that a
user pasted from a rendered page / URL. The same correct file can be "not found"
on the first paste and "found" on a clean retype when the pasted form carries:
  * a trailing non-breaking / zero-width space (paste artifact),
  * an NFD-decomposed accent (macOS pastes an umlaut as base + combining mark
    while the file on a Linux disk is NFC),
  * percent-encoding (a copied URL fragment: %20 -> space, %c3%bc -> u-umlaut).
The resolver tries these normalizations (stdlib unicodedata + urllib.parse) and
returns the real Path, or None when nothing on disk matches (never invents one).
"""
import sys
import tempfile
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import sources

UUML = "Ü"      # U-umlaut (composed)
uuml = "ü"      # u-umlaut (composed)


def _mk(d, name):
    p = Path(d) / name
    p.write_bytes(b"%PDF-1.4")
    return p


def test_exact_path_returned():
    with tempfile.TemporaryDirectory() as d:
        p = _mk(d, "Axe-Fx-II-Owners-Manual.pdf")
        assert sources.existing_local_path(str(p)) == p


def test_trailing_nbsp_and_zero_width_stripped():
    with tempfile.TemporaryDirectory() as d:
        p = _mk(d, "Axe-Fx-II-Owners-Manual.pdf")
        # regular space, NBSP, zero-width space, BOM, LRM (all common paste junk)
        for cp in (0x20, 0xA0, 0x200B, 0xFEFF, 0x200E):
            got = sources.existing_local_path(str(p) + chr(cp))
            assert got == p, f"U+{cp:04X}: {got}"


def test_nfd_decomposed_accent_matches_nfc_file():
    with tempfile.TemporaryDirectory() as d:
        # file on disk stored NFC (composed U-umlaut)
        p = _mk(d, unicodedata.normalize("NFC", UUML + "bungsbuch.pdf"))
        # user pastes the NFD (decomposed) form
        pasted = unicodedata.normalize("NFD", str(p))
        assert pasted != str(p)                      # genuinely different bytes
        assert sources.existing_local_path(pasted) == p


def test_percent_encoded_local_path_decoded():
    with tempfile.TemporaryDirectory() as d:
        p = _mk(d, UUML + "bungsbuch f" + uuml + "r Dummies.pdf")
        # a copied URL fragment: spaces -> %20, umlauts -> %c3%9c / %c3%bc
        enc = str(Path(d)) + "/" + "%C3%9Cbungsbuch%20f%C3%BCr%20Dummies.pdf"
        assert sources.existing_local_path(enc) == p


def test_absent_file_returns_none():
    with tempfile.TemporaryDirectory() as d:
        assert sources.existing_local_path(str(Path(d) / "nope.pdf")) is None


def test_pdf_arg_resolves_normalized():
    """_pdf (the CLI chokepoint) uses the resolver before raising Not found."""
    from pdfdrill import cli
    with tempfile.TemporaryDirectory() as d:
        p = _mk(d, "Report (final), v2.pdf")
        got = cli._pdf([str(p) + chr(0xA0)])    # trailing NBSP from a paste (U+00A0)
        assert got == p


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try:
            t()
            print(f"PASS {name}")
        except AssertionError as e:
            failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e:
            failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
