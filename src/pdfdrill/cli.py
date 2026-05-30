"""pdfdrill CLI — flat commands, prose output, sidecar persistence.

Each command does one thing, returns prose the LLM can quote directly.
State persists in paper.pdf.drill.json next to the PDF.

Usage:
    pdfdrill size paper.pdf
    pdfdrill abstract paper.pdf
    pdfdrill toc paper.pdf
    pdfdrill fonts paper.pdf
    pdfdrill status paper.pdf
    pdfdrill md paper.pdf [--pages 3-7]
    pdfdrill page paper.pdf 5
    pdfdrill fetch paper.pdf md [--section 3]
    pdfdrill plan paper.pdf "What theorem is proved?"
"""

from __future__ import annotations

import sys
from pathlib import Path


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        _print_help()
        return 0

    cmd = args[0]
    rest = args[1:]

    handlers = {
        "size": _do_size,
        "abstract": _do_abstract,
        "toc": _do_toc,
        "fonts": _do_fonts,
        "status": _do_status,
        "md": _do_md,
        "page": _do_page,
        "fetch": _do_fetch,
        "plan": _do_plan,
        "drill": _do_drill,
        "pdfinfo": _do_pdfinfo,
        "bibtex": _do_bibtex,
        "urls": _do_urls,
        "links": _do_links,
        "dests": _do_dests,
        "fonts_layer": _do_fonts_layer,
        "images": _do_images,
        "pix2tex": _do_pix2tex,
        "tsv": _do_tsv,
        "render": _do_render,
        "mathpix": _do_mathpix,
        "model": _do_model,
        "compare": _do_compare,
        "snip": _do_snip,
        "candidates": _do_candidates,
        "ingest": _do_ingest,
        "geometry": _do_geometry,
        "tiddlers": _do_tiddlers,
        "lists": _do_lists,
        "algorithms": _do_algorithms,
        "annotate": _do_annotate,
        "score": _do_score,
        "escalate": _do_escalate,
        "relearn": _do_relearn,
        "eqnums": _do_eqnums,
        "bibliography": _do_bibliography,
        "bibfetch": _do_bibfetch,
        "report": _do_report,
        "folder": _do_folder,
        "latex": _do_latex,
        "latexbook": _do_latexbook,
    }

    if cmd not in handlers:
        # Backward compat: if first arg is a file/dir, treat as "run"
        if Path(cmd).exists():
            rest = [cmd] + rest
            cmd = "drill"
        else:
            print(f"Unknown command: {cmd}. Run `pdfdrill help` for usage.", file=sys.stderr)
            return 1

    try:
        result = handlers[cmd](rest)
        if result:
            print(result)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _pdf(args: list[str]) -> Path:
    if not args:
        raise ValueError("No PDF file specified.")
    p = Path(args[0])
    if not p.exists():
        raise FileNotFoundError(f"Not found: {p}")
    return p


def _do_size(args):
    from .commands import cmd_size
    return cmd_size(_pdf(args))


def _do_abstract(args):
    from .commands import cmd_abstract
    return cmd_abstract(_pdf(args))


def _do_toc(args):
    from .commands import cmd_toc
    return cmd_toc(_pdf(args))


def _do_fonts(args):
    from .commands import cmd_fonts
    return cmd_fonts(_pdf(args))


def _do_status(args):
    from .commands import cmd_status
    return cmd_status(_pdf(args))


def _do_pdfinfo(args):
    from .commands import cmd_pdfinfo
    return cmd_pdfinfo(_pdf(args))


def _do_bibtex(args):
    from .commands import cmd_bibtex
    return cmd_bibtex(_pdf(args))


def _do_urls(args):
    from .commands import cmd_urls
    return cmd_urls(_pdf(args))


def _do_links(args):
    from .commands import cmd_links
    return cmd_links(_pdf(args))


def _do_dests(args):
    from .commands import cmd_dests
    return cmd_dests(_pdf(args))


