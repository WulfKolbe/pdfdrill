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

# A lone surrogate, built at RUNTIME. Writing the escape in source would
# put a real surrogate in this module's docstring, and importing a module
# whose docstring cannot be encoded fails outright — which is exactly how
# a one-line comment broke `import pdfdrill.commands`.
SURR = 'Alg' + chr(0xDCE8) + 'bre'


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


def test_sidecar_saves_data_containing_a_surrogate(tmp_path):
    """`Sidecar.save` wrote with `ensure_ascii=False` + `encoding="utf-8"`, which
    cannot encode a lone surrogate — so a filename that is not valid UTF-8 (18
    such folders existed in one library) failed the SAVE, and with it every
    command on that document.

    The surrogate is injected into the DATA here rather than the filename:
    pytest cannot report a tmp directory that contains a surrogate-named file,
    so writing one breaks every later test that uses tmp_path.
    """
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    sc = Sidecar(pdf)
    sc.set_evidence("original_name", SURR)       # the shape found on disk
    sc.save()                                             # must not raise

    again = Sidecar(pdf)
    assert again.get_evidence("original_name") == SURR, \
        "the exact name must survive the round trip"


def test_ordinary_sidecar_is_written_unescaped(tmp_path):
    """The fallback must not turn every umlaut into an escape."""
    pdf = tmp_path / "Bücher.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    sc = Sidecar(pdf); sc.add_fact("SIZE_KNOWN"); sc.save()
    assert "Bücher" in sc.json_path.read_text(encoding="utf-8")


def test_clean_name_removes_surrogates():
    """The bibkey is derived from the filename stem and then written into the
    model, the tiddler titles and every artifact name — so a stem that is not
    valid UTF-8 poisons all of them at once.

    pdfdrill has 78 `json.dump(..., ensure_ascii=False)` sites; patching each
    would be whack-a-mole. The surrogate enters ONCE, through the recorded name,
    so it is cleaned once, there. The filesystem PATH is untouched — I/O keeps
    the real bytes, only the RECORDED name is sanitised.

    (The surrogate-named file is not written to disk here: pytest cannot report
    a tmp directory containing one.)
    """
    from pdfdrill.commands import _clean_name

    key = _clean_name(SURR + " 1")
    key.encode("utf-8")                          # must not raise
    assert chr(0xDCE8) not in key
    assert key.startswith("Alg") and key.endswith("1")


def test_clean_name_leaves_ordinary_text_alone():
    from pdfdrill.commands import _clean_name
    for ok in ("2209.00445v3", "B\u00fccher", "Alg\u00e8bre", ""):
        assert _clean_name(ok) == ok


def test_explicit_bibkey_is_cleaned(tmp_path):
    from pdfdrill.commands import resolve_bibkey
    pdf = tmp_path / "x.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
    resolve_bibkey(pdf, SURR, None).encode("utf-8")


def test_normal_stem_is_untouched(tmp_path):
    from pdfdrill.commands import resolve_bibkey
    pdf = tmp_path / "2209.00445v3.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
    assert resolve_bibkey(pdf, None, None) == "2209.00445v3"
