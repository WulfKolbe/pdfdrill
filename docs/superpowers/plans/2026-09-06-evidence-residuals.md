# Evidence and Residuals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single accreted `report.pdf` with four per-kind evidence listings (HTML and PDF, six columns, crops for every kind including the inline formula's host line) and one `residuals` action list, gated on the measurement's timestamp rather than a PDF checksum.

**Architecture:** A new package `src/pdfdrill/reports/` holds a source-independent row model, a tiddler-backed builder (the only piece approach 3 later replaces), one crop filler, and two renderers (LaTeX and HTML) over the same rows. `evidence` and `residuals` are new handlers in `commands.py`; the old `report`, `reporttex`, `breport`, `inkreport` become aliases. `report_tex.py` keeps its cell helpers and the ink chain; nothing is copied out of it, only imported.

**Tech Stack:** Python 3 stdlib, xelatex through the existing `report_tex.compile_fixpoint`, KaTeX client-side for HTML, PIL for crops (already used), pytest.

**Spec:** `docs/superpowers/specs/2026-09-06-evidence-residuals-design.md`

## Global Constraints

- Run every test with `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q -p no:cacheprovider` (HANDOVER-RULES rule 4).
- `PYTHONPATH=src`; the import root is `src` (`from pdfdrill.reports import rows`).
- Every handler that writes beside the PDF carries `@_writes("<cmd>")` (`tests/test_doclock.py::test_every_pdf_writer_holds_the_lock`).
- New commands go into `.claude/skills/pdfdrill/commands.yaml`, then `python3 tools/skillsync.py all .`; never hand-edit generated help (`tests/test_skill_sync.py` gates drift).
- The six columns, everywhere: Identifier, Page, Conf., LaTeX source, Rendered, Image.
- A formula's Page, Conf. and Image are its HOST LINE's, and every file that shows them says so in one sentence.
- Nothing re-measures the 21 library documents in this plan. `--measure` runs the existing ink chain unchanged (measure build stays `report.pdf`; decoupling the chain from that name is deferred with inline-formula measurement).
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01APyumwvYmRdu9MNXEFEBm2`.
- No em-dashes in new user-facing prose written by this plan; existing code comments are untouched.

---

## File map

| file | responsibility |
|---|---|
| `src/pdfdrill/reports/__init__.py` | package marker, `KINDS = ("equation", "formula", "table", "image")` |
| `src/pdfdrill/reports/rows.py` | frozen dataclasses; no I/O |
| `src/pdfdrill/reports/from_tiddlers.py` | tiddlers + lines.json + ink → rows |
| `src/pdfdrill/reports/crops.py` | `ensure_crops(rows, doc_dir, pdf, bibkey, history)` fills `row.crop` |
| `src/pdfdrill/reports/tex.py` | `render_table(rows, kind, meta) -> str` LaTeX longtable |
| `src/pdfdrill/reports/html.py` | `render_page(rows, kind, meta) -> str` full HTML page |
| `src/pdfdrill/reports/evidence.py` | `build(pdf, kind, fmt, ...) -> dict` |
| `src/pdfdrill/reports/residuals.py` | `select(...) -> dict` and `build(...)` |
| `src/pdfdrill/reports/gate.py` | `timestamp_gate(doc_dir)` and `coverage_gate(doc_dir)` |
| `src/pdfdrill/commands.py` | `cmd_evidence`, `cmd_residuals`, alias notes, `publish_ready` new surface |
| `src/pdfdrill/cli.py` | `_do_evidence`, `_do_residuals`, HANDLERS entries |
| `.claude/skills/pdfdrill/commands.yaml` | two entries; "alias of" notes on four |
| `tools/publishcheck.py` | compares the five files |
| `tests/test_reports_rows.py`, `tests/test_reports_from_tiddlers.py`, `tests/test_reports_crops.py`, `tests/test_reports_tex.py`, `tests/test_reports_html.py`, `tests/test_reports_evidence.py`, `tests/test_reports_residuals.py`, `tests/test_reports_gate.py`, `tests/test_reports_aliases.py` | one test file per module |

---

### Task 1: the row model

**Files:**
- Create: `src/pdfdrill/reports/__init__.py`
- Create: `src/pdfdrill/reports/rows.py`
- Test: `tests/test_reports_rows.py`

**Interfaces:**
- Produces: `EvidenceRow`, `EquationRow`, `FormulaRow`, `TableRow`, `ImageRow`, `HostLine`, `KINDS`, `COLUMNS`, `row_kind(row) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reports_rows.py
"""The row model is source-independent: no I/O, frozen, one class per kind."""
import dataclasses

import pytest

from pdfdrill.reports import KINDS, COLUMNS
from pdfdrill.reports.rows import (EvidenceRow, EquationRow, FormulaRow,
                                   TableRow, ImageRow, HostLine, row_kind)


def test_the_six_columns_are_fixed():
    assert COLUMNS == ("Identifier", "Page", "Conf.", "LaTeX source",
                       "Rendered", "Image")
    assert KINDS == ("equation", "formula", "table", "image")


def test_rows_are_frozen():
    r = EquationRow(identifier="D_EQ0001", page="3", latex="x", eqnum="(1)")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.latex = "y"


def test_a_formula_without_a_host_line_shows_dashes():
    r = FormulaRow(identifier="D_FO0001", latex="P")
    assert r.page is None and r.confidence is None and r.crop is None
    assert r.host_line is None
    assert r.shown_page == "---"
    assert r.shown_confidence is None


def test_a_formula_with_a_host_line_shows_the_lines_values():
    h = HostLine(page=4, line_type="text", confidence=0.987,
                 region={"top_left_x": 1, "top_left_y": 2,
                         "width": 30, "height": 4})
    r = FormulaRow(identifier="D_FO0002", latex="P", host_line=h)
    assert r.shown_page == "4"
    assert r.shown_confidence == 0.987


def test_an_equation_row_carries_its_ink_code():
    r = EquationRow(identifier="D_EQ0002", page="1", latex="x",
                    confidence=0.5, ink={"flag": "weak", "code": "W|+1"})
    assert r.ink_code == "W|+1"
    assert EquationRow(identifier="D_EQ0003", latex="x").ink_code == ""


def test_row_kind_names_the_kind():
    assert row_kind(EquationRow(identifier="a", latex="")) == "equation"
    assert row_kind(FormulaRow(identifier="a", latex="")) == "formula"
    assert row_kind(TableRow(identifier="a", latex="")) == "table"
    assert row_kind(ImageRow(identifier="a", latex="")) == "image"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_rows.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError: No module named 'pdfdrill.reports'`

- [ ] **Step 3: Write the package and the model**

```python
# src/pdfdrill/reports/__init__.py
"""The report surface, redrawn (spec 2026-09-06-evidence-residuals-design).

Evidence = every LaTeX/image line of the document, one file per kind, for
lookup. Residuals = the open points only, sorted worst first. Both render
from the same row model, so HTML and PDF of one kind cannot disagree.
"""
KINDS = ("equation", "formula", "table", "image")
COLUMNS = ("Identifier", "Page", "Conf.", "LaTeX source", "Rendered", "Image")
```

```python
# src/pdfdrill/reports/rows.py
"""One frozen row per object. No I/O here: a row is what a renderer sees.

Source-independent by design. `from_tiddlers.py` builds these today; the
docmodel-fed builder of approach 3 will build the same classes, and the
renderers will not notice.
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

    @property
    def shown_page(self) -> str:
        return str(self.page) if self.page not in (None, "") else "---"

    @property
    def shown_confidence(self) -> Optional[float]:
        return self.confidence


@dataclass(frozen=True)
class EquationRow(EvidenceRow):
    eqnum: str = ""
    px_width: str = ""
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
    region: tuple = ()


@dataclass(frozen=True)
class ImageRow(EvidenceRow):
    dims: tuple = ("", "")
    region: tuple = ()
    texzip_crop: Optional[Path] = None


_KIND_OF = {EquationRow: "equation", FormulaRow: "formula",
            TableRow: "table", ImageRow: "image"}


def row_kind(row: EvidenceRow) -> str:
    return _KIND_OF[type(row)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_rows.py -q -p no:cacheprovider`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/pdfdrill/reports/__init__.py src/pdfdrill/reports/rows.py tests/test_reports_rows.py
git commit -m "reports: the row model, source-independent and frozen"
```

---

### Task 2: rows from the tiddlers

**Files:**
- Create: `src/pdfdrill/reports/from_tiddlers.py`
- Test: `tests/test_reports_from_tiddlers.py`

**Interfaces:**
- Consumes: `report_tex.rows_for(tiddlers, bibkey, refined)` (tuples: fo `(title, latex, page, punct)`, eq `(title, latex, page, num, wpx, punct, conf)`, tab `(title, latex, page, dims, region, conf)`, dia `(title, latex, page, dims, region)`), `inlinectx.attach(latexes, lines_path) -> {latex: ctx}` where ctx has `page, line_type, confidence, top_left_x, top_left_y, width, height`, `report_tex.load_ink(path) -> {id: {flag, code}}`.
- Produces: `build_rows(tiddlers, bibkey, *, lines_path=None, ink=None, refined=None) -> dict[str, list]` keyed by kind.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reports_from_tiddlers.py
import json

from pdfdrill.reports.from_tiddlers import build_rows
from pdfdrill.reports.rows import EquationRow, FormulaRow, TableRow, ImageRow

BK = "DOC"


def _tiddlers():
    return [
        {"title": "DOC_EQ0001", "latex": "a=b", "page": "2",
         "equation_number": "(1)", "width": "300", "confidence": "0.91",
         "trailing_punct": "."},
        {"title": "DOC_FO0001", "latex": "P"},
        {"title": "DOC_FO0002", "latex": "\\square"},
        {"title": "DOC_TAB0001", "mathpix_text": "\\begin{tabular}{c}1\\end{tabular}",
         "page": "5", "width": "400", "height": "80", "top_left_x": "1",
         "top_left_y": "2", "confidence": "0.7"},
        {"title": "DOC_DIA0001", "latex": "", "page": "6", "width": "100",
         "height": "50", "top_left_x": "3", "top_left_y": "4"},
        {"title": "prose", "page": "1", "text": "see {{DOC_FO0001||formula}}"},
    ]


def _lines(tmp_path):
    p = tmp_path / "DOC.lines.json"
    p.write_text(json.dumps({"pages": [
        {"lines": [{"type": "text", "text": "distribution \\(P\\) of",
                    "confidence": 0.98,
                    "region": {"top_left_x": 10, "top_left_y": 20,
                               "width": 800, "height": 40}}]}]}))
    return p


def test_every_kind_is_typed():
    rows = build_rows(_tiddlers(), BK)
    assert [type(r) for r in rows["equation"]] == [EquationRow]
    assert [type(r) for r in rows["formula"]] == [FormulaRow, FormulaRow]
    assert [type(r) for r in rows["table"]] == [TableRow]
    assert [type(r) for r in rows["image"]] == [ImageRow]


def test_equation_fields():
    (r,) = build_rows(_tiddlers(), BK)["equation"]
    assert (r.identifier, r.latex, r.page, r.eqnum, r.px_width,
            r.trailing_punct, r.confidence) == (
        "DOC_EQ0001", "a=b", "2", "(1)", "300", ".", 0.91)


def test_equation_carries_ink_when_given():
    ink = {"DOC_EQ0001": {"flag": "weak", "code": "W|+1"}}
    (r,) = build_rows(_tiddlers(), BK, ink=ink)["equation"]
    assert r.ink_code == "W|+1"


def test_formula_takes_its_host_line_from_lines_json(tmp_path):
    rows = build_rows(_tiddlers(), BK, lines_path=_lines(tmp_path))
    p, sq = rows["formula"]
    assert p.host_line.page == 1 and p.host_line.confidence == 0.98
    assert p.host_line.region == {"top_left_x": 10, "top_left_y": 20,
                                  "width": 800, "height": 40}
    assert sq.host_line is None          # \square has no span: reported, not defaulted


def test_formula_page_falls_back_to_first_transcluding_page():
    p, _ = build_rows(_tiddlers(), BK)["formula"]
    assert p.page == "1" and p.shown_page == "1"


def test_table_latex_is_mathpix_text():
    (t,) = build_rows(_tiddlers(), BK)["table"]
    assert t.latex.startswith("\\begin{tabular}")
    assert t.dims == ("400", "80") and t.confidence == 0.7


def test_missing_lines_json_is_not_an_error(tmp_path):
    rows = build_rows(_tiddlers(), BK, lines_path=tmp_path / "nope.json")
    assert all(r.host_line is None for r in rows["formula"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_from_tiddlers.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the builder**

```python
# src/pdfdrill/reports/from_tiddlers.py
"""Rows from the tiddler projection. The ONLY tiddler-aware code in the
package; approach 3 replaces this module with a docmodel-fed one.

