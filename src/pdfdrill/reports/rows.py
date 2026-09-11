"""One frozen row per object. No I/O here: a row is what a renderer sees.

Source-independent by design. `from_document.py` builds these from the
`docmodel.core.Document`; the renderers do not know or care.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class HostLine:
    """The line an inline formula was printed in. Its values, not the
    formula's: a line's confidence is not a formula's (inlinectx, 147)."""
    page: Optional[int] = None
    line_type: Optional[str] = None
    confidence: Optional[float] = None
    region: dict = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceRow:
    identifier: str
    latex: str = ""
    page: Optional[str] = None
    trailing_punct: str = ""
    confidence: Optional[float] = None
    crop: Optional[Path] = None
    notes: tuple = ()
    cdn_url: str = ""
    region: dict = field(default_factory=dict)
    #: 655 -- an EXPLICIT width WINS over the crop file's own (crop_cell,
    #: report_tex.py:712). Was EquationRow-only (538); every row kind can
    #: now be routed through `reports.budget`'s scaled copies, so every kind
    #: needs somewhere to carry the ORIGINAL pixel width forward.
    px_width: str = ""
    #: 669 -- set only when `latex` is a VERIFIED refinement (`refine.
    #: REFINED_FIELD`) that `from_document._chosen_reading` preferred over
    #: MathPix's own reading, because the raw did not survive
    #: `report_tex.display_safe` and the refined one did. Shaped like
    #: `refine.chosen_latex`'s VERIFIED evidence dict (`basis`,
    #: `verified_by`, `author`, `original`, `evidence`) so the existing
    #: `report_tex.refined_flag`/`refined_note` (233, the retired path's
    #: own mechanism for this) can be reused here unchanged. None on every
    #: other row -- no behaviour change for the population this does not
    #: touch.
    refined_info: "dict | None" = None

    @property
    def shown_page(self) -> str:
        return str(self.page) if self.page not in (None, "") else "---"

    @property
    def shown_confidence(self) -> Optional[float]:
        return self.confidence


@dataclass(frozen=True)
class EquationRow(EvidenceRow):
    eqnum: str = ""
    ink: Optional[dict] = None

    @property
    def ink_code(self) -> str:
        return str((self.ink or {}).get("code") or "")


@dataclass(frozen=True)
class FormulaRow(EvidenceRow):
    host_line: Optional[HostLine] = None

    @property
    def shown_page(self) -> str:
        if self.host_line and self.host_line.page is not None:
            return str(self.host_line.page)
        return super().shown_page

    @property
    def shown_confidence(self) -> Optional[float]:
        if self.host_line:
            return self.host_line.confidence
        return None


@dataclass(frozen=True)
class TableRow(EvidenceRow):
    dims: tuple = ("", "")


@dataclass(frozen=True)
class ImageRow(EvidenceRow):
    dims: tuple = ("", "")
    texzip_crop: Optional[Path] = None


_KIND_OF = {EquationRow: "equation", FormulaRow: "formula",
            TableRow: "table", ImageRow: "image"}


def row_kind(row: EvidenceRow) -> str:
    return _KIND_OF[type(row)]