def _do_fonts_layer(args):
    from .commands import cmd_fonts_layer
    return cmd_fonts_layer(_pdf(args))


def _do_images(args):
    from .commands import cmd_images
    return cmd_images(_pdf(args))


def _do_tsv(args):
    from .commands import cmd_tsv
    pdf_args: list[str] = []
    force_ocr = False
    for a in args:
        if a == "--ocr":
            force_ocr = True
        else:
            pdf_args.append(a)
    return cmd_tsv(_pdf(pdf_args), force_ocr=force_ocr)


def _do_render(args):
    from .commands import cmd_render
    pdf_args: list[str] = []
    force = False
    for a in args:
        if a == "--force":
            force = True
        else:
            pdf_args.append(a)
    return cmd_render(_pdf(pdf_args), force=force)


def _do_mathpix(args):
    """pdfdrill mathpix <pdf> [--force]"""
    from .commands import cmd_mathpix
    pdf_args: list[str] = []
    force = False
    for a in args:
        if a == "--force":
            force = True
        else:
            pdf_args.append(a)
    return cmd_mathpix(_pdf(pdf_args), force=force)


def _do_model(args):
    """pdfdrill model <pdf> [--force]"""
    from .commands import cmd_model
    pdf_args = [a for a in args if a != "--force"]
    return cmd_model(_pdf(pdf_args), force="--force" in args)


def _do_compare(args):
    """pdfdrill compare <pdf> [--force] [--embed]"""
    from .commands import cmd_compare
    pdf_args = [a for a in args if a not in ("--force", "--embed")]
    return cmd_compare(_pdf(pdf_args), force="--force" in args, embed="--embed" in args)


def _do_snip(args):
    """pdfdrill snip <pdf> [--limit N] [--force]"""
    from .commands import cmd_snip
    pdf_args: list[str] = []
    limit = None
    force = False
    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1]); i += 2
        elif args[i] == "--force":
            force = True; i += 1
        else:
            pdf_args.append(args[i]); i += 1
    return cmd_snip(_pdf(pdf_args), limit=limit, force=force)


def _do_geometry(args):
    """pdfdrill geometry <pdf> [--force]"""
    from .commands import cmd_geometry
    pdf_args = [a for a in args if a != "--force"]
    return cmd_geometry(_pdf(pdf_args), force="--force" in args)


def _do_tiddlers(args):
    """pdfdrill tiddlers <pdf> [--force] [--embed]"""
    from .commands import cmd_tiddlers
    pdf_args = [a for a in args if a not in ("--force", "--embed")]
    return cmd_tiddlers(_pdf(pdf_args), force="--force" in args, embed="--embed" in args)


def _do_lists(args):
    """pdfdrill lists <pdf> [--force]"""
    from .commands import cmd_lists
    pdf_args = [a for a in args if a != "--force"]
    return cmd_lists(_pdf(pdf_args), force="--force" in args)


def _do_algorithms(args):
    """pdfdrill algorithms <pdf> [--force]"""
    from .commands import cmd_algorithms
    pdf_args = [a for a in args if a != "--force"]
    return cmd_algorithms(_pdf(pdf_args), force="--force" in args)


def _do_annotate(args):
    """pdfdrill annotate <pdf> [--force]"""
    from .commands import cmd_annotate
    pdf_args = [a for a in args if a != "--force"]
    return cmd_annotate(_pdf(pdf_args), force="--force" in args)


def _do_score(args):
    """pdfdrill score <pdf> [--force]"""
    from .commands import cmd_score
    pdf_args = [a for a in args if a != "--force"]
    return cmd_score(_pdf(pdf_args), force="--force" in args)


def _do_escalate(args):
    """pdfdrill escalate <pdf> [--limit N]"""
    from .commands import cmd_escalate
    pdf_args: list[str] = []
    limit = None
    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1]); i += 2
        else:
            pdf_args.append(args[i]); i += 1
    return cmd_escalate(_pdf(pdf_args), limit=limit)


