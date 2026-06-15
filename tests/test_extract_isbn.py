"""
extract_isbn — ISBN-10 / ISBN-13 / ISSN identifiers with self-contained
checksum validation (mirrors extract_iban's keyless mod-97 approach; no
python-stdnum dependency). Found on the copyright/imprint page (front matter).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from features import extract_isbn as ei


def test_isbn13_checksum():
    assert ei.valid_isbn13("9783161484100")          # classic valid example
    assert ei.valid_isbn13("978-3-16-148410-0")      # hyphenated
    assert not ei.valid_isbn13("9783161484101")      # bad check digit


def test_isbn10_checksum_with_x():
    assert ei.valid_isbn10("0306406152")             # valid
    assert ei.valid_isbn10("0-306-40615-2")
    assert ei.valid_isbn10("097522980X")             # X check digit, valid
    assert not ei.valid_isbn10("0306406153")


def test_issn_checksum():
    assert ei.valid_issn("0378-5955")                # valid ISSN
    assert ei.valid_issn("2049-3630")
    assert not ei.valid_issn("0378-5956")


def test_extract_labelled_and_bare():
    text = ("Imprint page.\nISBN 978-3-16-148410-0 (hardcover)\n"
            "e-ISBN: 0306406152\nISSN 0378-5955\n"
            "A bare EAN 9783161484100 also appears.\n")
    feats = ei.extract(text)
    kinds = {(f.type, f.value) for f in feats}
    assert ("ISBN", "9783161484100") in kinds        # normalized (digits only)
    assert ("ISBN", "0306406152") in kinds
    assert ("ISSN", "0378-5955") in kinds
    assert all(f.confidence >= 0.9 for f in feats)    # checksum-valid


def test_invalid_checksum_not_emitted():
    # a 13-digit number that isn't a valid ISBN must not be reported as one
    feats = ei.extract("Order number 9783161484101 and code 1234567890123.")
    assert not any(f.type == "ISBN" for f in feats)


def test_in_registry():
    import features
    assert "isbn" in dict(features.EXTRACTORS)
    out = features.extract_all("ISBN 978-3-16-148410-0", only=["isbn"])
    assert any(f.type == "ISBN" for f in out)


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
