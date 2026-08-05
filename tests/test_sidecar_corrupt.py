"""A truncated sidecar must not make a document unopenable.

`Sidecar._load` called `json.loads` on the file with no guard, so a zero-byte or
half-written `.drill.json` raised JSONDecodeError out of the CONSTRUCTOR — and
every command builds a Sidecar first, so the document became unusable by every
route, including the ones that would have rebuilt the state.

18 such files existed in the library, all zero-byte, produced when batch runs
were killed mid-write. The sidecar is a CACHE of derived state: the recoverable
answer is to start empty and rebuild, never to refuse the document.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.sidecar import Sidecar


def _pdf(tmp_path) -> Path:
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.4\n%fake\n")
    return p


def test_zero_byte_sidecar_starts_fresh(tmp_path):
    pdf = _pdf(tmp_path)
    sc = Sidecar(pdf)
    sc.json_path.write_text("")                 # the exact corruption found
    sc2 = Sidecar(pdf)
    assert sc2.facts == set() or not sc2.facts
    sc2.add_fact("SIZE_KNOWN"); sc2.save()
    assert "SIZE_KNOWN" in Sidecar(pdf).facts, "must be writable again"


def test_truncated_json_starts_fresh(tmp_path):
    pdf = _pdf(tmp_path)
    sc = Sidecar(pdf)
    sc.json_path.write_text('{"facts": ["SIZE_KNOWN"], "evid')   # half-written
    assert Sidecar(pdf) is not None                              # must not raise


def test_a_valid_sidecar_is_still_read(tmp_path):
    """The guard must not quietly discard good state."""
    pdf = _pdf(tmp_path)
    sc = Sidecar(pdf); sc.add_fact("SIZE_KNOWN"); sc.save()
    assert "SIZE_KNOWN" in Sidecar(pdf).facts
    assert json.loads(sc.json_path.read_text())["facts"] == ["SIZE_KNOWN"]