def _do_relearn(args):
    """pdfdrill relearn <pdf>"""
    from .commands import cmd_relearn
    return cmd_relearn(_pdf(args))


def _do_eqnums(args):
    """pdfdrill eqnums <pdf> [--force]"""
    from .commands import cmd_eqnums
    pdf_args = [a for a in args if a != "--force"]
    return cmd_eqnums(_pdf(pdf_args), force="--force" in args)


def _do_bibliography(args):
    """pdfdrill bibliography <pdf> [--force]"""
    from .commands import cmd_bibliography
    pdf_args = [a for a in args if a != "--force"]
    return cmd_bibliography(_pdf(pdf_args), force="--force" in args)


def _do_report(args):
    """pdfdrill report <pdf> [--force] [--embed]"""
    from .commands import cmd_report
    pdf_args = [a for a in args if a not in ("--force", "--embed")]
    return cmd_report(_pdf(pdf_args), force="--force" in args, embed="--embed" in args)


def _do_latexbook(args):
    """pdfdrill latexbook <book.tex> [--bibkey K] [--force]"""
    from .commands import cmd_latexbook
    pos: list[str] = []
    bibkey = None
    force = False
    i = 0
    while i < len(args):
        if args[i] == "--bibkey" and i + 1 < len(args):
            bibkey = args[i + 1]; i += 2
        elif args[i] == "--force":
            force = True; i += 1
        else:
            pos.append(args[i]); i += 1
    if not pos:
        raise ValueError("Usage: pdfdrill latexbook <book.tex> [--bibkey K] [--force]")
    t = Path(pos[0])
    if not t.exists():
        raise FileNotFoundError(f"Not found: {t}")
    return cmd_latexbook(t, bibkey=bibkey, force=force)


def _do_latex(args):
    """pdfdrill latex <pdf> [--tex <path>] [--force]"""
    from .commands import cmd_latex
    pdf_args: list[str] = []
    tex = None
    force = False
    i = 0
    while i < len(args):
        if args[i] == "--tex" and i + 1 < len(args):
            tex = args[i + 1]; i += 2
        elif args[i] == "--force":
            force = True; i += 1
        else:
            pdf_args.append(args[i]); i += 1
    return cmd_latex(_pdf(pdf_args), tex=tex, force=force)


def _do_folder(args):
    """pdfdrill folder <dir> [--force]"""
    from .commands import cmd_folder
    pos = [a for a in args if a != "--force"]
    if not pos:
        raise ValueError("Usage: pdfdrill folder <dir> [--force]")
    d = Path(pos[0])
    if not d.is_dir():
        raise NotADirectoryError(f"Not a folder: {d}")
    return cmd_folder(d, force="--force" in args)


def _do_bibfetch(args):
    """pdfdrill bibfetch <pdf> [--limit N] [--force]"""
    from .commands import cmd_bibfetch
    pdf_args: list[str] = []
    limit = None
    force = False
    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1]); i += 2
        elif args[i] == "--force":
            force = True; i += 1
        else:
            pdf_args.append(args[i]); i += 1
    return cmd_bibfetch(_pdf(pdf_args), limit=limit, force=force)


def _do_candidates(args):
    """pdfdrill candidates <pdf> [--provider P] [--limit N] [--out F]"""
    from .commands import cmd_candidates
    pdf_args: list[str] = []
    provider = "llm"
    limit = None
    out = None
    i = 0
    while i < len(args):
        if args[i] == "--provider" and i + 1 < len(args):
            provider = args[i + 1]; i += 2
        elif args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1]); i += 2
        elif args[i] == "--out" and i + 1 < len(args):
            out = args[i + 1]; i += 2
        else:
            pdf_args.append(args[i]); i += 1
    return cmd_candidates(_pdf(pdf_args), provider=provider, limit=limit, out=out)


