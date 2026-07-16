"""SCANDRILL — image/scan ingestion → optimal PDF for the pdfdrill pipeline.

Four ingestion producers (CLI find, drag/drop, camera, ADF scanner) converge on
ONE canonical artifact: a job directory with ordered page images plus an
``ingest.json`` sidecar (see :mod:`scandrill.manifest`). Processing stages are
pure transforms of that manifest; the PDF is a lossless projection of it
(:mod:`scandrill.assemble`).

The OCR/analysis functions of pdfdrill — and the parallel-dev image tools
``pylepto`` (Leptonica bindings) and ``BlobTracker`` (blobcc/cropmark/deskew) —
are used only to *prepare an optimal PDF*, never as the final deliverable. They
are reached through the adapters in :mod:`scandrill.tools`.
"""

__version__ = "0.0.1"
