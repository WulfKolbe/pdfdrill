"""655 — a size budget for a built evidence/residuals PDF.

Task 654 fixed the CROP GEOMETRY; the crops it now renders correctly are, on
gilmore-lie-groups' formula evidence, 115.4 MB in one file -- over GitHub's
100 MB per-file hard limit -- and the rebuilt set across the 20 published
documents totals 1,041 MB. `report_tex.scale_crops` (task 538) already
re-encodes a directory of crops smaller and already returns each crop's
ORIGINAL pixel width so the physical size on the page does not move; it had
zero callers. This module decides, per document per KIND (one of
`gate.PUBLISHED_FILES` -- `evidence-formula.pdf`, `evidence-equation.pdf`,
`evidence-table.pdf`, `evidence-image.pdf` are each a SEPARATE file, sized
independently), WHICH rung of `scale_crops`'s ladder that document's kind
needs, by predicting real re-encoded bytes rather than rebuilding the PDF.

Model-agnostic by design, like every other module in this package except
`from_document.py`: this reads only crop FILES on disk and a list of
titles, never a `docmodel.core.Document`.
"""
from __future__ import annotations

import io
from pathlib import Path

#: 655 -- the user's own stated comfort, verbatim: "I have loaded pdf files
#: with 10-20MB without problems from Github.io". Applies per BUILT PDF, not
#: per document -- a document publishes up to five (gate.PUBLISHED_FILES).
CROP_BUDGET_MB = 20.0

#: 655 -- measured 2026-09-09 on 200 randomly sampled gilmore crops (seed
#: 654; see task-655-brief.md and out/655.txt for the full table): each
#: (scale, quality) pair and the fraction of today's bytes it produces.
#: rung 1.0 is NOT listed here -- it means "leave the originals alone" (see
#: `choose_rung`), never a recompress-only pass, so a document already under
#: budget is provably byte-identical (655 item 4).
#:
#: FLOORED at 0.42/q70. Legibility was checked BY EYE on the user's own
#: example crop (gilmore-lie-groups_FO0006, "four standard operations of
#: arithmetic") at every rung: sharp through 0.50, noticeably soft but still
#: fully readable at 0.42, degrading at 0.35 -- so 0.35 is never offered.
#: A document that cannot reach budget even at 0.42/q70 is built AT the
#: floor and reported OVER BUDGET, with its size. Never go below the floor:
#: illegible evidence is worse than a large file -- the whole point of these
#: PDFs is that a human can read the crop.
CROP_LADDER = ((0.85, 75), (0.70, 75), (0.60, 72), (0.50, 70), (0.42, 70))


def _encoded_size(path: Path, scale: float, quality: int) -> int:
    """Bytes `path` would occupy re-encoded at `scale`/`quality`, WITHOUT
    writing anything -- the search itself must not touch disk, only the
    winning rung does (via `report_tex.scale_crops`).

    A file that fails to open/encode contributes its OWN current size to
    the prediction rather than a guess at how much smaller it would get --
    conservative, not optimistic (HANDOVER-RULES §1.5: never a plausible
    default for an unknown)."""
    from PIL import Image
    try:
        with Image.open(path) as im:
            w = max(1, int(im.size[0] * scale))
            h = max(1, int(im.size[1] * scale))
            buf = io.BytesIO()
            im.convert("RGB").resize((w, h), Image.LANCZOS).save(
                buf, "JPEG", quality=quality, optimize=True)
            return buf.tell()
    except Exception:
        return path.stat().st_size


def choose_rung(src_dir: "Path | str", titles, budget_mb: float = CROP_BUDGET_MB,
                ladder=CROP_LADDER):
    """Pick the first (largest) rung whose predicted total, for exactly
    these `titles`' files under `src_dir`, lands at or under `budget_mb`.

    Returns `(scale, quality, total_bytes, over_budget)`.

    * `scale == 1.0` means "copy nothing, leave the originals as they are" --
      `total_bytes` is those files' ACTUAL size on disk today, never a
      recompress, so a document already under budget stays byte-identical
      (655 item 4). `quality` is `None` in this case: nothing is re-encoded.
    * Every smaller rung's `total_bytes` is the REAL re-encoded size of
      every one of `titles`, computed in memory (no sampling -- "you are
      writing the files anyway" only applies to the WINNING rung).
    * `over_budget` is True only when even the ladder's last (floor) rung
      does not fit; the floor is still what gets built (never go lower).
    * No files found for `titles` -> `(1.0, None, 0, False)`: nothing to
      scale is trivially "under budget".
    """
    src_dir = Path(src_dir)
    files = [f for f in (src_dir / ("%s.jpg" % t) for t in titles) if f.is_file()]
    budget = budget_mb * 1024 * 1024
    total = sum(f.stat().st_size for f in files)
    if not files or total <= budget:
        return 1.0, None, total, False
    scale = quality = None
    total_at = total
    for scale, quality in ladder:
        total_at = sum(_encoded_size(f, scale, quality) for f in files)
        if total_at <= budget:
            return scale, quality, total_at, False
    return scale, quality, total_at, True