def _do_ingest(args):
    """pdfdrill ingest <pdf> <candidates.json> [--provider P] [--force]"""
    from .commands import cmd_ingest
    pos: list[str] = []
    provider = "llm"
    force = False
    i = 0
    while i < len(args):
        if args[i] == "--provider" and i + 1 < len(args):
            provider = args[i + 1]; i += 2
        elif args[i] == "--force":
            force = True; i += 1
        else:
            pos.append(args[i]); i += 1
    if len(pos) < 2:
        raise ValueError("Usage: pdfdrill ingest <pdf> <candidates.json> [--provider P] [--force]")
    return cmd_ingest(_pdf(pos[:1]), pos[1], provider=provider, force=force)


def _do_pix2tex(args):
    """pdfdrill pix2tex <pdf> [--page N] [--rect x0,y0,x1,y1] [--rerun]"""
    from .commands import cmd_pix2tex
    pdf_args: list[str] = []
    page: int | None = None
    rect: tuple[float, float, float, float] | None = None
    rerun = False
    i = 0
    while i < len(args):
        if args[i] == "--page" and i + 1 < len(args):
            page = int(args[i + 1])
            i += 2
        elif args[i] == "--rect" and i + 1 < len(args):
            parts = args[i + 1].split(",")
            if len(parts) != 4:
                raise ValueError("--rect expects x0,y0,x1,y1")
            rect = (float(parts[0]), float(parts[1]),
                    float(parts[2]), float(parts[3]))
            i += 2
        elif args[i] == "--rerun":
            rerun = True
            i += 1
        else:
            pdf_args.append(args[i])
            i += 1
    return cmd_pix2tex(_pdf(pdf_args), page=page, rect=rect, rerun=rerun)


def _do_md(args):
    from .commands import cmd_md
    pages = None
    pdf_args = []
    i = 0
    while i < len(args):
        if args[i] == "--pages" and i + 1 < len(args):
            pages = args[i + 1]
            i += 2
        else:
            pdf_args.append(args[i])
            i += 1
    return cmd_md(_pdf(pdf_args), pages)


def _do_page(args):
    from .commands import cmd_page
    if len(args) < 2:
        raise ValueError("Usage: pdfdrill page <pdf> <page_number>")
    return cmd_page(Path(args[0]), int(args[1]))


def _do_fetch(args):
    from .commands import cmd_fetch
    if len(args) < 2:
        raise ValueError("Usage: pdfdrill fetch <pdf> <layer> [--section N]")
    pdf = Path(args[0])
    what = args[1]
    kwargs = {}
    i = 2
    while i < len(args):
        if args[i] == "--section" and i + 1 < len(args):
            kwargs["section"] = args[i + 1]
            i += 2
        else:
            i += 1
    return cmd_fetch(pdf, what, **kwargs)


def _do_plan(args):
    """Show what pdfdrill would do to answer a question."""
    pdf = _pdf(args[:1])
    question = " ".join(args[1:]) if len(args) > 1 else ""

    from .sidecar import Sidecar
    sc = Sidecar(pdf)
    facts = sc.facts

    steps = []
    if "SIZE_KNOWN" not in facts:
        steps.append(("size", "pdfinfo — page count, file size, producer"))
    if "FONTS_KNOWN" not in facts:
        steps.append(("fonts", "pdffonts — font list, math font detection"))
    if "ABSTRACT_KNOWN" not in facts and "ABSTRACT_ABSENT" not in facts:
        steps.append(("abstract", "pdftotext first 2 pages — extract abstract"))
    if "TOC_KNOWN" not in facts and "TOC_ABSENT" not in facts:
        steps.append(("toc", "pdftotext first 3 pages — extract table of contents"))

    needs_md = True  # default: full extraction
    if question:
        q_lower = question.lower()
        if any(w in q_lower for w in ["abstract", "summary", "about", "topic"]):
            needs_md = False
            steps.append(("→ answer from abstract", ""))
        elif any(w in q_lower for w in ["how many pages", "size", "author"]):
            needs_md = False
            steps.append(("→ answer from metadata", ""))

    if needs_md and "MD_BUILT" not in facts:
        steps.append(("md", "pdfplumber + layer pipeline — full Markdown extraction"))

    lines = [f"Plan for {pdf.name}:"]
    if question:
        lines.append(f"  Question: \"{question}\"")
    lines.append(f"  Already known: {', '.join(facts) if facts else 'nothing'}")
    lines.append(f"  Steps needed:")
    for name, desc in steps:
        if desc:
            lines.append(f"    {name}: {desc}")
        else:
            lines.append(f"    {name}")

    return "\n".join(lines)


