# pdfdrill — change request: make multi-document scan triage solvable by an LLM

> **Status: implemented** (all four items). See the *Implementation status*
> section at the end for commands, results on the test file, and commits.

## Context

This came out of an **LLM-usability test**, not a feature wishlist. The task
given to an LLM:

> "Here is a 45-page scanned PDF that is several separate German documents in
> unknown/shuffled order (duplex scan, blank backs removed). Find the address
> and bank-account data, and organize the documents using the continuity number
> printed on each page."

Test file: `~/WKprivate/Scanned/ocrtest.pdf` (45 pp, scanned, no text layer;
MathPix `ocrtest.lines.json` already present).

Result: the LLM **could not** solve it with pdfdrill commands alone and was
forced outside the tool (pdftoppm + tesseract on page strips, schwifty/stdnum,
custom regex). Every such workaround = a pdfdrill gap below.

**Root cause:** pdfdrill is MathPix-centric, and MathPix crops to the main
content block, so the continuity numbers — which in German documents sit in the
**margin, outside the normal print area** ("Seite N von M", Druck-/
Kontrollnummern) — are dropped or misfiled as footnotes/sidenotes. That is the
exact signal the task depends on.

Conceptual reference for the structure approach: arXiv 1904.12577 (Holeček et
al., "Table understanding in structured documents") — graph nodes with
geometric-neighbor edges; the same idea applies to locating margin tokens and
segmenting a bundle.

---

## ISSUE 1 (BUG/FEATURE, highest) — margin-aware OCR + continuity extraction

**Problem.** The page/continuity numbers are invisible to an LLM driving
pdfdrill.

