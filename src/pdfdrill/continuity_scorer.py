#!/usr/bin/env python3
"""
continuity_scorer — segment an ORDERED page stack into documents.

The acquisition floor (NAPS2 / scanner) hands us an ordered, deskewed,
blank-dropped page list. This stage scores every GAP between adjacent pages and
cuts where the boundary score crosses a threshold; pluggable signals each ABSTAIN
when their feature is missing, so it degrades gracefully (QR cover sheets →
deterministic; page numbers → near-deterministic; neither → semantic+structural).

Vendored from a reviewed prototype, with:
  * BUG #1 fix — a LEADING separator's QR payload now reaches the first document.
  * BUG #3 fix — a bare `N/M` is read as a page number only in header/footer
    BANDS, never from body prose (so "1/2 Tasse" isn't a page number).
  * Tracking-code TWO-LEVEL model — Deutsche Post DataMatrix codes (decoded by
    pdfdrill.qrscan) give a HARD outer "mailing" grouping (shared batch suffix =
    one envelope); the soft scorer refines INSIDE it (letter vs enclosure).
  * Commercial provenance — sender = PUBLISHER (its employees are the authors),
    receiver = a NEW explicit field (the audience a journal name leaves implicit),
    projectable to a BibTeX-like record via to_bibtex().

NB this assumes ORDERED input. For a SHUFFLED bundle use pdfdrill.segment
(groups by signature value, orders by continuity number) instead.
No third-party deps (BoW cosine fallback when no real embeddings are present).
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Optional


# --------------------------------------------------------------------------- #
# Per-page features (pdfdrill fills these from the sidecar; all optional)      #
# --------------------------------------------------------------------------- #

@dataclass
class PageFeatures:
    index: int
    text: str = ""
    header: str = ""
    footer: str = ""
    embedding: Optional[list[float]] = None
    page_no: Optional[int] = None
    page_total: Optional[int] = None
    sender: Optional[str] = None            # the PUBLISHER (company that issued it)
    receiver: Optional[str] = None          # the intended audience (explicit here)
    doc_number: Optional[str] = None
    date: Optional[str] = None
    has_letterhead: bool = False
    is_separator: bool = False
    qr_payload: Optional[dict] = None
    tracking_code: Optional[str] = None     # Deutsche Post DataMatrix (mailing batch)

    def derive(self) -> "PageFeatures":
        if self.page_no is None:
            # bands are trustworthy → allow a bare N/M there; body prose is NOT.
            pn = (parse_page_number(self.footer or "", allow_bare=True)
                  or parse_page_number(self.header or "", allow_bare=True)
                  or parse_page_number(self.text or "", allow_bare=False))
            if pn:
                self.page_no, self.page_total = pn
        return self


# --------------------------------------------------------------------------- #
# Page-number parsing — BUG #3 fix: keyworded patterns are body-safe; the bare #
# N/M form is accepted only from header/footer bands (allow_bare).             #
# --------------------------------------------------------------------------- #

_PAGE_KEYWORDED = [
    re.compile(r"seite\s+(\d{1,3})\s+von\s+(\d{1,3})", re.I),     # Seite 1 von 3
    re.compile(r"seite\s+(\d{1,3})\s*/\s*(\d{1,3})", re.I),       # Seite 1/2
    re.compile(r"\b(\d{1,3})\s*(?:of|von)\s+(\d{1,3})\b", re.I),  # 1 of 3 / 1 von 3
    re.compile(r"\bpage\s+(\d{1,3})\s*/\s*(\d{1,3})\b", re.I),    # page 1/3
    re.compile(r"\bpage\s+(\d{1,3})\b", re.I),                    # page 1
    re.compile(r"\bseite\s+(\d{1,3})\b", re.I),                   # Seite 1
]
_PAGE_BARE = re.compile(r"\b(\d{1,3})\s*/\s*(\d{1,3})\b")         # 1/3 — bands only


def parse_page_number(s: str, allow_bare: bool = True) -> Optional[tuple[int, Optional[int]]]:
    if not s:
        return None
    for pat in _PAGE_KEYWORDED:
        m = pat.search(s)
        if m:
            tot = int(m.group(2)) if m.lastindex and m.lastindex >= 2 else None
            return int(m.group(1)), tot
    if allow_bare:
        m = _PAGE_BARE.search(s)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


# --------------------------------------------------------------------------- #
# Text utilities                                                              #
# --------------------------------------------------------------------------- #

_WORD = re.compile(r"[a-zà-ÿ0-9]{2,}", re.I)

def tokens(s: str) -> list[str]:
    return _WORD.findall((s or "").lower())

def bow(s: str) -> dict[str, float]:
    v: dict[str, float] = {}
    for t in tokens(s):
        v[t] = v.get(t, 0.0) + 1.0
    return v

def cosine_sparse(a, b) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b.get(k, 0.0) for k in a)
    na = math.sqrt(sum(x * x for x in a.values()))
    nb = math.sqrt(sum(x * x for x in b.values()))
    return dot / (na * nb) if na and nb else 0.0

def cosine_dense(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0

def jaccard_distance(a, b):
    sa, sb = set(tokens(a)), set(tokens(b))
    if not sa and not sb:
        return None
    inter = len(sa & sb); union = len(sa | sb)
    return 1.0 - (inter / union if union else 0.0)

def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))

def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def slug(s, maxlen=40):
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    return (s[:maxlen].rstrip("_")) or "unknown"


# --------------------------------------------------------------------------- #
# Tracking-code mailing grouping (hard outer level)                            #
# --------------------------------------------------------------------------- #

def _common_suffix_len(a: str, b: str) -> int:
    n = 0
    for x, y in zip(reversed(a), reversed(b)):
        if x != y:
            break
        n += 1
    return n

def same_mailing(a: Optional[str], b: Optional[str], minlen: int = 12) -> bool:
    """Two Deutsche Post tracking codes belong to one mailing iff they share a
    long trailing batch id (≥ minlen chars). The leading sequence increments per
    page; the trailing Einlieferungs-/batch id is constant for the envelope."""
    if not a or not b:
        return False
    return _common_suffix_len(a, b) >= minlen

def assign_mailings(pages: list[PageFeatures]) -> dict[int, str]:
    """index → mailing label (M1, M2, …) by clustering tracking codes."""
    labels: dict[int, str] = {}
    reps: list[str] = []
    for p in pages:
        c = p.tracking_code
        if not c:
            continue
        for ci, rep in enumerate(reps):
            if same_mailing(c, rep):
                labels[p.index] = f"M{ci + 1}"
                break
        else:
            reps.append(c)
            labels[p.index] = f"M{len(reps)}"
    return labels


# --------------------------------------------------------------------------- #
# Signals — (evidence in [0,1] that THIS gap is a boundary, abstain=None)       #
# --------------------------------------------------------------------------- #

@dataclass
class SignalResult:
    name: str
    evidence: Optional[float]
    weight: float
    detail: str = ""
    @property
    def abstained(self) -> bool:
        return self.evidence is None


def sig_page_number(i, j, w):
    if j.page_no is None:
        return SignalResult("page_number_reset", None, w, "no page number on next page")
    if j.page_no == 1:
        if i.page_no is not None and i.page_total is not None and i.page_no == i.page_total:
            return SignalResult("page_number_reset", 0.97, w, f"{i.page_no}/{i.page_total} -> 1")
        return SignalResult("page_number_reset", 0.85, w, "next page is page 1")
    if i.page_no is not None and j.page_no == i.page_no + 1:
        return SignalResult("page_number_reset", 0.03, w, f"clean increment {i.page_no}->{j.page_no}")
    if i.page_no is not None and j.page_no <= i.page_no:
        return SignalResult("page_number_reset", 0.8, w, f"non-increasing {i.page_no}->{j.page_no}")
    return SignalResult("page_number_reset", None, w, "ambiguous")


def sig_embedding(i, j, w):
    if i.embedding is not None and j.embedding is not None:
        cos = cosine_dense(i.embedding, j.embedding)
        return SignalResult("embedding_dissimilarity", clamp(1.0 - cos), w, f"cos={cos:.3f} (dense)")
    ti, tj = i.text or "", j.text or ""
    if not ti or not tj:
        return SignalResult("embedding_dissimilarity", None, w, "missing text/embedding")
    cos = cosine_sparse(bow(ti), bow(tj))
    return SignalResult("embedding_dissimilarity", clamp(1.0 - cos), w, f"cos={cos:.3f} (bow)")


def sig_entity(i, j, w):
    if i.doc_number and j.doc_number:
        if norm(i.doc_number) == norm(j.doc_number):
            return SignalResult("entity_change", 0.02, w, f"same doc# {j.doc_number}")
        return SignalResult("entity_change", 0.92, w, f"doc# {i.doc_number} -> {j.doc_number}")
    checks, changed = 0, 0
    for attr in ("sender", "date"):
        a, b = getattr(i, attr), getattr(j, attr)
        if a and b:
            checks += 1
            if norm(a) != norm(b):
                changed += 1
    if checks == 0:
        return SignalResult("entity_change", None, w, "no comparable entities")
    return SignalResult("entity_change", changed / checks, w, f"{changed}/{checks} entities changed")


def sig_header_footer(i, j, w):
    ds = [d for d in (jaccard_distance(i.header, j.header),
                      jaccard_distance(i.footer, j.footer)) if d is not None]
    if not ds:
        return SignalResult("header_footer_change", None, w, "no bands")
    val = sum(ds) / len(ds)
    return SignalResult("header_footer_change", clamp(val), w, f"band dist={val:.2f}")


def sig_letterhead(i, j, w):
    if j.has_letterhead:
        return SignalResult("letterhead_present", 0.6, w, "letterhead on next page")
    return SignalResult("letterhead_present", None, w, "no letterhead signal")


DEFAULT_SIGNALS: list[tuple[Callable, float]] = [
    (sig_page_number,   0.30),
    (sig_embedding,     0.34),
    (sig_entity,        0.21),
    (sig_header_footer, 0.10),
    (sig_letterhead,    0.05),
]


# --------------------------------------------------------------------------- #
# Scoring                                                                      #
# --------------------------------------------------------------------------- #

def is_qr_boundary(p) -> bool:
    if p.is_separator:
        return True
    if p.qr_payload and str(p.qr_payload.get("type", "")).lower() in ("doc_start", "separator", "patcht"):
        return True
    return False


def score_gap(i, j, signals=DEFAULT_SIGNALS, forced_hard=False, reason="separator/QR boundary"):
    if forced_hard or is_qr_boundary(j):
        return {"gap": f"{i.index}|{j.index}", "boundary_score": 1.0, "continuity": 0.0,
                "hard": True, "reason": reason, "signals": [], "abstained": []}
    results = [fn(i, j, w) for fn, w in signals]
    active = [r for r in results if not r.abstained]
    abstained = [r.name for r in results if r.abstained]
    if active:
        wsum = sum(r.weight for r in active)
        b = sum(r.weight * r.evidence for r in active) / wsum if wsum else 0.0
    else:
        b = 0.0
    return {"gap": f"{i.index}|{j.index}", "boundary_score": round(b, 4),
            "continuity": round(1.0 - b, 4), "hard": False,
            "reason": "" if active else "no active signals (assumed continuous)",
            "signals": [{"name": r.name, "evidence": round(r.evidence, 4),
                         "weight": r.weight, "detail": r.detail} for r in active],
            "abstained": abstained}


def segment(pages: list[PageFeatures], threshold: float = 0.5, signals=DEFAULT_SIGNALS) -> dict:
    for p in pages:
        p.derive()

    # Split off standalone separators; carry their payload to the next content
    # page. BUG #1 fix: the carry is no longer gated on a preceding document, so
    # a LEADING separator names the first document.
    content: list[PageFeatures] = []
    forced_before_index: set[int] = set()
    n_sep = 0
    pending_payload: Optional[dict] = None
    pending_force = False
    for p in pages:
        if is_qr_boundary(p) and (p.is_separator or not (p.text and p.text.strip())):
            n_sep += 1
            pending_force = True
            pending_payload = p.qr_payload or pending_payload
            continue
        if pending_force:
            if content:                                # only force a cut if a doc precedes
                forced_before_index.add(p.index)
            if pending_payload and not p.qr_payload:   # carry payload even with no preceding doc
                p.qr_payload = pending_payload
        pending_force = False
        pending_payload = None
        content.append(p)

    mailings = assign_mailings(content)

    gaps = []
    cut_after = set()
    for a, b in zip(content, content[1:]):
        diff_mailing = bool(a.tracking_code and b.tracking_code
                            and not same_mailing(a.tracking_code, b.tracking_code))
        forced = (b.index in forced_before_index) or diff_mailing
        reason = "different mailing (tracking code)" if diff_mailing else "separator/QR boundary"
        g = score_gap(a, b, signals=signals, forced_hard=forced, reason=reason)
        g["mailing_boundary"] = diff_mailing
        g["is_cut"] = g["hard"] or g["boundary_score"] >= threshold
        if g["is_cut"]:
            cut_after.add(a.index)
        gaps.append(g)

    groups: list[list[PageFeatures]] = []
    cur: list[PageFeatures] = []
    for p in content:
        cur.append(p)
        if p.index in cut_after:
            groups.append(cur); cur = []
    if cur:
        groups.append(cur)

    documents = []
    for k, grp in enumerate(groups, 1):
        first = grp[0]
        name = propose_filename(first, grp)
        mid = next((mailings[p.index] for p in grp if p.index in mailings), None)
        prov = _provenance(first, name["evidence"])
        documents.append({
            "index": k, "pages": [p.index for p in grp],
            "mailing": mid,
            "proposed_filename": name["filename"],
            "naming_evidence": name["evidence"],
            "provenance": prov,
            "bibtex": to_bibtex(prov, key=slug(f"{prov['sender']}_{prov['date']}", 24)),
        })

    # mailing summary (the hard outer grouping)
    mailing_summary = {}
    for d in documents:
        if d["mailing"]:
            mailing_summary.setdefault(d["mailing"], []).extend(d["pages"])

    return {
        "n_pages_in": len(pages), "n_separators_dropped": n_sep,
        "n_documents": len(groups), "threshold": threshold,
        "mailings": {m: sorted(set(ps)) for m, ps in mailing_summary.items()},
        "gaps": gaps, "documents": documents,
    }


# --------------------------------------------------------------------------- #
# Content-derived naming                                                       #
# --------------------------------------------------------------------------- #

_DOCTYPE_KEYWORDS = [
    ("invoice",  ["rechnung", "invoice", "faktura"]),
    ("reminder", ["mahnung", "zahlungserinnerung", "reminder", "overdue"]),
    ("contract", ["vertrag", "contract", "vereinbarung", "agreement"]),
    ("offer",    ["angebot", "offer", "quotation", "kostenvoranschlag"]),
    ("statement",["kontoauszug", "statement", "abrechnung", "auflistung", "aufstellung"]),
    ("letter",   ["sehr geehrte", "dear ", "betreff", "schreiben"]),
]
_DATE_RX = [re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")]

def guess_doctype(text: str) -> str:
    low = (text or "").lower()
    for label, kws in _DOCTYPE_KEYWORDS:
        for kw in kws:
            if re.search(r"\b" + re.escape(kw.strip()) + r"\b", low):
                return label
    return "document"

def normalize_date(s: str) -> Optional[str]:
    if not s:
        return None
    m = _DATE_RX[0].search(s)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    m = _DATE_RX[1].search(s)
    if m:
        d, mo, y = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
        return f"{y}{mo}{d}"
    return None

def propose_filename(first: PageFeatures, group: list[PageFeatures]) -> dict:
    qr = first.qr_payload or {}
    date = (qr.get("date") and normalize_date(qr["date"])) \
        or (first.date and normalize_date(first.date)) \
        or normalize_date(first.text) or "00000000"
    sender = qr.get("sender") or first.sender or "unknown"
    # classify from the TITLE/HEADER zone first (body prose is noisy), then body
    doctype = qr.get("type") if qr.get("type") in dict(_DOCTYPE_KEYWORDS) else None
    doctype = doctype or guess_doctype((qr.get("title") or "") + " " + (first.header or ""))
    if doctype == "document":
        doctype = guess_doctype(first.text)
    span = f"p{group[0].index}-{group[-1].index}" if len(group) > 1 else f"p{group[0].index}"
    return {"filename": f"{date}_{slug(sender,24)}_{doctype}_{span}.pdf",
            "evidence": {"date": date, "sender": sender, "doctype": doctype,
                         "receiver": first.receiver, "doc_number": first.doc_number,
                         "source": "qr" if qr else "ocr"}}


# --------------------------------------------------------------------------- #
# Commercial provenance → BibTeX-like record (publisher=sender, NEW receiver)   #
# --------------------------------------------------------------------------- #

# A commercial document is a "contract" between a sender and a receiver. The
# sender is the PUBLISHER (its employees are the authors); the receiver is the
# intended audience — a field a journal name leaves implicit, explicit here.
_BIB_TYPE = {"invoice": "techreport", "reminder": "techreport", "contract": "techreport",
             "offer": "techreport", "statement": "techreport", "letter": "misc",
             "document": "misc"}

def _provenance(first: PageFeatures, ev: dict) -> dict:
    return {"sender": ev.get("sender") or "unknown", "receiver": first.receiver or "",
            "author": "", "doctype": ev.get("doctype") or "document",
            "date": ev.get("date") or "", "doc_number": ev.get("doc_number") or ""}

def to_bibtex(prov: dict, key: str = "doc") -> str:
    """Project a commercial document to a BibTeX-like record: publisher = sender,
    author = employee (if known), plus a NON-standard `receiver` field for the
    explicit intended audience. BibTeX itself round-trips back into the document."""
    year = (prov.get("date") or "")[:4]
    fields = [
        ("author", prov.get("author") or ""),
        ("title", f"{prov.get('doctype','document')} {prov.get('doc_number','')}".strip()),
        ("institution", prov.get("sender") or ""),      # the publisher / issuer
        ("publisher", prov.get("sender") or ""),
        ("year", year),
        ("date", prov.get("date") or ""),
        ("receiver", prov.get("receiver") or ""),       # NEW: explicit intended audience
        ("type", prov.get("doctype") or ""),
        ("number", prov.get("doc_number") or ""),
    ]
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields if v)
    etype = _BIB_TYPE.get(prov.get("doctype", "document"), "misc")
    return f"@{etype}{{{key},\n{body}\n}}"


# --------------------------------------------------------------------------- #
# Demo / self-test                                                             #
# --------------------------------------------------------------------------- #

def _fixture() -> list[PageFeatures]:
    inv = "rechnung acme gmbh betrag faktura kunde lieferung position summe mwst"
    con = "vertrag mueller kg paragraph klausel laufzeit kuendigung unterschrift partei"
    return [
        PageFeatures(1, text=f"Rechnung INV-2024-0042 {inv} seite 1 von 2", footer="Seite 1 von 2",
                     sender="Acme GmbH", doc_number="INV-2024-0042", date="2024-11-03", has_letterhead=True),
        PageFeatures(2, text=f"{inv} zwischensumme endbetrag seite 2 von 2", footer="Seite 2 von 2",
                     sender="Acme GmbH", doc_number="INV-2024-0042"),
        PageFeatures(3, text="Sehr geehrte Damen und Herren Betreff Stromabrechnung Stadtwerke Koeln",
                     header="Stadtwerke Koeln", sender="Stadtwerke Koeln", date="2024-11-10", has_letterhead=True),
        PageFeatures(4, text=f"Vertrag Nr VK-77 {con} 1/3", footer="1/3", sender="Mueller KG",
                     doc_number="VK-77", date="2024-09-01", has_letterhead=True),
        PageFeatures(5, text=f"{con} fortsetzung 2/3", footer="2/3", sender="Mueller KG", doc_number="VK-77"),
        PageFeatures(6, text=f"{con} schlussbestimmungen 3/3", footer="3/3", sender="Mueller KG", doc_number="VK-77"),
        PageFeatures(7, text="", is_separator=True,
                     qr_payload={"type": "offer", "title": "Angebot 2024", "sender": "Foo AG", "date": "2024-12-01"}),
        PageFeatures(8, text="Angebot fuer Dienstleistungen Foo AG Konditionen Preise",
                     sender="Foo AG", date="2024-12-01", has_letterhead=True),
    ]


if __name__ == "__main__":
    res = segment(_fixture())
    print(json.dumps({"documents": [(d["pages"], d["proposed_filename"], d["mailing"]) for d in res["documents"]],
                      "mailings": res["mailings"]}, indent=2, ensure_ascii=False))
