"""
QR / barcode scanning (pdfdrill.qrscan). The pure pieces are TDD'd here:
  * parse_epc: a GiroCode / EPC QR (BCD…) → structured SEPA payment fields —
    creditor name, IBAN, amount, reference. This is independent CONFIRMATION of
    the IBAN/amount/reference the text extractors find, and often supplies the
    issuer name the text layer omits.
  * _result_to_dict: normalise a zxing-cpp result (duck-typed) → a finding dict,
    binary-safe (base64 for non-text codes like Data Matrix franking marks).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.qrscan import parse_epc, _result_to_dict


AOK_QR = ("BCD\r\n002\r\n1\r\nSCT\r\n\r\nAOK Rheinland/Hamburg\r\n"
          "DE24300400000180384000\r\nEUR297.94\r\n\r\n\r\nD990775288 QR / Kolbe QR")


def test_parse_epc_girocode():
    epc = parse_epc(AOK_QR)
    assert epc is not None
    assert epc["service"] == "BCD" and epc["identification"] == "SCT"
    assert epc["name"] == "AOK Rheinland/Hamburg"        # the issuer/creditor
    assert epc["iban"] == "DE24300400000180384000"
    assert epc["currency"] == "EUR" and epc["amount"] == "297.94"
    assert "D990775288" in epc["remittance"]             # the Versichertennummer reference


def test_parse_epc_returns_none_for_non_epc():
    assert parse_epc("https://example.com/pay?x=1") is None
    assert parse_epc("just some text") is None


class _FakePoint:
    def __init__(self, x, y): self.x, self.y = x, y


class _FakePos:
    top_left = _FakePoint(10, 20)
    bottom_right = _FakePoint(110, 120)


class _FakeResult:
    def __init__(self, fmt, text, raw=b"", valid=True):
        self.format = fmt; self.text = text; self.bytes = raw; self.valid = valid
        self.position = _FakePos(); self.orientation = 0


def test_result_to_dict_text_qr():
    d = _result_to_dict(_FakeResult("QRCode", "BCD\n002"), page=2)
    assert d["format"] == "QRCode" and d["page"] == 2
    assert d["content"] == "BCD\n002" and d["bbox"] == [10, 20, 110, 120]


def test_result_to_dict_binary_is_base64():
    d = _result_to_dict(_FakeResult("DataMatrix", "", raw=b"\x00\x01\xfe"), page=2)
    assert d["content"] == "" and d.get("content_base64")   # binary → base64, not garbage


if __name__ == "__main__":
    test_parse_epc_girocode(); print("PASS epc")
    test_parse_epc_returns_none_for_non_epc(); print("PASS epc-none")
    test_result_to_dict_text_qr(); print("PASS result-text")
    test_result_to_dict_binary_is_base64(); print("PASS result-binary")
    print("\nAll tests passed.")