def _do_drill(args):
    """Auto-drill, status-driven by default.

    Runs only the steps whose fact is not yet present in the sidecar.
    Use --full to wipe the sidecar first and re-run from cold (useful for
    testing / forcing a fresh extraction).
    """
    pdf_args: list[str] = []
    full = False
    for a in args:
        if a == "--full":
            full = True
        elif not a.startswith("--"):
            pdf_args.append(a)
    pdf = _pdf(pdf_args[:1])

    from .commands import (
        cmd_size, cmd_fonts, cmd_abstract, cmd_toc, cmd_md, cmd_status,
        SIZE_KNOWN, FONTS_KNOWN, ABSTRACT_KNOWN, ABSTRACT_ABSENT,
        TOC_KNOWN, TOC_ABSENT, MD_BUILT,
    )
    from .sidecar import Sidecar

    if full:
        sc = Sidecar(pdf)
        if sc.json_path.exists():
            sc.json_path.unlink()
        if sc.blob_dir.exists():
            import shutil
            shutil.rmtree(sc.blob_dir)

    sc = Sidecar(pdf)
    facts = sc.facts

    # Status-driven plan: each step contributes a line only if it actually ran.
    plan: list[tuple[str, callable, set[str]]] = [
        ("size", lambda: cmd_size(pdf), {SIZE_KNOWN}),
        ("fonts", lambda: cmd_fonts(pdf), {FONTS_KNOWN}),
        ("abstract", lambda: cmd_abstract(pdf), {ABSTRACT_KNOWN, ABSTRACT_ABSENT}),
        ("toc", lambda: cmd_toc(pdf), {TOC_KNOWN, TOC_ABSENT}),
        ("md", lambda: cmd_md(pdf), {MD_BUILT}),
    ]

    ran: list[tuple[str, str]] = []
    skipped: list[str] = []
    for name, fn, settled in plan:
        if settled & facts:
            skipped.append(name)
            continue
        ran.append((name, fn()))
        facts = Sidecar(pdf).facts  # refresh in case the step touched others

    lines: list[str] = []
    if ran:
        lines.append("Drilled: " + ", ".join(n for n, _ in ran))
        for n, out in ran:
            lines.append(f"\n--- {n} ---\n{out}")
    if skipped:
        lines.append(f"\nSkipped (already done): {', '.join(skipped)}")
    if not ran and not skipped:
        lines.append("Nothing to do.")
    lines.append("")
    lines.append(cmd_status(pdf))
    return "\n".join(lines)


