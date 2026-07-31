"""
producer_policy — what the PDF's *Producer* tells us before we touch anything.

`pdfinfo` is the cheapest signal we have (~50 ms, no rendering, no parsing of
content streams), and it is therefore the FIRST thing the state machine should
consult. The Producer string is not cosmetic metadata: it identifies the writer
that produced the file, and some writers emit structures a given extraction lane
handles badly. Knowing that up front lets the machine DECLINE a lane instead of
producing quietly wrong text and discovering it downstream.

The case this exists for: **OpenOffice.org**. Its writer emits embedded TrueType
subsets with no `/Encoding` at all — the code→character mapping lives only in
`/ToUnicode`, and the codes themselves are sequential values starting at 0x01
(the C0 control range). Our pdfminer-based born-digital lane mishandles this
family, so it is DECLINED here. The other lanes are unaffected and are what the
router should use instead:

    pdftotext (poppler)   fine
    MathPix               fine
    tesseract (OCR)       fine

DELIBERATELY NARROW. `PDFMINER_UNSAFE_PRODUCERS` is an explicit list, not a
substring free-for-all: disabling the free/exact lane is costly, so a producer
earns a place here only once it has actually been seen to fail. LibreOffice —
OpenOffice's descendant — is intentionally NOT listed: it is a separate lineage
and has not been shown to fail. Add it only with evidence.
"""
from __future__ import annotations

import re

# Producer families whose PDFs our pdfminer lane must not be used on. Each entry
# is a regex matched case-insensitively against the raw Producer string.
# Keep this list EXPLICIT and evidence-driven — see the module docstring.
PDFMINER_UNSAFE_PRODUCERS: dict[str, str] = {
    # "OpenOffice.org 3.2", "OpenOffice 4.1.0" — but NOT "LibreOffice ...",
    # which is matched out explicitly by the leading boundary.
    "openoffice": r"(?<![a-z])openoffice(\.org)?\b",
}


def producer_family(producer: str | None) -> str | None:
    """The known family a Producer string belongs to, or None."""
    s = (producer or "").strip()
    if not s:
        return None
    for family, pattern in PDFMINER_UNSAFE_PRODUCERS.items():
        if re.search(pattern, s, re.I):
            return family
    return None


def avoid_pdfminer(producer: str | None) -> bool:
    """True when the pdfminer/born-digital lane must be DECLINED for this
    producer, because it is known to mishandle that writer's output."""
    return producer_family(producer) is not None


def policy_note(producer: str | None) -> str:
    """One prose line explaining the decision (empty when no policy applies) —
    the machine must say why it skipped a lane, never skip it silently."""
    fam = producer_family(producer)
    if fam is None:
        return ""
    return (f"Producer is {(producer or '').strip()!r} ({fam}): the pdfminer "
            f"text-layer lane is DECLINED for this family (it emits font subsets "
            f"with no /Encoding, mapping only via /ToUnicode). pdftotext, MathPix "
            f"and tesseract handle it correctly and are used instead.")
