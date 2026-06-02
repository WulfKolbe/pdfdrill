"""
Bundle segmentation — partition one scanned PDF that is several separate
documents (shuffled / duplex, blank backs removed) into ordered documents.

Heuristic, built on the continuity (Issue 1/2) + entities (Issue 4) signals:
group pages by a stable per-document signature (a sender-assigned identifier or
the sender/letterhead), order each group by its continuity number (so physical
scan order is irrelevant), and flag duplicate copies (same signature + same
page-sequence). Pure: takes the continuity/entities/text dicts, returns a flat
manifest — no I/O, unit-testable.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# Letterhead / sender patterns (German): authority or company.
_SENDER = re.compile(
    r"\b(Finanzamt\s+[A-ZÄÖÜ][\wäöüß.\-]+"
    r"|Stadt\s+[A-ZÄÖÜ][\wäöüß.\-]+"
    r"|Stadtkasse\s+[A-ZÄÖÜ][\wäöüß.\-]+"
    r"|Bundes(?:amt|kasse|bank)[\wäöüß.\- ]{0,30}"
    r"|[A-ZÄÖÜ][\wäöüß.\-]+(?:[ ][A-ZÄÖÜ][\wäöüß.\-]+){0,3}[ ]"
    r"(?:GmbH(?:[ ]&[ ]Co\.?[ ]KG)?|AG|KG|GbR|mbH|e\.K\.|e\.V\.|UG))\b")


def sender_of(text: str) -> str:
    m = _SENDER.search(text or "")
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _signature(page: int, ent: dict, text: str) -> Optional[tuple]:
    """A stable per-document key. Administrative ids key by VALUE only (so the
    same number tagged Steuernummer on one page and Aktenzeichen on another
    doesn't split one document); else the sender; else an invoice number."""
    rec = ent.get(page) or {}
    ids = dict((t, v) for t, v in rec.get("ids", []))
    for typ in ("KASSENZEICHEN", "AKTENZEICHEN", "STEUERNUMMER"):
        if ids.get(typ):
            return ("ID", ids[typ])
    s = sender_of(text)
    if s:
        return ("SENDER", s)
    if ids.get("INVOICE_NO"):
        return ("INVOICE_NO", ids["INVOICE_NO"])
    return None


def segment(continuity: dict, entities: dict, page_text: dict) -> list[dict[str, Any]]:
    """Return an ordered list of documents:
    {label, signature, identifier, pages:[ordered], duplicates:[pages], total}."""
    continuity = {int(k): v for k, v in continuity.items()}
    entities = {int(k): v for k, v in (entities or {}).items()}
    page_text = {int(k): v for k, v in (page_text or {}).items()}
    pages = sorted(set(continuity) | set(entities) | set(page_text))

    groups: dict[tuple, list[int]] = {}
    singles: list[int] = []
    for p in pages:
        sig = _signature(p, entities, page_text.get(p, ""))
        if sig is None:
            singles.append(p)
        else:
            groups.setdefault(sig, []).append(p)

    # Attach a signature-less page to the immediately-preceding grouped page when
    # it is a continuation (best-effort for blank-id continuation sheets).
    docs: list[dict[str, Any]] = []
    for sig, gpages in groups.items():
        seqd = {p: (continuity.get(p, {}) or {}).get("seq_in_doc") for p in gpages}
        ordered = sorted(gpages, key=lambda p: (seqd[p] is None, seqd[p] or 0, p))
        # Duplicates: same seq number within the group (or identical pages).
        seen_seq: dict[int, int] = {}
        dups: list[int] = []
        kept: list[int] = []
        for p in ordered:
            s = seqd[p]
            if s is not None and s in seen_seq:
                dups.append(p)
            else:
                kept.append(p)
                if s is not None:
                    seen_seq[s] = p
        total = next((continuity[p].get("doc_total") for p in kept
                      if continuity.get(p, {}).get("doc_total")), None)
        # Label by the sender found on any page of the group, else the id value.
        label = next((sender_of(page_text.get(p, "")) for p in ordered
                      if sender_of(page_text.get(p, ""))), "") or sig[1]
        docs.append({"label": label, "signature": sig, "identifier": sig[1],
                     "pages": kept, "duplicates": dups, "total": total})

    for p in singles:
        docs.append({"label": "(unidentified)", "signature": None,
                     "identifier": None, "pages": [p], "duplicates": [], "total": None})

    docs.sort(key=lambda d: d["pages"][0] if d["pages"] else 1e9)
    return docs
