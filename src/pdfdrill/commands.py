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
        cmd_mathpix(pdf)  # acquire OCR first
        sc = Sidecar(pdf)
    if not lines_path.exists():
        return f"No MathPix lines.json for {pdf.name} (run `pdfdrill mathpix` first)."

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


def cmd_compare(pdf: Path, force: bool = False) -> str:
    """Emit the LaTeX | KaTeX | MathPix-image comparison HTML.

    Auto-chains `model` if needed. Writes <pdf>.drill/compare.html.
    """
    from docmodel.core import Document
    from docops.base import OperatorConfig
    from docops.projectors.comparison_html import ComparisonHtmlProjector

    sc = Sidecar(pdf)
    model_path = _model_path(sc)
    if not sc.has(MODEL_BUILT) or not model_path.exists() or force:
        cmd_model(pdf, force=force)
        sc = Sidecar(pdf)
        model_path = _model_path(sc)
    if not model_path.exists():
        return f"No model for {pdf.name} (run `pdfdrill model` first)."

    t0 = time.monotonic()
    with open(model_path, "r", encoding="utf-8") as f:
        doc = Document.from_dict(json.load(f))

    proj = ComparisonHtmlProjector(
        OperatorConfig(op="projector", classname="ComparisonHtmlProjector")
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
    from .blocks import nest_list_items, max_depth, count_lists

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

    mp = doc.stream("mathpix_lines") if "mathpix_lines" in doc.streams else None

    def _indent_of(item_obj):
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


def _list_type(markers: list[str]) -> str:
    if not markers:
        return "list"
    bullets = sum(1 for m in markers if m and m[0] in "•○▪-*•‣◦⁃∙")
    return "itemize" if bullets >= len(markers) / 2 else "enumerate"


def _format_lists(sc: Sidecar) -> str:
    return (
        f"Reconstructed {sc.get_evidence('lists_created', 0)} nested List(s) "
        f"from {sc.get_evidence('lists_items', 0)} list items "
        f"(max nesting depth {sc.get_evidence('lists_max_depth', 0)}). "
        f"List objects carry list_type (itemize/enumerate) and indent_norm; "
        f"ListItems are now children of their List."
    )


# ---------------------------------------------------------------------------
# TiddlyWiki export — JSON tiddler array for quick data-structure inspection
# ---------------------------------------------------------------------------

def cmd_tiddlers(pdf: Path, force: bool = False) -> str:
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
        OperatorConfig(op="projector", classname="TiddlyWikiProjector"))
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
    sc.set_evidence("text_layer", True)  # refined by fonts
    sc.set_evidence("pdfinfo", info)

    sc.add_fact(SIZE_KNOWN)
    elapsed = time.monotonic() - t0
    sc.log_transition("size", "INIT", SIZE_KNOWN, cost_ms=elapsed * 1000,
                      detail=f"pdfinfo: {sc.page_count} pages, {sc.file_size} bytes")
    sc.save()
    return _format_size(sc)


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
    sc.set_evidence("text_layer", len(fonts) > 0)

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
