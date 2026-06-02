"""pdfdrill commands — each does one cheap thing, returns prose.

Every command:
1. Opens the sidecar (creates if needed)
2. Checks if the work is already done (idempotent)
3. Runs the minimum needed subprocess/extraction
4. Appends to sidecar with transition log
5. Returns a human-readable prose string
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

from .sidecar import Sidecar


# ---------------------------------------------------------------------------
# Fact constants
# ---------------------------------------------------------------------------

SIZE_KNOWN = "SIZE_KNOWN"
FONTS_KNOWN = "FONTS_KNOWN"
TOC_KNOWN = "TOC_KNOWN"
TOC_ABSENT = "TOC_ABSENT"
ABSTRACT_KNOWN = "ABSTRACT_KNOWN"
ABSTRACT_ABSENT = "ABSTRACT_ABSENT"
MD_BUILT = "MD_BUILT"
MMD_BUILT = "MMD_BUILT"
PDFINFO_KNOWN = "PDFINFO_KNOWN"
BIBTEX_KNOWN = "BIBTEX_KNOWN"
URLS_KNOWN = "URLS_KNOWN"
DESTS_KNOWN = "DESTS_KNOWN"
FONTS_LAYER_KNOWN = "FONTS_LAYER_KNOWN"
IMAGES_LAYER_KNOWN = "IMAGES_LAYER_KNOWN"
PIX2TEX_RAN = "PIX2TEX_RAN"
TSV_KNOWN = "TSV_KNOWN"
TSV_SOURCE = "TSV_SOURCE"  # evidence key: "pdftotext" or "tesseract"
MATHPIX_KNOWN = "MATHPIX_KNOWN"
MODEL_BUILT = "MODEL_BUILT"
COMPARE_BUILT = "COMPARE_BUILT"
SNIP_RAN = "SNIP_RAN"
LINKS_KNOWN = "LINKS_KNOWN"
GEOMETRY_FUSED = "GEOMETRY_FUSED"
TIDDLERS_BUILT = "TIDDLERS_BUILT"
LISTS_BUILT = "LISTS_BUILT"
ALGORITHMS_BUILT = "ALGORITHMS_BUILT"
ANNOTATIONS_BUILT = "ANNOTATIONS_BUILT"
SCORED = "SCORED"
ESCALATION_OPEN = "ESCALATION_OPEN"
EQNUMS_FUSED = "EQNUMS_FUSED"
BIBLIOGRAPHY_BUILT = "BIBLIOGRAPHY_BUILT"
BIBFETCH_DONE = "BIBFETCH_DONE"
REPORT_BUILT = "REPORT_BUILT"
LATEX_INGESTED = "LATEX_INGESTED"
NLP_ENHANCED = "NLP_ENHANCED"
OCR_BUILT = "OCR_BUILT"
VISION_DONE = "VISION_DONE"
EMBEDDED_IMAGES_BUILT = "EMBEDDED_IMAGES_BUILT"
BIBSOURCE_BUILT = "BIBSOURCE_BUILT"

# Hosts that almost always mean "here is the code / data for this paper".
_CODE_HOSTS = (
    "github.com", "gitlab.com", "bitbucket.org", "4open.science",
    "zenodo.org", "huggingface.co", "codeocean.com", "osf.io",
    "sourceforge.net", "paperswithcode.com", "colab.research.google.com",
    "figshare.com", "kaggle.com",
)


# ---------------------------------------------------------------------------
# MathPix OCR download
# ---------------------------------------------------------------------------

def cmd_mathpix(pdf: Path, force: bool = False) -> str:
    """Download MathPix OCR outputs (lines.json, md, tex.zip) next to the PDF.

    Idempotent: if the outputs already exist next to the PDF (and --force is
    not given), no upload happens, so re-runs cost no MathPix credits. The
    pdf_id and the downloaded files are recorded in the sidecar.

    MathPix `lines.json` is the format the comparison pipeline needs: it pairs
    each recognized expression's LaTeX with the CDN image MathPix rendered.
    """
    from .mathpix_client import fetch_mathpix

    sc = Sidecar(pdf)
    t0 = time.monotonic()
    result = fetch_mathpix(str(pdf), force=force)

    files_meta = []
    for ext, path in result["files"].items():
        p = Path(path)
        files_meta.append({
            "format": ext,
            "path": p.name,
            "bytes": p.stat().st_size if p.exists() else 0,
        })

    sc.set_evidence("mathpix_pdf_id", result.get("pdf_id"))
    sc.set_evidence("mathpix_status", result["status"])
    sc.set_evidence("mathpix_files", files_meta)
    prev = ",".join(sorted(sc.facts - {MATHPIX_KNOWN})) or "INIT"
    sc.add_fact(MATHPIX_KNOWN)
    sc.log_transition(
        "mathpix", prev, MATHPIX_KNOWN,
        cost_ms=(time.monotonic() - t0) * 1000, detail=result["status"],
    )
    sc.save()
    return _format_mathpix(result, files_meta)


def _format_mathpix(result: dict, files_meta: list[dict]) -> str:
    verb = "Already present" if result["status"] == "cached" else "Downloaded"
    lines = []
    for fm in files_meta:
        kb = fm["bytes"] / 1024.0
        lines.append(f"  {fm['format']:<10} {fm['path']}  ({kb:,.1f} KB)")
    pid = result.get("pdf_id")
    head = f"{verb} MathPix OCR outputs"
    if pid:
        head += f" (pdf_id {pid})"
    tail = "\nNext: build the unified model from lines.json (pdfdrill model)."
    return head + ":\n" + "\n".join(lines) + tail


# ---------------------------------------------------------------------------
# Unified model + comparison
# ---------------------------------------------------------------------------

def _lines_json_path(pdf: Path) -> Path:
    """Path MathPix lines.json would occupy next to the PDF."""
    base = pdf.name[:-4] if pdf.name.lower().endswith(".pdf") else pdf.name
    return pdf.parent / f"{base}.lines.json"


def _model_path(sc: Sidecar) -> Path:
    return sc.blob_dir / "model.docmodel.json"


def cmd_ocr(pdf: Path, lang: str = "eng", ppi: int = 300, force: bool = False) -> str:
    """Build a MathPix-compatible `<pdf>.lines.json` via tesseract OCR.

    The MathPix-free OCR input path: render each page, OCR with tesseract, group
    word boxes into text lines, and write a `lines.json` of the shape
    `pdfdrill model` ingests — so the whole toolkit runs without a MathPix key.
    Plain text only (no LaTeX / no equation typing / no CDN crops): the math
    comparison columns stay empty on this path. Use `--lang eng+equ` for math
    glyphs or `eng+deu` for German.
    """
    from . import ocr_lines

    sc = Sidecar(pdf)
    lines_path = _lines_json_path(pdf)
    if lines_path.exists() and not force:
        try:
            existing = json.loads(lines_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
        src = existing.get("source")
        if src != "tesseract":
            return (f"{lines_path.name} already exists (looks like a MathPix "
                    f"lines.json). Refusing to overwrite — pass --force to "
                    f"replace it with tesseract OCR.")

    ok, msg = ocr_lines.tools_available()
    if not ok:
        return msg

    t0 = time.monotonic()
    out_dir = sc.blob_dir / "ocr"
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    lj = ocr_lines.build_lines_json(pdf, out_dir, ppi=ppi, lang=lang)
    lines_path.write_text(json.dumps(lj, ensure_ascii=False), encoding="utf-8")

    n_pages = len(lj["pages"])
    n_lines = sum(len(p["lines"]) for p in lj["pages"])
    sc.set_evidence("ocr_lang", lang)
    sc.set_evidence("ocr_pages", n_pages)
    sc.set_evidence("ocr_lines", n_lines)
    prev = ",".join(sorted(sc.facts - {OCR_BUILT})) or "INIT"
    sc.add_fact(OCR_BUILT)
    sc.log_transition("ocr", prev, OCR_BUILT, cost_ms=(time.monotonic() - t0) * 1000,
                      detail=f"{n_pages} pages, {n_lines} lines, lang={lang}")
    sc.save()
    return (
        f"Tesseract OCR ({lang}): {n_lines} text line(s) across {n_pages} page(s) "
        f"→ {lines_path.name} (MathPix-compatible). Build the structure with "
        f"`pdfdrill model {pdf.name}`. Note: plain text only — no LaTeX/equation "
        f"typing/CDN crops (math comparison is MathPix-only)."
    )


def cmd_model(pdf: Path, force: bool = False) -> str:
    """Build the unified docmodel Document from MathPix lines.json.

    Auto-chains `mathpix` if the lines.json isn't there yet. Writes the
    serialized Document to <pdf>.drill/model.docmodel.json and records counts
    (objects, equations, equations carrying a CDN image) in the sidecar.
    """
    from docmodel.main import run as build_model, DEFAULT_CONFIG_PATH

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if sc.has(MODEL_BUILT) and model_path.exists() and not force:
        return _format_model(sc)

    lines_path = _lines_json_path(pdf)
    if not lines_path.exists():
        # Prefer MathPix (gives LaTeX + CDN crops). If it's unavailable — no
        # creds, no network — fall back to the tesseract OCR path so the
        # toolkit still runs end-to-end (plain text, no math fidelity).
        try:
            cmd_mathpix(pdf)
        except Exception as mathpix_err:
            from .ocr_lines import tools_available
            ok, _ = tools_available()
            if not ok:
                return (f"No lines.json for {pdf.name}. MathPix unavailable "
                        f"({mathpix_err}); tesseract OCR also unavailable. "
                        f"Set MathPix creds, or install poppler-utils + "
                        f"tesseract-ocr and run `pdfdrill ocr {pdf.name}`.")
            cmd_ocr(pdf)
        sc = Sidecar(pdf)
    if not lines_path.exists():
        return (f"No lines.json for {pdf.name} "
                f"(run `pdfdrill mathpix` or `pdfdrill ocr` first).")

    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    out = build_model(
        lines_path=str(lines_path),
        config_path=DEFAULT_CONFIG_PATH,
        bibkey=pdf.stem,
        out_path=str(model_path),
        debug_modules=[],
    )

    objects = out.get("objects", [])
    by_type: dict[str, int] = {}
    for o in objects:
        by_type[o["type"]] = by_type.get(o["type"], 0) + 1
    eq_with_cdn = sum(
        1 for o in objects
        if o["type"] == "Equation" and o.get("props", {}).get("cdn_url")
    )

    sc.set_evidence("model_path", str(model_path.relative_to(sc.pdf_path.parent)))
    sc.set_evidence("model_object_counts", by_type)
    sc.set_evidence("model_equations_with_cdn", eq_with_cdn)
    prev = ",".join(sorted(sc.facts - {MODEL_BUILT})) or "INIT"
    sc.add_fact(MODEL_BUILT)
    sc.log_transition(
        "model", prev, MODEL_BUILT, cost_ms=(time.monotonic() - t0) * 1000,
        detail=f"{len(objects)} objects, {eq_with_cdn} eq w/ cdn",
    )
    sc.save()
    return _format_model(sc)


def _format_model(sc: Sidecar) -> str:
    counts = sc.get_evidence("model_object_counts", {}) or {}
    eq_cdn = sc.get_evidence("model_equations_with_cdn", 0)
    total = sum(counts.values())
    top = ", ".join(f"{n} {t}" for t, n in sorted(
        counts.items(), key=lambda kv: -kv[1]) if t in (
        "Equation", "Formula", "Paragraph", "Section", "Table", "Picture"))
    return (
        f"Built unified model: {total} objects ({top}). "
        f"{eq_cdn} equations carry a MathPix CDN image. "
        f"Stored at {sc.get_evidence('model_path')}.\n"
        f"Next: pdfdrill compare <pdf> → LaTeX | KaTeX | image table."
    )


def cmd_compare(pdf: Path, force: bool = False, embed: bool = False) -> str:
    """Emit the LaTeX | KaTeX | MathPix-image comparison HTML.

    Auto-chains `model` if needed. Writes <pdf>.drill/compare.html.
    """
    from docmodel.core import Document
    from docops.base import OperatorConfig
    from docops.projectors.comparison_html import ComparisonHtmlProjector

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    # Projectors only READ the model. `--force` re-emits the artifact but must
    # NOT rebuild the model (that would wipe geometry/lists/annotate/biblio/
    # latex layers); only build when the model is genuinely absent.
    if not sc.has(MODEL_BUILT) or not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    t0 = time.monotonic()
    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    proj = ComparisonHtmlProjector(
        OperatorConfig(op="projector", classname="ComparisonHtmlProjector",
                   params={"embed": embed})
    )
    html_str = proj.project(doc)
    rows = proj.counters.get("rows", 0)

    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    out_path = sc.blob_dir / "compare.html"
    out_path.write_text(html_str, encoding="utf-8")

    sc.set_evidence("compare_path", str(out_path.relative_to(sc.pdf_path.parent)))
    sc.set_evidence("compare_rows", rows)
    prev = ",".join(sorted(sc.facts - {COMPARE_BUILT})) or "INIT"
    sc.add_fact(COMPARE_BUILT)
    sc.log_transition(
        "compare", prev, COMPARE_BUILT, cost_ms=(time.monotonic() - t0) * 1000,
        detail=f"{rows} rows",
    )
    sc.save()
    rel = out_path.relative_to(sc.pdf_path.parent)
    return (
        f"Comparison table: {rows} expressions (LaTeX | KaTeX | MathPix image). "
        f"Open {rel} in a browser."
    )


def cmd_bibsource(pdf: Path, bib_path: str | None = None,
                  bbl_path: str | None = None, force: bool = False) -> str:
    """Ingest the author's GOLD bibliography (`.bbl` + `.bib`) into the model.

    This is the bibliography analogue of `pdfdrill latex` (author .tex as gold
    equations): rather than reconstructing references from OCR (heuristic) or
    the web (Perplexity `bibfetch`), it reads the author's compiled `.bbl`
    (alpha label ↔ citekey ↔ printed entry) and `.bib` (structured fields), then
    links the in-text Citations to them by alpha label (OCR-tolerant). The
    `.bbl`/`.bib` become the authoritative References. Auto-chains `model`.

    Defaults: `<pdf-stem>.bbl` / `.bib` next to the PDF if present; else pass
    `--bbl`/`--bib`.
    """
    from docmodel.core import Document
    from .bibliography import (ingest_bbl, load_bibtex_file,
                               link_citations_by_label, link_citations)

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(MODEL_BUILT) or not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    def _default(ext):
        c = pdf.parent / f"{pdf.stem}{ext}"
        return str(c) if c.exists() else None
    bbl = bbl_path or _default(".bbl")
    bib = bib_path or _default(".bib")
    if not bbl and not bib:
        return ("No .bbl/.bib found next to the PDF. Pass --bbl <file.bbl> "
                "and/or --bib <file.bib> (the author's compiled bibliography).")

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    # The author's bibliography is authoritative: drop prior (heuristic)
    # References + their cites edges so we don't mix gold with OCR guesses.
    for oid in [oid for oid, o in doc.objects.items() if o.type == "Reference"]:
        doc.objects.pop(oid, None)
    doc.alignments = [a for a in doc.alignments if a.kind != "cites"]
    doc.streams.pop("references", None)

    created = enriched = 0
    if bbl:
        created = ingest_bbl(doc, Path(bbl).read_text(encoding="utf-8"))
    if bib:
        enriched = load_bibtex_file(doc, Path(bib).read_text(encoding="utf-8"))["attached"]

    n_refs = sum(1 for o in doc.objects.values() if o.type == "Reference")
    n_cits = sum(1 for o in doc.objects.values() if o.type == "Citation")
    linked = link_citations_by_label(doc)        # primary: alpha label
    if not bbl:                                   # no labels → citekey/number
        linked = link_citations(doc)

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    sc.set_evidence("bibsource_references", n_refs)
    sc.set_evidence("bibsource_enriched", enriched)
    sc.set_evidence("bibsource_citations_linked", linked)
    prev = ",".join(sorted(sc.facts - {BIBSOURCE_BUILT})) or "INIT"
    sc.add_fact(BIBSOURCE_BUILT)
    sc.log_transition("bibsource", prev, BIBSOURCE_BUILT,
                      detail=f"{n_refs} refs, {linked}/{n_cits} citations linked")
    sc.save()
    src = " + ".join(x for x in (Path(bbl).name if bbl else "",
                                 Path(bib).name if bib else "") if x)
    return (
        f"Gold bibliography ingested from {src}: {n_refs} Reference(s) "
        f"({enriched} enriched with structured BibTeX fields); "
        f"{linked}/{n_cits} in-text citations linked to a reference "
        f"(by alpha label, OCR-tolerant). No Perplexity needed — the author's "
        f"own .bbl/.bib is the gold source. Rebuild `pdfdrill tiddlers {pdf.name}`."
    )


def _load_bib_sidecar(pdf: Path, bib_path: Path) -> dict:
    """Apply a .bib file to the model's References (no Perplexity call)."""
    from docmodel.core import Document
    from .bibliography import load_bibtex_file

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not model_path.exists():
        return {"attached": 0, "created": 0}
    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))
    res = load_bibtex_file(doc, bib_path.read_text(encoding="utf-8"))
    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)
    sc.set_evidence("bibtex_file_entries", res["attached"])
    sc.save()
    return res


