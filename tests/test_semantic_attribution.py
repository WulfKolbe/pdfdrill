"""
Region-based sender/recipient attribution (completes Phase-C on the geometry).

Instead of guessing sender vs recipient from page TEXT, classify each line by its
REGION (classify_block) and split: header/footer/stamp lines are the sender side
(letterhead + registration), body lines hold the recipient block. The recipient's
address then provably comes from the recipient REGION, not from a keyword guess —
so it lands on the recipient Person, never the sender company.

Decoupled: semantic/attribution.py uses only semantic primitives (no pdfdrill
imports); the caller runs sender_of / address extraction on the returned regions.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic.attribution import attribute


def _region(bbox):
    x1, y1, x2, y2 = bbox
    return {"top_left_x": x1, "top_left_y": y1, "width": x2 - x1, "height": y2 - y1}


# Real Provinzial-letter blocks (0–1000 coords): letterhead, recipient, footer.
PROVINZIAL = [
    ("PROVINZIAL", [726, 18, 952, 55]),
    ("Einfach gut versichert GmbH\nGustav-Adolf-Str. 4\n04105 Leipzig", [730, 78, 952, 132]),
    ("Es schreibt Ihnen:\nProvinzialplatz 1, 40591 Düsseldorf", [730, 165, 952, 222]),
    ("Herrn\nWulf Alexander Kolbe\nRotkäppchenweg 1\n51515 Kürten", [195, 145, 455, 212]),
    ("Sehr geehrter Herr Kolbe,", [80, 345, 600, 360]),
    ("gerne informieren wir Sie über Ihre Sterbegeldversicherung für 2026.", [80, 372, 930, 620]),
    ("Provinzial Lebensversicherung AG\nAmtsgericht Kiel HRB 5705", [80, 905, 360, 960]),
]


def test_region_attribution_separates_sender_and_recipient():
    lines = [{"text": t, "region": _region(b)} for t, b in PROVINZIAL]
    att = attribute(lines)
    # the recipient comes from the body region, name + address split out
    assert att.recipient is not None
    assert att.recipient["name"] == "Wulf Alexander Kolbe"
    assert "Rotkäppchenweg 1" in att.recipient["address"]
    assert "51515 Kürten" in att.recipient["address"]
    # the sender side (header/footer) carries a company and NOT the recipient
    assert "Wulf Alexander Kolbe" not in att.sender_text
    assert "GmbH" in att.sender_text or "AG" in att.sender_text
    # the letterhead address is on the sender side, not in the recipient address
    assert "Düsseldorf" in att.sender_text
    assert "Düsseldorf" not in att.recipient["address"]


def test_attribute_no_recipient_when_no_body_marker():
    lines = [{"text": "Provinzial Lebensversicherung AG\nHRB 5705", "region": _region([80, 905, 360, 960])},
             {"text": "gerne informieren wir Sie ausführlich über die Bedingungen", "region": _region([80, 400, 900, 600])}]
    att = attribute(lines)
    assert att.recipient is None
    assert "Provinzial" in att.sender_text


if __name__ == "__main__":
    test_region_attribution_separates_sender_and_recipient(); print("PASS sep")
    test_attribute_no_recipient_when_no_body_marker(); print("PASS no-recipient")
    print("\nAll tests passed.")
