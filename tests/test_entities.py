"""
Tests for the commercial-entity extractors (features) + cmd_entities (CR #4).
Self-contained: IBAN mod-97 checksum, BIC, German address, ids — no external
tools, no real OCR.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from features import extract_iban, extract_bic, extract_german_address, extract_ids


def test_iban_checksum_and_parts():
    assert extract_iban.is_valid("DE11370501980093402972")      # Sparkasse KölnBonn
    assert extract_iban.is_valid("DE92370691252119644014")
    assert not extract_iban.is_valid("DE11370501980093402973")  # wrong check digits
    parts = extract_iban.german_parts("DE11 3705 0198 0093 4029 72")
    assert parts == {"blz": "37050198", "konto": "93402972"}


def test_extract_iban_marks_validity():
    feats = extract_iban.extract("Bank: DE11 3705 0198 0093 4029 72 (ours)", "p1")
    assert len(feats) == 1
    f = feats[0]
    assert f.type == "IBAN" and f.value == "DE11370501980093402972" and f.confidence == 1.0


def test_extract_bic_requires_label_or_plausible():
    feats = extract_bic.extract("BIC: COLSDE33XXX and noise WORDABCD here", "p")
    vals = {f.value for f in feats}
    assert "COLSDE33XXX" in vals
    assert "WORDABCD" not in vals          # unlabelled, implausible country -> rejected


def test_german_address_anchors_street_and_rejects_label_noise():
    text = ("Rotkäppchenweg 1\n51515 Kürten\n\n"
            "Rechnung 18285 Kundennummer 11445\n82131 USt-ID\n")
    vals = [f.value for f in extract_german_address.extract(text, "p")]
    assert any(v == "Rotkäppchenweg 1, 51515 Kürten" for v in vals)
    # The 5-digit invoice/label noise is not emitted as an address.
    assert not any("Kundennummer" in v or "USt" in v for v in vals)


def test_extract_ids_labels():
    text = "Kassenzeichen 725.356.194.433\nSteuernummer 204/5189/1009\nKundennummer: 11445"
    got = {(f.type, f.value) for f in extract_ids.extract(text, "p")}
    assert ("KASSENZEICHEN", "725.356.194.433") in got
    assert ("STEUERNUMMER", "204/5189/1009") in got
    assert ("CUSTOMER_NO", "11445") in got


def test_cmd_entities_end_to_end():
    from docmodel.core import Document, DocObject, Realization
    from pdfdrill.sidecar import Sidecar
    from pdfdrill.commands import cmd_entities, MODEL_BUILT, ENTITIES_BUILT
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "b.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
        sc = Sidecar(pdf); sc.blob_dir.mkdir(parents=True, exist_ok=True)
        doc = Document()
        mp = doc.ensure_stream("mathpix_lines")
        a = mp.append(type="text", _page=20,
                      text=("Sparkasse KölnBonn IBAN DE11 3705 0198 0093 4029 72 "
                            "BIC COLSDE33XXX\nKassenzeichen 725.356.194.433\n"
                            "Rotkäppchenweg 1\n51515 Kürten"))
        pg = DocObject(type="Page", props={"page_number": 20})
        pg.add_realization(Realization(stream="mathpix_lines", start=a, end=a, role="surface"))
        doc.add(pg)
        (sc.blob_dir / "model.docmodel.json").write_text(json.dumps(doc.to_dict()))
        sc.add_fact(MODEL_BUILT); sc.save()

        out = cmd_entities(pdf)
        assert "1/1 IBAN(s) checksum-valid" in out
        assert "DE11370501980093402972 (valid" in out and "BLZ 37050198" in out
        assert "Sparkasse KölnBonn" in out          # bank name near the IBAN
        assert "BIC  COLSDE33XXX" in out
        assert "Rotkäppchenweg 1, 51515 Kürten" in out
        assert "KASSENZEICHEN 725.356.194.433" in out
        assert Sidecar(pdf).has(ENTITIES_BUILT)


if __name__ == "__main__":
    import types
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and isinstance(v, types.FunctionType)]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"\nAll {len(fns)} tests passed.")