Reuses report_tex.rows_for so the row selection cannot drift from the
report the 21 documents were built with.
"""
from __future__ import annotations

from pathlib import Path

from ..report_tex import rows_for
from .rows import (EquationRow, FormulaRow, TableRow, ImageRow, HostLine)


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _host_line(ctx: dict) -> "HostLine | None":
    if not ctx:
        return None
    region = {k: ctx[k] for k in ("top_left_x", "top_left_y", "width",
                                  "height") if k in ctx}
    return HostLine(page=ctx.get("page"), line_type=ctx.get("line_type"),
                    confidence=_float(ctx.get("confidence")), region=region)


def build_rows(tiddlers: list, bibkey: str, *, lines_path=None,
               ink: "dict | None" = None, refined=None) -> dict:
    """{kind: [rows]} in the order rows_for yields them."""
    fo, eq, tab, dia = rows_for(tiddlers, bibkey, refined)
    ink = ink or {}

    ctx: dict = {}
    if lines_path and Path(lines_path).is_file():
        from .. import inlinectx
        ctx = inlinectx.attach([r[1] for r in fo], lines_path)

    out = {"equation": [], "formula": [], "table": [], "image": []}
    for title, latex, page, num, wpx, punct, conf in eq:
        out["equation"].append(EquationRow(
            identifier=title, latex=latex, page=page or None,
            trailing_punct=punct or "", confidence=_float(conf),
            eqnum=num or "", px_width=str(wpx or ""),
            ink=ink.get(title)))
    for title, latex, page, punct in fo:
        out["formula"].append(FormulaRow(
            identifier=title, latex=latex, page=page or None,
            trailing_punct=punct or "",
            host_line=_host_line(ctx.get(latex or ""))))
    for title, latex, page, dims, region, conf in tab:
        out["table"].append(TableRow(
            identifier=title, latex=latex, page=page or None,
            confidence=_float(conf), dims=tuple(dims), region=tuple(region)))
    for title, latex, page, dims, region in dia:
        out["image"].append(ImageRow(
            identifier=title, latex=latex, page=page or None,
            dims=tuple(dims), region=tuple(region)))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_from_tiddlers.py -q -p no:cacheprovider`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/pdfdrill/reports/from_tiddlers.py tests/test_reports_from_tiddlers.py
git commit -m "reports: rows from the tiddlers, the one source-aware module"
```

---

### Task 3: crops for every kind

**Files:**
- Create: `src/pdfdrill/reports/crops.py`
- Test: `tests/test_reports_crops.py`

**Interfaces:**
- Consumes: `report_tex.download_crops(tiddlers, dest) -> (ok, cached, failed)`, `report_tex.render_crops(tiddlers, dest, pdf, kinds=(...)) -> (rendered, cached, skipped)`, `report_tex.crop_file(crops_dir, title, bibkey, history) -> Path|None`, `report_tex.find_texzip(pdf)`, `report_tex.texzip_images(dir) -> (registry, n)`.
- Produces: `ensure_crops(rows_by_kind, tiddlers, doc_dir, pdf, *, bibkey, history=None, images=True) -> (rows_by_kind, note)`; returns NEW row objects with `crop` set (rows are frozen).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reports_crops.py
import dataclasses
from pathlib import Path

import pdfdrill.reports.crops as C
from pdfdrill.reports.rows import EquationRow, FormulaRow, HostLine, TableRow


def _jpg(d: Path, name: str):
    d.mkdir(exist_ok=True)
    (d / name).write_bytes(b"\xff\xd8" + b"0" * 600)


def test_formula_crop_is_rendered_from_the_host_line_region(tmp_path, monkeypatch):
    calls = []

    def fake_render(tiddlers, dest, pdf, kinds=("_TAB",), **kw):
        calls.append((list(tiddlers), kinds))
        for t in tiddlers:
            _jpg(dest, t["title"] + ".jpg")
        return len(tiddlers), 0, 0

    monkeypatch.setattr(C.rt, "render_crops", fake_render)
    monkeypatch.setattr(C.rt, "download_crops", lambda t, d, **kw: (0, 0, 0))
    h = HostLine(page=3, confidence=0.9, region={"top_left_x": 1,
                 "top_left_y": 2, "width": 30, "height": 4})
    rows = {"equation": [], "table": [], "image": [],
            "formula": [FormulaRow(identifier="D_FO0001", latex="P", host_line=h),
                        FormulaRow(identifier="D_FO0002", latex="\\square")]}
    out, note = C.ensure_crops(rows, [], tmp_path, tmp_path / "D.pdf", bibkey="D")
    (pseudo, kinds), = [c for c in calls if "_FO" in c[1]]
    assert pseudo == [{"title": "D_FO0001", "page": "3", "top_left_x": 1,
                       "top_left_y": 2, "width": 30, "height": 4}]
    assert out["formula"][0].crop == tmp_path / "report-crops" / "D_FO0001.jpg"
    assert out["formula"][1].crop is None
    assert "1 rendered" in note


def test_equation_crops_come_from_the_cdn_download(tmp_path, monkeypatch):
    def fake_download(tiddlers, dest, **kw):
        _jpg(dest, "D_EQ0001.jpg")
        return 1, 0, 0
    monkeypatch.setattr(C.rt, "download_crops", fake_download)
    monkeypatch.setattr(C.rt, "render_crops", lambda *a, **k: (0, 0, 0))
    rows = {"equation": [EquationRow(identifier="D_EQ0001", latex="x")],
            "formula": [], "table": [], "image": []}
    out, _ = C.ensure_crops(rows, [], tmp_path, tmp_path / "D.pdf", bibkey="D")
    assert out["equation"][0].crop.name == "D_EQ0001.jpg"


def test_table_and_image_regions_are_rendered_from_the_pdf(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(C.rt, "download_crops", lambda t, d, **kw: (0, 0, 0))
    monkeypatch.setattr(C.rt, "render_crops",
                        lambda t, d, p, kinds=("_TAB",), **kw: seen.append(kinds) or (0, 0, 0))
    rows = {"equation": [], "formula": [],
            "table": [TableRow(identifier="D_TAB0001", latex="")], "image": []}
    C.ensure_crops(rows, [], tmp_path, tmp_path / "D.pdf", bibkey="D")
    assert ("_TAB", "_DIA", "_PIC") in seen


def test_images_off_leaves_every_crop_none(tmp_path):
    rows = {"equation": [EquationRow(identifier="D_EQ0001", latex="x")],
            "formula": [], "table": [], "image": []}
    out, note = C.ensure_crops(rows, [], tmp_path, tmp_path / "D.pdf",
                               bibkey="D", images=False)
    assert out["equation"][0].crop is None and note == "images: off"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_crops.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the crop filler**

```python
# src/pdfdrill/reports/crops.py
"""One entry point fills `row.crop` for every kind.

Equations: the MathPix CDN crop (download_crops, cached in report-crops/).
Tables and images: the region rendered from the PDF (render_crops, 461).
Formulas: the HOST LINE's region rendered from the PDF, exactly as the B
command did it (530), so the 15 documents that already hold FO crops build
without rendering anything.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

from .. import report_tex as rt
from .rows import FormulaRow

CROPS_DIR = "report-crops"


def _pseudo_tiddlers(formulas: list) -> list:
    out = []
    for r in formulas:
        h = r.host_line
        if h is None or h.page is None or not h.region:
            continue
        out.append(dict({"title": r.identifier, "page": str(h.page)},
                        **h.region))
    return out


def ensure_crops(rows: dict, tiddlers: list, doc_dir: Path, pdf: Path, *,
                 bibkey: str, history=None, images: bool = True):
    """Returns (rows with `crop` set, one-line note)."""
    if not images:
        return rows, "images: off"
    doc_dir = Path(doc_dir)
    crops = doc_dir / CROPS_DIR
    ok, cached, failed = rt.download_crops(tiddlers, crops)
    r_ok, r_cached, r_skip = rt.render_crops(tiddlers, crops, Path(pdf),
                                             kinds=("_TAB", "_DIA", "_PIC"))
    pseudo = _pseudo_tiddlers(rows.get("formula", []))
    f_ok = f_cached = f_skip = 0
    if pseudo:
        f_ok, f_cached, f_skip = rt.render_crops(pseudo, crops, Path(pdf),
                                                 kinds=("_FO",))
    out = {}
    for kind, lst in rows.items():
        out[kind] = [dataclasses.replace(
            r, crop=rt.crop_file(crops, r.identifier, bibkey, history))
            for r in lst]
    note = ("crops: %d fetched, %d cached, %d failed; regions %d rendered, "
            "%d cached, %d skipped; host lines %d rendered, %d cached, "
            "%d skipped" % (ok, cached, failed, r_ok, r_cached, r_skip,
                            f_ok, f_cached, f_skip))
    return out, note
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_crops.py -q -p no:cacheprovider`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/pdfdrill/reports/crops.py tests/test_reports_crops.py
git commit -m "reports: one crop filler for four kinds, host lines included"
```

---

### Task 4: the LaTeX renderer

**Files:**
- Create: `src/pdfdrill/reports/tex.py`
- Test: `tests/test_reports_tex.py`

**Interfaces:**
- Consumes: `report_tex.esc_text`, `renderable`, `breakable_ident`, `conf_cell`, `conf_flag`, `crop_cell(crops_dir, out_dir, title, px_width, px2mm, col_mm, bibkey, history)`, `col_widths(usable_mm, with_image)`, `table_open(caption, widths, form, legend_on)`, `refused_for_align_only`, `standalone_math`, `preamble(**slots)`, `unicode_decls(body)`, `MATHBB_DIGITS`, `PAPER_MM`, `pagesel_line`.
- Produces: `HOST_LINE_SENTENCE`, `widths_for(paper, landscape, with_image) -> tuple`, `render_table(rows, kind, *, widths, out_dir, px2mm, bibkey, history, caption=None, legend_on=False, form=False, ink_bullets=False) -> str`, `document(body, *, paper, landscape, pages=None, title="") -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reports_tex.py
from pathlib import Path

from pdfdrill.reports import COLUMNS
from pdfdrill.reports.rows import EquationRow, FormulaRow, HostLine, TableRow
from pdfdrill.reports import tex as T


def _jpg(d: Path, name: str):
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_bytes(b"\xff\xd8" + b"0" * 600)
    return p


def test_six_columns_for_every_kind(tmp_path):
    w = T.widths_for("a3", True, with_image=True)
    assert len(w) == 6
    body = T.render_table([EquationRow(identifier="D_EQ0001", latex="a=b",
                                       page="2", confidence=0.9)],
                          "equation", widths=w, out_dir=tmp_path, px2mm=None,
                          bibkey="D")
    for h in COLUMNS[:-1]:
        assert "\\textbf{%s}" % h in body
    assert "\\textbf{Image}" in body
    assert body.count(" & ") >= 5


def test_formula_row_shows_host_line_values_and_the_sentence(tmp_path):
    crop = _jpg(tmp_path / "report-crops", "D_FO0001.jpg")
    h = HostLine(page=4, confidence=0.98, region={"width": 800})
    r = FormulaRow(identifier="D_FO0001", latex="P", host_line=h, crop=crop)
    w = T.widths_for("a3", True, with_image=True)
    body = T.render_table([r], "formula", widths=w, out_dir=tmp_path,
                          px2mm=None, bibkey="D")
    assert T.HOST_LINE_SENTENCE in body
    assert "& 4 &" in body
    assert "\\confcell{confgreen}{0.980}" in body
    assert "report-crops/D_FO0001.jpg" in body


def test_formula_without_host_line_is_dashes(tmp_path):
    r = FormulaRow(identifier="D_FO0002", latex="\\square")
    body = T.render_table([r], "formula",
                          widths=T.widths_for("a3", True, True),
                          out_dir=tmp_path, px2mm=None, bibkey="D")
    assert "& --- & --- &" in body
    assert body.rstrip().endswith("\\end{longtable}")


def test_document_wraps_a_body_with_the_report_preamble():
    doc = T.document("BODY", paper="a3", landscape=True, pages=None,
                     title="Evidence")
    assert doc.startswith("%%") and "\\begin{document}" in doc
    assert "BODY" in doc and doc.rstrip().endswith("\\end{document}")
    assert "pagesel" not in doc
    assert "\\usepackage[1-3]{pagesel}" in T.document(
        "x", paper="a3", landscape=True, pages=3)


def test_no_legend_and_no_bullets_by_default(tmp_path):
    body = T.render_table([EquationRow(identifier="D_EQ0001", latex="x")],
                          "equation", widths=T.widths_for("a3", True, True),
                          out_dir=tmp_path, px2mm=None, bibkey="D")
    assert "\\endfoot" not in body and "\\inkbullet" not in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_tex.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the renderer**

```python
# src/pdfdrill/reports/tex.py
"""LaTeX rendering of evidence rows. Imports report_tex's cell helpers; it
copies nothing, so a fix there is a fix here."""
from __future__ import annotations

