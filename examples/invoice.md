# Example — a commercial document (invoice / letter / scanned bundle)

Commercial docs are a sender↔receiver contract with structured facts (IBAN, VAT,
addresses, dates) and often a scanned, multi-document bundle. pdfdrill extracts the
facts and builds an evidence-backed entity graph — keyless, offline.

```bash
pdfdrill size      invoice.pdf                # scan? → needs_ocr
pdfdrill ocr       invoice.pdf --lang deu+eng # keyless OCR → lines.json (a scan)
pdfdrill entities  invoice.pdf               # IBAN (mod-97) / BIC / address / tax-id
pdfdrill qr        invoice.pdf               # GiroCode/EPC + DataMatrix franking codes
pdfdrill semantic  invoice.pdf --store graph.json   # entity/relation graph;
                                             #   --store accumulates ACROSS documents
```

A scanned bundle of several shuffled documents:

```bash
pdfdrill autosegment bundle.pdf              # picks: ordered stack vs shuffled bundle
pdfdrill segment     bundle.pdf              # group by sender/admin-id signature
pdfdrill continuity  bundle.pdf              # margin "Seite N von M" markers (page-order)
```

**Why not read it yourself:** an IBAN checksum, a GiroCode creditor, or a
"Fortsetzung Seite N" continuity marker in the margin are exactly what a plain-text
read drops. `entities`/`qr`/`continuity` recover them deterministically; `semantic`
turns them into a graph where a Company accumulates evidence across many documents.

**Gotcha:** `qr` needs the `[qr]` extra (zxing-cpp); `semantic` runs keyless. A
GiroCode often supplies the issuer the OCR text omits — `semantic` folds it in.