def _print_help():
    print("""pdfdrill — portable PDF drill-down toolkit

Introspection (fast, no extraction):
  pdfdrill size <pdf>          File size, page count, producer
  pdfdrill pdfinfo <pdf>       Full PdfInfo struct (title/author/dates/flags)
  pdfdrill bibtex <pdf>        Derived BibTeX record
  pdfdrill links <pdf>         FAST external URLs via pdfinfo -url (~50ms); flags code/data hosts
  pdfdrill urls <pdf>          URL annotations with anchor text (heavier; pdfplumber)
  pdfdrill dests <pdf>         Named destinations: theorems, equations, sections
  pdfdrill fonts_layer <pdf>   Structured per-font records (pdffonts)
  pdfdrill images <pdf>        Image rectangles + metadata (pdfplumber + pdfimages -list)
  pdfdrill pix2tex <pdf>       Run pix2tex on candidate rects (auto from images_layer)
  pdfdrill pix2tex <pdf> --page N --rect x0,y0,x1,y1   Explicit crop OCR
  pdfdrill tsv <pdf>           Word-level bounding boxes (pdftotext -tsv; --ocr forces tesseract)
  pdfdrill render <pdf>        Render the built markdown to PDF (pandoc + lualatex)
  pdfdrill mathpix <pdf>       Download MathPix OCR (lines.json, md, tex.zip); --force re-uploads
  pdfdrill model <pdf>         Build unified docmodel from lines.json (auto-chains mathpix)
  pdfdrill compare <pdf>       LaTeX | KaTeX | MathPix-image comparison HTML (auto-chains model)
  pdfdrill report <pdf>        Full inline+display math report (formula-report.html)
  pdfdrill latex <pdf>         Ingest author .tex/.tgz as a `tex` provenance (original+expanded LaTeX); --tex <path>
  pdfdrill latexbook <book.tex> Build a source-only model + KaTeX formula report from LaTeX (no PDF/MathPix); resolves local .sty macros
  pdfdrill folder <dir>        Build the full structure for every PDF in <dir> from existing
                               .lines.json/.bib/.md — runs all levels, NO MathPix/Perplexity calls
  pdfdrill snip <pdf>          OCR each equation crop via MathPix Snip (/v3/text) → competing column; --limit N
  pdfdrill candidates <pdf>    Export equation crops as a manifest for an LLM to read; --provider P --limit N
  pdfdrill ingest <pdf> <json> Attach externally-produced {eq_id,latex} candidates as a provenance column; --provider P
  pdfdrill geometry <pdf>      Fuse pdftotext -tsv layout (indent/margins) onto the model — substrate for block detection
  pdfdrill tiddlers <pdf>      Emit a TiddlyWiki JSON tiddler array (latex/displayMode/canonical_uri/width/height) for quick inspection
  pdfdrill lists <pdf>         Nest flat ListItems into recursive List blocks using fused indentation (auto-chains geometry)
  pdfdrill algorithms <pdf>    Reconstruct Algorithm blocks from MathPix pseudocode lines (caption + indented steps)
  pdfdrill annotate <pdf>      Promote hyperlink annotations into the model as first-class Link nodes (uri + rect Region)
  pdfdrill score <pdf>         Score equations by cross-provenance agreement + snip confidence; flags review candidates
  pdfdrill escalate <pdf>      Phase-3: export flagged equations for a second LLM reading; --limit N
  pdfdrill relearn <pdf>       Phase-3: re-score after ingest; report resolved vs still-flagged
  pdfdrill eqnums <pdf>        Fuse equation numbers ("(N)") from margin geometry for ||FO/||FREF transclusion
  pdfdrill bibliography <pdf>  Parse the References section into Reference nodes (citekey/author/year/text)
  pdfdrill bibfetch <pdf>      Enrich References with full BibTeX via Perplexity SONAR; --limit N (needs PERPLEXITY_API_KEY)
  pdfdrill toc <pdf>           Table of contents
  pdfdrill abstract <pdf>      Abstract from first pages
  pdfdrill fonts <pdf>         Font analysis, math font detection
  pdfdrill status <pdf>        What is already known

Extraction:
  pdfdrill md <pdf>            Full Markdown with math transclusions
  pdfdrill page <pdf> <n>      Single page text extraction

Query:
  pdfdrill fetch <pdf> md      Retrieve stored Markdown
  pdfdrill fetch <pdf> md --section 3   Specific section
  pdfdrill fetch <pdf> abstract

Planning & automation:
  pdfdrill plan <pdf> "question"   Show what steps are needed
  pdfdrill drill <pdf>             Full auto-drill

State persists in <pdf>.drill.json next to the PDF file.
Each command returns prose ready for LLM consumption.""")