from pathlib import Path

from .. import report_tex as rt
from . import COLUMNS
from .rows import EvidenceRow, FormulaRow, EquationRow, row_kind

HOST_LINE_SENTENCE = (
    "The page, the confidence and the picture of an inline formula are its "
    "HOST LINE's --- a formula has none of its own. A line's confidence is "
    "not a formula's.")

CAPTIONS = {"equation": "Display equations",
            "formula": "Inline formulas (first occurrence)",
            "table": "Tables",
            "image": "Image regions"}


def widths_for(paper: str, landscape: bool, with_image: bool) -> tuple:
    w_mm, h_mm = rt.PAPER_MM[paper]
    if landscape:
        w_mm, h_mm = h_mm, w_mm
    return rt.col_widths(w_mm - 36, with_image=with_image)


def _open(caption: str, widths, legend_on: bool, form: bool) -> str:
    cols = "|" + "|".join("p{%smm}" % w for w in widths) + "|"
    heads = COLUMNS if len(widths) == 6 else COLUMNS[:-1]
    return ("\\section*{%s}\n" % caption +
            "\\begin{longtable}{%s}\n\\hline\n" % cols +
            " & ".join("\\textbf{%s}" % h for h in heads) +
            " \\\\\n\\hline\\endhead\n" +
            (rt.legend_foot(widths, form) if legend_on else ""))


def _rendered(r: EvidenceRow, widths) -> str:
    safe = rt.renderable(r.latex) if r.latex else ""
    tail = rt.esc_text(r.trailing_punct) if r.trailing_punct else ""
    if safe:
        return "\\FitMath{$\\displaystyle %s$}%s" % (safe, tail)
    if r.latex and rt.refused_for_align_only(r.latex):
        return rt.standalone_math(r.latex, r.identifier, Path("."),
                                  col_mm=widths[4])
    return "\\emph{(not rendered)}" if r.latex else "---"


def _conf(r: EvidenceRow, ink_bullets: bool) -> str:
    cell = rt.conf_cell(r.shown_confidence)
    if ink_bullets and isinstance(r, EquationRow):
        code = r.ink_code
        colour = rt._INK_COLOUR.get((r.ink or {}).get("flag"), "inkUnmeasured")
        txt = ("\\,\\texttt{\\tiny %s}" % rt.esc_text(code)) if code else ""
        cell = "%s\\hspace{0.6em}\\inkbullet{%s}%s" % (cell, colour, txt)
    return cell


def render_row(r: EvidenceRow, widths, *, out_dir, px2mm, bibkey,
               history=None, ink_bullets=False) -> str:
    extra = getattr(r, "eqnum", "")
    ident = "\\ident{%s}%s%s" % (
        rt.breakable_ident(r.identifier),
        ("~\\eqnum{%s}" % rt.esc_text(extra)) if extra else "",
        rt.conf_flag(r.shown_confidence))
    src = ("{\\ttfamily\\footnotesize %s}" % rt.esc_text(r.latex)
           if r.latex else "---")
    cells = [ident, rt.esc_text(r.shown_page), _conf(r, ink_bullets), src,
             _rendered(r, widths)]
    if len(widths) == 6:
        if r.crop is not None:
            cells.append(rt.crop_cell(r.crop.parent, Path(out_dir), r.crop.stem,
                                      px_width=getattr(r, "px_width", ""),
                                      px2mm=px2mm, col_mm=widths[5],
                                      bibkey=bibkey, history=history))
        else:
            cells.append("---")
    return " & ".join(cells) + " \\\\ \\hline\n"


def render_table(rows: list, kind: str, *, widths, out_dir, px2mm, bibkey,
                 history=None, caption=None, legend_on=False, form=False,
                 ink_bullets=False) -> str:
    parts = []
    if kind == "formula":
        parts.append("\\noindent{\\small %s}\\\\[.6em]\n" % HOST_LINE_SENTENCE)
    parts.append(_open(caption or CAPTIONS[kind], widths, legend_on, form))
    for r in rows:
        parts.append(render_row(r, widths, out_dir=out_dir, px2mm=px2mm,
                                bibkey=bibkey, history=history,
                                ink_bullets=ink_bullets))
    parts.append("\\end{longtable}\n")
    return "".join(parts)


def document(body: str, *, paper: str, landscape: bool, pages=None,
             title: str = "") -> str:
    geom = "%spaper%s" % (paper, ",landscape" if landscape else "")
    pre = rt.preamble(bbdigits=rt.MATHBB_DIGITS, form="", geom=geom,
                      pagesel=rt.pagesel_line(pages),
                      unicode=rt.unicode_decls(body))
    head = ("\\begin{center}{\\Large\\bfseries %s}\\end{center}\n"
            % rt.esc_text(title)) if title else ""
    return pre + head + body + "\n\\end{document}\n"
```

If `rt.unicode_decls` does not exist under that name, find the function the B command calls for the `unicode` slot (`grep -n "unicode_decls\|\"unicode\"" src/pdfdrill/commands.py src/pdfdrill/report_tex.py`) and use it.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_tex.py -q -p no:cacheprovider`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/pdfdrill/reports/tex.py tests/test_reports_tex.py
git commit -m "reports: the LaTeX renderer, six columns for every kind"
```

---

### Task 5: the HTML renderer

**Files:**
- Create: `src/pdfdrill/reports/html.py`
- Test: `tests/test_reports_html.py`

**Interfaces:**
- Consumes: `docops.katex_notice.KATEX_WARNING_HTML`, `tex.HOST_LINE_SENTENCE`, `tex.CAPTIONS`.
- Produces: `render_page(rows, kind, *, title, doc_dir, meta_lines=()) -> str` (a complete HTML document; image `src` relative to `doc_dir`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reports_html.py
from pathlib import Path

from pdfdrill.reports import COLUMNS
from pdfdrill.reports.rows import EquationRow, FormulaRow, HostLine
from pdfdrill.reports import html as H
from pdfdrill.reports.tex import HOST_LINE_SENTENCE


def test_six_columns_and_katex(tmp_path):
    page = H.render_page([EquationRow(identifier="D_EQ0001", latex="a<b",
                                      page="2", confidence=0.95)],
                         "equation", title="D", doc_dir=tmp_path)
    for h in COLUMNS:
        assert "<th>%s</th>" % h in page
    assert 'data-latex="a&lt;b"' in page and "katex.min.js" in page
    assert "KaTeX" in page                        # the caveat banner


def test_formula_row_links_the_host_line_crop_relative(tmp_path):
    crop = tmp_path / "report-crops" / "D_FO0001.jpg"
    crop.parent.mkdir()
    crop.write_bytes(b"x")
    h = HostLine(page=4, confidence=0.5, region={})
    page = H.render_page([FormulaRow(identifier="D_FO0001", latex="P",
                                     host_line=h, crop=crop)],
                         "formula", title="D", doc_dir=tmp_path)
    assert HOST_LINE_SENTENCE.replace("---", "\u2014") in page or \
        HOST_LINE_SENTENCE in page
    assert '<img src="report-crops/D_FO0001.jpg"' in page
    assert "<td>4</td>" in page and "0.500" in page


def test_missing_values_are_dashes(tmp_path):
    page = H.render_page([FormulaRow(identifier="D_FO0002", latex="")],
                         "formula", title="D", doc_dir=tmp_path)
    assert page.count("<td>---</td>") >= 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_html.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the renderer**

```python
# src/pdfdrill/reports/html.py
"""HTML rendering of evidence rows: KaTeX client-side, lazy-loaded images.

An HTML rendering is a convenience, not evidence (530): KaTeX has no
preamble. The caveat banner says so on every page.
"""
from __future__ import annotations

import html as _h
from pathlib import Path

from docops.katex_notice import KATEX_WARNING_HTML
from . import COLUMNS
from .rows import EvidenceRow, EquationRow
from .tex import CAPTIONS, HOST_LINE_SENTENCE

_KV = "0.16.11"

