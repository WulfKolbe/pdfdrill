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
from .model_io import load_model, save_model


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
NEEDS_VISION_OCR = "NEEDS_VISION_OCR"  # math-bearing doc built prose-only (tesseract)
EMBEDDED_IMAGES_BUILT = "EMBEDDED_IMAGES_BUILT"
BIBSOURCE_BUILT = "BIBSOURCE_BUILT"
TRANSLATED = "TRANSLATED"
CONTINUITY_BUILT = "CONTINUITY_BUILT"
ENTITIES_BUILT = "ENTITIES_BUILT"
SEGMENTED = "SEGMENTED"
ELEMENTS_BUILT = "ELEMENTS_BUILT"
SEMANTIC_BUILT = "SEMANTIC_BUILT"
RASTERIZED = "RASTERIZED"
ATTACHMENTS_KNOWN = "ATTACHMENTS_KNOWN"
FORMFIELDS_KNOWN = "FORMFIELDS_KNOWN"
IMAGES_EXTRACTED = "IMAGES_EXTRACTED"
TABLES_KNOWN = "TABLES_KNOWN"
QR_KNOWN = "QR_KNOWN"

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
    from .mathpix_client import fetch_mathpix, upload_preflight, expected_outputs
    from .net import NetworkBlocked

    sc = Sidecar(pdf)

    # Pre-flight the upload only if one would actually happen (not already cached).
    # Refuse gracefully over MathPix's size limit (route to keyless OCR) rather
    # than OOM on the encode or POST a doomed 463 MB body; warn on large inputs.
    warn = ""
    cached = all(Path(p).exists() for p in expected_outputs(str(pdf)).values())
    # arXiv: don't spend a MathPix credit by default — the author's LaTeX source
    # is the FREE gold form. Skip the upload and point at the free routes; `model`
    # then builds page structure with keyless tesseract. `--force` uses MathPix.
    if not force and not cached:
        aid = _arxiv_id_for(pdf, sc)
        if aid:
            return (f"MathPix skipped — {pdf.name} is arXiv:{aid}, and the author's "
                    f"LaTeX source is FREE.\n"
                    f"  • equations (gold): `pdfdrill injectlatex {pdf.name}` auto-downloads "
                    f"the e-print .tgz\n"
                    f"  • abstract (free):  `pdfdrill abstract {pdf.name}` reads the abs "
                    f"page\n"
                    f"  • page structure:   `pdfdrill model {pdf.name}` falls back to "
                    f"keyless tesseract OCR\n"
                    f"Pass --force to use MathPix anyway.")
    if force or not cached:
        size = pdf.stat().st_size if pdf.exists() else 0
        pages = None
        try:
            info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True,
                                  text=True, timeout=30)
            m = re.search(r"Pages:\s*(\d+)", info.stdout)
            pages = int(m.group(1)) if m else None
        except Exception:
            pass
        ok, level, msg = upload_preflight(size, pages)
        if not ok:
            return (f"MathPix upload skipped — {msg}\n(Built-in fallback: `pdfdrill "
                    f"model` will use tesseract OCR instead when no lines.json appears.)")
        if level == "warn":
            warn = f"⚠ {msg}\n"

    t0 = time.monotonic()
    try:
        result = fetch_mathpix(str(pdf), force=force)
    except NetworkBlocked as e:
        return str(e)
    except Exception as e:        # 413 too-large / API error / oversize → degrade to OCR
        return (f"MathPix upload/conversion failed: {e}\nUse `pdfdrill ocr {pdf.name}` "
                f"(keyless tesseract) — `pdfdrill model` falls back to it automatically "
                f"when no lines.json appears.")

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
    return warn + _format_mathpix(result, files_meta)


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

def _missing_tool_msg(tool: str, pkg: str) -> str:
    """Clear, actionable message for a missing system tool — never the raw
    `[Errno 2] No such file or directory: <tool>` a bare FileNotFoundError gives."""
    return (f"`{tool}` is not installed — it's a prerequisite. Install it: "
            f"`sudo apt-get install {pkg}` (Debian/Ubuntu), `sudo dnf install "
            f"{pkg}` (Fedora), or your distro's package. Run `pdfdrill doctor` "
            f"to check every prerequisite.")


def _display_path(path: Path, base: Path) -> Path:
    """`path` shown relative to `base` when possible, else `path` unchanged.
    Never raises — Sidecar absolutizes pdf_path while a relative CLI arg leaves
    the base as '.', which would make `Path.relative_to` throw ValueError."""
    try:
        return path.relative_to(base)
    except (ValueError, TypeError):
        return path


def _unrendered_graphics_note(objects) -> str:
    """Guard against a STALE tiddlers.json: warn when the model has table/diagram
    graphics with LaTeX source (`latex_code`) but no rendered `svg` yet — the exact
    state that leaves those tiddlers empty (svg run after tiddlers were written).
    Counts ONLY genuine graphics (`svg.is_latex_graphic` — the same predicate `svg`
    uses), so a code listing or a non-graphic body that `svg` correctly skips is
    never flagged (no false 'run svg' when svg already ran)."""
    try:
        from .svg import is_latex_graphic
    except Exception:                                  # svg module unavailable
        is_latex_graphic = lambda s: bool(s)           # noqa: E731
    n = 0
    for o in objects:
        if getattr(o, "type", "") not in ("Diagram", "Table"):
            continue
        p = getattr(o, "props", {})
        code = p.get("latex_code")
        if code and not p.get("svg") and p.get("subtype") != "code" \
                and is_latex_graphic(code):
            n += 1
    if not n:
        return ""
    return (f" NOTE: {n} table/diagram(s) carry LaTeX source but no rendered SVG yet "
            f"— run `pdfdrill svg <pdf>` then `pdfdrill tiddlers <pdf> --force` so they "
            f"render inline (otherwise those tiddlers are empty).")


def _safe_bibkey(bibkey: str) -> str:
    """A filesystem/URL-safe bibkey for ARTIFACT FILENAMES. A bibkey from a spaced
    filename stem ("Great Paper") made `Great Paper.distill.html`, whose spaces
    break URLs + drillui's whitespace-splitting path scanner (→ 404). Replace every
    run of non-`[A-Za-z0-9._-]` with `_`; a clean id (`2004.05631v1`) is unchanged.
    Never empty."""
    import re as _re
    s = _re.sub(r"[^A-Za-z0-9._-]+", "_", (bibkey or "").strip()).strip("_.")
    return s or "doc"


def _lines_json_path(pdf: Path) -> Path:
    """Path MathPix lines.json would occupy next to the PDF."""
    base = pdf.name[:-4] if pdf.name.lower().endswith(".pdf") else pdf.name
    return pdf.parent / f"{base}.lines.json"


# Keyless, TEXT-only build sources (no LaTeX/math typing): tesseract OCR and the
# pdfplumber born-digital text layer. The math-bearing gate treats both alike.
_KEYLESS_TEXTONLY_SOURCES = ("tesseract", "pdfminer-chars", "pdfplumber-chars")


def _is_keyless_textonly_source(source: str) -> bool:
    return source in _KEYLESS_TEXTONLY_SOURCES


def _has_usable_math(objects: list, source: str) -> bool:
    """True if the model carries math that is actually USABLE (real LaTeX).

    A keyless TEXT-only source cannot produce LaTeX **by construction**: tesseract
    reads glyphs, pdfminer reads the text layer. The enriched tesseract module
    still emits typed `equation` lines — with a CORRECT region but GARBLED text —
    and the EquationProcessor stores that text in `latex`. So neither an Equation
    COUNT nor a non-empty `latex` proves the math was captured; on those sources
    only a gold-source overlay (`added_by="latex"`, from `pdfdrill injectlatex`) or a
    keyed route (MathPix/visionocr) supplies real LaTeX.

    Non-keyless sources (MathPix) are trusted as before.
    """
    keyless = _is_keyless_textonly_source(source)
    for o in objects:
        if o.get("type") != "Equation":
            continue
        props = o.get("props") or {}
        if not str(props.get("latex") or "").strip():
            continue
        if not keyless or props.get("added_by") == "latex":
            return True
    return False


def _pdfminer_char_dump(pdf: Path) -> dict:
    """Extract a born-digital CHARACTER dump with **pdfminer.six** in the shape
    `chars_to_lines` expects (PDF bottom-left origin, chars grouped per page).
    pdfminer.six is the born-digital engine (it replaced pdfplumber here — richer
    font/emphasis, and the one engine the font-span leg already uses). Raises when
    pdfminer.six is absent so the caller can fall back."""
    from . import pdfminer_layer as PM
    if not PM.available():
        raise RuntimeError("pdfminer.six not installed")
    recs = PM.char_records(str(pdf))                 # top-left origin: top/bottom
    dims = PM.page_dims(str(pdf))                     # {pg: (w, h)}
    by_page: dict[int, list[dict]] = {}
    for c in recs:
        by_page.setdefault(c["page"], []).append(c)
    pages = []
    for pg in sorted(dims):
        w, h = dims[pg]
        chars = [{"x0": float(c["x0"]), "x1": float(c["x1"]),
                  # top-left top/bottom → bottom-left y0/y1 (chars_to_lines re-flips)
                  "y0": float(h) - float(c["bottom"]),
                  "y1": float(h) - float(c["top"]),
                  "text": c.get("text", "")} for c in by_page.get(pg, [])]
        pages.append({"page_number": pg, "width": float(w), "height": float(h),
                      "chars": chars})
    return {"source": "pdfminer-chars", "total_pages": len(pages), "pages": pages}


def _pdfplumber_char_dump(pdf: Path) -> dict:
    """FALLBACK born-digital CHARACTER dump via pdfplumber (used only when
    pdfminer.six is unavailable). Thin wrapper so it can be monkeypatched in
    tests."""
    import pdfplumber
    pages = []
    with pdfplumber.open(str(pdf)) as doc:
        for i, page in enumerate(doc.pages, 1):
            pages.append({
                "page_number": i,
                "width": float(page.width),
                "height": float(page.height),
                "chars": [{"x0": float(c["x0"]), "x1": float(c["x1"]),
                           "y0": float(c["y0"]), "y1": float(c["y1"]),
                           "text": c.get("text", "")} for c in page.chars],
            })
    return {"source": "pdfplumber-chars", "total_pages": len(pages), "pages": pages}


def _born_digital_char_dump(pdf: Path) -> dict:
    """The born-digital char dump: **pdfminer.six** first (the engine that replaced
    pdfplumber), pdfplumber only as a fallback when pdfminer.six is absent."""
    try:
        return _pdfminer_char_dump(pdf)
    except Exception:                                # noqa: BLE001 (absent / parse)
        return _pdfplumber_char_dump(pdf)


def _write_born_digital_lines(pdf: Path) -> bool:
    """Born-digital TEXT-LAYER route: read the PDF's own text layer with
    **pdfminer.six** (pdfplumber fallback) and write a MathPix-shape
    `<stem>.lines.json` (source `pdfminer-chars`/`pdfplumber-chars`). FREE and
    fast — no MathPix, no OCR. Returns False when there is effectively no text
    layer (a scan → let OCR handle it) or extraction fails, so the caller falls
    through to tesseract. This is what `route`'s "born-digital → text-layer (free)"
    promise resolves to inside `model`."""
    from . import chars_to_lines
    try:
        data = _born_digital_char_dump(pdf)
    except Exception:                                # noqa: BLE001
        return False
    if sum(len(p.get("chars", [])) for p in data.get("pages", [])) < 20:
        return False                                 # no real text layer → OCR
    try:
        lines = chars_to_lines.chars_to_lines_json(data)
        from . import model_io
        model_io._atomic_write(_lines_json_path(pdf), json.dumps(lines))
    except Exception:                                # noqa: BLE001
        return False
    return True


def _model_path(sc: Sidecar) -> Path:
    return sc.blob_dir / "model.docmodel.json"


def _legacy_stale() -> bool:
    """Env opt-out (`PDFDRILL_LEGACY_STALE=1`) that keeps the pure-mtime staleness
    trigger during the transition to content-hash proofs (Phase D)."""
    import os
    return os.environ.get("PDFDRILL_LEGACY_STALE", "").lower() in ("1", "true", "yes")


def _stale_or_absent(sc: "Sidecar", model_path: Path, lines_path: Path) -> bool:
    """True if the model must be (re)built before a projector/read can trust it.

    Missing model → always stale. Otherwise, when the model carries a content-hash
    PROOF (Phase B) and we're not in legacy mode, staleness is decided by the proof
    — the model is stale iff its recorded inputs no longer hash-match (principled,
    and it does NOT rebuild merely because an unchanged lines.json was re-touched,
    unlike the old mtime trigger). A model without a proof (legacy build) or
    `PDFDRILL_LEGACY_STALE=1` falls back to the mtime heuristic (lines.json newer
    than the model — the 2305.04710 'no formulas' bug)."""
    if not sc.has(MODEL_BUILT) or not model_path.exists():
        return True
    try:
        caps = sc.get_evidence("model_caps") or {}
        source_trap = bool(lines_path.exists() and caps.get("geometry") is False)
        proof = None if _legacy_stale() else sc.capabilities.get(MODEL_BUILT)
        if proof is not None:
            from . import proofs
            if not proofs.verify(proof):     # recorded inputs changed → stale
                return True
            return source_trap               # proof valid → ignore mtime
        # legacy / no-proof: mtime heuristic
        if (lines_path.exists()
                and lines_path.stat().st_mtime > model_path.stat().st_mtime):
            return True
        # source→mathpix trap (see cmd_model): a geometry-less SOURCE model with a
        # MathPix lines.json present must rebuild — else inspect/locate stay
        # box-less on the source model though a geometry-bearing lines.json exists.
        return source_trap
    except OSError:
        return False


def _fresh_docgraph(pdf: Path, sc: "Sidecar", model_path: Path):
    """Read-path loader that REBUILDS first if the model is stale (lines.json
    newer), so fast DocGraph commands (llmtext/mathcheck/classify/retrieve/
    identifiers/booktoc) never silently serve out-of-date content. Offline-safe:
    cmd_model only auto-runs offline steps. The model must already exist (the
    caller guards absence)."""
    from . import model_io
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
        cmd_model(pdf)
    return model_io.load_docgraph(model_path)


def _lines_json_source(lines_path: Path) -> str:
    """Cheap read of the `source` field of a lines.json (e.g. 'tesseract',
    'mathpix') without loading the whole file. Both producers emit `source`
    near the top; falls back to '' if not found in the head."""
    try:
        head = lines_path.read_text(encoding="utf-8")[:8192]
    except OSError:
        return ""
    m = re.search(r'"source"\s*:\s*"([^"]*)"', head)
    return m.group(1) if m else ""


# A "junky" filename stem that makes a poor tiddler prefix: a long leading
# digit run (≥5, so arXiv ids like `2004.05631v1` are NOT flagged), whitespace,
# or doubled punctuation. Used to suggest `--bibkey`.
_JUNK_STEM = re.compile(r"^\d{5,}|\s|[._-]{2,}")


def resolve_bibkey(pdf: Path, explicit: str | None = None,
                   sc: "Sidecar | None" = None) -> str:
    """Resolve the bibkey/tiddler-prefix for a PDF.

    Precedence: explicit `--bibkey` > the key persisted in the sidecar (set by a
    previous `model --bibkey`) > the filename stem. A clean stem (e.g. an arXiv
    id `2004.05631v1`) is kept as-is; the caller can warn when it's junky.
    """
    if explicit:
        return explicit.strip()
    sc = sc or Sidecar(pdf)
    stored = sc.get_evidence("bibkey")
    return stored or pdf.stem


def _bibkey_hint(bibkey: str) -> str:
    """A one-line tip when the resolved bibkey looks like a junky filename stem."""
    return (f" Tip: the prefix '{bibkey}' is derived from the filename — pass "
            f"--bibkey <key> (e.g. surname2018topic) for clean tiddler titles."
            if _JUNK_STEM.search(bibkey) else "")


# TeX .sty packages the TikZ/table SVG route commonly needs, → apt package.
# (The first mass keyless-LaTeX run failed renders on the font ones — all in
# texlive-fonts-extra — which a binary-only check could not foresee.)
_TEX_STYLES = [
    ("standalone.sty", "texlive-latex-extra", "standalone TikZ/table crop"),
    ("tikz.sty", "texlive-pictures", "TikZ pictures"),
    ("pgfplots.sty", "texlive-pictures", "plots"),
    ("soul.sty", "texlive-latex-extra", "highlighting (common preamble)"),
    ("multirow.sty", "texlive-latex-extra", "table multirow"),
    ("inconsolata.sty", "texlive-fonts-extra", "mono font"),
    ("fontawesome.sty", "texlive-fonts-extra", "icon font"),
    ("bbold.sty", "texlive-fonts-extra", "blackboard-bold"),
    ("bbding.sty", "texlive-fonts-extra", "dingbats"),
    ("mhchem.sty", "texlive-science", "chemistry (mhchem)"),
    ("chemfig.sty", "texlive-pictures", "chem structures"),
]


def tex_style_status(check=None) -> list:
    """Which common TikZ/table-render .sty packages are present. `check(sty)->bool`
    is injectable (tests); the default uses `kpsewhich`. Returns [] when there is
    no TeX at all (the binary check already reports that)."""
    import shutil
    import subprocess
    if check is None:
        if not shutil.which("kpsewhich"):
            return []
        def check(sty):                                  # noqa: E306
            try:
                r = subprocess.run(["kpsewhich", sty], capture_output=True,
                                   text=True, timeout=10)
                return bool(r.stdout.strip())
            except Exception:
                return False
    return [{"sty": s, "pkg": p, "desc": d, "present": bool(check(s))}
            for s, p, d in _TEX_STYLES]


def cmd_doctor() -> str:
    """Requirement check: report which system tools / Python deps / API keys are
    present, which routes they enable, and the apt-get line to fix any gaps.

    The LaTeX DVI toolchain + dvisvgm (the TikZ/table SVG route) and
    poppler/tesseract are system packages `bootstrap.sh` installs via apt-get.
    """
    import shutil
    import importlib.util
    from .env import get

    # (tool, apt-package, route it enables)
    tools = [
        ("pdftotext", "poppler-utils", "core: text/geometry/embedimages"),
        ("pdfimages", "poppler-utils", "core: images/embedimages"),
        ("gs", "ghostscript", "REQUIRED page rasterizer (the ONLY one; >=400 DPI for OCR/vision/layout)"),
        ("pdfinfo", "poppler-utils", "size/links/dests"),
        ("tesseract", "tesseract-ocr", "keyless OCR route (pdfdrill ocr)"),
        ("latex", "texlive-latex-base", "TikZ/table SVG (pdfdrill svg)"),
        ("pdflatex", "texlive-latex-base", "SVG / latex expansion"),
        ("dvips", "texlive-binaries", "DVI toolchain"),
        ("dvisvgm", "dvisvgm", "DVI -> SVG (pdfdrill svg, latexbook)"),
        ("scanimage", "sane-utils", "scanner ADF acquisition (pdfdrill scan)"),
    ]
    lines = ["pdfdrill requirement check", "=" * 27, "", "System tools:"]
    missing_pkgs: list[str] = []
    for tool, pkg, route in tools:
        ok = shutil.which(tool) is not None
        lines.append(f"  [{'OK ' if ok else 'MISSING'}] {tool:<10} — {route}")
        if not ok and pkg not in missing_pkgs:
            missing_pkgs.append(pkg)

    # TeX .sty packages (only meaningful once `latex` exists) — names the missing
    # font/style packages a mass TikZ/table render needs, BEFORE a batch fails.
    if shutil.which("latex"):
        sty_rows = tex_style_status()
        if sty_rows:
            lines.append("")
            lines.append("TeX packages (TikZ/table SVG route):")
            for r in sty_rows:
                lines.append(f"  [{'OK ' if r['present'] else 'MISSING'}] "
                             f"{r['sty']:<16} — {r['desc']}")
                if not r["present"] and r["pkg"] not in missing_pkgs:
                    missing_pkgs.append(r["pkg"])

    lines.append("")
    lines.append("Python deps:")
    for mod, note in [("pdfminer", "core: born-digital text layer (model)"),
                      ("pdfplumber", "core: tables / image rects / URL anchors"),
                      ("pydantic", "core (md/drill path)"),
                      ("pypdf", "core (formfields/attachments)"),
                      ("numpy", "optional [layout] extra — pdfdrill elements GNN"),
                      ("stanza", "optional [nlp] extra — pdfdrill nlp"),
                      ("img2pdf", "optional [scan] extra — pdfdrill scan "
                                  "(lossless image→PDF)"),
                      ("pikepdf", "optional [scan] extra — pdfdrill scan "
                                  "(PDF metadata, no pixel touch)")]:
        ok = importlib.util.find_spec(mod) is not None
        lines.append(f"  [{'OK ' if ok else 'MISSING'}] {mod:<10} — {note}")
    # libpostal: a find_spec on `postal` isn't enough (the C-extension needs
    # libpostal.so loadable), so actually attempt the load via the preloader.
    try:
        from .layout_elements import _libpostal_parser
        lp_ok = _libpostal_parser() is not None
    except Exception:
        lp_ok = False
    lines.append(f"  [{'OK ' if lp_ok else 'MISSING'}] {'libpostal':<10} — "
                 f"optional: real address-component parsing (pdfdrill elements / "
                 f"extract_addresses); auto-preloaded from /usr/local/lib")

    lines.append("")
    lines.append("API keys (env / .env; only needed for the named routes):")
    for var, route in [("MATHPIX_APP_ID", "mathpix/model"), ("MATHPIX_APP_KEY", "mathpix/snip"),
                       ("OPENAI_API_KEY", "vision"), ("NOVITA_API_KEY", "snip --gemma / route (Gemma-4)"),
                       ("PERPLEXITY_API_KEY", "bibfetch"), ("DEEPL_API_KEY", "translate")]:
        lines.append(f"  [{'set ' if get(var) else 'unset'}] {var:<18} — {route}")

    # Math-OCR routes — which path types equations, given what's available.
    lines.append("")
    lines.append("Math (equation) OCR routes — in preference order:")
    has_mpx = bool(get("MATHPIX_APP_ID") and get("MATHPIX_APP_KEY"))
    lines.append(f"  [{'OK ' if has_mpx else 'n/a'}] MathPix (`pdfdrill mathpix`) "
                 f"— LaTeX + CDN crops; needs MATHPIX_APP_ID/KEY")
    try:
        from . import llm_delegate as _D
        rt = _D.detect_runtime().value
    except Exception:
        rt = "none"
    agent_ok = rt in ("cli", "sandbox")
    lines.append(f"  [{'OK ' if agent_ok else 'n/a'}] delegated vision OCR "
                 f"(`pdfdrill visionocr`) — KEYLESS math route: the running Claude "
                 f"agent reads each page (runtime: {rt})")
    lines.append("  [n/a] tesseract (`pdfdrill ocr`) — PROSE ONLY; cannot type "
                 "equations (a math doc built this way sets NEEDS_VISION_OCR)")

    lines.append("")
    if missing_pkgs:
        # Expand the LaTeX/SVG package to the full support set when needed.
        if any(p in missing_pkgs for p in ("texlive-latex-base", "dvisvgm", "texlive-binaries")):
            for p in ("texlive-latex-base", "dvisvgm", "texlive-binaries"):
                if p in missing_pkgs:
                    missing_pkgs.remove(p)
            missing_pkgs += ["dvisvgm", "texlive-latex-base", "texlive-latex-recommended",
                             "texlive-latex-extra", "texlive-pictures",
                             "texlive-fonts-recommended", "texlive-fonts-extra",
                             "texlive-science",
                             # chemfig (texlive-pictures) inputs simplekv.tex,
                             # which Debian/Ubuntu ship in texlive-plain-generic.
                             "texlive-plain-generic", "texlive-binaries"]
        seen: list[str] = []
        for p in missing_pkgs:
            if p not in seen:
                seen.append(p)
        lines.append("To install the missing system tools (Debian/Ubuntu):")
        lines.append("  sudo apt-get install -y " + " ".join(seen))
    else:
        lines.append("All system tools present — every route is available.")
    return "\n".join(lines)


def cmd_config(action: str = "show", value: str | None = None) -> str:
    """Show / init / set the pdfdrill config FILE.

    `pdfdrill config`                 → show the active config file + locations
    `pdfdrill config --init`          → write a starter config
    `pdfdrill config --json`          → machine-readable
    `pdfdrill config --download-dir [DIR]` → get (no arg) or SET the download dir
    `pdfdrill config --library-root DIR`   → SET the library root (relocate target)
    """
    from . import config as cfg
    if action == "set-download-dir":
        written = cfg.set_key("download_dir", value or ".")
        return f"Set download_dir = {cfg.download_dir()}  ({written})"
    if action == "set-library-root":
        written = cfg.set_key("library_root", value or ".")
        return f"Set library_root = {cfg.library_root()}  ({written})"
    p = cfg.config_path()
    dl = cfg.download_dir()
    if action == "download-dir":
        return str(dl)
    if action == "library-dir":
        return str(cfg.library_root())
    if action == "init":
        written = cfg.write_default()
        cfg.load(refresh=True)
        return (f"Wrote starter config: {written}\n"
                f"  edit `download_dir` to change where downloads + each doc's "
                f"`<name>.drill` sidecar land.\n  active download_dir: {cfg.download_dir()}")
    if action == "json":
        return json.dumps({"config_path": str(p) if p else None,
                           "download_dir": str(dl)}, ensure_ascii=False)
    return "\n".join([
        "pdfdrill config",
        f"  config file   : {p if p else '(none — using defaults; run `pdfdrill config --init`)'}",
        f"  download_dir  : {dl}",
        "                  ↑ URL/arXiv downloads land HERE (in a per-doc folder).",
        f"  library_root  : {cfg.library_root()}",
        "                  ↑ one self-contained folder per drilled doc "
        "(<stem>/<stem>.pdf + model, report.html, *.md …). `pdfdrill relocate` "
        "migrates legacy scattered drills into it.",
        f"  drillui store : {dl / '.drillui_session.docpack'}  (multi-doc `add`)",
    ])


def cmd_relocate(paths, library=None, apply=False) -> str:
    """Migrate legacy scattered drills into the self-contained library layout —
    `<library>/<stem>/` holding the PDF + every `X.*` sibling + the flattened
    `X.pdf.drill/` blobs, with `X.pdf.drill.json` renamed `X.drill.json`.

    `paths` may be individual PDFs and/or directories (scanned recursively for
    legacy PDFs). Dry-run by default — prints the plan; pass `apply=True` to move.
    Collision-safe (never overwrites) and idempotent (already-migrated docs are
    skipped). See docs/superpowers/specs/2026-07-14-self-contained-doc-folders.md.
    """
    from . import config as cfg
    from . import relocate as R
    lib = Path(library).expanduser() if library else cfg.library_root()

    pdfs: list[Path] = []
    for raw in (paths or []):
        p = Path(raw).expanduser()
        if p.is_dir():
            pdfs.extend(R.find_docs(p))
        elif p.suffix.lower() == ".pdf" and p.exists():
            if p.resolve().parent.name != p.stem:      # skip already-migrated
                pdfs.append(p.resolve())
    # de-dup preserving order
    seen: set = set()
    pdfs = [p for p in pdfs if not (p in seen or seen.add(p))]

    if not pdfs:
        return (f"No legacy scattered drills to relocate (library: {lib}).\n"
                "A doc is 'migrated' when it lives at <library>/<stem>/<stem>.pdf.")

    lines = [f"{'RELOCATE' if apply else 'PLAN (dry-run — pass --apply to move)'} "
             f"→ library: {lib}", ""]
    tot_moved = tot_skipped = 0
    for pdf in pdfs:
        plan = R.plan_relocation(pdf, lib)
        if not plan:
            continue
        target = lib / pdf.stem
        lines.append(f"• {pdf.name}  →  {target}/  ({len(plan)} items)")
        if apply:
            moved, skipped = R.apply_relocation(pdf, lib)
            tot_moved += moved
            tot_skipped += skipped
            note = f"    moved {moved}" + (f", skipped {skipped} (already present)"
                                           if skipped else "")
            lines.append(note)
    lines.append("")
    if apply:
        lines.append(f"Done: {len(pdfs)} doc(s), {tot_moved} files moved"
                     + (f", {tot_skipped} skipped." if tot_skipped else "."))
        lines.append("Tip: set `library_root` in your config so new downloads land "
                     "here too — `pdfdrill config --library-root <dir>`.")
    else:
        lines.append(f"{len(pdfs)} doc(s) would be relocated. "
                     "Re-run with `--apply` to move them.")
    return "\n".join(lines)


_ARTIFACT_EXTS = (".html", ".htm", ".json", ".md", ".svg", ".pdf", ".txt",
                  ".tex", ".csv")
# Huge / internal artifacts skipped by default (shown with --all): the raw model
# (tens of MB) and the IR/packed sidecars — not things to open in a browser tab.
_HEAVY_INTERNAL = {"model.docmodel.json", "model.docpack.json", "ir.json"}
_HEAVY_BYTES = 15_000_000


def _list_artifacts(sc: "Sidecar", all_files: bool = False) -> "list[Path]":
    """Top-level drill OUTPUTS (report.html, <bibkey>.md, *.json, *.txt) + rendered
    `svg/` — NOT the texsrc/remath/ocr/… scratch trees. By default skips the giant
    model JSON / IR sidecars; `all_files=True` keeps them."""
    d = sc.blob_dir
    if not d.exists():
        return []
    files = [p for p in d.glob("*")
             if p.is_file() and p.suffix.lower() in _ARTIFACT_EXTS]
    svgdir = d / "svg"
    if svgdir.is_dir():
        files += [p for p in svgdir.glob("*.svg")]
    # OKF bundles live in okf/<bibkey>/; surface each bundle's index.md entry point
    # (the whole bundle is reachable from it via relative links) so drillui lists it.
    for okfsub in ("okf", "okf-semantic"):
        okfdir = d / okfsub
        if okfdir.is_dir():
            files += [p for p in okfdir.glob("*/index.md") if p.is_file()]
    if not all_files:
        # The heavy-size cut hides the giant model JSON — but NEVER the doc's own
        # PDF (which lives in the folder in the self-contained layout and is meant
        # to be opened/viewed, however large). Exempt PDFs from the size filter.
        files = [p for p in files
                 if p.name not in _HEAVY_INTERNAL
                 and (p.suffix.lower() == ".pdf" or p.stat().st_size <= _HEAVY_BYTES)]
    files.sort(key=lambda p: (p.suffix.lower(), p.name))
    return files


def _artref(sc: "Sidecar", p: Path) -> str:
    """A browser-facing artifact reference RELATIVE TO THE LIBRARY ROOT
    (`blob_dir.parent`) so it carries the DOC FOLDER — `<stem>/<file>` in the
    self-contained layout, `<name>.pdf.drill/<file>` in the legacy one. A bare
    `<file>` (what `relative_to(pdf.parent)` collapses to when the folder IS the
    doc folder) is ambiguous for the drillui bridge: a generic name like
    `tables.html` then matches the WRONG doc folder (the "found but empty" bug),
    and a prefixed name can 404. Falls back to the basename if p escapes the root."""
    try:
        return str(p.relative_to(sc.blob_dir.parent))
    except ValueError:
        return p.name


def cmd_artifacts(pdf: Path, all_files: bool = False) -> str:
    """List the openable files in this doc's drill folder (report.html, the
    extracted `<bibkey>.md`, tiddlers/semantic/llm `*.json`/`*.txt`, SVGs) with
    their paths — so they're clickable in the drillui Outputs panel (the browser
    opens md/json/svg/pdf/html directly). The giant model JSON is skipped unless
    `--all`. No `fetch`, no `find`."""
    sc = Sidecar(pdf)
    if not sc.blob_dir.exists():
        return (f"No drill folder yet for {pdf.name} — run `pdfdrill model` / "
                f"`md` / `report` / `tiddlers` first.")
    rel_dir = _artref(sc, sc.blob_dir)
    files = _list_artifacts(sc, all_files=all_files)
    if not files:
        return f"No openable artifacts in {rel_dir}/ yet (run md/report/tiddlers/…)."
    lines = [f"{len(files)} artifact(s) in {rel_dir}/ — click to open in a tab:"]
    for p in files:
        lines.append(f"  {_artref(sc, p)}  "
                     f"({p.stat().st_size / 1024:.0f} KB)")
    if not all_files and any((sc.blob_dir / n).exists() for n in _HEAVY_INTERNAL):
        lines.append("  (the raw model JSON is hidden — `pdfdrill artifacts "
                     f"{pdf.name} --all` to include it)")
    return "\n".join(lines)


def cmd_ocr(pdf: Path, lang: str = "eng", ppi: int = 300, force: bool = False,
            min_conf: float | None = None, typing: bool = True) -> str:
    """Build a MathPix-compatible `<pdf>.lines.json` via tesseract OCR (enriched).

    The MathPix-free OCR input path: render each page with Ghostscript (>=400 DPI
    floor), OCR with tesseract, and write a `lines.json` of the shape
    `pdfdrill model` ingests — so the whole toolkit runs without a MathPix key.

    The lines are TYPED MathPix-compatibly (section_header / table / equation /
    diagram / page_info), carry per-line `conf` + `words` + block/par/line, and
    their regions are PDF POINTS (`ocr.units="pt"`, `image_id="tesseract-p{N}"`),
    so `/cropped/…&units=pt` local-pyramid crops work on the keyless path.
    Second passes add Greek re-OCR of equation regions, a pdftotext text-layer
    merge, and barcodes.

    HONEST LIMIT: an equation line gets a correct REGION but its TEXT is garbled
    (tesseract cannot read math) — there is no LaTeX on this route. Use
    `pdfdrill visionocr` / `mathpix` for the math itself; the regions are what
    let those crop it. `--lang eng+deu` for German (the module also
    auto-corrects the language order); `--min-conf` tunes the noise filter;
    `--no-typing` falls back to untyped text lines.
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
    kw: dict = {"ppi": ppi, "lang": lang, "typing": typing}
    if min_conf is not None:
        kw["min_conf"] = float(min_conf)
    lj = ocr_lines.build_lines_json(pdf, out_dir, **kw)
    lines_path.write_text(json.dumps(lj, ensure_ascii=False), encoding="utf-8")

    n_pages = len(lj["pages"])
    n_lines = sum(len(p["lines"]) for p in lj["pages"])
    meta = lj.get("ocr") or {}
    counts = meta.get("type_counts") or {}
    lang_eff = meta.get("lang_effective") or lang
    sc.set_evidence("ocr_lang", lang)
    sc.set_evidence("ocr_lang_effective", lang_eff)
    sc.set_evidence("ocr_pages", n_pages)
    sc.set_evidence("ocr_lines", n_lines)
    sc.set_evidence("ocr_units", meta.get("units"))
    sc.set_evidence("ocr_render_dpi", meta.get("render_dpi"))
    sc.set_evidence("ocr_type_counts", counts)
    if meta.get("warnings"):
        sc.set_evidence("ocr_warnings", meta["warnings"])
    prev = ",".join(sorted(sc.facts - {OCR_BUILT})) or "INIT"
    sc.add_fact(OCR_BUILT)
    sc.log_transition("ocr", prev, OCR_BUILT, cost_ms=(time.monotonic() - t0) * 1000,
                      detail=f"{n_pages} pages, {n_lines} lines, lang={lang_eff}")
    sc.save()

    typed = ", ".join(f"{k}={v}" for k, v in counts.items()
                      if v and k not in ("absorbed_lines",)) or "none"
    lang_note = (f" (auto-corrected from '{lang}')" if lang_eff != lang else "")
    warn = ("  ⚠ " + "; ".join(meta["warnings"][:2])) if meta.get("warnings") else ""
    eq = counts.get("equation", 0)
    math_note = (
        f" {eq} equation region(s) typed — their TEXT is garbled (tesseract can't "
        f"read math); run `pdfdrill visionocr {pdf.name}` or `mathpix` for the "
        f"LaTeX (the regions are what let those crop it)." if eq else
        " No equation regions found — if this doc has math, the LaTeX routes are "
        "`visionocr` / `mathpix`.")
    return (
        f"Tesseract OCR ({lang_eff}{lang_note}): {n_lines} line(s) across "
        f"{n_pages} page(s) at {meta.get('render_dpi', '?')} DPI → "
        f"{lines_path.name} (MathPix-compatible; regions in "
        f"{meta.get('units', '?')}, crops via /cropped/…&units=pt).\n"
        f"  typed: {typed}\n"
        f"  Build the structure with `pdfdrill model {pdf.name}`.{math_note}{warn}"
    )


def _load_or_build_continuity(pdf: Path, sc: "Sidecar", force: bool = False,
                              ppi: int = 250, lang: str = "deu+eng"):
    """Return {page_no: continuity-info}, from the sidecar cache or by OCRing
    the full pages. Cached because the render+OCR of every page is slow. Returns
    (data, error_msg): error_msg set only when the OCR tools are unavailable."""
    from . import continuity
    cached = sc.get_evidence("continuity")
    if cached and not force:
        return {int(k): v for k, v in cached.items()}, None
    ok, msg = continuity.tools_available()
    if not ok:
        return None, msg
    out_dir = sc.blob_dir / "continuity"
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    data = continuity.extract_continuity(pdf, out_dir, ppi=ppi, lang=lang)
    sc.set_evidence("continuity", {str(k): v for k, v in data.items()})
    sc.save()
    return data, None


def cmd_pageside(pdf: Path) -> str:
    """Classify each page as recto (right) / verso (left) book page.

    Column indices are LAYOUT positions, not semantic roles — on a book with
    marginal side notes their meaning flips with the page side (verso: col 0 =
    side notes; recto: col 0 = body). Three per-page signals (printed page-
    number parity incl. roman numerals, page-number x-position on the OUTER
    edge, narrow-side-note-column asymmetry) fused by confidence-weighted
    vote, then the sequence-alternation post-pass (book pages alternate).
    Attaches `page_side`/`page_side_confidence` to each model `Page`.
    """
    from . import rectoverso

    sc = Sidecar(pdf)
    lines_path = _lines_json_path(pdf)
    if not lines_path.exists():
        return (f"No {lines_path.name} — run `pdfdrill mathpix {pdf.name}` "
                f"(or the keyless `pdfdrill ocr {pdf.name}`) first.")
    t0 = time.monotonic()
    results = rectoverso.apply_alternation(
        rectoverso.classify_lines_json(str(lines_path)))
    sides = [{"page": i, "side": r.side, "confidence": r.confidence,
              "signals": r.evidence.get("signals", {})}
             for i, r in enumerate(results, start=1)]
    sc.set_evidence("page_sides", sides)

    # Attach to the model's Page objects, if built (continuity pattern).
    model_path = _model_path(sc)
    annotated = 0
    model_exists = model_path.exists()
    if model_exists:
        from docmodel.core import Document
        doc = load_model(model_path)
        pages = {p.props.get("page_number"): p for p in doc.objects_of_type("Page")}
        for i, r in enumerate(results, start=1):
            pg = pages.get(i)
            if pg is not None and r.side:
                pg.props["page_side"] = r.side
                pg.props["page_side_confidence"] = r.confidence
                annotated += 1
        save_model(model_path, doc)
    sc.save()

    n = len(results)
    known = [r for r in results if r.side]
    rectos = sum(1 for r in known if r.side == "recto")
    by_sig = {}
    for r in known:
        for k in r.evidence.get("signals", {}):
            by_sig[k] = by_sig.get(k, 0) + 1
    sig_s = ", ".join(f"{k}:{v}" for k, v in sorted(by_sig.items()))
    mean_conf = sum(r.confidence for r in known) / len(known) if known else 0.0
    return (f"Page sides for {n} page(s): {rectos} recto / {len(known) - rectos} "
            f"verso ({n - len(known)} unknown), mean confidence {mean_conf:.2f} "
            f"(signals: {sig_s}). "
            + (f"Attached page_side to {annotated} model Page(s). " if annotated
               else ("Model present, nothing to attach (no page got a side). "
                     if model_exists else
                     "No model built yet — sides stored in the sidecar; `pdfdrill "
                     "model` then re-run to annotate Pages. "))
            + "Use it to map column 0/1 to body vs side note per page "
              "({:.0f} ms).".format((time.monotonic() - t0) * 1000))


def _born_digital_scan_guard(pdf: Path, cmd: str) -> "str | None":
    """Scan-triage commands (continuity/ordered/autosegment) OCR every page to
    segment a SCANNED multi-document bundle. On a BORN-DIGITAL doc (a text layer)
    that's semantically wrong and slow (a 200-page OCR that times out). Returns a
    clear skip message when the doc is born-digital, else None. Uses the cached
    text-layer signal; probes cheaply if `size` never ran."""
    sc = Sidecar(pdf)
    tl = sc.get_evidence("text_layer")
    if tl is None:
        try:
            tl, _, _ = _probe_text_layer(pdf)
        except Exception:                            # noqa: BLE001
            tl = None
    if tl:
        return (f"`{cmd}` is a SCAN-triage command — per-page OCR to segment a "
                f"SCANNED multi-document bundle. {pdf.name} is BORN-DIGITAL (it "
                f"has a text layer), so scan-artifact segmentation doesn't apply "
                f"and would needlessly OCR every page. Use `pdfdrill model` + "
                f"`booktoc`/`toc`/`llmtext` for its structure. (These triage "
                f"commands are for scanned bundles like a shuffled stack of "
                f"letters.)")
    return None


def cmd_continuity(pdf: Path, force: bool = False, ppi: int = 250,
                   lang: str = "deu+eng") -> str:
    """Recover page-continuity markers from the page MARGINS via full-page OCR.

    German documents print "Seite N von M" / "Fortsetzung Seite N" / control
    numbers in the margin, OUTSIDE MathPix's content crop — so they're invisible
    to the MathPix path. This renders each page and OCRs the whole page
    (margins included) with tesseract, then classifies the continuity tokens
    (with their margin position). When a `model` exists, the page-sequence is
    also attached to each `Page` (`seq_in_doc`/`doc_total`/`is_continuation`/
    `control_no`) — see `pdfdrill status`. Reuses the `ocr`/`geometry` plumbing;
    never routes through the MathPix crop. Cached in the sidecar.
    """
    if not force:
        guard = _born_digital_scan_guard(pdf, "continuity")
        if guard:
            return guard
    sc = Sidecar(pdf)
    data, err = _load_or_build_continuity(pdf, sc, force=force, ppi=ppi, lang=lang)
    if err:
        return (f"Continuity OCR needs {err} Install poppler-utils + "
                f"tesseract-ocr (with the `deu` language pack) and rerun.")

    # ISSUE 2: attach the page-sequence to the model's Page objects, if built.
    attached = 0
    model_path = _model_path(sc)
    if model_path.exists():
        from docmodel.core import Document
        doc = load_model(model_path)
        pages = {p.props.get("page_number"): p for p in doc.objects_of_type("Page")}
        for page_no, info in data.items():
            pg = pages.get(page_no)
            if pg is None:
                continue
            for k in ("seq_in_doc", "doc_total", "is_continuation",
                      "next_seite", "control_no"):
                if info.get(k) not in (None, False):
                    pg.props[k] = info[k]
            attached += 1
        save_model(model_path, doc)

    prev = ",".join(sorted(sc.facts - {CONTINUITY_BUILT})) or "INIT"
    sc.add_fact(CONTINUITY_BUILT)
    n_seq = sum(1 for i in data.values() if i.get("seq_in_doc") is not None)
    n_marker = sum(1 for i in data.values()
                   if i.get("seq_in_doc") is not None or i.get("is_continuation"))
    sc.set_evidence("continuity_pages_with_seq", n_seq)
    sc.set_evidence("continuity_pages_with_marker", n_marker)
    sc.log_transition("continuity", prev, CONTINUITY_BUILT,
                      detail=f"{n_marker}/{len(data)} pages w/ a continuity marker")
    sc.save()

    lines = []
    for page_no in sorted(data):
        i = data[page_no]
        bits = []
        if i.get("seq_in_doc") is not None:
            bits.append(f"Seite {i['seq_in_doc']}"
                        + (f" von {i['doc_total']}" if i.get("doc_total") else ""))
        if i.get("is_continuation"):
            bits.append(f"→ Fortsetzung Seite {i.get('next_seite') or '?'}")
        if i.get("control_no"):
            bits.append(f"control={i['control_no']}")
        if bits:
            where = ",".join(sorted({m["where"] for m in i.get("markers", [])}))
            lines.append(f"  p{page_no:>2}: {' | '.join(bits)}  [{where}]")
    body = "\n".join(lines) if lines else "  (no continuity markers found)"
    head = (f"Continuity (full-page OCR, margins included): {n_marker}/{len(data)} "
            f"page(s) carry a continuity marker ({n_seq} a 'Seite N' sequence, "
            f"{n_marker - n_seq} a 'Fortsetzung' pointer)"
            + (f"; page-sequence attached to {attached} Page object(s)" if attached else "")
            + ". Pages without a marker are typically single-page documents. "
            f"These include margin-only markers MathPix's content crop drops.")
    return head + "\n" + body


# A bank name: the bank-type keyword + ≤2 preceding capitalised tokens, on a
# single line (no newline spanning, so it doesn't swallow a sender block).
_BANK_NAME = re.compile(
    r"\b((?:[A-ZÄÖÜ][\wäöüß.\-]*[^\S\n]+){0,2}"
    r"(?:Kreissparkasse|Sparkasse|Volksbank|Raiffeisenbank|Bankhaus|Bank)"
    r"(?:[^\S\n]+[A-ZÄÖÜ][\wäöüß.\-]*){0,2})\b")


def _bank_near(text: str, pos: int) -> str:
    """Best-effort bank name in a window around an IBAN occurrence."""
    window = text[max(0, pos - 160):pos + 40]
    m = _BANK_NAME.search(window)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _page_text_from_model(doc) -> dict:
    """Per-page content text from the mathpix_lines stream (the OCR content)."""
    pages: dict[int, list[str]] = {}
    mp = doc.streams.get("mathpix_lines")
    if mp is None:
        return {}
    for a in mp.anchors:
        p = mp.payload[a]
        t = p.get("text_display") or p.get("text") or ""
        if t.strip():
            pages.setdefault(p.get("_page"), []).append(t)
    return {pg: "\n".join(v) for pg, v in pages.items() if pg is not None}


def _page_lines_from_model(doc) -> dict:
    """Per-page list of {text, region} from the mathpix_lines stream — the raw
    geometry needed to detect out-of-column margin content (works for MathPix and
    the tesseract-OCR path, both carrying a `region`)."""
    pages: dict[int, list] = {}
    mp = doc.streams.get("mathpix_lines")
    if mp is None:
        return {}
    for a in mp.anchors:
        p = mp.payload[a]
        region = p.get("region")
        # use the clean `text` (text_display carries layout newlines that would
        # split a multi-line recipient block with spurious blank lines)
        text = (p.get("text") or p.get("text_display") or "").strip()
        if region and text and p.get("_page") is not None:
            pages.setdefault(p["_page"], []).append({"text": text, "region": region})
    return pages


def cmd_entities(pdf: Path, force: bool = False) -> str:
    """Extract commercial entities per page — self-contained, zero external tools.

    Per page: IBAN (mod-97 checksum-validated; DE BLZ/Konto + bank name derived
    from the page text), BIC, German postal ADDRESS block, and labelled ids
    (Steuernummer/Kassenzeichen/Aktenzeichen/Rechnungs-/Kundennummer). Built on
    the additive `features` extractors; reuses the existing model's content text.
    """
    from docmodel.core import Document
    from features import (extract_iban, extract_bic, extract_german_address,
                          extract_ids)

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    doc = load_model(model_path)
    page_text = _page_text_from_model(doc)

    per_page: dict[int, dict] = {}
    n_iban = n_valid = 0
    for page in sorted(page_text):
        text = page_text[page]
        ibans = extract_iban.extract(text, str(page))
        rec = {"iban": [], "bic": [f.value for f in extract_bic.extract(text, str(page))],
               "address": [f.value for f in extract_german_address.extract(text, str(page))],
               "ids": [(f.type, f.value) for f in extract_ids.extract(text, str(page))]}
        for f in ibans:
            n_iban += 1
            valid = f.confidence >= 1.0
            n_valid += valid
            parts = extract_iban.german_parts(f.value)
            bank = _bank_near(text, f.start or 0)
            rec["iban"].append({"iban": f.value, "valid": valid,
                                 "blz": parts.get("blz"), "konto": parts.get("konto"),
                                 "bank": bank})
        if rec["iban"] or rec["bic"] or rec["address"] or rec["ids"]:
            per_page[page] = rec

    sc.set_evidence("entities", {str(k): v for k, v in per_page.items()})
    sc.set_evidence("entities_ibans_valid", n_valid)
    prev = ",".join(sorted(sc.facts - {ENTITIES_BUILT})) or "INIT"
    sc.add_fact(ENTITIES_BUILT)
    sc.log_transition("entities", prev, ENTITIES_BUILT,
                      detail=f"{n_valid}/{n_iban} valid IBAN, {len(per_page)} pages")
    sc.save()

    lines = []
    for page in sorted(per_page):
        r = per_page[page]
        for ib in r["iban"]:
            tag = "valid" if ib["valid"] else "INVALID checksum"
            extra = (f", BLZ {ib['blz']}, Konto {ib['konto']}" if ib.get("blz") else "")
            bank = f" — {ib['bank']}" if ib.get("bank") else ""
            lines.append(f"  p{page:>2} IBAN {ib['iban']} ({tag}{extra}){bank}")
        for b in r["bic"]:
            lines.append(f"  p{page:>2} BIC  {b}")
        for a in r["address"]:
            lines.append(f"  p{page:>2} ADDR {a}")
        for typ, val in r["ids"]:
            lines.append(f"  p{page:>2} {typ} {val}")
    body = "\n".join(lines) if lines else "  (no commercial entities found)"
    return (f"Entities: {n_valid}/{n_iban} IBAN(s) checksum-valid across "
            f"{len(per_page)} page(s); BIC / German address / ids too. "
            f"Zero external tools (built-in mod-97 IBAN check).\n" + body)


def cmd_segment(pdf: Path, force: bool = False) -> str:
    """Partition a scanned bundle into ordered documents (CR #3).

    Groups pages by a stable per-document signature (Kassen-/Akten-/Steuernummer,
    else sender/letterhead), orders each group by its continuity number (so the
    shuffled/duplex physical order is irrelevant), and flags duplicate copies.
    Consumes `continuity` (Issue 1/2) + `entities` (Issue 4); auto-chains both.
    """
    from docmodel.core import Document
    from . import segment as seg

    sc = Sidecar(pdf)
    cont, err = _load_or_build_continuity(pdf, sc, force=force)
    if err:
        return f"Segment needs continuity OCR: {err}"
    if not sc.has(ENTITIES_BUILT) or force:
        cmd_entities(pdf, force=force)
        sc = Sidecar(pdf)
    entities = sc.get_evidence("entities") or {}

    model_path = _model_path(sc)
    page_text = {}
    if model_path.exists():
        doc = load_model(model_path)
        page_text = _page_text_from_model(doc)

    docs = seg.segment(cont, entities, page_text)

    prev = ",".join(sorted(sc.facts - {SEGMENTED})) or "INIT"
    sc.add_fact(SEGMENTED)
    sc.set_evidence("segments", len(docs))
    sc.log_transition("segment", prev, SEGMENTED, detail=f"{len(docs)} documents")
    sc.save()

    lines = []
    for i, d in enumerate(docs, 1):
        pp = ",".join(f"p{p}" for p in d["pages"])
        tot = f"/{d['total']}" if d.get("total") else ""
        dup = f"  [dup: {','.join('p'+str(p) for p in d['duplicates'])}]" if d["duplicates"] else ""
        ident = f" ({d['identifier']})" if d.get("identifier") else ""
        lines.append(f"  Doc {i} — {d['label']}{ident}, {len(d['pages'])} pp{tot}: {pp}{dup}")
    return (f"Segmented {pdf.name} into {len(docs)} document(s) by sender/identifier "
            f"+ continuity order (duplex/shuffle handled via the page-sequence "
            f"number):\n" + "\n".join(lines))


def cmd_elements(pdf: Path, force: bool = False, model: str | None = None,
                 bibkey: str | None = None, source: str | None = None,
                 ppi: int = 300, lang: str = "deu+eng") -> str:
    """Find structured layout ELEMENTS (postal addresses, BOM line items) with
    the geometric-attention GNN over tesseract word boxes (`pdfdrill.tsv_gcn`).

    The layout analogue of the MathPix→LaTeX layer: each element is isolated,
    given a content-addressed identity (blake3/sha256), and emitted as a
    TiddlyWiki tiddler (`<bibkey>_AD/BM_<serial>`) with data fields, a normalised
    `geo-projection`, and a learned `projection` embedding. The result is dropped
    into the sidecar as a `layout` layer and written to a sibling
    `<bibkey>.elements.tiddlers.json`.

    Additive — it never touches the docmodel/docops pipeline. The GNN path needs
    a trained model supplied via `--model` (train one with `python -m
    pdfdrill.tsv_gcn synth/train`); without a model it falls back to the optional
    `extract_addresses` heuristic (address-only) if that module is importable,
    else returns an actionable message. Degrades cleanly when NumPy/OCR tools are
    absent. Reuses the `ocr`/`geometry` page-render + tesseract plumbing.
    """
    from . import layout_elements

    sc = Sidecar(pdf)
    key = resolve_bibkey(pdf, bibkey, sc)
    model_path = Path(model).expanduser() if model else None
    if model_path is not None and not model_path.exists():
        return (f"--model {model_path} not found. Train one with "
                f"`python -m pdfdrill.tsv_gcn synth <dir> -n 24 && "
                f"python -m pdfdrill.tsv_gcn train <dir>/*.tsv --labels-dir <dir> "
                f"-o {model_path.name}`.")

    t0 = time.monotonic()
    blob_dir = sc.blob_dir / "elements"
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    res = layout_elements.find_elements(
        pdf, model_path=model_path, bibkey=key, source=source,
        blob_dir=blob_dir, ppi=ppi, lang=lang, force=force)

    if not res["available"]:
        return f"pdfdrill elements: {res['message']}"

    tiddlers = res["tiddlers"]
    out_path = sc.blob_dir / f"{key}.elements.tiddlers.json"
    out_path.write_text(json.dumps(tiddlers, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    # Layout layer in the sidecar: a compact, prose-addressable summary.
    by_kind: dict[str, int] = {}
    layer = []
    for t in tiddlers:
        by_kind[t["kind"]] = by_kind.get(t["kind"], 0) + 1
        layer.append({"title": t["title"], "kind": t["kind"], "page": t["page"],
                      "source": t.get("source", ""), "hash": t["hash"],
                      "bbox": t.get("bbox", "")})
    sc.set_evidence("layout", layer)
    sc.set_evidence("layout_counts", by_kind)
    sc.set_evidence("layout_tiddlers_path",
                    str(out_path.relative_to(sc.pdf_path.parent)))
    prev = ",".join(sorted(sc.facts - {ELEMENTS_BUILT})) or "INIT"
    sc.add_fact(ELEMENTS_BUILT)
    sc.log_transition("elements", prev, ELEMENTS_BUILT,
                      cost_ms=(time.monotonic() - t0) * 1000,
                      detail=f"{len(tiddlers)} elements " + str(by_kind))
    sc.save()

    n_ad = by_kind.get("address", 0)
    n_bm = by_kind.get("bom-line", 0)
    prov = {}
    for e in res["elements"]:
        prov[e.get("source", "?")] = prov.get(e.get("source", "?"), 0) + 1
    prov_str = (", ".join(f"{k}={v}" for k, v in sorted(prov.items()))
                if prov else "—")
    route = ("GNN model" if res["model"] else "extract_addresses heuristic")

    lines = []
    for t in tiddlers:
        txt = (t.get("text", "") or "").replace("\n", " / ")[:60]
        agr = f" agree={t['agreement']}" if t.get("agreement") not in (None, "", "0.0") else ""
        lines.append(f"  {t['title']}  [{t['kind']} p{t['page']} "
                     f"{t.get('source', '')}{agr}]  {txt}")
    body = "\n".join(lines) if lines else "  (no layout elements found)"
    # Be route-accurate: only the GNN path attaches a learned projection
    # embedding; the heuristic path emits a content hash (+ bbox/geo-projection
    # when the page is known) but no embedding.
    h0 = tiddlers[0]["hash"][:10] + "…" if tiddlers else "n/a"
    n_proj = sum(1 for t in tiddlers if t.get("projection"))
    n_geo = sum(1 for t in tiddlers if t.get("geo-projection"))
    extras = [f"content-addressed ({h0})"]
    if n_geo:
        extras.append(f"{n_geo} with a geo-projection")
    if n_proj:
        extras.append(f"{n_proj} with a learned GNN projection embedding")
    # libpostal component-parsing status (optional upgrade for the address path).
    n_lp = res.get("libpostal_enriched", 0)
    if n_lp:
        lp_note = f" {n_lp} address(es) parsed into components by libpostal."
    elif n_ad and not res["model"]:
        lp_note = (" Tip: install libpostal (pypostal `postal`) for clean "
                   "road/house-number/postcode/city components on heuristic "
                   "addresses (it degrades silently when absent).")
    else:
        lp_note = ""
    return (f"Layout elements ({route}): {len(tiddlers)} found — {n_ad} address(es), "
            f"{n_bm} BOM-line(s) → {out_path.name} (+ sidecar `layout` layer). "
            f"Address provenance: {prov_str}. Tiddlers: {'; '.join(extras)}.{lp_note}\n"
            + body)


def cmd_semantic(pdf: Path, store: str | None = None, force: bool = False) -> str:
    """Build the semantic graph (CSP layer): entities accumulate evidence.

    Turns this document's extractor output (sender, IBAN/BIC/address/ids) into
    Evidence fed through the IdentityResolver — extractors are sensors, the graph
    is the artifact. The address/IBAN are evidence pointing at the Company, not
    primary objects. Persists `<bibkey>.semantic.json`. Pass `--store graph.json`
    to accumulate ACROSS documents: run it over several PDFs with the same store
    and one Company gathers evidence (addresses, bank accounts, tax ids) from all
    of them — the thing a flat chunk store cannot do.
    """
    from docmodel.core import Document
    from features import (extract_iban, extract_bic, extract_german_address,
                          extract_ids)
    from semantic.graph import SemanticGraph
    from semantic.identity import IdentityResolver
    from semantic.build import ingest_document
    from semantic import proof, compiler
    # Import the content-identity layer BEFORE the resolver reindex below: it
    # registers the `content_hash` strong key at import, so reindex() indexes the
    # loaded graph's content hashes and a re-run dedups (not double-mints).
    from semantic.layers import content_identity  # noqa: F401  (side effect)
    from . import segment as seg

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."
    doc = load_model(model_path)
    page_text = _page_text_from_model(doc)
    key = resolve_bibkey(pdf, None, sc)

    # Load-or-create the graph; --store enables cross-document accumulation.
    store_path = Path(store).expanduser() if store else None
    sem_path = sc.blob_dir / f"{key}.semantic.json"
    g = None
    if store_path and store_path.exists():
        g = SemanticGraph.from_dict(json.loads(store_path.read_text(encoding="utf-8")))
    elif sem_path.exists() and not force:
        g = SemanticGraph.from_dict(json.loads(sem_path.read_text(encoding="utf-8")))
    if g is None:
        g = SemanticGraph()
    n_before = g.entity_count()
    r = IdentityResolver(g).reindex()

    from semantic.blocks import detect_recipient
    from semantic.attribution import attribute

    # Per-page geometry (text + region) for region-based attribution.
    page_lines = _page_lines_from_model(doc)

    # Per-page extractor output (the sensors). IBAN/BIC/ids are not region-bound;
    # addresses are attributed by region (sender vs recipient) below.
    page_recs: dict[int, dict] = {}
    for p in sorted(page_text):
        t = page_text[p]
        prec = {"iban": [], "bic": [], "ids": []}
        for f in extract_iban.extract(t, str(p)):
            parts = extract_iban.german_parts(f.value)
            prec["iban"].append({"iban": f.value, "blz": parts.get("blz"),
                                 "konto": parts.get("konto"),
                                 "bank": _bank_near(t, f.start or 0)})
        prec["bic"] += [f.value for f in extract_bic.extract(t, str(p))]
        prec["ids"] += [(f.type, f.value) for f in extract_ids.extract(t, str(p))]
        page_recs[p] = prec

    def _agg(pages):
        rec = {"iban": [], "bic": [], "address": [], "ids": []}
        for p in pages:
            for k in ("iban", "bic", "ids"):
                rec[k] += page_recs.get(p, {}).get(k, [])
        return rec, "\n".join(page_text.get(p, "") for p in pages)

    def _is_auth(name):
        return bool(re.search(r"\b(Finanzamt|Stadt|Stadtkasse|Bundes)", name or ""))

    def _real_sender(name):
        """A genuine sender name has letters and isn't just an id/number — so a
        segment keyed on a Steuer-/Kassenzeichen value doesn't mint a pseudo-
        company named after the number. Also rejects a BANK name: on a commercial
        doc the bank in the transfer line is the payee's bank (captured as the
        account's `bank`/`bic` evidence), NOT the document issuer — so e.g. an AOK
        dunning letter is not mis-attributed to 'Commerzbank AG'."""
        if not name or name.replace(" ", "").isdigit():
            return None
        if re.search(r"\b(Bank|Sparkasse|Volksbank|Raiffeisen|Commerzbank|Postbank|"
                     r"Bankhaus|Kreditinstitut)\b", name, re.I):
            return None
        return name if re.search(r"[A-Za-zÄÖÜäöüß]{3,}", name) else None

    def _attribute(pages, fallback_text):
        """Region-based: split into sender (header/footer) text + recipient (body)
        using line geometry; fall back to whole text when no regions are present."""
        lines = [l for p in pages for l in page_lines.get(p, [])]
        if lines:
            att = attribute(lines)
            return (att.sender_text or fallback_text), att.recipient
        return fallback_text, detect_recipient(fallback_text)

    def _sender_and_recipient(rec, pages, text, label=None):
        sender_text, recp = _attribute(pages, text)
        # prefer the sender from the header/footer region; fall back to the whole
        # text (then the segment label) so we never LOSE a sender when the layout
        # doesn't classify cleanly — region only sharpens, it doesn't gate.
        sender = _real_sender(seg.sender_of(sender_text) or seg.sender_of(text) or label)
        rec = dict(rec)
        # company addresses come from the sender (header/footer) region only
        rec["address"] = [f.value for f in extract_german_address.extract(sender_text)]
        rname = rrec = None
        if recp:
            rname, rrec = recp["name"], {"address": [recp["address"]]}
            m = re.search(r"\b(\d{5})\b", recp["address"])
            if m:                       # belt-and-suspenders: drop recipient PLZ from sender
                rec["address"] = [a for a in rec["address"] if m.group(1) not in a]
        return sender, rec, rname, rrec

    # Segment-aware: a scanned bundle is several senders → ingest each as its own
    # document so IBANs/ids don't collapse onto one company. Single-sender PDFs
    # ingest as one document. (continuity={} → segment by sender/id only, no slow
    # margin OCR.)
    per_page_ent = {p: {"ids": page_recs[p]["ids"]} for p in page_recs}
    segments = seg.segment({}, per_page_ent, page_text)
    identified = [d for d in segments if d.get("identifier")]

    doc_entities: dict[str, object] = {}
    page2src: dict[int, str] = {}
    if len(identified) >= 2:
        for d in segments:
            rec_d, txt_d = _agg(d["pages"])
            label = d.get("label")
            label = label if label and label != "(unidentified)" else None
            sender, rec_d, rname, rrec = _sender_and_recipient(rec_d, d["pages"], txt_d, label)
            src = f"{key}#{d.get('identifier') or 'p' + '-'.join(map(str, d['pages']))}"
            de = ingest_document(g, r, source=src, sender=sender, entities_rec=rec_d,
                                 recipient_name=rname, recipient_rec=rrec,
                                 authority=_is_auth(sender), page_text=txt_d)
            doc_entities[src] = de
            for p in d["pages"]:
                page2src[p] = src
        n_docs = len(segments)
    else:
        rec_all, full_text = _agg(sorted(page_text))
        sender, rec_all, rname, rrec = _sender_and_recipient(rec_all, sorted(page_text), full_text)
        de = ingest_document(g, r, source=key, sender=sender or None, entities_rec=rec_all,
                             recipient_name=rname, recipient_rec=rrec,
                             authority=_is_auth(sender), page_text=full_text)
        doc_entities[key] = de
        for p in page_text:
            page2src[p] = key
        n_docs = 1

    # Out-of-column margin pass: continuity numbers / control keys printed outside
    # the body column are first-class CONFIRMATION, not footnotes. Attach control
    # keys + continuity markers to their page's document as geometry evidence.
    from semantic.geometry_columns import tag_out_of_column, is_substantive_marker
    from semantic.evidence import Evidence
    margin_markers: list[dict] = []
    for p, plines in _page_lines_from_model(doc).items():
        tag_out_of_column(plines)
        for ln in plines:
            side = ln.get("out_of_column")
            if not side:
                continue
            role = ln.get("margin_role")
            text = (ln.get("text") or "").strip()
            if not is_substantive_marker(text, role):
                continue          # drop single-char / scan-edge noise (LLM clarity)
            margin_markers.append({"page": p, "side": side, "role": role, "text": text[:80]})
            de = doc_entities.get(page2src.get(p))
            if de is not None and role in ("control_number", "continuity"):
                de.attach(Evidence(page2src.get(p) or key, f"margin_{role}",
                                   text, "geometry", confidence=0.85))

    # QR / barcode pass: codes are confirmation OUTSIDE the text layer. A
    # GiroCode/EPC QR independently gives the creditor (often the issuer the OCR
    # text omits), the IBAN and the payment reference; franking Data Matrix codes
    # are page-continuity markers. Best-effort — graceful if zxing-cpp is absent.
    from semantic.relation import RelationType as _RT
    from semantic.entity import EntityType as _ET
    qr_findings: list[dict] = []
    try:
        from . import qrscan
        if qrscan.tools_available()[0]:
            qr_findings = qrscan.scan_pdf(pdf, sc.blob_dir / "qr_pages", dpi=300)
    except Exception:
        qr_findings = []
    for f in qr_findings:
        p = f.get("page")
        de = doc_entities.get(page2src.get(p)) if p else None
        src = page2src.get(p) or key
        epc = f.get("epc")
        if epc:
            margin_markers.append({"page": p, "side": "qr", "role": "qr_payment",
                                   "text": (f"GiroCode creditor={epc['name']} "
                                            f"IBAN={epc['iban']} {epc['currency']}{epc['amount']} "
                                            f"ref={epc['remittance']}")[:120]})
            if de is not None:
                for prop, val in (("qr_creditor", epc["name"]), ("qr_iban", epc["iban"]),
                                  ("qr_amount", f"{epc['currency']} {epc['amount']}".strip()),
                                  ("qr_reference", epc["remittance"])):
                    if val:
                        de.attach(Evidence(src, prop, val, "qr", confidence=0.95))
                # The GiroCode creditor is the issuer the text layer often omits.
                if epc.get("name") and not g.relations_of(de.id, _RT.ISSUED_BY):
                    org = r.resolve(_ET.ORGANIZATION, keys=[("name", epc["name"])],
                                    evidence=[Evidence(src, "name", epc["name"], "qr", confidence=0.9)])
                    g.relate_once(de.id, _RT.ISSUED_BY, org.id, produced_by="qr", confidence=0.9)
                    acct = (r.find_existing_entity(_ET.BANK_ACCOUNT, [("iban", epc["iban"])])
                            if epc.get("iban") else None)
                    if acct is not None:        # the account named in the QR belongs to the creditor
                        g.relate_once(acct.id, _RT.BELONGS_TO, org.id, produced_by="qr", confidence=0.9)
        else:
            content = (f.get("content") or "").replace("\n", " ")[:60]
            margin_markers.append({"page": p, "side": "qr", "role": "barcode",
                                   "text": (f"{f['format']}: {content}" if content
                                            else f["format"])})

    # Scientific layer: the docmodel's structural tree + occurrence-bearing items
    # (formulas/tables/figures/citations) ingested through the composable layers
    # (ordering / content-identity / dual-positioned occurrences) onto the SAME
    # graph. Additive; runs alongside the commercial ingest above.
    from semantic.build import ingest_docmodel
    # Quantities + measurements (S4.2): when the model objects carry the
    # quantity/measurement pass layers (props['quant']/props['meas'] from
    # `pdfdrill enhance`), collect and pass them — the papers path; the
    # commercial invoice path above is untouched.
    _quant_records, _meas_records = [], []
    for _o in doc.objects.values():
        for _q in (_o.props.get("quant") or []):
            _quant_records.append({**_q, "obj_id": _o.id})
        for _m in (_o.props.get("meas") or []):
            _meas_records.append({**_m, "para_id": _o.id})
    sci_counts = ingest_docmodel(g, r, doc, key,
                                 quant_records=_quant_records,
                                 meas_records=_meas_records)
    sc.set_evidence("semantic_scientific", sci_counts)

    # The compiler gate: type-check + consistency over the graph.
    result = compiler.compile(g)

    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    graph_out = g.to_dict()
    graph_out["validity"] = result.validity
    graph_out["warnings"] = result.to_dict()["warnings"]
    blob = json.dumps(graph_out, ensure_ascii=False, indent=2)
    sem_path.write_text(blob, encoding="utf-8")
    if store_path:
        store_path.write_text(blob, encoding="utf-8")

    prev = ",".join(sorted(sc.facts - {SEMANTIC_BUILT})) or "INIT"
    sc.add_fact(SEMANTIC_BUILT)
    sc.set_evidence("semantic_entities", g.entity_count())
    sc.set_evidence("semantic_relations", len(g.relations))
    sc.set_evidence("semantic_validity", result.validity)
    sc.set_evidence("semantic_warnings", len(result.warnings))
    sc.set_evidence("margin_markers", margin_markers)
    sc.set_evidence("semantic_path", str(sem_path.relative_to(sc.pdf_path.parent)))
    sc.log_transition("semantic", prev, SEMANTIC_BUILT,
                      detail=f"{g.entity_count()} entities, {len(g.relations)} "
                             f"relations, {result.validity}")
    sc.save()

    # Implicit language detection (features layer; pure-Python fallback, no deps).
    from features.extract_language import language_of
    doc_lang = language_of("\n".join(page_text.get(p, "") for p in sorted(page_text)))
    sc.set_evidence("language", doc_lang)
    sc.save()

    # The consumer is an LLM: emit the whole graph structured + clean, no prose.
    from semantic.render import render_for_llm
    store_note = (f" · +{g.entity_count() - n_before} new this doc (store holds "
                  f"{g.entity_count()})" if store_path else "")
    return render_for_llm(g, bibkey=key, validity=result.validity,
                          warnings=result.warnings, markers=margin_markers,
                          json_name=sem_path.name, n_docs=n_docs, store_note=store_note,
                          language=doc_lang)


# ===========================================================================
# pdf-reading primitives (parity with the Claude.ai pdf-reading skill, but
# file-based: results land in the sidecar, not in an LLM context window).
# ===========================================================================

_BANK_RE = re.compile(r"\b(Bank|Sparkasse|Commerzbank|Volksbank|Raiffeisen|Postbank|Bankhaus)\b", re.I)


def _per_page_ocr_text(pdf: Path, sc: "Sidecar", lang: str = "deu+eng") -> dict[int, str]:
    """Per-PHYSICAL-page full OCR text, blank duplex backsides dropped. The
    ordered scorer + the mode detector need complete per-page text (the MathPix
    logical model fragments pages and collapses BoW cosine → over-segmentation)."""
    from . import ocr_lines, geometry
    ok, msg = ocr_lines.tools_available()
    if not ok:
        raise RuntimeError(msg)
    words, _ = ocr_lines._render_and_ocr(pdf, sc.blob_dir / "ordered_pages", 200, lang)
    by_page: dict[int, list] = {}
    for ln in geometry.group_lines(words):
        by_page.setdefault(ln["page"], []).append(ln["text"])
    return {p: "\n".join(v) for p, v in by_page.items()
            if len("\n".join(v).strip()) >= 25}


def _page_signature(text: str) -> Optional[str]:
    """A stable per-page document key for shuffle detection: an admin id value
    (Steuer-/Kassen-/Aktenzeichen) if present, else the sender/letterhead."""
    from . import segment as seg
    from features import extract_ids
    for f in extract_ids.extract(text or ""):
        if f.type in ("STEUERNUMMER", "KASSENZEICHEN", "AKTENZEICHEN"):
            return f"{f.type}:{f.value}"
    s = seg.sender_of(text or "")
    return s or None


def _run_ordered(pdf: Path, sc: "Sidecar", page_text: dict[int, str],
                 threshold: float, mode_note: str = "") -> str:
    from . import continuity_scorer as csr
    from . import segment as seg, qrscan
    from semantic.blocks import detect_recipient

    qr_by_page: dict[int, list] = {}
    try:
        if qrscan.tools_available()[0]:
            for f in qrscan.scan_pdf(pdf, sc.blob_dir / "qr_pages", dpi=300):
                qr_by_page.setdefault(f.get("page"), []).append(f)
    except Exception:
        pass

    pages = []
    for p in sorted(page_text):
        text = page_text[p]
        sender = seg.sender_of(text) or None
        if sender and _BANK_RE.search(sender):
            sender = None                       # the payee's bank, not the issuer
        recp = detect_recipient(text)
        tracking = epc_name = None
        for f in qr_by_page.get(p, []):
            if f.get("epc"):
                epc_name = f["epc"].get("name") or epc_name
            c = (f.get("content") or "")
            if c.isdigit() and len(c) >= 12 and (tracking is None or len(c) > len(tracking)):
                tracking = c
        sender = sender or epc_name
        pages.append(csr.PageFeatures(index=p, text=text, sender=sender,
                                      receiver=recp["name"] if recp else None,
                                      tracking_code=tracking))

    res = csr.segment(pages, threshold=threshold)
    sc.set_evidence("ordered_documents", res["documents"])
    sc.set_evidence("ordered_mailings", res["mailings"])
    sc.add_fact("ORDERED_BUILT")
    sc.save()

    lines = [f"ORDERED SEGMENTATION {resolve_bibkey(pdf, None, sc)} · "
             f"{res['n_pages_in']} pages → {res['n_documents']} document(s) in "
             f"{len(res['mailings'])} mailing(s) (threshold {threshold}).{mode_note}", ""]
    if res["mailings"]:
        lines.append("MAILINGS (hard outer grouping — Deutsche Post tracking codes)")
        for m, ps in sorted(res["mailings"].items()):
            lines.append(f"  {m}: pages {ps}")
        lines.append("")
    lines.append("DOCUMENTS")
    for d in res["documents"]:
        pv = d["provenance"]
        mail = f" [{d['mailing']}]" if d["mailing"] else ""
        lines.append(f"  doc{d['index']} pages {d['pages']}{mail} — {d['proposed_filename']}")
        lines.append(f"    publisher(sender)={pv['sender'] or '?'} · "
                     f"receiver={pv['receiver'] or '?'} · type={pv['doctype']} · date={pv['date'] or '?'}")
    lines.append("")
    lines.append("GAP DECISIONS (why each cut/keep — for the LLM)")
    for g in res["gaps"]:
        verdict = "CUT" if g["is_cut"] else "keep"
        why = g["reason"] or ", ".join(f"{s['name']}={s['evidence']}" for s in g["signals"])
        lines.append(f"  {g['gap']}: B={g['boundary_score']} → {verdict}"
                     + (" (hard)" if g["hard"] else "") + f"  [{why}]")
    return "\n".join(lines)


def cmd_ordered(pdf: Path, threshold: float = 0.5) -> str:
    """Segment an ORDERED page stack into documents (continuity_scorer).

    Score each adjacent-page GAP from page numbers / semantics / entities /
    letterhead / Deutsche Post tracking codes; cut where the boundary score
    crosses `--threshold`. Two-level: DataMatrix tracking codes give a HARD outer
    MAILING grouping, the soft signals refine letter-vs-enclosure inside. Each
    document carries commercial provenance (sender=publisher, receiver=audience),
    BibTeX-projectable. For a SHUFFLED bundle use `pdfdrill segment`, or let
    `pdfdrill autosegment` pick.
    """
    guard = _born_digital_scan_guard(pdf, "ordered")
    if guard:
        return guard
    sc = Sidecar(pdf)
    try:
        page_text = _per_page_ocr_text(pdf, sc)
    except RuntimeError as e:
        return f"`ordered` needs per-page OCR: {e}"
    return _run_ordered(pdf, sc, page_text, threshold)


def cmd_autosegment(pdf: Path, threshold: float = 0.5) -> str:
    """Auto-pick the segmenter: ORDERED stack → gap scorer; SHUFFLED bundle →
    signature grouping. Decides from whether each document's pages form a
    contiguous run (ordered) or interleave (shuffled), then runs the right one.
    """
    guard = _born_digital_scan_guard(pdf, "autosegment")
    if guard:
        return guard
    from . import continuity_scorer as csr

    sc = Sidecar(pdf)
    try:
        page_text = _per_page_ocr_text(pdf, sc)
    except RuntimeError as e:
        return f"`autosegment` needs per-page OCR: {e}"
    sigs = [_page_signature(page_text[p]) for p in sorted(page_text)]
    mode, reason, frac = csr.detect_acquisition_mode(sigs)
    head = (f"AUTOSEGMENT {pdf.name}: mode={mode} ({reason}, interleave={frac}) → "
            f"running `{'ordered' if mode == 'ordered' else 'segment'}`.\n")

    if mode == "ordered":
        return head + _run_ordered(pdf, sc, page_text, threshold,
                                   mode_note=f"  [auto: ordered, interleave={frac}]")
    # shuffled → delegate to the signature-grouping segmenter (model + entities)
    return head + cmd_segment(pdf)


def cmd_fontid(pdf: Path, pages: str | None = None, limit: int = 12,
               ppi: int = 200) -> str:
    """Identify the font VISUALLY for scanned/OCR input (the PDF has no font
    layer, so `fonts`/`fonts_layer` return nothing). Renders WORD crops, classifies
    each with the torch-free storia/font-classify ONNX model (Google-Fonts
    classes), and votes WITHIN each OCR block — so font is reported as a property
    of every text FIELD (heading vs body vs fine-print), not one document-level
    vote. HONEST: the model is reliable on distinctive faces but weak on scanned
    generic sans-serifs, and Arial/Helvetica/Computer-Modern aren't clean classes
    — so per-field confidence + agreement are reported and a low field is flagged
    as a weak hint, not a fact.
    """
    import subprocess
    import numpy as np
    from PIL import Image
    from . import font_classify as fc, geometry, pdf_reading

    ok, msg = fc.tools_available()
    if not ok:
        return msg
    sc = Sidecar(pdf)
    if not fc.available():
        return ("font-classify model unavailable offline — it fetches ~61 MB from "
                "HuggingFace on first use. Set $FONT_CLASSIFY_DIR or ensure network "
                "access to huggingface.co, then retry.")
    out_dir = sc.blob_dir / "fontid"
    n_pages = getattr(sc, "page_count", None) or None
    if not n_pages:
        try:
            info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True,
                                  text=True, timeout=30)
            m = re.search(r"Pages:\s*(\d+)", info.stdout)
            n_pages = int(m.group(1)) if m else None
        except Exception:
            n_pages = None
    page_list = pdf_reading.parse_pages(pages, n_pages)
    # Font is sampled, not exhaustive: cap to the first few pages when none asked
    # (so a 175-page scan doesn't rasterize all of it just to read a font), and
    # never ask for a page past the document (gs errors on an out-of-range page).
    if pages is None:
        page_list = (page_list or list(range(1, (n_pages or 3) + 1)))[:3]
    if n_pages:
        page_list = [p for p in page_list if 1 <= p <= n_pages]
    imgs = pdf_reading.rasterize(pdf, out_dir, pages=page_list, dpi=ppi)

    # WORD-level crops grouped per TEXT FIELD: a word's ~5:1 aspect fills the
    # classifier's square box (vs a full line's thin band), and font is a property
    # of each OCR block (heading vs body vs fine-print), NOT one document vote.
    classified: list[tuple[dict, tuple[str, float]]] = []
    n_words = 0
    for pno, img_path in zip(page_list, imgs):
        if n_words >= limit:
            break
        page_img = np.array(Image.open(img_path).convert("RGB"))
        res = subprocess.run(["tesseract", str(img_path), "-", "--psm", "1", "tsv"],
                             capture_output=True, text=True)
        words, _ = geometry.parse_tsv(res.stdout)
        cands = [w for w in words
                 if len(re.sub(r"[^A-Za-zÄÖÜäöüß]", "", w["text"])) >= 5
                 and (w["x1"] - w["x0"]) >= 40 and (w["y1"] - w["y0"]) >= 10]
        # within each OCR block keep the widest few words (most glyph signal),
        # so every field is sampled rather than spending the budget on one block.
        from collections import defaultdict
        by_block: dict[int, list] = defaultdict(list)
        for w in cands:
            by_block[w.get("block", 0)].append(w)
        for blk, bws in by_block.items():
            for w in sorted(bws, key=lambda w: -(w["x1"] - w["x0"]))[:4]:
                if n_words >= limit:
                    break
                y0, y1 = int(w["y0"]), int(w["y1"])
                x0, x1 = int(w["x0"]), int(w["x1"])
                pad = max(3, (y1 - y0) // 6)
                crop = page_img[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]
                pred = fc.classify_crop(crop, k=1)
                if pred:
                    classified.append(({**w, "page": pno}, pred[0]))
                    n_words += 1

    fields = fc.field_fonts(classified)
    if not fields:
        return f"No classifiable text fields found in {pdf.name}."
    from collections import Counter
    distinct = Counter(f["font"] for f in fields)
    cat_counts = Counter(f["category"] for f in fields if f["category"])
    sc.set_evidence("fontid", {"fields": fields,
                               "distinct": dict(distinct.most_common()),
                               "categories": dict(cat_counts.most_common())})
    sc.add_fact("FONTID_BUILT")
    sc.save()
    # also drop a human-readable report into .drill/fontid/ so `ls` shows a result
    report = fc.format_report(pdf.name, fields, n_words=len(classified))
    report_path = out_dir / "fontid.txt"
    report_path.write_text(report, encoding="utf-8")

    npages = len(set(f["page"] for f in fields))
    # The CATEGORY vote (sans-serif/serif/mono/…) is the robust signal: on an
    # out-of-class scanned face the exact Google-Fonts guess is noise, but its
    # top guesses are all the same CATEGORY. Lead with that; the face is a hint.
    if cat_counts:
        top_cat, tc = cat_counts.most_common(1)[0]
        catsumm = ", ".join(f"{c}×{n}" for c, n in cat_counts.most_common())
        verdict = f"predominantly {top_cat} ({tc}/{len(fields)} fields; {catsumm})"
    else:
        verdict = "category uncertain (faces out of the Google-Fonts class set)"
    out = [f"FONTID {pdf.name} (VISUAL estimate — no font layer; per text FIELD, "
           f"{len(fields)} fields over {npages} page(s)). Document is {verdict}.",
           "Per field the CATEGORY is the robust signal; the specific Google-Fonts "
           "face is a low-confidence guess (Arial/Helvetica/Computer-Modern aren't "
           "classes). ⚠ = even the category is uncertain:"]
    for f in fields:
        cat = f["category"] or "uncertain"
        weak = "" if (f["category"] and f["cat_agreement"] >= 0.5) else " ⚠"
        out.append(
            f"  p{f['page']} field {f['block']:>2} {f['sample']!r:46} → {cat} "
            f"({f['cat_votes']}/{f['cat_total']}); face≈{f['font']} "
            f"(conf {f['mean_conf']}){weak}")
    out.append(f"Report with statistics written to {report_path}")
    return "\n".join(out)


def cmd_spellqc(pdf: Path, lang: str | None = None) -> str:
    """Dictionary-assisted de-hyphenation QC over the transcluded text.

    For each `left-/right` line-break: join if the joined word is valid, keep if
    the hyphenated compound is valid, else REVIEW (neither is a word — likely an
    OCR error). Hunspell via spylls→enchant→.dic-set, loaded on demand for the
    document language (auto-detected); falls back to the soft-break heuristic when
    the dictionary is weak/absent (German affix-compounding). The `review` bucket
    is the QC value — fragments to fix rather than silently guess.
    """
    from docmodel.core import Document
    from . import spellqc

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."
    doc = load_model(model_path)
    page_text = _page_text_from_model(doc)
    if not lang:                          # resolve once so the dict label is accurate
        lang = sc.get_evidence("language")
    if not lang or lang == "und":
        from features.extract_language import language_of
        lang = language_of("\n".join(page_text.get(p, "") for p in sorted(page_text)))

    all_dec = []
    for p in sorted(page_text):
        _fixed, dec = spellqc.dehyphenate_text(page_text[p], lang)
        all_dec += dec
    if not all_dec:
        return (f"No line-break hyphenation found in {pdf.name} (the transcluded "
                f"text has no `word-`/`word` wraps — already clean, e.g. MathPix).")

    by = {"join": 0, "keep": 0, "review": 0}
    for d in all_dec:
        by[d.decision] += 1
    backend = spellqc.get_speller(lang).backend if lang and lang != "und" else "heuristic"
    sc.set_evidence("spellqc", by)
    sc.add_fact("SPELLQC_BUILT")
    sc.save()

    lines = [f"SPELLQC {pdf.name} (lang={lang or 'auto'}, dict={backend}): "
             f"{len(all_dec)} hyphen-break(s) — {by['join']} joined, "
             f"{by['keep']} kept (compounds), {by['review']} flagged for REVIEW."]
    reviews = [d for d in all_dec if d.decision == "review"]
    if reviews:
        lines.append("REVIEW (neither form is a word — likely OCR error, fix manually):")
        lines += [f"  {d.left}-{d.right}  → ?  [{d.reason}]" for d in reviews[:15]]
    joins = [d for d in all_dec if d.decision == "join"][:8]
    if joins:
        lines.append("Joined (de-hyphenated):")
        lines += [f"  {d.left}-{d.right} → {d.joined}  [{d.reason}]" for d in joins]
    return "\n".join(lines)


def cmd_qr(pdf: Path, dpi: int = 300, pages: str | None = None,
           formats: str | None = None) -> str:
    """Scan for QR codes & barcodes — confirmation data the text layer can't give.

    A GiroCode/EPC QR encodes the creditor name, IBAN, amount and payment
    reference (often the issuer the OCR text omits, and an independent check on
    the extracted IBAN/reference). Data Matrix franking/routing marks are
    captured too. Rasterizes with Ghostscript, decodes with zxing-cpp. Findings land
    in the sidecar (`qr_codes`).
    """
    from . import qrscan, pdf_reading

    ok, msg = qrscan.tools_available()
    if not ok:
        return msg
    sc = Sidecar(pdf)
    page_list = pdf_reading.parse_pages(pages, getattr(sc, "page_count", None) or None)
    out_dir = sc.blob_dir / "qr_pages"
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    try:
        findings = qrscan.scan_pdf(pdf, out_dir, dpi=dpi, pages=page_list, formats=formats)
    except Exception as e:
        return f"QR scan failed: {type(e).__name__}: {e}"

    sc.set_evidence("qr_codes", findings)
    prev = ",".join(sorted(sc.facts - {QR_KNOWN})) or "INIT"
    sc.add_fact(QR_KNOWN)
    n_epc = sum(1 for f in findings if f.get("epc"))
    sc.log_transition("qr", prev, QR_KNOWN, cost_ms=(time.monotonic() - t0) * 1000,
                      detail=f"{len(findings)} code(s), {n_epc} EPC/GiroCode")
    sc.save()
    if not findings:
        return (f"No QR/barcodes found in {pdf.name}"
                + (f" (pages {pages})" if page_list else "") + ".")
    lines = []
    for f in findings:
        loc = f"p{f['page']}"
        if f.get("epc"):
            e = f["epc"]
            lines.append(f"  {f['format']} {loc} — GiroCode/EPC SEPA: "
                         f"creditor='{e['name']}', IBAN={e['iban']}, "
                         f"{e['currency']} {e['amount']}, ref='{e['remittance']}'")
        else:
            c = (f.get("content") or "").replace("\n", "⏎")
            if not c and f.get("content_base64"):
                c = f"<binary {len(f['content_base64'])}b base64>"
            lines.append(f"  {f['format']} {loc} — {c[:90]}")
    return (f"{len(findings)} code(s) found ({n_epc} GiroCode/EPC payment QR). "
            f"These are confirmation data outside the text layer:\n" + "\n".join(lines))


def cmd_selftest(target: Path, full: bool = False) -> str:
    """Diagnostic grid: run the command battery across a PDF (or every PDF in a
    folder), capture OK/ERROR + the actual one-line result/error per command, and
    write a full log. So 'it failed' becomes a reproducible grid we can both read,
    instead of cherry-picked verification. `--full` adds the heavy OCR/model
    commands (entities/elements/semantic)."""
    import traceback as _tb

    tp = Path(target)
    pdfs = sorted(tp.glob("*.pdf")) if tp.is_dir() else [tp]
    pdfs = [p for p in pdfs if p.exists()]
    if not pdfs:
        return f"No PDF(s) at {target}."

    core = [
        ("doctor", lambda p: cmd_doctor()),
        ("size", cmd_size), ("pdfinfo", cmd_pdfinfo), ("fonts", cmd_fonts),
        ("links", cmd_links), ("dests", cmd_dests), ("images", cmd_images),
        ("md", cmd_md), ("rasterize", lambda p: cmd_rasterize(p, pages="1", dpi=100)),
        ("attachments", cmd_attachments), ("formfields", cmd_formfields),
        ("tables", lambda p: cmd_tables(p, pages="1")),
    ]
    heavy = [("entities", cmd_entities), ("elements", lambda p: cmd_elements(p)),
             ("semantic", lambda p: cmd_semantic(p))]
    battery = core + (heavy if full else [])

    results: dict[str, list[tuple]] = {}
    for pdf in pdfs:
        rows = []
        for label, fn in battery:
            try:
                out = (fn(pdf) or "").strip()
                first = out.splitlines()[0][:140] if out else "(empty output)"
                # heuristic 3rd state: ran but not-applicable / degraded
                low = first.lower()
                degraded = any(s in low for s in (
                    "no text layer", "scanned pdf", "no embedded", "no interactive",
                    "no tables", "no model", "not installed", "needs ", "appears blocked",
                    "no element source", "refusing", "(empty", "no commercial",
                    "0 word", "no raster", "no pages"))
                status = "skip" if degraded else "ok"
                rows.append((label, status, first))
            except Exception as e:
                rows.append((label, "ERROR", f"{type(e).__name__}: {e}".replace("\n", " ")[:140],
                             _tb.format_exc()))
        results[str(pdf)] = rows

    mark = {"ok": "✓", "skip": "⊘", "ERROR": "✗"}
    lines, log = [], []
    n_ok = n_skip = n_err = 0
    for pdf, rows in results.items():
        name = Path(pdf).name
        lines.append(f"\n### {name}")
        lines.append("| command | status | result / error (first line) |")
        lines.append("|---|:---:|---|")
        for row in rows:
            label, status, first = row[0], row[1], row[2]
            lines.append(f"| {label} | {mark[status]} | {first} |")
            log.append(f"[{name}] {label}: {status}\n    {first}")
            if status == "ok":
                n_ok += 1
            elif status == "skip":
                n_skip += 1
            else:
                n_err += 1
                if len(row) > 3:
                    log.append("    --- traceback ---\n" + row[3])

    # save full log
    out_dir = tp if tp.is_dir() else (Sidecar(pdfs[0]).blob_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "selftest.log"
    log_path.write_text("\n".join(log), encoding="utf-8")

    head = (f"pdfdrill selftest — {len(pdfs)} document(s) × {len(battery)} commands: "
            f"{n_ok} ✓ ran, {n_skip} ⊘ n/a-or-degraded, {n_err} ✗ ERROR. "
            f"Full log + tracebacks: {log_path}.  "
            f"(✓=returned a result, ⊘=ran but not-applicable/needs-a-tool, "
            f"✗=raised — see log.)" + ("  Pass --full for entities/elements/semantic."
                                       if not full else ""))
    return head + "\n" + "\n".join(lines)


def _write_offline_bundle(viewer: Path, title: str) -> str:
    """Add the server-free deep-zoom bundle (viewer_offline.html + vendored
    OpenSeadragon) to a built pyramid dir. Returns a prose fragment ('' when the
    writer is unavailable — degrade, never raise)."""
    import importlib.util
    ov = Path(__file__).resolve().parents[2] / "tools" / "imageserver" / "offline_viewer.py"
    if not ov.exists():
        return " (offline writer not found — tools/imageserver/offline_viewer.py)"
    try:
        spec = importlib.util.spec_from_file_location("offline_viewer", ov)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        dest = mod.write_offline_bundle(viewer, title=title)
        return (f" Offline bundle: {dest.name} (open via file:// — no server, "
                f"no network; copy the viewer/ folder to share).")
    except SystemExit as e:
        return f" (offline bundle not written: {e})"
    except Exception as e:                               # noqa: BLE001
        return f" (offline bundle failed: {e})"


def cmd_pyramid(pdf: Path, dpi: int = 600, force: bool = False,
                offline: bool = False) -> str:
    """Build a local 600-DPI Deep-Zoom (DZI) pyramid for the doc — the
    MathPix-free image source. Renders pages with Ghostscript (the gs-only
    rasterizer) and tiles them with pyvips into `<drill>/viewer/` (tiles/ +
    manifest.json + viewer.html). The pyramid then backs BOTH `pdfdrill
    imageserve` (the cdn.mathpix.com crop drop-in) and the deep-zoom viewer.
    Needs ghostscript + pyvips/libvips (`pip install 'pdfdrill[imageserver]'`).

    `--offline` additionally writes the SERVER-FREE bundle into viewer/
    (viewer_offline.html + vendored OpenSeadragon — opens via file://, no
    server, no network); on an already-built pyramid it just adds the bundle,
    no rebuild."""
    import shutil
    from . import pyramid as _pyr

    sc = Sidecar(pdf)
    viewer = sc.blob_dir / "viewer"
    ok, msg = _pyr.tools_available()
    if not ok:
        return f"Pyramid not built — {msg}"
    if (viewer / "manifest.json").exists() and not force:
        man = json.loads((viewer / "manifest.json").read_text(encoding="utf-8"))
        extra = _write_offline_bundle(viewer, pdf.stem) if offline else ""
        return (f"Pyramid already built: {len(man)} page(s) at "
                f"{viewer.relative_to(sc.pdf_path.parent)}/ (--force to rebuild). "
                f"Serve it with `pdfdrill imageserve {pdf.name}`.{extra}")
    try:
        res = _pyr.build_pyramid(pdf, viewer, dpi=dpi)
    except Exception as e:                                   # noqa: BLE001
        return f"Pyramid build failed: {e}"
    # copy the deep-zoom viewer into the doc's viewer/ so it is self-contained
    vh = Path(__file__).resolve().parents[2] / "tools" / "imageserver" / "viewer.html"
    if vh.exists():
        try:
            shutil.copy(vh, viewer / "viewer.html")
        except OSError:
            pass
    extra = _write_offline_bundle(viewer, pdf.stem) if offline else ""
    sc.set_evidence("pyramid", {"dpi": res["dpi"], "pages": res["pages"],
                                "tiles": str((viewer / "tiles").relative_to(sc.pdf_path.parent))})
    sc.save()
    return (f"Built a {res['dpi']}-DPI DZI pyramid: {res['pages']} page(s) → "
            f"{viewer.relative_to(sc.pdf_path.parent)}/ (tiles + manifest.json + "
            f"viewer.html). Serve the local cdn + deep-zoom viewer with "
            f"`pdfdrill imageserve {pdf.name}`.{extra}")


def _imageserve_argv(pdf: Path, sc: "Sidecar", port: int, dpi: int | None):
    """Build (argv, url, err) for the local image server over the doc's pyramid.
    `err` is set (argv None) when the pyramid or the server script is missing."""
    import sys as _sys
    viewer = sc.blob_dir / "viewer"
    if not (viewer / "manifest.json").exists():
        return None, "", (f"No pyramid for {pdf.name} — run `pdfdrill pyramid "
                          f"{pdf.name}` first to build the local 600-DPI tiles.")
    server = Path(__file__).resolve().parents[2] / "tools" / "imageserver" / "mathpix_server.py"
    if not server.exists():
        return None, "", "imageserver not found (tools/imageserver/mathpix_server.py)."
    pdpi = int(dpi or (sc.get_evidence("pyramid") or {}).get("dpi") or 600)
    argv = [_sys.executable, str(server), "--root", str(viewer),
            "--tiles", str(viewer / "tiles"), "--pyramid-dpi", str(pdpi),
            "--port", str(port)]
    lp = _lines_json_path(pdf)
    if lp.exists():                                          # exact MathPix→pyramid scale
        argv += ["--lines", str(lp)]
    return argv, f"http://localhost:{port}/viewer.html", ""


def cmd_imageserve(pdf: Path, port: int = 8000, dpi: int | None = None,
                   background: bool = False) -> str:
    """Serve the doc's local pyramid as a MathPix-free image source: a drop-in
    `cdn.mathpix.com` (`/cropped/<id>?top_left_x=…` assembled from the 600-DPI
    tiles) PLUS the deep-zoom viewer (`/viewer.html`). Needs `pdfdrill pyramid`
    first. Foreground (Ctrl-C to stop) unless `--background`. The bun drillui
    bridge spawns this and proxies /cropped,/tiles,/viewer.html to it."""
    import os, sys, subprocess, shutil
    sc = Sidecar(pdf)
    argv, url, err = _imageserve_argv(pdf, sc, port, dpi)
    if err:
        return err
    # ALREADY SERVING? The drillui bridge spawns an image server on this port on
    # demand, so a manual `imageserve` used to race into an "address already in
    # use" crash (a blocking foreground server also froze the REPL). If something
    # is already answering, just point at it — don't try to bind again.
    import socket as _socket
    try:
        with _socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return (f"Image server is already running → {url}  — open "
                    f"{url}/viewer.html to view the pyramid. (The drillui bridge "
                    f"manages one on demand; nothing to start. Use --port for a "
                    f"second one.)")
    except OSError:
        pass                                             # nothing there → start it
    # refresh the served viewer.html from the package so an OLD pyramid build never
    # serves a stale viewer (the deep-zoom UI is decoupled from the tiles)
    pkg_viewer = Path(__file__).resolve().parents[2] / "tools" / "imageserver" / "viewer.html"
    if pkg_viewer.exists():
        try:
            shutil.copy(pkg_viewer, sc.blob_dir / "viewer" / "viewer.html")
        except OSError:
            pass
    # A blocking foreground server only makes sense with a TTY (Ctrl-C to stop). A
    # non-interactive caller (the drillui REPL subprocess, a pipe) would FREEZE, so
    # background it automatically there.
    if not background:
        try:
            if not sys.stdin.isatty():
                background = True
        except (OSError, ValueError):
            background = True
    if background:
        # detached on purpose (meant to outlive this shell) → NO --die-with-parent
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return (f"Image server started in the background → {url}  (cdn drop-in: "
                f"/cropped/<id>?top_left_x=… from the local pyramid). Stop it with "
                f"`pkill -f 'mathpix_server.py.*--port {port}'`.")
    # Foreground: REPLACE this process with the server (os.execv) instead of running
    # it as a child. So Ctrl-C / SIGTERM reach the server DIRECTLY (clean shutdown,
    # port freed) and there is no wrapper child to orphan when the parent (a shell,
    # or the drillui bridge) dies. --die-with-parent is the belt-and-braces: the
    # server self-exits if it ever gets reparented to init (terminal closed / bridge
    # SIGKILLed) — which is exactly what used to leave orphans holding the port.
    print(f"Image server (cdn.mathpix.com drop-in + deep-zoom viewer) on the local "
          f"pyramid → {url}\n  /cropped/<id>?top_left_x=… serves a 600-DPI region; "
          f"Ctrl-C to stop.", flush=True)
    argv = argv + ["--die-with-parent"]
    os.execv(argv[0], argv)        # never returns; the server's own banner follows
    return ""                      # unreachable


def cmd_rasterize(pdf: Path, pages: str | None = None, dpi: int = 400,
                  fmt: str = "png", force: bool = False) -> str:
    """Rasterize page(s) to images for visual inspection (the skill's core op).

    Text extraction is blind to charts, diagrams, equations, multi-column layout
    and form structure; when those matter, render the page and *look* at it.
    Writes PNG/JPEG page images into the sidecar (`rasterize/`) via Ghostscript
    (the only rasterizer) and returns their paths so the driving LLM can Read
    them. `--pages N|N-M|1,3,5|all`, `--dpi 400` (the >=400 floor — best OCR/
    vision fidelity). A 400-DPI page is larger/more tokens than 150 but far more
    legible — rasterize only the pages that matter.
    """
    from . import pdf_reading

    sc = Sidecar(pdf)
    # page_count is 0 until `size` runs; coerce to None so parse_pages doesn't
    # clamp every requested page away (which would silently render ALL pages).
    page_list = pdf_reading.parse_pages(pages, getattr(sc, "page_count", None) or None)
    out_dir = sc.blob_dir / "rasterize"
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    if force and out_dir.exists():
        for p in out_dir.glob("page-*"):
            p.unlink()
    t0 = time.monotonic()
    try:
        imgs = pdf_reading.rasterize(pdf, out_dir, pages=page_list, dpi=dpi, fmt=fmt)
    except RuntimeError as e:
        return str(e)
    if not imgs:
        return f"No pages rasterized for {pdf.name}."

    rel = [str(p.relative_to(sc.pdf_path.parent)) for p in imgs]
    sc.set_evidence("rasterize_dir", str(out_dir.relative_to(sc.pdf_path.parent)))
    sc.set_evidence("rasterize_pages", len(imgs))
    sc.set_evidence("rasterize_dpi", dpi)
    prev = ",".join(sorted(sc.facts - {RASTERIZED})) or "INIT"
    sc.add_fact(RASTERIZED)
    sc.log_transition("rasterize", prev, RASTERIZED,
                      cost_ms=(time.monotonic() - t0) * 1000,
                      detail=f"{len(imgs)} page(s) @ {dpi} DPI")
    sc.save()
    spec = f"pages {pages}" if page_list else "all pages"
    body = "\n".join(f"  {r}" for r in rel)
    return (f"Rasterized {len(imgs)} page image(s) ({spec}, {dpi} DPI, {fmt}) → "
            f"{out_dir.name}/. Read these files to inspect the pages visually "
            f"(~1,600 tokens each at 150 DPI):\n" + body)


def cmd_attachments(pdf: Path, extract: bool = False) -> str:
    """List (and optionally extract) embedded file attachments.

    PDFs can carry embedded spreadsheets, data files, or whole documents
    (business reports, PDF portfolios, PDF/A-3). These are invisible to text
    extraction and to MathPix — like annotation-only links, a cheap dedicated
    probe surfaces them. `pdfdetach -list`; `--extract` saves all to the sidecar
    (`attachments/`). Falls back to pypdf's document-level attachments.
    """
    from . import pdf_reading

    sc = Sidecar(pdf)
    items, src = pdf_reading.list_attachments(pdf)
    saved: list[str] = []
    if extract and items:
        out_dir = sc.blob_dir / "attachments"
        sc.blob_dir.mkdir(parents=True, exist_ok=True)
        try:
            files = pdf_reading.extract_attachments(pdf, out_dir)
            saved = [str(p.relative_to(sc.pdf_path.parent)) for p in files]
        except RuntimeError as e:
            return str(e)

    sc.set_evidence("attachments", items)
    sc.set_evidence("attachments_source", src)
    prev = ",".join(sorted(sc.facts - {ATTACHMENTS_KNOWN})) or "INIT"
    sc.add_fact(ATTACHMENTS_KNOWN)
    sc.log_transition("attachments", prev, ATTACHMENTS_KNOWN,
                      detail=f"{len(items)} attachment(s) via {src}")
    sc.save()

    if not items:
        return (f"No embedded file attachments in {pdf.name} "
                f"(checked via {src}). Note: rich-media (3D/video) annotations "
                f"may not appear here.")
    lines = [f"  {it['index']}: {it['name']}" for it in items]
    head = (f"{len(items)} embedded file attachment(s) in {pdf.name} (via {src}):")
    tail = ""
    if extract:
        tail = ("\nExtracted to:\n" + "\n".join(f"  {s}" for s in saved))
    elif items:
        tail = "\nRun with --extract to save them to the sidecar."
    return head + "\n" + "\n".join(lines) + tail


def cmd_formfields(pdf: Path) -> str:
    """Read interactive (AcroForm) form-field values programmatically.

    Government forms, applications and contracts carry fillable fields whose
    values can be read without rasterizing. pypdf `get_fields()` covers text
    inputs, checkboxes, radio buttons and dropdowns (name / value / type /
    options). Persisted to the sidecar.
    """
    from . import pdf_reading

    sc = Sidecar(pdf)
    fields, err = pdf_reading.read_form_fields(pdf)
    if err:
        return f"pdfdrill formfields: {err}"

    sc.set_evidence("form_fields", fields)
    prev = ",".join(sorted(sc.facts - {FORMFIELDS_KNOWN})) or "INIT"
    sc.add_fact(FORMFIELDS_KNOWN)
    sc.log_transition("formfields", prev, FORMFIELDS_KNOWN,
                      detail=f"{len(fields)} field(s)")
    sc.save()

    if not fields:
        return (f"No interactive form fields in {pdf.name} (no AcroForm). "
                f"If it's a flat/scanned form, rasterize the page and read it "
                f"visually instead.")
    by_type: dict[str, int] = {}
    lines = []
    for f in fields:
        by_type[f["type"]] = by_type.get(f["type"], 0) + 1
        opt = f" options={f['options']}" if f["options"] else ""
        lines.append(f"  {f['name']}: {f['value']!r} ({f['type']}){opt}")
    summary = ", ".join(f"{n} {t}" for t, n in sorted(by_type.items()))
    return (f"{len(fields)} form field(s) in {pdf.name} ({summary}):\n"
            + "\n".join(lines))


def cmd_extractimages(pdf: Path, pages: str | None = None,
                      original_format: bool = False, force: bool = False) -> str:
    """Extract embedded raster image BYTES to files (`pdfimages`).

    Complements `images`/`embedimages` (which carry only metadata): this writes
    the actual PNGs so the driving LLM can Read them. Tiny/empty images (masks /
    transparency / decorative layers) are filtered by size. Gotcha: vector charts
    (matplotlib/Excel/R) are page operators, not image objects — they will NOT
    appear; rasterize the page instead.
    """
    from . import pdf_reading

    sc = Sidecar(pdf)
    # page_count is 0 until `size` runs; coerce to None so parse_pages doesn't
    # clamp every requested page away (which would silently render ALL pages).
    page_list = pdf_reading.parse_pages(pages, getattr(sc, "page_count", None) or None)
    out_dir = sc.blob_dir / "images_extracted"
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    if force and out_dir.exists():
        for p in out_dir.glob("img*"):
            p.unlink()
    t0 = time.monotonic()
    try:
        files = pdf_reading.extract_images(pdf, out_dir, pages=page_list,
                                           original_format=original_format)
    except RuntimeError as e:
        return str(e)
    kept, dropped = pdf_reading.filter_real_images(files)

    rel = [str(p.relative_to(sc.pdf_path.parent)) for p in kept]
    sc.set_evidence("images_extracted_dir",
                    str(out_dir.relative_to(sc.pdf_path.parent)))
    sc.set_evidence("images_extracted", len(kept))
    prev = ",".join(sorted(sc.facts - {IMAGES_EXTRACTED})) or "INIT"
    sc.add_fact(IMAGES_EXTRACTED)
    sc.log_transition("extractimages", prev, IMAGES_EXTRACTED,
                      cost_ms=(time.monotonic() - t0) * 1000,
                      detail=f"{len(kept)} kept, {dropped} filtered")
    sc.save()
    if not kept:
        return (f"No raster images extracted from {pdf.name} "
                f"({dropped} tiny/empty filtered). Vector charts won't appear "
                f"here — rasterize the page with `pdfdrill rasterize`.")
    note = f" ({dropped} tiny/empty filtered)" if dropped else ""
    body = "\n".join(f"  {r}" for r in rel)
    return (f"Extracted {len(kept)} raster image(s){note} → {out_dir.name}/. "
            f"Read them to view the figures (vector charts excluded — use "
            f"`rasterize` for those):\n" + body)


def _prose_table(t: dict) -> bool:
    """True if a pdfplumber 'table' is really two-column body PROSE mis-detected
    as a table — its cells are long sentence fragments, not tabular values. On a
    born-digital two-column paper the text strategy splits the columns into fake
    cells; a real data table has short cells (numbers, labels)."""
    cells = t.get("cells") or []
    texts = [(c.get("text") or "").strip() for c in cells]
    texts = [x for x in texts if x]
    if len(texts) < 3:
        return False
    prosey = sum(1 for x in texts if len(x.split()) >= 6)
    return prosey >= 0.5 * len(texts)


def _latex_table_rows(latex: str) -> list[list[str]]:
    """Best-effort tabular → rows of cell text (split on `\\\\`, cells on `&`,
    strip rules + font/command wrappers). Good enough for a QA view of a gold
    table; `pdfdrill svg` renders it faithfully."""
    import re
    m = re.search(r"\\begin\{(?:tabular\*?|tabularx|array)\}\s*(?:\[[^\]]*\])?\s*"
                  r"\{[^}]*\}(.*?)\\end\{(?:tabular\*?|tabularx|array)\}", latex, re.S)
    body = m.group(1) if m else latex
    # drop booktabs/plain rules and spacing commands
    body = re.sub(r"\\(?:top|mid|bottom)rule|\\hline|\\cmidrule(?:\([^)]*\))?"
                  r"(?:\[[^\]]*\])?\{[^}]*\}|\\addlinespace(?:\[[^\]]*\])?", " ", body)

    def _cell(c: str) -> str:
        c = re.sub(r"\\multicolumn\{\d+\}\{[^}]*\}\{(.*?)\}", r"\1", c)
        c = re.sub(r"\\multirow\{[^}]*\}\{[^}]*\}\{(.*?)\}", r"\1", c)
        c = re.sub(r"\\text(?:bf|it|tt|rm|sf)\{(.*?)\}", r"\1", c)
        c = re.sub(r"\\[a-zA-Z]+\*?", "", c)          # remaining commands
        return c.replace("{", "").replace("}", "").replace("\\&", "&").strip()

    rows: list[list[str]] = []
    for raw in re.split(r"\\\\", body):
        if not raw.strip():
            continue
        cells = [_cell(c) for c in raw.split("&")]
        if any(cells):
            rows.append(cells)
    return rows


def _gold_table_dicts(doc) -> list[dict]:
    """The model's REAL Table objects rendered into the pdf_reading table shape, so
    `tables_to_html`/`_markdown` render THEM — the paper's actual tables — instead
    of pdfplumber's two-column-prose garbage. Handles both sources: MathPix/span-
    aware `cells` are used directly; a gold-LaTeX `latex_code` table is parsed into
    cells."""
    out: list[dict] = []
    tabs = sorted(doc.objects_of_type("Table"),
                  key=lambda o: float(o.props.get("flow_index") or 0))
    for o in tabs:
        p = o.props
        caption = p.get("caption") or p.get("refnum") or ""
        cells = p.get("cells")
        if cells:                                    # MathPix / span-aware: use as-is
            n_cols = p.get("n_cols") or (max((c.get("col", 0) + c.get("col_span", 1)
                                              for c in cells), default=0))
            out.append({
                "page": p.get("page"), "index": len(out), "rows": p.get("rows") or [],
                "n_rows": p.get("n_rows") or 0, "n_cols": n_cols, "cells": cells,
                "columns": p.get("columns") or [], "header_rows": p.get("header_rows", 1),
                "strategy": "model", "caption": caption})
            continue
        latex = p.get("latex_code") or p.get("latex_original")
        if not latex:
            continue
        rows = _latex_table_rows(latex)
        if not rows:
            continue
        n_cols = max(len(r) for r in rows)
        built = [{"row": r, "col": c, "row_span": 1, "col_span": 1, "text": val}
                 for r, row in enumerate(rows) for c, val in enumerate(row) if val]
        out.append({
            "page": p.get("page"), "index": len(out),
            "rows": rows, "n_rows": len(rows), "n_cols": n_cols,
            "cells": built, "columns": rows[0] if rows else [],
            "header_rows": 1, "strategy": "latex-gold", "caption": caption})
    return out


def cmd_tables(pdf: Path, pages: str | None = None) -> str:
    """Tables from the model's gold LaTeX (if built) + keyless pdfplumber.

    On a born-digital paper whose model carries gold LaTeX tables (arXiv source),
    those are the AUTHORITATIVE tables. pdfplumber is the keyless fallback — but on
    a two-column page it mis-reads the columns of body prose as a table, so those
    prose-as-table results are dropped. Writes `tables.json`/`.md`/`.html`.
    """
    from . import pdf_reading

    sc = Sidecar(pdf)
    # page_count is 0 until `size` runs; coerce to None so parse_pages doesn't
    # clamp every requested page away (which would silently render ALL pages).
    page_list = pdf_reading.parse_pages(pages, getattr(sc, "page_count", None) or None)
    t0 = time.monotonic()
    tables, err = pdf_reading.extract_tables(pdf, pages=page_list)
    note = None
    if err and err.startswith("skipped"):     # informational, not an error
        note, err = err, None

    # Drop the two-column-prose-as-table garbage pdfplumber produces on a
    # multi-column paper (long sentence-fragment cells, not tabular values).
    n_raw = len(tables)
    tables = [t for t in tables if not _prose_table(t)]
    dropped = n_raw - len(tables)

    # Prefer the model's GOLD LaTeX tables (arXiv source) — the paper's real
    # tables — rendered ahead of any surviving pdfplumber tables.
    gold: list[dict] = []
    model_path = _model_path(sc)
    if model_path.exists():
        try:
            from .model_io import load_model
            gold = _gold_table_dicts(load_model(model_path))
        except Exception:                      # best-effort; pdfplumber stands alone
            gold = []
    # Gold model tables are authoritative — when present, they ARE the paper's
    # tables, so pdfplumber's keyless guesses are suppressed entirely (they only
    # add noise/duplicates). pdfplumber is used only when the model has none.
    all_tables = gold if gold else tables

    if err and not all_tables:
        return f"pdfdrill tables: {err}"

    out_dir = sc.blob_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "tables.json").write_text(
        json.dumps(all_tables, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "tables.md").write_text(
        pdf_reading.tables_to_markdown(all_tables), encoding="utf-8")
    # The QA projection: real <table>s with rowspan/colspan (a spanned header
    # renders as the range it covers, not as '' placeholders).
    (out_dir / "tables.html").write_text(
        pdf_reading.tables_to_html(all_tables), encoding="utf-8")

    sc.set_evidence("tables_count", len(all_tables))
    sc.set_evidence("tables_gold", len(gold))
    sc.set_evidence("tables_path", str((out_dir / "tables.json")
                                       .relative_to(sc.pdf_path.parent)))
    prev = ",".join(sorted(sc.facts - {TABLES_KNOWN})) or "INIT"
    sc.add_fact(TABLES_KNOWN)
    sc.log_transition("tables", prev, TABLES_KNOWN,
                      cost_ms=(time.monotonic() - t0) * 1000,
                      detail=f"{len(gold)} gold + {len(tables)} pdfplumber")
    sc.save()
    drop_note = (f" Dropped {dropped} two-column-prose false table(s)."
                 if dropped else "")
    if not all_tables:
        return (f"No tables found in {pdf.name}"
                + (f" (pages {pages})" if page_list else "")
                + (f" ({note})" if note else "") + "." + drop_note
                + " If a table is present but garbled, rasterize the page.")
    if gold:
        src = (f"{len(gold)} table(s) from the model's real tables "
               f"(pdfplumber's {len(tables)} keyless guess(es) suppressed as noise)")
        extra = (" These are the paper's actual tables; run `pdfdrill svg` to "
                 "render the gold LaTeX exactly.")
    else:
        src = f"{len(tables)} pdfplumber table(s)"
        extra = ""
    preview = pdf_reading.tables_to_markdown(all_tables[:2])
    html_ref = _artref(sc, out_dir / "tables.html")
    return (f"Extracted {src} → {html_ref} (+ tables.json/.md; open the html "
            f"for QA)." + extra
            + drop_note + (f" Note: {note}." if note else "") + "\n\nPreview:\n\n"
            + preview)


def _build_arxiv_source_model(pdf: Path, sc: "Sidecar", key: str,
                              model_path: Path) -> "str | None":
    """For an arXiv doc, build the model from the FREE LaTeX e-print
    (`build_source_model`) — fast and gold — instead of keyless tesseract OCR.
    Returns the formatted result on success, None to fall through to OCR."""
    aid = _arxiv_id_for(pdf, sc)
    if not aid:
        return None
    try:
        import tarfile as _tarfile
        from . import sources, latex_source as ls, model_io
        src = sources.download_arxiv_source(aid, pdf.parent)
        if not (src and Path(src).exists()):
            return None
        # Extract the e-print to <drill>/texsrc/ and build from the main .tex, so
        # the source (incl. biblio.bib/.bbl or an inline thebibliography) PERSISTS
        # for bibsource/bibliography — not a temp dir that vanishes.
        build_target = str(src)
        source_dir = None
        if _tarfile.is_tarfile(str(src)):
            texsrc = sc.blob_dir / "texsrc"
            texsrc.mkdir(parents=True, exist_ok=True)
            with _tarfile.open(str(src)) as tf:
                tf.extractall(texsrc, filter="data")
            source_dir = str(texsrc)
            # arXiv's 00README.json names the toplevel .tex authoritatively (the
            # main file can have ANY name); use it first. Else find_main_tex
            # inspects CONTENT for \documentclass — pass the REAL text, not "" (empty
            # content made it pick the alphabetically-first file, e.g. Conclusion.tex,
            # truncating multi-file \input papers).
            main = ls.main_tex_from_readme(str(texsrc))
            if not main:
                paths = {}
                for p in texsrc.rglob("*.tex"):
                    try:
                        paths[str(p)] = p.read_text(errors="replace")
                    except Exception:
                        paths[str(p)] = ""
                main = ls.find_main_tex(paths)
            if main:
                build_target = main
        doc = ls.build_source_model(build_target, bibkey=key)
        if source_dir:
            doc.meta["latex_source_dir"] = source_dir
    except Exception:
        return None
    objs = list(doc.objects.values())
    if not objs:
        return None
    model_io.save_model(model_path, doc)
    by_type: dict[str, int] = {}
    for o in objs:
        by_type[o.type] = by_type.get(o.type, 0) + 1
    sc.set_evidence("bibkey", key)
    sc.set_evidence("model_path", str(model_path.relative_to(sc.pdf_path.parent)))
    sc.set_evidence("model_object_counts", by_type)
    sc.set_evidence("model_equations_with_cdn", 0)
    sc.set_evidence("model_source", "latex")
    prev = ",".join(sorted(sc.facts - {MODEL_BUILT})) or "INIT"
    # Proof: this model was built from the arXiv LaTeX source (not lines.json).
    # Hash the source dir's main.tex when findable; provenance records the lane
    # (Phase B — content-hash staleness over the source build is a refinement).
    src_inputs = [Path(source_dir) / "main.tex"] if source_dir else []
    sc.mark(MODEL_BUILT, produced_by="model", inputs=src_inputs,
            params={"bibkey": key}, provenance="latex-source")
    sc.log_transition("model", prev, MODEL_BUILT,
                      detail=f"{len(objs)} objects from arXiv LaTeX source")
    sc.save()
    return _format_model(sc) + ("\n(Built from the free arXiv LaTeX source — "
                                "fast + gold, no OCR. `mathpix --force` for the "
                                "paid OCR/CDN route.)")


def cmd_model(pdf: Path, force: bool = False, bibkey: str | None = None) -> str:
    """Build the unified docmodel Document from MathPix lines.json.

    Auto-chains `mathpix` if the lines.json isn't there yet. Writes the
    serialized Document to <pdf>.drill/model.docmodel.json and records counts
    (objects, equations, equations carrying a CDN image) in the sidecar.

    `bibkey` sets the tiddler-prefix / object namespace (e.g. `kolbe2018hubbard`)
    used by `tiddlers`/`report`/`compare`; it is persisted in the sidecar so
    later commands reuse it without re-passing `--bibkey`. Defaults to the
    filename stem (preserving clean arXiv ids like `2004.05631v1`).
    """
    from docmodel.main import run as build_model, DEFAULT_CONFIG_PATH

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    key = resolve_bibkey(pdf, bibkey, sc)
    lines_path = _lines_json_path(pdf)
    # A new explicit --bibkey forces a rebuild so titles/meta pick it up.
    if bibkey and key != sc.get_evidence("bibkey"):
        force = True
    # Auto-rebuild if the lines.json is NEWER than the model — e.g. MathPix
    # replaced an earlier tesseract OCR. Otherwise a stale, garbled model would
    # shadow the better OCR (the AOK 'Kürten'→'Kirten' bug).
    stale = (lines_path.exists() and model_path.exists()
             and lines_path.stat().st_mtime > model_path.stat().st_mtime)
    # Self-heal the source→mathpix ordering trap: on arXiv, `add` builds a
    # geometry-less LaTeX-SOURCE model (fast, gold math) when no lines.json exists
    # yet. If the user then runs `mathpix` (creating a lines.json WITH page
    # geometry), the model must upgrade to it — else `inspect`/`locate` stay
    # box-less on a source model even though a geometry-bearing lines.json is right
    # there. So: a present lines.json + a current model that reports no geometry
    # ⇒ rebuild. (No lines.json ⇒ this never fires; the source model is kept.)
    if lines_path.exists() and model_path.exists() and not stale:
        caps = sc.get_evidence("model_caps") or {}
        if caps.get("geometry") is False:
            stale = True
    if sc.has(MODEL_BUILT) and model_path.exists() and not force and not stale:
        return _format_model(sc)

    if not lines_path.exists():
        # 1) MathPix if a key is present (best: page geometry + LaTeX + CDN crops).
        #    Skips for arXiv unless --force; a no-key / blocked host just returns
        #    without a lines.json, so we fall through to the free routes below.
        try:
            cmd_mathpix(pdf)
        except (Exception, SystemExit):     # missing creds raise SystemExit — must
            pass                            # still fall through to the free routes
        sc = Sidecar(pdf)
        if not lines_path.exists():
            # 2) BORN-DIGITAL default (the no-OCR route): read the PDF's OWN text
            #    stream with pdfplumber (chars → lines.json WITH page geometry) —
            #    free, fast, no key. This is what `route` promises and what lets
            #    inspect/locate work without MathPix. The arXiv gold LaTeX math is a
            #    `latex` OVERLAY on top, NOT the base — the source model has no page
            #    geometry, so it can never be boxed (the 'inspect box-less' report).
            if not _write_born_digital_lines(pdf):
                # 3) No text layer → a genuine SCAN. arXiv gold e-print if cached
                #    (content, no geometry), else tesseract OCR.
                built = _build_arxiv_source_model(pdf, sc, key, model_path)
                if built:
                    return built
                from .ocr_lines import tools_available
                if tools_available()[0]:
                    cmd_ocr(pdf)
            sc = Sidecar(pdf)
    if not lines_path.exists():
        return (f"No lines.json for {pdf.name}: it has no born-digital text layer "
                f"(a scan), MathPix is unavailable (no creds / blocked host), and "
                f"tesseract OCR is not installed. Provide a lines.json, set MathPix "
                f"creds, or install ghostscript + tesseract-ocr and run "
                f"`pdfdrill ocr {pdf.name}`.")

    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    out = build_model(
        lines_path=str(lines_path),
        config_path=DEFAULT_CONFIG_PATH,
        bibkey=key,
        out_path=str(model_path),
        debug_modules=[],
    )
    sc.set_evidence("bibkey", key)

    # Auto-strip MathPix HEADING RESIDUALS + lift footnotes at build time, so no
    # Paragraph carries a leaked `\section*{}` (which overflowed the inspect box,
    # duplicated the Section, and never reached llmtext). Idempotent + offline; a
    # source model (headings already blanked) is a no-op. Materialization stays
    # projection-time (`pdfdrill clean`).
    try:
        from docmodel.core import Document as _Doc
        from . import heading_cleanup as _hc
        _doc = _Doc.from_dict(out)
        if _hc.clean_heading_residuals(_doc) + _hc.extract_footnote_paragraphs(_doc):
            save_model(model_path, _doc)
            out = _doc.to_dict()
    except Exception:                                  # cleanup is best-effort
        pass

    objects = out.get("objects", [])
    by_type: dict[str, int] = {}
    for o in objects:
        by_type[o["type"]] = by_type.get(o["type"], 0) + 1
    eq_with_cdn = sum(
        1 for o in objects
        if o["type"] == "Equation" and o.get("props", {}).get("cdn_url")
    )
    lines_source = _lines_json_source(lines_path) or "mathpix"

    sc.set_evidence("model_path", str(model_path.relative_to(sc.pdf_path.parent)))
    sc.set_evidence("model_object_counts", by_type)
    sc.set_evidence("model_equations_with_cdn", eq_with_cdn)
    sc.set_evidence("model_source", lines_source)
    # CAPABILITIES, not just MODEL_BUILT: `model` yields incompatible SPECIES —
    # geometry (page boxes) for `inspect`/`locate`, math (typed equations) for
    # `report`/`compare`. Record what THIS species can support so commands +
    # `status` can be honest instead of trusting the single MODEL_BUILT fact.
    has_geometry = bool((out.get("meta") or {}).get("pages"))
    has_math = by_type.get("Equation", 0) > 0 or by_type.get("Formula", 0) > 0
    sc.set_evidence("model_caps", {"geometry": has_geometry, "math": has_math,
                                   "source": lines_source})
    prev = ",".join(sorted(sc.facts - {MODEL_BUILT})) or "INIT"
    # Record a proof object (content-hash of the lines.json this model was built
    # from + the bibkey) alongside the fact — so validity is later decidable by
    # re-hashing instead of trusting mtime (Phase B, the mtime-trigger fix).
    sc.mark(MODEL_BUILT, produced_by="model", inputs=[lines_path],
            params={"bibkey": key}, provenance=lines_source)
    sc.log_transition(
        "model", prev, MODEL_BUILT, cost_ms=(time.monotonic() - t0) * 1000,
        detail=f"{len(objects)} objects, {eq_with_cdn} eq w/ cdn",
    )
    sc.save()

    # AUTO-MERGE — pdfdrill's whole purpose is to extract AND merge sources. When
    # the model was built from the born-digital pdfminer text stream (page
    # geometry) and the doc is arXiv, OVERLAY the e-print's gold LaTeX (equations +
    # TikZ/tables) so the DEFAULT model carries BOTH: geometry (pdfminer) AND gold
    # math (LaTeX) — not one or the other. Runs AFTER MODEL_BUILT is set so the
    # nested cmd_latex won't recurse into cmd_model. Downloads the e-print once
    # (cached); graceful when the source is blocked/absent; non-arXiv is a no-op.
    if (lines_source in ("pdfminer-chars", "pdfplumber-chars")
            and _arxiv_id_for(pdf, sc) and not sc.has(LATEX_INGESTED)):
        try:
            cmd_injectlatex(pdf)                    # overlay gold equations + graphics
            # AND merge the gold LaTeX PROSE onto the born-digital paragraphs — the
            # char-layer prose is garbled by two-column interleaving + the arXiv
            # margin watermark; the gold text replaces it (LaTeX-wins, original
            # saved as text_source), so the model's prose is clean by default. This
            # is "extract AND merge several sources" automatically. Best-effort.
            try:
                cmd_merge(pdf)
            except (Exception, SystemExit):
                pass
            sc = Sidecar(pdf)
            with open(model_path, "r", encoding="utf-8") as _f:
                out = json.load(_f)                 # reload the MERGED model
            objects = out.get("objects", [])
            by_type = {}
            for o in objects:
                by_type[o["type"]] = by_type.get(o["type"], 0) + 1
            has_math = by_type.get("Equation", 0) > 0 or by_type.get("Formula", 0) > 0
            sc.set_evidence("model_object_counts", by_type)
            sc.set_evidence("model_caps", {"geometry": has_geometry, "math": has_math,
                                           "source": lines_source, "merged": "latex"})
            sc.save()
        except (Exception, SystemExit):             # source blocked/absent → pdfminer only
            pass

    # MATH-BEARING GATE: a keyless build that captured NO USABLE MATH on a doc that
    # clearly carries math is a FAILURE, not a result. Don't present it as complete
    # — flag NEEDS_VISION_OCR and instruct the keyless delegation route
    # (visionocr). The MathPix path and non-math docs are untouched.
    #
    # It keys on MISSING LaTeX, not on "0 Equations": the enriched tesseract module
    # DOES emit equation lines (correct region, GARBLED text — it cannot read math),
    # and an Equation's `latex` prop is then just that OCR text
    # ("Ih=glly <7 =3k € = < | =] (4)"). A count- or empty-latex-based gate is
    # satisfied by that garbage and silently passes a broken math doc.
    if (not _has_usable_math(objects, _lines_json_source(lines_path))
            and _is_keyless_textonly_source(_lines_json_source(lines_path))):
        from . import mathqc, llm_delegate as _D
        bearing, reason = mathqc.is_math_bearing(pdf, sc)
        if bearing:
            sc.add_fact(NEEDS_VISION_OCR)
            sc.save()
            n_para = by_type.get("Paragraph", 0)
            n_eq = by_type.get("Equation", 0)
            src = _lines_json_source(lines_path)
            how = ("the born-digital text layer (pdfminer.six)"
                   if src in ("pdfminer-chars", "pdfplumber-chars") else "tesseract OCR")
            # Be precise about WHY it failed: 0 equations, or equations whose
            # "LaTeX" is really the route's garbled OCR/plain text.
            got = (f"{n_para} Paragraph and 0 Equation" if not n_eq else
                   f"{n_para} Paragraph and {n_eq} Equation region(s) whose LaTeX "
                   f"is just this route's TEXT (garbled math), not real LaTeX")
            base = (f"{pdf.name} is math-bearing ({reason}) but was built from "
                    f"{how} with no MathPix key — that route captures prose, not "
                    f"typed equations, so this model has {got}. ")
            rt = _D.detect_runtime()
            if rt is _D.Runtime.NONE:
                return base + (
                    "WARNING: the mathematics was NOT captured. With a Claude "
                    "agent (Claude Code / the Claude.ai sandbox) run `pdfdrill "
                    f"visionocr {pdf.name}` to read each page and supply equation "
                    "LaTeX (keyless); with an OpenAI/MathPix key use `pdfdrill "
                    "mathpix`. A 0-equation model on a math doc is a failure "
                    "signal, not a result.")
            return base + (
                f"Run `pdfdrill visionocr {pdf.name}` to read each rendered page "
                f"and supply equation LaTeX — keyless, delegated to YOU the agent; "
                f"it folds them into the lines.json as real Equation nodes and "
                f"rebuilds. (Alternatively `pdfdrill remath {pdf.name}` rebuilds "
                f"each whole page as MathPix-Markdown.)")

    # "If LaTeX is available it must be used": when the arXiv e-print source is
    # cached (texsrc/), overlay its \appendix onto the model's sections so the
    # TOC/fractal index letters the appendix (A, B, …) even on a MathPix model.
    n_app = _overlay_appendix_from_source(sc, model_path)
    base = _format_model(sc)
    if n_app:
        base += (f" {n_app} section(s) flagged as appendix (from the LaTeX "
                 f"\\appendix in the e-print source).")
    return base


def _overlay_appendix_from_source(sc: "Sidecar", model_path: Path) -> int:
    """Mark model Section objects at/after the source `\\appendix` (idempotent).
    No-op when no cached `texsrc/` source or no `\\appendix` is present."""
    src_dir = sc.blob_dir / "texsrc"
    if not src_dir.is_dir():
        return 0
    from . import latex_source as ls, model_io
    try:
        doc = model_io.load_model(model_path)
        n = ls.mark_appendix_from_source(doc, str(src_dir))
    except Exception:
        return 0
    if n:
        model_io.save_model(model_path, doc)
        sc.set_evidence("appendix_sections", n)
        sc.save()
    return n


def _format_model(sc: Sidecar) -> str:
    counts = sc.get_evidence("model_object_counts", {}) or {}
    eq_cdn = sc.get_evidence("model_equations_with_cdn", 0)
    source = sc.get_evidence("model_source", "mathpix")
    total = sum(counts.values())
    top = ", ".join(f"{n} {t}" for t, n in sorted(
        counts.items(), key=lambda kv: -kv[1]) if t in (
        "Equation", "Formula", "Paragraph", "Section", "Table", "Picture"))
    key = sc.get_evidence("bibkey") or ""
    # Source-aware image line: MathPix regions are CDN pixel crops; a pdfminer
    # (DRILLPDFse) model locates equations in OUR coordinate system (PDF points)
    # and crops them from OUR local pyramid — never a MathPix CDN claim.
    if source == "mathpix":
        img_line = f"{eq_cdn} equations carry a MathPix CDN image. "
        nxt = "Next: pdfdrill compare <pdf> → LaTeX | KaTeX | image table."
    elif eq_cdn:
        img_line = (f"{eq_cdn} equations are located in OUR coordinate system "
                    f"(PDF points, source={source!r}); high-res crops come from "
                    f"the local pyramid. ")
        nxt = "Next: pdfdrill pyramid <pdf> → build the deep-zoom images, then compare/inspect."
    else:
        img_line = f"source={source!r}. "
        nxt = "Next: pdfdrill compare <pdf> → LaTeX | KaTeX | image table."
    return (
        f"Built unified model: {total} objects ({top}). "
        f"{img_line}"
        f"bibkey={key!r}. Stored at {sc.get_evidence('model_path')}.\n"
        f"{nxt}"
        + _bibkey_hint(key)
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
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
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
    rel = _artref(sc, out_path)
    return (
        f"Comparison table: {rows} expressions (LaTeX | KaTeX | MathPix image). "
        f"Open {rel} in a browser."
    )


def cmd_bibsource(pdf: Path, bib_path: str | None = None,
                  bbl_path: str | None = None, force: bool = False) -> str:
    """Ingest the author's GOLD bibliography (`.bbl` + `.bib`) into the model.

    This is the bibliography analogue of `pdfdrill injectlatex` (author .tex as gold
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
                               link_citations_by_label, link_citations,
                               detect_author_year_in_objects)

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    def _default(ext):
        c = pdf.parent / f"{pdf.stem}{ext}"
        return str(c) if c.exists() else None
    bbl = bbl_path or _default(".bbl")
    bib = bib_path or _default(".bib")
    discovered = ""
    if not bbl and not bib:
        # DISCOVER the bib the LaTeX source NAMES (\bibliography{}/\addbibresource{})
        # in the e-print source dir — e.g. \bibliography{biblio} -> texsrc/biblio.bib,
        # which a bare <stem>.bib lookup would never find.
        from . import latex_source
        src_dir = (doc.meta.get("latex_source_dir")
                   or str(model_path.parent / "texsrc"))
        res = latex_source.find_bib_resources(src_dir)
        if res["bbl"]:
            bbl = res["bbl"][0]
        if res["bib"]:
            bib = res["bib"][0]
        if bbl or bib:
            discovered = f" (auto-discovered in {Path(src_dir).name}/)"
    if not bbl and not bib:
        return ("No .bbl/.bib found next to the PDF or named by the LaTeX source "
                "(\\bibliography{}/\\addbibresource{}) in texsrc/. Pass --bbl "
                "<file.bbl> and/or --bib <file.bib>.")

    # The author's bibliography is authoritative: drop prior (heuristic)
    # References + their cites edges so we don't mix gold with OCR guesses.
    for oid in [oid for oid, o in doc.objects.items() if o.type == "Reference"]:
        doc.objects.pop(oid, None)
    doc.alignments = [a for a in doc.alignments if a.kind != "cites"]
    doc.streams.pop("references", None)

    # The paper's bibliography = the CITED subset of a (possibly larger, shared)
    # .bib. Gather the cited keys from the in-text Citation objects the LaTeX-
    # source builder extracted from \cite{}; restrict the .bib to them. (No
    # citations detected → ingest all, backward-compatible.)
    cited = {(c.props.get("citekey") or "").strip()
             for c in doc.objects.values() if c.type == "Citation"}
    cited.discard("")
    created = enriched = 0
    if bbl:
        created = ingest_bbl(doc, Path(bbl).read_text(encoding="utf-8"))
    if bib:
        enriched = load_bibtex_file(doc, Path(bib).read_text(encoding="utf-8"),
                                    restrict=(cited or None))["attached"]

    n_refs = sum(1 for o in doc.objects.values() if o.type == "Reference")
    n_cits = sum(1 for o in doc.objects.values() if o.type == "Citation")
    linked = link_citations_by_label(doc)        # primary: alpha label
    if not linked:                               # no labeled links → citekey/number
        linked = link_citations(doc)
    if not linked:                               # still none: detect author-year
        # MathPix renders natbib as [Surname, year]; mine them from object text
        doc.objects = {k: v for k, v in doc.objects.items()
                       if not (v.type == "Citation"
                               and v.props.get("added_by") == "bibliography")}
        detect_author_year_in_objects(doc)
        linked = link_citations(doc)
        n_cits = sum(1 for o in doc.objects.values() if o.type == "Citation")

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
        f"Gold bibliography ingested from {src}{discovered}: {n_refs} Reference(s) "
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


def cmd_rulebook(pdf: Path, force: bool = False) -> str:
    """The vertical slice: claims/definitions -> kitems -> rulebook.md.

    Runs the stratum-4 claim extractor inside the FIXPOINT driver over the
    document's semantic graph (loaded from `<key>.semantic.json` when present,
    so kitems join the entities `semantic` built; created fresh otherwise),
    persists the graph, and projects `rulebook.md` — one supported/accepted
    statement per line with a `[→k:hash]` drill-down anchor — plus the
    `<key>.kitems.tiddlers.json` for the wiki. Re-running is a no-op (content-
    hash identity).
    """
    from docmodel.core import Document
    from semantic.graph import SemanticGraph
    from semantic.identity import IdentityResolver
    from semantic.layers import content_identity  # registers content_hash BEFORE reindex
    from semantic import claims, fixpoint, kitems, rulebook as _rulebook

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not model_path.exists():
        return (f"No model for {pdf.name} — run `pdfdrill model` (PDF) or "
                f"`pdfdrill markdown` (.md) first.")
    doc = load_model(model_path)
    key = sc.get_evidence("bibkey") or doc.meta.get("bibkey") or pdf.stem

    sem_path = sc.blob_dir / f"{key}.semantic.json"
    if sem_path.exists() and not force:
        g = SemanticGraph.from_dict(json.loads(sem_path.read_text(encoding="utf-8")))
    else:
        g = SemanticGraph()
    r = IdentityResolver(g).reindex()

    res = fixpoint.run_fixpoint(g, r, [(4, claims.make_claims_pass(doc, key))])
    sem_path.parent.mkdir(parents=True, exist_ok=True)
    sem_path.write_text(json.dumps(g.to_dict(), indent=2, ensure_ascii=False),
                        encoding="utf-8")

    md = _rulebook.project_rulebook(g, key)
    rb_path = sc.blob_dir / "rulebook.md"
    rb_path.write_text(md, encoding="utf-8")
    tids = kitems.kitem_tiddlers(g, key)
    (sc.blob_dir / f"{key}.kitems.tiddlers.json").write_text(
        json.dumps(tids, ensure_ascii=False, indent=1), encoding="utf-8")

    ks = kitems.all_kitems(g)
    by_status: dict[str, int] = {}
    for e in ks:
        st = kitems.status_of(g, e.id)
        by_status[st] = by_status.get(st, 0) + 1
    sc.set_evidence("kitems", {"count": len(ks), **by_status})
    sc.save()
    stat_s = ", ".join(f"{v} {k}" for k, v in sorted(by_status.items()))
    return (f"Fixpoint: {res['rounds']} round(s), {res['new_kitems']} new "
            f"kitem(s) ({len(ks)} total: {stat_s}). Rulebook -> "
            f"{rb_path.relative_to(sc.pdf_path.parent)} "
            f"({len(tids)} kitem tiddler(s)). Drill-down: rulebook line "
            f"[→k:hash] -> kitem tiddler -> evidence span (bibkey/node/page) "
            f"-> the model object.")


def cmd_locate(pdf: Path) -> str:
    """Locate every embedded raster image on its page in ONE canonical system
    (points, top-left origin, y-down — the MathPix orientation): native pixel
    size + ppi, the placement rectangle (pdfplumber), full-page detection, the
    PDF object number (the join key), and normalized [0,1] coords. When a
    MathPix `lines.json` exists, each image is COMPARED to the MathPix line(s)
    drawn over it (IoU / fraction-inside) and MathPix-only figures (vector
    charts / figures inside a scanned full-page raster) are surfaced. Reuses
    the stored pdfinfo/pdfimages text when present (no re-run). Stores
    `image_placements` in the sidecar.
    """
    from . import pdfimg_locate as L

    sc = Sidecar(pdf)
    info_txt = sc.get_evidence("pdfinfo_text") or None
    list_txt = sc.get_evidence("pdfimages_list_text") or None
    try:
        res = L.locate_pdf_images(str(pdf), pdfinfo_text=info_txt,
                                  pdfimages_list_text=list_txt)
    except Exception as e:
        return f"pdfdrill locate: {e}"

    # Compare against MathPix regions if the model/lines are available.
    lines_path = _lines_json_path(pdf)
    matched = mp_only = 0
    if lines_path.exists():
        try:
            lines = json.loads(lines_path.read_text(encoding="utf-8"))
            L.match_against_mathpix_lines(res, lines)
            mo = L.mathpix_only_figures(dict(res), lines)
            mp_only = sum(len(p.get("mathpix_only", [])) for p in mo.get("pages", []))
            matched = sum(1 for p in res["pages"] for im in p["images"]
                          if im.get("mathpix"))
        except Exception:
            pass

    pages = res.get("pages", [])
    imgs = [im for p in pages for im in p["images"]]
    full = sum(1 for im in imgs if im.get("full_page"))
    tmpl = sum(1 for im in imgs if im.get("template"))
    sc.set_evidence("image_placements", res)
    sc.save()
    return (f"Located {len(imgs)} embedded image(s) across {len(pages)} page(s): "
            f"{full} full-page, {tmpl} recurring template(s)"
            + (f", {matched} matched to a MathPix region" if lines_path.exists() else "")
            + (f", {mp_only} MathPix-only figure(s) (no XObject — vector/scan-inside)"
               if mp_only else "")
            + ". Canonical coords (pt, top-left, y-down) + normalized [0,1] + PDF "
              "object number stored in the sidecar (image_placements). A full-page "
              "image = 'nothing to do'; a MathPix-only figure -> rasterize+crop.")


def cmd_clean(pdf: Path) -> str:
    """Clean MathPix LaTeX residuals from the model so semantic analysis sees
    plain text. Today: leading `\\section*{Title}` commands that MathPix merged
    into a Paragraph's text are stripped to the title alone, with `kind`
    (section/subsection/...) + `refnum` recorded on the object. Re-saves the
    model; idempotent.
    """
    from docmodel.core import Document
    from . import heading_cleanup

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} — run `pdfdrill model` first."
    doc = load_model(model_path)
    fn = heading_cleanup.extract_footnote_paragraphs(doc)
    nh = heading_cleanup.clean_heading_residuals(doc)
    mt = heading_cleanup.materialize_transclusions(doc)
    if fn or nh or mt:
        save_model(model_path, doc)
    return (f"Cleaned: {fn} footnote(s) lifted into Footnote objects, {nh} leading "
            f"LaTeX sectioning command(s) stripped (title + kind/refnum), {mt} "
            f"paragraph(s) materialized with transclusion tokens ({{{{||FO}}}}/"
            f"{{{{||FN}}}}) so semantic/llmtext read transcluded text. "
            + ("Re-run tiddlers/report/semantic/llmtext to refresh."
               if (fn or nh or mt) else "Nothing to clean.")) 


def cmd_llmtext(pdf: Path, delimiter: str = "%%%%", split: bool = True) -> str:
    """Flat, delimiter-separated dump for an LLM: per unit the tiddler-style
    title then the content (paragraph TEXT or formula LATEX), in document
    order, units separated by `delimiter` (default %%%%). A LaTeX paragraph is
    one block — paragraph text is split on double line breaks into separate
    units; empty/null formulas (CDN-crop only) are skipped. Writes
    `<key>.llm.txt`.
    """
    from docmodel.core import Document
    from docops.projectors.llm_text import LLMTextProjector
    from docops.base import OperatorConfig

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not model_path.exists():
        return (f"No model for {pdf.name} — run `pdfdrill model` (PDF) or "
                f"`pdfdrill markdown` (.md) first.")
    # Fast read-path: build the dump from the lazy DocGraph over the packed
    # sidecar (≈0.2s, never expands the char streams) — byte-identical to the
    # full-Document path (build_llm_text reads .type/.id/.props on either).
    from docops.projectors.llm_text import build_llm_text
    from . import model_io
    g = _fresh_docgraph(pdf, sc, model_path)
    key = sc.get_evidence("bibkey") or g.meta.get("bibkey") or pdf.stem
    out = build_llm_text(list(g), g.meta, delimiter=delimiter, split_paragraphs=split)
    doc = None
    out_path = sc.blob_dir / f"{key}.llm.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out, encoding="utf-8")
    n_units = out.count("\n" + delimiter + "\n") + 1 if out else 0
    n_para = len(g.type_index.get("Paragraph", []))
    n_eq = len(g.type_index.get("Equation", [])) + len(g.type_index.get("Formula", []))
    return (f"LLM text dump: {n_units} unit(s) from {n_para} paragraph(s) + "
            f"{n_eq} formula(s) (paragraphs split on double line breaks, "
            f"empty formulas skipped), delimiter '{delimiter}'. "
            f"Open {_artref(sc, out_path)} in a browser.")


def cmd_enhance(pdf: Path, only: str | None = None, skip: str | None = None) -> str:
    """Run the uniform enhancement PASS PIPELINE over the model's IR — an ordered,
    dependency-aware sequence of idempotent passes (frontmatter / math / citation /
    concepts / abstract / toc / index / summary). Loads the Document once, runs the
    passes, persists once. `--only a,b` / `--skip a,b` filter. Each projector then
    consumes the enriched model unchanged.
    """
    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not model_path.exists():
        return (f"No model for {pdf.name} — run `pdfdrill model` (PDF) or "
                f"`pdfdrill markdown` (.md) first.")
    try:
        from passes import PassContext, run_pipeline
    except Exception as e:
        return f"Pass pipeline unavailable: {e}"

    doc = load_model(model_path)
    ctx = PassContext(doc=doc, pdf=pdf, sidecar=sc)
    onlyset = {s.strip() for s in only.split(",")} if only else None
    skipset = {s.strip() for s in skip.split(",")} if skip else None
    results = run_pipeline(ctx, only=onlyset, skip=skipset)
    if any(r.changed for r in results):
        save_model(model_path, doc)

    icon = {"ran": "✓", "n/a": "·", "skipped": "—", "error": "✗"}
    lines = [f"Enhancement pipeline on {pdf.name} "
             f"({sum(r.status == 'ran' for r in results)} ran, "
             f"{sum(r.changed for r in results)} changed the model):"]
    for r in results:
        lines.append(f"  {icon.get(r.status, '?')} {r.name:11s} {r.summary}")
    return "\n".join(lines)


def cmd_scan(job=None, *, out_dir=None, simplex=False, from_dir=None,
             device=None, title=None, deskew=True, as_json=False) -> str:
    """Acquire paper from the scanner's ADF and assemble its lossless PDF.

    pdfdrill drives SCANDRILL as a library — SCANDRILL owns the rig (ADF duplex
    @300dpi, deskew measured+applied, raw/ retained, blank sides recorded rather
    than deleted) and the lossless projection; pdfdrill owns the integration.

    NO OCR text layer is added: that would make `route` read the scan as
    born-digital and send it to pdfminer instead of the vision lane. The
    searchable underlay is a human deliverable, produced separately.
    """
    import json as _json

    from . import config as cfg
    from . import scan as scan_mod

    out_dir = Path(out_dir) if out_dir else cfg.library_root()
    steps: list[str] = []
    try:
        res = scan_mod.scan(job, out_dir, simplex=simplex, from_dir=from_dir,
                            device=device, title=title, deskew=deskew,
                            on_progress=steps.append)
    except scan_mod.ScanUnavailable as exc:
        return str(exc)
    except Exception as exc:                               # noqa: BLE001
        return (f"scan failed: {type(exc).__name__}: {exc}\n"
                f"  `pdfdrill doctor` checks the tools; a scanner that is asleep "
                f"or busy often just needs a retry.")

    if as_json:
        return _json.dumps({"job": res.job, "pdf": str(res.pdf),
                            "manifest": str(res.manifest),
                            "raw_dir": str(res.raw_dir), "sides": res.sides,
                            "kept": res.kept, "blanks": res.blanks,
                            "deskewed": res.deskewed, "device": res.device,
                            "orientation": res.orientation})

    out = [f"scan {res.job}: {res.summary} → {res.pdf}"]
    out += [f"  {s}" for s in steps]
    if res.orientation:
        out.append(f"  the stack was fed {res.orientation}°-rotated — all pages "
                   f"turned upright (recorded, raw kept)")
    if res.blanks:
        out.append(f"  {res.blanks} blank side(s) recorded in the manifest "
                   f"(not deleted) — page removals stay accountable.")
    out.append(f"  raw sides kept in {res.raw_dir} (deskew is the only "
               f"pixel-touching step, and it is recorded)")
    out.append(f"  the PDF is a projection of {res.manifest.name} — no OCR layer "
               f"was added, so `route` sees a scan and picks the vision lane.")
    out.append(f"  Next: pdfdrill route {res.pdf.name}   (then drill it)")
    return "\n".join(out)


def cmd_docos(line: str = "") -> str:
    """docOS — the document-set shell. Runs one L0 selector command line against
    the persisted working set (`cd`/`add <glob>`/`remove`/`clear`/`show`/
    `save-set`/`load-set`/`sets`) and prints the compact, level-gated state UI.
    No args → just show the current state. (L1+ materialization: later steps.)"""
    from . import docos
    state = docos.load_state()
    msg = ""
    if line.strip():
        msg, state = docos.dispatch(state, line)
        docos.save_state(state)
    ui = docos.render_ui(state)
    return (msg + "\n\n" + ui) if msg else ui


def cmd_conclusion(pdf: Path, limit: int = 8) -> str:
    """Retrieve the document's CONCLUDING paragraphs — the actual outcome, which
    the Abstract (goal + method) does NOT give. Finds the conclusion SECTION by a
    heading heuristic over the Section captions (the TOC), preferring a strong
    match before the References/Appendix boundary; returns its paragraphs in flow
    order, else the final body paragraphs. Fast DocGraph read path.
    """
    from . import conclusion as C

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return (f"No model for {pdf.name} — run `pdfdrill model` (PDF) or "
                f"`pdfdrill markdown` (.md) first.")

    g = _fresh_docgraph(pdf, sc, model_path)
    res = C.conclusion_text(list(g), final_n=limit)
    paras = res["paragraphs"][:limit]
    if not paras:
        return (f"No concluding text found in {pdf.name} (no conclusion section "
                f"and no final paragraphs).")
    if res["source"] == "section":
        head = f"Conclusion of {pdf.name} — section “{res['section']}”:"
    else:
        head = (f"No explicit conclusion section in {pdf.name}; the final "
                f"{len(paras)} body paragraph(s):")
    caveat = ("\n\n(Note: this is the authors' stated conclusion — distinct from "
              "the Abstract, which gives the goal/method, not the results. It may "
              "still overstate scope vs. the actual examples/code; check those.)")
    return head + "\n\n" + "\n\n".join(paras) + caveat


def cmd_mathir(pdf: Path) -> str:
    """Canonical math layer: parse every FO/EQ's macro-EXPANDED LaTeX into a
    canonical tree (SymPy, anchored by its srepr) and PERSIST it under
    `props["math"]` on the model. SymPy is the first of several backends off the
    SAME tree (Lean4/FriCAS/Mathematica/SMT-LIB/GraphRAG planned). Our operator/
    symbol layer normalizes the surface first (\\mathcal{L} -> L). Needs the
    [math] extra; otherwise the model is left untouched.
    """
    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not model_path.exists():
        return (f"No model for {pdf.name} — run `pdfdrill model` (PDF) or "
                f"`pdfdrill markdown` (.md) first.")
    try:
        from mathlayer import annotate_object, backends, parse as mlparse
    except Exception:
        return ("Canonical math layer unavailable — install the extra: "
                "pip install 'pdfdrill[math]' (sympy + latex2sympy2_extended).")
    if not mlparse.available():
        return ("Canonical math layer needs a LaTeX→SymPy parser: "
                "pip install 'pdfdrill[math]' (latex2sympy2_extended). "
                "The FO/EQ LaTeX is unchanged.")

    doc = load_model(model_path)
    counts = {"seen": 0, "parsed": 0, "relations": 0, "unparsed": 0}
    samples: list[str] = []
    for obj in doc.objects.values():
        if obj.type not in ("Formula", "Equation"):
            continue
        cm = annotate_object(obj)        # feeds props["latex"] (macro-expanded)
        if cm is None:
            continue
        counts["seen"] += 1
        if cm.role == "unparsed":
            counts["unparsed"] += 1
        else:
            counts["parsed"] += 1
            if cm.role == "relation":
                counts["relations"] += 1
            if len(samples) < 3 and cm.sympy:
                samples.append(f"{obj.id}: {cm.sympy}")
    if counts["seen"]:
        save_model(model_path, doc)

    seen = counts["seen"]
    if not seen:
        return f"No Formula/Equation objects in {pdf.name}'s model."
    rate = 100.0 * counts["parsed"] / seen
    out = [
        f"Canonical math layer written to props['math'] for {seen} FO/EQ in "
        f"{pdf.name}: {counts['parsed']} parsed ({rate:.0f}%), "
        f"{counts['relations']} relations, {counts['unparsed']} unparsed.",
        f"Backends now: {', '.join(backends.available())}; "
        f"planned off the same tree: {', '.join(backends.PLANNED)}.",
    ]
    if samples:
        out.append("Sample: " + " | ".join(samples))
    if counts["unparsed"]:
        out.append("(Unparsed = research-grade LaTeX the parser can't yet read; "
                   "extend the operator layer or feed cleaner LaTeX.)")
    return "\n".join(out)


def cmd_quantities(pdf: Path) -> str:
    """Quantitative-layer report (S4.4): quantities by kind, measurements, the
    verification tally (verified/refuted/uncheckable via VER.EQ.RECOMPUTE — the
    verifier is pure, so this runs offline over the stored props) and the top
    refuted item. Fast DocGraph read path; hints at `pdfdrill enhance` when the
    quantity/measurement layers are absent."""
    from semantic.verify import verify_derivation

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not model_path.exists():
        return (f"No model for {pdf.name} — run `pdfdrill model` (PDF) or "
                f"`pdfdrill markdown` (.md) first.")
    g = _fresh_docgraph(pdf, sc, model_path)

    quants: list[dict] = []
    n_meas = 0
    for o in g:
        for q in (o.props.get("quant") or []):
            quants.append(q)
        n_meas += len(o.props.get("meas") or [])

    if not quants and not n_meas:
        return (f"quantities {pdf.name}: no quantity/measurement layer on the "
                f"model — run `pdfdrill enhance {pdf.name} --only "
                f"quantity,measurement,concepts` first.")

    kinds: dict[str, int] = {}
    for q in quants:
        kinds[q.get("kind", "?")] = kinds.get(q.get("kind", "?"), 0) + 1
    verified = refuted = uncheckable = 0
    top_refuted = None
    for q in quants:
        if q.get("kind") != "derivation":
            continue
        v = verify_derivation(q)
        if v["ok"] is True:
            verified += 1
        elif v["ok"] is False:
            refuted += 1
            if top_refuted is None:
                top_refuted = (q.get("raw", ""), v["detail"])
        else:
            uncheckable += 1

    lines = [
        f"quantities {pdf.name}: {len(quants)} quantities "
        f"({', '.join(f'{k}:{v}' for k, v in sorted(kinds.items()))}), "
        f"{n_meas} measurement(s).",
        f"  derivation check: {verified} verified, {refuted} refuted, "
        f"{uncheckable} uncheckable (VER.EQ.RECOMPUTE).",
    ]
    if top_refuted is not None:
        lines.append(f"  top refuted: `{top_refuted[0]}` — {top_refuted[1]}")
    if n_meas:
        lines.append("  measurements live on the paragraphs (props['meas']); "
                     "`pdfdrill semantic` projects them as MEASURES edges.")
    return "\n".join(lines)


def cmd_mathcheck(pdf: Path, limit: int = 8) -> str:
    """Formula QC: scan the model's formula LaTeX for FLATTENED equations — a
    keyless/visual reconstruction that linearised a 2-D layout instead of
    emitting LaTeX (subscripts dropped to neighbouring lines, the equation
    number mashed in, e.g. `M = m a (F + j ) (B65) n 0`). Such formulas are not
    valid LaTeX and won't render/transclude. Fast DocGraph read path. When any
    are flagged, points back to `pdfdrill remath` (the LaTeX-demanding rebuild).
    """
    from . import mathqc, model_io

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not model_path.exists():
        return (f"No model for {pdf.name} — run `pdfdrill model` (PDF) or "
                f"`pdfdrill markdown` (.md) first.")
    g = _fresh_docgraph(pdf, sc, model_path)
    rep = mathqc.audit_formulas(list(g), max_samples=limit)
    total, flat = rep["total"], rep["flattened"]
    if total == 0:
        return f"mathcheck {pdf.name}: no formula objects in the model."
    if flat == 0:
        return (f"mathcheck {pdf.name}: {total} formula(s), 0 flattened — the "
                f"LaTeX carries 2-D structure (subscripts/superscripts). Clean.")
    lines = [
        f"mathcheck {pdf.name}: {flat}/{total} formula(s) ({rep['ratio']*100:.0f}%) "
        f"look FLATTENED — linearised text, not LaTeX (won't render/transclude).",
        "",
        "Examples:",
    ]
    for s in rep["samples"]:
        lines.append(f"  [{s['id']}] {s['latex']!r}")
    lines += [
        "",
        "These were transcribed visually without preserving the 2-D math layout "
        "(the tesseract chain, or a hand-rolled pseudo-lines.json). To rebuild "
        "them as real LaTeX (so transclusion works):",
        f"  pdfdrill remath {pdf.name}",
        "then `pdfdrill markdown <key>.mathpix.md` to re-model. `remath` delegates "
        "each rendered page to the LLM with the MathPix-replacement prompt "
        "(emit \\(..\\)/$$..$$ LaTeX, or decline a page honestly).",
    ]
    return "\n".join(lines)


def cmd_classify(pdf: Path, k: int = 8) -> str:
    """Subject-classify the drilled document against the vocabnet vocabularies
    (MSC first; any compiled scheme in vocab/compiled/ participates). Gathers
    section captions + prose + equation LaTeX (fast DocGraph read path), runs
    the federation, persists `classification` in the sidecar, returns prose.

    German prose only matches the English vocabulary labels AFTER translation —
    run `pdfdrill translate --from DE --to EN-US` first; a NOTE is emitted when
    the doc looks non-English and untranslated (equation/caption signal still
    classifies)."""
    from . import classify as _cl
    from . import model_io
    from vocabnet.sources import COMPILED_DIR
    from vocabnet import Federation

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not model_path.exists():
        return (f"No model for {pdf.name} — run `pdfdrill model` (PDF) or "
                f"`pdfdrill markdown` (.md) first.")
    g = _fresh_docgraph(pdf, sc, model_path)
    nodes = list(g)

    import os
    fed = Federation.load_dir(COMPILED_DIR) if os.path.isdir(COMPILED_DIR) else Federation([])
    if not fed.vocabs:
        return ("No compiled vocabularies in vocab/compiled/ — build one first, "
                "e.g. `python3 -m vocabnet.sources build msc` after dropping the "
                "MSC listing into vocab/sources/msc/ (see its STUB.md).")

    # language note (translation guidance)
    note = ""
    try:
        from features.extract_language import language_of
        lang = language_of(_cl.gather_classification_text(nodes)[:4000])
    except Exception:
        lang = "und"
    if lang not in ("en", "und") and not _cl.has_translation(nodes):
        note = (f" NOTE: document language looks '{lang}' and no translation is "
                f"present — run `pdfdrill translate --from {lang.upper()} --to EN-US` "
                f"for full keyword matching (math/captions still classified).")

    res = _cl.classify_document(nodes, fed, k=k)
    res["language"] = lang
    sc.set_evidence("classification", res)
    sc.save()

    if not res["msc_top"]:
        return (f"Classified {pdf.name} over {sorted(fed.vocabs)} but no subject "
                f"hits (text chars={res['chars']}).{note}")
    rolls = ", ".join(f"{c} ({s:.0f})" for c, s in list(res["msc_sections"].items())[:5])
    lines = [f"Subject classification of {pdf.name} "
             f"(schemes present: {', '.join(res['present']) or 'none'}; "
             f"absent: {', '.join(res['absent']) or 'none'}):",
             f"  MSC discipline rollup (2-digit): {rolls}",
             "  Top MSC codes:"]
    for h in res["msc_top"][:k]:
        lines.append(f"    {h['code']:8} {h['pref'][:60]:60} {h['score']:.1f}")
    for s in res["present"]:
        if s == "msc":
            continue
        hits = res["per_source"].get(s, [])[:k]
        if hits:
            lines.append(f"  {s} (top concepts by votes):")
            for h in hits:
                lines.append(f"    {h['pref'][:60]:60} (votes {h['votes']}, {h['score']:.0f})")
    return "\n".join(lines) + note


# ---------------------------------------------------------------------------
# Chat-proxy primitives (the external drillui_chat tool shells out to these):
#   retrieve — the question→context transformation (RAG enrichment)
#   chatlog  — store one Q&A turn as a transcript line + an answer kitem
# Both are read-mostly and additive; the conversational proxy stays external.
# ---------------------------------------------------------------------------

# Retrievable object types pooled into a combined store (what retrieve reads).
_COMBINE_TYPES = ("Section", "Paragraph", "Abstract", "ListItem", "Footnote",
                  "Toc", "Equation", "Formula", "Concept")


def cmd_combine(out: Path, pdfs: "list[Path]", force: bool = False) -> str:
    """Merge several drilled documents into ONE combined store for multi-document
    chat: pool each doc's retrievable objects (prose/math/concepts), namespacing
    every id as `<bibkey>:<id>` so an answer cites which paper. Each input must
    already be drilled (`pdfdrill model`); writes a JSON store at `--out` that
    `pdfdrill retrieve <out>` / drillui chat over as one context."""
    from . import model_io
    if not pdfs:
        return "combine: give two or more drilled PDFs/.md and --out <file>."
    objects: list[dict] = []
    used, missing, srcs = [], [], []
    for pdf in pdfs:
        sc = Sidecar(pdf)
        mp = _model_path(sc)
        if not mp.exists():
            missing.append(pdf.name)
            continue
        bk = resolve_bibkey(pdf, None, sc)
        g = model_io.load_docgraph(mp)
        n = 0
        for o in g:
            if getattr(o, "type", "") not in _COMBINE_TYPES:
                continue
            props = dict(getattr(o, "props", {}) or {})
            props["bibkey"] = bk
            objects.append({"type": o.type, "id": f"{bk}:{o.id}", "props": props})
            n += 1
        used.append((bk, n))
        srcs.append({"bibkey": bk, "path": str(pdf)})    # so per-doc commands can fan out
    if not used:
        return ("combine: none of the inputs has a built model — run `pdfdrill "
                f"model` first. Missing: {', '.join(missing) or '(none given)'}.")
    out = Path(out)
    if out.exists() and not force:
        return f"combine: {out.name} exists — pass --force to overwrite."
    meta = {"title": f"Combined: {', '.join(bk for bk, _ in used)}",
            "bibkey": out.stem, "combined_docs": [bk for bk, _ in used],
            "num_docs": len(used), "sources": srcs}
    out.write_text(json.dumps(
        {"is_combined": True, "meta": meta, "objects": objects},
        ensure_ascii=False), encoding="utf-8")
    parts = ", ".join(f"{bk} ({n})" for bk, n in used)
    warn = (f" Skipped (no model): {', '.join(missing)}." if missing else "")
    return (f"Combined {len(used)} document(s) → {len(objects)} units in {out.name} "
            f"[{parts}].{warn} Chat over all: `pdfdrill retrieve {out.name} \"…\"` "
            f"or `bun tools/drillui_bridge.ts {out.name}`.")


def _load_combined_store(path: Path):
    """If `path` is a combined store (from `pdfdrill combine`), return (nodes,
    meta) where nodes expose .type/.id/.props for retrieve; else None."""
    from types import SimpleNamespace
    p = Path(path)
    if not p.is_file() or p.suffix.lower() not in (".json", ".docpack", ".combined"):
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(d, dict) or not d.get("is_combined"):
        return None
    nodes = [SimpleNamespace(type=o.get("type", ""), id=o.get("id", ""),
                             props=o.get("props", {})) for o in d.get("objects", [])]
    return nodes, d.get("meta", {})


def cmd_retrieve(pdf: Path, question: str, k: int = 8, as_json: bool = False) -> str:
    """Transform a question into grounded CONTEXT from the drilled model: the
    top-k relevant units (paragraphs/sections/formulas/concepts), each tagged by
    object id. `--json` returns {question, units, prompt, title, subjects} for a
    wrapper; otherwise prose. Fast DocGraph read path. Also accepts a COMBINED
    store from `pdfdrill combine` (multi-document context)."""
    from . import retrieve as R, model_io
    # Multi-document: a combined store is retrieved across all pooled docs.
    combo = _load_combined_store(pdf)
    if combo is not None:
        nodes, meta = combo
        hits = R.retrieve(question, nodes, k=k)
        title = meta.get("title") or Path(pdf).stem
        prompt = R.build_prompt(question, hits, title=str(title), subjects="")
        if as_json:
            return json.dumps({"question": question, "units": hits, "prompt": prompt,
                               "title": str(title), "subjects": ""}, ensure_ascii=False)
        if not hits:
            return f"No relevant units for the question in {Path(pdf).name}."
        lines = [f"Top {len(hits)} unit(s) across {meta.get('num_docs', '?')} "
                 f"document(s) (cite these ids):"]
        for h in hits:
            lines.append(f"  [{h['id']}] ({h['type']}, {h['score']:.1f}) "
                         f"{h['text'][:140].strip()}")
        return "\n".join(lines)

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} — run `pdfdrill model`/`markdown` first."
    g = _fresh_docgraph(pdf, sc, model_path)
    hits = R.retrieve(question, list(g), k=k)
    title = g.meta.get("title") or sc.get_evidence("arxiv_title") or pdf.stem
    cls = sc.get_evidence("classification") or {}
    subjects = ", ".join(list((cls.get("msc_sections") or {}).keys())[:4])
    prompt = R.build_prompt(question, hits, title=str(title), subjects=subjects)
    if as_json:
        return json.dumps({"question": question, "units": hits, "prompt": prompt,
                           "title": str(title), "subjects": subjects},
                          ensure_ascii=False)
    if not hits:
        return f"No relevant units for the question in {pdf.name}."
    lines = [f"Top {len(hits)} unit(s) for the question (cite these ids):"]
    for h in hits:
        lines.append(f"  [{h['id']}] ({h['type']}, {h['score']:.1f}) "
                     f"{h['text'][:140].strip()}")
    return "\n".join(lines)


def _model_equations(doc) -> "tuple[list, dict]":
    """(equations, pages) from a Document/DocGraph: each equation {id,page,region,
    latex}; pages maps page → (width,height) from meta['pages']."""
    eqs = []
    for o in getattr(doc, "objects", {}).values() if hasattr(doc, "objects") else doc:
        if getattr(o, "type", "") in ("Equation", "Formula"):
            p = getattr(o, "props", {})
            eqs.append({"id": getattr(o, "id", ""), "page": p.get("page"),
                        "region": p.get("region") or {}, "latex": p.get("latex") or ""})
    pages = {}
    for pm in (doc.meta.get("pages") if hasattr(doc, "meta") else []) or []:
        pages[pm.get("page")] = (pm.get("page_width"), pm.get("page_height"))
    return eqs, pages


def _lines_json_equations(lines: dict) -> "tuple[list, dict]":
    """(equations, pages) from a MathPix-shape lines.json."""
    eqs, pages = [], {}
    for pg in lines.get("pages", []):
        n = pg.get("page")
        pages[n] = (pg.get("page_width"), pg.get("page_height"))
        for ln in pg.get("lines", []):
            if ln.get("type") in ("math", "equation"):
                tx = (ln.get("text") or "").strip().strip("$").strip()
                eqs.append({"page": n, "region": ln.get("region") or {}, "latex": tx})
    return eqs, pages


def cmd_reconcile(pdf: Path, mathpix: str | None = None, adopt_all: bool = False) -> str:
    """Dual-route reconciliation: keep the pdfminer model's STRUCTURE + GEOMETRY,
    correct its garbled MATH with MathPix's clean LaTeX, region-matched. Runs the
    P3 math-garble QC always; when a MathPix lines.json is available (`--mathpix
    PATH`, else `<stem>.mathpix.lines.json`) it adopts the clean math onto the
    region-matched equations (geometry untouched; original kept as latex_pdfminer).
    Without a MathPix source it reports the garble + the sanctioned next step."""
    from . import reconcile as RC, model_io
    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} — run `pdfdrill model` first."

    doc = model_io.load_model(model_path)
    pm_eqs, pm_pages = _model_equations(doc)
    n_garbled = sum(1 for e in pm_eqs if RC.math_qc(e["latex"])["garbled"])

    # locate a MathPix lines.json (distinct from the pdfminer one)
    mp_path = Path(mathpix) if mathpix else pdf.with_suffix(".mathpix.lines.json")
    if not mp_path.exists():
        tip = (f"\nTo correct them, get clean math from MathPix and reconcile: "
               f"`pdfdrill mathpix {pdf.name} --force` saving a MathPix lines.json, "
               f"then `pdfdrill reconcile {pdf.name} --mathpix <that.lines.json>`. "
               f"(MathPix is the paid route; the garble itself is a DRILLPDFse "
               f"extraction bug — the QC above lists concrete cases.)") if n_garbled else ""
        return (f"reconcile {pdf.name}: {len(pm_eqs)} equations, {n_garbled} flagged "
                f"GARBLED by the QC (char-spacing / truncation) — no MathPix source "
                f"found to correct them.{tip}")

    with open(mp_path, "r", encoding="utf-8") as f:
        mp_eqs, mp_pages = _lines_json_equations(json.load(f))
    adoptions = RC.plan_adoptions(pm_eqs, mp_eqs, pm_pages, mp_pages)
    by_id = {a["pm_id"]: a for a in adoptions}
    n_adopted = 0
    for o in doc.objects.values():
        a = by_id.get(getattr(o, "id", ""))
        if a and a["mathpix_latex"] and (adopt_all or a["was_garbled"]):
            o.props.setdefault("latex_pdfminer", o.props.get("latex", ""))
            o.props["latex"] = a["mathpix_latex"]
            o.props["math_provenance"] = "mathpix"
            n_adopted += 1
    if n_adopted:
        model_io.save_model(model_path, doc)
    return (f"reconcile {pdf.name}: matched {len(adoptions)}/{len(pm_eqs)} equations "
            f"to MathPix by region; adopted MathPix clean LaTeX on {n_adopted} "
            f"(garbled) equation(s), keeping pdfminer geometry + structure. "
            f"{n_garbled} were flagged garbled. Re-run `tiddlers`/`report`/`inspect` "
            f"for the corrected math with the original structure intact.")


def cmd_occurrences(pdf: Path, types: str | None = None) -> str:
    """Emit `<bibkey>.occurrences.json` — a clean per-element region list (page +
    bbox + tiddler title) for the optional external IMAGE-ENRICHMENT tools (locate
    an element on the rendered page by region, no content matching). Region-bearing
    types only: Equation by default, `--type` adds Table/Picture/Diagram. Inline
    Formula is excluded (deduped, no per-object region; the pdfminer.six CTM chain
    is the future source). Fast DocGraph read path."""
    from . import occurrences as OC
    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} — run `pdfdrill model` first."
    g = _fresh_docgraph(pdf, sc, model_path)
    bibkey = g.meta.get("bibkey") or sc.get_evidence("bibkey") or pdf.stem
    wanted = tuple(t.strip().capitalize() for t in (types or "Equation").split(",")
                   if t.strip()) or ("Equation",)
    recs = OC.occurrence_records(list(g), str(bibkey), types=wanted)
    out_path = sc.blob_dir / f"{_safe_bibkey(str(bibkey))}.occurrences.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(recs, indent=1, ensure_ascii=False), encoding="utf-8")
    rel = _display_path(out_path, sc.pdf_path.parent)
    sc.set_evidence("occurrences_path", str(rel))
    sc.save()
    by_t: dict = {}
    for r in recs:
        by_t[r["type"]] = by_t.get(r["type"], 0) + 1
    breakdown = ", ".join(f"{n} {t.lower()}" for t, n in by_t.items()) or "none"
    return (f"Occurrences: {len(recs)} region record(s) ({breakdown}) with page + "
            f"top_left_x/y/width/height + title. Open {rel} in a browser. The image-"
            f"enrichment tool contract — locate each on the page by its region.")


def cmd_okf(pdf: Path, out: str | None = None, bibkey: str | None = None,
            semantic: bool = False) -> str:
    """Project into an OKF (Open Knowledge Format) bundle: one Markdown-with-YAML-
    frontmatter file per knowledge unit (required `type`) + a reserved `index.md`,
    cross-linked by relative Markdown links; the `.md` files open in drillui like
    any markdown. Written to `<drill>/okf/<bibkey>/` (or `--out DIR`).

    Default projects the DOCMODEL (paragraphs/equations/sections/…). `--semantic`
    instead projects the SEMANTIC GRAPH — one file per ENTITY (Company / BankAccount
    / Person / Document / …), relations as cross-links — the commercial-doc form
    that matches OKF's own examples (auto-builds the graph via `semantic`)."""
    from docmodel.core import Document
    from docops.base import OperatorConfig
    from docops.projectors.okf import OKFProjector, semantic_to_okf

    sc = Sidecar(pdf)
    key = (bibkey or sc.get_evidence("bibkey") or pdf.stem).strip()

    if semantic:
        from datetime import datetime, timezone
        graph_path = sc.blob_dir / f"{key}.semantic.json"
        if not graph_path.exists():
            cmd_semantic(pdf)
            sc = Sidecar(pdf)
            key = (bibkey or sc.get_evidence("bibkey") or pdf.stem).strip()
            graph_path = sc.blob_dir / f"{key}.semantic.json"
        if not graph_path.exists():
            return f"No semantic graph for {pdf.name} — run `pdfdrill semantic` first."
        with open(graph_path, "r", encoding="utf-8") as f:
            graph = json.load(f)
        ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        bundle = semantic_to_okf(graph, key, ts)
    else:
        model_path = _model_path(sc)
        if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
            cmd_model(pdf, bibkey=bibkey)
            sc = Sidecar(pdf)
            model_path = _model_path(sc)
        if not model_path.exists():
            return f"No model for {pdf.name} — run `pdfdrill model` first."
        with open(model_path, "r", encoding="utf-8") as f:
            doc = Document.from_dict(json.load(f))
        key = (bibkey or sc.get_evidence("bibkey") or doc.meta.get("bibkey")
               or pdf.stem).strip()
        if bibkey:
            doc.meta["bibkey"] = key
        proj = OKFProjector(OperatorConfig(op="projector", classname="OKFProjector",
                                           params={}))
        bundle = proj.project(doc)
    sub = "okf-semantic" if semantic else "okf"
    out_dir = Path(out) if out else (sc.blob_dir / sub / _safe_bibkey(key))
    out_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in bundle.items():
        fp = out_dir / rel
        fp.parent.mkdir(parents=True, exist_ok=True)   # per-type subfolders
        fp.write_text(content, encoding="utf-8")
    rel_dir = _display_path(out_dir, sc.pdf_path.parent)
    sc.set_evidence("okf_semantic_path" if semantic else "okf_path", str(rel_dir))
    sc.save()
    ndir = len({r.split('/')[0] for r in bundle if '/' in r})
    kind = ("entity graph (Company/BankAccount/Person/…)" if semantic
            else "docmodel (equations/ sections/ references/ …)")
    return (f"OKF bundle for {pdf.name}: {len(bundle)} files in {ndir} per-type "
            f"folders — {kind} + index.md → {rel_dir}/. Each is Markdown-with-"
            f"frontmatter (`type` per unit), cross-linked by relative Markdown "
            f"links; open {rel_dir}/index.md in drillui.")


def cmd_context(pdf: Path, query: str = "", *, types: str | None = None,
                concept: str | None = None, section: str | None = None,
                k: int | None = None, max_tokens: int | None = None,
                aspect: str = "structural", out: str | None = None) -> str:
    """Project a query into an LLM CONTEXT: select typed docmodel objects (by
    free-text + --type/--concept/--section filters), rank (structural/IDF now;
    pluggable per-aspect embedding rankers later), and render Markdown blocks with
    metadata + object ids under a --max-tokens budget. The deterministic,
    structural RAG retriever — the LLM sees a projection, never the whole doc.
    Fast DocGraph read path; also accepts a combined store."""
    from . import projection as P, model_io
    type_list = [t for t in (types or "").split(",") if t.strip()] or None

    combo = _load_combined_store(pdf)
    if combo is not None:
        nodes, meta = combo
        title = str(meta.get("title") or Path(pdf).stem)
    else:
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
        if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
            cmd_model(pdf)
            sc = Sidecar(pdf)
            model_path = _model_path(sc)
        if not model_path.exists():
            return f"No model for {pdf.name} — run `pdfdrill model`/`markdown` first."
        g = _fresh_docgraph(pdf, sc, model_path)
        nodes = list(g)
        title = str(g.meta.get("title") or sc.get_evidence("arxiv_title") or pdf.stem)

    md = P.project_context(nodes, query, types=type_list, concept=concept,
                           section=section, k=k, max_tokens=max_tokens,
                           aspect=aspect, title=title)
    if out:
        Path(out).write_text(md, encoding="utf-8")
        return f"Context projection → {out} ({len(md)} chars). {md.splitlines()[-1]}"
    return md


def cmd_ask(pdf: Path, question: str, precision: float | None = None,
            json_out: bool = False, k: int = 8) -> str:
    """Gated, grounded answering (S6.2 + the A4 readout discipline): retrieve
    the top-k units, collect the ANSWER PARTS grounded in them, and compose
    each part as a PRODUCT TUPLE (value, witnesses, count, calibrated) that
    collapses ONLY at the final rendering:

      * the grounded/derived/proposed label is a READOUT over the tuple —
        `derived` = a VER-checked derivation (recomputed here, offline),
        `grounded` = span-verified (witnesses flowed through structurally),
        `proposed` = neither (retrieved prose context);
      * `--precision p` gates: the calibrated component through Threshold(p)
        when calibration tallies exist (S6.3), else the span-status gate —
        `proposed` parts are suppressed AND the report says what was withheld
        and why (the abstention protocol);
      * no grounded/derived part at all = the bottom of the status space: an
        explicit no-grounded-answer, ZERO paragraphs quoted.

    The proof block (witness ids, recompute details, conditions) follows the
    answer; the turn persists via the chatlog (answer kitem + transcript)."""
    from . import retrieve as R
    from semantic.verify import verify_derivation

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} — run `pdfdrill model`/`markdown` first."
    g = _fresh_docgraph(pdf, sc, model_path)
    nodes = list(g)
    by_id = {getattr(o, "id", ""): o for o in nodes}
    hits = R.retrieve(question, nodes, k=k)
    # Measurement units are SHORT (a handful of tokens), so summed-IDF ranking
    # systematically favors long paragraphs over them. ask's whole point is the
    # quantitative layer, so consult it at greater depth: any measurement unit
    # that shares terms with the question joins the candidate parts (dedup by
    # id; the honest abstention below still fires when nothing matches at all).
    deep = R.retrieve(question, nodes, k=max(k, 48))
    seen_ids = {h["id"] for h in hits}
    hits += [h for h in deep if "#m" in h["id"] and h["id"] not in seen_ids]

    # --- collect the answer parts (product tuples; nothing collapses yet) ---
    parts: list[dict] = []
    for h in hits:
        hid = h["id"]
        if "#m" in hid:                          # a Measurement unit
            oid, _, mi = hid.partition("#m")
            o = by_id.get(oid)
            meas = (o.props.get("meas") or []) if o is not None else []
            try:
                m = meas[int(mi)]
            except (ValueError, IndexError):
                continue
            qref = m.get("quantity_ref") or {}
            fo = by_id.get(qref.get("obj_id") or "")
            quants = (fo.props.get("quant") or []) if fo is not None else []
            idx = qref.get("idx", 0)
            q = quants[idx] if idx < len(quants) else {}
            v = verify_derivation(q) if q.get("kind") == "derivation" else \
                {"ok": None, "detail": "", "witness": sorted(q.get("witness") or [])}
            witnesses = sorted(set(m.get("witness") or []) | set(v.get("witness") or []))
            label = ("derived" if v["ok"] is True
                     else "grounded" if witnesses else "proposed")
            if v["ok"] is False:
                label = "proposed"               # a refuted derivation never answers
            parts.append({
                "id": hid, "label": label,
                "value": f"{m.get('concept') or ''}: {m.get('measure') or ''} "
                         f"{q.get('value', '')}"
                         f"{(' ' + q['unit']) if q.get('unit') else ''}".strip(),
                "witnesses": witnesses, "count": len(witnesses),
                "calibrated": None,              # S6.3 fills from CAL tallies
                "conditions": m.get("conditions") or {},
                "detail": v.get("detail", ""),
            })
        else:                                    # retrieved prose = proposed
            parts.append({"id": hid, "label": "proposed",
                          "value": h["text"][:160], "witnesses": [],
                          "count": 0, "calibrated": None, "conditions": {},
                          "detail": ""})

    # --- the calibrated component (S6.3): the producer's Wilson estimate from
    # the doc's semantic graph tallies, filled into every proposed part's tuple
    # (still no collapse — the gate below is the readout). ---------------------
    if precision is not None:
        try:
            from semantic.graph import SemanticGraph
            from semantic import calibration as _C
            key = resolve_bibkey(pdf, None, sc)
            sem_path = sc.blob_dir / f"{key}.semantic.json"
            if sem_path.exists():
                sg = SemanticGraph.from_dict(
                    json.loads(sem_path.read_text(encoding="utf-8")))
                est = _C.precision_estimate(sg, "ask")
                if est is not None:
                    for p in parts:
                        if p["label"] == "proposed" and p["calibrated"] is None:
                            p["calibrated"] = est
        except Exception:                        # calibration must never kill ask
            pass

    answering = [p for p in parts if p["label"] in ("derived", "grounded")]
    proposed = [p for p in parts if p["label"] == "proposed"]

    if json_out:
        return json.dumps({"question": question, "parts": parts,
                           "precision": precision}, ensure_ascii=False)

    # --- abstention: bottom of the status space, quote NOTHING --------------
    if not answering:
        return (f"ask {pdf.name}: no grounded answer for {question!r} — "
                f"{len(proposed)} retrieved unit(s) are merely proposed "
                f"(un-span-verified prose), and quoting them would present "
                f"retrieval as knowledge. Try `pdfdrill retrieve` for raw "
                f"context, or enhance + semantic to grow the grounded layer.")

    # --- the precision gate (A4): a READOUT at render time — Threshold(p)
    # over the calibrated component when a tally exists (S6.3), else the
    # span-status gate (an uncalibrated proposed part never clears). ---------
    withheld = 0
    if precision is not None:
        from semantic.aggregate import Threshold
        gate = Threshold(precision)
        gated = []
        for p in proposed:
            est = p["calibrated"]
            if est is not None and gate(est):
                gated.append(p)
            else:
                withheld += 1
        proposed = gated

    lines = [f"ask {pdf.name}: {question}"]
    for p in answering:
        cond = ", ".join(f"{k2}={v2}" for k2, v2 in sorted(p["conditions"].items()))
        lines.append(f"  [{p['label']}] {p['value']}"
                     + (f" (under {cond})" if cond else ""))
    for p in proposed:
        lines.append(f"  [proposed] {p['value']}")
    if withheld:
        lines.append(f"  ({withheld} proposed part(s) WITHHELD at "
                     f"--precision {precision}: not span-verified and no "
                     f"calibration tally clears the gate)")
    lines.append("")
    lines.append("PROOF")
    for p in answering:
        lines.append(f"  {p['id']}: witnesses {', '.join(p['witnesses']) or '—'}"
                     + (f"; {p['detail']}" if p["detail"] else ""))

    answer_text = "; ".join(p["value"] for p in answering)
    try:
        cmd_chatlog(pdf, question, answer_text,
                    units=",".join(p["id"].split("#")[0] for p in answering))
    except Exception:                            # persistence must never kill the answer
        pass
    return "\n".join(lines)


def cmd_chatlog(pdf: Path, question: str, answer: str,
                units: str = "", model: str = "",
                verdict: str | None = None) -> str:
    """Store one Q&A turn in pdfdrill's structures: append it to the sidecar
    transcript (`chat.jsonl`) AND emit the answer as a KITEM in the semantic
    graph — statement = the answer, evidence = the cited units' spans, grouped
    under one Transformation(qid="ask", model=…). `units` is a comma-separated
    list of the unit ids the answer cited.

    `verdict` ("correct"|"wrong", default None) is the S6.3 calibration
    feedback: it lands as a tally row on the `ask` question-record, feeding the
    Wilson precision estimate `ask --precision` gates with."""
    import time
    from semantic.graph import SemanticGraph
    from semantic.identity import IdentityResolver
    from semantic import kitems, transformation as T, calibration as C
    from semantic.layers import content_identity  # registers the content_hash key

    sc = Sidecar(pdf)
    key = resolve_bibkey(pdf, None, sc)
    unit_ids = [u.strip() for u in units.split(",") if u.strip()]

    # 1) transcript (always)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    turn = {"question": question, "answer": answer, "units": unit_ids,
            "model": model, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if verdict:
        turn["verdict"] = verdict
    with open(sc.blob_dir / "chat.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(turn, ensure_ascii=False) + "\n")

    # 2) answer kitem in the semantic graph (load-or-create), provenance-stamped
    sem_path = sc.blob_dir / f"{key}.semantic.json"
    g = (SemanticGraph.from_dict(json.loads(sem_path.read_text(encoding="utf-8")))
         if sem_path.exists() else SemanticGraph())
    r = IdentityResolver(g).reindex()
    snap = T.snapshot(g)
    spans = [{"bibkey": key, "node": uid, "range": "", "role": "answers"}
             for uid in unit_ids]
    statement = f"Q: {question}\nA: {answer}"
    k = kitems.emit_kitem(g, r, statement, kind="answer", stratum=5,
                          spans=spans, produced_by="ask")
    if verdict in ("correct", "wrong"):
        C.record_verdict(g, r, "ask", verdict == "correct")
    T.record_batch(g, "ask", snap, seed=key, model=model or "claude")
    sem_path.write_text(json.dumps(g.to_dict(), ensure_ascii=False, indent=2),
                        encoding="utf-8")
    n_turns = sum(1 for _ in open(sc.blob_dir / "chat.jsonl", encoding="utf-8"))
    return (f"Logged Q&A turn #{n_turns} for {pdf.name}: answer stored as kitem "
            f"{k.id} (status {kitems.status_of(g, k.id)}), grounded in "
            f"{len(unit_ids)} cited unit(s). Transcript: {sc.blob_dir.name}/chat.jsonl.")


def cmd_remath(pdf: Path, pages: "list[int] | None" = None, force: bool = False) -> str:
    """Rebuild MathPix-quality Markdown (WITH LaTeX math) from rendered pages by
    delegating each page to the Claude agent (openai_vision.MATHPIX_MD_PROMPT).

    The keyless fix for the broken-transclusion problem: tesseract's text layer
    has no LaTeX, so equations never become `{{…||FO}}`. This renders the pages
    and has a multimodal model re-emit MathPix-shape Markdown (inline `\\(..\\)`,
    display `$$..$$`) that `markdown_source` turns into real Equation objects.
    CLI runtime answers synchronously; the sandbox defers one request per page.
    A page the model declines (PDFDRILL_CANNOT_RECONSTRUCT) is skipped + counted —
    never faked. Writes `<key>.mathpix.md`; then `pdfdrill markdown` it."""
    import re as _re
    from . import openai_vision, llm_delegate as D, pdf_reading

    sc = Sidecar(pdf)
    key = resolve_bibkey(pdf, None, sc)
    rt = D.detect_runtime()
    if rt is D.Runtime.NONE:
        return ("Re-math needs a Claude agent to read the pages (this is the "
                "keyless MathPix replacement). Run under Claude Code / the "
                "Claude.ai sandbox; if in the sandbox but undetected, force it "
                "with PDFDRILL_DELEGATE=sandbox (check `pdfdrill llm <pdf> "
                "--runtime`). With an OpenAI key, `pdfdrill mathpix` is the paid route.")

    out_md = sc.blob_dir / f"{key}.mathpix.md"
    rdir = sc.blob_dir / "remath"
    try:
        pngs = pdf_reading.rasterize(pdf, rdir, pages=pages, dpi=150)
    except Exception as e:  # noqa: BLE001
        return f"Re-math: could not render pages ({e})."
    if not pngs:
        return f"Re-math: no pages rendered for {pdf.name}."

    def _pageno(p: Path) -> int:
        m = _re.search(r"page-(\d+)", p.name)
        return int(m.group(1)) if m else 0

    tasks, pairs = [], []
    for p in pngs:
        t = D.LLMTask(kind="page_md", prompt=openai_vision.MATHPIX_MD_PROMPT,
                      image_path=str(p), meta={"page": _pageno(p)})
        pairs.append((_pageno(p), t))
        tasks.append(t)
    try:
        results, deferred = D.delegate_batch(tasks, drill_dir=sc.blob_dir,
                                             runtime=rt, timeout=240.0)
    except D.DelegateUnavailable as e:
        return str(e)
    if deferred is not None:
        return (f"Re-math deferred to the {rt.value} Claude agent: "
                f"{len(deferred.tasks)} page request(s) written.\n\n"
                + deferred.instruction)

    parts, gave = [], 0
    for _pageno_, t in sorted(pairs):
        res = results.get(t.task_id) or {}
        if res.get("given_up") or not res.get("markdown"):
            gave += 1
            continue
        parts.append(res["markdown"])
    if not parts:
        return (f"Re-math: the model declined every page ({gave} gave up) for "
                f"{pdf.name} — nothing written (no math was guessed).")
    out_md.write_text(f"# {key}\n\n" + "\n\n".join(parts) + "\n", encoding="utf-8")
    return (f"Re-math: rebuilt {len(parts)} page(s) of MathPix-quality Markdown"
            + (f" ({gave} page(s) the model declined, skipped)" if gave else "")
            + f" → {_artref(sc, out_md)}. Now build the model "
            f"WITH LaTeX transclusions: `pdfdrill markdown {out_md} --bibkey {key}`.\n"
            + _MATHPIX_TIP)


# Keyless page->LaTeX delegation is a fallback. MathPix does it natively, much
# faster and cheaper (an LLM re-reads each rendered page; MathPix is one OCR
# call). Surfaced in the prose of the delegating commands.
_MATHPIX_TIP = ("Tip: with any volume of math PDFs, MathPix is much faster and "
                "cheaper than per-page LLM OCR — https://mathpix.com/pricing/all "
                "(set MATHPIX_APP_ID/KEY, then `pdfdrill mathpix`).")


def _fold_eq_records_into_lines_json(lines_path: Path, records: list,
                                     force: bool = False) -> "tuple[int, int]":
    """Append agent-supplied equation records to a tesseract lines.json as real
    `equation` (+ paired `equation_number`) lines, preserving the prose lines.

    Each record is {page, number, latex, kind}. Within a page the equations are
    laid out top-to-bottom at synthetic y positions (when none is supplied) and
    each `equation_number` is placed at its equation's `top_left_y` so
    `EquationProcessor` pairs them by page+y. Returns (n_equations, n_numbers).
    Refuses to clobber a non-tesseract (MathPix) lines.json without `force`."""
    lj = json.loads(lines_path.read_text(encoding="utf-8"))
    if lj.get("source") not in ("tesseract", "visionocr") and not force:
        raise ValueError(
            f"{lines_path.name} is a {lj.get('source')!r} lines.json — refusing "
            f"to fold equations into it without --force.")
    pages_by_no = {p.get("page"): p for p in lj.get("pages", [])}
    by_page: dict = {}
    for r in records:
        pg = r.get("page")
        if pg is None and len(pages_by_no) == 1:        # single-page doc: assume it
            pg = next(iter(pages_by_no))
        by_page.setdefault(pg, []).append(r)

    n_eq = n_num = 0
    for pg, recs in by_page.items():
        page = pages_by_no.get(pg)
        if page is None:                                 # unknown page → skip
            continue
        ph = float(page.get("page_height") or 0) or 1400.0
        pw = float(page.get("page_width") or 0) or 1000.0
        step = ph / (len(recs) + 1)
        for i, r in enumerate(recs):
            latex = (r.get("latex") or "").strip()
            if not latex:
                continue
            kind = r.get("kind") if r.get("kind") in ("equation", "math") else "equation"
            reg = r.get("region")
            y = (reg.get("top_left_y") if isinstance(reg, dict)
                 and reg.get("top_left_y") is not None else round(step * (i + 1), 2))
            n_eq += 1
            page["lines"].append({
                "id": f"veq_p{pg}_{i}", "type": kind,
                "text": latex, "text_display": latex,
                "region": {"top_left_x": round(pw * 0.12, 2), "top_left_y": y,
                           "width": round(pw * 0.6, 2), "height": 24.0},
            })
            num = r.get("number")
            if num not in (None, ""):
                num_s = str(num).strip()
                disp = num_s if num_s.startswith("(") else f"({num_s})"
                n_num += 1
                page["lines"].append({
                    "id": f"veqn_p{pg}_{i}", "type": "equation_number",
                    "text": disp, "text_display": disp,
                    "region": {"top_left_x": round(pw * 0.85, 2), "top_left_y": y,
                               "width": round(pw * 0.1, 2), "height": 24.0},
                })
    # mark provenance so a re-fold is allowed and a later `ocr` won't clobber blind
    lj["source"] = "visionocr"
    lines_path.write_text(json.dumps(lj, ensure_ascii=False), encoding="utf-8")
    return n_eq, n_num


def cmd_visionocr(pdf: Path, ingest: str | None = None, dpi: int = 200,
                  pages: "list[int] | None" = None, force: bool = False) -> str:
    """Keyless, agent-delegated equation OCR — the MathPix-free route to first-class
    Equation nodes when tesseract built a math doc prose-only (NEEDS_VISION_OCR).

    Default (export/delegate): rasterize every page (≥200 DPI) and delegate each
    to the running Claude agent with `openai_vision.EQ_OCR_PROMPT` (one `eq_ocr`
    request per page, visible in `pdfdrill llm --show`). The agent returns a JSON
    array of `{page, number, latex, kind}` per page. CLI answers synchronously;
    the sandbox defers and you re-run to ingest. Answers are folded into the
    tesseract lines.json as `equation`/`equation_number` lines (number paired by
    page+y), then `model`+`eqnums` rebuild and NEEDS_VISION_OCR is cleared.

    `--ingest <json>`: fold a supplied records file (a flat array, or {records:[…]})
    directly, skipping delegation. Mirrors `candidates`/`ingest`. Equations are
    never transcribed in code — the agent (your sight) supplies the LaTeX."""
    import re as _re
    from . import openai_vision, llm_delegate as D, pdf_reading, mathqc  # noqa: F401

    sc = Sidecar(pdf)
    key = resolve_bibkey(pdf, None, sc)
    lines_path = _lines_json_path(pdf)

    def _rebuild_and_clear(n_eq: int, n_num: int, via: str) -> str:
        cmd_model(pdf, force=True)
        try:
            cmd_eqnums(pdf, force=True)
        except Exception:
            pass
        sc2 = Sidecar(pdf)
        sc2.remove_fact(NEEDS_VISION_OCR)
        sc2.save()
        counts = sc2.get_evidence("model_object_counts", {}) or {}
        return (f"visionocr ({via}): folded {n_eq} equation(s) ({n_num} numbered) "
                f"into {lines_path.name} → rebuilt model with "
                f"{counts.get('Equation', 0)} Equation node(s). "
                f"NEEDS_VISION_OCR cleared. Next: `pdfdrill tiddlers {pdf.name}` / "
                f"`pdfdrill report {pdf.name}`.\n" + _MATHPIX_TIP)

    # --- explicit ingest of a supplied records file --------------------------
    if ingest:
        ip = Path(ingest)
        if not ip.exists():
            return f"visionocr --ingest: file not found: {ingest}"
        if not lines_path.exists():
            return (f"visionocr --ingest needs the tesseract prose lines.json "
                    f"({lines_path.name}); run `pdfdrill model {pdf.name}` first.")
        try:
            payload = json.loads(ip.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return f"visionocr --ingest: {ingest} is not valid JSON ({e})."
        records = payload.get("records") if isinstance(payload, dict) else payload
        if not isinstance(records, list) or not records:
            return f"visionocr --ingest: no records in {ingest}."
        try:
            n_eq, n_num = _fold_eq_records_into_lines_json(lines_path, records, force)
        except ValueError as e:
            return str(e)
        if n_eq == 0:
            return f"visionocr --ingest: {ingest} held no usable equations."
        return _rebuild_and_clear(n_eq, n_num, "ingest")

    # --- delegate: rasterize → eq_ocr per page → fold ------------------------
    rt = D.detect_runtime()
    if rt is D.Runtime.NONE:
        return ("visionocr needs a Claude agent to read the page crops (this is "
                "the keyless equation-OCR route). Run under Claude Code / the "
                "Claude.ai sandbox; if in the sandbox but undetected, force it "
                "with PDFDRILL_DELEGATE=sandbox (check `pdfdrill llm <pdf> "
                "--runtime`). With a MathPix/OpenAI key use `pdfdrill mathpix`. "
                "Or hand-supply LaTeX with `pdfdrill visionocr --ingest <json>`.")

    if not lines_path.exists():
        from .ocr_lines import tools_available
        if tools_available()[0]:
            cmd_ocr(pdf)                      # build the prose layer first
        if not lines_path.exists():
            return (f"visionocr needs a prose lines.json for {pdf.name} — run "
                    f"`pdfdrill model` / `pdfdrill ocr` first.")

    rdir = sc.blob_dir / "visionocr"
    try:
        pngs = pdf_reading.rasterize(pdf, rdir, pages=pages, dpi=dpi)
    except Exception as e:  # noqa: BLE001
        return f"visionocr: could not render pages ({e})."
    if not pngs:
        return f"visionocr: no pages rendered for {pdf.name}."

    def _pageno(p: Path) -> int:
        m = _re.search(r"page-(\d+)", p.name)
        return int(m.group(1)) if m else 0

    # write an inspectable manifest (per-page image + dims) alongside the requests
    dims = {p.get("page"): (p.get("page_width"), p.get("page_height"))
            for p in json.loads(lines_path.read_text(encoding="utf-8")).get("pages", [])}
    manifest = []
    tasks, pairs = [], []
    for p in pngs:
        pn = _pageno(p)
        w, h = dims.get(pn, (None, None))
        manifest.append({"page": pn, "image_path": str(p),
                         "page_width": w, "page_height": h})
        t = D.LLMTask(kind="eq_ocr", prompt=openai_vision.EQ_OCR_PROMPT,
                      image_path=str(p), meta={"page": pn})
        pairs.append((pn, t))
        tasks.append(t)
    (sc.blob_dir / "visionocr_manifest.json").write_text(
        json.dumps({"pages": manifest}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    try:
        results, deferred = D.delegate_batch(tasks, drill_dir=sc.blob_dir,
                                             runtime=rt, timeout=240.0)
    except D.DelegateUnavailable as e:
        return str(e)
    if deferred is not None:
        return (f"visionocr deferred to the {rt.value} Claude agent: "
                f"{len(deferred.tasks)} page request(s) written (manifest: "
                f"{sc.blob_dir.name}/visionocr_manifest.json).\n" + _MATHPIX_TIP
                + "\n\n" + deferred.instruction)

    records, blank = [], 0
    for pn, t in sorted(pairs):
        res = results.get(t.task_id) or {}
        recs = res.get("records") or []
        if not recs:
            blank += 1
        for r in recs:
            if r.get("page") is None:
                r["page"] = pn                 # default to the task's page
            records.append(r)
    if not records:
        return (f"visionocr: the agent reported no display equations on any of "
                f"{len(pngs)} page(s) for {pdf.name} — nothing folded.")
    n_eq, n_num = _fold_eq_records_into_lines_json(lines_path, records, force=True)
    return _rebuild_and_clear(n_eq, n_num, rt.value)


def cmd_identifiers(pdf: Path) -> str:
    """Scan the FRONT MATTER for known identifiers + named-entity candidates.

    Front matter (title + copyright/imprint page) holds a book's ISBN/ISSN/DOI
    and its publisher/author. The window is scoped by the booktoc page offset
    (pages 1..offset) when known, else the first few pages — so the scan is
    cheap and precise. Runs the checksum-validated `features` extractors (ISBN/
    ISSN, DOI, German admin ids) + the arXiv id, plus an ALL-CAPS pass for NE
    candidates. Loads via the lazy DocGraph read path. Stores `identifiers` in
    the sidecar.
    """
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
    from . import booktoc, identifiers as idn, model_io
    from features import extract_isbn, extract_doi, extract_ids

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} — run `pdfdrill model` first."
    g = _fresh_docgraph(pdf, sc, model_path)

    # front-matter window from the booktoc offset (or default)
    raw = [e for t in g.of_type("Toc") for e in (t.props.get("entries") or [])]
    sections = [{"caption": sn.props.get("caption"), "page": sn.props.get("page")}
                for sn in g.of_type("Section")]
    offset, _conf, _ = booktoc.compute_offset(booktoc.parse_toc_entries(raw), sections)
    limit = idn.frontmatter_limit(offset)
    text = idn.collect_frontmatter_text(list(g), limit)

    ids: list[dict] = []
    for f in (extract_isbn.extract(text) + extract_doi.extract(text)
              + extract_ids.extract(text)):
        ids.append({"type": f.type, "value": f.value, "confidence": f.confidence})
    arxiv = sc.get_evidence("source_arxiv_id")
    if arxiv:
        ids.append({"type": "ARXIV", "value": arxiv, "confidence": 1.0})
    ne = idn.caps_entities(text)

    # Split author runs out of the caps candidates and resolve them against the
    # known author list (arXiv metadata) via match_entities (fuzzy SAME_AS).
    reference = sc.get_evidence("arxiv_authors") or g.meta.get("authors") or []
    cand_names: list[str] = []
    for run in ne:
        cand_names.extend(idn.split_author_names(run))
    authors = idn.resolve_authors(cand_names, reference) if reference else {
        "resolved": [], "confirmed": 0, "unresolved": cand_names}

    sc.set_evidence("identifiers", {"front_pages": limit, "ids": ids,
                                    "ne_candidates": ne, "authors": authors})
    sc.save()
    id_s = ("; ".join(f"{x['type']} {x['value']}" for x in ids) or "none")
    ne_s = (", ".join(ne[:8]) + (" …" if len(ne) > 8 else "")) if ne else "none"
    au_s = ""
    if reference:
        au_s = (f" Authors: {authors['confirmed']}/{len(reference)} confirmed on the "
                f"title page" + (f" ({len(authors['unresolved'])} unresolved candidate(s))"
                                 if authors['unresolved'] else "") + ".")
    return (f"Front matter (PDF pages 1–{limit}{' via booktoc offset' if offset>=3 else ''}): "
            f"identifiers — {id_s}. ALL-CAPS NE candidate(s): {ne_s}.{au_s} "
            f"Stored in the sidecar (identifiers).")


def cmd_booktoc(pdf: Path) -> str:
    """Greppable table of contents with printed→PDF page alignment.

    A book's printed TOC pages list each chapter/section with its PRINTED page
    number, which differs from the PDF page by the front-matter offset (title/
    copyright/TOC/preface). We recover that offset by matching TOC titles to the
    model's Section objects (which carry the real PDF page), then write
    `<bibkey>.toc.txt` — one line per entry an LLM can grep by name to read the
    PDF page directly, then `pdfdrill page`/`rasterize` it. Cheap read (loads
    via the lazy DocGraph; no full model build).
    """
    from . import booktoc, model_io

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} — run `pdfdrill model` first."
    g = _fresh_docgraph(pdf, sc, model_path)
    key = sc.get_evidence("bibkey") or g.meta.get("bibkey") or pdf.stem

    raw = []
    for t in g.of_type("Toc"):
        raw += (t.props.get("entries") or [])
    sections = [{"caption": sn.props.get("caption"), "page": sn.props.get("page")}
                for sn in g.of_type("Section")]
    entries = booktoc.parse_toc_entries(raw)
    if not entries:
        return (f"No parseable TOC entries for {pdf.name} (no Toc object or "
                f"unrecognized format). {len(sections)} Section(s) are available "
                f"via `pdfdrill status`.")
    offset, conf, pairs = booktoc.compute_offset(entries, sections)
    aligned = booktoc.align_toc(entries, sections)
    out = booktoc.render_toc(aligned, offset, key)
    toc_path = sc.blob_dir / f"{key}.toc.txt"
    toc_path.parent.mkdir(parents=True, exist_ok=True)
    toc_path.write_text(out, encoding="utf-8")
    sc.set_evidence("toc_offset", offset)
    sc.save()
    exact = sum(1 for a in aligned if a["exact"])
    return (f"Book TOC: {len(aligned)} entrie(s), printed→PDF offset {offset:+d} "
            f"(from {len(pairs)} title↔section matches, {conf:.0%} agree); "
            f"{exact} page-exact, {len(aligned)-exact} estimated → "
            f"{toc_path.relative_to(sc.pdf_path.parent)}. grep a chapter/section "
            f"name for its PDF page, then `pdfdrill page {pdf.name} <pdf_page>`.")


def cmd_gaps(pdf: Path) -> str:
    """Detect MISSING information — "cohomology as a linter".

    Where `semantic`'s compiler validates what IS there, this reports what is
    NOT: acronyms used but never expanded, greek symbols in math with no
    notation entry, novelty claims without a citation, in-text citations that
    resolve to no bibliography entry. Diagnostics with locations, never
    exceptions. Works on any built model (PDF, markdown, latexbook).
    """
    from docmodel.core import Document
    from semantic import gaps as _gaps

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not model_path.exists():
        return (f"No model for {pdf.name} — run `pdfdrill model` (PDF) or "
                f"`pdfdrill markdown` (.md) first.")
    doc = load_model(model_path)
    found = _gaps.detect_gaps(doc)
    sc.set_evidence("gaps", [{k: g[k] for k in ("kind", "severity", "name", "detail")}
                             for g in found])
    sc.save()
    return _gaps.report(found)


def cmd_markdown(md: Path, bibkey: str | None = None, force: bool = False) -> str:
    """Build a source-only model from a Markdown file (the yt2tw route).

    LLM-summary Markdown (Perplexity etc.): `#` title, `##`/`###` sections,
    \\(...\\)/\\[...\\] math, `\\cite{key}` in prose, a numbered References
    section, and a fenced ```bibtex appendix. The appendix is GOLD: its entries
    become Reference objects (citekey/author/year/title/entry_type + verbatim
    bibtex) and every \\cite links to them (`cites` alignments). No PDF, no
    MathPix, no OCR. Artifacts go in `<md>.drill/` next to the file; run
    `pdfdrill tiddlers/report/semantic` on it like any model.
    """
    from . import markdown_source as msrc

    md = Path(md)
    if not md.exists():
        return f"No such Markdown file: {md}"
    key = bibkey or md.stem
    drill = md.parent / f"{md.name}.drill"
    model_path = drill / "model.docmodel.json"

    if model_path.exists() and not force:
        from docmodel.core import Document
        doc = load_model(model_path)
        c = doc.meta.get("source_counts", {})
        return (f"Markdown model already built for {md.name} "
                f"({', '.join(f'{v} {k}' for k, v in c.items() if v)}). "
                f"--force rebuilds.")
    doc = msrc.build_markdown_model(md.read_text(encoding="utf-8"),
                                    bibkey=key, source_path=str(md))
    drill.mkdir(parents=True, exist_ok=True)
    save_model(model_path, doc)

    sc = Sidecar(md)
    sc.set_evidence("bibkey", key)
    sc.set_evidence("source_format", "markdown")
    sc.add_fact(MODEL_BUILT)
    sc.save()

    c = doc.meta.get("source_counts", {})
    linked = sum(1 for a in doc.alignments if a.kind == "cites")
    parts = ", ".join(f"{v} {k}" for k, v in c.items() if v)
    return (f"Built Markdown model for {md.name}: {parts}; {linked} citation(s) "
            f"linked to references"
            + (" (gold BibTeX appendix)" if any(
                o.props.get("added_by") == "markdown_bibtex"
                for o in doc.objects.values() if o.type == "Reference") else "")
            + f". bibkey='{key}'. Stored at {drill.name}/model.docmodel.json. "
              f"Next: pdfdrill tiddlers/report/semantic {md.name}.")


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
        doc = load_model(model_path)
    else:
        doc = ls.build_source_model(str(tex), bibkey=key)
        drill.mkdir(parents=True, exist_ok=True)
        save_model(model_path, doc)

    # Mark the source model BUILT on the sidecar so projectors (tiddlers/llmtext/
    # svg) consume it directly instead of force-rebuilding via MathPix/OCR — which
    # would clobber the keyless source model (the mass-run collision). A source
    # model has no lines.json, so `_stale_or_absent` keys on this fact.
    sc = Sidecar(tex)
    sc.set_evidence("bibkey", key)
    if not sc.has(MODEL_BUILT):
        sc.add_fact(MODEL_BUILT)
    sc.save()

    # Render TikZ/tables to SVG (cmd_svg mutates the saved model in place),
    # then reload so the report embeds the freshly-rendered SVGs.
    svg_note = ""
    # Count only true graphics (carry latex_code); code-listing diagrams have
    # latex_code="" so they're correctly excluded from the render ratio.
    n_graphics = sum(1 for o in doc.objects.values()
                     if o.type in ("Diagram", "Table") and o.props.get("latex_code"))
    if not no_svg and n_graphics:
        if tools_available():
            cmd_svg(tex, force=force)
            doc = load_model(model_path)
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
    alg_note = (f" {c['algorithms']} algorithms ({c.get('algorithm_steps', 0)} steps);"
                if c.get("algorithms") else "")
    return (f"LaTeX source model for {tex.name}: {c.get('sections', 0)} sections, "
            f"{c.get('equations', 0)} display equations,{alg_note} "
            f"{c.get('macros', 0)} macros "
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
    # The extracted LaTeX-source folder (so a local \usepackage{siamproceedings}/
    # mystyle resolves), else the document's own folder.
    resource_dir = doc.meta.get("latex_source_dir") or str(target.parent)
    if not (resource_dir and Path(resource_dir).is_dir()):
        resource_dir = str(target.parent)
    targets = [o for o in doc.objects.values()
               if o.type in ("Diagram", "Table") and o.props.get("latex_code")]
    todo = [o for o in targets if force or not o.props.get("svg")]
    if limit is not None:
        todo = todo[:limit]
    # graphics already rendered in a prior run (skipped unless --force) — report
    # them so "Rendered 0" isn't mistaken for "nothing is rendered".
    already = 0 if force else sum(1 for o in targets if o.props.get("svg"))

    # Persist the EXACT standalone .tex compiled for each graphic (+ the latex
    # log on failure) so it can be opened in a LaTeX editor (Gummi) and debugged.
    bibkey = doc.meta.get("bibkey") or target.stem
    debug_dir = (sc.blob_dir if sc is not None else target.parent / f"{target.stem}.drill") / "svg" / "tex"

    done = errors = skipped = 0
    for i, o in enumerate(todo):
        if force:
            o.realizations = [r for r in o.realizations if r.provenance != "dvisvgm"]
            o.props.pop("svg", None)
        res = compile_to_svg(o.props["latex_code"], preamble=preamble,
                             resource_dir=resource_dir)
        if res.get("src"):
            debug_dir.mkdir(parents=True, exist_ok=True)
            name = f"{bibkey}_{o.type}_{i+1:02d}"
            (debug_dir / f"{name}.tex").write_text(res["src"], encoding="utf-8")
            if not res["ok"] and res.get("log"):
                (debug_dir / f"{name}.log").write_text(res["log"], encoding="utf-8")
        if res["ok"]:
            o.props["svg"] = res["svg"]
            if res["ratio"]:
                o.props["svg_ratio"] = res["ratio"]
            o.add_realization(Realization(stream="svg", role="svg_render",
                                          provenance="dvisvgm",
                                          props={"ratio": res["ratio"]}))
            done += 1
        elif res.get("skipped"):
            # Not a LaTeX graphic (e.g. a code listing) — never a render failure.
            o.props["svg_skipped"] = res["error"]
            skipped += 1
        else:
            o.props["svg_error"] = res["error"]
            errors += 1

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    if sc is not None:
        sc.set_evidence("svg_rendered", done)
        sc.set_evidence("svg_errors", errors)
        sc.set_evidence("svg_skipped", skipped)
        sc.save()
    total_svg = already + done
    return (f"Rendered {done} new TikZ/table SVG(s)"
            + (f", {already} already rendered" if already else "")
            + (f", {errors} failed" if errors else "")
            + (f", {skipped} skipped (not a LaTeX graphic, e.g. code listing)" if skipped else "")
            + f" of {len(targets)} graphic object(s) "
            f"({total_svg} now have an SVG). SVGs stored on the model "
            f"(props['svg']); `pdfdrill report {target.name}` embeds them inline."
            + (f" The exact compiled .tex (+ latex .log for any failure) is in "
               f"{_display_path(debug_dir, sc.pdf_path.parent) if sc is not None else debug_dir}/ "
               f"— open in a LaTeX editor (Gummi) to debug." if todo else "")
            + (f" Re-run with --force to retry the {errors} that failed." if errors else ""))


def cmd_distill(pdf: Path, embed: bool = False) -> str:
    """Emit a distill-structured single-file reading view (`<bibkey>.distill.html`).

    The document skeleton of an Anthropic/Distill v2 article (named-column grid,
    runtime TOC, late-bound `??` figure/eq references, hover cite/footnote
    popovers), rebuilt from the docmodel — self-contained, no template JS, KaTeX
    from the house data-latex pattern. `--embed` base64-inlines every CDN crop.
    Auto-chains `model`. Citation popovers light up when `bibliography`/`bibsource`
    has run (else the `[n]` chips render without bodies — graceful)."""
    from docmodel.core import Document
    from docops.base import OperatorConfig
    from docops.projectors.distill_reader import DistillReaderProjector

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))
    proj = DistillReaderProjector(OperatorConfig(
        op="projector", classname="DistillReaderProjector", params={"embed": embed}))
    result = proj.project(doc)
    bibkey = _safe_bibkey(doc.meta.get("bibkey") or pdf.stem)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    out_path = sc.blob_dir / f"{bibkey}.distill.html"
    out_path.write_text(result, encoding="utf-8")
    sc.set_evidence("distill_path", str(out_path.relative_to(sc.pdf_path.parent)))
    sc.save()
    rel = _artref(sc, out_path)
    blocks = proj.counters.get("blocks", 0)
    return (f"Distill reading view: {blocks} blocks ({len(result) // 1024} KB, "
            f"self-contained) — named-column layout, runtime TOC, late-bound figure "
            f"refs, hover citations. Open {rel} in a browser.")


def cmd_report(pdf: Path, force: bool = False, embed: bool = False,
               scale: float = 1.0) -> str:
    """Emit a full inline+display math report (formula-report.html).

    Lists every inline Formula (LaTeX + KaTeX) and every display Equation
    (+ MathPix CDN image + equation number). Auto-chains `model`. `scale` sets
    the KaTeX-to-CDN-image height multiplier (1.0 = same height, 2.0 = 200%).
    """
    from docmodel.core import Document
    from docops.base import OperatorConfig
    from docops.projectors.formula_report import FormulaReportProjector

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    proj = FormulaReportProjector(
        OperatorConfig(op="projector", classname="FormulaReportProjector",
                   params={"embed": embed, "katex_scale": scale}))
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
    rel = _artref(sc, out_path)
    msg = (f"Formula report: {inline} inline formulas + {eqs} display equations "
           f"(LaTeX | KaTeX | image). Open {rel} in a browser.")
    # If the report is EMPTY of math, don't leave the user guessing — say WHY and
    # WHAT to do. A keyless (tesseract) build types no equations; the gate sets
    # NEEDS_VISION_OCR. Steer to the right recovery, arXiv-gold first.
    if inline == 0 and eqs == 0:
        from . import mathqc
        bearing, why = (True, "math-bearing") if sc.has(NEEDS_VISION_OCR) \
            else mathqc.is_math_bearing(pdf, sc)
        if bearing:
            aid = _arxiv_id_for(pdf, sc)
            routes = []
            if aid:
                routes.append(f"`pdfdrill injectlatex {pdf.name}` (FREE: the author's gold "
                              f"arXiv equations → real Equation objects)")
            routes.append(f"`pdfdrill visionocr {pdf.name}` (keyless: an LLM reads each page)")
            routes.append(f"`pdfdrill mathpix {pdf.name} --force` (paid MathPix)")
            msg += ("\n⚠ 0 formulas because the model was built from keyless "
                    f"tesseract OCR, which cannot type equations ({why}). Recover them with:\n  - "
                    + "\n  - ".join(routes) + "\nthen re-run `report`.")
    return msg


def _inspect_pages_dir(pdf: Path, sc: "Sidecar", pages: str | None,
                       src_dpi: int) -> tuple[Path | None, int]:
    """Rasterize page(s) into <drill>/inspect/pages as p{N}.png (the naming
    docinspect reads), reusing any already present. Returns (dir, src_dpi) or
    (None, src_dpi) when Ghostscript is unavailable — the inspector then renders
    boxes-only (still a working tree/inspector). Never raises."""
    import os
    from . import pdf_reading
    out = sc.blob_dir / "inspect" / "pages"
    out.mkdir(parents=True, exist_ok=True)
    page_list = pdf_reading.parse_pages(pages, getattr(sc, "page_count", None) or None)
    try:
        imgs = pdf_reading.rasterize(pdf, out, pages=page_list, dpi=src_dpi)
    except RuntimeError:
        return None, src_dpi                       # gs missing → boxes-only
    # rasterize writes page-<NNNN>.png; docinspect wants p{N}.png — hardlink
    # (no extra bytes; copy fallback across filesystems).
    import re as _re
    for img in imgs:
        m = _re.search(r"page-(\d+)\.png$", img.name)
        if not m:
            continue
        target = out / f"p{int(m.group(1))}.png"
        if target.exists():
            continue
        try:
            os.link(img, target)
        except OSError:
            import shutil as _sh
            _sh.copyfile(img, target)
    return out, src_dpi


def cmd_inspect(pdf: Path, pages: str | None = None, embed: bool = True,
                dpi: int = 120, src_dpi: int = 400, images: bool = True,
                force: bool = False) -> str:
    """Build a DevTools-style docmodel inspector HTML (`<bibkey>.inspect.html`).

    A second lens on the same model the OpenSeadragon viewer shows: every
    DocObject is drawn as a hover/click box on the rendered page AND as a row in
    a DOM-like ELEMENTS tree, with an INSPECTOR pane for the selected element
    (type / page / region / LaTeX-via-KaTeX / props / realizations / alignments)
    and a reading-order REFLOW tab. Self-contained by default (`--embed` inlines
    downscaled page JPEGs — offline, no server). `--no-images` (or absent gs)
    renders boxes-only. Auto-chains `model`. Clickable in drillui's Outputs.
    """
    from . import docinspect

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    pages_dir = None
    if images and embed:
        pages_dir, src_dpi = _inspect_pages_dir(pdf, sc, pages, src_dpi)
    # --pages restricts the whole inspector (elements + embedded page images), not
    # just which pages get rasterized — else a big doc always emits the full (14 MB)
    # HTML that chokes a reverse-proxy/drillui load.
    page_filter = None
    if pages and str(pages).lower() != "all":
        from . import pdf_reading
        pl = pdf_reading.parse_pages(pages, getattr(sc, "page_count", None) or None)
        page_filter = set(pl) if pl else None

    with open(model_path, "r", encoding="utf-8") as f:
        bibkey = (json.load(f).get("meta", {}) or {}).get("bibkey") or pdf.stem
    tiddlers = sc.blob_dir / f"{bibkey}.tiddlers.json"
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    out_path = sc.blob_dir / f"{bibkey}.inspect.html"
    try:
        html_doc, n_pages, n_el, mode = docinspect.build_from_paths(
            str(model_path), out=str(out_path),
            tiddlers=str(tiddlers) if tiddlers.exists() else None,
            pages_dir=str(pages_dir) if pages_dir else None,
            embed=embed, embed_dpi=dpi, src_dpi=src_dpi, title=bibkey,
            page_filter=page_filter)
    except Exception as e:                          # noqa: BLE001
        return f"inspect failed for {pdf.name}: {e}"

    sc.set_evidence("inspect_path", str(out_path.relative_to(sc.pdf_path.parent)))
    sc.save()
    rel = _artref(sc, out_path)
    # A LaTeX-source model has no page geometry, so nothing can be boxed. Keep it
    # SHORT and point at the one fix (rebuild with the born-digital / MathPix route,
    # which now carries geometry) — no wall of text.
    if n_pages == 0:
        return (f"{pdf.name}: this model was built from LaTeX source (no page "
                f"geometry), so the page-box view is empty — the element tree is "
                f"in {rel}. For boxes, rebuild with geometry: `pdfdrill model "
                f"{pdf.name} --force`.")
    note = "" if mode != "embed" or pages_dir else " (boxes-only — no page images)"
    return (f"Docmodel inspector: {n_el} elements over {n_pages} page(s){note}. "
            f"Open {rel} in a browser (hover the tree to highlight boxes; click "
            f"an element for its full record).")


def _deliver_region_crop(pdf: Path, sc: "Sidecar", page: int,
                         rect: tuple, ppi: int = 200) -> Path:
    """Rasterize `page` and crop the pixel `rect` (x0,y0,x1,y1 at `ppi`), saving
    the crop PNG into the sidecar. Delivers the image regardless of any OCR."""
    from . import pdf_reading
    from PIL import Image
    out_dir = sc.blob_dir / "snip"
    imgs = pdf_reading.rasterize(pdf, out_dir, pages=[page], dpi=ppi)
    if not imgs:
        raise RuntimeError(f"could not rasterize page {page}")
    x0, y0, x1, y1 = (int(v) for v in rect)
    crop = Image.open(imgs[0]).convert("RGB").crop((x0, y0, x1, y1))
    crop_path = out_dir / f"snip_p{page}_{x0}-{y0}-{x1}-{y1}.png"
    crop.save(crop_path)
    return crop_path


def cmd_snip(pdf: Path, limit: int | None = None, force: bool = False,
             image: str | None = None, page: int | None = None,
             rect: tuple | None = None, ppi: int = 200,
             provider: str | None = None) -> str:
    """OCR image crops via MathPix Snip (/v3/text) — or Gemma-4 (`--gemma`).

    Three modes — the state machine should deliver ANY special image, not just
    equations:
      * `--image <path|url|data:>` → OCR exactly that image.
      * `--page N --rect x0,y0,x1,y1` → rasterize that region, DELIVER the crop
        PNG (Read it to view), and OCR it. The crop is delivered even when OCR is
        unavailable (no key / blocked) — deliver what we can.
      * neither → the default: OCR every equation's CDN crop as a competing
        'snip'/'gemma' provenance attached to the model (auto-chains `model`;
        idempotent per equation unless --force; `--limit N` caps requests).

    `provider`: None (default) → THE STATE MACHINE DECIDES via
    `vision_router.route("equation_ocr")` — MathPix when its keys are present
    (native, promptless), else the cheap Gemma-4 vision route on Novita.
    Explicit "mathpix" / "gemma" (`--gemma`, `--provider`) remain as overrides.
    Both return the same record shape, attached with `provenance=<provider>`
    so `compare` grows a column for whichever served.
    """
    from docmodel.core import Document, Realization, Region
    from .net import NetworkBlocked

    if not provider:                            # the router decides, not the user
        from . import vision_router
        routed, reason = vision_router.route("equation_ocr")
        if routed in (None, "delegate", "openai"):
            # snip's two wired providers; anything else → the classic default
            # (mathpix), whose own key error explains what to set.
            provider = "mathpix" if routed is None else "mathpix"
        else:
            provider = routed
    provider = provider.lower()
    if provider == "gemma":
        from .gemma_client import snip_result
        prov_name = "gemma"
    else:
        from .mathpix_snip import snip_result
        prov_name = "snip"

    sc = Sidecar(pdf)

    # --- special-image delivery (explicit image, or a page region) ----------
    if image or (page is not None and rect is not None):
        delivered = None
        if image is None:                       # region → deliver the crop first
            sc.blob_dir.mkdir(parents=True, exist_ok=True)
            try:
                delivered = _deliver_region_crop(pdf, sc, page, rect, ppi)
            except Exception as e:
                return f"Could not deliver page {page} rect {rect}: {e}"
            target = str(delivered)
        else:
            target = image
            if Path(image).exists():
                delivered = Path(image)
        out = [f"Special image: {target}"]
        if delivered is not None:
            rel = (str(delivered.relative_to(sc.pdf_path.parent))
                   if str(delivered).startswith(str(sc.pdf_path.parent)) else str(delivered))
            out.append(f"  crop delivered → {rel}  (Read it to view; or `pdfdrill "
                       f"vision` for a GPT-4o read)")
        try:
            res = snip_result(target)
        except NetworkBlocked as nb:
            out.append(f"  OCR unavailable: {nb}")
            return "\n".join(out)
        except Exception as e:
            out.append(f"  OCR unavailable ({e}) — the crop above is still delivered.")
            return "\n".join(out)
        latex, text, conf = res.get("latex", ""), res.get("text", ""), res.get("confidence")
        if latex:
            out.append(f"  latex: {latex}")
        if text and text != latex:
            out.append(f"  text:  {text}")
        if conf is not None:
            out.append(f"  confidence: {conf:.3f}")
        sc.set_evidence("snip_special", {"image": target, "crop": str(delivered) if delivered else None,
                                         "latex": latex, "text": text, "confidence": conf})
        sc.save()
        return "\n".join(out)
    model_path = _model_path(sc)
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
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
        has_snip = any(r.role == "latex_candidate" and r.provenance == prov_name
                       for r in e.realizations)
        if has_snip and not force:
            continue
        todo.append(e)
    if limit is not None:
        todo = todo[:limit]

    t0 = time.monotonic()
    done = errors = 0
    confs: list[float] = []
    from .net import NetworkBlocked
    for e in todo:
        try:
            res = snip_result(e.props["cdn_url"])
        except NetworkBlocked as nb:  # blocked host: abort, don't hammer N crops
            return str(nb)
        except Exception:  # noqa: BLE001 — one bad crop shouldn't abort the batch
            errors += 1
            continue
        if force:
            e.realizations = [r for r in e.realizations
                              if not (r.role == "latex_candidate" and r.provenance == prov_name)]
        region = None
        lines = res.get("lines") or []
        if lines and lines[0].get("cnt"):
            region = Region.from_cnt(lines[0]["cnt"], page=e.props.get("page"))
        e.add_realization(Realization(
            stream=prov_name, role="latex_candidate", provenance=prov_name,
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

    _via = "the Gemma-4 vision model (Novita.ai)" if prov_name == "gemma" else "MathPix /v3/text"
    msg = f"Snipped {done} equation crop(s) via {_via}"
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
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
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
                    "bibkey": doc.meta.get("bibkey", pdf.stem),
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
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    existing = [o for o in doc.objects.values() if o.type in ("Algorithm", "AlgorithmStep")]
    if existing and not force:
        return _format_algorithms(doc)
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
            "bibkey": doc.meta.get("bibkey", pdf.stem)})
        step_anchors = [idmap[s["id"]] for s in a["steps"] if s["id"] in idmap]
        span = ([idmap[a["caption_id"]]] if a["caption_id"] in idmap else []) + step_anchors
        if span:
            alg.add_realization(Realization(stream="mathpix_lines",
                                            start=span[0], end=span[-1], role="surface"))
        doc.add(alg)
        created += 1
        for s in a["steps"]:
            st = DocObject(type="AlgorithmStep",
                           props={"text": s["text"], "depth": s["depth"],
                                  "bibkey": doc.meta.get("bibkey", pdf.stem)},
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
    return _format_algorithms(doc)


def _format_algorithms(doc) -> str:
    """Summarise the Algorithm blocks FROM THE MODEL OBJECTS (the source of
    truth) — works for both the MathPix-pseudocode path and the LaTeX-source
    path (`build_source_model`'s `extract_algorithms`, incl. algorithm2e
    `\\begin{algorithm}` floats). The sidecar evidence is only set by the
    MathPix path, so reading it reported 0 on a source-built model."""
    algos = [o for o in doc.objects.values() if o.type == "Algorithm"]
    steps = [o for o in doc.objects.values() if o.type == "AlgorithmStep"]
    if not algos and not steps:
        return ("No algorithm blocks found (no MathPix `pseudocode` lines and no "
                "`\\begin{algorithm}`/`algorithmic` in the LaTeX source).")
    max_depth = max((int(s.props.get("depth") or 0) for s in steps), default=0)
    titles = [a.props.get("title") for a in algos if (a.props.get("title") or "").strip()]
    extra = f" — {', '.join(titles)}" if titles else ""
    return (
        f"{len(algos)} Algorithm block(s) with {len(steps)} steps "
        f"(max indent depth {max_depth}){extra}. Each Algorithm carries "
        f"number/title/page; steps carry text + depth (if/else/end nesting)."
    )


def _xelatex_compile(main_tex: Path) -> "tuple[bool, str]":
    """Compile `main_tex` with **xelatex** (Unicode-native — MathPix LaTeX emits
    raw `≥ ✓ → ℃` that pdflatex/inputenc cannot map). Returns (ok, note)."""
    import shutil
    import subprocess
    if not shutil.which("xelatex"):
        return False, "xelatex not on PATH (install texlive-xetex)"
    try:
        subprocess.run(["xelatex", "-interaction=nonstopmode", "-halt-on-error",
                        main_tex.name], cwd=str(main_tex.parent),
                       capture_output=True, timeout=180)
    except Exception as exc:                              # noqa: BLE001
        return False, f"xelatex failed: {type(exc).__name__}"
    pdf_out = main_tex.with_suffix(".pdf")
    return (pdf_out.exists(), "" if pdf_out.exists()
            else "xelatex produced no PDF (see the .log in the env dir)")


def cmd_latex(pdf: Path, force: bool = False, compile: bool = False,
              dump_stages: bool = False) -> str:
    """PROJECT the drilled document to a self-contained, COMPILABLE LaTeX
    ENVIRONMENT folder — the LaTeX analog of `md`. OUTPUT direction.

    A PROJECTION over the docmodel — exactly like `md` projects Markdown and
    `tiddlers` projects TiddlyWiki. It reads the unified `Document`; the SOURCE
    that built that Document (MathPix / arXiv LaTeX / tesseract / textscan) is
    IRRELEVANT, because the docmodel is the canonical IR. The `LaTeXProjector`
    walks the objects and the inspectable `latex_pipeline` resolves transclusion
    markers (`{{id||FO}}` → `$…$` by array lookup), emits `\\cite`, and builds the
    bibliography from Reference objects.

    Writes `<drill>/latex/<bibkey>.tex` (+ a `.bib` from References carrying
    BibTeX). **Compile with `xelatex`** (not pdflatex): the model can carry raw
    Unicode (`≥ ✓ → ℃`) that inputenc/pdflatex reject. `--compile` runs it;
    `--dump-stages` writes the generation stages for inspection.

    Distinct from `injectlatex` (pull an author/MathPix source INTO the model as
    provenance). For enriched LaTeX (glossary/index, ORKG) see `stex`/`scikgtex`.
    """
    from .sidecar import Sidecar
    sc = Sidecar(pdf)
    key = resolve_bibkey(pdf, None, sc)
    env_dir = sc.blob_dir / "latex"

    # Load/build the docmodel — the ONE source of the projection (source-agnostic).
    model_path = _model_path(sc)
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
        cmd_model(pdf)
        model_path = _model_path(sc)
    doc = load_model(model_path) if model_path.exists() else None
    if doc is None:
        return ("No docmodel to project. Build one first (`pdfdrill model`), "
                "then re-run `pdfdrill latex`.")

    from docops.base import OperatorConfig
    from docops.projectors.latex import LaTeXProjector
    from docops.projectors import latex_pipeline as _pipe
    tex = LaTeXProjector(
        OperatorConfig(op="projector", classname="LaTeXProjector")).project(doc)
    env_dir.mkdir(parents=True, exist_ok=True)
    main_tex = env_dir / f"{key}.tex"
    main_tex.write_text(tex, encoding="utf-8")

    # inspectable side-artifacts: a real .bib from References + the stage dumps
    bib_db = _pipe.bib_database(doc)
    if bib_db.strip():
        (env_dir / f"{key}.bib").write_text(bib_db, encoding="utf-8")
    if dump_stages:
        _pipe.dump_stages(_pipe.run_stages(doc), env_dir / "stages")

    n_eq = len(doc.objects_of_type("Equation")) + len(doc.objects_of_type("Formula"))
    n_ref = len(doc.objects_of_type("Reference"))
    lines = [
        f"Projected the docmodel → LaTeX → {_artref(sc, main_tex)}  "
        f"({len(tex.split())} words, {n_eq} math object(s), {n_ref} reference(s)).",
        f"  compile : cd {_artref(sc, env_dir)} && xelatex {main_tex.name}",
        f"  NOTE: use xelatex (or lualatex), NOT pdflatex — the model can carry "
        f"raw Unicode (≥ ✓ → ℃) that inputenc/pdflatex reject.",
    ]
    if dump_stages:
        lines.append(f"  stages  : {_artref(sc, env_dir / 'stages')}/  "
                     f"(transclusion lookup / citations / bibliography)")
    if compile:
        ok, note = _xelatex_compile(main_tex)
        pdf_out = main_tex.with_suffix(".pdf")
        lines.append(f"  compiled: {'✓ ' + _artref(sc, pdf_out) if ok else '✗ ' + note}")
    lines.append("  (`injectlatex` pulls a source INTO the model; `stex`/`scikgtex` "
                 "for enriched LaTeX.)")
    return "\n".join(lines)


def cmd_injectlatex(pdf: Path, tex: str | None = None, force: bool = False) -> str:
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
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    # Locate the source. For an arXiv doc PREFER the author's GOLD e-print
    # (.tgz, local or downloaded) over the MathPix <stem>.tex.zip — the .tex.zip
    # is MathPix's OWN reconstruction (redundant with the mathpix column), while
    # the e-print is the author's real LaTeX. Order: explicit --tex > arXiv e-print
    # > local <stem>.tex > MathPix <stem>.tex.zip.
    src = Path(tex) if tex else None
    aid = None if tex else _arxiv_id_for(pdf, sc)
    if src is None and aid:
        for ext in (".tgz", ".tar.gz"):
            cand = pdf.parent / f"{pdf.stem}{ext}"
            if cand.exists():
                src = cand
                break
        if src is None:
            try:
                from . import sources
                src = sources.download_arxiv_source(aid, pdf.parent)
            except Exception:
                src = None                       # fall through to a local .tex/.tex.zip
    if src is None:
        for ext in (".tex", ".tex.zip", ".tgz", ".tar.gz"):
            cand = pdf.parent / f"{pdf.stem}{ext}"
            if cand.exists():
                src = cand
                break
    if src is None or not src.exists():
        return (f"No LaTeX source found for {pdf.name} "
                f"(looked for {pdf.stem}.tex / .tex.zip / .tgz / .tar.gz). "
                f"Run `pdfdrill mathpix {pdf.name}` first (it downloads the MathPix "
                f"{pdf.stem}.tex.zip), or pass --tex <path>.")

    full, main = ls.read_source(str(src))
    if not full:
        return f"Could not read LaTeX source from {src.name}."
    preamble, body = ls.split_preamble(full)
    macros = ls.extract_macros(preamble)
    src_eqs = ls.extract_display_equations(body)

    # Persist the source folder so `pdfdrill svg` can resolve the project's local
    # style files (e.g. siamproceedings.sty bundled in the e-print .tgz). A
    # tarball is extracted to <pdf>.drill/texsrc/; a loose .tex uses its folder.
    import tarfile as _tarfile
    import zipfile as _zipfile
    if _tarfile.is_tarfile(str(src)):
        texsrc = sc.blob_dir / "texsrc"
        texsrc.mkdir(parents=True, exist_ok=True)
        with _tarfile.open(str(src)) as tf:
            tf.extractall(texsrc, filter="data")
        source_dir = str(texsrc)
    elif _zipfile.is_zipfile(str(src)):            # MathPix <stem>.tex.zip
        texsrc = sc.blob_dir / "texsrc"
        texsrc.mkdir(parents=True, exist_ok=True)
        with _zipfile.ZipFile(str(src)) as zf:
            zf.extractall(texsrc)
        source_dir = str(texsrc)
    else:
        source_dir = str(src.parent)

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    if force:
        for o in list(doc.objects.values()):
            if o.type == "Equation":
                o.realizations = [r for r in o.realizations
                                  if not (r.role == "latex_candidate" and r.provenance == "tex")]
        # also drop equations we previously CREATED from source (re-created below)
        doc.objects = {k: v for k, v in doc.objects.items()
                       if not (v.type == "Equation" and v.props.get("added_by") == "latex")}
        doc.meta.pop("latex_preamble", None)

    # Persist the two preamble forms on the document for the later SVG step.
    doc.meta["latex_preamble"] = {
        "main": main,
        "original": preamble.strip(),
        "standalone": ls.standalone_preamble(preamble),
        "num_macros": len(macros),
    }
    doc.meta["latex_source_dir"] = source_dir   # for svg's TEXINPUTS (local .sty)

    eqs = [o for o in doc.objects.values() if o.type == "Equation"]
    # Precompute normalized OCR latex per equation (skip ones WE created from
    # source, so a re-run doesn't overlay gold-onto-gold).
    eq_norm = [(o, normalize_latex(o.props.get("latex", ""))) for o in eqs
               if o.props.get("added_by") != "latex"]
    scaffold = len(eq_norm)   # genuine OCR/MathPix equation slots to overlay onto

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

    # KEYLESS-BASE FIX: a tesseract/OCR base model has NO equation slots to
    # overlay onto, so every gold equation is "unmatched" and the report stays
    # empty. When there's no scaffold, the author's display equations ARE the
    # document's equations — create them as first-class Equation objects so
    # `report`/`compare`/tiddlers render them. (Skipped when a real MathPix
    # scaffold exists, to avoid duplicating its equations.)
    # IDEMPOTENCY: if a prior `latex` run already CREATED gold equations (they
    # carry added_by="latex"), do NOT create them again — else running latex
    # twice (e.g. cmd_model's auto-overlay, then an explicit `pdfdrill latex`)
    # doubles every equation (the EQ0001–14 + EQ0015–28 byte-identical duplicate
    # bug). `--force` drops the prior latex equations above, so it re-creates.
    already_created = any(o.type == "Equation" and o.props.get("added_by") == "latex"
                          for o in doc.objects.values())
    created = 0
    if scaffold == 0 and src_eqs and not already_created:
        from docmodel.core import DocObject
        base_fi = max((o.props.get("flow_index", 0) for o in doc.objects.values()),
                      default=0)
        bk = doc.meta.get("bibkey", "DOC")
        for i, se in enumerate(src_eqs, 1):
            original = se["latex"]
            expanded = ls.expand_macros(original, macros)
            if not normalize_latex(expanded):
                continue
            doc.add(DocObject(type="Equation", props={
                "latex": expanded, "latex_raw": original, "latex_original": original,
                "refnum": se.get("label") or "", "env": se["env"],
                "numbered": se.get("numbered"), "bibkey": bk,
                "added_by": "latex", "provenance": "tex",
                "flow_index": base_fi + i, "page": None, "region": None,
                "cdn_url": "",
            }))
            created += 1

    # Ingest the source's TikZ/tables (tikzcd commutative diagrams, tabular, …)
    # as Diagram/Table objects with latex_code — so `pdfdrill svg` can render
    # them. The base OCR/MathPix model rarely has these as graphic objects.
    n_graphics = ingest_source_graphics(
        doc, body, macros, doc.meta.get("bibkey", "DOC"), force)

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    # If we created equations, clear the keyless math-missing flag — the gold
    # source filled the gap.
    if created:
        sc.remove_fact(NEEDS_VISION_OCR)
    sc.set_evidence("latex_source", src.name)
    sc.set_evidence("latex_macros", len(macros))
    sc.set_evidence("latex_src_equations", len(src_eqs))
    sc.set_evidence("latex_attached", attached)
    sc.set_evidence("latex_created", created)
    sc.set_evidence("latex_graphics", n_graphics)
    prev = ",".join(sorted(sc.facts - {LATEX_INGESTED})) or "INIT"
    # Proof: the gold LaTeX source this enrichment was ingested from (Phase B).
    sc.mark(LATEX_INGESTED, produced_by="latex", inputs=[src],
            params={"created": created, "attached": attached})
    sc.log_transition("latex", prev, LATEX_INGESTED,
                      detail=f"{attached}/{len(src_eqs)} eqs matched, {created} created, "
                             f"{n_graphics} graphics, {len(macros)} macros")
    sc.save()
    gfx = (f" Added {n_graphics} TikZ/table graphic object(s) — run "
           f"`pdfdrill svg {pdf.name}` to render them to SVG." if n_graphics else "")
    if created:
        # the keyless case: gold equations became first-class objects
        return (f"Ingested LaTeX source {src.name}: {len(src_eqs)} display equations, "
                f"{len(macros)} preamble macros. The base model had no equation "
                f"slots (keyless OCR), so CREATED {created} Equation object(s) from "
                f"the author's gold LaTeX.{gfx} Run `pdfdrill report {pdf.name}` — "
                f"the equations now render.")
    return (f"Ingested LaTeX source {src.name}: {len(src_eqs)} display equations, "
            f"{len(macros)} preamble macros. Attached {attached} as `tex` "
            f"provenance to MathPix equations ({unmatched} source eqs unmatched). "
            f"Kept original+expanded LaTeX; preamble stored for the SVG step.{gfx} "
            f"Run `pdfdrill compare {pdf.name}` to see the tex column.")


def _locate_latex_source(pdf: Path, sc: "Sidecar", tex: str | None):
    """Find the LaTeX source for `pdf` (explicit --tex, a local .tex/.tex.zip/
    .tgz/.tar.gz sibling, else the arXiv e-print). Returns (path, err_message):
    exactly one is non-None."""
    src = Path(tex) if tex else None
    if src is None:
        for ext in (".tex", ".tex.zip", ".tgz", ".tar.gz"):
            cand = pdf.parent / f"{pdf.stem}{ext}"
            if cand.exists():
                src = cand
                break
    if src is None:
        aid = _arxiv_id_for(pdf, sc)
        if aid:
            try:
                from . import sources
                src = sources.download_arxiv_source(aid, pdf.parent)
            except Exception as e:
                return None, (f"arXiv source download failed for arXiv:{aid}: {e} "
                              f"(pass --tex <path> if you have the .tex/.tgz locally).")
    if src is None or not src.exists():
        return None, (f"No LaTeX source found for {pdf.name} "
                      f"(looked for {pdf.stem}.tex / .tex.zip / .tgz / .tar.gz). "
                      f"Run `pdfdrill mathpix {pdf.name}` (downloads the MathPix "
                      f"{pdf.stem}.tex.zip), or pass --tex <path>.")
    return src, None


def cmd_merge(pdf: Path, tex: str | None = None) -> str:
    """Three-source prose merge — **LaTeX content onto MathPix geometry**.

    The MathPix model is the LAYOUT truth: its Paragraph objects fix the paragraph
    boundaries + each one's `region`. The author's gold LaTeX prose is the CONTENT
    truth: it is re-partitioned across those boundaries by word-alignment, and each
    paragraph's `text` is REPLACED by its aligned LaTeX span (LaTeX always wins),
    the MathPix `region` kept, the original OCR preserved under `text_source`.

    Fixes the source-build's coarse paragraphs (a 3000-char LaTeX block that
    MathPix visually splits into 3-4) WITHOUT losing MathPix geometry, and lifts
    OCR errors out of the prose. A MathPix paragraph with no LaTeX counterpart
    (a caption OCR'd as prose) is left untouched. Requires a MathPix model
    (paragraphs+regions) AND a LaTeX source. Auto-chains `model`.
    """
    from .model_io import load_model, save_model
    from . import merge_latex as ML
    from . import latex_source as ls

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} — run `pdfdrill model` first."

    doc = load_model(model_path)
    # The merge needs a LAYOUT skeleton (Paragraph objects with geometry) whose
    # prose is imperfect — MathPix OCR, or a born-digital pdfminer/pdfplumber char
    # layer (garbled by two-column interleaving + the arXiv margin watermark), or
    # tesseract OCR. It does NOT apply to a source-BUILT model, whose prose already
    # IS the gold LaTeX (there's nothing to correct).
    source = doc.meta.get("source")
    if source == "latex":
        return (f"{pdf.name}: this model was built FROM the LaTeX source, so its "
                f"prose is already the gold text — nothing to merge onto. (merge "
                f"corrects an OCR/pdfminer layout skeleton with the gold prose.)")
    _SRC_LABEL = {"mathpix": "MathPix", "pdfminer-chars": "born-digital (pdfminer)",
                  "pdfplumber-chars": "born-digital (pdfplumber)",
                  "tesseract": "tesseract OCR", "visionocr": "vision OCR"}
    skel = _SRC_LABEL.get(source, source or "the")
    paras = doc.objects_of_type("Paragraph")
    # MathPix stores paragraph geometry in the `mathpix_lines` realizations (line
    # regions), not props["region"]; the merge leaves realizations untouched, so
    # `inspect` still derives each paragraph's bbox from them. Count what's located.
    located = [p for p in paras
               if p.props.get("page") is not None or p.realizations]
    if not paras:
        return f"{pdf.name}: the {skel} model has no Paragraph objects to merge onto."

    src, err = _locate_latex_source(pdf, sc, tex)
    if err:
        return err
    full, _main = ls.read_source(str(src))
    if not full:
        return f"Could not read LaTeX source from {src.name}."
    _pre, body = ls.split_preamble(full)
    gold = ML.latex_prose_from_body(body)
    if not gold.strip():
        return f"{src.name}: no extractable prose (all math/floats?)."

    changed = ML.merge_latex_prose(doc, gold)
    save_model(model_path, doc)

    sc.set_evidence("merge_latex_source", src.name)
    sc.set_evidence("merge_paragraphs_changed", changed)
    sc.save()
    watermark = (" This drops the two-column interleaving + arXiv margin watermark "
                 "from the prose (the gold text replaces the char-layer text)."
                 if source in ("pdfminer-chars", "pdfplumber-chars") else "")
    return (f"Merged LaTeX prose from {src.name} onto {len(paras)} {skel} "
            f"paragraph(s) ({len(located)} located; geometry/regions preserved — "
            f"the merge only replaces `text`): {changed} paragraph(s) got gold text "
            f"(LaTeX-wins; boundaries kept, original saved as `text_source`)."
            f"{watermark} Unmatched captions left as-is. "
            f"Run `pdfdrill inspect {pdf.name}` to see the corrected partitioning.")


def _fuse_emphasis_onto_paragraphs(model_dict: dict, doc, spans: list, pdf_dims: dict):
    """Fuse pdfminer emphasis runs onto the MERGED MathPix paragraphs by
    page-fraction overlap (the two coordinate systems — MathPix pixels vs PDF
    points — are each normalised to [0,1], never mixed raw). Writes
    `props['emphasis']` onto each matched Paragraph in `doc`. Returns the count.
    """
    from . import docinspect as DI
    from . import reconcile as RC
    from . import pdfminer_layer as PM

    sidx = DI.build_stream_index(model_dict)
    mp_dims = {o["props"].get("page_number"): (o["props"].get("page_width"),
                                               o["props"].get("page_height"))
               for o in model_dict.get("objects", []) if o["type"] == "Page"}
    paragraphs = []
    for o in model_dict.get("objects", []):
        if o["type"] != "Paragraph":
            continue
        page, box, _ = DI.object_geometry(o, sidx)
        dims = mp_dims.get(page)
        if page is None or not box or not dims or None in dims:
            continue
        frac = RC.to_page_fraction(
            {"top_left_x": box["x"], "top_left_y": box["y"],
             "width": box["w"], "height": box["h"]}, dims[0], dims[1])
        if frac:
            paragraphs.append({"id": o["id"], "page": page, "frac": frac})

    # Only INLINE emphasis fuses onto a paragraph: bold/italic body-size key terms
    # (defined terms, emphasis). Headings (bold+LARGER) are structural → Sections;
    # size-only runs (footnotes/captions) stay page-level. Keeps paragraph emphasis
    # meaningful for an LLM instead of dumping every deviating glyph.
    import re as _re
    run_items = []
    for s in spans:
        kind = s["kind"]
        if "larger" in kind or not any(t in kind for t in ("bold", "italic", "colored")):
            continue
        # word gate: a real emphasized WORD, not a single math variable / symbol /
        # number — needs >=3 Latin letters (drops C / α / "1.1" / punctuation).
        if len(_re.sub(r"[^A-Za-zÀ-ÿ]", "", (s["text"] or ""))) < 3:
            continue
        dims = pdf_dims.get(int(s["page"]))
        if not dims:
            continue
        frac = RC.to_page_fraction(s["region"], dims[0], dims[1])
        if frac:
            run_items.append({"page": int(s["page"]), "frac": frac,
                              "text": (s["text"] or "").strip(), "kind": kind,
                              "font": s["font"], "size": s["size"]})

    fused = PM.fuse_emphasis(paragraphs, run_items)
    n = 0
    for p in doc.objects_of_type("Paragraph"):
        p.props.pop("emphasis", None)          # idempotent: clear stale first
        e = fused.get(p.id)
        if e:
            p.props["emphasis"] = [{k: r[k] for k in ("text", "kind", "font", "size")}
                                   for r in e]
            n += 1
    return n


def cmd_fontspans(pdf: Path, pages: str | None = None) -> str:
    """The pdfminer LEG — recover the local formatting MathPix flattens.

    MathPix returns clean text but drops every local typography decision. The
    born-digital text layer, read glyph-by-glyph via pdfminer.six (`fontname`,
    `size`, the CTM `matrix`, colour), still carries it. This classifies each
    font-run against the body font and reports the **font/size changes** — bold
    headings, bold/italic key terms, small-font footnotes/captions — writing
    `<bibkey>.fontspans.json` and attaching the per-page emphasis onto each model
    `Page` (`props['font_emphasis']`). Born-digital only (a scan has no text
    layer → run `pdfdrill rasterize`/`ocr`). pdfminer.six required.
    """
    from .model_io import load_model, save_model
    from . import pdfminer_layer as PM

    if not PM.available():
        return ("pdfminer.six is not installed — the font-span leg needs it "
                "(`pip install pdfminer.six`).")
    sc = Sidecar(pdf)
    # born-digital gate: a scan has no glyph layer to read
    recs = PM.char_records(str(sc.pdf_path), pages=pages)
    if not recs:
        return (f"{pdf.name}: no born-digital text layer (pdfminer found 0 glyphs"
                f"{' on the requested pages' if pages else ''}). This is a scan — "
                f"`pdfdrill rasterize`/`ocr` for the visual/OCR route; font runs "
                f"need vector text.")
    body = PM.dominant_style(recs)
    body_color = PM.dominant_color(recs)
    runs = PM.font_runs(recs)
    spans = PM.emphasis_spans(runs, body, body_color=body_color)

    # by-kind rollup for the summary
    from collections import Counter
    kinds = Counter(s["kind"] for s in spans)
    headings = [s for s in spans if "larger" in s["kind"] and s.get("bold")]
    emph = [s for s in spans if s["kind"] in ("bold", "italic", "bold+italic")]
    small = [s for s in spans if "smaller" in s["kind"]]
    colored = [s for s in spans if "colored" in s["kind"]]

    bibkey = sc.get_evidence("bibkey") or pdf.stem
    out = {
        "body": body, "body_color": body_color,
        "counts": {"glyphs": len(recs), "runs": len(runs),
                   "emphasis": len(spans), "by_kind": dict(kinds)},
        "spans": [{"page": s["page"], "text": s["text"].strip(), "kind": s["kind"],
                   "font": s["font"], "size": s["size"], "color": s.get("color"),
                   "region": s["region"]}
                  for s in spans if (s["text"] or "").strip()],
    }
    out_path = sc.blob_dir / f"{_safe_bibkey(str(bibkey))}.fontspans.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")

    # enrich the model (if one exists): per-page emphasis onto Page objects,
    # per-PARAGRAPH fusion by overlap, and the heading cross-check vs Sections.
    attached = fused_paras = confirmed_h = 0
    missed_h: list = []
    model_path = _model_path(sc)
    if model_path.exists():
        try:
            with open(model_path, "r", encoding="utf-8") as f:
                model_dict = json.load(f)
            doc = load_model(model_path)
            attached = PM.attach_page_emphasis(doc, spans)
            pdf_dims = PM.page_dims(str(sc.pdf_path), pages=pages)
            fused_paras = _fuse_emphasis_onto_paragraphs(model_dict, doc, spans, pdf_dims)
            # heading cross-check: visual bold+larger runs vs the model Sections.
            # A match CONFIRMS the Section (three-source agreement); a visual
            # heading with no Section is a repair candidate (reported, not forced).
            sections = [{"id": o.id,
                         "caption": o.props.get("caption") or o.props.get("title")}
                        for o in doc.objects_of_type("Section")]
            hx = PM.heading_crosscheck(sections, headings)
            secmap = {o.id: o for o in doc.objects_of_type("Section")}
            for c in hx["confirmed"]:
                s = secmap.get(c["section_id"])
                if s:
                    s.props["visual_confirmed"] = True
                    s.props["visual_font"] = c["font"]
                    s.props["visual_size"] = c["size"]
            confirmed_h, missed_h = len(hx["confirmed"]), hx["missed"]
            save_model(model_path, doc)
        except Exception:
            attached = fused_paras = confirmed_h = 0
            missed_h = []

    rel = _display_path(out_path, sc.pdf_path.parent)
    sc.set_evidence("fontspans_path", str(rel))
    sc.set_evidence("fontspans_body_font", body.get("font"))
    sc.set_evidence("fontspans_emphasis", len(spans))
    sc.save()

    def _ex(items, k=4):
        seen, out_ex = set(), []
        for s in items:
            t = (s["text"] or "").strip()
            if len(t) >= 3 and t.lower() not in seen:
                out_ex.append(f"“{t[:40]}”"); seen.add(t.lower())
            if len(out_ex) >= k:
                break
        return ", ".join(out_ex) or "—"

    lines = [
        f"Font-span analysis of {pdf.name} ({len(recs)} glyphs, {len(runs)} runs) "
        f"— pdfminer recovers the local formatting MathPix flattens.",
        f"Body font: {body.get('font')} @ {body.get('size')}pt, colour {body_color}.",
        f"  headings (bold+larger): {len(headings)}  e.g. {_ex(headings)}",
        f"  key terms (bold/italic): {len(emph)}  e.g. {_ex(emph)}",
        f"  coloured runs: {len(colored)}  e.g. {_ex(colored)}",
        f"  small (footnotes/captions): {len(small)}",
    ]
    if model_path.exists():
        lines.append(
            f"Heading cross-check vs Sections: {confirmed_h} confirmed (three-source "
            f"agreement), {len(missed_h)} visual heading(s) with NO Section"
            + (f" — repair candidates: {_ex(missed_h)}" if missed_h else "") + ".")
    lines.append(
        f"Wrote {rel}"
        + (f"; font_emphasis onto {attached} Page(s)" if attached else "")
        + (f"; fused emphasis onto {fused_paras} Paragraph(s)" if fused_paras else "")
        + ".")
    return "\n".join(lines)


def ingest_source_graphics(doc, body: str, macros: dict, bibkey: str,
                           force: bool = False) -> int:
    """Create Diagram/Table DocObjects from the LaTeX source's TikZ/tables
    (tikzcd commutative diagrams, tabular, …), each carrying the expanded
    `latex_code` + verbatim `latex_original` so `pdfdrill svg` can render it.
    Tagged `added_by="latex"`; idempotent (dedupes by source code); `force`
    drops previously-ingested source graphics first. Returns the count added."""
    from docmodel.core import DocObject
    from . import latex_source as ls
    if force:
        doc.objects = {k: v for k, v in doc.objects.items()
                       if not (v.type in ("Diagram", "Table")
                               and v.props.get("added_by") == "latex")}
        for o in doc.objects.values():            # un-overlay MathPix tables
            if o.type == "Table" and o.props.pop("latex_overlaid", None):
                for k in ("latex_code", "latex_original", "env"):
                    o.props.pop(k, None)
    existing = {o.props.get("latex_original", "").strip()
                for o in doc.objects.values() if o.type in ("Diagram", "Table")}
    # MathPix-detected tables (region, no source latex yet) a source tabular can
    # OVERLAY onto — so one Table carries BOTH region + latex_code (the equation
    # pattern), never a duplicate. Content-matched once each here (SequenceMatcher
    # against MathPix's own `\begin{tabular}` line text, like the enrich step), so
    # downstream tools address a table by its region, not by content.
    from difflib import SequenceMatcher
    _norm = lambda s: " ".join((s or "").split())    # noqa: E731
    mp_tables = [o for o in doc.objects.values()
                 if o.type == "Table" and o.props.get("region")
                 and o.props.get("added_by") != "latex"
                 and not o.props.get("latex_code")]
    used_mp: set = set()
    base_fi = max((o.props.get("flow_index", 0) for o in doc.objects.values()),
                  default=0)
    added = 0
    for gi, g in enumerate(ls.extract_graphics(body), 1):
        if g["code"].strip() in existing:
            continue
        expanded = ls.expand_macros(g["code"], macros)
        if g["kind"] == "Table":
            src = _norm(g["code"])
            best, best_r = None, 0.55              # ratio threshold (latex↔latex)
            for o in mp_tables:
                if o.id in used_mp:
                    continue
                cand = _norm(o.props.get("mathpix_text") or o.props.get("raw_text"))
                if not cand:
                    continue
                r = SequenceMatcher(None, src, cand).ratio()
                if r > best_r:
                    best, best_r = o, r
            if best is not None:                   # overlay, keep region/page
                best.props["latex_code"] = expanded
                best.props["latex_original"] = g["code"]
                best.props["env"] = g["env"]
                if g.get("caption"):
                    best.props.setdefault("caption", g["caption"])
                best.props["latex_overlaid"] = True
                used_mp.add(best.id)
                added += 1
                continue
        doc.add(DocObject(type=g["kind"], props={
            "latex_code": expanded,
            "latex_original": g["code"], "caption": g.get("caption", ""),
            "env": g["env"], "flow_index": base_fi + gi,
            "bibkey": bibkey, "added_by": "latex"}))
        added += 1
    return added



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

def _externalize_svg_tiddlers(tiddlers: list, svg_dir: Path, uri_prefix: str) -> int:
    """`--embed-svg=false`: move each tiddler's inline `svg_tiddler` SVG out to an
    external `<svg_dir>/<title>.svg` file and rewrite the tiddler to reference it
    (`type: image/svg+xml`, `_canonical_uri: <prefix>/<title>.svg`, empty text) —
    a lean wiki store instead of ~1 MB of inline SVG. Non-SVG tiddlers untouched.
    Returns the count externalized."""
    svg_dir = Path(svg_dir)
    prefix = uri_prefix.rstrip("/")
    n = 0
    for t in tiddlers:
        svg = t.get("svg_tiddler")
        if not (isinstance(svg, str) and svg.lstrip().startswith("<svg")):
            continue
        if n == 0:
            svg_dir.mkdir(parents=True, exist_ok=True)
        fname = re.sub(r"[^\w.\-]", "_", t["title"]) + ".svg"
        (svg_dir / fname).write_text(svg, encoding="utf-8")
        t.pop("svg_tiddler", None)
        t["type"] = "image/svg+xml"
        t["_canonical_uri"] = f"{prefix}/{fname}" if prefix else fname
        t["text"] = ""
        n += 1
    return n


def cmd_tiddlers(pdf: Path, force: bool = False, embed: bool = False,
                 bibkey: str | None = None, embed_svg: bool = True) -> str:
    """Emit a TiddlyWiki JSON tiddler array from the unified model.

    Quick way to eyeball the structure: drop the array into TiddlyWiki and a
    `<$list>` table macro renders each equation's LaTeX (`<$latex>`), its
    KaTeX rendering, and the MathPix crop (`<$image source={{!!canonical_uri}}
    width={{!!width}} height={{!!height}}>`). Equation tiddlers carry `latex`,
    `displayMode`, `refnum`, `canonical_uri`, region `width`/`height`, and any
    competing readings as `latex_<provenance>` fields. Auto-chains `model`.

    `bibkey` sets the tiddler-prefix / title namespace + the artifact filename;
    it falls back to the key persisted by `model` (sidecar), then the stem.
    """
    from docmodel.core import Document
    from docops.base import OperatorConfig
    from docops.projectors.tiddlywiki import TiddlyWikiProjector

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
        cmd_model(pdf, bibkey=bibkey)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    # If a LaTeX-source model has in-text Citations but NO References yet, build the
    # bibliography from the source bib (.bbl/.bib) so citations resolve to Reference
    # tiddlers (carrying the .bbl text) instead of "Citation placeholder for …".
    if (not sc.has(BIBLIOGRAPHY_BUILT)
            and any(o.type == "Citation" for o in doc.objects.values())
            and not any(o.type == "Reference" for o in doc.objects.values())):
        cmd_bibliography(pdf)
        sc = Sidecar(pdf)
        with open(model_path, "r", encoding="utf-8") as f:
            doc = Document.from_dict(json.load(f))

    # Resolve the prefix with documented precedence:
    #   explicit --bibkey > sidecar (set by `model`) > model meta > filename stem.
    key = (bibkey or sc.get_evidence("bibkey") or doc.meta.get("bibkey")
           or pdf.stem)
    key = key.strip()
    # Make an explicit override DURABLE: persist into the model meta + sidecar so
    # later `report`/`compare` (which read doc.meta['bibkey']) reuse it too.
    if doc.meta.get("bibkey") != key:
        doc.meta["bibkey"] = key
        with open(model_path, "w", encoding="utf-8") as f:
            json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)
    if sc.get_evidence("bibkey") != key:
        sc.set_evidence("bibkey", key)

    t0 = time.monotonic()
    proj = TiddlyWikiProjector(
        OperatorConfig(op="projector", classname="TiddlyWikiProjector",
                   params={"embed": embed}))
    result = proj.project(doc)
    count = proj.counters.get("tiddlers_emitted", 0)

    bibkey = key
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    out_path = sc.blob_dir / f"{bibkey}.tiddlers.json"

    # --embed-svg=false: write each diagram's SVG to an external file referenced
    # by _canonical_uri, instead of inlining it in the svg_tiddler field.
    svg_note = ""
    if not embed_svg:
        tiddlers = json.loads(result)
        svg_dir = sc.blob_dir / "svg"
        n_ext = _externalize_svg_tiddlers(tiddlers, svg_dir, "svg")
        result = json.dumps(tiddlers, ensure_ascii=False, indent=1)
        if n_ext:
            rel_dir = svg_dir.relative_to(sc.pdf_path.parent)
            svg_note = (f" {n_ext} diagram SVG(s) written to {rel_dir}/ and referenced "
                        f"via _canonical_uri (svg/<title>.svg) — copy that folder "
                        f"alongside your wiki HTML.")
    out_path.write_text(result, encoding="utf-8")

    sc.set_evidence("tiddlers_path", str(out_path.relative_to(sc.pdf_path.parent)))
    sc.set_evidence("tiddlers_count", count)
    sc.set_evidence("tiddlers_svg_mode", "inline" if embed_svg else "external")
    prev = ",".join(sorted(sc.facts - {TIDDLERS_BUILT})) or "INIT"
    sc.add_fact(TIDDLERS_BUILT)
    sc.log_transition(
        "tiddlers", prev, TIDDLERS_BUILT, cost_ms=(time.monotonic() - t0) * 1000,
        detail=f"{count} tiddlers, svg={'inline' if embed_svg else 'external'}",
    )
    sc.save()
    rel = _artref(sc, out_path)
    # Referential-integrity guard: every transclusion target/template must exist
    # and no synthetic FOX may be orphaned (created but never referenced) — the
    # "double bug" class. Report it so it can't hide.
    from docops.projectors.tiddlywiki import tiddler_integrity
    integ = tiddler_integrity(json.loads(result))
    if integ["dangling"] or integ["orphan_synthetic"]:
        bits = []
        if integ["dangling"]:
            bits.append(f"{len(integ['dangling'])} DANGLING transclusion(s) "
                        f"(e.g. {', '.join(integ['dangling'][:3])})")
        if integ["orphan_synthetic"]:
            bits.append(f"{len(integ['orphan_synthetic'])} ORPHAN synthetic "
                        f"formula(s) (e.g. {', '.join(integ['orphan_synthetic'][:3])})")
        integ_note = " ⚠ integrity: " + "; ".join(bits) + "."
    else:
        integ_note = (f" Integrity OK: {integ['transclusions']} transclusions, "
                      f"0 dangling, 0 orphan.")
    guard = _unrendered_graphics_note(doc.objects.values())
    return (f"Wrote {count} TiddlyWiki tiddlers to {rel}. Import into TiddlyWiki; "
            f"diagram SVGs render via {{{{!!svg_tiddler}}}} "
            f"({'inline' if embed_svg else 'external _canonical_uri'}).{svg_note}"
            f"{integ_note}{guard}")


# Tag -> the tiddler field whose prose gets translated. Math/code/image/toc
# tiddlers (equation, formula, code, picture, diagram, table, toc, page,
# reference) are intentionally absent — their text is not natural-language prose.
_TRANSLATE_FIELD = {
    "paragraph": "text", "footnote": "text", "sidenote": "text",
    "abstract": "text", "section": "caption",
}


def _translate_field_for(tiddler: dict) -> Optional[str]:
    tags = set((tiddler.get("tags") or "").split())
    for tag, field in _TRANSLATE_FIELD.items():
        if tag in tags:
            return field
    return None


# DocObject type -> the prose prop translated in the MODEL. Math/code/image/
# table objects are absent (their content is not natural-language prose).
_TRANSLATE_MODEL_FIELD = {
    "Paragraph": "text", "Abstract": "text",
    "Footnote": "content", "Sidenote": "content", "ListItem": "content",
    "Section": "caption",
}


def translate_model_prose(doc, batch_fn, target_lang: str,
                          source_lang: str | None = None,
                          limit: int | None = None, force: bool = False) -> int:
    """Translate each prose DocObject's text IN PLACE, keeping the original under
    `<field>_source` (the bi-layer backup). `batch_fn(texts, target, source)` is
    the DeepL batch call (injected for unit-testing). Already-translated objects
    (those that already carry `<field>_source`) are skipped unless `force`.
    Returns the count changed; math/code/image objects are left untouched."""
    jobs: list[tuple] = []
    for obj in doc.objects.values():
        field = _TRANSLATE_MODEL_FIELD.get(obj.type)
        if not field:
            continue
        backup = field + "_source"
        already = backup in obj.props
        if already and not force:                         # already translated
            continue
        # on --force re-translate from the PRESERVED original, not the translation
        src = obj.props.get(backup) if (already and force) else obj.props.get(field)
        if not (isinstance(src, str) and src.strip()):
            continue
        jobs.append((obj, field, backup, src))
    if limit is not None:
        jobs = jobs[:limit]
    if not jobs:
        return 0
    texts = [j[3] for j in jobs]
    translated: list[str] = []
    for i in range(0, len(texts), 40):                # DeepL: <=50 texts/request
        translated.extend(batch_fn(texts[i:i + 40], target_lang, source_lang))
    changed = 0
    for (obj, field, backup, src), tr in zip(jobs, translated):
        if tr and tr != src:
            obj.props[backup] = src                       # keep the original (bi-layer)
            obj.props[field] = tr                         # translation under the field
            changed += 1
    return changed


def _translate_tiddler_file_inplace(path: Path, batch_fn, target_lang: str,
                                    source_lang: str | None = None,
                                    force: bool = False) -> int:
    """Translate prose tiddlers (`_translate_field_for`) IN the file at `path`,
    writing the changed array back to the SAME file. Translation replaces the
    field; the original is kept under `<field>_source`. Handles transcluded
    paragraphs (the `{{...||FO}}` tokens are already in the text, so DeepL
    translates the prose around them). Idempotent; `force` re-translates from the
    preserved original. Returns the count changed."""
    tiddlers = json.loads(path.read_text(encoding="utf-8"))
    jobs: list[tuple] = []
    for t in tiddlers:
        field = _translate_field_for(t)
        if not field:
            continue
        backup = field + "_source"
        already = backup in t
        if already and not force:
            continue
        src = t.get(backup) if (already and force) else t.get(field)
        if not (isinstance(src, str) and src.strip()):
            continue
        jobs.append((t, field, backup, src))
    if not jobs:
        return 0
    texts = [j[3] for j in jobs]
    translated: list[str] = []
    for i in range(0, len(texts), 40):
        translated.extend(batch_fn(texts[i:i + 40], target_lang, source_lang))
    changed = 0
    for (t, field, backup, src), tr in zip(jobs, translated):
        if tr and tr != src:
            t[backup] = src
            t[field] = tr
            tags = set((t.get("tags") or "").split())
            tags.add("translated")
            t["tags"] = " ".join(sorted(tags))
            t["translated_lang"] = target_lang.upper()
            changed += 1
    path.write_text(json.dumps(tiddlers, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return changed


def cmd_translate(pdf: Path, target_lang: str = "EN-US",
                  source_lang: str | None = None, limit: int | None = None,
                  force: bool = False) -> str:
    """Translate the document in place via DeepL — one source, two outputs.

    The MODEL's prose objects (Paragraph/Abstract → `text`, Section → `caption`,
    ListItem/Footnote/Sidenote → `content`) are translated **in place**: the
    translation replaces the field and the original is kept under `<field>_source`.
    The translated `model.docmodel.json` is then re-projected, so BOTH the tiddler
    file (`<bibkey>.tiddlers.json`, translated text in the `text` field) AND a
    **bi-layer Markdown** (`<bibkey>.md`: translation + a hidden source layer with
    a CSS/JS toggle) carry the translation. Math/code/image objects are untouched.
    Idempotent (skips objects already carrying `<field>_source`; `--force` redoes).
    Needs `DEEPL_API_KEY` (env / .env).
    """
    from . import deepl_client
    from .net import NetworkBlocked
    from docmodel.core import Document
    from docops.base import OperatorConfig
    from docops.projectors.llm_compact import LLMCompactProjector

    sc = Sidecar(pdf)
    key = resolve_bibkey(pdf, None, sc)
    if not deepl_client.available():
        return ("DeepL unavailable: set DEEPL_API_KEY in the environment or .env "
                "(https://www.deepl.com/your-account/keys), then rerun "
                "`pdfdrill translate`.")

    model_path = _model_path(sc)
    if not (sc.has(MODEL_BUILT) and model_path.exists()):
        cmd_model(pdf)
        sc = Sidecar(pdf)
        key = resolve_bibkey(pdf, None, sc)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    doc = load_model(model_path)
    t0 = time.monotonic()
    try:
        changed = translate_model_prose(
            doc, deepl_client.translate_batch, target_lang, source_lang, limit, force)
    except NetworkBlocked as e:
        return str(e)

    # Persist the translated model in place (only if it changed), then re-project.
    if changed:
        doc.meta["translated_lang"] = target_lang.upper()
        save_model(model_path, doc)

    # Regenerate the tiddler file from the model, then translate it IN PLACE.
    # The TiddlyWiki projector rebuilds transcluded paragraphs from the immutable
    # source stream BY OFFSET (to re-insert {{...||FO}} tokens), so the model's
    # translated `text` doesn't reach them — the tiddler `text`/`caption` fields
    # must be translated at the tiddler level (tokens already inserted). This is
    # your original approach; the changed tiddler file is written in place.
    cmd_tiddlers(pdf, force=True)
    sc = Sidecar(pdf)
    key = resolve_bibkey(pdf, None, sc)
    tid_path = sc.blob_dir / f"{key}.tiddlers.json"
    try:
        tid_changed = _translate_tiddler_file_inplace(
            tid_path, deepl_client.translate_batch, target_lang, source_lang, force)
    except NetworkBlocked as e:
        return str(e)

    projector = LLMCompactProjector(OperatorConfig(
        op="projector", classname="LLMCompactProjector",
        params={"bilayer": True, "source_lang": (source_lang or "").upper(),
                "target_lang": target_lang.upper()}))
    md_text = projector.project(doc)
    md_path = sc.blob_dir / f"{key}.md"
    md_path.write_text(md_text, encoding="utf-8")

    sc.set_evidence("translated_lang", target_lang.upper())
    sc.set_evidence("translated_count", changed)
    prev = ",".join(sorted(sc.facts - {TRANSLATED})) or "INIT"
    sc.add_fact(TRANSLATED)
    sc.log_transition("translate", prev, TRANSLATED,
                      cost_ms=(time.monotonic() - t0) * 1000,
                      detail=f"{changed} prose objects -> {target_lang}")
    sc.save()
    tid_rel = tid_path.relative_to(sc.pdf_path.parent)
    md_rel = md_path.relative_to(sc.pdf_path.parent)
    return (f"Translated to {target_lang.upper()} via DeepL (in place; original kept "
            f"under <field>_source).\n"
            f"  • tiddlers: {tid_rel} — {tid_changed} tiddler(s), translated text in "
            f"the `text` field\n"
            f"  • markdown: {md_rel} — {changed} object(s), bi-layer (translation + "
            f"hidden source, CSS/JS toggle)")


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
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
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
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
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
    numeric = authyear = cites = 0
    source_note = ""

    if n == 0:
        # Heuristic found no INLINED references — the keyless arXiv LaTeX-source
        # case: the entries live in biblio.bib (named by \bibliography{}), not in
        # the prose. Build THIS paper's bibliography from that GOLD source (full
        # BibTeX fields, free — Perplexity/bibfetch then has nothing to do).
        from .bibliography import build_bibliography_from_source
        src_dir = doc.meta.get("latex_source_dir") or str(model_path.parent / "texsrc")
        if Path(src_dir).is_dir():
            res = build_bibliography_from_source(doc, src_dir)
            n = sum(1 for o in doc.objects.values() if o.type == "Reference")
            with_year = sum(1 for o in doc.objects.values()
                            if o.type == "Reference" and o.props.get("year"))
            cites = sum(1 for a in doc.alignments if a.kind == "cites")
            if n:
                source_note = (f"  (heuristic found none → built {n} from the source "
                               f"bibliography: gold BibTeX, {res['linked']} citations "
                               f"linked, no Perplexity needed)")

    if not source_note:
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
    return _format_bibliography(sc) + source_note


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

    # Keyless fallback: with no PERPLEXITY_API_KEY, delegate the web-search BibTeX
    # task to the Claude agent running pdfdrill (CLI `claude -p` or the sandbox
    # handshake), handed perplexity_client's OWN bibtex_prompt. The API path
    # below is untouched when a key is present.
    from . import perplexity_client as _pc, llm_delegate as _D
    if not _pc.available():
        rt = _D.detect_runtime()
        if rt is _D.Runtime.NONE:
            return ("BibTeX enrichment unavailable: set PERPLEXITY_API_KEY (env "
                    "or .env), or run pdfdrill under Claude Code / the Claude.ai "
                    "sandbox for the keyless web-search delegation fallback. In "
                    "the sandbox but not detected? force it: "
                    "PDFDRILL_DELEGATE=sandbox (check `pdfdrill llm <pdf> --runtime`).")
        return _bibfetch_via_delegate(pdf, doc, todo, sc, model_path, rt)

    from .net import NetworkBlocked
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
        except NetworkBlocked as nb:  # blocked host: abort, don't hammer N refs
            return str(nb)
        except Exception:  # noqa: BLE001 — one failure shouldn't abort the batch
            errors += 1
            continue
        if res["bibtex"]:
            r.props["bibtex"] = res["bibtex"]
            r.props["citations"] = " ".join(res["citations"])
            r.props["bibfetched"] = True   # web-sourced → may introduce errors
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


def _bibfetch_via_delegate(pdf: Path, doc, todo, sc, model_path, runtime) -> str:
    """Keyless BibTeX enrichment: one delegated web-search task per Reference,
    handed perplexity_client.bibtex_prompt. CLI runtime answers synchronously;
    SANDBOX writes request files + returns the agent instruction (re-run ingests).
    Applies the parsed {bibtex, citations, fields} exactly as the API loop does."""
    from . import perplexity_client as pc, llm_delegate as D

    if not todo:
        return (f"BibTeX (delegated/{runtime.value}): nothing to do — every "
                f"Reference already carries bibtex (use --force to redo).")

    pairs, tasks, seen = [], [], set()
    for r in todo:
        p = r.props
        prompt = pc.bibtex_prompt(p.get("citekey", ""), p.get("author", ""),
                                  p.get("year", ""), p.get("title", ""),
                                  p.get("raw_text", ""))
        t = D.LLMTask(kind="bibtex", prompt=prompt,
                      meta={"citekey": p.get("citekey", "")})
        pairs.append((r, t))
        if t.task_id not in seen:
            seen.add(t.task_id)
            tasks.append(t)

    try:
        results, deferred = D.delegate_batch(
            tasks, drill_dir=sc.blob_dir, runtime=runtime, timeout=120.0)
    except D.DelegateUnavailable as e:
        return str(e)

    if deferred is not None:                       # sandbox: hand off + stop
        return (f"BibTeX deferred to the {runtime.value} Claude agent: "
                f"{len(deferred.tasks)} request(s) written"
                + (f", {len(results)} already answered" if results else "")
                + ".\n\n" + deferred.instruction)

    done = errors = 0
    for r, t in pairs:
        res = results.get(t.task_id)
        if res is None:
            errors += 1
            continue
        if res.get("bibtex"):
            r.props["bibtex"] = res["bibtex"]
            r.props["citations"] = " ".join(res.get("citations", []))
            r.props["bibfetched"] = True   # web-sourced → may introduce errors
            for k in ("author", "year", "title", "entry_type"):
                if res.get("fields", {}).get(k):
                    r.props[k] = res["fields"][k]
            done += 1
        else:
            errors += 1

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)
    total = (sc.get_evidence("bibfetch_done", 0) or 0) + done
    sc.set_evidence("bibfetch_done", total)
    prev = ",".join(sorted(sc.facts - {BIBFETCH_DONE})) or "INIT"
    sc.add_fact(BIBFETCH_DONE)
    sc.log_transition("bibfetch", prev, BIBFETCH_DONE,
                      detail=f"{done} enriched, {errors} errors (delegated/{runtime.value})")
    sc.save()
    return (f"Enriched {done} reference(s) with full BibTeX by delegating the "
            f"web-search to the {runtime.value} Claude agent"
            + (f" ({errors} failed)" if errors else "")
            + f". Rebuild `pdfdrill tiddlers {pdf.name}`.")


def cmd_citedrill(pdf: Path, limit: int | None = None, force: bool = False) -> str:
    """Drill INTO each citation: find where the cited publication can be
    downloaded (Perplexity SONAR for all links, plus links seeded from the
    reference's own bibtex/raw_text), rank free routes first (arXiv → its PDF,
    then .pdf, then DOI), attempt to fetch the PDF into `<drill>/cited/`, and
    stamp the Reference with drill STATUS: `drill_status` (fetched/links_only/
    no_links/blocked), `pdf_url`, `pdf_path`, `pdf_json` (the per-reference
    attempt record), and `download_links`. Idempotent (skips already-drilled
    unless --force); `--limit N` caps the references processed.
    """
    from docmodel.core import Document
    from . import citedrill as cdr
    from .net import NetworkBlocked

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(BIBLIOGRAPHY_BUILT) and not _has_references(model_path):
        cmd_bibliography(pdf)
        sc = Sidecar(pdf)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill bibliography`/`bibsource` first)."

    doc = load_model(model_path)
    refs = [o for o in doc.objects.values() if o.type == "Reference"]
    todo = [r for r in refs if force or not r.props.get("drill_status")]
    if limit is not None:
        todo = todo[:limit]
    if not refs:
        return f"No References in {pdf.name} — run `pdfdrill bibliography`/`bibsource` first."

    cited_dir = sc.blob_dir / "cited"
    fetched = links_only = no_links = blocked = 0
    for r in todo:
        p = r.props
        title, author = p.get("title", ""), p.get("author", "")
        year, raw = p.get("year", ""), p.get("raw_text", "")
        # seed candidate links from the reference itself (works offline)
        seed = cdr.extract_links(f"{raw}\n{p.get('bibtex','')}")
        is_blocked = False
        # Perplexity (graceful): a missing key / blocked network only affects this step
        try:
            from . import perplexity_client as _pc
            res = _pc.fetch_links(title, author, year, raw)
            seed = cdr.extract_links(res["answer"], res.get("citations")) + seed
        except NetworkBlocked:
            is_blocked = True
        except Exception:
            pass  # no key / API error → fall back to seeded links only

        candidates = cdr.rank_links(seed)
        pdf_url = pdf_path = None
        for c in candidates:
            c["verify"] = cdr.verify(c["url"])
            c["fetched"] = False
            if pdf_path is None:                       # attempt any link, in rank order
                dest = cited_dir / f"{p.get('citekey','ref')}.pdf"
                if cdr.fetch(c["url"], dest):
                    c["fetched"] = True
                    pdf_url = c["url"]
                    pdf_path = str(dest.relative_to(sc.blob_dir))
        record = cdr.build_record(p.get("citekey", ""), title, year, candidates,
                                  pdf_url, pdf_path, blocked=is_blocked and not candidates)
        # write the per-reference pdf.json attempt record
        cited_dir.mkdir(parents=True, exist_ok=True)
        jpath = cited_dir / f"{p.get('citekey','ref')}.pdf.json"
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        p.update(cdr.reference_fields(record, str(jpath.relative_to(sc.blob_dir))))
        st = record["drill_status"]
        fetched += st == "fetched"
        links_only += st == "links_only"
        no_links += st == "no_links"
        blocked += st == "blocked"

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)
    sc.set_evidence("citedrill", {"fetched": fetched, "links_only": links_only,
                                  "no_links": no_links, "blocked": blocked,
                                  "processed": len(todo)})
    sc.save()
    return (f"Drilled {len(todo)} citation(s): {fetched} PDF(s) fetched, "
            f"{links_only} with links only, {no_links} no links"
            + (f", {blocked} blocked (no Perplexity/network)" if blocked else "")
            + f". Each Reference carries drill_status/pdf_url/pdf_path + a "
            f"cited/<citekey>.pdf.json record. PDFs in {cited_dir.relative_to(sc.pdf_path.parent)}/.")


def _has_references(model_path: Path) -> bool:
    try:
        import json as _j
        d = _j.load(open(model_path, encoding="utf-8"))
        objs = d.get("objects", {})
        vals = objs.values() if isinstance(objs, dict) else objs
        return any(o.get("type") == "Reference" for o in vals)
    except Exception:
        return False


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
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
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
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
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
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
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
    rel = _artref(sc, out_path)
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
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
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
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
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
        rel = _artref(sc, out_path)
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
    from .net import NetworkBlocked as _NetworkBlocked

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."
    from . import llm_delegate as _D
    use_delegate = not openai_vision.available()
    if use_delegate and _D.detect_runtime() is _D.Runtime.NONE:
        return ("OpenAI vision unavailable: set OPENAI_API_KEY in the "
                "environment or .env (https://platform.openai.com/api-keys), "
                "then rerun `pdfdrill vision`. (No Claude agent detected for the "
                "keyless delegation fallback — run under Claude Code or the "
                "Claude.ai sandbox; if you ARE in the sandbox but it isn't "
                "detected, force it with PDFDRILL_DELEGATE=sandbox — check with "
                "`pdfdrill llm <pdf> --runtime`.)")

    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    def _has_openai(o, url):
        return any(r.role == "latex_candidate" and r.provenance == "openai"
                   and (r.props or {}).get("url") == url for r in o.realizations)

    targets = _collect_cdn_crops(doc)
    if not targets:
        # `vision` reads the image crops MathPix produces; a MathPix-KEYLESS model
        # (tesseract / rasterize / chars→lines) has none, so there is nothing to
        # delegate. The correct keyless math move is to render + read the pages.
        return (f"No MathPix CDN image crops in {pdf.name}'s model — `vision` "
                f"reads the crops MathPix emits, and this model has none. For a "
                f"MathPix-keyless MATH document, render the pages and READ the "
                f"equations visually: `pdfdrill rasterize {pdf.name}` (then open "
                f"the PNGs). For born-digital papers, `pdfdrill latex {pdf.name}` "
                f"recovers the author's gold equations. `vision` only applies once "
                f"a MathPix model with CDN crops exists.")
    todo = [(o, u) for (o, u) in targets if force or not _has_openai(o, u)]
    if limit is not None:
        todo = todo[:limit]

    if use_delegate:
        return _vision_via_delegate(pdf, doc, todo, targets, sc, model_path,
                                    _D.detect_runtime(), force)

    # An image whose caption/title names a graph/subgraph is a vertex+edge
    # drawing that reconstructs cleanly as TikZ — use the targeted prompt.
    graph_kw = re.compile(r"\b(sub)?graph\b", re.I)

    def _is_graph(o):
        txt = " ".join(str((o.props or {}).get(k) or "")
                       for k in ("caption", "title", "raw_text"))
        return bool(graph_kw.search(txt))

    # An image whose caption/title names a molecule/compound/reaction (or a
    # chemistry "Scheme N") is a drawn structure that reconstructs cleanly as
    # chemfig — use the targeted chemistry prompt. Deliberately NOT matching
    # bare "structure" (data structures!) or "formula" (math).
    chem_kw = re.compile(
        r"\b(molecul\w*|molekül\w*|compound|verbindung\w*|reaktion\w*|reaction"
        r"|synthes\w*|reagent|reagenz\w*|catalyst|katalysator\w*|isomer\w*"
        r"|ligand\w*|monomer\w*|polymer\w*|strukturformel\w*)\b"
        r"|\bscheme\s+\d", re.I)

    def _is_chem(o):
        txt = " ".join(str((o.props or {}).get(k) or "")
                       for k in ("caption", "title", "raw_text"))
        return bool(chem_kw.search(txt))

    t0 = time.monotonic()
    processed = 0
    by_sel: Counter = Counter()
    errors = 0
    api_calls = 0
    graphs = 0
    chems = 0
    adopted = 0
    url_cache: dict[str, tuple] = {}   # the same crop can hang off >1 object
    for o, url in todo:
        is_chem = _is_chem(o)
        is_graph = (not is_chem) and _is_graph(o)
        ckey = (url, is_graph, is_chem)
        if ckey in url_cache:
            selector, code, res = url_cache[ckey]
        else:
            try:
                prompt = (openai_vision.CHEM_STRUCTURE_PROMPT if is_chem
                          else openai_vision.GRAPH_TIKZ_PROMPT if is_graph
                          else openai_vision.DEFAULT_PROMPT)
                res = openai_vision.analyze_image(url, prompt=prompt)
            except _NetworkBlocked as nb:   # blocked host: abort the batch
                return str(nb)
            except Exception:
                errors += 1
                continue
            api_calls += 1
            if is_graph:
                graphs += 1
            selector, code = openai_vision.result_to_latex(res)
            if is_chem and selector in ("chemical_structure", "chemical_equation"):
                chems += 1
            url_cache[ckey] = (selector, code, res)
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
        # Chemistry bridge to the existing TikZ/table SVG route: a Diagram crop
        # that MathPix left as an image has latex_code="" — adopt the chemfig /
        # \ce code into latex_code (never overwriting MathPix/source LaTeX) so
        # `pdfdrill svg` compiles it via latex->dvisvgm exactly like TikZ.
        if (selector in ("chemical_structure", "chemical_equation") and code
                and o.type in ("Diagram", "Table")
                and not (o.props.get("latex_code") or "").strip()):
            o.props["latex_code"] = code
            o.props["latex_code_provenance"] = "openai"
            adopted += 1
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
    graph_s = f" {graphs} graph/subgraph image(s) reconstructed as TikZ." if graphs else ""
    chem_s = (f" {chems} chemistry image(s) reconstructed as chemfig/mhchem"
              + (f"; {adopted} adopted into latex_code — run `pdfdrill svg "
                 f"{pdf.name}` to render them via latex->dvisvgm."
                 if adopted else ".")) if chems else ""
    remaining = len(targets) - processed if limit is None else max(0, len(targets) - len(todo))
    return (
        f"OpenAI vision: read {processed} CDN crop(s){dedup_s} ({sel_s}){err_s}; "
        f"{len(targets)} total crops in the model. Attached as the 'openai' "
        f"provenance (selector + LaTeX/TikZ/table).{graph_s}{chem_s} "
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
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
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
        doc, image_layer, page_dims, bibkey=doc.meta.get("bibkey", pdf.stem))
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
    try:
        out = subprocess.run(
            ["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        return _missing_tool_msg("pdfinfo", "poppler-utils")
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


def _drillpdfse_dir() -> Path:
    """Where DRILLPDFse (the pdfminer.six lines.json producer) lives: env
    DRILLPDFSE_DIR, else ~/DRILLPDFse."""
    import os
    return Path(os.environ.get("DRILLPDFSE_DIR") or
                os.path.expanduser("~/DRILLPDFse"))


def _run_born_digital(pdf: Path) -> str:
    """Execute the born-digital lane: run DRILLPDFse's pdfminer extractor to
    write the sibling `<stem>.lines.json` (real math in OUR coordinate system),
    then build the model from it. Falls back to pdfdrill's own `model` build when
    DRILLPDFse is absent or fails. FREE — no key, no network."""
    import sys as _sys
    note = ""
    lj = _lines_json_path(pdf)
    script = _drillpdfse_dir() / "lines_json.py"
    if script.exists() and not (lj.exists() and lj.stat().st_size > 0):
        try:
            r = subprocess.run([_sys.executable, str(script), str(pdf)],
                               cwd=str(script.parent), capture_output=True,
                               text=True, timeout=900)
            if lj.exists() and lj.stat().st_size > 0:
                note = "pdfminer (DRILLPDFse) → lines.json; "
            else:
                note = ("(DRILLPDFse produced no lines.json — "
                        f"{(r.stderr or r.stdout).strip()[:120]}; using pdfdrill's "
                        "own build) ")
        except Exception as e:                      # noqa: BLE001
            note = f"(DRILLPDFse failed: {e}; using pdfdrill's own build) "
    elif not script.exists():
        note = ("(DRILLPDFse not found at "
                f"{_drillpdfse_dir()} — using pdfdrill's own build; set "
                "$DRILLPDFSE_DIR for the pdfminer math route) ")
    return note + cmd_model(pdf)


def _execute_lane(pdf: Path, d) -> str:
    """Run the chosen OCR lane and return the executor's output. Paid/keyed lanes
    degrade gracefully (their commands return a clear message when creds/keys are
    absent — no spend, no crash)."""
    from . import ocr_router as _r
    label = _r._LANE_LABEL.get(d.lane, d.lane)
    head = f"Route → {label} [{d.cost}] — running…\n"
    if d.lane == "born_digital":
        return head + _run_born_digital(pdf)
    if d.lane == "gemma":
        # keyless per-page LLM OCR; vision_router routes the pages to Gemma when
        # NOVITA_API_KEY is set, else to the running agent. Degrades gracefully.
        return head + cmd_visionocr(pdf)
    if d.lane == "mathpix":
        m = cmd_mathpix(pdf, force=True)            # graceful when no creds
        return head + m + "\n" + cmd_model(pdf)
    return head + "unclassified — run `pdfdrill size` first."


def _pdfimages_count(pdf: Path, sc: "Sidecar") -> int:
    """Number of embedded raster images (`pdfimages -list` rows), cached in the
    sidecar. Returns -1 when pdfimages is unavailable."""
    cached = sc.get_evidence("image_count")
    if cached is not None:
        return cached
    try:
        out = subprocess.run(["pdfimages", "-list", str(pdf)],
                             capture_output=True, text=True, timeout=60)
        rows = out.stdout.strip().splitlines()
        n = max(0, len(rows) - 2)          # minus 2 header rows
    except Exception:                        # noqa: BLE001
        n = -1
    sc.set_evidence("image_count", n)
    sc.save()
    return n


def _format_ls(rows: list, images: bool) -> str:
    """Compact shallow-scan table, led by the PRODUCER (the triage signal)."""
    if not rows:
        return "No PDFs."
    hdr = f"{'file':<40} {'pages':>5} {'MB':>6}  {'text?':<7} producer"
    if images:
        hdr = (f"{'file':<40} {'pages':>5} {'MB':>6}  {'text?':<7} {'imgs':>5}  "
               f"producer")
    lines = [hdr, "-" * len(hdr)]
    for r in rows:
        tl = r.get("text")
        text = "text" if tl else ("NO text/scan" if tl is False else "?")
        prod = (r.get("producer") or "—")[:48]
        cols = (f"{r['name'][:40]:<40} {r.get('pages', 0):>5} "
                f"{r.get('mb', 0):>6.1f}  {text:<7} ")
        if images:
            n = r.get("images")
            cols += f"{('—' if n in (None, -1) else n):>5}  "
        lines.append(cols + prod)
    return "\n".join(lines)


def cmd_ls(directory: Path, images: bool = False) -> str:
    """Shallow-scan a folder: run pdfinfo (`size`) on every PDF, store it in each
    file's sidecar, and report a compact table led by the PRODUCER.

    The shallowest drill rung — the cheapest useful pass over a whole directory
    before deciding which files deserve a deeper drill. `size` is cached, so
    re-running `ls` is fast. `--images` adds the `pdfimages -list` count.
    """
    d = Path(directory)
    if not d.is_dir():
        return f"Not a directory: {d}"
    pdfs = sorted(p for p in d.glob("*.pdf") if p.is_file())
    if not pdfs:
        return f"No PDFs in {d}."
    rows = []
    for pdf in pdfs:
        try:
            cmd_size(pdf)                    # idempotent: pdfinfo → sidecar
        except Exception:                    # noqa: BLE001
            pass
        sc = Sidecar(pdf)
        row = {
            "name": pdf.name,
            "pages": sc.get_evidence("pages", 0),
            "mb": (sc.file_size or pdf.stat().st_size) / 1_000_000,
            "text": sc.get_evidence("text_layer"),
            "producer": sc.get_evidence("producer", ""),
        }
        if images:
            row["images"] = _pdfimages_count(pdf, sc)
        rows.append(row)
    n_scan = sum(1 for r in rows if r["text"] is False)
    head = (f"{len(pdfs)} PDF(s) in {d} — {n_scan} scanned (need OCR), "
            f"{len(pdfs) - n_scan} with a text layer.\n")
    return head + _format_ls(rows, images)


def cmd_route(pdf: Path, run: bool = False) -> str:
    """Pick the OCR-lane automatically and, with --run, EXECUTE it.

    The state machine classifies the document from the cheap `size` signals and
    picks the extraction lane — born-digital → pdfminer/text-layer (FREE);
    scanned & ≤20 pages → Gemma 4 (5-parallel); scanned & larger → MathPix (the
    only viable OCR for large books). Auto-chains `size`.

    Without `--run` it reports the decision (and the command per lane) so you
    never hand-pick per document. With `--run` it runs the chosen lane: the free
    born-digital lane always; the paid/keyed lanes degrade gracefully to a clear
    message when their creds/key are absent (no accidental spend).
    """
    from . import ocr_router as _r
    sc = Sidecar(pdf)
    if not sc.has(SIZE_KNOWN):
        cmd_size(pdf)                      # cheap; fills text_layer/needs_ocr/pages
        sc = Sidecar(pdf)
    d = _r.route_for_sidecar(sc)
    sc.set_evidence("ocr_route", {"lane": d.lane, "cost": d.cost, "reason": d.reason})
    sc.save()
    if not run:
        return _r.format_decision(d, pdf.name) + "\n  (add --run to execute this lane now)"
    return _r.format_decision(d, pdf.name) + "\n" + _execute_lane(pdf, d)


# Pages to sample when page 1 is text-poor (a cover-page figure). A born-digital
# book/paper has a near-empty page 1 but real text within the first few pages.
_TEXT_SAMPLE_PAGES = 5


def _text_layer_from_counts(first_page_chars: int, sampled_chars: int) -> bool:
    """Pure text-layer decision. Born-digital iff page 1 has real characters OR
    the first few pages do (a cover-page FIGURE leaves page 1 text-poor while the
    document still has a text layer). A scan is near-zero across all pages, so the
    16-char floor over several pages tolerates a stray watermark without flipping."""
    return first_page_chars >= 4 or sampled_chars >= 16


def _probe_text_layer(pdf: Path) -> tuple[bool, int, int]:
    """Cheap scan detector. Returns (has_text_layer, n_fonts, first_page_chars).

    A born-digital PDF has extractable text; a scan has none (just a page-image).
    We sample the FIRST FEW pages, not page 1 alone, because a cover-page figure
    (common in books/arXiv papers) leaves page 1 text-poor even though the doc is
    born-digital. Fonts corroborate but don't decide (a stray stamp font on an
    image PDF must not flip it to has-text). first_page_chars is still reported
    (page 1) for the size summary."""
    n_fonts = 0
    try:
        fout = subprocess.run(["pdffonts", str(pdf)], capture_output=True,
                              text=True, timeout=30)
        rows = fout.stdout.strip().splitlines()
        n_fonts = max(0, len(rows) - 2)  # minus the 2 header rows
    except Exception:
        pass

    def _chars(last_page: int) -> int:
        try:
            tout = subprocess.run(
                ["pdftotext", "-l", str(last_page), str(pdf), "-"],
                capture_output=True, text=True, timeout=60)
            return len("".join(tout.stdout.split()))
        except Exception:
            return 0

    first_page_chars = _chars(1)
    # Only pay the extra multi-page extraction when page 1 is text-poor.
    sampled = first_page_chars if first_page_chars >= 4 else _chars(_TEXT_SAMPLE_PAGES)
    has_text = _text_layer_from_counts(first_page_chars, sampled)
    return has_text, n_fonts, first_page_chars


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
        md_blob = _read_md(pdf, sc) or ""
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

    # FREE arxiv route: the abstract lives on the abs page — no MathPix, no text
    # layer needed. Cheapest authoritative source, so try it before anything else.
    arxiv_id = _arxiv_id_for(pdf, sc)
    if arxiv_id:
        try:
            from . import sources
            meta = sources.fetch_arxiv_metadata(arxiv_id)
            abstract_text = (meta.get("abstract") or "").strip()
            if abstract_text:
                if sc.has(ABSTRACT_ABSENT):
                    sc._data["facts"] = [f for f in sc._data.get("facts", [])
                                         if f != ABSTRACT_ABSENT]
                sc.set_evidence("abstract", abstract_text)
                sc.set_evidence("abstract_method", "arxiv-abs-page")
                sc.set_evidence("abstract_search_scope", "arxiv")
                if meta.get("title"):
                    sc.set_evidence("arxiv_title", meta["title"])
                if meta.get("authors"):
                    sc.set_evidence("arxiv_authors", meta["authors"])
                if meta.get("primary_category"):
                    sc.set_evidence("arxiv_primary_category", meta["primary_category"])
                sc.add_fact(ABSTRACT_KNOWN)
                sc.save()
                return _format_abstract(sc)
        except Exception:
            pass  # network blocked / parse miss → fall through to local routes

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
        md_blob = _read_md(pdf, sc) or ""
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


def _arxiv_id_for(pdf: Path, sc: Sidecar) -> str | None:
    """The arXiv id for this input, if any: from the sidecar (a resolved URL),
    else parsed from the filename stem (a downloaded/named `<id>.pdf`)."""
    from . import sources
    aid = sc.get_evidence("source_arxiv_id")
    if aid:
        return aid
    return sources.parse_arxiv_id(pdf.stem)


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


_REF_SOURCE_LABEL = {
    "bib": "from .bib (gold BibTeX)",
    "bbl": "from .bbl (compiled)",
    "bibitem": "from inline \\bibitem",
    "text": "from text (OCR/printed, heuristic)",
    "unknown": "source unrecorded",
}


def _format_bibliography_state(ref_props: list[dict], cites: int = 0) -> list[str]:
    """Bibliography lines for `status`: count + per-SOURCE breakdown (where each
    BibTeX record came from — .bib / .bbl / inline \\bibitem / printed text) +
    how many carry full BibTeX, and a WARNING for any web-enriched via bibfetch
    (Perplexity/LLM — may introduce errors). Pure over a list of Reference
    props."""
    if not ref_props:
        return []
    from collections import Counter
    src = Counter((p.get("ref_source") or "unknown") for p in ref_props)
    with_bibtex = sum(1 for p in ref_props if p.get("bibtex"))
    with_year = sum(1 for p in ref_props if p.get("year"))
    fetched = sum(1 for p in ref_props if p.get("bibfetched"))
    src_str = ", ".join(f"{n} {_REF_SOURCE_LABEL.get(k, k)}"
                        for k, n in src.most_common())
    lines = [f"  bibliography ({len(ref_props)} entries: {src_str})",
             f"    {with_bibtex} with full BibTeX, {with_year} with a year, "
             f"{cites} in-text citations linked"]
    if fetched:
        lines.append(
            f"    ⚠ {fetched} web-enriched via bibfetch "
            f"(Perplexity/LLM — may introduce errors; verify against the source)")
    return lines


def _format_environments(env: dict) -> list[str]:
    """LaTeX-environment lines for `status` from `doc.meta["environments"]`:
    the used census, theorem-like declarations (\\newtheorem) with theorem/proof
    block counts (LEAN4-export candidates), and custom \\newenvironment defs."""
    if not env:
        return []
    used = env.get("used") or {}
    nthm = env.get("newtheorem") or []
    nenv = env.get("newenvironment") or []
    thm_blocks = env.get("theorem_blocks") or 0
    proof = env.get("proof_blocks") or 0
    lines = [f"  LaTeX environments ({len(used)} distinct used, "
             f"{sum(used.values())} total)"]
    if nthm:
        names = ", ".join(t["name"] for t in nthm)
        lines.append(f"    theorem-like declared (\\newtheorem): {names}")
    if thm_blocks or proof:
        lines.append(f"    {thm_blocks} theorem/lemma/def block(s) + {proof} "
                     f"proof block(s) — theorem–proof pairs (LEAN4 candidates)")
    if nenv:
        visible = [n for n in nenv if "@" not in n]      # hide style-internal @-names
        shown = ", ".join(visible[:10]) + ("…" if len(visible) > 10 else "")
        lines.append(f"    {len(nenv)} custom \\newenvironment(s)"
                     + (f": {shown}" if shown else ""))
    return lines


def _model_status_lines(sc: "Sidecar") -> list[str]:
    """Bibliography + LaTeX-environment status — one DocGraph load (no rebuild)."""
    model_path = _model_path(sc)
    if not model_path.exists():
        if sc.has(BIBLIOGRAPHY_BUILT):
            n = sc.get_evidence("bibliography_entries", 0) or 0
            return [f"  bibliography ({n} entries; model file unavailable)"] if n else []
        return []
    try:
        from . import model_io
        g = model_io.load_docgraph(model_path)
    except Exception:                                          # noqa: BLE001
        return []
    lines: list[str] = []
    lines += _format_genre(g.meta.get("genre") or {})
    if sc.has(BIBLIOGRAPHY_BUILT):
        cites = sc.get_evidence("bibliography_cites", 0) or 0
        lines += _format_bibliography_state(
            [r.props for r in g.of_type("Reference")], cites)
    lines += _format_environments(g.meta.get("environments") or {})
    return lines


def _format_genre(genre: dict) -> list[str]:
    """The one-line genre certificate for `status` (pure): entrytype +
    confidence + the top evidence — so a mis-classification is visible at a
    glance. Silent when the genre pass has not run."""
    if not genre or not genre.get("entrytype"):
        return []
    ev = "; ".join(genre.get("evidence", [])[:3])
    return [f"  genre: @{genre['entrytype']} "
            f"(confidence {genre.get('confidence', 0):.2f}"
            + (f"; {ev}" if ev else "") + ")"]


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
    parts.extend(_model_status_lines(sc))
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
    if CONTINUITY_BUILT in facts:
        cont = sc.get_evidence("continuity") or {}
        n_seq = sc.get_evidence("continuity_pages_with_seq", 0)
        parts.append(f"  continuity ({n_seq}/{len(cont)} pages carry a Seite N marker):")
        for page_no in sorted(cont, key=lambda k: int(k)):
            i = cont[page_no]
            if i.get("seq_in_doc") is None and not i.get("is_continuation"):
                continue
            seq = (f"Seite {i['seq_in_doc']}"
                   + (f"/{i['doc_total']}" if i.get("doc_total") else "")
                   ) if i.get("seq_in_doc") is not None else "Seite ?"
            cont_s = " (→cont.)" if i.get("is_continuation") else ""
            parts.append(f"    p{int(page_no):>2}: {seq}{cont_s}")

    # Surface the openable artifacts so they appear as clickable links in the
    # drillui Outputs panel (the giant model JSON is skipped — see `artifacts --all`).
    arts = _list_artifacts(sc)
    if arts:
        parts.append("\nFiles (open in a tab / click in the Outputs panel):")
        for p in arts:
            parts.append(f"  {p.relative_to(sc.pdf_path.parent)}  "
                         f"({p.stat().st_size / 1024:.0f} KB)")

    last = sc.last_node
    parts.append(f"\nLast action: {last}. {len(sc.transitions)} transitions logged.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Extraction commands
# ---------------------------------------------------------------------------

def _md_filename(pdf: Path, sc: "Sidecar") -> str:
    """The doc's ONE markdown file name: `<bibkey>.md` (findable / clickable)."""
    try:
        return f"{resolve_bibkey(pdf, None, sc)}.md"
    except Exception:                                      # noqa: BLE001
        return f"{pdf.stem}.md"


def _read_md(pdf: Path, sc: "Sidecar") -> "str | None":
    """The doc's markdown. Canonical `<bibkey>.md`, falling back to the legacy
    `md.md` blob so folders drilled before the single-file consolidation still
    read. None when neither exists."""
    try:
        named = sc.read_blob(_md_filename(pdf, sc))
    except Exception:                                      # noqa: BLE001
        named = None
    return named if named is not None else sc.read_blob("md.md")


def _md_note(pdf: Path, sc: "Sidecar") -> str:
    """The findable-path note for the doc's `<bibkey>.md` (already on disk)."""
    try:
        p = sc.blob_dir / _md_filename(pdf, sc)
        return (f"\n→ Markdown file: {_artref(sc, p)}  "
                f"(open it directly; clickable in the drillui Outputs panel).")
    except Exception:                                      # noqa: BLE001
        return ""


def _ensure_named_md(pdf: Path, sc: "Sidecar", md_text: str) -> str:
    """Make sure `<bibkey>.md` exists (migrating a legacy `md.md`-only folder on
    re-serve) and return its findable-path note — WITHOUT touching the layer or
    facts (the caller owns those)."""
    try:
        p = sc.blob_dir / _md_filename(pdf, sc)
        if not p.exists():
            sc.blob_dir.mkdir(parents=True, exist_ok=True)
            p.write_text(md_text or "", encoding="utf-8")
    except Exception:                                      # noqa: BLE001
        pass
    return _md_note(pdf, sc)


def _write_md(pdf: Path, sc: "Sidecar", md_text: str, *, source: str) -> str:
    """Write the doc's markdown to the SINGLE canonical `<bibkey>.md`, point the
    `md` layer at it, mark MD_BUILT, save, and return the findable-path note.

    This is the one writer — it replaces the former duplicate pair (an internal
    `md.md` blob PLUS a byte-identical `<bibkey>.md` copy). `<bibkey>.md` is both
    the findable/clickable file and what every reader (`fetch`/`toc`/`abstract`/
    `render`) reads via `_read_md`."""
    name = _md_filename(pdf, sc)
    sc.write_blob(name, md_text or "")
    sc.set_layer("md", {"blob": name, "words": len((md_text or "").split()),
                        "source": source,
                        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    sc.add_fact(MD_BUILT)
    sc.save()
    return _md_note(pdf, sc)


def _serve_mathpix_md(pdf: Path, sc: "Sidecar", *, scanned: bool = True) -> str | None:
    """If MathPix already produced `<stem>.md`, serve it into the md layer and
    return the prose result; else None. Used both for a SCANNED doc and to
    PREFER the user's MathPix markdown over the lossy text-layer engine."""
    mathpix_md = pdf.parent / f"{pdf.stem}.md"
    if not (mathpix_md.exists() and mathpix_md.stat().st_size > 0):
        return None
    md_text = mathpix_md.read_text(encoding="utf-8")
    why = ("scanned (no text layer)" if scanned
           else "born-digital, but the MathPix markdown you generated is preferred "
                "over the text-layer extraction")
    return (f"Markdown from MathPix{' OCR' if scanned else ''} "
            f"({len(md_text.split())} words) — {pdf.name} is {why}, served from "
            f"{mathpix_md.name}. Use `pdfdrill fetch {pdf.name} md` to retrieve."
            + _write_md(pdf, sc, md_text, source="mathpix"))


def _is_latex_source_model(model_path: Path) -> bool:
    if not model_path.exists():
        return False
    try:
        m = load_model(model_path).meta or {}
    except Exception:
        return False
    return ("LaTeX source" in (m.get("source_path") or "")) or bool(m.get("latex_source_dir"))


def _md_from_latex_source(pdf: Path, sc: "Sidecar") -> "str | None":
    """Clean Markdown from the author's LaTeX docmodel, or None if no LaTeX source
    is available. RULE: if LaTeX is available it MUST be used — the PDF text-layer
    has line-break hyphenation, no isolated abstract, and no bibliography; the
    LaTeX source has none of those. Builds the source model (arXiv → e-print) +
    bibliography, projects the docmodel markdown, and renders the per-format
    transclusions for Markdown ({{…||CIT}}→[CITATION: key], {{…||FO}}→[FORMULA N];
    the formulas are listed in the trailing glossary)."""
    model_path = _model_path(sc)
    if not _is_latex_source_model(model_path):
        if not _arxiv_id_for(pdf, sc):
            return None                      # not arXiv, no source model → engine path
        cmd_model(pdf)                       # arXiv → builds from the LaTeX e-print
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
        if not _is_latex_source_model(model_path):
            return None                      # didn't actually build from source
    if not sc.has(BIBLIOGRAPHY_BUILT):
        cmd_bibliography(pdf)                 # references + linked citations (gold)
        sc = Sidecar(pdf)

    from docops.projectors.llm_compact import LLMCompactProjector
    from docops.base import OperatorConfig
    from docops import transclusion_render as _tr
    doc = load_model(_model_path(sc))
    md = LLMCompactProjector(OperatorConfig(
        op="projector", classname="LLMCompactProjector")).project(doc)

    def _lk(title, template):                 # citation transclusion → the citekey
        if template == "CIT":
            mm = re.search(r"_REF_(.+)$", title)
            return mm.group(1) if mm else None
        return None
    md = _tr.render(md, "typed_gloss", _lk)

    return (f"Markdown from the author's LaTeX source ({len(md.split())} words) — "
            f"no OCR/text-layer, so NO line-break hyphenation, an isolated "
            f"`## Abstract`, and the bibliography are included."
            + _write_md(pdf, sc, md, source="latex"))


def cmd_md(pdf: Path, pages: str | None = None) -> str:
    """Build Markdown. Prefers the author's LaTeX (arXiv/source) — clean, no
    hyphenation, isolated abstract, bibliography — else the PDF text-layer."""
    sc = Sidecar(pdf)

    # RULE: if the LaTeX source is available, use it (not the lossy text-layer).
    if pages is None:
        latex_md = _md_from_latex_source(pdf, sc)
        if latex_md is not None:
            return latex_md
        sc = Sidecar(pdf)

    if not sc.has(SIZE_KNOWN):
        cmd_size(pdf)
    if not sc.has(FONTS_KNOWN):
        cmd_fonts(pdf)

    sc = Sidecar(pdf)

    # A SCANNED PDF has no text layer — pdfplumber/pdftotext markdown is empty.
    # If MathPix already produced `<stem>.md`, SERVE that (the real OCR markdown)
    # into the md layer so `md`/`fetch md` return content, not an empty blob.
    if sc.get_evidence("needs_ocr"):
        served = _serve_mathpix_md(pdf, sc)
        if served is not None:
            return served
        # No OCR markdown yet. If MathPix keys are configured, JUST RUN IT and
        # return the result — no discussion about OCR (the user's instruction:
        # keys present ⇒ produce the result). Paid step, so gated on real creds.
        from . import mathpix_creds
        if mathpix_creds.available():
            cmd_mathpix(pdf)
            sc = Sidecar(pdf)
            served = _serve_mathpix_md(pdf, sc)
            if served is not None:
                return served
        # keyless (or MathPix produced nothing, e.g. an arXiv skip) → the
        # actionable hint, only when we genuinely can't produce the markdown.
        lp = _lines_json_path(pdf)
        hint = (f"A MathPix lines.json is present but no `{pdf.stem}.md` — re-run "
                f"`pdfdrill mathpix {pdf.name}`." if lp.exists() else
                f"Run `pdfdrill mathpix {pdf.name}` (OCR markdown; needs MathPix "
                f"creds) or `pdfdrill ocr {pdf.name}` (keyless tesseract).")
        return (f"{pdf.name} is a SCANNED PDF (no text layer) — `pdfdrill md` "
                f"extracts the text layer and finds nothing. {hint}")

    # PREFER the user's MathPix markdown (<stem>.md) over the text-layer engine,
    # which can mis-flag nearly every short line of an old/2-column report as a
    # heading. Only for whole-doc (pages is None); the engine handles page ranges.
    if pages is None:
        served = _serve_mathpix_md(pdf, sc, scanned=False)
        if served is not None:
            return served

    if sc.has(MD_BUILT) and pages is None:
        md_meta = sc.get_layer("md") or {}
        blob = _read_md(pdf, sc)
        if blob:
            words = len(blob.split())
            return (f"Markdown already extracted ({words} words across "
                    f"{sc.page_count} pages). Stored as layer `md`.\n\nUse "
                    f"`pdfdrill fetch {pdf.name} md` to retrieve."
                    + _ensure_named_md(pdf, sc, blob))

    t0 = time.monotonic()

    # Ensure a COMPLETE chars.json exists — regenerate a truncated one (a killed
    # write on a huge born-digital book left a partial dump that poisoned md).
    chars_path = _chars_json_path(pdf)                 # in the .drill/ sidecar folder
    if not _json_file_looks_complete(chars_path):
        if chars_path.exists():
            try:
                chars_path.unlink()
            except OSError:
                pass
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

    # Save — the ONE canonical <bibkey>.md (no separate md.md blob).
    sc = Sidecar(pdf)
    _md_name = _md_filename(pdf, sc)
    sc.write_blob(_md_name, md_text)
    ir_json = ctx.to_json()
    sc.write_blob("ir.json", ir_json)

    words = len(md_text.split())
    math_i = sum(1 for s in ctx.L4 if s.kind == "math_inline")
    math_d = sum(1 for s in ctx.L4 if s.kind == "math_display")
    refs = sum(1 for s in ctx.L3 if s.kind in ("citation", "eq_number", "struct_ref"))

    sc.set_layer("md", {
        "blob": _md_name,
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
    summary += _md_note(pdf, sc)
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

    # ATOMIC write: a 1000-page book's .chars.json is 600-800 MB; a non-atomic
    # dump killed mid-write (e.g. a timeout) left a truncated file that poisoned
    # every later md/drill. Dump to a temp then os.replace so it's all-or-nothing.
    import os as _os
    chars_path = _chars_json_path(pdf)                 # .drill/ sidecar folder
    chars_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = chars_path.with_name(f"{chars_path.name}.tmp-{_os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json_mod.dump(
                {"source": pdf.name, "total_pages": len(pages_data), "pages": pages_data},
                f, default=default, ensure_ascii=False,
            )
        _os.replace(tmp, chars_path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _chars_json_path(pdf: Path) -> Path:
    """The pdfplumber char dump's location: inside the `.drill/` sidecar folder,
    NOT next to the PDF (the 600-800 MB dumps cluttered the working directory). A
    legacy dump beside the PDF is migrated into `.drill/` on first access."""
    import os as _os
    from .sidecar import blob_dir_for
    drill = blob_dir_for(Path(pdf).resolve())[0]     # layout-aware, never hardcoded legacy
    new = drill / "chars.json"
    legacy = pdf.with_suffix(".chars.json")
    if legacy.exists() and not new.exists():
        drill.mkdir(parents=True, exist_ok=True)
        try:
            _os.replace(legacy, new)                  # atomic move into the sidecar
        except OSError:
            pass
    return new


def _json_file_looks_complete(path: Path) -> bool:
    """Cheap completeness check for a large JSON dump WITHOUT parsing it: a
    complete object ends with `}` (a truncated write ends mid-content). Reads
    only the tail — parsing an 800 MB file is exactly the cost we're avoiding."""
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size == 0:
        return False
    with open(path, "rb") as f:
        f.seek(max(0, size - 64))
        tail = f.read().rstrip()
    return tail.endswith(b"}")


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
        blob = _read_md(pdf, sc)
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
    try:
        info = fetch_pdfinfo_struct(pdf)
    except FileNotFoundError:
        return _missing_tool_msg("pdfinfo", "poppler-utils")
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


def _is_placeholder_bib(bib: dict | None) -> bool:
    """A BibTeX record derived from EMPTY embedded PDF metadata — no title and an
    `unknown…` / author-less citekey. Worthless; should be recomputed/augmented."""
    if not bib:
        return True
    return (not (bib.get("title") or "").strip()
            and (not (bib.get("author") or "").strip()
                 or str(bib.get("citekey", "")).startswith("unknown")))


def _arxiv_year(aid: str) -> str:
    """Publication year encoded in an arXiv id (new-style YYMM `2305.04710` →
    2023; old-style `math/0309136` → 2003)."""
    m = re.match(r"(\d{2})\d{2}", aid or "")
    if m:
        return "20" + m.group(1)
    m = re.search(r"/(\d{2})\d{2}", aid or "")
    return "20" + m.group(1) if m else ""


def _augment_bibtex(bib: dict, pdf: Path, sc: "Sidecar") -> str:
    """Fill a pdfinfo-derived record from richer, FREE sources — the fix for an
    arXiv input giving `@misc{unknown2023}` (the embedded PDF metadata is empty,
    but arXiv has title/authors for free). Recomputes the citekey. Returns a
    warning string when the record is STILL a placeholder (deep drill needed)."""
    from .pdfinfo_layers import _make_citekey
    from . import sources

    aid = (sc.get_evidence("source_arxiv_id")
           or sources.bare_arxiv_id(pdf.stem) or sources.parse_arxiv_id(pdf.stem))
    if aid:
        meta = None
        if sc.get_evidence("arxiv_title") or sc.get_evidence("arxiv_authors"):
            meta = {"title": sc.get_evidence("arxiv_title") or "",
                    "authors": sc.get_evidence("arxiv_authors") or [],
                    "primary_category": sc.get_evidence("arxiv_primary_category") or ""}
        else:                                    # free abs-page metadata (graceful if blocked)
            try:
                meta = sources.fetch_arxiv_metadata(aid)
                if meta.get("title"):
                    sc.set_evidence("arxiv_title", meta["title"])
                if meta.get("authors"):
                    sc.set_evidence("arxiv_authors", meta["authors"])
                if meta.get("primary_category"):
                    sc.set_evidence("arxiv_primary_category", meta["primary_category"])
            except Exception:
                meta = None
        if meta:
            if meta.get("title"):
                bib["title"] = meta["title"]
            if meta.get("authors"):
                bib["author"] = " and ".join(meta["authors"])
            # The canonical arXiv @misc form: eprint / archivePrefix / primaryClass.
            bib["entry_type"] = "misc"
            bib["arxiv_id"] = aid
            bib["eprint"] = aid
            bib["archive_prefix"] = "arXiv"
            bib["primary_class"] = meta.get("primary_category", "") or bib.get("primary_class", "")
            bib["publisher"] = ""            # never the pdfTeX producer for an arXiv paper
            bib["url"] = sources.arxiv_urls(aid).get("abs", bib.get("url", ""))
            if not bib.get("year"):
                bib["year"] = _arxiv_year(aid)

    # Secondary (offline): the document title captured into the model meta.
    if not (bib.get("title") or "").strip():
        mp = _model_path(sc)
        if mp.exists():
            try:
                from . import model_io
                t = (model_io.load_docgraph(mp).meta or {}).get("title")
                if t:
                    bib["title"] = t
            except Exception:
                pass

    bib["citekey"] = _make_citekey(bib.get("author", ""), bib.get("year", ""),
                                   bib.get("title", ""))
    if _is_placeholder_bib(bib):
        return ("\n⚠ This is a PLACEHOLDER — the PDF's embedded metadata has no "
                "title/author and no richer source was available. For a real "
                "record run a deeper step first: `pdfdrill abstract` (free; arXiv "
                "abs page) for title/authors, or `pdfdrill model` + `pdfdrill "
                "bibsource`/`bibfetch`. `bibtex` alone reads only embedded metadata.")
    return ""


def cmd_bibtex(pdf: Path) -> str:
    """Derive a BibTeX record — from the embedded PDF metadata, AUGMENTED by the
    free arXiv abs-page metadata (title/authors) and the drilled title when the
    embedded metadata is empty (otherwise an arXiv PDF yields `@misc{unknown2023}`
    because its Info dict has no title/author). Warns when still a placeholder."""
    from .pdfinfo_layers import derive_bibtex

    # A combined store (from `pdfdrill combine`) isn't a PDF — fan out to each
    # member doc (the multi-doc/drillui case where `bibtex` ran on the .docpack
    # and got @misc{unknown} because the store has no embedded metadata).
    combo = _load_combined_store(pdf)
    if combo is not None:
        _, meta = combo
        srcs = meta.get("sources") or []
        if not srcs:
            return (f"{Path(pdf).name} is a combined store of "
                    f"{', '.join(meta.get('combined_docs') or [])}; `bibtex` applies "
                    f"to individual documents — run it on a source PDF, or re-make "
                    f"the store with the current `pdfdrill combine` (records member "
                    f"paths).")
        out = [f"BibTeX for {len(srcs)} document(s) in {Path(pdf).name}:"]
        for s in srcs:
            out.append(cmd_bibtex(Path(s["path"])))
        return "\n\n".join(out)

    sc = Sidecar(pdf)
    if not sc.has(PDFINFO_KNOWN):
        cmd_pdfinfo(pdf)
        sc = Sidecar(pdf)
    # Trust the cache only if it's a REAL record — never re-serve a placeholder.
    if sc.has(BIBTEX_KNOWN) and not _is_placeholder_bib(sc.bibtex):
        return _format_bibtex(sc.bibtex)

    t0 = time.monotonic()
    bib = derive_bibtex(sc.pdfinfo or {})
    note = _augment_bibtex(bib, pdf, sc)
    sc.set_bibtex(bib)
    sc.add_fact(BIBTEX_KNOWN)

    elapsed = time.monotonic() - t0
    prev = ",".join(sorted(sc.facts - {BIBTEX_KNOWN})) or "INIT"
    sc.log_transition("bibtex", prev, BIBTEX_KNOWN, cost_ms=elapsed * 1000,
                      detail=f"citekey={bib['citekey']}")
    sc.save()
    return _format_bibtex(bib) + note


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
    if not _read_md(pdf, sc):
        return "Markdown not available — `pdfdrill md` failed."

    out_dir = sc.blob_dir / "render"
    pdf_out = out_dir / "rendered.pdf"
    if pdf_out.exists() and not force:
        rel = pdf_out.relative_to(pdf.resolve().parent)
        return (f"Rendered PDF already present: {rel} "
                f"({pdf_out.stat().st_size//1024} KB). Re-render with `--force`.")

    if not shutil.which("pandoc") or not shutil.which("lualatex"):
        return "render requires `pandoc` and `lualatex` on PATH."

    # the canonical <bibkey>.md, falling back to a legacy md.md for old folders
    md_path = sc.blob_dir / _md_filename(pdf, sc)
    if not md_path.exists():
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


def cmd_stex(pdf: Path, flavor: str = "latex", compile: bool = False) -> str:
    """Project the semantic graph to enriched LaTeX.

    `flavor="latex"` (default) emits a standard document with all the LaTeX lists
    (acronyms / glossary / Table of Symbols / index) driven by the extracted named
    concepts; `flavor="stex"` emits the sTeX form (smodule / \\symdecl / sdefinition
    / \\symref). `--compile` runs lualatex (+ makeglossaries + makeindex) to prove
    the output. Needs the semantic graph (auto-chains `semantic`)."""
    import shutil
    import subprocess
    from semantic.graph import SemanticGraph
    from semantic import stex as stexproj

    sc = Sidecar(pdf)
    key = resolve_bibkey(pdf, None, sc)
    sem_path = sc.blob_dir / f"{key}.semantic.json"
    if not sem_path.exists():
        cmd_semantic(pdf)
        sc = Sidecar(pdf)
        key = resolve_bibkey(pdf, None, sc)
        sem_path = sc.blob_dir / f"{key}.semantic.json"
    if not sem_path.exists():
        return f"No semantic graph for {pdf.name} (run `pdfdrill semantic` first)."

    g = SemanticGraph.from_dict(json.loads(sem_path.read_text(encoding="utf-8")))
    is_stex = flavor == "stex"
    tex = stexproj.project_stex(g, key) if is_stex else stexproj.project_latex(g, key)
    out = sc.blob_dir / (f"{key}.stex.tex" if is_stex else f"{key}.glossaries.tex")
    out.write_text(tex, encoding="utf-8")
    rel = out.relative_to(sc.pdf_path.parent)

    note = ""
    if compile:
        if not shutil.which("lualatex"):
            note = " (lualatex not installed — skipped compile)"
        else:
            d = out.parent
            base = out.stem
            r = lambda *c: subprocess.run(c, cwd=d, capture_output=True, text=True, timeout=300)
            r("lualatex", "-interaction=nonstopmode", "-halt-on-error", out.name)
            if not is_stex:
                r("makeglossaries", base); r("makeindex", base + ".idx")
            r("lualatex", "-interaction=nonstopmode", out.name)
            r("lualatex", "-interaction=nonstopmode", out.name)
            pdf_out = d / (base + ".pdf")
            note = (f" Compiled with lualatex → {pdf_out.relative_to(sc.pdf_path.parent)}."
                    if pdf_out.exists() else " ⚠ lualatex did not produce a PDF (see the .log).")

    n_concepts = sum(1 for e in g.entities.values()
                     if e.type.value == "concept" and e.subtype in ("acronym", "term", "symbol"))
    kind = "sTeX (smodule/\\symdecl/sdefinition/\\symref)" if is_stex else \
           "enhanced LaTeX (acronyms/glossary/Table of Symbols/index)"
    return (f"Projected the semantic graph to {kind}: {n_concepts} named concepts → "
            f"{rel}.{note}")


def cmd_lean(pdf: Path, limit: int | None = None, force: bool = False,
             emit_only: bool = False) -> str:
    """Export theorems to Lean 4 — STORE then PROJECT.

    Stage 1 GENERATES Lean per Theorem via the keyless LLM delegation (the Claude
    agent / CLI / sandbox, like `bibfetch`) and STORES it on each Theorem
    (`props['lean4']` + the tiddler `lean4` field). Stage 2 PROJECTS the stored
    code into `<bibkey>.lean` (a Theorem with no stored Lean → a `sorry` stub;
    the paired proof is a LaTeX comment). `--emit-only` skips generation and just
    re-projects from stored code. Needs theorem-like environments from a
    LaTeX-source build. Auto-chains `model`."""
    from . import lean_export, llm_delegate as D

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if _stale_or_absent(sc, model_path, _lines_json_path(pdf)):
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."
    doc = load_model(model_path)
    theorems = [o for o in doc.objects.values() if o.type == "Theorem"]
    if not theorems:
        return (f"No Theorem objects in {pdf.name} — Lean export needs theorem-like "
                f"environments (\\begin{{theorem}}/lemma/…) from a LaTeX-source build.")
    key = resolve_bibkey(pdf, None, sc)

    gen_note = ""
    if not emit_only:
        try:
            res = lean_export.generate_lean(
                doc, drill_dir=sc.blob_dir, limit=limit, force=force)
        except D.DelegateUnavailable as e:
            res = None
            gen_note = (" Generation skipped (no LLM agent/key: "
                        f"{str(e).splitlines()[0]}) — emitting sorry-stubs.")
        if res is not None:
            save_model(model_path, doc)              # persist stored Lean
            if res["deferred"] is not None:
                return (res["deferred"].instruction +
                        f"\n\n{res['generated']}/{res['requested']} Lean translation(s) "
                        f"ready; re-run `pdfdrill lean {pdf.name}` after answering to "
                        f"finish and emit the .lean.")
            gen_note = (f" Generated {res['generated']} new Lean theorem(s) "
                        f"({res['answered']}/{res['requested']} answered).")

    out = sc.blob_dir / f"{key}.lean"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(lean_export.project_lean(doc), encoding="utf-8")
    stored = sum(1 for o in theorems if o.props.get("lean4"))
    return (f"Lean 4 export: {len(theorems)} theorem(s), {stored} with stored Lean "
            f"(the rest are `sorry` stubs) → {out.relative_to(sc.pdf_path.parent)}.{gen_note} "
            f"Lean is LLM-sourced (store-then-project) — VERIFY before trusting. "
            f"Re-run `pdfdrill tiddlers {pdf.name}` to carry the lean4 field onto the "
            f"theorem tiddlers.")


def cmd_scikgtex(pdf: Path, compile: bool = False) -> str:
    """Project the drilled document to SciKGTeX-annotated LaTeX, so the compiled
    PDF carries ORKG contribution metadata as XMP/RDF (title/authors/research
    field + the five research-contribution roles + numeric facts + bib-DOI links).
    `--compile` runs lualatex (needs `scikgtex.sty`/`.lua` — in texmf, or the repo's
    `tests/fixtures/scikgtex/`). Auto-chains `model`."""
    import shutil
    import subprocess
    from docmodel.core import Document
    from docops.base import OperatorConfig
    from docops.projectors.scikgtex import SciKGTeXProjector

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not model_path.exists():
        cmd_model(pdf)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."
    key = resolve_bibkey(pdf, None, sc)
    doc = load_model(model_path)
    # enrich title/authors/field from the sidecar (the free arXiv-abs metadata that
    # `abstract` fetched) when the OCR-built model doesn't carry them.
    if not doc.meta.get("title") and sc.get_evidence("arxiv_title"):
        doc.meta["title"] = sc.get_evidence("arxiv_title")
    if not doc.meta.get("authors") and sc.get_evidence("arxiv_authors"):
        doc.meta["authors"] = sc.get_evidence("arxiv_authors")
    if not doc.meta.get("primary_category") and sc.get_evidence("arxiv_primary_category"):
        doc.meta["primary_category"] = sc.get_evidence("arxiv_primary_category")

    # fold the MSC/PhySH subject tags from `pdfdrill classify` (sidecar) into the
    # SciKGTeX XMP, if a classification has been run.
    params = {}
    cls = sc.get_evidence("classification") or {}
    msc = [f"{h['code']} {h['pref']}".strip() for h in (cls.get("msc_top") or [])[:8]]
    physh = [h["pref"] for h in (cls.get("per_source", {}).get("physh") or [])[:6] if h.get("pref")]
    if msc:
        params["msc_subjects"] = msc
    if physh:
        params["physh_subjects"] = physh

    proj = SciKGTeXProjector(OperatorConfig(op="projector",
                                            classname="SciKGTeXProjector", params=params))
    tex = proj.project(doc)
    out = sc.blob_dir / f"{key}.scikg.tex"
    out.write_text(tex, encoding="utf-8")
    c = proj.counters
    summary = (f"{c.get('contributions', 0)} contribution role(s), "
               f"{c.get('fact', 0)} numeric fact(s), {c.get('doi_uri', 0)} DOI link(s)")
    if c.get("subjects"):
        summary += (f", {len(msc)} MSC + {len(physh)} PhySH subject tag(s) "
                    f"from classify")
    rel = out.relative_to(sc.pdf_path.parent)

    note = ""
    if compile:
        if not shutil.which("lualatex"):
            note = " (lualatex not installed — emitted only)"
        else:
            # locate scikgtex: texmf, else the repo fixtures (dev convenience)
            fix = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "scikgtex"
            have_texmf = subprocess.run(["kpsewhich", "scikgtex.sty"],
                                        capture_output=True).stdout.strip()
            if not have_texmf and (fix / "scikgtex.sty").exists():
                for f in ("scikgtex.sty", "scikgtex.lua"):
                    shutil.copy(fix / f, sc.blob_dir / f)
            elif not have_texmf:
                return (f"Wrote {rel} ({summary}). To compile, install SciKGTeX "
                        f"(github.com/Christof93/SciKGTeX) and rerun with --compile.")
            env = {**__import__("os").environ, "TEXINPUTS": ".:"}
            subprocess.run(["lualatex", "-interaction=nonstopmode", "-halt-on-error", out.name],
                           cwd=sc.blob_dir, capture_output=True, env=env, timeout=300)
            pdf_out = sc.blob_dir / f"{key}.scikg.pdf"
            xmp = sc.blob_dir / f"{key}.scikg.xmp_metadata.xml"
            note = (f" Compiled with lualatex → {pdf_out.relative_to(sc.pdf_path.parent)}"
                    + (f"; ORKG XMP → {xmp.relative_to(sc.pdf_path.parent)}." if xmp.exists()
                       else " (⚠ no XMP — see the .log).")) if pdf_out.exists() \
                   else " ⚠ lualatex did not produce a PDF (see the .log)."

    return (f"Projected to SciKGTeX/ORKG-annotated LaTeX → {rel} ({summary}). "
            f"The compiled PDF embeds an orkg:Paper (title/authors/researchfield) + "
            f"ResearchContributions in XMP/RDF that ORKG / PDF2ORKG can ingest.{note}")


# ---------------------------------------------------------------------------
# llm — driver/inspector for the keyless LLM-delegation fallback
# (the agent-facing SKILL/tool surface; see pdfdrill.llm_delegate)
# ---------------------------------------------------------------------------

def cmd_llm(pdf: Path, action: str = "status") -> str:
    """Inspect / drive the keyless LLM-delegation queue for one PDF.

      pdfdrill llm <pdf>             # status: detected runtime + pending count
      pdfdrill llm <pdf> --show      # dump every open request (prompt+image) as JSON
      pdfdrill llm <pdf> --runtime   # just print the detected delegation runtime

    When pdfdrill runs without API keys inside the Claude.ai sandbox, LLM
    sub-tasks (vision, bibtex, links) are written as request files under
    `<pdf>.drill/llm/`. This command lets the driving Claude agent enumerate
    them in one read (`--show`), answer each by writing `<task_id>.resp.json`,
    then re-run the original command to ingest the answers.
    """
    from collections import Counter
    from . import llm_delegate as D

    if action == "runtime":
        return f"llm-delegation runtime: {D.detect_runtime().value}"

    sc = Sidecar(pdf)
    pend = D.pending_requests(sc.blob_dir)

    if action == "show":
        return json.dumps(pend, ensure_ascii=False, indent=2)

    # status (default)
    rt = D.detect_runtime()
    if not pend:
        return (f"llm-delegation runtime: {rt.value}; no pending requests for "
                f"{pdf.name}.")
    kinds = Counter(p.get("kind", "?") for p in pend)
    kind_s = ", ".join(f"{n} {k}" for k, n in kinds.most_common())
    return (f"llm-delegation runtime: {rt.value}; {len(pend)} pending request(s) "
            f"for {pdf.name} ({kind_s}). Run `pdfdrill llm {pdf.name} --show` to "
            f"dump them, answer each as <task_id>.resp.json under "
            f"{sc.blob_dir.name}/llm/, then re-run the original command.")


# ---------------------------------------------------------------------------
# Keyless vision fallback: delegate each CDN crop to the running Claude agent
# (CLI: synchronous `claude -p`; sandbox: deferred request/response handshake).
# Mirrors cmd_vision's realization-attach + chemistry-bridge ingestion, so a
# delegated result is byte-identical to an OpenAI result downstream.
# ---------------------------------------------------------------------------

def _vision_via_delegate(pdf: Path, doc, todo, targets, sc, model_path,
                         runtime, force: bool) -> str:
    import re as _re
    import hashlib
    from docmodel.core import Realization
    from . import llm_delegate as D, openai_vision, net

    if not todo:
        return (f"Vision (delegated/{runtime.value}): nothing to do — "
                f"{len(targets)} crop(s) already have an 'openai' realization.")

    graph_kw = _re.compile(r"\b(sub)?graph\b", _re.I)
    chem_kw = _re.compile(
        r"\b(molecul\w*|molekül\w*|compound|verbindung\w*|reaktion\w*|reaction"
        r"|synthes\w*|reagent|reagenz\w*|catalyst|katalysator\w*|isomer\w*"
        r"|ligand\w*|monomer\w*|polymer\w*|strukturformel\w*)\b"
        r"|\bscheme\s+\d", _re.I)

    def _ctx(o):
        return " ".join(str((o.props or {}).get(k) or "")
                        for k in ("caption", "title", "raw_text"))

    # Resolve every crop to a LOCAL file the agent / Claude Code can read,
    # then build one LLMTask per crop. CDN URLs are downloaded once; a crop
    # that is already a local path is used as-is. A crop we cannot fetch
    # (blocked host, 404) is skipped and reported.
    crop_dir = sc.blob_dir / "llm" / "crops"
    crop_dir.mkdir(parents=True, exist_ok=True)
    tasks: list = []                      # unique tasks (deduped by content id)
    seen_ids: set = set()
    pairs: list = []                      # (object, url, task) per todo entry
    fetch_errors = 0
    for o, url in todo:
        ctx = _ctx(o)
        is_chem = bool(chem_kw.search(ctx))
        is_graph = (not is_chem) and bool(graph_kw.search(ctx))
        prompt = (openai_vision.CHEM_STRUCTURE_PROMPT if is_chem
                  else openai_vision.GRAPH_TIKZ_PROMPT if is_graph
                  else openai_vision.DEFAULT_PROMPT)
        # local-vs-URL crop source
        local = None
        if url.startswith(("http://", "https://")):
            dest = crop_dir / (hashlib.blake2b(url.encode(), digest_size=12)
                               .hexdigest() + ".img")
            if not dest.exists():
                try:
                    with net.urlopen(url, timeout=30) as r:
                        dest.write_bytes(r.read())
                except Exception:
                    fetch_errors += 1
                    continue
            local = str(dest)
        else:
            local = url if os.path.exists(url) else None
            if local is None:
                fetch_errors += 1
                continue
        t = D.LLMTask(kind="vision", prompt=prompt, image_path=local,
                      meta={"url": url, "chem": is_chem, "graph": is_graph})
        pairs.append((o, url, t))
        if t.task_id not in seen_ids:      # one request per distinct crop+prompt
            seen_ids.add(t.task_id)
            tasks.append(t)

    if not tasks:
        return (f"Vision (delegated/{runtime.value}): could not fetch any of "
                f"{len(todo)} crop(s) ({fetch_errors} fetch error(s)). In a "
                f"sandbox with a blocked CDN host, run `pdfdrill mathpix` where "
                f"the host is reachable, or supply local crops.")

    try:
        results, deferred = D.delegate_batch(
            tasks, drill_dir=sc.blob_dir, runtime=runtime, timeout=120.0)
    except D.DelegateUnavailable as e:
        return str(e)

    if deferred is not None:
        # Sandbox: requests written, hand the agent its instructions and stop.
        return (f"Vision deferred to the {runtime.value} Claude agent: "
                f"{len(deferred.tasks)} request(s) written"
                + (f", {len(results)} already answered" if results else "")
                + (f"; {fetch_errors} crop(s) unfetchable" if fetch_errors else "")
                + ".\n\n" + deferred.instruction)

    # CLI (or sandbox with everything already answered): ingest like cmd_vision.
    # Iterate per-object PAIRS so a crop shared by several objects (deduped to
    # one task) still attaches a realization to each — matching cmd_vision's
    # url_cache behaviour.
    from collections import Counter
    processed = adopted = errors = 0
    by_sel: Counter = Counter()
    for o, url, t in pairs:
        res = results.get(t.task_id)
        if res is None:
            errors += 1
            continue
        selector, code = openai_vision.result_to_latex(res)
        if force:
            o.realizations = [r for r in o.realizations
                              if not (r.role == "latex_candidate"
                                      and r.provenance == "openai"
                                      and (r.props or {}).get("url") == url)]
        o.add_realization(Realization(
            stream="openai", role="latex_candidate", provenance="openai",
            props={"url": url, "selector": selector, "latex": code,
                   "gnuplot": res.get("gnuplot", ""),
                   "csv_data": res.get("csv_data", ""),
                   "delegated": runtime.value},
        ))
        if (selector in ("chemical_structure", "chemical_equation") and code
                and o.type in ("Diagram", "Table")
                and not (o.props.get("latex_code") or "").strip()):
            o.props["latex_code"] = code
            o.props["latex_code_provenance"] = "openai"
            adopted += 1
        processed += 1
        by_sel[selector or "?"] += 1

    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)
    sc.set_evidence("vision_crops_total", len(targets))
    sc.set_evidence("vision_processed",
                    (sc.get_evidence("vision_processed", 0) or 0) + processed)
    prev = ",".join(sorted(sc.facts - {VISION_DONE})) or "INIT"
    sc.add_fact(VISION_DONE)
    sc.save()

    sel_s = ", ".join(f"{n} {s}" for s, n in by_sel.most_common()) or "none"
    adopt_s = (f"; {adopted} chemistry crop(s) adopted into latex_code — run "
               f"`pdfdrill svg {pdf.name}`." if adopted else ".")
    return (f"Vision (delegated to {runtime.value} Claude): read {processed} "
            f"crop(s) ({sel_s}){f', {errors} error(s)' if errors else ''}"
            f"{f', {fetch_errors} unfetchable' if fetch_errors else ''}. "
            f"Attached as the 'openai' provenance{adopt_s} "
            f"Run `pdfdrill compare {pdf.name}` to see the column.")