def cmd_folder(folder: Path, force: bool = False) -> str:
    """Build the full structure for every PDF in a folder from existing
    sidecars — NO MathPix/Perplexity calls.

    For each `<name>.pdf` that has a sibling `<name>.lines.json`, run all the
    state-building levels (model, geometry, equation numbers, lists,
    algorithms, link annotations, bibliography, scoring) and, if present, load
    `<name>.bib` into the References. PDFs without a lines.json are skipped
    (run `pdfdrill mathpix` for those first). `<name>.md` is noted if present.
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise NotADirectoryError(f"Not a folder: {folder}")
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        return f"No PDF files in {folder}."

    # Ordered, network-free levels (each is idempotent / honors --force).
    levels = [
        ("model", cmd_model), ("geometry", cmd_geometry), ("eqnums", cmd_eqnums),
        ("lists", cmd_lists), ("algorithms", cmd_algorithms),
        ("annotate", cmd_annotate), ("embedimages", cmd_embedimages),
        ("bibliography", cmd_bibliography), ("score", cmd_score),
    ]

    lines_out, processed, skipped = [], 0, 0
    for pdf in pdfs:
        lines = pdf.parent / f"{pdf.stem}.lines.json"
        if not lines.exists():
            lines_out.append(f"  {pdf.name}: SKIP — no {pdf.stem}.lines.json "
                             f"(run `pdfdrill mathpix {pdf.name}` first)")
            skipped += 1
            continue
        errs = []
        for name, fn in levels:
            try:
                fn(pdf, force=force)
            except Exception as e:  # noqa: BLE001 — one level shouldn't abort the file
                errs.append(f"{name}({e})")

        extra = []
        bib = pdf.parent / f"{pdf.stem}.bib"
        if bib.exists():
            try:
                res = _load_bib_sidecar(pdf, bib)
                extra.append(f"bib+{res['attached']}")
            except Exception as e:  # noqa: BLE001
                errs.append(f"bib({e})")
        if (pdf.parent / f"{pdf.stem}.md").exists():
            extra.append("md")

        sc = Sidecar(pdf)
        counts = sc.get_evidence("model_object_counts", {}) or {}
        summary = (f"eq={counts.get('Equation', 0)} "
                   f"forms={counts.get('Formula', 0)} "
                   f"lists={sc.get_evidence('lists_created', 0)} "
                   f"algs={sc.get_evidence('algorithms_created', 0)} "
                   f"links={sc.get_evidence('annotation_links', 0)} "
                   f"refs={sc.get_evidence('bibliography_entries', 0)} "
                   f"flagged={sc.get_evidence('scored_flagged', 0)}")
        tail = (" ERRORS: " + ", ".join(errs)) if errs else ""
        extra_s = (" [" + ",".join(extra) + "]") if extra else ""
        lines_out.append(f"  {pdf.name}: {summary}{extra_s}{tail}")
        processed += 1

    head = (f"Folder {folder}: {processed} built, {skipped} skipped "
            f"(of {len(pdfs)} PDFs) — no MathPix/Perplexity calls.")
    return head + "\n" + "\n".join(lines_out)


def cmd_latexbook(tex: Path, bibkey: str | None = None, force: bool = False,
                  no_svg: bool = False) -> str:
    """Build a source-only model from a LaTeX file, render TikZ/tables to SVG,
    and emit the formula report — in one step.

    For a `.tex` (master with `\\input` chapters, e.g. a book) with NO PDF/OCR:
    inline includes, resolve macros from the preamble AND local style files
    (`\\usepackage{mystyle}` -> mystyle.sty), extract sections + display
    equations (author LaTeX, macro-expanded) and TikZ/tables, render those to
    SVG via latex->dvisvgm (skipped with --no-svg or when the tools are
    absent), then write a KaTeX formula report embedding the SVGs. No MathPix,
    no credits. Artifacts go in `<tex>.drill/` next to the file.
    """
    from docmodel.core import Document
    from docops.base import OperatorConfig
    from docops.projectors.formula_report import FormulaReportProjector
    from . import latex_source as ls
    from .svg import tools_available

    tex = Path(tex)
    if not tex.exists():
        return f"No such LaTeX file: {tex}"
    key = bibkey or tex.stem
    drill = tex.parent / f"{tex.name}.drill"
    model_path = drill / "model.docmodel.json"

    if model_path.exists() and not force:
        doc = Document.from_dict(json.loads(model_path.read_text(encoding="utf-8")))
    else:
        doc = ls.build_source_model(str(tex), bibkey=key)
        drill.mkdir(parents=True, exist_ok=True)
        model_path.write_text(
            json.dumps(doc.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    # Render TikZ/tables to SVG (cmd_svg mutates the saved model in place),
    # then reload so the report embeds the freshly-rendered SVGs.
    svg_note = ""
    n_graphics = sum(1 for o in doc.objects.values() if o.type in ("Diagram", "Table"))
    if not no_svg and n_graphics:
        if tools_available():
            cmd_svg(tex, force=force)
            doc = Document.from_dict(json.loads(model_path.read_text(encoding="utf-8")))
            n_svg = sum(1 for o in doc.objects.values()
                        if o.type in ("Diagram", "Table") and o.props.get("svg"))
            svg_note = f" {n_svg}/{n_graphics} TikZ/tables rendered to SVG."
        else:
            svg_note = (f" {n_graphics} TikZ/tables NOT rendered "
                        f"(latex/dvisvgm absent; use --no-svg to silence).")

    proj = FormulaReportProjector(
        OperatorConfig(op="projector", classname="FormulaReportProjector"))
    out_path = drill / "formula-report.html"
    out_path.write_text(proj.project(doc), encoding="utf-8")

    c = doc.meta.get("source_counts", {})
    return (f"LaTeX source model for {tex.name}: {c.get('sections', 0)} sections, "
            f"{c.get('equations', 0)} display equations, {c.get('macros', 0)} macros "
            f"(preamble + local style files).{svg_note} Wrote "
            f"{model_path.relative_to(tex.parent)} and "
            f"{out_path.relative_to(tex.parent)} (KaTeX report; no MathPix).")


def cmd_svg(target: Path, limit: int | None = None, force: bool = False) -> str:
    """Render TikZ `Diagram`s and `Table`s to SVG via latex -> dvisvgm.

    KaTeX can't render TikZ/tables; SVG embeds in HTML. For each Diagram/Table
    carrying `latex_code`, compile a standalone snippet (using the document's
    expanded preamble if stored) and attach the SVG to the object's props
    (`svg`) + a `provenance="dvisvgm"` realization. `target` may be a PDF (its
    .drill model) or a .tex (its .drill model from `latexbook`). Needs `latex`
    + `dvisvgm` on PATH; degrades with a clear message if absent.
    """
    from docmodel.core import Document, Realization
    from .svg import compile_to_svg, tools_available

    target = Path(target)
    # Resolve the model path: PDF sidecar OR <tex>.drill.
    if target.suffix == ".tex":
        model_path = target.parent / f"{target.name}.drill" / "model.docmodel.json"
        sc = None
    else:
        sc = Sidecar(target)
        model_path = _model_path(sc)
    if not model_path.exists():
        return (f"No model for {target.name}. Build it first "
                f"(`pdfdrill model` for a PDF, `pdfdrill latexbook` for a .tex).")
    if not tools_available():
        return ("latex/dvisvgm not found on PATH — cannot render SVG here. "
                "Install TeX Live + dvisvgm; the model still holds latex_code "
                "for each Diagram/Table.")

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    preamble = (doc.meta.get("latex_preamble") or {}).get("standalone")
    # The document's own folder, so local \usepackage{mystyle}/tkz-* resolve.
    resource_dir = str(target.parent)
    targets = [o for o in doc.objects.values()
               if o.type in ("Diagram", "Table") and o.props.get("latex_code")]
    todo = [o for o in targets if force or not o.props.get("svg")]
    if limit is not None:
        todo = todo[:limit]

    done = errors = 0
    for o in todo:
        if force:
            o.realizations = [r for r in o.realizations if r.provenance != "dvisvgm"]
            o.props.pop("svg", None)
        res = compile_to_svg(o.props["latex_code"], preamble=preamble,
                             resource_dir=resource_dir)
        if res["ok"]:
            o.props["svg"] = res["svg"]
            if res["ratio"]:
                o.props["svg_ratio"] = res["ratio"]
            o.add_realization(Realization(stream="svg", role="svg_render",
                                          provenance="dvisvgm",
                                          props={"ratio": res["ratio"]}))
            done += 1
        else:
            o.props["svg_error"] = res["error"]
            errors += 1

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    if sc is not None:
        sc.set_evidence("svg_rendered", done)
        sc.set_evidence("svg_errors", errors)
        sc.save()
    return (f"Rendered {done} TikZ/table SVG(s)"
            + (f", {errors} failed" if errors else "")
            + f" of {len(targets)} graphic object(s). SVGs stored on the model "
            f"(props['svg']); the report embeds them inline.")


def cmd_report(pdf: Path, force: bool = False, embed: bool = False) -> str:
    """Emit a full inline+display math report (formula-report.html).

    Lists every inline Formula (LaTeX + KaTeX) and every display Equation
    (+ MathPix CDN image + equation number). Auto-chains `model`.
    """
    from docmodel.core import Document
    from docops.base import OperatorConfig
    from docops.projectors.formula_report import FormulaReportProjector

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(MODEL_BUILT) or not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    proj = FormulaReportProjector(
        OperatorConfig(op="projector", classname="FormulaReportProjector",
                   params={"embed": embed}))
    result = proj.project(doc)
    inline = proj.counters.get("inline_rows", 0)
    eqs = proj.counters.get("equation_rows", 0)

    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    out_path = sc.blob_dir / "formula-report.html"
    out_path.write_text(result, encoding="utf-8")

    sc.set_evidence("report_path", str(out_path.relative_to(sc.pdf_path.parent)))
    prev = ",".join(sorted(sc.facts - {REPORT_BUILT})) or "INIT"
    sc.add_fact(REPORT_BUILT)
    sc.log_transition("report", prev, REPORT_BUILT, detail=f"{inline} inline, {eqs} equations")
    sc.save()
    rel = out_path.relative_to(sc.pdf_path.parent)
    return (f"Formula report: {inline} inline formulas + {eqs} display equations "
            f"(LaTeX | KaTeX | image). Open {rel} in a browser.")


def cmd_snip(pdf: Path, limit: int | None = None, force: bool = False) -> str:
    """OCR each equation's CDN crop via MathPix Snip (/v3/text) as a competing
    'snip' provenance, attaching the LaTeX + confidence to the model.

    Auto-chains `model` if needed. Idempotent per equation: an equation that
    already has a snip candidate is skipped unless --force. `--limit N` caps
    how many crops are sent (each is one MathPix request).
    """
    from docmodel.core import Document, Realization, Region
    from .mathpix_snip import snip_result

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(MODEL_BUILT) or not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    eqs = [o for o in doc.objects.values()
           if o.type == "Equation" and o.props.get("cdn_url")]
    todo = []
    for e in eqs:
        has_snip = any(r.role == "latex_candidate" and r.provenance == "snip"
                       for r in e.realizations)
        if has_snip and not force:
            continue
        todo.append(e)
    if limit is not None:
        todo = todo[:limit]

    t0 = time.monotonic()
    done = errors = 0
    confs: list[float] = []
    for e in todo:
        try:
            res = snip_result(e.props["cdn_url"])
        except Exception:  # noqa: BLE001 — one bad crop shouldn't abort the batch
            errors += 1
            continue
        if force:
            e.realizations = [r for r in e.realizations
                              if not (r.role == "latex_candidate" and r.provenance == "snip")]
        region = None
        lines = res.get("lines") or []
        if lines and lines[0].get("cnt"):
            region = Region.from_cnt(lines[0]["cnt"], page=e.props.get("page"))
        e.add_realization(Realization(
            stream="snip", role="latex_candidate", provenance="snip",
            score=res.get("confidence"),
            props={"latex": res.get("latex", ""), "text": res.get("text", ""),
                   "confidence": res.get("confidence")},
            region=region,
        ))
        done += 1
        if res.get("confidence") is not None:
            confs.append(res["confidence"])

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    avg = sum(confs) / len(confs) if confs else None
    total = (sc.get_evidence("snip_count", 0) or 0) + done
    sc.set_evidence("snip_count", total)
    sc.set_evidence("snip_avg_confidence", avg)
    prev = ",".join(sorted(sc.facts - {SNIP_RAN})) or "INIT"
    sc.add_fact(SNIP_RAN)
    sc.log_transition(
        "snip", prev, SNIP_RAN, cost_ms=(time.monotonic() - t0) * 1000,
        detail=f"{done} snipped, {errors} errors",
    )
    sc.save()

    msg = f"Snipped {done} equation crop(s) via MathPix /v3/text"
    if errors:
        msg += f" ({errors} failed)"
    if avg is not None:
        msg += f"; mean confidence {avg:.3f}"
    msg += f". Run `pdfdrill compare {pdf.name}` to see the Snip column."
    return msg


# ---------------------------------------------------------------------------
# Block reconstruction — nest ListItems into a recursive List tree
# ---------------------------------------------------------------------------

def cmd_lists(pdf: Path, force: bool = False) -> str:
    """Group flat ListItems into nested `List` containers using fused
    indentation geometry. Auto-chains `model` and `geometry`.

    Each contiguous run of list items (no page change / no big line gap)
    becomes a List; items indented past the current level open a nested
    sublist (LaTeX-list semantics). Recursive `List` DocObjects are added with
    ListItem/List children and parent links.
    """
    from docmodel.core import Document, DocObject
    from .blocks import (nest_list_items, max_depth, count_lists,
                         resplit_list_items_by_geometry)

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(MODEL_BUILT) or not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not sc.has(GEOMETRY_FUSED):
        cmd_geometry(pdf)
        sc = Sidecar(pdf)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    existing = [o for o in doc.objects.values() if o.type == "List"]
    if existing and not force:
        return _format_lists(sc)
    if force and existing:
        ids = {o.id for o in existing}
        for o in existing:
            doc.objects.pop(o.id, None)
        for o in doc.objects.values():          # detach children/parents
            o.children = [c for c in o.children if c not in ids]
            if o.parent in ids:
                o.parent = None
        # drop previously geometry-resplit items so we don't accumulate
        for o in [o for o in doc.objects.values()
                  if o.type == "ListItem" and o.props.get("provenance") == "geometry_resplit"]:
            doc.objects.pop(o.id, None)

    # Recover bullets the OCR merged onto one line, using pdftotext y-breaks.
    resplit = resplit_list_items_by_geometry(doc)

    mp = doc.stream("mathpix_lines") if "mathpix_lines" in doc.streams else None

    def _indent_of(item_obj):
        ri = item_obj.props.get("_resplit_indent")
        if ri is not None:
            return ri
        if mp is None:
            return None
        r = next((r for r in item_obj.realizations
                  if r.stream == "mathpix_lines" and r.start is not None), None)
        if r is None:
            return None
        g = mp.payload.get(r.start, {}).get("_geom")
        return g.get("indent_norm") if g else None

    items = []
    for o in doc.objects.values():
        if o.type != "ListItem":
            continue
        items.append({
            "id": o.id,
            "page": o.props.get("page"),
            "line_index": o.props.get("line_index"),
            "indent": _indent_of(o),
            "marker": o.props.get("marker"),
        })
    items.sort(key=lambda it: (it["page"] if it["page"] is not None else 1 << 30,
                               it["line_index"] if it["line_index"] is not None else 1 << 30))

    roots = nest_list_items(items)

    created = [0]

    def materialize(nodes, parent_id):
        for ch in nodes:
            if ch["kind"] == "item":
                it = doc.objects.get(ch["id"])
                if it is None:
                    continue
                if parent_id:
                    it.parent = parent_id
                    doc.objects[parent_id].children.append(ch["id"])
            else:
                node = ch["node"]
                markers = [c.get("marker") for c in node["children"]
                           if c["kind"] == "item" and c.get("marker")]
                lst = DocObject(type="List", props={
                    "indent_norm": round(node["indent"], 4),
                    "list_type": _list_type(markers),
                    "bibkey": pdf.stem,
                })
                doc.add(lst)
                created[0] += 1
                if parent_id:
                    lst.parent = parent_id
                    doc.objects[parent_id].children.append(lst.id)
                materialize(node["children"], lst.id)

    materialize(roots, None)

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    depth = max_depth(roots)
    n_items = len(items)
    sc.set_evidence("lists_created", created[0])
    sc.set_evidence("lists_max_depth", depth)
    sc.set_evidence("lists_items", n_items)
    sc.set_evidence("lists_resplit", resplit)
    prev = ",".join(sorted(sc.facts - {LISTS_BUILT})) or "INIT"
    sc.add_fact(LISTS_BUILT)
    sc.log_transition(
        "lists", prev, LISTS_BUILT,
        detail=f"{created[0]} lists, depth {depth}, {n_items} items",
    )
    sc.save()
    return _format_lists(sc)


def cmd_algorithms(pdf: Path, force: bool = False) -> str:
    """Reconstruct `Algorithm` blocks from MathPix `pseudocode` lines.

    MathPix tags algorithm bodies with line type `pseudocode` and preserves
    indentation in `region.top_left_x`; we group them per `Algorithm N:`
    caption and derive an integer `depth` per step (if/else/end nesting).
    Each Algorithm DocObject gets AlgorithmStep children. Auto-chains `model`.
    """
    from docmodel.core import Document, DocObject, Realization
    from .blocks import detect_algorithms, algorithm_max_depth

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(MODEL_BUILT) or not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    existing = [o for o in doc.objects.values() if o.type in ("Algorithm", "AlgorithmStep")]
    if existing and not force:
        return _format_algorithms(sc)
    if force and existing:
        ids = {o.id for o in existing}
        for o in existing:
            doc.objects.pop(o.id, None)
        for o in doc.objects.values():
            o.children = [c for c in o.children if c not in ids]
            if o.parent in ids:
                o.parent = None

    mp = doc.stream("mathpix_lines") if "mathpix_lines" in doc.streams else None
    if mp is None:
        return f"No mathpix_lines in the model for {pdf.name}."

    raw = []
    idmap = {}
    for i, anchor in enumerate(mp.anchors):
        p = mp.payload[anchor]
        if p.get("type") != "pseudocode":
            continue
        reg = p.get("region") or {}
        raw.append({"id": i, "page": p.get("_page"), "line_index": p.get("_line_index"),
                    "text": p.get("text") or p.get("text_display") or "",
                    "x": reg.get("top_left_x")})
        idmap[i] = anchor

    algos = detect_algorithms(raw)

    created = steps_total = 0
    for a in algos:
        alg = DocObject(type="Algorithm", props={
            "number": a["number"], "title": a["title"], "page": a["page"],
            "bibkey": pdf.stem})
        step_anchors = [idmap[s["id"]] for s in a["steps"] if s["id"] in idmap]
        span = ([idmap[a["caption_id"]]] if a["caption_id"] in idmap else []) + step_anchors
        if span:
            alg.add_realization(Realization(stream="mathpix_lines",
                                            start=span[0], end=span[-1], role="surface"))
        doc.add(alg)
        created += 1
        for s in a["steps"]:
            st = DocObject(type="AlgorithmStep",
                           props={"text": s["text"], "depth": s["depth"], "bibkey": pdf.stem},
                           parent=alg.id)
            anc = idmap.get(s["id"])
            if anc is not None:
                st.add_realization(Realization(stream="mathpix_lines",
                                               start=anc, end=anc, role="surface"))
            doc.add(st)
            alg.children.append(st.id)
            steps_total += 1

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    depth = algorithm_max_depth(algos)
    sc.set_evidence("algorithms_created", created)
    sc.set_evidence("algorithms_steps", steps_total)
    sc.set_evidence("algorithms_max_depth", depth)
    prev = ",".join(sorted(sc.facts - {ALGORITHMS_BUILT})) or "INIT"
    sc.add_fact(ALGORITHMS_BUILT)
    sc.log_transition("algorithms", prev, ALGORITHMS_BUILT,
                      detail=f"{created} algorithms, {steps_total} steps, depth {depth}")
    sc.save()
    return _format_algorithms(sc)


def _format_algorithms(sc: Sidecar) -> str:
    return (
        f"Reconstructed {sc.get_evidence('algorithms_created', 0)} Algorithm "
        f"block(s) with {sc.get_evidence('algorithms_steps', 0)} steps "
        f"(max indent depth {sc.get_evidence('algorithms_max_depth', 0)}) from "
        f"MathPix pseudocode lines. Each Algorithm carries number/title/page; "
        f"steps carry text + depth (if/else/end nesting)."
    )


def cmd_latex(pdf: Path, tex: str | None = None, force: bool = False) -> str:
    """Ingest the author's LaTeX source (.tex or arXiv .tgz) as a competing
    `tex` provenance on each matched equation.

    For each display equation found in the source, store the **original** author
    LaTeX and a preamble-**expanded** form, then attach it to the MathPix
    `Equation` whose normalized LaTeX is the closest match — as a
    `provenance="tex"` `latex_candidate` realization (the gold reference vs OCR;
    a new column in `compare`). Two forms are kept because TikZ/operator macros
    only compile after preamble expansion (future latex->dvisvgm step). No
    LaTeX tools or network needed. Auto-chains `model`.
    """
    from docmodel.core import Document, Realization
    from . import latex_source as ls
    from .scoring import normalize_latex, latex_similarity

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(MODEL_BUILT) or not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    # Locate the source: explicit --tex, else <stem>.tex / <stem>.tgz / .tar.gz.
    src = Path(tex) if tex else None
    if src is None:
        for ext in (".tex", ".tgz", ".tar.gz"):
            cand = pdf.parent / f"{pdf.stem}{ext}"
            if cand.exists():
                src = cand
                break
    if src is None or not src.exists():
        return (f"No LaTeX source found for {pdf.name} "
                f"(looked for {pdf.stem}.tex / .tgz / .tar.gz; pass --tex <path>).")

    full, main = ls.read_source(str(src))
    if not full:
        return f"Could not read LaTeX source from {src.name}."
    preamble, body = ls.split_preamble(full)
    macros = ls.extract_macros(preamble)
    src_eqs = ls.extract_display_equations(body)

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    if force:
        for o in doc.objects.values():
            if o.type == "Equation":
                o.realizations = [r for r in o.realizations
                                  if not (r.role == "latex_candidate" and r.provenance == "tex")]
        doc.meta.pop("latex_preamble", None)

    # Persist the two preamble forms on the document for the later SVG step.
    doc.meta["latex_preamble"] = {
        "main": main,
        "original": preamble.strip(),
        "standalone": ls.standalone_preamble(preamble),
        "num_macros": len(macros),
    }

    eqs = [o for o in doc.objects.values() if o.type == "Equation"]
    # Precompute normalized OCR latex per equation.
    eq_norm = [(o, normalize_latex(o.props.get("latex", ""))) for o in eqs]

    attached = unmatched = 0
    for se in src_eqs:
        original = se["latex"]
        expanded = ls.expand_macros(original, macros)
        target = normalize_latex(expanded)
        if not target:
            continue
        best, best_sim = None, 0.0
        for o, onorm in eq_norm:
            if any(r.role == "latex_candidate" and r.provenance == "tex"
                   for r in o.realizations):
                continue  # already has a tex reading
            s = latex_similarity(expanded, o.props.get("latex", ""))
            if s > best_sim:
                best_sim, best = s, o
        if best is not None and best_sim >= 0.55:
            best.add_realization(Realization(
                stream="tex", role="latex_candidate", provenance="tex",
                score=round(best_sim, 3),
                props={"latex": expanded, "latex_original": original,
                       "env": se["env"], "label": se.get("label"),
                       "numbered": se.get("numbered"), "match_sim": round(best_sim, 3)}))
            attached += 1
        else:
            unmatched += 1

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    sc.set_evidence("latex_source", src.name)
    sc.set_evidence("latex_macros", len(macros))
    sc.set_evidence("latex_src_equations", len(src_eqs))
    sc.set_evidence("latex_attached", attached)
    prev = ",".join(sorted(sc.facts - {LATEX_INGESTED})) or "INIT"
    sc.add_fact(LATEX_INGESTED)
    sc.log_transition("latex", prev, LATEX_INGESTED,
                      detail=f"{attached}/{len(src_eqs)} eqs matched, {len(macros)} macros")
    sc.save()
    return (f"Ingested LaTeX source {src.name}: {len(src_eqs)} display equations, "
            f"{len(macros)} preamble macros. Attached {attached} as `tex` "
            f"provenance to MathPix equations ({unmatched} source eqs unmatched). "
            f"Kept original+expanded LaTeX; preamble stored for the SVG step. "
            f"Run `pdfdrill compare {pdf.name}` to see the tex column.")


def _list_type(markers: list[str]) -> str:
    if not markers:
        return "list"
    bullets = sum(1 for m in markers if m and m[0] in "•○▪-*•‣◦⁃∙")
    return "itemize" if bullets >= len(markers) / 2 else "enumerate"


def _format_lists(sc: Sidecar) -> str:
    resplit = sc.get_evidence("lists_resplit", 0)
    rs = f" Recovered {resplit} merged bullet(s) via y-position re-split." if resplit else ""
    return (
        f"Reconstructed {sc.get_evidence('lists_created', 0)} nested List(s) "
        f"from {sc.get_evidence('lists_items', 0)} list items "
        f"(max nesting depth {sc.get_evidence('lists_max_depth', 0)}).{rs} "
        f"List objects carry list_type (itemize/enumerate) and indent_norm; "
        f"ListItems are now children of their List."
    )


# ---------------------------------------------------------------------------
# TiddlyWiki export — JSON tiddler array for quick data-structure inspection
# ---------------------------------------------------------------------------

def cmd_tiddlers(pdf: Path, force: bool = False, embed: bool = False) -> str:
    """Emit a TiddlyWiki JSON tiddler array from the unified model.

    Quick way to eyeball the structure: drop the array into TiddlyWiki and a
    `<$list>` table macro renders each equation's LaTeX (`<$latex>`), its
    KaTeX rendering, and the MathPix crop (`<$image source={{!!canonical_uri}}
    width={{!!width}} height={{!!height}}>`). Equation tiddlers carry `latex`,
    `displayMode`, `refnum`, `canonical_uri`, region `width`/`height`, and any
    competing readings as `latex_<provenance>` fields. Auto-chains `model`.
    """
    from docmodel.core import Document
    from docops.base import OperatorConfig
    from docops.projectors.tiddlywiki import TiddlyWikiProjector

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(MODEL_BUILT) or not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    t0 = time.monotonic()
    proj = TiddlyWikiProjector(
        OperatorConfig(op="projector", classname="TiddlyWikiProjector",
                   params={"embed": embed}))
    result = proj.project(doc)
    count = proj.counters.get("tiddlers_emitted", 0)

    bibkey = doc.meta.get("bibkey", pdf.stem)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    out_path = sc.blob_dir / f"{bibkey}.tiddlers.json"
    out_path.write_text(result, encoding="utf-8")

    sc.set_evidence("tiddlers_path", str(out_path.relative_to(sc.pdf_path.parent)))
    sc.set_evidence("tiddlers_count", count)
    prev = ",".join(sorted(sc.facts - {TIDDLERS_BUILT})) or "INIT"
    sc.add_fact(TIDDLERS_BUILT)
    sc.log_transition(
        "tiddlers", prev, TIDDLERS_BUILT, cost_ms=(time.monotonic() - t0) * 1000,
        detail=f"{count} tiddlers",
    )
    sc.save()
    rel = out_path.relative_to(sc.pdf_path.parent)
    return (f"Wrote {count} TiddlyWiki tiddlers to {rel}. Import into TiddlyWiki; "
            f"equation tiddlers carry latex / displayMode / canonical_uri / "
            f"width / height for your <$latex>/<$image> table macro.")


# ---------------------------------------------------------------------------
# Geometry fusion — lift pdftotext -tsv layout onto the model (cross-level)
# ---------------------------------------------------------------------------

def cmd_geometry(pdf: Path, force: bool = False) -> str:
    """Fuse cheap pdftotext -tsv word geometry onto the unified model.

    Adds a `pdf_lines` stream, aligns each MathPix line to its pdftotext line
    (page + normalized-y + string match) as `Alignment(kind="geometry")`, and
    annotates each matched line with `_geom` (normalized margins + indentation
    relative to the page body-left). This is the layout substrate that
    algorithm/itemize/equation-number detectors consume. Auto-chains `model`.
    """
    from docmodel.core import Document
    from .geometry import run_tsv, parse_tsv, group_lines, fuse, clear_geometry

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(MODEL_BUILT) or not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    if "pdf_lines" in doc.streams and not force:
        return _format_geometry(sc)
    if force:
        clear_geometry(doc)

    t0 = time.monotonic()
    words, page_dims = parse_tsv(run_tsv(str(pdf)))
    lines = group_lines(words)
    stats = fuse(doc, lines, page_dims)

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    sc.set_evidence("geometry_pdf_lines", stats["pdf_lines"])
    sc.set_evidence("geometry_matched", stats["matched"])
    sc.set_evidence("geometry_mean_sim", stats["mean_sim"])
    prev = ",".join(sorted(sc.facts - {GEOMETRY_FUSED})) or "INIT"
    sc.add_fact(GEOMETRY_FUSED)
    sc.log_transition(
        "geometry", prev, GEOMETRY_FUSED, cost_ms=(time.monotonic() - t0) * 1000,
        detail=f"{stats['matched']}/{stats['pdf_lines']} matched",
    )
    sc.save()
    return _format_geometry(sc)


def _format_geometry(sc: Sidecar) -> str:
    pl = sc.get_evidence("geometry_pdf_lines", 0)
    m = sc.get_evidence("geometry_matched", 0)
    sim = sc.get_evidence("geometry_mean_sim")
    sim_s = f", mean text-match {sim}" if sim is not None else ""
    return (
        f"Geometry fused: {pl} pdftotext lines lifted into `pdf_lines`; "
        f"{m} MathPix lines now carry layout (indentation/margins){sim_s}. "
        f"Block detectors (algorithm/itemize) and equation-number fusion can "
        f"now read each line's `_geom`."
    )


# ---------------------------------------------------------------------------
# Bibliography — parse the References section into Reference objects
# ---------------------------------------------------------------------------

def cmd_bibliography(pdf: Path, force: bool = False) -> str:
    """Parse the References section into `Reference` DocObjects.

    Heuristic (entries are unstructured): segments on year/page-range line
    endings, extracts year + author block + a generated citekey, keeps the
    original text. The TiddlyWiki output renders each as a bibliographic
    tiddler whose text starts with a `{{||CIT}}` self-reference. Auto-chains
    `model`. Full structured BibTeX fields await a real grammar.
    """
    from docmodel.core import Document
    from .bibliography import (parse_bibliography, add_reference_objects,
                               link_citations, detect_numeric_citations,
                               detect_author_year_citations)

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(MODEL_BUILT) or not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    existing = [o for o in doc.objects.values() if o.type == "Reference"]
    if existing and not force:
        return _format_bibliography(sc)
    if force and existing:
        for o in existing:
            doc.objects.pop(o.id, None)
        doc.alignments = [a for a in doc.alignments if a.kind != "cites"]
        # drop citations we previously detected so we don't duplicate
        for o in [o for o in doc.objects.values()
                  if o.type == "Citation" and o.props.get("added_by") == "bibliography"]:
            doc.objects.pop(o.id, None)

    entries = parse_bibliography(doc)
    n = add_reference_objects(doc, entries)
    with_year = sum(1 for e in entries if e["year"])
    # In-text citations resolve against the references; skip the bibliography's
    # own lines. Numeric ([N]) and parenthetical author-year ((Asai, 2023)).
    ref_anchors = {r.start for o in doc.objects.values() if o.type == "Reference"
                   for r in o.realizations if r.stream == "mathpix_lines" and r.start}
    numeric = detect_numeric_citations(doc, max_num=n, exclude_anchors=ref_anchors)
    authyear = detect_author_year_citations(doc, exclude_anchors=ref_anchors)
    cites = link_citations(doc)

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    sc.set_evidence("bibliography_entries", n)
    sc.set_evidence("bibliography_with_year", with_year)
    sc.set_evidence("bibliography_numeric_citations", numeric)
    sc.set_evidence("bibliography_authoryear_citations", authyear)
    sc.set_evidence("bibliography_cites", cites)
    prev = ",".join(sorted(sc.facts - {BIBLIOGRAPHY_BUILT})) or "INIT"
    sc.add_fact(BIBLIOGRAPHY_BUILT)
    sc.log_transition("bibliography", prev, BIBLIOGRAPHY_BUILT,
                      detail=f"{n} entries, {numeric}+{authyear} cites detected, {cites} linked")
    sc.save()
    return _format_bibliography(sc)


def cmd_bibfetch(pdf: Path, limit: int | None = None, force: bool = False) -> str:
    """Enrich Reference entries with full BibTeX via Perplexity SONAR.

    Printed references are truncated, so each Reference's BibTeX is requested
    from the LLM (which searches online for missing fields), parsed, and stored
    on the Reference (`bibtex`, `citations`, refined author/year/title).
    Auto-chains `bibliography`. Idempotent per reference (skips those already
    enriched unless --force); `--limit N` caps the number of API calls.
    """
    from docmodel.core import Document
    from .perplexity_client import enrich

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(BIBLIOGRAPHY_BUILT):
        cmd_bibliography(pdf)
        sc = Sidecar(pdf)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill bibliography` first)."

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    refs = [o for o in doc.objects.values() if o.type == "Reference"]
    todo = [r for r in refs if force or not r.props.get("bibtex")]
    if limit is not None:
        todo = todo[:limit]

    done = errors = 0
    for r in todo:
        try:
            res = enrich(
                citekey=r.props.get("citekey", ""),
                author=r.props.get("author", ""),
                year=r.props.get("year", ""),
                raw_text=r.props.get("raw_text", ""),
                title=r.props.get("title", ""),
            )
        except Exception:  # noqa: BLE001 — one failure shouldn't abort the batch
            errors += 1
            continue
        if res["bibtex"]:
            r.props["bibtex"] = res["bibtex"]
            r.props["citations"] = " ".join(res["citations"])
            for k in ("author", "year", "title", "entry_type"):
                if res["fields"].get(k):
                    r.props[k] = res["fields"][k]
            done += 1

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    total = (sc.get_evidence("bibfetch_done", 0) or 0) + done
    sc.set_evidence("bibfetch_done", total)
    prev = ",".join(sorted(sc.facts - {BIBFETCH_DONE})) or "INIT"
    sc.add_fact(BIBFETCH_DONE)
    sc.log_transition("bibfetch", prev, BIBFETCH_DONE,
                      detail=f"{done} enriched, {errors} errors")
    sc.save()
    msg = f"Enriched {done} reference(s) with full BibTeX via Perplexity SONAR"
    if errors:
        msg += f" ({errors} failed)"
    msg += f". Rebuild `pdfdrill tiddlers {pdf.name}` — Reference tiddlers now carry bibtex + citations."
    return msg


def _format_bibliography(sc: Sidecar) -> str:
    n = sc.get_evidence("bibliography_entries", 0)
    y = sc.get_evidence("bibliography_with_year", 0)
    cites = sc.get_evidence("bibliography_cites", 0)
    numeric = sc.get_evidence("bibliography_numeric_citations", 0)
    authyear = sc.get_evidence("bibliography_authoryear_citations", 0)
    det = numeric + authyear
    det_s = (f" {det} in-text citations detected ({numeric} numeric, "
             f"{authyear} author-year), {cites} linked to references." if det else "")
    cite_s = det_s
    return (f"Parsed {n} bibliography entries ({y} with a year) into Reference "
            f"nodes (citekey + author + year + original text; heuristic).{cite_s} "
            f"TiddlyWiki renders each as a bib tiddler led by {{{{||CIT}}}}. "
            f"Rebuild `pdfdrill tiddlers {sc.pdf_path.name}`.")


# ---------------------------------------------------------------------------
# Equation-number fusion — attach (N) from margin geometry
# ---------------------------------------------------------------------------

def cmd_eqnums(pdf: Path, force: bool = False) -> str:
    """Attach `equation_number` ("(1)") to each display equation.

    Normalizes MathPix-supplied numbers and recovers margin numbers MathPix
    missed from the fused `pdf_lines` geometry (matching by page + vertical
    position). Auto-chains `model` + `geometry`. Enables transcluding both the
    equation and its reference (`||FO` / `||FREF`) in the TiddlyWiki output.
    """
    from docmodel.core import Document
    from .eqnums import fuse_equation_numbers

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(MODEL_BUILT) or not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not sc.has(GEOMETRY_FUSED):
        cmd_geometry(pdf)
        sc = Sidecar(pdf)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    if force:
        for o in doc.objects.values():
            if o.type == "Equation":
                o.props.pop("equation_number", None)
        doc.alignments = [a for a in doc.alignments if a.kind != "equation_number"]

    stats = fuse_equation_numbers(doc)

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    sc.set_evidence("eqnums_from_mathpix", stats["from_mathpix"])
    sc.set_evidence("eqnums_recovered", stats["recovered"])
    prev = ",".join(sorted(sc.facts - {EQNUMS_FUSED})) or "INIT"
    sc.add_fact(EQNUMS_FUSED)
    sc.log_transition("eqnums", prev, EQNUMS_FUSED,
                      detail=f"{stats['from_mathpix']} mathpix, {stats['recovered']} recovered")
    sc.save()
    return (f"Equation numbers: {stats['from_mathpix']} from MathPix + "
            f"{stats['recovered']} recovered from margin geometry. Each "
            f"equation now carries equation_number ('(N)') for ||FO/||FREF "
            f"transclusion. Rebuild `pdfdrill tiddlers {pdf.name}`.")


# ---------------------------------------------------------------------------
# Phase-2 scoring — quantify agreement across provenances
# ---------------------------------------------------------------------------

def cmd_score(pdf: Path, force: bool = False) -> str:
    """Score each equation by cross-provenance agreement + snip confidence.

    Stores `props["score"]` per equation (agreement vs each competing reading,
    mean agreement, snip confidence, a 0..1 min_signal, and flags). Surfaces in
    `compare` as a score column with low-signal rows highlighted. Auto-chains
    `model`.
    """
    from docmodel.core import Document
    from .scoring import score_equation

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(MODEL_BUILT) or not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    scored = flagged = 0
    agreements: list[float] = []
    for o in doc.objects.values():
        if o.type != "Equation" or not o.props.get("cdn_url"):
            continue
        cands: dict[str, dict] = {}
        for r in o.realizations:
            if r.role == "latex_candidate" and r.provenance:
                cands[r.provenance] = {"latex": r.props.get("latex", ""), "score": r.score}
        s = score_equation(o.props.get("latex", ""), cands)
        o.props["score"] = s
        scored += 1
        if s["flags"]:
            flagged += 1
        if s["mean_agreement"] is not None:
            agreements.append(s["mean_agreement"])

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    mean_ag = round(sum(agreements) / len(agreements), 3) if agreements else None
    sc.set_evidence("scored_equations", scored)
    sc.set_evidence("scored_flagged", flagged)
    sc.set_evidence("scored_mean_agreement", mean_ag)
    prev = ",".join(sorted(sc.facts - {SCORED})) or "INIT"
    sc.add_fact(SCORED)
    sc.log_transition("score", prev, SCORED,
                      detail=f"{scored} scored, {flagged} flagged")
    sc.save()
    return _format_score(sc)


def _format_score(sc: Sidecar) -> str:
    n = sc.get_evidence("scored_equations", 0)
    fl = sc.get_evidence("scored_flagged", 0)
    ag = sc.get_evidence("scored_mean_agreement")
    ag_s = f"mean cross-provenance agreement {ag}; " if ag is not None else ""
    return (f"Scored {n} equations; {ag_s}{fl} flagged for review "
            f"(low agreement or low snip confidence). "
            f"Run `pdfdrill compare {sc.pdf_path.name}` — flagged rows are "
            f"highlighted with a score column.")


# ---------------------------------------------------------------------------
# NLP enhancement (Stanza) — optional [nlp] extra
# ---------------------------------------------------------------------------

# Object types StanzaNlpMutator can annotate, in a sensible default order.
_NLP_DEFAULT_TYPES = ["Paragraph", "Abstract", "Section", "ListItem", "Footnote"]


def cmd_nlp(pdf: Path, limit: int | None = None, pages: int | None = None,
            types: list[str] | None = None, force: bool = False) -> str:
    """Run the Stanza neural NLP pipeline over the model's prose objects.

    For each Paragraph/Abstract/Section/ListItem/Footnote, projects the text to
    clean prose (LaTeX/TiddlyWiki markup stripped, inline math → ⟨math⟩) and
    attaches per-sentence tokens (POS/lemma/dependency) + named entities under
    `props["nlp"]`. The raw source field is left untouched. Auto-chains `model`.

    Optional. Needs the `[nlp]` extra (`pip install 'pdfdrill[nlp]'`) plus the
    one-time model download (`python -c "import stanza; stanza.download('en')"`);
    when Stanza or the model is missing this returns a friendly install hint
    instead of an error.
    """
    from docmodel.core import Document
    from docops.base import OperatorConfig
    from docops.mutators.stanza_nlp import StanzaNlpMutator

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(MODEL_BUILT) or not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    cfg = OperatorConfig(
        op="mutator", classname="StanzaNlpMutator", title="nlp",
        params={
            "lang": "en",
            "types": types or _NLP_DEFAULT_TYPES,
            "max_page": pages,
            "limit": limit,
            "require": False,
        },
    )
    mutator = StanzaNlpMutator(cfg)
    mutator.apply(doc)

    if mutator.counters.get("skipped_stanza_unavailable"):
        return (
            "NLP skipped: Stanza (or its English model) is not available. "
            "Install the optional extra and download the model once:\n"
            "  pip install 'pdfdrill[nlp]'\n"
            "  python -c \"import stanza; stanza.download('en')\""
        )

    annotated = mutator.counters.get("objects_annotated", 0)
    # Aggregate signal for the prose summary.
    sentences = entities = 0
    ent_types: dict[str, int] = {}
    sample: list[str] = []
    for o in doc.objects.values():
        nlp = (o.props or {}).get("nlp")
        if not nlp:
            continue
        for s in nlp.get("sentences", []):
            sentences += 1
            for e in s.get("entities", []):
                entities += 1
                ent_types[e["type"]] = ent_types.get(e["type"], 0) + 1
                if len(sample) < 6 and e["text"] not in sample:
                    sample.append(e["text"])

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    sc.set_evidence("nlp_objects_annotated", annotated)
    sc.set_evidence("nlp_sentences", sentences)
    sc.set_evidence("nlp_entities", entities)
    prev = ",".join(sorted(sc.facts - {NLP_ENHANCED})) or "INIT"
    sc.add_fact(NLP_ENHANCED)
    sc.log_transition("nlp", prev, NLP_ENHANCED,
                      detail=f"{annotated} objects, {entities} entities")
    sc.save()

    by_type = ", ".join(f"{k} {v}" for k, v in
                        sorted(ent_types.items(), key=lambda kv: -kv[1])[:5])
    sample_s = ("; e.g. " + ", ".join(sample)) if sample else ""
    return (
        f"NLP (Stanza): annotated {annotated} prose object(s), {sentences} "
        f"sentence(s), {entities} named entit{'y' if entities == 1 else 'ies'}"
        f"{' (' + by_type + ')' if by_type else ''}{sample_s}. "
        f"Stored under each object's props['nlp'] in model.docmodel.json."
    )


# ---------------------------------------------------------------------------
# Phase 3 — closed self-learning loop: escalate flagged equations, relearn
# ---------------------------------------------------------------------------

_ESCALATE_PROMPT = (
    "These equations were FLAGGED for review (low confidence or disagreement). "
    "For each, open the image at `cdn_url` and transcribe ONLY the mathematics "
    "as a single LaTeX string (no surrounding $; \\begin{aligned} for "
    "multi-line). Return JSON list of {eq_id, latex}. A reading that "
    "corroborates the existing one will resolve the flag."
)


def cmd_escalate(pdf: Path, limit: int | None = None) -> str:
    """Phase-3 step 1: export the FLAGGED equations for a second opinion.

    Auto-chains `score`. Writes a candidates manifest of only the flagged
    equations and snapshots their current signals, so `relearn` can report
    what improved after the new readings are ingested.
    """
    from docmodel.core import Document

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(SCORED):
        cmd_score(pdf)
        sc = Sidecar(pdf)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    flagged = []
    snapshot = {}
    for o in doc.objects.values():
        if o.type != "Equation" or not o.props.get("cdn_url"):
            continue
        s = o.props.get("score") or {}
        if not s.get("flags"):
            continue
        # Skip ones that already have an LLM reading (nothing new to ask).
        if any(r.role == "latex_candidate" and r.provenance == "llm"
               for r in o.realizations):
            continue
        flagged.append({
            "eq_id": o.id,
            "refnum": o.props.get("refnum") or "",
            "page": o.props.get("page"),
            "cdn_url": o.props["cdn_url"],
            "mathpix_latex": o.props.get("latex", ""),
            "current_flags": s.get("flags"),
            "current_min_signal": s.get("min_signal"),
            "latex": "",
        })
        snapshot[o.id] = {"before_min_signal": s.get("min_signal"),
                          "before_flags": s.get("flags")}
    if limit is not None:
        flagged = flagged[:limit]
        snapshot = {e["eq_id"]: snapshot[e["eq_id"]] for e in flagged}

    manifest = {"bibkey": doc.meta.get("bibkey", pdf.stem), "provider": "llm",
                "instructions": _ESCALATE_PROMPT, "equations": flagged}
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    out_path = sc.blob_dir / "escalate.llm.json"
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                        encoding="utf-8")

    sc.set_evidence("escalation", snapshot)
    sc.set_evidence("escalation_count", len(flagged))
    sc.add_fact(ESCALATION_OPEN)
    sc.save()
    rel = out_path.relative_to(sc.pdf_path.parent)
    return (
        f"Escalated {len(flagged)} flagged equation(s) → {rel}. Provide LLM "
        f"readings (look at each `cdn_url`), then:\n"
        f"  pdfdrill ingest {pdf.name} {rel} --provider llm\n"
        f"  pdfdrill relearn {pdf.name}"
    )


def cmd_relearn(pdf: Path) -> str:
    """Phase-3 step 2: re-score and report what the new readings resolved.

    Compares each escalated equation's signal against the pre-escalation
    snapshot: resolved (flags cleared), improved (signal up, still flagged),
    or still-shaky.
    """
    from docmodel.core import Document

    sc = Sidecar(pdf)
    snapshot = sc.get_evidence("escalation", {}) or {}
    if not snapshot:
        return ("No open escalation. Run `pdfdrill escalate <pdf>`, ingest the "
                "readings, then `pdfdrill relearn`.")

    cmd_score(pdf, force=True)        # recompute with the newly ingested readings
    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    resolved = improved = still = 0
    shaky: list[str] = []
    for eq_id, before in snapshot.items():
        o = doc.objects.get(eq_id)
        if o is None:
            continue
        s = o.props.get("score") or {}
        before_flags = before.get("before_flags") or []
        before_sig = before.get("before_min_signal")
        now_flags = s.get("flags") or []
        now_sig = s.get("min_signal")
        if before_flags and not now_flags:
            resolved += 1
        elif now_flags:
            if before_sig is not None and now_sig is not None and now_sig > before_sig:
                improved += 1
            else:
                still += 1
            shaky.append(f"ref {o.props.get('refnum') or '?'} {now_flags}")
        # else: was not flagged / nothing to do

    sc.set_evidence("relearn_resolved", resolved)
    sc.set_evidence("relearn_improved", improved)
    sc.set_evidence("relearn_still", still)
    prev = ",".join(sorted(sc.facts - {SCORED})) or "INIT"
    sc.log_transition("relearn", prev, SCORED,
                      detail=f"{resolved} resolved, {improved} improved, {still} still")
    sc.save()

    lines = [f"Relearn: {resolved} resolved, {improved} improved, "
             f"{still} still flagged (of {len(snapshot)} escalated)."]
    if shaky:
        lines.append("Still shaky: " + "; ".join(shaky[:10]))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Link annotations as first-class model nodes
# ---------------------------------------------------------------------------

def cmd_annotate(pdf: Path, force: bool = False) -> str:
    """Promote hyperlink annotations into the model as `Link` DocObjects.

    Pulls the rich `urls` layer (auto-running `urls` if needed) and lifts each
    record into a Link node (uri/anchor_text/context + a Region for the rect),
    so annotations — including code links with no visible text — become
    queryable graph nodes instead of living only in the sidecar.
    """
    from docmodel.core import Document
    from .annotations import add_link_objects, link_xref_alignments

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(MODEL_BUILT) or not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."
    if not sc.has(URLS_KNOWN):
        cmd_urls(pdf)
        sc = Sidecar(pdf)
    records = sc.urls or []

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    existing = [o for o in doc.objects.values() if o.type == "Link"]
    if existing and not force:
        return _format_annotations(sc)
    if force and existing:
        ids = {o.id for o in existing}
        for o in existing:
            doc.objects.pop(o.id, None)
        doc.alignments = [a for a in doc.alignments if a.kind not in ("cites", "xref")]

    created = add_link_objects(doc, records)
    xref = link_xref_alignments(doc, created)
    code = sum(1 for r in records if _is_code_host(r.get("uri") or ""))

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    sc.set_evidence("annotation_links", len(created))
    sc.set_evidence("annotation_code_links", code)
    sc.set_evidence("annotation_cites", xref["cites"])
    sc.set_evidence("annotation_xrefs", xref["xrefs"])
    prev = ",".join(sorted(sc.facts - {ANNOTATIONS_BUILT})) or "INIT"
    sc.add_fact(ANNOTATIONS_BUILT)
    sc.log_transition("annotate", prev, ANNOTATIONS_BUILT,
                      detail=f"{len(created)} links, {code} code/data, "
                             f"{xref['cites']} cites, {xref['xrefs']} xrefs")
    sc.save()
    return _format_annotations(sc)


def _format_annotations(sc: Sidecar) -> str:
    n = sc.get_evidence("annotation_links", 0)
    code = sc.get_evidence("annotation_code_links", 0)
    cites = sc.get_evidence("annotation_cites", 0)
    xrefs = sc.get_evidence("annotation_xrefs", 0)
    extra = f" ({code} to code/data hosts)" if code else ""
    edges = []
    if cites:
        edges.append(f"{cites} cite edges")
    if xrefs:
        edges.append(f"{xrefs} page xrefs")
    edge_s = f" Graph: {', '.join(edges)}." if edges else ""
    return (f"Promoted {n} hyperlink annotation(s) into the model as Link "
            f"nodes{extra}. Each carries uri/kind/anchor_text/context + a "
            f"Region (rect).{edge_s}")


# ---------------------------------------------------------------------------
# External-provenance candidates (LLM, or any tool): export manifest + ingest
# ---------------------------------------------------------------------------

_LLM_PROMPT = (
    "For each entry below, open the image at `cdn_url` and transcribe ONLY the "
    "mathematics as a single LaTeX string (no surrounding $ or \\[ \\]; use "
    "\\begin{aligned}...\\end{aligned} for multi-line). Return a JSON list of "
    '{"eq_id": <unchanged>, "latex": <your LaTeX>}. Keep eq_id exactly as given.'
)


def cmd_candidates(pdf: Path, provider: str = "llm",
                   limit: int | None = None, out: str | None = None) -> str:
    """Export a manifest of equation crops for an external reader (e.g. an LLM).

    Writes JSON the reader fills in: per equation its id, refnum, page,
    `cdn_url` (the crop to look at) and the MathPix LaTeX for reference. The
    reader returns a list of {eq_id, latex}; feed it back with `pdfdrill
    ingest`. This keeps pdfdrill pure-Python — the LLM (claude.ai web, or an
    agent) supplies the vision, not an embedded API client.
    """
    from docmodel.core import Document

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(MODEL_BUILT) or not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    entries = []
    for e in doc.objects.values():
        if e.type != "Equation" or not e.props.get("cdn_url"):
            continue
        has = any(r.role == "latex_candidate" and r.provenance == provider
                  for r in e.realizations)
        if has:
            continue
        entries.append({
            "eq_id": e.id,
            "refnum": e.props.get("refnum") or "",
            "page": e.props.get("page"),
            "cdn_url": e.props["cdn_url"],
            "mathpix_latex": e.props.get("latex", ""),
            "latex": "",  # <- the reader fills this in
        })
    if limit is not None:
        entries = entries[:limit]

    manifest = {
        "bibkey": doc.meta.get("bibkey", pdf.stem),
        "provider": provider,
        "instructions": _LLM_PROMPT,
        "equations": entries,
    }
    out_path = Path(out) if out else (sc.blob_dir / f"candidates.{provider}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    try:
        rel = out_path.relative_to(sc.pdf_path.parent)
    except ValueError:
        rel = out_path
    return (
        f"Wrote {len(entries)} '{provider}' candidate slots to {rel}. "
        f"Have the reader fill each entry's \"latex\" (look at \"cdn_url\"), "
        f"then: pdfdrill ingest {pdf.name} {rel} --provider {provider}"
    )


def cmd_ingest(pdf: Path, candidates_path: str, provider: str = "llm",
               force: bool = False) -> str:
    """Attach externally-produced LaTeX candidates to the model.

    Accepts a manifest from `pdfdrill candidates` (with each entry's "latex"
    filled), or a bare list of {eq_id, latex[, confidence]}. Each becomes a
    `latex_candidate` realization with the given provenance, so the comparison
    table grows a column for it.
    """
    from docmodel.core import Document, Realization

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    with open(candidates_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        provider = data.get("provider", provider)
        items = data.get("equations") or data.get("candidates") or []
    else:
        items = data

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    attached = skipped = 0
    for it in items:
        eq_id = it.get("eq_id") or it.get("id")
        latex = (it.get("latex") or "").strip()
        if not eq_id or not latex:
            continue
        obj = doc.objects.get(eq_id)
        if obj is None:
            continue
        has = any(r.role == "latex_candidate" and r.provenance == provider
                  for r in obj.realizations)
        if has and not force:
            skipped += 1
            continue
        if force:
            obj.realizations = [r for r in obj.realizations
                                if not (r.role == "latex_candidate" and r.provenance == provider)]
        obj.add_realization(Realization(
            stream=provider, role="latex_candidate", provenance=provider,
            score=it.get("confidence") if it.get("confidence") is not None else it.get("score"),
            props={"latex": latex},
        ))
        attached += 1

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    fact = f"CANDIDATES_{provider.upper()}"
    sc.set_evidence(f"candidates_{provider}_count",
                    (sc.get_evidence(f"candidates_{provider}_count", 0) or 0) + attached)
    prev = ",".join(sorted(sc.facts - {fact})) or "INIT"
    sc.add_fact(fact)
    sc.log_transition("ingest", prev, fact, detail=f"{attached} {provider} candidates")
    sc.save()
    msg = f"Ingested {attached} '{provider}' candidate(s)"
    if skipped:
        msg += f" ({skipped} already present; use --force to replace)"
    msg += f". Run `pdfdrill compare {pdf.name}` to see the {provider} column."
    return msg


# ---------------------------------------------------------------------------
# OpenAI GPT-4o vision — extract LaTeX/TikZ/gnuplot/table from CDN crops that
# MathPix left as an image (incl. CDN links embedded inside table cells).
# ---------------------------------------------------------------------------

_CDN_CROP_RE = re.compile(r'https://cdn\.mathpix\.com/cropped/\S+?\.jpg\?[^)"\s\\]*')
# A well-formed MathPix cropped-page URL (page image + rectangle query).
_VALID_CROP = re.compile(
    r'^https://cdn\.mathpix\.com/cropped/[\w.-]+\.jpg\?'
    r'(?=.*height=\d+)(?=.*width=\d+)(?=.*top_left_y=\d+)(?=.*top_left_x=\d+)\S+$')


def _norm_crop_url(u: str) -> Optional[str]:
    """Normalize a crop URL or return None if it isn't a valid crop link.

    MathPix sometimes leaves LaTeX-escaped `\\&` in a URL stored inside a table
    cell (`![](cdn…\\&width=…)`); URL-based routes (vision, snip, download) 400
    on that. We unescape `\\&`→`&`, trim trailing punctuation, and validate the
    page+rectangle shape so `cnt`-array fragments and truncated links are
    dropped rather than handed to a fetcher.
    """
    if not u:
        return None
    u = u.replace("\\&", "&").replace("\\%", "%").strip().rstrip(').,"\'')
    return u if _VALID_CROP.match(u) else None


def _collect_cdn_crops(doc) -> list[tuple]:
    """Yield (object, crop_url) for every well-formed MathPix CDN crop.

    Picks up an object's own `cdn_url`/`url` AND any crop embedded in a string
    prop (e.g. a table cell's `![](cdn…)` left in `raw_text`). Every URL is
    normalized + validated by `_norm_crop_url`, so the (object, url) pairs are
    always fetchable. De-duplicated per (object, url).
    """
    out: list[tuple] = []
    seen: set = set()
    for o in doc.objects.values():
        candidates: list[str] = []
        for k in ("cdn_url", "url"):
            v = (o.props or {}).get(k)
            if isinstance(v, str) and "cdn.mathpix.com/cropped" in v:
                candidates.append(v)
        for v in (o.props or {}).values():
            if isinstance(v, str) and "cdn.mathpix.com/cropped" in v:
                candidates.extend(_CDN_CROP_RE.findall(v.replace("\\&", "&")))
        for cand in candidates:
            u = _norm_crop_url(cand)
            key = (o.id, u)
            if u and key not in seen:
                seen.add(key)
                out.append((o, u))
    return out


def cmd_vision(pdf: Path, limit: int | None = None, force: bool = False) -> str:
    """Read every MathPix CDN crop with GPT-4o vision (the `openai` provenance).

    For each crop (equation/picture/diagram image, or a CDN link MathPix left
    inside a table cell) the model returns a `selector`
    (math/tikzpicture/commutative_diagram/gnuplot/tensor/table/empty) plus the
    corresponding LaTeX/TikZ/table code; we attach it as a
    `provenance="openai"` `latex_candidate` realization (with `selector` and any
    gnuplot/csv_data). Needs `OPENAI_API_KEY` (env / .env). Auto-chains `model`.
    """
    from collections import Counter
    from docmodel.core import Document, Realization
    from . import openai_vision

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(MODEL_BUILT) or not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."
    if not openai_vision.available():
        return ("OpenAI vision unavailable: set OPENAI_API_KEY in the "
                "environment or .env (https://platform.openai.com/api-keys), "
                "then rerun `pdfdrill vision`.")

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    def _has_openai(o, url):
        return any(r.role == "latex_candidate" and r.provenance == "openai"
                   and (r.props or {}).get("url") == url for r in o.realizations)

    targets = _collect_cdn_crops(doc)
    todo = [(o, u) for (o, u) in targets if force or not _has_openai(o, u)]
    if limit is not None:
        todo = todo[:limit]

    t0 = time.monotonic()
    processed = 0
    by_sel: Counter = Counter()
    errors = 0
    api_calls = 0
    url_cache: dict[str, tuple] = {}   # the same crop can hang off >1 object
    for o, url in todo:
        if url in url_cache:
            selector, code, res = url_cache[url]
        else:
            try:
                res = openai_vision.analyze_image(url)
            except Exception:
                errors += 1
                continue
            api_calls += 1
            selector, code = openai_vision.result_to_latex(res)
            url_cache[url] = (selector, code, res)
        if force:
            o.realizations = [r for r in o.realizations
                              if not (r.role == "latex_candidate"
                                      and r.provenance == "openai"
                                      and (r.props or {}).get("url") == url)]
        o.add_realization(Realization(
            stream="openai", role="latex_candidate", provenance="openai",
            props={"url": url, "selector": selector, "latex": code,
                   "gnuplot": res.get("gnuplot", ""),
                   "csv_data": res.get("csv_data", "")},
        ))
        processed += 1
        by_sel[selector or "?"] += 1

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    sc.set_evidence("vision_crops_total", len(targets))
    sc.set_evidence("vision_processed",
                    (sc.get_evidence("vision_processed", 0) or 0) + processed)
    prev = ",".join(sorted(sc.facts - {VISION_DONE})) or "INIT"
    sc.add_fact(VISION_DONE)
    sc.log_transition("vision", prev, VISION_DONE,
                      cost_ms=(time.monotonic() - t0) * 1000,
                      detail=f"{processed} attached / {api_calls} API calls, {errors} errors")
    sc.save()

    sel_s = ", ".join(f"{n} {s}" for s, n in by_sel.most_common()) or "none"
    err_s = f", {errors} error(s)" if errors else ""
    dedup_s = f" ({api_calls} GPT-4o calls; {processed - api_calls} reused across objects)" if processed > api_calls else ""
    remaining = len(targets) - processed if limit is None else max(0, len(targets) - len(todo))
    return (
        f"OpenAI vision: read {processed} CDN crop(s){dedup_s} ({sel_s}){err_s}; "
        f"{len(targets)} total crops in the model. Attached as the 'openai' "
        f"provenance (selector + LaTeX/TikZ/table). "
        f"Run `pdfdrill compare {pdf.name}` to see the column."
        + (f" {remaining} crop(s) not yet read — raise --limit to continue."
           if (limit is not None and len(todo) >= limit and remaining > 0) else "")
    )


def cmd_embedimages(pdf: Path, force: bool = False) -> str:
    """Wire embedded raster images (pdfplumber rects + `pdfimages -list`) into
    the model as `EmbeddedImage` nodes, fused onto MathPix Picture/Diagram crops.

    Each embedded image becomes a DocObject with a `Region` (PDF points) + its
    pdfimages metadata (true pixel size, encoding, colour, ppi, file size); a
    MathPix crop contained within an image is linked by
    `Alignment(kind="image_region")` so every route to an image lives on one
    graph. Auto-chains `model`.
    """
    from docmodel.core import Document
    from . import image_model
    from .font_image_layers import fetch_image_layer

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(MODEL_BUILT) or not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    t0 = time.monotonic()
    image_layer = fetch_image_layer(pdf)
    page_dims = image_model.fetch_page_dims_pts(pdf)

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))
    stats = image_model.attach_embedded_images(
        doc, image_layer, page_dims, bibkey=pdf.stem)
    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    sc.set_evidence("embedded_images", stats["created"])
    sc.set_evidence("embedded_images_fused", stats["fused"])
    prev = ",".join(sorted(sc.facts - {EMBEDDED_IMAGES_BUILT})) or "INIT"
    sc.add_fact(EMBEDDED_IMAGES_BUILT)
    sc.log_transition("embedimages", prev, EMBEDDED_IMAGES_BUILT,
                      cost_ms=(time.monotonic() - t0) * 1000,
                      detail=f"{stats['created']} images, {stats['fused']} fused")
    sc.save()
    return (
        f"Embedded images: {stats['created']} pdfimages/pdfplumber image(s) "
        f"lifted into the model as EmbeddedImage nodes (Region in PDF points + "
        f"pixel size/encoding/colour/ppi). {stats['fused']} MathPix crop(s) "
        f"linked to the image containing them (Alignment 'image_region'); "
        f"{stats['with_coords']} image(s) had positions to fuse. Every route to "
        f"an image (CDN crop, vision read, XObject metadata, page rect) now "
        f"hangs off one graph."
    )


# ---------------------------------------------------------------------------
# Links — the fast "where is the code/data?" path (annotation layer only)
# ---------------------------------------------------------------------------

_PDFINFO_URL_RE = re.compile(r"^\s*(\d+)\s+\S+\s+(https?://\S+)\s*$")


def _parse_pdfinfo_urls(text: str) -> list[dict]:
    """Parse `pdfinfo -url` output into [{page, url}] (external links only)."""
    out: list[dict] = []
    for line in text.splitlines():
        m = _PDFINFO_URL_RE.match(line)
        if m:
            out.append({"page": int(m.group(1)), "url": m.group(2)})
    return out


def _is_code_host(url: str) -> bool:
    u = url.lower()
    return any(h in u for h in _CODE_HOSTS)


def cmd_links(pdf: Path) -> str:
    """List external URL annotations via `pdfinfo -url` (~50 ms).

    This reads the PDF *annotation layer*, so it catches hyperlinks that have
    no visible anchor text — the common case for a paper's code release. It is
    the fast path for "where is the source code / dataset?"; escalate to
    `urls` only when you need the visible anchor text, and never use the
    Markdown/MathPix path for this (rendered text omits annotation-only links).
    """
    sc = Sidecar(pdf)
    if sc.has(LINKS_KNOWN):
        return _format_links(sc.get_evidence("links", []))

    t0 = time.monotonic()
    out = subprocess.run(
        ["pdfinfo", "-url", str(pdf)], capture_output=True, text=True, timeout=30,
    )
    parsed = _parse_pdfinfo_urls(out.stdout)
    # Deduplicate by URL, keeping the earliest page it appears on.
    seen: set[str] = set()
    links: list[dict] = []
    for l in parsed:
        if l["url"] not in seen:
            seen.add(l["url"])
            links.append(l)

    sc.set_evidence("links", links)
    prev = ",".join(sorted(sc.facts - {LINKS_KNOWN})) or "INIT"
    sc.add_fact(LINKS_KNOWN)
    sc.log_transition(
        "links", prev, LINKS_KNOWN, cost_ms=(time.monotonic() - t0) * 1000,
        detail=f"{len(links)} external urls",
    )
    sc.save()
    return _format_links(links)


def _format_links(links: list[dict] | None) -> str:
    if not links:
        return ("No external URL annotations found. (Use `pdfdrill urls` for "
                "anchor-text-level analysis of internal/visible links.)")
    code = [l for l in links if _is_code_host(l["url"])]
    lines: list[str] = []
    if code:
        lines.append("Likely source-code / data links:")
        for l in code:
            lines.append(f"  p.{l['page']}  {l['url']}")
        lines.append("")
    lines.append(f"All external URL annotations ({len(links)}):")
    for l in links[:40]:
        lines.append(f"  p.{l['page']}  {l['url']}")
    if len(links) > 40:
        lines.append(f"  ... and {len(links) - 40} more")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Introspection commands
# ---------------------------------------------------------------------------

def cmd_size(pdf: Path) -> str:
    """Run pdfinfo. Return one paragraph of metadata."""
    sc = Sidecar(pdf)

    if sc.has(SIZE_KNOWN):
        return _format_size(sc)

    t0 = time.monotonic()
    out = subprocess.run(
        ["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=30,
    )
    info = {}
    for line in out.stdout.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            info[k.strip()] = v.strip()

    sc.set_evidence("pages", int(info.get("Pages", "0")))
    sc.set_evidence("bytes", pdf.stat().st_size)
    sc.set_evidence("page_size", info.get("Page size", ""))
    sc.set_evidence("producer", info.get("Producer", ""))
    sc.set_evidence("creator", info.get("Creator", ""))
    sc.set_evidence("encrypted", info.get("Encrypted", "no") != "no")
    sc.set_evidence("pdfinfo", info)

    # Determine the text layer NOW (the key level-0 signal): a scanned PDF has
    # no extractable text and no fonts -> OCR is mandatory. Two cheap probes:
    # the first page's extractable chars (pdftotext -l 1) and the font count.
    has_text, n_fonts, n_chars = _probe_text_layer(pdf)
    sc.set_evidence("text_layer", has_text)
    sc.set_evidence("font_count", n_fonts)
    sc.set_evidence("first_page_chars", n_chars)
    sc.set_evidence("needs_ocr", not has_text)

    sc.add_fact(SIZE_KNOWN)
    elapsed = time.monotonic() - t0
    sc.log_transition("size", "INIT", SIZE_KNOWN, cost_ms=elapsed * 1000,
                      detail=f"pdfinfo: {sc.page_count} pages, {sc.file_size} bytes, "
                             f"text_layer={has_text}")
    sc.save()
    return _format_size(sc)


def _probe_text_layer(pdf: Path) -> tuple[bool, int, int]:
    """Cheap scan detector. Returns (has_text_layer, n_fonts, first_page_chars).

    A born-digital PDF has embedded fonts AND extractable text; a scan has
    neither (just a page-image). We check both because some PDFs carry fonts
    only for headers/stamps yet are otherwise images, and some carry an OCR
    text layer with no listed fonts — requiring real characters on page 1 is
    the robust signal, fonts the corroborator."""
    n_fonts = 0
    try:
        fout = subprocess.run(["pdffonts", str(pdf)], capture_output=True,
                              text=True, timeout=30)
        rows = fout.stdout.strip().splitlines()
        n_fonts = max(0, len(rows) - 2)  # minus the 2 header rows
    except Exception:
        pass
    n_chars = 0
    try:
        tout = subprocess.run(["pdftotext", "-l", "1", str(pdf), "-"],
                              capture_output=True, text=True, timeout=60)
        n_chars = len("".join(tout.stdout.split()))
    except Exception:
        pass
    # Text layer iff page 1 yields real characters (a handful, to ignore stray
    # artifacts). Fonts alone don't prove extractable text.
    has_text = n_chars >= 4
    return has_text, n_fonts, n_chars


def _format_size(sc: Sidecar) -> str:
    pages = sc.page_count
    size_mb = sc.file_size / 1_000_000
    producer = sc.get_evidence("producer", "unknown")
    encrypted = sc.get_evidence("encrypted", False)
    page_size = sc.get_evidence("page_size", "")

    parts = [f"{pages}-page PDF, {size_mb:.1f} MB"]
    if page_size:
        parts.append(page_size.split("(")[-1].rstrip(")") if "(" in page_size else page_size)
    parts.append(f"produced by {producer}")
    if sc.get_evidence("text_layer"):
        parts.append("has a text layer")
    else:
        parts.append("NO text layer — scanned, OCR required (run `pdfdrill mathpix`)")
    if encrypted:
        parts.append("ENCRYPTED")
    else:
        parts.append("not encrypted")

    return ", ".join(parts) + "."


def cmd_fonts(pdf: Path) -> str:
    """Run pdffonts. Return sentence summary of fonts."""
    sc = Sidecar(pdf)

    if not sc.has(SIZE_KNOWN):
        cmd_size(pdf)
        sc = Sidecar(pdf)

    if sc.has(FONTS_KNOWN):
        return _format_fonts(sc)

    t0 = time.monotonic()
    out = subprocess.run(
        ["pdffonts", str(pdf)], capture_output=True, text=True, timeout=60,
    )

    fonts = []
    lines = out.stdout.strip().splitlines()
    for line in lines[2:]:
        parts = line.split()
        if parts:
            fonts.append(parts[0])

    math_kw = ["math", "symbol", "msbm", "eufm", "cmsy", "cmmi", "cmex",
               "mt2mi", "mt2sy", "newpxmi", "pxsy", "msam"]
    math_fonts = [f for f in fonts if any(k in f.lower() for k in math_kw)]

    sc.set_evidence("fonts", fonts)
    sc.set_evidence("math_fonts", math_fonts)
    sc.set_evidence("has_math_fonts", len(math_fonts) > 0)
    sc.set_evidence("font_count", len(fonts))
    # The authoritative text-layer signal is page-1 extractable chars, set by
    # `size` (_probe_text_layer). Only fill it here if size never ran; don't
    # let a stray stamp font flip a scanned PDF back to "has text layer".
    if sc.get_evidence("text_layer") is None:
        sc.set_evidence("text_layer", len(fonts) > 0)
        sc.set_evidence("needs_ocr", len(fonts) == 0)

    sc.add_fact(FONTS_KNOWN)
    elapsed = time.monotonic() - t0
    sc.log_transition("fonts", SIZE_KNOWN, FONTS_KNOWN, cost_ms=elapsed * 1000,
                      detail=f"{len(fonts)} fonts, {len(math_fonts)} math")
    sc.save()
    return _format_fonts(sc)


def _format_fonts(sc: Sidecar) -> str:
    fonts = sc.get_evidence("fonts", [])
    math_fonts = sc.get_evidence("math_fonts", [])

    # Deduplicate by base name (strip subset prefix)
    base_fonts = set()
    for f in fonts:
        name = f.split("+")[-1] if "+" in f else f
        base_fonts.add(name.split("-")[0])

    parts = [f"Uses {len(base_fonts)} font families"]
    if math_fonts:
        math_names = ", ".join(set(f.split("+")[-1].split("-")[0] for f in math_fonts[:4]))
        parts.append(f"including math fonts ({math_names})")
        parts.append("pdfplumber extraction will detect math expressions")
    else:
        parts.append("no math fonts detected")
        parts.append("math expressions may need MathPix for recognition")

    return ". ".join(parts) + "."


def cmd_toc(pdf: Path) -> str:
    """Extract the table of contents.

    Cheap path: pdftotext on the first 3 pages, regex for numbered
    sections. If the MD is built, re-derive from the markdown's heading
    structure (this is the superseding path).
    """
    sc = Sidecar(pdf)

    if not sc.has(SIZE_KNOWN):
        cmd_size(pdf)
        sc = Sidecar(pdf)

    if sc.has(TOC_KNOWN):
        return _format_toc(sc)

    prev_scope = sc.get_evidence("toc_search_scope")
    have_md = sc.has(MD_BUILT)
    desired_scope = "markdown" if have_md else "first3pages"

    if sc.has(TOC_ABSENT) and not _can_supersede(prev_scope, desired_scope):
        return _format_toc(sc)

    t0 = time.monotonic()
    toc: list[dict] = []

    if have_md:
        md_blob = sc.read_blob("md.md") or ""
        toc = _extract_toc_from_markdown(md_blob)
        actual_scope = "markdown"
    else:
        last = min(3, sc.page_count or 3)
        out = subprocess.run(
            ["pdftotext", "-f", "1", "-l", str(last), "-layout", str(pdf), "-"],
            capture_output=True, text=True, timeout=30,
        )
        toc = _extract_toc_from_layout_text(out.stdout)
        actual_scope = "first3pages"

    sc = Sidecar(pdf)
    if toc:
        if sc.has(TOC_ABSENT):
            facts = [f for f in sc._data.get("facts", []) if f != TOC_ABSENT]
            sc._data["facts"] = facts
        sc.set_evidence("toc", toc)
        sc.set_evidence("toc_search_scope", actual_scope)
        sc.add_fact(TOC_KNOWN)
        fact = TOC_KNOWN
    else:
        sc.set_evidence("toc_search_scope", actual_scope)
        sc.add_fact(TOC_ABSENT)
        fact = TOC_ABSENT

    elapsed = time.monotonic() - t0
    prev = ",".join(sorted(sc.facts - {fact})) or "INIT"
    sc.log_transition("toc", prev, fact, cost_ms=elapsed * 1000,
                      detail=f"scope={actual_scope}")
    sc.save()
    return _format_toc(sc)


def _extract_toc_from_layout_text(text: str) -> list[dict]:
    """Scrape TOC entries from `pdftotext -layout` output (front pages)."""
    toc_entries = re.findall(
        r"^(\d+(?:\.\d+)*)\s+([A-Z].*?)(?:\s{2,}(\d+))?\s*$",
        text, re.MULTILINE,
    )
    if len(toc_entries) >= 3:
        return [{"number": e[0], "title": e[1].strip(), "page": e[2] or ""}
                for e in toc_entries[:30]]
    heading_pattern = re.findall(
        r"^(\d+)\s+([A-Z][A-Za-z ]{3,50})\s*$", text, re.MULTILINE,
    )
    if len(heading_pattern) >= 2:
        return [{"number": h[0], "title": h[1].strip(), "page": ""}
                for h in heading_pattern[:20]]
    return []


def _extract_toc_from_markdown(md: str) -> list[dict]:
    """Build a TOC from heading lines in the built markdown."""
    entries: list[dict] = []
    counter = {1: 0, 2: 0, 3: 0}
    for m in re.finditer(r"(?m)^(#{1,3})\s+(.+?)$", md):
        level = len(m.group(1))
        title = m.group(2).strip()
        # Skip TOC lines like "# Abstract  7" — these are usually short and
        # end with a page number. We're after real section headings, but
        # we accept the TOC entries too if there's no plain-heading set.
        counter[level] = counter[level] + 1
        # Reset deeper counters
        for d in range(level + 1, 4):
            counter[d] = 0
        number = ".".join(str(counter[i]) for i in range(1, level + 1))
        entries.append({"number": number, "title": title, "page": "",
                        "level": level})
    return entries[:50]


def _format_toc(sc: Sidecar) -> str:
    if sc.has(TOC_ABSENT):
        return f"No table of contents found; the document is {sc.page_count} pages and likely doesn't have one."

    toc = sc.get_evidence("toc", [])
    if not toc:
        return "No TOC entries detected."

    lines = [f"Table of contents ({len(toc)} sections):"]
    for entry in toc:
        page = f" (p.{entry['page']})" if entry.get("page") else ""
        lines.append(f"  {entry['number']}  {entry['title']}{page}")
    return "\n".join(lines)


# Scopes — narrow → wide. A wider scope supersedes the same fact stored at
# a narrower scope, so calling `abstract` again after `md` was built will
# retry on the markdown.
_SCOPE_ORDER = {
    "first2pages": 1,
    "first3pages": 2,
    "first5pages": 3,
    "markdown": 4,
}


def _can_supersede(prev_scope: str | None, new_scope: str) -> bool:
    if not prev_scope:
        return True
    return _SCOPE_ORDER.get(new_scope, 0) > _SCOPE_ORDER.get(prev_scope, 0)


def cmd_abstract(pdf: Path) -> str:
    """Extract the abstract.

    Cheap path: pdftotext on the first two pages with regex match.
    If that fails, the absent fact is stored at scope=first2pages.
    Re-call after `pdfdrill md` has built the markdown will retry on
    the markdown (scope=markdown) since markdown is a strictly wider
    source. This is the state-machine supersession mechanism.
    """
    sc = Sidecar(pdf)

    if not sc.has(SIZE_KNOWN):
        cmd_size(pdf)
        sc = Sidecar(pdf)

    if sc.has(ABSTRACT_KNOWN):
        return _format_abstract(sc)

    prev_scope = sc.get_evidence("abstract_search_scope")
    have_md = sc.has(MD_BUILT)
    desired_scope = "markdown" if have_md else "first2pages"

    # If the previous absent verdict was at a narrower scope than what is
    # available now, drop it and retry.
    if sc.has(ABSTRACT_ABSENT) and not _can_supersede(prev_scope, desired_scope):
        return _format_abstract(sc)

    # Try the widest available source first.
    t0 = time.monotonic()
    abstract = None
    method_used = None

    if have_md:
        md_blob = sc.read_blob("md.md") or ""
        abstract = _extract_abstract_from_markdown(md_blob)
        if abstract:
            method_used = "markdown-heading"
        actual_scope = "markdown"
    else:
        out = subprocess.run(
            ["pdftotext", "-f", "1", "-l", "2", "-layout", str(pdf), "-"],
            capture_output=True, text=True, timeout=30,
        )
        abstract = _extract_abstract_text(out.stdout)
        if abstract:
            method_used = "pdftotext-2pages"
        actual_scope = "first2pages"

    # Re-load the sidecar in case earlier state changed
    sc = Sidecar(pdf)
    if abstract:
        # Clear an obsolete absent flag if we previously stored one
        if sc.has(ABSTRACT_ABSENT):
            facts = [f for f in sc._data.get("facts", []) if f != ABSTRACT_ABSENT]
            sc._data["facts"] = facts
        sc.set_evidence("abstract", abstract)
        sc.set_evidence("abstract_method", method_used)
        sc.set_evidence("abstract_search_scope", actual_scope)
        sc.add_fact(ABSTRACT_KNOWN)
        fact = ABSTRACT_KNOWN
    else:
        sc.set_evidence("abstract_search_scope", actual_scope)
        sc.add_fact(ABSTRACT_ABSENT)
        fact = ABSTRACT_ABSENT

    elapsed = time.monotonic() - t0
    prev = ",".join(sorted(sc.facts - {fact})) or "INIT"
    sc.log_transition(
        "abstract", prev, fact, cost_ms=elapsed * 1000,
        detail=f"scope={actual_scope} method={method_used or 'none'}",
    )
    sc.save()
    return _format_abstract(sc)


def _extract_abstract_text(text: str) -> str | None:
    m = re.search(r"(?i)abstract\s*\n(.*?)(?:\n\s*\n|\n\d+\s|\nIntroduction|\n1\s)",
                  text, re.DOTALL)
    if m and len(m.group(1).strip()) > 30:
        return m.group(1).strip()
    return None


def _extract_abstract_from_markdown(md: str) -> str | None:
    """Find an Abstract section in a built markdown.

    Skips TOC entries (single-line `# Abstract N` where N is a page number)
    and locks onto the actual section body, which is followed by paragraph
    text rather than another heading or a page number.
    """
    # Find every `# Abstract` or `## Abstract` heading
    for m in re.finditer(r"(?im)^#{1,4}\s*abstract\b[^\n]*$", md):
        rest = md[m.end():].lstrip("\n")
        # Skip if this heading is immediately followed by another heading or
        # is a TOC line (very short, ends with a number).
        first_para = rest.split("\n\n", 1)[0].strip()
        if not first_para or first_para.startswith("#"):
            continue
        if len(first_para) < 80:
            continue
        return first_para
    return None


def _format_abstract(sc: Sidecar) -> str:
    if sc.has(ABSTRACT_KNOWN):
        abstract = sc.get_evidence("abstract", "")
        method = sc.get_evidence("abstract_method", "")
        suffix = f" (via {method})" if method else ""
        return f"Abstract{suffix}:\n\n{abstract}"
    if sc.has(ABSTRACT_ABSENT):
        scope = sc.get_evidence("abstract_search_scope", "unknown")
        if scope == "markdown":
            return ("No abstract block detected anywhere in the document "
                    "(searched the full markdown).")
        return ("No abstract block detected on the first two pages. "
                "Run `pdfdrill md` to build the markdown, then try again — "
                "this re-scans the full document.")
    return "Abstract not yet extracted."


def cmd_status(pdf: Path) -> str:
    """Report what is already known, no subprocess."""
    sc = Sidecar(pdf)
    facts = sc.facts
    if not facts:
        return f"No information gathered yet for {pdf.name}. Run `pdfdrill size` to start."

    parts = [f"For {pdf.name} I have:"]
    if SIZE_KNOWN in facts:
        parts.append(f"  size info ({sc.page_count} pages, {sc.file_size/1e6:.1f} MB)")
    if PDFINFO_KNOWN in facts:
        info = sc.pdfinfo or {}
        title = info.get("title") or "(no title)"
        parts.append(f"  pdfinfo struct (title: {title[:60]})")
    if BIBTEX_KNOWN in facts:
        bib = sc.bibtex or {}
        parts.append(f"  BibTeX record ({bib.get('citekey','?')}, "
                     f"entry type: {bib.get('entry_type','?')})")
    if URLS_KNOWN in facts:
        links = sc.urls or []
        n_url = sum(1 for r in links if r.get("kind") == "url")
        n_int = sum(1 for r in links if r.get("kind") == "internal")
        parts.append(f"  URLs layer ({n_url} URL, {n_int} internal links)")
    if DESTS_KNOWN in facts:
        n = len(sc.dests or [])
        parts.append(f"  named destinations ({n} entries)")
    if FONTS_LAYER_KNOWN in facts:
        from .font_image_layers import summarize_fonts
        s = summarize_fonts(sc.fonts_layer or [])
        parts.append(f"  fonts_layer ({s['n_fonts']} fonts, "
                     f"{s['n_families']} families, {s['n_math']} math)")
    if IMAGES_LAYER_KNOWN in facts:
        imgs = sc.images_layer or []
        cand = sum(1 for i in imgs if i.get("candidate_pix2latex"))
        parts.append(f"  images_layer ({len(imgs)} images, "
                     f"{cand} pix2latex candidates)")
    if PIX2TEX_RAN in facts:
        results = sc.pix2tex_results or []
        ok = sum(1 for r in results if "error" not in r)
        parts.append(f"  pix2tex results ({ok} crops OCR'd to LaTeX)")
    if TSV_KNOWN in facts:
        words = sc.tsv_layer or []
        source = sc.get_evidence(TSV_SOURCE, "?")
        parts.append(f"  tsv_layer ({len(words)} words via {source})")
    if FONTS_KNOWN in facts:
        mf = sc.get_evidence("math_fonts", [])
        parts.append(f"  font analysis ({'math fonts present' if mf else 'no math fonts'})")
    if TOC_KNOWN in facts:
        toc = sc.get_evidence("toc", [])
        parts.append(f"  table of contents ({len(toc)} sections)")
    if TOC_ABSENT in facts:
        parts.append("  no TOC found")
    if ABSTRACT_KNOWN in facts:
        parts.append("  abstract extracted")
    if ABSTRACT_ABSENT in facts:
        parts.append("  no abstract found")
    if MD_BUILT in facts:
        md_meta = sc.get_layer("md") or {}
        parts.append(f"  Markdown extracted ({md_meta.get('words', '?')} words)")
    if MMD_BUILT in facts:
        parts.append("  MathPix-style Markdown built")

    last = sc.last_node
    parts.append(f"\nLast action: {last}. {len(sc.transitions)} transitions logged.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Extraction commands
# ---------------------------------------------------------------------------

def cmd_md(pdf: Path, pages: str | None = None) -> str:
    """Build Markdown via pdfplumber + layer pipeline."""
    sc = Sidecar(pdf)

    if not sc.has(SIZE_KNOWN):
        cmd_size(pdf)
    if not sc.has(FONTS_KNOWN):
        cmd_fonts(pdf)

    sc = Sidecar(pdf)

    if sc.has(MD_BUILT) and pages is None:
        md_meta = sc.get_layer("md") or {}
        blob = sc.read_blob("md.md")
        if blob:
            words = len(blob.split())
            return f"Markdown already extracted ({words} words across {sc.page_count} pages). Stored as layer `md`.\n\nUse `pdfdrill fetch {pdf.name} md` to retrieve."

    t0 = time.monotonic()

    # Ensure chars.json exists
    chars_path = pdf.with_suffix(".chars.json")
    if not chars_path.exists():
        _extract_pdfplumber_chars(pdf, pages)

    # Run the layer pipeline
    from .context import DocMeta, DocumentContext
    from .engine import SequentialEngine
    from .nodes.ingest_pdfplumber import IngestPdfplumberNode
    from .nodes.lines_paragraphs import LinesParagraphsNode
    from .nodes.tokenizer import TokenizerNode
    from .nodes.emphasis_detector import EmphasisDetectorNode
    from .nodes.reference_detector import ReferenceDetectorNode
    from .nodes.math_detector import MathDetectorNode
    from .nodes.math_assembler import MathAssemblerNode
    from .nodes.flagger import FlaggerNode
    from .nodes.stub_nlp import StubNlpNode
    from .projectors.markdown import MarkdownProjector

    ctx = DocumentContext(meta=DocMeta(source=pdf.name))
    nodes = [
        IngestPdfplumberNode(chars_path),
        LinesParagraphsNode(), TokenizerNode(), EmphasisDetectorNode(),
        ReferenceDetectorNode(), MathDetectorNode(), MathAssemblerNode(),
        FlaggerNode(), StubNlpNode(),
    ]
    engine = SequentialEngine(nodes, verbose=False)
    ctx = engine.run(ctx)

    md_text = MarkdownProjector().project(ctx)
    elapsed = time.monotonic() - t0

    # Save
    sc = Sidecar(pdf)
    blob_path = sc.write_blob("md.md", md_text)
    ir_json = ctx.to_json()
    sc.write_blob("ir.json", ir_json)

    words = len(md_text.split())
    math_i = sum(1 for s in ctx.L4 if s.kind == "math_inline")
    math_d = sum(1 for s in ctx.L4 if s.kind == "math_display")
    refs = sum(1 for s in ctx.L3 if s.kind in ("citation", "eq_number", "struct_ref"))

    sc.set_layer("md", {
        "blob": blob_path,
        "words": words,
        "math_inline": math_i,
        "math_display": math_d,
        "references": refs,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    sc.add_fact(MD_BUILT)
    sc.log_transition("md", "FONTS_KNOWN", MD_BUILT, cost_ms=elapsed * 1000,
                      detail=f"{words} words, {math_i}+{math_d} math, {refs} refs")
    sc.save()

    # Opportunistic supersession: if abstract/toc were previously absent at
    # a narrower scope, retry against the just-built markdown. Errors here
    # don't fail the md command — they're a best-effort upgrade.
    suppressed = _retry_absents_with_md(pdf)

    summary = (f"Extracted {words} words of Markdown across {sc.page_count} pages. "
               f"Detected {math_i} inline and {math_d} display math expressions, "
               f"{refs} references. Stored as layer `md`.")
    if suppressed:
        summary += "\n\nSuperseded earlier absents using the markdown: " + ", ".join(suppressed)
    return summary


def _retry_absents_with_md(pdf: Path) -> list[str]:
    """Re-run the cheap absents now that we have the markdown.

    Returns the list of facts that flipped from absent to known.
    """
    flipped: list[str] = []
    sc = Sidecar(pdf)
    if sc.has(ABSTRACT_ABSENT):
        cmd_abstract(pdf)
        sc = Sidecar(pdf)
        if sc.has(ABSTRACT_KNOWN):
            flipped.append("abstract")
    if sc.has(TOC_ABSENT):
        cmd_toc(pdf)
        sc = Sidecar(pdf)
        if sc.has(TOC_KNOWN):
            flipped.append("toc")
    return flipped


def _extract_pdfplumber_chars(pdf: Path, pages: str | None = None):
    """Run pdfplumber to create .chars.json."""
    import json as json_mod
    import pdfplumber
    from decimal import Decimal

    pages_data = []
    with pdfplumber.open(pdf) as pdf_obj:
        for page in pdf_obj.pages:
            pages_data.append({
                "page_number": page.page_number,
                "width": float(page.width),
                "height": float(page.height),
                "chars": page.chars,
            })

    def default(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        raise TypeError(f"Not serializable: {type(obj)}")

    chars_path = pdf.with_suffix(".chars.json")
    with open(chars_path, "w", encoding="utf-8") as f:
        json_mod.dump(
            {"source": pdf.name, "total_pages": len(pages_data), "pages": pages_data},
            f, default=default, ensure_ascii=False,
        )


def cmd_page(pdf: Path, page_num: int) -> str:
    """Single-page deep extract."""
    sc = Sidecar(pdf)
    if not sc.has(SIZE_KNOWN):
        cmd_size(pdf)
        sc = Sidecar(pdf)

    t0 = time.monotonic()
    out = subprocess.run(
        ["pdftotext", "-f", str(page_num), "-l", str(page_num), "-layout", str(pdf), "-"],
        capture_output=True, text=True, timeout=30,
    )
    elapsed = time.monotonic() - t0

    text = out.stdout
    lines = len(text.splitlines())
    words = len(text.split())

    sc.log_transition("page", "INIT", f"PAGE_{page_num}_EXTRACTED",
                      cost_ms=elapsed * 1000, detail=f"page {page_num}: {words} words")
    sc.save()

    return f"Page {page_num} of {sc.page_count} ({words} words, {lines} lines):\n\n{text}"


# ---------------------------------------------------------------------------
# Fetch command — retrieve stored content
# ---------------------------------------------------------------------------

def cmd_fetch(pdf: Path, what: str, **kwargs) -> str:
    """Retrieve stored content by name."""
    sc = Sidecar(pdf)

    if what == "md":
        blob = sc.read_blob("md.md")
        if blob:
            section = kwargs.get("section")
            if section:
                return _extract_section(blob, section)
            return blob
        return "Markdown not yet built. Run `pdfdrill md` first."

    if what == "abstract":
        return _format_abstract(sc)

    if what == "toc":
        return _format_toc(sc)

    if what == "status":
        return cmd_status(pdf)

    return f"Unknown layer: {what}. Available: md, abstract, toc, status."


def _extract_section(md: str, section: str | int) -> str:
    """Extract a section by number from markdown."""
    pattern = rf"^##?\s*{section}\s"
    lines = md.split("\n")
    in_section = False
    result = []
    for line in lines:
        if re.match(pattern, line):
            in_section = True
        elif in_section and re.match(r"^##?\s*\d", line):
            break
        if in_section:
            result.append(line)
    if result:
        return "\n".join(result)
    return f"Section {section} not found in the markdown."


# ---------------------------------------------------------------------------
# pdfinfo-derived layers
# ---------------------------------------------------------------------------

def cmd_pdfinfo(pdf: Path) -> str:
    """Build the full PdfInfo struct via two pdfinfo calls."""
    from .pdfinfo_layers import fetch_pdfinfo_struct

    sc = Sidecar(pdf)
    if sc.has(PDFINFO_KNOWN):
        return _format_pdfinfo(sc.pdfinfo)

    t0 = time.monotonic()
    info = fetch_pdfinfo_struct(pdf)
    sc.set_pdfinfo(info)
    sc.add_fact(PDFINFO_KNOWN)

    # Backfill the size evidence so cmd_size stays consistent.
    if not sc.has(SIZE_KNOWN):
        sc.set_evidence("pages", info["pages"])
        sc.set_evidence("bytes", info["size_in_bytes"])
        sc.set_evidence("page_size", info["page_size"])
        sc.set_evidence("producer", info["producer"])
        sc.set_evidence("creator", info["creator"])
        sc.set_evidence("encrypted", info["encrypted"])
        sc.set_evidence("text_layer", True)
        sc.add_fact(SIZE_KNOWN)

    elapsed = time.monotonic() - t0
    prev = ",".join(sorted(sc.facts - {PDFINFO_KNOWN})) or "INIT"
    sc.log_transition("pdfinfo", prev, PDFINFO_KNOWN, cost_ms=elapsed * 1000,
                      detail=f"title={bool(info['title'])} author={bool(info['author'])}")
    sc.save()
    return _format_pdfinfo(info)


def _format_pdfinfo(info: dict) -> str:
    if not info:
        return "No pdfinfo gathered yet."
    parts = []
    if info.get("title"):
        parts.append(f"Title: {info['title']}")
    if info.get("author"):
        parts.append(f"Author: {info['author']}")
    parts.append(f"{info['pages']} pages, PDF {info['pdf_version']}, "
                 f"{info['size_in_bytes']:,} bytes")
    if info.get("page_size"):
        parts.append(f"Page size: {info['page_size']}")
    if info.get("producer"):
        parts.append(f"Producer: {info['producer']}")
    if info.get("creator") and info["creator"] != info["producer"]:
        parts.append(f"Creator: {info['creator']}")
    if info.get("creation_date"):
        parts.append(f"Created: {info['creation_date']}")
    if info.get("mod_date") and info["mod_date"] != info.get("creation_date"):
        parts.append(f"Modified: {info['mod_date']}")
    flags = []
    for f, label in [("custom_metadata", "custom metadata"),
                     ("metadata_stream", "XMP stream"),
                     ("tagged", "tagged"),
                     ("encrypted", "ENCRYPTED"),
                     ("javascript", "has JavaScript"),
                     ("optimized", "optimized"),
                     ("linearized", "linearized")]:
        if info.get(f):
            flags.append(label)
    if flags:
        parts.append(", ".join(flags))
    custom = info.get("custom_fields") or {}
    if custom:
        names = ", ".join(sorted(custom.keys()))
        parts.append(f"Extra metadata keys: {names}")
    return "\n".join(parts)


def cmd_bibtex(pdf: Path) -> str:
    """Derive a BibTeX record from pdfinfo metadata."""
    from .pdfinfo_layers import derive_bibtex, bibtex_to_string

    sc = Sidecar(pdf)
    if not sc.has(PDFINFO_KNOWN):
        cmd_pdfinfo(pdf)
        sc = Sidecar(pdf)
    if sc.has(BIBTEX_KNOWN):
        return _format_bibtex(sc.bibtex)

    t0 = time.monotonic()
    bib = derive_bibtex(sc.pdfinfo or {})
    sc.set_bibtex(bib)
    sc.add_fact(BIBTEX_KNOWN)

    elapsed = time.monotonic() - t0
    prev = ",".join(sorted(sc.facts - {BIBTEX_KNOWN})) or "INIT"
    sc.log_transition("bibtex", prev, BIBTEX_KNOWN, cost_ms=elapsed * 1000,
                      detail=f"citekey={bib['citekey']}")
    sc.save()
    return _format_bibtex(bib)


def _format_bibtex(bib: dict | None) -> str:
    from .pdfinfo_layers import bibtex_to_string
    if not bib:
        return "No BibTeX record built."
    rendered = bibtex_to_string(bib)
    missing = [k for k in ("title", "author", "year", "doi") if not bib.get(k)]
    note = (f"\n\nNote: {', '.join(missing)} not found in metadata; "
            f"consider augmenting from the abstract."
            if missing else "")
    return f"Derived BibTeX record:\n\n{rendered}{note}"


def cmd_urls(pdf: Path) -> str:
    """Extract link annotations with anchor text and surrounding context.

    pdfinfo -url gives URL + page but no bounding rectangle, so it can't
    answer "where on the page is this link, and what is the visible text
    that's hyperlinked?". This implementation uses pdfplumber's annot API
    instead, which gives us the rectangle, and intersects it with the
    page's char positions to recover the anchor text. Internal links (no
    URI) are resolved against the `dests` layer so we know what each
    cross-reference points to.

    Killer case: "The source code could be found here" where "here" is a
    link — we get `anchor_text="here"` and `context="...could be found
    [here]..."` and the URL in one record.
    """
    from .links_layer import fetch_links, summarize_links

    sc = Sidecar(pdf)
    if sc.has(URLS_KNOWN):
        return _format_urls(sc.urls)

    # Bring dests in if available — we use them to resolve internal links.
    if not sc.has(DESTS_KNOWN):
        cmd_dests(pdf)
        sc = Sidecar(pdf)

    t0 = time.monotonic()
    links = fetch_links(pdf, dests=sc.dests or [])
    sc.set_urls(links)
    sc.add_fact(URLS_KNOWN)

    elapsed = time.monotonic() - t0
    prev = ",".join(sorted(sc.facts - {URLS_KNOWN})) or "INIT"
    counts = summarize_links(links)
    detail = ", ".join(f"{n} {k}" for k, n in counts.items()) or "0"
    sc.log_transition("urls", prev, URLS_KNOWN, cost_ms=elapsed * 1000,
                      detail=detail)
    sc.save()
    return _format_urls(links)


def _format_urls(links: list | None) -> str:
    if links is None:
        return "URLs not yet extracted."
    if not links:
        return "No link annotations found in the document."
    from .links_layer import summarize_links
    counts = summarize_links(links)
    parts = [f"{n} {k}" for k, n in counts.items()]
    lines = [f"Found {len(links)} link annotations ({', '.join(parts)}):", ""]

    # Show URL links first with anchor text
    url_links = [r for r in links if r["kind"] == "url"]
    for r in url_links[:25]:
        anchor = r.get("anchor_text") or "(no visible text)"
        target = r.get("uri") or ""
        # When anchor == URL, just show one of them
        if anchor and anchor != target and len(anchor) < 80:
            lines.append(f"  p.{r['page']:<3} '{anchor}' → {target}")
        else:
            lines.append(f"  p.{r['page']:<3} {target}")
        ctx = r.get("context") or ""
        if ctx and ctx != f"[{anchor}]":
            lines.append(f"        context: {ctx[:120]}")
    if len(url_links) > 25:
        lines.append(f"  ... and {len(url_links) - 25} more URL links")

    internal = [r for r in links if r["kind"] == "internal"]
    if internal:
        lines.append("")
        lines.append(f"Internal cross-references ({len(internal)}):")
        for r in internal[:15]:
            anchor = r.get("anchor_text") or "?"
            dest = r.get("dest_name") or "?"
            dest_page = r.get("dest_page")
            target_str = f"→ {dest}"
            if dest_page:
                target_str += f" (p.{dest_page})"
            lines.append(f"  p.{r['page']:<3} '{anchor}' {target_str}")
        if len(internal) > 15:
            lines.append(f"  ... and {len(internal) - 15} more internal refs")

    return "\n".join(lines)


def cmd_dests(pdf: Path) -> str:
    """Extract named destinations from pdfinfo -dests."""
    from .pdfinfo_layers import fetch_dests, summarize_dests

    sc = Sidecar(pdf)
    if sc.has(DESTS_KNOWN):
        return _format_dests(sc.dests)

    t0 = time.monotonic()
    dests = fetch_dests(pdf)
    sc.set_dests(dests)
    sc.add_fact(DESTS_KNOWN)

    elapsed = time.monotonic() - t0
    prev = ",".join(sorted(sc.facts - {DESTS_KNOWN})) or "INIT"
    summary = summarize_dests(dests)
    sc.log_transition("dests", prev, DESTS_KNOWN, cost_ms=elapsed * 1000,
                      detail=f"{len(dests)} dests across {len(summary)} kinds")
    sc.save()
    return _format_dests(dests)


def _format_dests(dests: list | None) -> str:
    from .pdfinfo_layers import summarize_dests
    if dests is None:
        return "Named destinations not yet extracted."
    if not dests:
        return "No named destinations found in the PDF."
    counts = summarize_dests(dests)
    lines = [f"Found {len(dests)} named destinations across {len(counts)} kinds:"]
    for kind, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {kind:14s} {n}")
    # Show the interesting structural items (theorems, equations, etc.)
    interesting = {"theorem", "lemma", "proposition", "corollary",
                   "definition", "equation", "figure", "table", "section"}
    samples = [d for d in dests if d["kind"] in interesting][:15]
    if samples:
        lines.append("")
        lines.append("Sample document-structure anchors:")
        for d in samples:
            lines.append(f"  p.{d['page']:<3} {d['kind']:<11s} {d['name']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# pdffonts + pdfimages-derived layers
# ---------------------------------------------------------------------------

def cmd_fonts_layer(pdf: Path) -> str:
    """Build the structured fonts_layer via pdffonts."""
    from .font_image_layers import fetch_fonts, summarize_fonts

    sc = Sidecar(pdf)
    if sc.has(FONTS_LAYER_KNOWN):
        return _format_fonts_layer(sc.fonts_layer or [])

    t0 = time.monotonic()
    fonts = fetch_fonts(pdf)
    sc.set_fonts_layer(fonts)
    sc.add_fact(FONTS_LAYER_KNOWN)

    elapsed = time.monotonic() - t0
    prev = ",".join(sorted(sc.facts - {FONTS_LAYER_KNOWN})) or "INIT"
    summary = summarize_fonts(fonts)
    sc.log_transition("fonts_layer", prev, FONTS_LAYER_KNOWN, cost_ms=elapsed * 1000,
                      detail=f"{summary['n_fonts']} fonts, {summary['n_math']} math")
    sc.save()
    return _format_fonts_layer(fonts)


def _format_fonts_layer(fonts: list) -> str:
    from .font_image_layers import summarize_fonts
    if not fonts:
        return "No fonts reported by pdffonts (typewriter-style or scanned PDF)."
    s = summarize_fonts(fonts)
    lines = [
        f"Found {s['n_fonts']} font records across {s['n_families']} families."
    ]
    if s["n_math"]:
        lines.append(f"  Math fonts: {s['n_math']} ({', '.join(s['math_families'][:6])})")
    if s["n_bold"]:
        lines.append(f"  Bold variants: {s['n_bold']}")
    if s["n_italic"]:
        lines.append(f"  Italic variants: {s['n_italic']}")
    if s["n_not_embedded"]:
        lines.append(f"  ⚠ {s['n_not_embedded']} font(s) not embedded "
                     f"(rendering may vary)")
    if len(s["families"]) <= 20:
        lines.append("")
        lines.append(f"Families: {', '.join(s['families'])}")
    return "\n".join(lines)


def cmd_images(pdf: Path) -> str:
    """Build the structured images_layer from pdfplumber + pdfimages -list."""
    from .font_image_layers import fetch_image_layer

    sc = Sidecar(pdf)
    if sc.has(IMAGES_LAYER_KNOWN):
        return _format_images_layer(sc.images_layer or [])

    t0 = time.monotonic()
    images = fetch_image_layer(pdf)
    sc.set_images_layer(images)
    sc.add_fact(IMAGES_LAYER_KNOWN)

    elapsed = time.monotonic() - t0
    prev = ",".join(sorted(sc.facts - {IMAGES_LAYER_KNOWN})) or "INIT"
    n_candidates = sum(1 for r in images if r.get("candidate_pix2latex"))
    sc.log_transition("images", prev, IMAGES_LAYER_KNOWN, cost_ms=elapsed * 1000,
                      detail=f"{len(images)} images, {n_candidates} pix2latex candidates")
    sc.save()
    return _format_images_layer(images)


def _format_images_layer(images: list) -> str:
    if not images:
        return "No embedded images found in the document."

    by_page: dict[int, list] = {}
    encodings: dict[str, int] = {}
    candidates: list[dict] = []
    no_position: list[dict] = []
    total_bytes = 0
    for r in images:
        by_page.setdefault(r["page"], []).append(r)
        enc = r.get("encoding") or "unknown"
        encodings[enc] = encodings.get(enc, 0) + 1
        total_bytes += r.get("size_bytes", 0) or 0
        if r.get("candidate_pix2latex"):
            candidates.append(r)
        if r.get("position_unknown"):
            no_position.append(r)

    lines = [
        f"Found {len(images)} embedded image(s) across {len(by_page)} page(s)."
    ]
    enc_summary = ", ".join(f"{n} {enc}" for enc, n in sorted(encodings.items()))
    lines.append(f"  encodings: {enc_summary}")
    if total_bytes:
        lines.append(f"  total image bytes: {total_bytes/1024:.0f} KB")
    if no_position:
        lines.append(f"  {len(no_position)} image(s) without position "
                     f"(inline or masked — pdfplumber didn't surface them)")
    if candidates:
        lines.append(
            f"  {len(candidates)} pix2latex candidate(s) — small bitmaps that may be "
            f"rasterised equations"
        )

    lines.append("")
    lines.append("Per-page sample (first 15 images):")
    shown = 0
    for r in images[:15]:
        shown += 1
        if r.get("position_unknown"):
            lines.append(
                f"  p.{r['page']:<3} {r.get('encoding','?'):<8s} "
                f"{r['width_px']}×{r['height_px']}px (no position)"
            )
        else:
            tag = "  pix2latex?" if r.get("candidate_pix2latex") else ""
            lines.append(
                f"  p.{r['page']:<3} x=[{r['x0']:6.1f},{r['x1']:6.1f}] "
                f"y=[{r['y0']:6.1f},{r['y1']:6.1f}] "
                f"{r['w_pt']:.0f}×{r['h_pt']:.0f}pt "
                f"{r.get('encoding','?')}{tag}"
            )
    if len(images) > shown:
        lines.append(f"  ... and {len(images) - shown} more")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# pix2tex (image → LaTeX) — visual math OCR for rasterized equations
# ---------------------------------------------------------------------------

def cmd_pix2tex(
    pdf: Path,
    page: int | None = None,
    rect: tuple[float, float, float, float] | None = None,
    rerun: bool = False,
) -> str:
    """Run pix2tex on rasterized equations.

    Three modes:
      * `page` and `rect` given → OCR exactly that crop.
      * neither given          → OCR every pix2latex candidate from the
                                  images_layer (auto-chains `images`).
      * `page` only            → OCR every candidate on that page.
    """
    from .pix2tex_runner import process_rect

    sc = Sidecar(pdf)

    # Make sure we know page geometry. images_layer auto-chains size.
    if not sc.has(SIZE_KNOWN):
        cmd_size(pdf)
        sc = Sidecar(pdf)
    if rect is None and not sc.has(IMAGES_LAYER_KNOWN):
        cmd_images(pdf)
        sc = Sidecar(pdf)

    page_geometry = _page_geometry_table(pdf, sc)

    # Build the request list.
    requests = _pix2tex_requests(sc, page, rect)
    if not requests:
        if rect or page:
            return f"No candidate rect for page={page} rect={rect} in this PDF."
        return ("No rasterized-equation candidates found in the images_layer. "
                "Either the PDF uses native math fonts, or rasterized equations "
                "are larger than the candidate threshold; you can force OCR with "
                "`pdfdrill pix2tex <pdf> --page N --rect x0,y0,x1,y1`.")

    blob_dir = sc.blob_dir / "pix2tex"
    # Skip already-run requests unless rerun=True.
    done_keys = {
        (r["page"], tuple(r["rect"]))
        for r in (sc.pix2tex_results or [])
    }
    new_results: list[dict] = []
    skipped = 0
    t0 = time.monotonic()
    for req in requests:
        key = (req["page"], tuple(req["rect"]))
        if not rerun and key in done_keys:
            skipped += 1
            continue
        try:
            geom = page_geometry.get(req["page"]) or (612.0, 792.0)
            res = process_rect(
                pdf=pdf,
                page=req["page"],
                rect_pts=tuple(req["rect"]),
                page_width_pt=geom[0],
                page_height_pt=geom[1],
                out_dir=blob_dir,
            )
            res["source"] = req.get("source", "explicit")
            new_results.append(res)
            sc.append_pix2tex_result(res)
            sc.save()
        except Exception as exc:
            new_results.append({
                "page": req["page"],
                "rect": req["rect"],
                "error": str(exc),
                "source": req.get("source", "explicit"),
            })

    elapsed = time.monotonic() - t0
    sc.add_fact(PIX2TEX_RAN)
    prev = ",".join(sorted(sc.facts - {PIX2TEX_RAN})) or "INIT"
    sc.log_transition("pix2tex", prev, PIX2TEX_RAN, cost_ms=elapsed * 1000,
                      detail=f"{len(new_results)} new, {skipped} cached")
    sc.save()
    return _format_pix2tex(new_results, skipped, sc.pix2tex_results or [])


# ---------------------------------------------------------------------------
# Helpers for cmd_pix2tex
# ---------------------------------------------------------------------------

def _pix2tex_requests(
    sc: Sidecar,
    page: int | None,
    rect: tuple[float, float, float, float] | None,
) -> list[dict]:
    """Resolve the call signature into a list of {page, rect, source}."""
    if rect is not None:
        if page is None:
            return []
        return [{"page": page, "rect": list(rect), "source": "explicit"}]
    images = sc.images_layer or []
    candidates = [
        r for r in images
        if r.get("candidate_pix2latex") and r.get("x0") is not None
    ]
    if page is not None:
        candidates = [c for c in candidates if c["page"] == page]
    return [
        {
            "page": c["page"],
            "rect": [c["x0"], c["y0"], c["x1"], c["y1"]],
            "source": "candidate",
        }
        for c in candidates
    ]


def _page_geometry_table(pdf: Path, sc: Sidecar) -> dict[int, tuple[float, float]]:
    """Return {page_number: (width_pt, height_pt)}.

    Prefers the cached pdfinfo struct (single Page-size string for the
    whole document); falls back to pdfplumber for per-page sizes if the
    document has heterogeneous pages.
    """
    page_size_str = ""
    if sc.pdfinfo and sc.pdfinfo.get("page_size"):
        page_size_str = sc.pdfinfo["page_size"]
    elif sc.get_evidence("page_size"):
        page_size_str = sc.get_evidence("page_size", "")

    import re
    m = re.match(r"\s*([\d.]+)\s*x\s*([\d.]+)\s*pts", page_size_str)
    n_pages = sc.page_count or 0
    if m and n_pages:
        w, h = float(m.group(1)), float(m.group(2))
        return {p: (w, h) for p in range(1, n_pages + 1)}

    # Fallback: ask pdfplumber.
    import pdfplumber
    out: dict[int, tuple[float, float]] = {}
    with pdfplumber.open(pdf) as pdf_obj:
        for page in pdf_obj.pages:
            out[page.page_number] = (float(page.width), float(page.height))
    return out


def _format_pix2tex(
    new_results: list[dict],
    skipped: int,
    all_results: list[dict],
) -> str:
    if not new_results and not all_results:
        return "No pix2tex results."
    lines: list[str] = []
    if new_results:
        lines.append(
            f"pix2tex ran on {len(new_results)} new crop(s); {skipped} skipped (cached)."
        )
    else:
        lines.append(f"All {len(all_results)} candidate(s) were already cached.")

    show = new_results if new_results else all_results
    for r in show:
        if "error" in r:
            lines.append(f"  p.{r['page']}  ⚠ error: {r['error']}")
            continue
        rect = r.get("rect", [])
        rect_str = f"[{rect[0]:.0f},{rect[1]:.0f},{rect[2]:.0f},{rect[3]:.0f}]" if len(rect) == 4 else "?"
        timing = ""
        if r.get("ocr_ms") is not None:
            timing = f" (render {r['render_ms']:.0f}ms + OCR {r['ocr_ms']:.0f}ms)"
        lines.append(f"  p.{r['page']}  rect {rect_str} {r.get('source', '?')}{timing}")
        lines.append(f"      $ {r.get('latex', '')} $")
        if r.get("crop_path"):
            lines.append(f"      crop: {r['crop_path']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Text-with-positions layer (pdftotext -tsv → tesseract fallback)
# ---------------------------------------------------------------------------

def cmd_tsv(pdf: Path, force_ocr: bool = False) -> str:
    """Extract per-word records with bounding boxes.

    Uses pdftotext -tsv if the PDF has a text layer (cheap, accurate). Falls
    back to tesseract on rendered PNGs if there's no text layer or the
    caller forces OCR. Tesseract is opt-in: missing binary returns a
    clear prose error instead of failing.
    """
    from .text_layers import (
        fetch_pdftotext_tsv, fetch_tesseract_tsv,
        summarize_tsv, tesseract_available,
    )

    sc = Sidecar(pdf)
    if not sc.has(SIZE_KNOWN):
        cmd_size(pdf)
        sc = Sidecar(pdf)
    if not sc.has(FONTS_KNOWN):
        cmd_fonts(pdf)
        sc = Sidecar(pdf)

    if sc.has(TSV_KNOWN) and not force_ocr:
        return _format_tsv(sc)

    has_text_layer = bool(sc.get_evidence("text_layer"))
    use_ocr = force_ocr or not has_text_layer
    if use_ocr and not tesseract_available():
        return ("No text layer in this PDF and tesseract is not installed. "
                "Install with `apt install tesseract-ocr` (and a language pack like "
                "`tesseract-ocr-eng`) then rerun.")

    t0 = time.monotonic()
    try:
        if use_ocr:
            ocr_dir = sc.blob_dir / "tesseract"
            words = fetch_tesseract_tsv(pdf, ocr_dir)
            source = "tesseract"
        else:
            words = fetch_pdftotext_tsv(pdf)
            source = "pdftotext"
    except Exception as exc:
        return f"TSV extraction failed: {exc}"

    sc.set_tsv_layer(words)
    sc.set_evidence(TSV_SOURCE, source)
    sc.add_fact(TSV_KNOWN)

    elapsed = time.monotonic() - t0
    summary = summarize_tsv(words)
    prev = ",".join(sorted(sc.facts - {TSV_KNOWN})) or "INIT"
    sc.log_transition("tsv", prev, TSV_KNOWN, cost_ms=elapsed * 1000,
                      detail=f"{source}: {summary['words']} words")
    sc.save()
    return _format_tsv(sc)


def _format_tsv(sc: Sidecar) -> str:
    from .text_layers import summarize_tsv
    words = sc.tsv_layer or []
    s = summarize_tsv(words)
    source = sc.get_evidence(TSV_SOURCE, "?")
    if not words:
        return f"TSV layer empty (source: {source})."
    lines = [
        f"Extracted {s['words']} words with bounding boxes across "
        f"{s['pages']} page(s) via {source}.",
    ]
    if source == "tesseract":
        lines.append(f"  Average OCR confidence: {s['avg_conf']:.1f}")
        if s["low_conf_words"]:
            lines.append(
                f"  ⚠ {s['low_conf_words']} word(s) below 60 confidence — "
                f"likely OCR noise"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Render command — reconstruct MD → PDF via pandoc + lualatex
# ---------------------------------------------------------------------------

_PANDOC_HEADER = r"""\usepackage{fontspec}
\usepackage{luacode}
\directlua{
    luaotfload.add_fallback("emojifallback",
      {
        "Noto Color Emoji:mode=harf;script=DFLT;"
      }
    )
}
\setmainfont{DejaVu Serif}[RawFeature={fallback=emojifallback}]
\setsansfont{DejaVu Sans}[RawFeature={fallback=emojifallback}]
\setmonofont{DejaVu Sans Mono}[RawFeature={fallback=emojifallback}]
\usepackage{xcolor}
\usepackage{listings}
\lstset{
    basicstyle=\ttfamily\small,
    backgroundcolor=\color{white},
    frame=single,
    framesep=5pt,
    framexleftmargin=5pt,
    numbers=left,
    numberstyle=\tiny\color{gray},
    breaklines=true,
    showstringspaces=false,
    keywordstyle=\color{blue},
    commentstyle=\color{green!60!black},
    stringstyle=\color{red!80!black},
    tabsize=2,
    captionpos=b
}
"""


def cmd_render(pdf: Path, force: bool = False) -> str:
    """Render the built markdown to a PDF via pandoc + lualatex.

    The output PDF goes into the sidecar blob dir as `rendered.pdf`. Useful
    for visually verifying math transclusions and citation rendering.

    This command relies on the bash workflow the user supplied:
    pandoc → LaTeX (listings + emoji fallback) → lualatex.

    Idempotent: subsequent calls return the cached path unless `force=True`.
    """
    import shutil

    sc = Sidecar(pdf)
    if not sc.has(MD_BUILT):
        cmd_md(pdf)
        sc = Sidecar(pdf)
    if not sc.read_blob("md.md"):
        return "Markdown not available — `pdfdrill md` failed."

    out_dir = sc.blob_dir / "render"
    pdf_out = out_dir / "rendered.pdf"
    if pdf_out.exists() and not force:
        rel = pdf_out.relative_to(pdf.resolve().parent)
        return (f"Rendered PDF already present: {rel} "
                f"({pdf_out.stat().st_size//1024} KB). Re-render with `--force`.")

    if not shutil.which("pandoc") or not shutil.which("lualatex"):
        return "render requires `pandoc` and `lualatex` on PATH."

    md_path = sc.blob_dir / "md.md"
    out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / "rendered.tex"
    header_path = out_dir / "header.tex"
    header_path.write_text(_PANDOC_HEADER, encoding="utf-8")

    t0 = time.monotonic()
    pandoc = subprocess.run(
        [
            "pandoc", str(md_path),
            "-o", str(tex_path),
            "--from=markdown",
            "--to=latex",
            "--standalone",
            "--listings",
            f"--include-in-header={header_path}",
            "--toc", "--number-sections",
            "-V", "geometry:margin=0.75in",
            "-V", "fontsize=11pt",
        ],
        capture_output=True, text=True, timeout=120,
    )
    if pandoc.returncode != 0:
        return f"pandoc failed: {pandoc.stderr[:500]}"

    lualatex = subprocess.run(
        ["lualatex", "-interaction=nonstopmode",
         "-output-directory", str(out_dir), str(tex_path)],
        capture_output=True, text=True, timeout=300,
    )
    elapsed = time.monotonic() - t0

    if not pdf_out.exists():
        tail = lualatex.stdout[-1000:] if lualatex.stdout else ""
        return f"lualatex failed (after pandoc). Tail of log:\n{tail}"

    prev = ",".join(sorted(sc.facts)) or "INIT"
    sc.log_transition("render", prev, "RENDERED", cost_ms=elapsed * 1000,
                      detail=f"rendered.pdf {pdf_out.stat().st_size} bytes")
    sc.save()
    rel = pdf_out.relative_to(pdf.resolve().parent)
    return (f"Rendered the markdown to PDF in {elapsed:.1f}s. "
            f"Output: {rel} ({pdf_out.stat().st_size//1024} KB).")