_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@{kv}/dist/katex.min.css">
  <script defer src="https://cdn.jsdelivr.net/npm/katex@{kv}/dist/katex.min.js"></script>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #222; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #bbb; padding: .3rem .5rem; vertical-align: top; }}
    td.src {{ font-family: ui-monospace, monospace; font-size: .8rem; white-space: pre-wrap; }}
    img {{ max-width: 100%; height: auto; }}
    .note {{ color: #555; font-size: .9rem; }}
  </style>
  <script>
    document.addEventListener("DOMContentLoaded", function () {{
      document.querySelectorAll(".math-render").forEach(function (el) {{
        try {{ katex.render(el.dataset.latex, el,
              {{ displayMode: el.dataset.display === "true", throwOnError: false }}); }}
        catch (e) {{ el.textContent = "(not rendered)"; }}
      }});
    }});
  </script>
</head>
<body>
<h1>{title}</h1>
{caveat}
{meta}
"""


def _cell(v) -> str:
    return "<td>%s</td>" % ("---" if v in (None, "") else _h.escape(str(v)))


def _conf(r: EvidenceRow) -> str:
    c = r.shown_confidence
    if c is None:
        base = "---"
    else:
        base = "%.3f" % c
    if isinstance(r, EquationRow) and r.ink_code:
        base += " <code>%s</code>" % _h.escape(r.ink_code)
    return "<td>%s</td>" % base


def _img(r: EvidenceRow, doc_dir: Path) -> str:
    if r.crop is None:
        return "<td>---</td>"
    try:
        rel = r.crop.relative_to(doc_dir)
    except ValueError:
        rel = r.crop
    return '<td><img src="%s" loading="lazy" alt="%s"></td>' % (
        _h.escape(str(rel).replace("\\", "/")), _h.escape(r.identifier))


def _row(r: EvidenceRow, doc_dir: Path, display: bool) -> str:
    latex = r.latex or ""
    rendered = ('<span class="math-render" data-latex="%s" data-display="%s"></span>'
                % (_h.escape(latex, quote=True), "true" if display else "false")
                ) if latex else "---"
    return ("<tr>%s%s%s<td class=\"src\">%s</td><td>%s</td>%s</tr>\n"
            % (_cell(r.identifier), _cell(r.shown_page), _conf(r),
               _h.escape(latex) if latex else "---", rendered,
               _img(r, doc_dir)))


def render_page(rows: list, kind: str, *, title: str, doc_dir,
                meta_lines=(), caption=None) -> str:
    doc_dir = Path(doc_dir)
    meta = "".join('<p class="note">%s</p>\n' % _h.escape(m) for m in meta_lines)
    out = [_HEAD.format(title=_h.escape(title), kv=_KV,
                        caveat=KATEX_WARNING_HTML, meta=meta)]
    out.append("<h2>%s (%d)</h2>\n" % (_h.escape(caption or CAPTIONS[kind]),
                                       len(rows)))
    if kind == "formula":
        out.append('<p class="note">%s</p>\n' % _h.escape(HOST_LINE_SENTENCE))
    out.append("<table>\n<thead><tr>%s</tr></thead>\n<tbody>\n"
               % "".join("<th>%s</th>" % c for c in COLUMNS))
    for r in rows:
        out.append(_row(r, doc_dir, display=(kind == "equation")))
    out.append("</tbody></table>\n</body></html>\n")
    return "".join(out)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_html.py -q -p no:cacheprovider`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/pdfdrill/reports/html.py tests/test_reports_html.py
git commit -m "reports: the HTML renderer over the same rows"
```

---

### Task 6: `evidence` — builder, command, manifest

**Files:**
- Create: `src/pdfdrill/reports/evidence.py`
- Modify: `src/pdfdrill/commands.py` (add `cmd_evidence` after `cmd_breport`)
- Modify: `src/pdfdrill/cli.py` (add `_do_evidence`, HANDLERS entry)
- Modify: `.claude/skills/pdfdrill/commands.yaml` (one entry)
- Test: `tests/test_reports_evidence.py`

**Interfaces:**
- Consumes: Tasks 2 to 5; `commands._resolve_tiddlers(pdf, sc, announce=False) -> (tid_path, sc, note)`, `_lines_json_path(pdf)`, `_bibkey_history(sc)`, `report_tex.resolve_bibkey(tid_path)`, `report_tex.auto_px2mm(pdf)`, `report_tex.compile_fixpoint(tex_path) -> (pages, errors, demoted) | None`, `report_tex.glyphs_dropped(log)`.
- Produces: `evidence.OUTPUT = "evidence-%s.%s"`, `evidence.build(rows_by_kind, kind, fmt, *, doc_dir, pdf, bibkey, history, px2mm, paper, landscape, compile_pdf) -> dict(out, rows, pages, errors, demoted)`, `cmd_evidence(pdf, kind=None, pdf_out=False, all_kinds=False, images=True, paper="a3", landscape=True, compile_pdf=True) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reports_evidence.py
import json
from pathlib import Path

import pytest

from pdfdrill.reports import evidence as E
from pdfdrill.reports.rows import EquationRow, FormulaRow, HostLine


def _rows():
    return {"equation": [EquationRow(identifier="D_EQ0002", latex="b", confidence=0.3),
                         EquationRow(identifier="D_EQ0001", latex="a", confidence=0.9),
                         EquationRow(identifier="D_EQ0003", latex="c")],
            "formula": [FormulaRow(identifier="D_FO0001", latex="P",
                                   host_line=HostLine(page=1, confidence=0.9))],
            "table": [], "image": []}


def test_html_output_name_and_content(tmp_path):
    r = E.build(_rows(), "formula", "html", doc_dir=tmp_path,
                pdf=tmp_path / "D.pdf", bibkey="D", history=None,
                px2mm=None, paper="a3", landscape=True, compile_pdf=False)
    assert r["out"] == tmp_path / "evidence-formula.html"
    assert "D_FO0001" in r["out"].read_text()
    assert r["rows"] == 1


def test_equations_sort_by_confidence_ascending_absent_last(tmp_path):
    r = E.build(_rows(), "equation", "html", doc_dir=tmp_path,
                pdf=tmp_path / "D.pdf", bibkey="D", history=None,
                px2mm=None, paper="a3", landscape=True, compile_pdf=False)
    body = r["out"].read_text()
    assert body.index("D_EQ0002") < body.index("D_EQ0001") < body.index("D_EQ0003")


def test_pdf_format_writes_tex_without_a_page_bound(tmp_path, monkeypatch):
    import pdfdrill.reports.evidence as mod
    monkeypatch.setattr(mod.rt, "compile_fixpoint", lambda p: (2, 0, 0))
    r = E.build(_rows(), "equation", "pdf", doc_dir=tmp_path,
                pdf=tmp_path / "D.pdf", bibkey="D", history=None,
                px2mm=None, paper="a3", landscape=True, compile_pdf=True)
    tex = (tmp_path / "evidence-equation.tex").read_text()
    assert "pagesel" not in tex and "\\inkbullet" not in tex
    assert r["pages"] == 2


def test_unknown_kind_or_format_is_refused(tmp_path):
    with pytest.raises(ValueError):
        E.build(_rows(), "prose", "html", doc_dir=tmp_path, pdf=tmp_path / "D.pdf",
                bibkey="D", history=None, px2mm=None, paper="a3",
                landscape=True, compile_pdf=False)
    with pytest.raises(ValueError):
        E.build(_rows(), "equation", "docx", doc_dir=tmp_path, pdf=tmp_path / "D.pdf",
                bibkey="D", history=None, px2mm=None, paper="a3",
                landscape=True, compile_pdf=False)


def test_cmd_evidence_is_a_locked_handler():
    import ast, inspect
    from pdfdrill import commands
    src = inspect.getsource(commands.cmd_evidence)
    fn = ast.parse(src).body[0]
    assert any(getattr(d.func, "id", "") == "_writes" for d in fn.decorator_list
               if isinstance(d, ast.Call))


def test_cli_knows_evidence():
    from pdfdrill.cli import HANDLERS
    assert "evidence" in HANDLERS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_evidence.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the builder**

```python
# src/pdfdrill/reports/evidence.py
"""Evidence = every object of one kind, unbounded, six columns. Lookup, not
reading matter. No ink, no legend, no findings, no cell-rect marks."""
from __future__ import annotations

from pathlib import Path

from .. import report_tex as rt
from . import KINDS
from . import html as H
from . import tex as T

OUTPUT = "evidence-%s.%s"
FORMATS = ("html", "pdf")


def ordered(rows: list, kind: str) -> list:
    if kind != "equation":
        return list(rows)
    return sorted(rows, key=lambda r: (r.confidence if r.confidence is not None
                                       else 2.0))


def build(rows_by_kind: dict, kind: str, fmt: str, *, doc_dir, pdf, bibkey,
          history, px2mm, paper, landscape, compile_pdf) -> dict:
    if kind not in KINDS:
        raise ValueError("kind must be one of %s, not %r" % (", ".join(KINDS), kind))
    if fmt not in FORMATS:
        raise ValueError("format must be html or pdf, not %r" % fmt)
    doc_dir = Path(doc_dir)
    rows = ordered(rows_by_kind.get(kind, []), kind)
    title = "%s: %s evidence" % (bibkey, kind)
    if fmt == "html":
        out = doc_dir / (OUTPUT % (kind, "html"))
        out.write_text(H.render_page(rows, kind, title=title, doc_dir=doc_dir,
                                     meta_lines=("%d rows" % len(rows),)),
                       encoding="utf-8")
        return {"out": out, "rows": len(rows), "pages": None, "errors": 0,
                "demoted": 0}
    widths = T.widths_for(paper, landscape, with_image=True)
    body = T.render_table(rows, kind, widths=widths, out_dir=doc_dir,
                          px2mm=px2mm, bibkey=bibkey, history=history)
    tex_path = doc_dir / (OUTPUT % (kind, "tex"))
    tex_path.write_text(T.document(body, paper=paper, landscape=landscape,
                                   pages=None, title=title), encoding="utf-8")
    res = {"out": tex_path.with_suffix(".pdf"), "rows": len(rows),
           "pages": None, "errors": 0, "demoted": 0}
    if compile_pdf:
        c = rt.compile_fixpoint(tex_path)
        if c is not None:
            res["pages"], res["errors"], res["demoted"] = c
    return res
```

- [ ] **Step 4: Write the command handler** (in `commands.py`, directly after `cmd_breport`)

```python
@_writes("evidence")
def cmd_evidence(pdf: Path, kind: "str | None" = None, pdf_out: bool = False,
                 all_kinds: bool = False, images: bool = True,
                 paper: str = "a3", landscape: bool = True,
                 compile_pdf: bool = True) -> str:
    """Evidence listing: every object of one kind in six columns, HTML by
    default, --pdf for the xelatex build through the document's own preamble.
    Inline formulas show their HOST LINE's page, confidence and picture."""
    from . import report_tex as rt
    from .reports import KINDS
    from .reports import evidence as EV
    from .reports.crops import ensure_crops
    from .reports.from_tiddlers import build_rows
    if not all_kinds and kind not in KINDS:
        return ("evidence: --kind must be one of %s (or --all-kinds)."
                % ", ".join(KINDS))
    sc = Sidecar(pdf)
    tid, sc, _note = _resolve_tiddlers(pdf, sc, announce=False)
    if tid is None:
        return (f"No tiddler array for {pdf.name} and `tiddlers` did not "
                f"produce one.")
    tiddlers = json.loads(Path(tid).read_text())
    bibkey = rt.resolve_bibkey(Path(tid))
    doc_dir = pdf.parent
    lines_path = _lines_json_path(pdf)
    ink_path = doc_dir / "report.ink.json"
    ink = rt.load_ink(ink_path) if ink_path.is_file() else {}
    rows = build_rows(tiddlers, bibkey,
                      lines_path=lines_path if lines_path.exists() else None,
                      ink=ink)
    rows, crop_note = ensure_crops(rows, tiddlers, doc_dir, pdf, bibkey=bibkey,
                                   history=_bibkey_history(sc), images=images)
    px2mm = rt.auto_px2mm(pdf)
    out = [crop_note]
    for k in (KINDS if all_kinds else (kind,)):
        r = EV.build(rows, k, "pdf" if pdf_out else "html", doc_dir=doc_dir,
                     pdf=pdf, bibkey=bibkey, history=_bibkey_history(sc),
                     px2mm=px2mm, paper=paper, landscape=landscape,
                     compile_pdf=compile_pdf)
        line = "Wrote %s: %d rows" % (r["out"], r["rows"])
        if pdf_out and r["pages"] is not None:
            line += " (%d pages, %d errors, %d demoted)" % (
                r["pages"], r["errors"], r["demoted"])
        elif pdf_out:
            line += " (xelatex not installed; .tex written)"
        out.append(line)
    sc.set_evidence("evidence_kinds", list(KINDS if all_kinds else (kind,)))
    sc.save()
    return "\n".join(out)
```

- [ ] **Step 5: Write the CLI handler** (in `cli.py`, next to `_do_breport`, and add `"evidence": _do_evidence,` to `HANDLERS`)

```python
def _do_evidence(args):
    """pdfdrill evidence <pdf> --kind equation|formula|table|image [--pdf]
    [--all-kinds] [--no-images] [--paper a4|a3] [--portrait] [--no-compile]"""
    from .commands import cmd_evidence
    kind, args = _opt(args, "--kind")
    paper, args = _opt(args, "--paper")
    pdf_args = [a for a in args if a not in ("--pdf", "--all-kinds",
                                             "--no-images", "--portrait",
                                             "--no-compile")]
    return cmd_evidence(_pdf(pdf_args), kind=kind, pdf_out="--pdf" in args,
                        all_kinds="--all-kinds" in args,
                        images="--no-images" not in args,
                        paper=paper or "a3",
                        landscape="--portrait" not in args,
                        compile_pdf="--no-compile" not in args)
```

- [ ] **Step 6: Add the manifest entry** (in `commands.yaml`, after the `breport` entry, same indentation as its neighbours)

```yaml
- name: evidence
  section: Reporting
  summary: 'EVIDENCE listing, one file per kind (evidence-<kind>.html, or .pdf with
    --pdf): every display equation, inline formula, table or image region of the
    document in six columns — Identifier, Page, Conf., LaTeX source, Rendered, Image —
    unbounded, for lookup rather than reading. Inline formulas show their HOST LINE''s
    page, confidence and picture, and the file says so. The PDF renders through the
    document''s own preamble, which is the rendering that counts as evidence; the HTML
    is KaTeX and carries the caveat. No ink, no legend, no findings: those are `residuals`.'
  offline_ok: true
  requires:
  - model
  - tiddlers
  - cdncrops
  done_when: artifact:evidence
  positionals:
  - name: pdf
    type: pdf
    required: true
    help: PDF path, https URL, or bare arXiv id
  flags:
  - name: kind
    flag: --kind
    type: str
    help: equation, formula, table or image
  - name: all_kinds
    flag: --all-kinds
    type: flag
    help: build all four kinds in one call (what publishing uses)
  - name: pdf
    flag: --pdf
    type: flag
    help: LaTeX/xelatex build instead of HTML
  - name: no_images
    flag: --no-images
    type: flag
    help: skip the Image column and every crop fetch or render
  - name: paper
    flag: --paper
    type: str
    help: a4 or a3 (default a3)
  - name: portrait
    flag: --portrait
    type: flag
    help: portrait instead of landscape
  - name: no_compile
    flag: --no-compile
    type: flag
    help: with --pdf, write the .tex without running xelatex
  typed: true
```

Then find how `done_when: artifact:<name>` resolves (`grep -n "artifact:" src/pdfdrill/planner.py`) and register `evidence` there the way `breport` is (a glob for `evidence-*.html|pdf`). Then run `python3 tools/skillsync.py all .`.

- [ ] **Step 7: Run the tests**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_evidence.py tests/test_skill_sync.py tests/test_doclock.py -q -p no:cacheprovider`
Expected: all pass

- [ ] **Step 8: Smoke it on a real document**

Run: `PDFDRILL_NO_PREFLIGHT=1 ./pdfdrill evidence ~/pdfdrill-library/2010.14265/2010.14265.pdf --kind formula --pdf`
Expected: `Wrote .../evidence-formula.pdf: 369 rows (N pages, 0 errors, ...)`, and `pdftotext evidence-formula.pdf - | head` shows the six headers and the host-line sentence. Open page 1 as an image (`pdftoppm -r 60 -f 1 -l 1 -png`) and Read it: the Image column must show a text line, not a blank.

- [ ] **Step 9: Commit**

```bash
git add src/pdfdrill/reports/evidence.py src/pdfdrill/commands.py src/pdfdrill/cli.py .claude/skills/pdfdrill/ tests/test_reports_evidence.py src/pdfdrill/planner.py
git commit -m "evidence: one listing per kind, six columns, host-line crops for formulas"
```

---

### Task 7: residuals — the selection

**Files:**
- Create: `src/pdfdrill/reports/residuals.py` (selection half)
- Test: `tests/test_reports_residuals.py`

**Interfaces:**
- Consumes: `report_tex.findings_rows(tiddlers, bibkey, doc_dir, ink, refined) -> {corrected: [pairs], unresolved: [{identifier, page, latex, why}], flagged: [{identifier, page, latex, conf, code}], doubted: [...]}`, `report_tex.flagged_split(rows) -> (shown, summary)`, `report_tex.CONF_THRESHOLD`.
- Produces: `SECTIONS = ("corrected", "unresolved", "flagged", "lowconf", "doubted")`, `select(rows_by_kind, found, *, conf=CONF_THRESHOLD) -> dict[str, list]` where every non-corrected section holds row objects from `rows_by_kind` (so crops and host lines ride along), and `corrected` holds the pairs unchanged; `select` also returns `"flagged_rest"` (the banded summary).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reports_residuals.py
from pdfdrill.reports import residuals as R
from pdfdrill.reports.rows import EquationRow, FormulaRow, HostLine


def _rows():
    return {"equation": [
                EquationRow(identifier="D_EQ0001", latex="x", confidence=0.02,
                            ink={"flag": "clean", "code": "K|0"}),      # doubted
                EquationRow(identifier="D_EQ0002", latex="y", confidence=0.95,
                            ink={"flag": "component", "code": "C|+40"}),  # flagged
                EquationRow(identifier="D_EQ0003", latex="z", confidence=0.05),  # lowconf
                EquationRow(identifier="D_EQ0004", latex="w", confidence=0.99),
                EquationRow(identifier="D_EQ0005", latex="\\bad{", confidence=0.5)],  # unresolved
            "formula": [FormulaRow(identifier="D_FO0001", latex="\\bad{",
                                   host_line=HostLine(page=1, confidence=0.01))],
            "table": [], "image": []}


def _found():
    return {"corrected": [{"identifier": "D_EQ0009", "before": "a", "after": "b"}],
            "unresolved": [{"identifier": "D_EQ0005", "page": "1", "latex": "\\bad{",
                            "why": "does not render"},
                           {"identifier": "D_FO0001", "page": "1", "latex": "\\bad{",
                            "why": "does not render"}],
            "flagged": [{"identifier": "D_EQ0002", "page": "1", "latex": "y",
                         "conf": 0.95, "code": "C|+40"}],
            "doubted": [{"identifier": "D_EQ0001", "page": "1", "latex": "x",
                         "conf": 0.02, "code": "K|0"}]}


def test_sections_in_order_and_membership():
    s = R.select(_rows(), _found(), conf=0.1)
    assert R.SECTIONS == ("corrected", "unresolved", "flagged", "lowconf", "doubted")
    assert [p["identifier"] for p in s["corrected"]] == ["D_EQ0009"]
    assert [r.identifier for r in s["unresolved"]] == ["D_FO0001", "D_EQ0005"]  # conf asc
    assert [r.identifier for r in s["flagged"]] == ["D_EQ0002"]
    assert [r.identifier for r in s["lowconf"]] == ["D_EQ0003"]
    assert [r.identifier for r in s["doubted"]] == ["D_EQ0001"]


def test_a_row_appears_in_one_section_only():
    s = R.select(_rows(), _found(), conf=0.1)
    seen = [r.identifier for k in R.SECTIONS[1:] for r in s[k]]
    assert len(seen) == len(set(seen))
    assert "D_EQ0001" not in [r.identifier for r in s["lowconf"]]   # doubted wins


def test_a_host_line_confidence_never_flags_a_formula():
    s = R.select(_rows(), _found(), conf=0.1)
    assert all(r.identifier != "D_FO0001" for r in s["lowconf"])
    assert all(r.identifier != "D_FO0001" for r in s["flagged"])


def test_unresolved_rows_keep_their_row_objects():
    s = R.select(_rows(), _found(), conf=0.1)
    fo = [r for r in s["unresolved"] if r.identifier == "D_FO0001"][0]
    assert fo.host_line.page == 1


def test_the_flagged_band_is_stated_not_listed():
    found = _found()
    found["flagged"].append({"identifier": "D_EQ0004", "page": "1", "latex": "w",
                             "conf": 0.99, "code": "W|+1"})
    s = R.select(_rows(), found, conf=0.1)
    assert [r.identifier for r in s["flagged"]] == ["D_EQ0002"]
    assert s["flagged_rest"]["n"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_residuals.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the selection**

```python
# src/pdfdrill/reports/residuals.py
"""Residuals = the open points only, worst first. What B was trying to be.

Selection reuses report_tex.findings_rows (509/513/515) so the classes the
21 documents were judged by do not change here; this module adds the
Low-confidence section and joins every selected identifier back to its row
object, so crops and host lines ride along into both renderers.
"""
from __future__ import annotations

from .. import report_tex as rt
from .rows import EquationRow

SECTIONS = ("corrected", "unresolved", "flagged", "lowconf", "doubted")
CAPTIONS = {"corrected": "Corrected",
            "unresolved": "Unresolved",
            "flagged": "Flagged, not acted on",
            "lowconf": "Low confidence",
            "doubted": "Doubted but correct"}


def _by_conf(rows):
    return sorted(rows, key=lambda r: (r.shown_confidence
                                       if r.shown_confidence is not None else 2.0))


def select(rows_by_kind: dict, found: dict, *, conf: float = rt.CONF_THRESHOLD) -> dict:
    index = {r.identifier: r for lst in rows_by_kind.values() for r in lst}
    taken = set()

    def pick(records):
        out = []
        for rec in records:
            ident = rec.get("identifier")
            r = index.get(ident)
            if r is None or ident in taken:
                continue
            taken.add(ident)
            out.append(r)
        return _by_conf(out)

    corrected = list(found.get("corrected") or [])
    taken.update(p.get("identifier") for p in corrected if p.get("identifier"))
    unresolved = pick(found.get("unresolved") or [])
    shown, rest = rt.flagged_split(found.get("flagged") or [])
    flagged = pick(shown)
    taken.update(r.get("identifier") for r in (found.get("flagged") or []))
    doubted_recs = found.get("doubted") or []
    doubted_ids = {r.get("identifier") for r in doubted_recs}
    lowconf = _by_conf([r for r in rows_by_kind.get("equation", [])
                        if isinstance(r, EquationRow)
                        and r.confidence is not None and r.confidence < conf
                        and r.identifier not in taken
                        and r.identifier not in doubted_ids])
    taken.update(r.identifier for r in lowconf)
    doubted = pick(doubted_recs)
    return {"corrected": corrected, "unresolved": unresolved,
            "flagged": flagged, "lowconf": lowconf, "doubted": doubted,
            "flagged_rest": rest}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_residuals.py -q -p no:cacheprovider`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/pdfdrill/reports/residuals.py tests/test_reports_residuals.py
git commit -m "residuals: the selection — five sections, one row in one section, worst first"
```

---

### Task 8: residuals — rendering, command, `--measure`

**Files:**
- Modify: `src/pdfdrill/reports/residuals.py` (add `build`)
- Modify: `src/pdfdrill/commands.py` (add `cmd_residuals`)
- Modify: `src/pdfdrill/cli.py` (`_do_residuals`, HANDLERS)
- Modify: `.claude/skills/pdfdrill/commands.yaml`
- Test: `tests/test_reports_residuals.py` (append)

**Interfaces:**
- Consumes: Task 7; `report_tex.findings_tex(found, widths, crops, out_dir, px2mm, bibkey, history, form, legend_on, bullets) -> str` for the Corrected pairs only; `tex.render_table` with `legend_on=True, form=True, ink_bullets=True`; `report_tex.measure_stamp(doc_dir)`; `commands.cmd_inkreport` for `--measure`.
- Produces: `residuals.OUTPUT = "residuals.%s"`, `residuals.header_lines(doc_dir) -> list[str]` (the "equations measured … against the model of …" sentence), `residuals.build(selected, fmt, *, doc_dir, pdf, bibkey, history, px2mm, paper, landscape, pages, compile_pdf) -> dict`, `cmd_residuals(pdf, pdf_out=False, measure=False, conf=None, pages=None, images=True, paper="a3", landscape=True, compile_pdf=True, timeout=900) -> str`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_reports_residuals.py`)

```python
import json


def test_header_names_the_measurement_time_and_the_model(tmp_path):
    (tmp_path / "report.ink.json").write_text(json.dumps({
        "rows": [], "measured_against": {"built_at": "2026-09-05T10:57:49Z",
                                         "model_mtime": 1788385038,
                                         "model_sha256": "abc"}}))
    lines = R.header_lines(tmp_path)
    assert any("measured 2026-09-05T10:57:49Z" in l for l in lines)
    assert any("model of 2026-09-01" in l for l in lines)


def test_header_says_so_when_nothing_was_measured(tmp_path):
    assert any("no ink measurement" in l for l in R.header_lines(tmp_path))


def test_build_html_lists_sections_worst_first(tmp_path):
    s = R.select(_rows(), _found(), conf=0.1)
    r = R.build(s, "html", doc_dir=tmp_path, pdf=tmp_path / "D.pdf", bibkey="D",
                history=None, px2mm=None, paper="a3", landscape=True,
                pages=10, compile_pdf=False)
    body = r["out"].read_text()
    assert r["out"].name == "residuals.html"
    order = [body.index(R.CAPTIONS[k]) for k in R.SECTIONS if s[k]]
    assert order == sorted(order)
    assert "1 more flagged" in body or "stated as a count" in body


def test_build_pdf_has_legend_bullets_and_a_page_bound(tmp_path, monkeypatch):
    monkeypatch.setattr(R.rt, "compile_fixpoint", lambda p: (1, 0, 0))
    monkeypatch.setattr(R.rt, "findings_tex", lambda *a, **k: "%% pairs\n")
    s = R.select(_rows(), _found(), conf=0.1)
    R.build(s, "pdf", doc_dir=tmp_path, pdf=tmp_path / "D.pdf", bibkey="D",
            history=None, px2mm=None, paper="a3", landscape=True,
            pages=10, compile_pdf=True)
    tex = (tmp_path / "residuals.tex").read_text()
    assert "\\usepackage[1-10]{pagesel}" in tex
    assert "\\endfoot" in tex and "\\inkbullet{" in tex
    assert "Low confidence" in tex


def test_cli_and_lock():
    import ast, inspect
    from pdfdrill import commands
    from pdfdrill.cli import HANDLERS
    assert "residuals" in HANDLERS
    fn = ast.parse(inspect.getsource(commands.cmd_residuals)).body[0]
    assert any(getattr(d.func, "id", "") == "_writes" for d in fn.decorator_list
               if isinstance(d, ast.Call))
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_residuals.py -q -p no:cacheprovider`
Expected: the five new tests FAIL with `AttributeError` / `KeyError`

- [ ] **Step 3: Add the rendering half** (append to `residuals.py`)

```python
import datetime as _dt
import json as _json
from pathlib import Path

from . import html as H
from . import tex as T

OUTPUT = "residuals.%s"


def _ink_meta(doc_dir) -> dict:
    p = Path(doc_dir) / "report.ink.json"
    if not p.is_file():
        return {}
    try:
        return (_json.loads(p.read_text(encoding="utf-8"))
                .get(rt.MEASURED_AGAINST) or {})
    except Exception:
        return {}


def header_lines(doc_dir) -> list:
    ma = _ink_meta(doc_dir)
    if not ma.get("built_at"):
        return ["no ink measurement for this document: the Flagged and "
                "Doubted sections cannot be filled; run `residuals --measure`"]
    mt = ma.get("model_mtime")
    when = (_dt.datetime.fromtimestamp(int(mt), _dt.timezone.utc)
            .strftime("%Y-%m-%d") if mt else "unknown date")
    return ["equations measured %s against the model of %s"
            % (ma["built_at"], when)]


def _rest_line(rest: dict) -> str:
    if not rest or not rest.get("n"):
        return ""
    return ("%d more flagged rows below the band, stated as a count: "
            "%d component, %d weak; confidence high %d, mid %d, low %d, none %d"
            % (rest["n"], rest["C"], rest["W"], rest["high"], rest["mid"],
               rest["low"], rest["none"]))


def build(selected: dict, fmt: str, *, doc_dir, pdf, bibkey, history, px2mm,
          paper, landscape, pages, compile_pdf) -> dict:
    doc_dir = Path(doc_dir)
    meta = header_lines(doc_dir)
    rest = _rest_line(selected.get("flagged_rest") or {})
    n = sum(len(selected[k]) for k in SECTIONS)
    title = "%s: residuals" % bibkey
    if fmt == "html":
        parts = []
        first = True
        for k in SECTIONS:
            if not selected[k]:
                continue
            if k == "corrected":
                rows_html = "".join(
                    "<li>%s: <code>%s</code> \u2192 <code>%s</code></li>"
                    % (H._h.escape(p.get("identifier", "")),
                       H._h.escape(p.get("before", "")),
                       H._h.escape(p.get("after", "")))
                    for p in selected[k])
                parts.append("<h2>%s (%d)</h2><ul>%s</ul>\n"
                             % (CAPTIONS[k], len(selected[k]), rows_html))
                continue
            page = H.render_page(selected[k], "equation", title=title,
                                 doc_dir=doc_dir, meta_lines=meta if first else (),
                                 caption=CAPTIONS[k])
            body = page[page.index("<h2>"):page.index("</body>")] if not first \
                else page[:page.index("</body>")]
            parts.append(body)
            if k == "flagged" and rest:
                parts.append('<p class="note">%s</p>\n' % H._h.escape(rest))
            first = False
        if not parts:
            parts.append(H.render_page([], "equation", title=title, doc_dir=doc_dir,
                                       meta_lines=meta + ["nothing open"],
                                       caption="Residuals")[:-len("</body></html>\n")])
        out = doc_dir / (OUTPUT % "html")
        out.write_text("".join(parts) + "</body></html>\n", encoding="utf-8")
        return {"out": out, "rows": n, "pages": None, "errors": 0, "demoted": 0}

    widths = T.widths_for(paper, landscape, with_image=True)
    body = ["\\noindent{\\small %s}\\\\[.6em]\n" % rt.esc_text("; ".join(meta))]
    if selected["corrected"]:
        body.append(rt.findings_tex(
            {"corrected": selected["corrected"], "unresolved": [],
             "flagged": [], "doubted": []},
            widths, crops=doc_dir / "report-crops", out_dir=doc_dir,
            px2mm=px2mm, bibkey=bibkey, history=history, form=True,
            legend_on=True, bullets=True))
    for k in SECTIONS[1:]:
        if not selected[k]:
            continue
        body.append("\\clearpage\n")
        body.append(T.render_table(selected[k], "equation", widths=widths,
                                   out_dir=doc_dir, px2mm=px2mm, bibkey=bibkey,
                                   history=history, caption=CAPTIONS[k],
                                   legend_on=True, form=True, ink_bullets=True))
        if k == "flagged" and rest:
            body.append("\\noindent{\\small %s}\n" % rt.esc_text(rest))
    if n == 0:
        body.append("\\section*{Residuals}\\noindent Nothing open.\n")
    tex_path = doc_dir / (OUTPUT % "tex")
    tex_path.write_text(T.document("".join(body), paper=paper,
                                   landscape=landscape, pages=pages, title=title),
                        encoding="utf-8")
    res = {"out": tex_path.with_suffix(".pdf"), "rows": n, "pages": None,
           "errors": 0, "demoted": 0}
    if compile_pdf:
        c = rt.compile_fixpoint(tex_path)
        if c is not None:
            res["pages"], res["errors"], res["demoted"] = c
    return res
```

`T.document` must accept the `form` slot when bullets are used: check `rt.FORM_PREAMBLE` and pass `form=rt.FORM_PREAMBLE` through `document(..., form=True)`; add a `form: bool = False` parameter to `tex.document` that fills the slot with `rt.FORM_PREAMBLE` when true (update Task 4's test expectations if the slot name differs; `grep -n '"form"' src/pdfdrill/commands.py` shows the value the reading build passes).

- [ ] **Step 4: Write the command handler** (in `commands.py`, after `cmd_evidence`)

```python
@_writes("residuals")
def cmd_residuals(pdf: Path, pdf_out: bool = False, measure: bool = False,
                  conf: "float | None" = None, pages: "int | None" = None,
                  images: bool = True, paper: str = "a3",
                  landscape: bool = True, compile_pdf: bool = True,
                  timeout: int = 900) -> str:
    """The action list: only rows with something open, worst first.
    --measure runs the ink chain first (the existing inkreport chain,
    unchanged; the measure build is still report.pdf)."""
    from . import report_tex as rt
    from .reports import residuals as RS
    from .reports.crops import ensure_crops
    from .reports.from_tiddlers import build_rows
    out = []
    if measure:
        out.append(cmd_inkreport(pdf, timeout=timeout, profile="internal",
                                 findings=False))
    sc = Sidecar(pdf)
    tid, sc, _note = _resolve_tiddlers(pdf, sc, announce=False)
    if tid is None:
        return "\n".join(out + [f"No tiddler array for {pdf.name}."])
    tiddlers = json.loads(Path(tid).read_text())
    bibkey = rt.resolve_bibkey(Path(tid))
    doc_dir = pdf.parent
    lines_path = _lines_json_path(pdf)
    ink_path = doc_dir / "report.ink.json"
    ink = rt.load_ink(ink_path) if ink_path.is_file() else {}
    rows = build_rows(tiddlers, bibkey,
                      lines_path=lines_path if lines_path.exists() else None,
                      ink=ink)
    rows, crop_note = ensure_crops(rows, tiddlers, doc_dir, pdf, bibkey=bibkey,
                                   history=_bibkey_history(sc), images=images)
    found = rt.findings_rows(tiddlers, bibkey, doc_dir, ink=ink)
    selected = RS.select(rows, found,
                         conf=conf if conf is not None else rt.CONF_THRESHOLD)
    r = RS.build(selected, "pdf" if pdf_out else "html", doc_dir=doc_dir,
                 pdf=pdf, bibkey=bibkey, history=_bibkey_history(sc),
                 px2mm=rt.auto_px2mm(pdf), paper=paper, landscape=landscape,
                 pages=(rt.PAGES_DEFAULT if pages is None else pages),
                 compile_pdf=compile_pdf)
    counts = ", ".join("%d %s" % (len(selected[k]), k) for k in RS.SECTIONS)
    out.append(crop_note)
    out.append("; ".join(RS.header_lines(doc_dir)))
    line = "Wrote %s: %d open rows (%s)" % (r["out"], r["rows"], counts)
    if pdf_out and r["pages"] is not None:
        line += " (%d pages, %d errors, %d demoted)" % (
            r["pages"], r["errors"], r["demoted"])
    out.append(line)
    sc.set_evidence("residuals_path", str(r["out"].relative_to(pdf.parent)))
    sc.save()
    return "\n".join(out)
```

Check `cmd_inkreport`'s signature before calling it (`profile`, `findings`, `timeout` exist; pass `findings=False` so the measure build is the full listing, which is what the ink must see per 585).

- [ ] **Step 5: CLI and manifest**

```python
def _do_residuals(args):
    """pdfdrill residuals <pdf> [--pdf] [--measure] [--conf F] [--pages N]
    [--no-images] [--paper a4|a3] [--portrait] [--no-compile] [--timeout S]"""
    from .commands import cmd_residuals
    conf, args = _opt(args, "--conf")
    npages, args = _opt(args, "--pages")
    paper, args = _opt(args, "--paper")
    timeout, args = _opt(args, "--timeout")
    pdf_args = [a for a in args if a not in ("--pdf", "--measure", "--no-images",
                                             "--portrait", "--no-compile")]
    return cmd_residuals(_pdf(pdf_args), pdf_out="--pdf" in args,
                         measure="--measure" in args,
                         conf=float(conf) if conf is not None else None,
                         pages=int(npages) if npages is not None else None,
                         images="--no-images" not in args,
                         paper=paper or "a3",
                         landscape="--portrait" not in args,
                         compile_pdf="--no-compile" not in args,
                         timeout=int(timeout) if timeout is not None else 900)
```

Manifest entry (after `evidence`):

```yaml
- name: residuals
  section: Reporting
  summary: 'THE ACTION LIST (residuals.html, or .pdf with --pdf): only rows with
    something open, worst first — Corrected (both readings against one scan),
    Unresolved (does not render through the document''s own preamble), Flagged
    (ink differs, banded on the component delta, the rest stated as a count), Low
    confidence (MathPix confidence under --conf, default 0.1), Doubted but correct.
    Six columns plus the ink bullet and code, legend on every page, bounded at 10
    pages. The header states WHEN the equations were measured and against which
    model. --measure runs the ink chain first (the existing inkreport chain; no
    measurement of inline formulas exists yet). Reads report.ink.json as it stands.'
  offline_ok: true
  requires:
  - model
  - tiddlers
  - cdncrops
  - inkconvert
  done_when: artifact:residuals
  positionals:
  - name: pdf
    type: pdf
    required: true
    help: PDF path, https URL, or bare arXiv id
  flags:
  - name: pdf
    flag: --pdf
    type: flag
    help: LaTeX/xelatex build instead of HTML
  - name: measure
    flag: --measure
    type: flag
    help: run the ink chain (measure build, inkdrill compare, inkconvert) before selecting
  - name: conf
    flag: --conf
    type: str
    help: Low-confidence threshold (default 0.1)
  - name: pages
    flag: --pages
    type: str
    help: emit only the first N pages of the PDF (default 10; 0 for every page)
  - name: no_images
    flag: --no-images
    type: flag
    help: skip the Image column
  - name: paper
    flag: --paper
    type: str
    help: a4 or a3 (default a3)
  - name: portrait
    flag: --portrait
    type: flag
    help: portrait instead of landscape
  - name: no_compile
    flag: --no-compile
    type: flag
    help: with --pdf, write the .tex without running xelatex
  - name: timeout
    flag: --timeout
    type: int
    help: with --measure, per-page compare timeout in seconds (default 900)
  typed: true
```

Register `artifact:residuals` in the planner beside `artifact:evidence`; run `python3 tools/skillsync.py all .`.

- [ ] **Step 6: Run the tests**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_residuals.py tests/test_skill_sync.py tests/test_doclock.py -q -p no:cacheprovider`
Expected: all pass

- [ ] **Step 7: Smoke it**

Run: `PDFDRILL_NO_PREFLIGHT=1 ./pdfdrill residuals ~/pdfdrill-library/johnston-linear-matrix-algebra/*.pdf --pdf`
Expected: a line "equations measured 2026-09-…" and counts close to today's findings (johnston reports Corrected 16, Unresolved 7, Flagged 37 in task 551). Rasterise page 1 and Read it.

- [ ] **Step 8: Commit**

```bash
git add src/pdfdrill/reports/residuals.py src/pdfdrill/reports/tex.py src/pdfdrill/commands.py src/pdfdrill/cli.py .claude/skills/pdfdrill/ src/pdfdrill/planner.py tests/test_reports_residuals.py
git commit -m "residuals: the action list, HTML and PDF, header names the measurement"
```

---

### Task 9: the timestamp gate and the new publish surface

**Files:**
- Create: `src/pdfdrill/reports/gate.py`
- Modify: `src/pdfdrill/commands.py` (`publish_ready`: new surface when `residuals.pdf` exists)
- Modify: `tools/publishcheck.py` (five files)
- Test: `tests/test_reports_gate.py`

**Interfaces:**
- Consumes: `report_tex.model_state(doc_dir) -> {model_sha256, model_bytes, model_mtime}`, `report_tex.glyphs_dropped(log)`, `inkconvert.identifiers(tex_text) -> list`, `report_tex.ROWS_MANIFEST`.
- Produces: `gate.PUBLISHED_FILES = ("evidence-equation.pdf", "evidence-formula.pdf", "evidence-table.pdf", "evidence-image.pdf", "residuals.pdf")`, `gate.timestamp_gate(doc_dir) -> (ok, detail)`, `gate.coverage_gate(doc_dir) -> (ok, detail)`, `gate.artefacts_gate(doc_dir) -> (ok, detail)`, `gate.glyphs_gate(doc_dir) -> (ok, detail)`, `gate.checklist(doc_dir) -> dict` with keys `artefacts, glyphs, ink, timestamp, coverage`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reports_gate.py
import json

from pdfdrill.reports import gate as G


def _doc(tmp_path, *, model_mtime=100, ink_mtime=100, ink_sha="S", model_sha="S",
         built_at="2026-09-05T10:57:49Z", files=G.PUBLISHED_FILES,
         glyph_loss=False, shown=("D_EQ0001", "D_EQ0002"), measured=("D_EQ0001", "D_EQ0002"),
         straddle=()):
    d = tmp_path / "D"
    d.mkdir()
    (d / "model.docmodel.json").write_text("{}")
    import os
    os.utime(d / "model.docmodel.json", (model_mtime, model_mtime))
    ma = {"built_at": built_at, "model_mtime": ink_mtime, "model_sha256": ink_sha}
    (d / "report.ink.json").write_text(json.dumps(
        {"rows": [{"id": i, "code": "K|0"} for i in measured],
         "measured_against": ma}))
    for f in files:
        (d / f).write_bytes(b"%PDF-1.4\n")
        log = "Output written on %s (1 page, 10 bytes).\n" % f
        if glyph_loss:
            log += 'Missing character: There is no g ("67) in font rsfs10!\n'
        (d / f).with_suffix(".log").write_text(log)
    (d / "residuals.tex").write_text("".join(
        "\\ident{%s} & 1 & x\n" % i for i in shown))
    (d / "pdfdrill-rows.json").write_text(json.dumps({"rows": [
        {"identifier": i, "rules_on_one_page": i not in straddle}
        for i in set(shown) | set(measured)]}))
    return d


def test_matching_model_passes(tmp_path, monkeypatch):
    d = _doc(tmp_path)
    monkeypatch.setattr(G.rt, "model_state", lambda dd: {"model_sha256": "S",
                                                         "model_mtime": 100})
    ok, detail = G.timestamp_gate(d)
    assert ok and "2026-09-05T10:57:49Z" in detail


def test_newer_model_fails_and_names_the_fix(tmp_path, monkeypatch):
    d = _doc(tmp_path, ink_mtime=100)
    monkeypatch.setattr(G.rt, "model_state", lambda dd: {"model_sha256": "T",
                                                         "model_mtime": 200})
    ok, detail = G.timestamp_gate(d)
    assert not ok and "residuals --measure" in detail


def test_no_ink_fails(tmp_path):
    d = _doc(tmp_path)
    (d / "report.ink.json").unlink()
    assert G.timestamp_gate(d)[0] is False


def test_pdf_checksum_is_never_compared(tmp_path, monkeypatch):
    d = _doc(tmp_path)
    (d / "residuals.pdf").write_bytes(b"%PDF-1.4 different\n")
    monkeypatch.setattr(G.rt, "model_state", lambda dd: {"model_sha256": "S",
                                                         "model_mtime": 100})
    assert G.timestamp_gate(d)[0]


def test_coverage_excepts_straddlers_and_refuses_unknown_rows(tmp_path):
    d = _doc(tmp_path, shown=("D_EQ0001", "D_EQ0002", "D_EQ0003"),
             measured=("D_EQ0001",), straddle=("D_EQ0002",))
    ok, detail = G.coverage_gate(d)
    assert not ok and "D_EQ0003" in detail
    d2 = _doc(tmp_path / "b", shown=("D_EQ0001", "D_EQ0002"),
              measured=("D_EQ0001",), straddle=("D_EQ0002",))
    assert G.coverage_gate(d2)[0]


def test_artefacts_and_glyphs(tmp_path):
    d = _doc(tmp_path)
    assert G.artefacts_gate(d)[0] and G.glyphs_gate(d)[0]
    (d / "evidence-table.pdf").unlink()
    ok, detail = G.artefacts_gate(d)
    assert not ok and "evidence-table.pdf" in detail
    d2 = _doc(tmp_path / "g", glyph_loss=True)
    assert G.glyphs_gate(d2)[0] is False


def test_publish_ready_uses_the_new_surface_when_residuals_exist(tmp_path, monkeypatch):
    from pdfdrill.commands import publish_ready
    d = _doc(tmp_path)
    (d / "D.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(G.rt, "model_state", lambda dd: {"model_sha256": "S",
                                                         "model_mtime": 100})
    r = publish_ready(d / "D.pdf")
    assert set(r["checks"]) >= {"artefacts", "glyphs", "ink", "timestamp", "coverage"}
    assert r["ready"], r["checks"]
```

`publish_ready` takes the PDF and derives the folder through `Sidecar(pdf).blob_dir`; if `blob_dir` is not the PDF's parent in this fixture, mirror how `tests/test_publish_ready.py::_doc` lays the folder out and adjust the fixture, not the code.

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_gate.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the gate**

```python
# src/pdfdrill/reports/gate.py
"""The publish gate for the redrawn surface.

The old gate compared the ink's PDF checksum with the measure build's, so a
layout change could never publish without re-measuring. The measurement is
about the MODEL's equations, not about a PDF: the ink records the model it
measured (sha256 and mtime, 575), and that is what is compared. The PDF
checksum is recorded and never compared.
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import report_tex as rt

PUBLISHED_FILES = ("evidence-equation.pdf", "evidence-formula.pdf",
                   "evidence-table.pdf", "evidence-image.pdf", "residuals.pdf")
FIX = "run `pdfdrill residuals --measure --pdf <pdf>`"


def _ink(doc_dir: Path) -> dict:
    p = Path(doc_dir) / "report.ink.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def timestamp_gate(doc_dir) -> tuple:
    doc_dir = Path(doc_dir)
    ink = _ink(doc_dir)
    if not ink:
        return False, "no report.ink.json; %s" % FIX
    ma = ink.get(rt.MEASURED_AGAINST) or {}
    if not ma.get("built_at"):
        return False, "the ink does not say when it was measured; %s" % FIX
    live = rt.model_state(doc_dir)
    same_sha = (ma.get("model_sha256") and live.get("model_sha256")
                and ma["model_sha256"] == live["model_sha256"])
    if same_sha:
        return True, "measured %s against the model on disk" % ma["built_at"]
    try:
        older = int(live.get("model_mtime") or 0) > int(ma.get("model_mtime") or 0)
    except (TypeError, ValueError):
        older = True
    if older:
        return False, ("measured %s, but the model was rebuilt since (model "
                       "mtime %s > measured %s); %s"
                       % (ma["built_at"], live.get("model_mtime"),
                          ma.get("model_mtime"), FIX))
    return True, ("measured %s; model sha differs but is not newer (mtime %s)"
                  % (ma["built_at"], live.get("model_mtime")))


def coverage_gate(doc_dir) -> tuple:
    doc_dir = Path(doc_dir)
    tex = doc_dir / "residuals.tex"
    if not tex.is_file():
        return False, "no residuals.tex to read row identifiers from"
    from ..inkconvert import identifiers
    shown = {i for i in identifiers(tex.read_text(encoding="utf-8", errors="replace"))
             if "_EQ" in i}
    measured = {r.get("id") for r in (_ink(doc_dir).get("rows") or []) if r.get("id")}
    straddle = set()
    mf = doc_dir / rt.ROWS_MANIFEST
    if mf.is_file():
        try:
            straddle = {r["identifier"] for r in
                        (json.loads(mf.read_text(encoding="utf-8")).get("rows") or [])
                        if not r.get("rules_on_one_page", True)}
        except Exception:
            straddle = set()
    gone = sorted((shown - measured) - straddle)
    if gone:
        return False, ("%d equation row(s) shown carry no measurement and do not "
                       "straddle a page: %s" % (len(gone), ", ".join(gone[:8])))
    return True, "%d equation rows shown, all measured (%d straddle)" % (
        len(shown), len(shown & straddle))


def artefacts_gate(doc_dir) -> tuple:
    missing = [f for f in PUBLISHED_FILES
               if not (Path(doc_dir) / f).is_file()
               or (Path(doc_dir) / f).stat().st_size == 0]
    if missing:
        return False, "missing: %s" % ", ".join(missing)
    return True, "all five present"


def glyphs_gate(doc_dir) -> tuple:
    bad = []
    for f in PUBLISHED_FILES:
        log = (Path(doc_dir) / f).with_suffix(".log")
        if not log.is_file():
            bad.append("%s: no log" % f)
            continue
        lost = rt.glyphs_dropped(log)
        if lost is not None:
            bad.append("%s: %d dropped" % (f, lost[0]))
    return (not bad), ("clean" if not bad else "; ".join(bad))


def checklist(doc_dir) -> dict:
    doc_dir = Path(doc_dir)
    ink_p = doc_dir / "report.ink.json"
    live = [n for n in ("report.ink.json.REFUSED", "report.ink.json.MISPAIRED")
            if (doc_dir / n).is_file() and ink_p.is_file()
            and (doc_dir / n).stat().st_mtime >= ink_p.stat().st_mtime]
    return {
        "artefacts": artefacts_gate(doc_dir),
        "glyphs": glyphs_gate(doc_dir),
        "ink": ((ink_p.is_file() and not live),
                "present" if ink_p.is_file() and not live else
                ("%s is newer: the last attempt failed to pair" % live[0]
                 if live else "no report.ink.json")),
        "timestamp": timestamp_gate(doc_dir),
        "coverage": coverage_gate(doc_dir),
    }
```

- [ ] **Step 4: Wire `publish_ready`**

At the top of `publish_ready` in `commands.py`, right after `d = sc.blob_dir`, add:

```python
    # the redrawn surface (spec 2026-09-06): when residuals.pdf exists the
    # five-file checklist applies and the report.pdf checklist below is the
    # legacy path kept for documents not yet rebuilt.
    if (d / "residuals.pdf").is_file():
        from .reports import gate as G
        checks = G.checklist(d)
        fields = {"bibkey": sc.get_evidence("bibkey") or pdf.stem,
                  "folder": d.name, "pages": None, "equations": None,
                  "residual": None, "refined_rows": 0}
        return {"ready": all(v[0] for v in checks.values()),
                "checks": checks, "fields": fields}
```

Then make `cmd_publishready` iterate `r["checks"]` in insertion order instead of `PUBLISH_CHECKS` (both surfaces then print), keeping the `handover:` line guarded by `f.get("pages") is not None`.

- [ ] **Step 5: `tools/publishcheck.py`**

Where it hashes `report.pdf` per document, hash every name in `gate.PUBLISHED_FILES` that exists locally and compare each; a document is "identical" only when all present files match, and the listing names the file that differs. Keep the exit-code contract (0 only when everything matches). Import with `sys.path.insert(0, "src")` as the tool already does for other imports, or duplicate the five names in a constant with a comment naming `gate.PUBLISHED_FILES` as the source.

- [ ] **Step 6: Run the tests**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_gate.py tests/test_publish_ready.py -q -p no:cacheprovider`
Expected: all pass (the legacy tests still hit the old path since their fixture has no `residuals.pdf`)

- [ ] **Step 7: Commit**

```bash
git add src/pdfdrill/reports/gate.py src/pdfdrill/commands.py tools/publishcheck.py tests/test_reports_gate.py
git commit -m "gate: the measurement is about the model, not a PDF — timestamp and sha, never the checksum"
```

---

### Task 10: aliases

**Files:**
- Modify: `src/pdfdrill/commands.py` (`cmd_report`, `cmd_reporttex`, `cmd_breport`, `cmd_inkreport`)
- Modify: `.claude/skills/pdfdrill/commands.yaml` (four summaries gain a leading "ALIAS of …" sentence)
- Test: `tests/test_reports_aliases.py`

**Interfaces:**
- Produces: `commands.ALIASES = {"report": "evidence --kind formula / --kind equation", "reporttex": "evidence --all-kinds --pdf", "breport": "residuals --pdf", "inkreport": "residuals --measure --pdf"}`, `commands.alias_note(name) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reports_aliases.py
import yaml

from pdfdrill import commands as C


def test_alias_table_names_the_four():
    assert set(C.ALIASES) == {"report", "reporttex", "breport", "inkreport"}
    assert C.alias_note("breport").startswith("breport is an alias of residuals --pdf")


def test_manifest_summaries_say_alias_of():
    d = yaml.safe_load(open(".claude/skills/pdfdrill/commands.yaml"))
    by = {c["name"]: c for c in d["commands"]}
    for name, target in C.ALIASES.items():
        assert by[name]["summary"].startswith("ALIAS of %s" % target.split(" /")[0]), name


def test_report_alias_writes_the_old_file_name(tmp_path, monkeypatch):
    """`report` used to write formula-report.html; keep that name as a copy."""
    import pdfdrill.commands as mod
    calls = []
    monkeypatch.setattr(mod, "cmd_evidence",
                        lambda pdf, **kw: calls.append(kw) or "ok")
    (tmp_path / "evidence-formula.html").write_text("<html>")
    (tmp_path / "D.pdf").write_bytes(b"%PDF-1.4\n")
    out = mod.cmd_report(tmp_path / "D.pdf")
    assert [c["kind"] for c in calls] == ["formula", "equation"]
    assert (tmp_path / "formula-report.html").read_text() == "<html>"
    assert "alias" in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_reports_aliases.py -q -p no:cacheprovider`
Expected: FAIL with `AttributeError: ALIASES`

- [ ] **Step 3: Implement**

Add near the top of `commands.py` (after `PUBLISH_CHECKS`):

```python
#: spec 2026-09-06 — the old report commands are thin aliases; removal is a
#: later task. Each prints one line naming what it ran.
ALIASES = {"report": "evidence --kind formula / --kind equation",
           "reporttex": "evidence --all-kinds --pdf",
           "breport": "residuals --pdf",
           "inkreport": "residuals --measure --pdf"}


def alias_note(name: str) -> str:
    return "%s is an alias of %s (spec 2026-09-06); the new command is the code path." % (
        name, ALIASES[name])
```

Replace the BODY of `cmd_report` with:

```python
    import shutil as _sh
    out = [cmd_evidence(pdf, kind="formula", pdf_out=False),
           cmd_evidence(pdf, kind="equation", pdf_out=False)]
    src = pdf.parent / "evidence-formula.html"
    if src.is_file():
        _sh.copyfile(src, pdf.parent / "formula-report.html")
        out.append("formula-report.html kept as a copy of evidence-formula.html")
    out.append(alias_note("report"))
    return "\n".join(out)
```

Keep `cmd_report`'s signature and decorator; ignore its old parameters (`force`, `embed`, …) in the body but leave them in the signature so the CLI keeps parsing. Do the same for `cmd_reporttex` → `cmd_evidence(pdf, all_kinds=True, pdf_out=True, paper=paper, landscape=landscape, compile_pdf=compile_pdf, images=images)`; `cmd_breport` → `cmd_residuals(pdf, pdf_out=True, paper=paper, landscape=landscape, compile_pdf=compile_pdf, images=images, pages=pages)`; `cmd_inkreport` → `cmd_residuals(pdf, pdf_out=True, measure=True, timeout=timeout)` **but only when called from the CLI**: `cmd_residuals --measure` itself calls the original chain, so rename the original to `_inkreport_chain` and have `cmd_inkreport` call `cmd_residuals(..., measure=True)` while `cmd_residuals` calls `_inkreport_chain`. Existing tests that call `cmd_inkreport` directly (`tests/test_inkreport*.py`) must be re-pointed at `_inkreport_chain` where they assert on its step output.

In `commands.yaml`, prefix each of the four summaries with `ALIAS of <target>. ` (target = the first alternative in `ALIASES`), then `python3 tools/skillsync.py all .`.

- [ ] **Step 4: Run the whole suite**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/ -q -p no:cacheprovider`
Expected: everything passes. Tests of the old bodies (`tests/test_report.py`, `tests/test_report_filters.py`, `tests/test_reporttex_ink_adopt.py`, `tests/test_inkreport*.py`) will need their expectations re-pointed at the new outputs or at `_inkreport_chain`; list each change in the commit message. A test that asserted the old five-column formulas table is deleted with a one-line note, not kept failing.

- [ ] **Step 5: Commit**

```bash
git add -A src/pdfdrill/commands.py .claude/skills/pdfdrill/ tests/
git commit -m "aliases: report, reporttex, breport, inkreport route to evidence and residuals"
```

---

### Task 11: rollout on the 21 and the site

**Files:**
- Create: `~/pdfdrill-library/out/634/script.py`, `counts.json`, `INSPECT.txt` (library, not repo)
- Create: `out/634.txt` (repo)
- Modify: `docs/HANDOVER.md`, `docs/superpowers/specs/2026-09-06-evidence-residuals-design.md` (note the `--measure` deferral)

- [ ] **Step 1: Build**

```python
# ~/pdfdrill-library/out/634/script.py
"""634 — build the five files for the 21 published documents; no measurement."""
import json, os, subprocess, sys, time
from pathlib import Path
LIB = Path.home() / "pdfdrill-library"
docs = json.load(open(LIB / "out" / "documents.json"))
env = dict(os.environ, PDFDRILL_NO_PREFLIGHT="1", PYTHONPATH="src")
counts = {}
for key, pdf in docs.items():
    if not pdf:
        continue
    t0 = time.time()
    r1 = subprocess.run([sys.executable, "-m", "pdfdrill", "evidence", pdf,
                         "--all-kinds", "--pdf"], env=env, capture_output=True,
                        text=True, cwd=Path.home() / "MX" / "PDFDRILL")
    r2 = subprocess.run([sys.executable, "-m", "pdfdrill", "residuals", pdf,
                         "--pdf"], env=env, capture_output=True, text=True,
                        cwd=Path.home() / "MX" / "PDFDRILL")
    r3 = subprocess.run([sys.executable, "-m", "pdfdrill", "publishready", pdf],
                        env=env, capture_output=True, text=True,
                        cwd=Path.home() / "MX" / "PDFDRILL")
    counts[key] = {"evidence": r1.stdout, "residuals": r2.stdout,
                   "publishready": r3.stdout, "seconds": round(time.time() - t0)}
    print(key, counts[key]["seconds"], "s", flush=True)
json.dump(counts, open(Path(__file__).parent / "counts.json", "w"), indent=1)
```

Run it with `run_in_background` and a long timeout; it compiles roughly 100 PDFs. Do NOT run `--measure`.

- [ ] **Step 2: Compare row counts**

For each document, the equation row count in `evidence-equation.pdf` must equal today's `equations_table(doc).rows` from `report.tables.json`, and the formula row count must equal the `pdfdrill-rows.json` FO count from the measure build. Write the comparison into `counts.json` under `"check"`; any mismatch is a FINDING (rule 12) to be explained in `out/634.txt` before publishing.

- [ ] **Step 3: INSPECT.txt and out/634.txt**

Use `pdfdrill.taskout.inspect_list(target, 634, [(path, reason), ...])` for: three `evidence-formula.pdf` (2010.14265, 0902.0431, kohlhase-omdoc), three `residuals.pdf` (johnston, penev_A, 0707.4470), `counts.json`. Print `taskout.inspect_report(...)`. `out/634.txt` states: what was built, the counts table, the publishready result per document (expect penev_A to fail the ink check as before), what was not done (no measurement).

- [ ] **Step 4: Publish**

Run `python3 tools/publishcheck.py --list ~/pdfdrill-library/out/documents.json` (expect every document "not published" for the new names). Then the existing publish path for the site (`tools/publishsite.sh` or whatever `docs/HANDOVER.md` names; read it first) copying the five files per document; update the site's per-document `index.html` to link the five. Push, then `git -C <site clone> ls-remote origin` to verify. Re-run `publishcheck` and expect 0 stale for documents that passed `publishready`.

- [ ] **Step 5: HANDOVER and spec note**

In `docs/HANDOVER.md` replace the "measurement chain" block's phase-2 line with the new surface (five files, `residuals`, timestamp gate) and add under "Next task": **approach 3, `from_document.py` fed by the docmodel through docops projectors** as the agreed next step; inline-formula measurement still unstarted. In the spec, under "Commands", add: "Implemented: `--measure` runs the existing chain against `report.pdf`; the evidence-equation measure build is deferred with inline-formula measurement."

- [ ] **Step 6: Commit and push**

```bash
git add out/634.txt docs/HANDOVER.md docs/superpowers/specs/2026-09-06-evidence-residuals-design.md
git commit -m "634: the 21 rebuilt on the evidence/residuals surface, no measurement; site updated"
git push && git ls-remote origin | grep eqblobs-and-gzip-tex
```
