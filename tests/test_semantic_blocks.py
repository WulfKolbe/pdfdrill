"""
Phase C — block-role classifier.

Classifies a layout block (text + bbox) into header/footer/body/table/signature/
stamp/other, so the graph builder can attribute evidence correctly: the sender is
in the letterhead (header), the recipient is a body address block, and company
registration data (HRB/USt-ID/Vorstand) is in the footer. Content cues override
position. Fixtures are the real Provinzial-letter blocks (bbox in 0–1000).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic.blocks import BlockRole, classify_block, classify_blocks


# Real blocks from the Provinzial letter (0–1000 coords), with expected roles.
PROVINZIAL = [
    ("b1", "PROVINZIAL", [726, 18, 952, 55], BlockRole.HEADER),
    ("b2", "Ihr Partner vor Ort ist\nEinfach gut versichert GmbH\nGustav-Adolf-Str. 4\n"
           "04105 Leipzig\nTelefon 0341 250 779 66", [730, 78, 952, 132], BlockRole.HEADER),
    ("b5", "50KD04 85500127379\n08 2FD0 8E81 40 E003 EE8E\nP  DV 04.26   0,95  Deutsche Post",
     [80, 100, 470, 172], BlockRole.STAMP),
    ("b6", "Herrn\nWulf Alexander Kolbe\nRotkäppchenweg 1\n51515 Kürten",
     [195, 145, 455, 212], BlockRole.BODY),
    ("b9", "gerne informieren wir Sie über Ihre Sterbegeldversicherung und Ihre "
           "Beteiligung an erwirtschafteten Überschüssen für das Versicherungsjahr 2026.",
     [80, 372, 930, 620], BlockRole.BODY),
    ("b11", "bitte wenden", [730, 855, 900, 870], BlockRole.OTHER),
    ("b12", "Provinzial Lebensversicherung AG\nSitz Kiel\nAmtsgericht Kiel HRB 5705\n"
            "USt.-ID-Nr. DE 134859008", [80, 905, 360, 960], BlockRole.FOOTER),
    ("b14", "Vorstand: Dr. Wolfgang Breuer (Vorsitzender), Patric Fedlmeier\n"
            "Vorsitzender des Aufsichtsrats: Dr. Georg Lunemann", [650, 905, 950, 960],
     BlockRole.FOOTER),
]


def test_classify_block_on_real_provinzial_blocks():
    for bid, text, bbox, expected in PROVINZIAL:
        got = classify_block(text, bbox, page_height=1000)
        assert got == expected, f"{bid}: expected {expected}, got {got}"


def test_stamp_cue_overrides_top_position():
    # A franking stamp sits high on the page but must NOT be read as header.
    role = classify_block("Entgelt bezahlt Deutsche Post P DV 04.26 0,95",
                          [80, 90, 470, 160], page_height=1000)
    assert role == BlockRole.STAMP


def test_footer_cue_overrides_mid_position():
    # Registration data anywhere on the page is footer-class content.
    role = classify_block("Amtsgericht Kiel HRB 5705  USt.-ID-Nr. DE 134859008",
                          [80, 500, 360, 540], page_height=1000)
    assert role == BlockRole.FOOTER


def test_recipient_block_is_body_not_header():
    role = classify_block("Herrn\nMax Mustermann\nHauptstr. 1\n50667 Köln",
                          [195, 150, 455, 215], page_height=1000)
    assert role == BlockRole.BODY


def test_signature_cue():
    role = classify_block("Mit freundlichen Grüßen\ni.A. S. Krummenerl",
                          [80, 700, 400, 760], page_height=1000)
    assert role == BlockRole.SIGNATURE


def test_detect_recipient_separates_name_and_address():
    from semantic.blocks import detect_recipient
    rec = detect_recipient("Herrn\nWulf Alexander Kolbe\nRotkäppchenweg 1\n51515 Kürten")
    assert rec is not None
    assert rec["name"] == "Wulf Alexander Kolbe"
    assert "Rotkäppchenweg 1" in rec["address"] and "51515 Kürten" in rec["address"]
    assert "Wulf" not in rec["address"]          # the name is not folded into the address


def test_detect_recipient_none_when_no_marker():
    from semantic.blocks import detect_recipient
    assert detect_recipient("Sehr geehrte Damen und Herren, anbei ...") is None


def test_classify_blocks_tags_a_list():
    blocks = [{"id": bid, "text": text, "bbox": bbox} for bid, text, bbox, _ in PROVINZIAL]
    tagged = classify_blocks(blocks, page_height=1000)
    roles = {b["id"]: b["role"] for b in tagged}
    assert roles["b5"] == BlockRole.STAMP.value and roles["b12"] == BlockRole.FOOTER.value


if __name__ == "__main__":
    test_classify_block_on_real_provinzial_blocks(); print("PASS provinzial")
    test_detect_recipient_separates_name_and_address(); print("PASS recipient-detect")
    test_detect_recipient_none_when_no_marker(); print("PASS recipient-none")
    test_stamp_cue_overrides_top_position(); print("PASS stamp")
    test_footer_cue_overrides_mid_position(); print("PASS footer")
    test_recipient_block_is_body_not_header(); print("PASS recipient")
    test_signature_cue(); print("PASS signature")
    test_classify_blocks_tags_a_list(); print("PASS list")
    print("\nAll tests passed.")
