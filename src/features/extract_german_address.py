"""extract_german_address — German postal-address blocks (ADDRESS).

Locale-specific (kept out of the generic `extract_all` set; used by
`pdfdrill entities`). Anchors on a `PLZ Ort` line (5-digit postal code + city)
and folds in the preceding street line ("Strasse <No>") to form the block.
"""
from __future__ import annotations

import re

from .features import Feature

# "51515 Kürten" — German PLZ (not 00xxx) + a capitalised city.
_PLZ_CITY = re.compile(r"\b(?<!\d)([1-9]\d{4})\s+([A-ZÄÖÜ][A-Za-zäöüß.\-/() ]{1,40})")

# Words that follow a 5-digit number but are NOT a city (invoice/customer/label
# tokens, contact-field labels). A "PLZ <word>" hit is rejected when the word is
# one of these or looks like a label (ends in nummer / -nr / -id).
_NOT_CITY = {
    "kundennummer", "kundennr", "rechnungsnummer", "rechnungsnr", "bitte",
    "ust", "ustid", "ust-id", " usti", "e-mail", "email", "mail", "fax", "tel",
    "telefon", "zimmer", "datum", "rechnung", "betrag", "summe", "seite",
    "konto", "iban", "bic", "blz", "nr", "nummer", "az", "steuernummer",
    "kassenzeichen", "aktenzeichen", "buchungszeichen", "vom", "am",
}
_LABELISH = re.compile(r"(?:nummer|-?nr\.?|-?id)$", re.I)
# "Rotkäppchenweg 1" / "Musterstr. 12a" — a street ending + house number.
_STREET = re.compile(
    r"[A-ZÄÖÜ][\wäöüß.\-]*(?:stra(?:ß|ss)e|str\.?|weg|platz|allee|gasse|ring|damm|"
    r"ufer|chaussee)\s+\d+[a-z]?", re.I)


def extract(text: str, page_id: str = "") -> list[Feature]:
    text = text or ""
    out: list[Feature] = []
    for m in _PLZ_CITY.finditer(text):
        plz, city = m.group(1), m.group(2).strip(" .,-")
        first = city.split()[0] if city else ""
        if first.lower() in _NOT_CITY or _LABELISH.search(first) or len(first) < 2:
            continue                            # not a real city -> skip
        # Keep the city to its first 1-3 plausible tokens (drop trailing labels).
        toks = []
        for w in city.split():
            if w.lower() in _NOT_CITY or _LABELISH.search(w):
                break
            toks.append(w)
            if len(toks) >= 3:
                break
        city = " ".join(toks)
        # Look back a little for a street line to anchor the block.
        back = text[max(0, m.start() - 80):m.start()]
        sm = list(_STREET.finditer(back))
        street = sm[-1].group(0).strip() if sm else ""
        block = (f"{street}, " if street else "") + f"{plz} {city}"
        start = (max(0, m.start() - 80) + sm[-1].start()) if sm else m.start(1)
        out.append(Feature.create(page_id, "ADDRESS", block, 0.8 if street else 0.6,
                                   start, m.end(2)))
    return out


def available() -> bool:
    return True