**Evidence (ocrtest.pdf).** `pdfdrill model` builds ~41 Sidenotes; the few
continuity numbers that survived landed there (e.g. p31 held a "Fortsetzung
Seite 2"), and most were dropped. Rendering each page and running tesseract over
the **full page including margins** (outside the text column) recovers
"Seite N von M" / "Fortsetzung Seite N" — proving the data is on the page but
not in what MathPix returns.

**Root cause.** No pdfdrill path OCRs the page **margins**; `model` reads the
content-cropped lines.json, and nothing classifies a "page/continuity number".

**Proposed.** New command `pdfdrill continuity <pdf>`:
- Render each page, run tesseract over the **full page including margins**.
- Classify margin tokens: page-sequence (`Seite N von M`, `Fortsetzung Seite N`,
  bare `Seite N`) and free control numbers (Druck-/Kontrollnummer).
- Return prose per page (`p14: "Seite 2 von 6" | …`).

**Where.** `src/pdfdrill/commands.py` (`cmd_continuity`); reuse the page-render +
tesseract plumbing behind `ocr`/`geometry`. Do NOT route through the MathPix
content crop.

**Acceptance.** `pdfdrill continuity` recovers the continuity markers that
exist, each tagged with its page and margin position, using no external tools.

---

## ISSUE 2 (FEATURE, high) — page-sequence as first-class Page metadata

**Problem.** Even when "Seite N von M" is detected, it disappears into Sidenote/
Footnote objects instead of describing the page.

**Proposed.** Parse page-sequence markers (from Issue 1's margin OCR) and attach
to the `Page` object: `seq_in_doc`, `doc_total`, `control_no`, `is_continuation`
(footer "Fortsetzung"). Surface via `status` and `model`. Convention: header
`Seite N` = this page's number; footer `Fortsetzung Seite N` = next page.

**Acceptance.** `pdfdrill status ocrtest.pdf` reports per-page `seq_in_doc` /
`doc_total`.

---

## ISSUE 3 (FEATURE, high) — bundle segmentation (1 scan → N ordered docs)

**Problem.** pdfdrill builds ONE `Document` from the whole scan; the bundle is
several distinct documents (Finanzamt Einkommensteuerbescheid, Stadt Köln
Mahnung, BB-Solartechnik/Burkhardt invoices) with duplicate copies and there was
no pdfdrill way to group/order them.

**Proposed.** New `pdfdrill segment <pdf>`. Partition pages into ordered
documents using, in priority:
1. page-number resets — `Seite 1 von M` opens a document;
2. sender/letterhead change;
3. shared identifier (Steuernummer, Kassenzeichen, …).

Detect duplicate copies. Handle the duplex/blank-back case implicitly by
ordering on the continuity number (physical order is irrelevant). Output a prose
manifest:

```
Doc 1 — Finanzamt EStBescheid (Steuernummer 204/5189/1009), 11 pp: p14,p42,…  [dup: p17]
Doc 2 — Stadt Köln Mahnung (Kassenzeichen 725.356.194.433), 2 pp: p22,p31
Doc 3 — Burkhardt Kundendienst GmbH, 6 pp: p21,p20,…  [dup: p26,p36]
```

**Acceptance.** On ocrtest.pdf, `segment` returns the three senders as separate,
page-ordered documents with duplicates flagged.

---

## ISSUE 4 (FEATURE, medium) — built-in entity extraction (IBAN/BIC/address/IDs)

**Problem.** The model exposes raw text only, so the LLM wrote IBAN/BIC regex
and pulled in schwifty/stdnum to validate.

**Proposed.** New `pdfdrill entities <pdf>`: emit, per page —
- **IBAN** (checksum-validated; derive bank name + Konto/BLZ internally),
  **BIC**, German **postal address** block, **Kassenzeichen/Aktenzeichen/
  Steuernummer**, amounts, dates.

Validation must be self-contained (no runtime pip dep); a small bundled IBAN
checksum is enough.

**Acceptance.** On ocrtest.pdf, `entities` returns the IBANs (valid; banks
named — Kreissparkasse Köln, Sparkasse KölnBonn, Raiffeisenbank …) and the
recipient address (Wulf Kolbe, Rotkäppchenweg 1, 51515 Kürten), with no external
tools.

---

## Target end-to-end LLM flow (after the changes)

```
pdfdrill continuity ocrtest.pdf   # per-page Seite N + control no.
pdfdrill segment    ocrtest.pdf   # ordered documents, duplicates flagged
pdfdrill entities   ocrtest.pdf   # validated IBANs + address + IDs
```

…and the LLM answers the task from prose alone — zero external tools.

Priority: #1 and #2 first (the actual blocker), then #3, then #4.

---

## Implementation status (delivered)

All four items are implemented, tested, and verified on `ocrtest.pdf` with no
external tools.

| # | Command | Module | Result on ocrtest.pdf |
|---|---------|--------|-----------------------|
| 1 | `pdfdrill continuity` | `src/pdfdrill/continuity.py` | 19/45 pages carry a continuity marker (13 `Seite N` + 6 `Fortsetzung`), incl. margin-only ones MathPix's crop drops |
| 2 | continuity → `Page` + `status` | `commands.cmd_continuity` | `seq_in_doc`/`doc_total`/`is_continuation`/`control_no` on every Page; listed by `pdfdrill status` |
| 3 | `pdfdrill segment` | `src/pdfdrill/segment.py` | three senders separated + page-ordered with dups flagged (Finanzamt / Burkhardt Kundendienst GmbH / Stadt Köln) |
| 4 | `pdfdrill entities` | `features/extract_iban\|bic\|german_address\|ids` | 16/17 IBANs checksum-valid (built-in mod-97) + BLZ/Konto + bank name; recipient address `Rotkäppchenweg 1, 51515 Kürten`; Kassenzeichen 725.356.194.433 |

Tests: `tests/test_continuity.py`, `tests/test_entities.py`,
`tests/test_segment.py` (+ the `features` extractors in `tests/test_features.py`).

**Honest caveat on the Issue-1 metric.** The original brief floated "≥90% of
pages carry a Seite N". That is not achievable for this file and is not the real
target: only ~18–19 of the 45 pages actually *have* a continuity marker — the
rest are genuine single-page documents. The delivered value is recovering the
**margin** markers MathPix loses (which the content crop drops), not a
percentage-of-all-pages figure. The numbers above are reported truthfully rather
than tuned to a target.
