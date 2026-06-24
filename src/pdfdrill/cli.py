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


    if cmd not in HANDLERS:
        # Backward compat: if first arg is a file/dir, treat as "run"
        if Path(cmd).exists():
            rest = [cmd] + rest
            cmd = "drill"
        else:
            print(f"Unknown command: {cmd}. Run `pdfdrill help` for usage.", file=sys.stderr)
            return 1

    # --ensure: auto-insert the missing OFFLINE prerequisite steps (model /
    # bibliography) before running the target — the state machine reacting to a
    # skipped step. The target's own handler still runs normally afterwards.
    if "--ensure" in rest:
        rest = [a for a in rest if a != "--ensure"]
        try:
            from . import planner
            pdf_arg = next((a for a in rest if not a.startswith("-")), None)
            if pdf_arg is not None:
                ran = planner.ensure(cmd, Path(pdf_arg), HANDLERS, pdf_arg)
                if ran:
                    print(f"[ensure] ran missing prerequisite(s): {', '.join(ran)}")
        except Exception as e:
            print(f"[ensure] skipped ({e})", file=sys.stderr)

    try:
        result = HANDLERS[cmd](rest)
        if result:
            print(result)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _pdf(args: list[str]) -> Path:
    if not args:
        raise ValueError("No PDF file specified.")
    arg = args[0]
    from . import sources
    # expand `~` / `~user` for local paths ($HOME shorthand) — so `~/x.pdf`
    # resolves exactly like `/home/me/x.pdf`. A no-op on URLs / bare arXiv ids.
    if not sources.is_url(arg):
        arg = str(Path(arg).expanduser())
    # work directly on an https URL from a known host, OR a bare arXiv id — but
    # never shadow a real local file (checked first inside resolve_input).
    if (sources.is_url(arg) or sources.bare_arxiv_id(arg)) and not Path(arg).exists():
        # download once (cached) to a local PDF so every command runs on it. For
        # arXiv the stem is the id, recorded so abstract/latex take the FREE routes.
        info = sources.resolve_input(arg)
        p = info["path"]
        if not (p.exists() and p.stat().st_size > 0):
            raise FileNotFoundError(f"Download failed: {arg}")
        if info.get("arxiv_id"):
            try:
                from .sidecar import Sidecar
                sc = Sidecar(p)
                sc.set_evidence("source_arxiv_id", info["arxiv_id"])
                sc.set_evidence("source_kind", info.get("source"))
                sc.save()
            except Exception:
                pass
        return p
    p = Path(arg)
    if not p.exists():
        raise FileNotFoundError(f"Not found: {p}")
    return p


def _drilled(args: list[str]) -> Path:
    """Resolve the target for a MODEL-ONLY command (translate/classify). These
    read only the persisted model, so accept a drilled doc whose source file was
    removed after drilling (e.g. a consumed .md): if `<arg>.drill` exists, use
    the literal path; otherwise fall back to the normal `_pdf` resolution
    (local file / known-host URL / bare arXiv id)."""
    if not args:
        raise ValueError("No file specified.")
    from . import sources
    a0 = args[0] if sources.is_url(args[0]) else str(Path(args[0]).expanduser())
    cand = Path(a0)
    if (cand.parent / (cand.name + ".drill")).exists():
        return cand
    return _pdf([a0, *args[1:]])


def _do_artifacts(args):
    """pdfdrill artifacts <pdf|md> [--all] — list the drill-folder files
    (md/json/html/svg/…) with paths, clickable in the drillui Outputs panel.
    --all includes the giant model JSON (hidden by default)."""
    from .commands import cmd_artifacts
    all_files = "--all" in args
    rest = [a for a in args if a != "--all"]
    return cmd_artifacts(_drilled(rest), all_files=all_files)


def _do_config(args):
    """pdfdrill config [--init|--json|--download-dir] — show/init the config file
    (where downloads + .drill folders go; default ~/Downloads)."""
    from .commands import cmd_config
    if "--init" in args:
        return cmd_config("init")
    if "--json" in args:
        return cmd_config("json")
    if "--download-dir" in args:
        return cmd_config("download-dir")
    return cmd_config("show")


def _do_doctor(args):
    """pdfdrill doctor — check system tools / Python deps / API keys."""
    from .commands import cmd_doctor
    return cmd_doctor()


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


def _do_embedimages(args):
    """pdfdrill embedimages <pdf> [--force]"""
    from .commands import cmd_embedimages
    pdf_args = [a for a in args if a != "--force"]
    return cmd_embedimages(_pdf(pdf_args), force="--force" in args)


def _do_vision(args):
    """pdfdrill vision <pdf> [--limit N] [--force]"""
    from .commands import cmd_vision
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
    return cmd_vision(_pdf(pdf_args), limit=limit, force=force)


def _do_llm(args):
    """pdfdrill llm <pdf> [--show | --runtime]"""
    from .commands import cmd_llm
    from .llm_delegate import detect_runtime
    if "--runtime" in args:
        return f"llm-delegation runtime: {detect_runtime().value}"
    action = "show" if "--show" in args else "status"
    pdf_args = [a for a in args if a not in ("--show", "--status")]
    return cmd_llm(_pdf(pdf_args), action=action)


def _do_entities(args):
    """pdfdrill entities <pdf>"""
    from .commands import cmd_entities
    pdf_args = [a for a in args if a != "--force"]
    return cmd_entities(_pdf(pdf_args), force="--force" in args)


def _do_segment(args):
    """pdfdrill segment <pdf> [--force]"""
    from .commands import cmd_segment
    pdf_args = [a for a in args if a != "--force"]
    return cmd_segment(_pdf(pdf_args), force="--force" in args)


def _do_elements(args):
    """pdfdrill elements <pdf> [--model M.npz] [--bibkey KEY] [--source S]
    [--lang deu+eng] [--ppi 300] [--force]"""
    from .commands import cmd_elements
    model, args = _opt(args, "--model")
    bibkey, args = _opt(args, "--bibkey")
    source, args = _opt(args, "--source")
    lang, args = _opt(args, "--lang")
    ppi, args = _opt(args, "--ppi")
    pdf_args = [a for a in args if a != "--force"]
    return cmd_elements(_pdf(pdf_args), force="--force" in args, model=model,
                        bibkey=bibkey, source=source,
                        ppi=int(ppi) if ppi else 300, lang=lang or "deu+eng")


def _do_semantic(args):
    """pdfdrill semantic <pdf> [--store graph.json] [--force]"""
    from .commands import cmd_semantic
    store, args = _opt(args, "--store")
    pdf_args = [a for a in args if a != "--force"]
    return cmd_semantic(_pdf(pdf_args), store=store, force="--force" in args)


def _do_ordered(args):
    """pdfdrill ordered <pdf> [--threshold 0.5]"""
    from .commands import cmd_ordered
    thr, args = _opt(args, "--threshold")
    return cmd_ordered(_pdf(args), threshold=float(thr) if thr else 0.5)


def _do_autosegment(args):
    """pdfdrill autosegment <pdf> [--threshold 0.5]"""
    from .commands import cmd_autosegment
    thr, args = _opt(args, "--threshold")
    return cmd_autosegment(_pdf(args), threshold=float(thr) if thr else 0.5)


def _do_fontid(args):
    """pdfdrill fontid <pdf> [--pages N|N-M] [--limit 12] [--ppi 200]"""
    from .commands import cmd_fontid
    pages, args = _opt(args, "--pages")
    limit, args = _opt(args, "--limit")
    ppi, args = _opt(args, "--ppi")
    return cmd_fontid(_pdf(args), pages=pages, limit=int(limit) if limit else 12,
                      ppi=int(ppi) if ppi else 200)


def _do_spellqc(args):
    """pdfdrill spellqc <pdf> [--lang de|en]"""
    from .commands import cmd_spellqc
    lang, args = _opt(args, "--lang")
    return cmd_spellqc(_pdf(args), lang=lang)


def _do_qr(args):
    """pdfdrill qr <pdf> [--pages N|N-M] [--dpi 300] [--formats QRCode,DataMatrix]"""
    from .commands import cmd_qr
    dpi, args = _opt(args, "--dpi")
    pages, args = _opt(args, "--pages")
    formats, args = _opt(args, "--formats")
    return cmd_qr(_pdf(args), dpi=int(dpi) if dpi else 300, pages=pages, formats=formats)


def _do_selftest(args):
    """pdfdrill selftest <pdf|dir> [--full]"""
    from .commands import cmd_selftest
    full = "--full" in args
    rest = [a for a in args if a != "--full"]
    from pathlib import Path
    return cmd_selftest(Path(rest[0]) if rest else Path("."), full=full)


def _do_rasterize(args):
    """pdfdrill rasterize <pdf> [--pages N|N-M|all] [--dpi 150] [--fmt png|jpeg] [--force]"""
    from .commands import cmd_rasterize
    pages, args = _opt(args, "--pages")
    dpi, args = _opt(args, "--dpi")
    fmt, args = _opt(args, "--fmt")
    pdf_args = [a for a in args if a != "--force"]
    return cmd_rasterize(_pdf(pdf_args), pages=pages, dpi=int(dpi) if dpi else 150,
                         fmt=fmt or "png", force="--force" in args)


def _do_attachments(args):
    """pdfdrill attachments <pdf> [--extract]"""
    from .commands import cmd_attachments
    pdf_args = [a for a in args if a != "--extract"]
    return cmd_attachments(_pdf(pdf_args), extract="--extract" in args)


def _do_formfields(args):
    """pdfdrill formfields <pdf>"""
    from .commands import cmd_formfields
    return cmd_formfields(_pdf(args))


def _do_extractimages(args):
    """pdfdrill extractimages <pdf> [--pages N|N-M] [--all-formats] [--force]"""
    from .commands import cmd_extractimages
    pages, args = _opt(args, "--pages")
    pdf_args = [a for a in args if a not in ("--force", "--all-formats")]
    return cmd_extractimages(_pdf(pdf_args), pages=pages,
                             original_format="--all-formats" in args,
                             force="--force" in args)


def _do_tables(args):
    """pdfdrill tables <pdf> [--pages N|N-M]"""
    from .commands import cmd_tables
    pages, args = _opt(args, "--pages")
    return cmd_tables(_pdf(args), pages=pages)


def _do_pageside(args):
    """pdfdrill pageside <pdf>"""
    from .commands import cmd_pageside
    return cmd_pageside(_pdf(args))


def _do_continuity(args):
    """pdfdrill continuity <pdf> [--lang deu+eng] [--ppi 250] [--force]"""
    from .commands import cmd_continuity
    lang, args = _opt(args, "--lang")
    ppi, args = _opt(args, "--ppi")
    pdf_args = [a for a in args if a != "--force"]
    return cmd_continuity(_pdf(pdf_args), force="--force" in args,
                          ppi=int(ppi) if ppi else 250, lang=lang or "deu+eng")


def _do_ocr(args):
    """pdfdrill ocr <pdf> [--lang eng] [--ppi 300] [--force]"""
    from .commands import cmd_ocr
    pdf_args: list[str] = []
    lang = "eng"
    ppi = 300
    force = False
    i = 0
    while i < len(args):
        if args[i] == "--lang" and i + 1 < len(args):
            lang = args[i + 1]; i += 2
        elif args[i] == "--ppi" and i + 1 < len(args):
            ppi = int(args[i + 1]); i += 2
        elif args[i] == "--force":
            force = True; i += 1
        else:
            pdf_args.append(args[i]); i += 1
    return cmd_ocr(_pdf(pdf_args), lang=lang, ppi=ppi, force=force)


def _opt(args, name):
    """Pop `--name VALUE`; return (value_or_None, remaining_args)."""
    out, val, i = [], None, 0
    while i < len(args):
        if args[i] == name and i + 1 < len(args):
            val = args[i + 1]; i += 2
        else:
            out.append(args[i]); i += 1
    return val, out


def _do_model(args):
    """pdfdrill model <pdf> [--bibkey KEY] [--force]"""
    from .commands import cmd_model
    bibkey, args = _opt(args, "--bibkey")
    pdf_args = [a for a in args if a != "--force"]
    return cmd_model(_pdf(pdf_args), force="--force" in args, bibkey=bibkey)


def _do_compare(args):
    """pdfdrill compare <pdf> [--force] [--embed]"""
    from .commands import cmd_compare
    pdf_args = [a for a in args if a not in ("--force", "--embed")]
    return cmd_compare(_pdf(pdf_args), force="--force" in args, embed="--embed" in args)


def _do_snip(args):
    """pdfdrill snip <pdf> [--limit N] [--force]
    pdfdrill snip <pdf> --image <path|url>            (OCR any special image)
    pdfdrill snip <pdf> --page N --rect x0,y0,x1,y1   (deliver+OCR a region crop)"""
    from .commands import cmd_snip
    image, args = _opt(args, "--image")
    page, args = _opt(args, "--page")
    rect_s, args = _opt(args, "--rect")
    ppi, args = _opt(args, "--ppi")
    limit, args = _opt(args, "--limit")
    rect = tuple(float(x) for x in rect_s.split(",")) if rect_s else None
    pdf_args = [a for a in args if a != "--force"]
    return cmd_snip(_pdf(pdf_args), limit=int(limit) if limit else None,
                    force="--force" in args, image=image,
                    page=int(page) if page else None, rect=rect,
                    ppi=int(ppi) if ppi else 200)


def _do_nlp(args):
    """pdfdrill nlp <pdf> [--limit N] [--pages N] [--types T,T] [--force]"""
    from .commands import cmd_nlp
    pdf_args: list[str] = []
    limit = pages = None
    types = None
    force = False
    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1]); i += 2
        elif args[i] == "--pages" and i + 1 < len(args):
            pages = int(args[i + 1]); i += 2
        elif args[i] == "--types" and i + 1 < len(args):
            types = [t.strip() for t in args[i + 1].split(",") if t.strip()]; i += 2
        elif args[i] == "--force":
            force = True; i += 1
        else:
            pdf_args.append(args[i]); i += 1
    return cmd_nlp(_pdf(pdf_args), limit=limit, pages=pages, types=types, force=force)


def _do_geometry(args):
    """pdfdrill geometry <pdf> [--force]"""
    from .commands import cmd_geometry
    pdf_args = [a for a in args if a != "--force"]
    return cmd_geometry(_pdf(pdf_args), force="--force" in args)


def _do_translate(args):
    """pdfdrill translate <pdf> [--to LANG] [--from LANG] [--limit N] [--force]"""
    from .commands import cmd_translate
    to, args = _opt(args, "--to")
    src, args = _opt(args, "--from")
    limit, args = _opt(args, "--limit")
    pdf_args = [a for a in args if a != "--force"]
    return cmd_translate(_drilled(pdf_args), target_lang=(to or "EN-US"),
                         source_lang=src, limit=int(limit) if limit else None,
                         force="--force" in args)


def _do_tiddlers(args):
    """pdfdrill tiddlers <pdf> [--bibkey KEY] [--force] [--embed] [--embed-svg=false]"""
    from .commands import cmd_tiddlers
    bibkey, args = _opt(args, "--bibkey")
    # diagram SVGs: inline in the svg_tiddler field (default) or external files
    # referenced by _canonical_uri (--embed-svg=false / --no-embed-svg).
    embed_svg = not any(a in ("--embed-svg=false", "--no-embed-svg") for a in args)
    flags = ("--force", "--embed", "--embed-svg=false", "--embed-svg=true", "--no-embed-svg")
    pdf_args = [a for a in args if a not in flags]
    return cmd_tiddlers(_pdf(pdf_args), force="--force" in args,
                        embed="--embed" in args, bibkey=bibkey, embed_svg=embed_svg)


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


def _do_bibsource(args):
    """pdfdrill bibsource <pdf> [--bbl f.bbl] [--bib f.bib] [--force]"""
    from .commands import cmd_bibsource
    pdf_args: list[str] = []
    bib = bbl = None
    force = False
    i = 0
    while i < len(args):
        if args[i] == "--bib" and i + 1 < len(args):
            bib = args[i + 1]; i += 2
        elif args[i] == "--bbl" and i + 1 < len(args):
            bbl = args[i + 1]; i += 2
        elif args[i] == "--force":
            force = True; i += 1
        else:
            pdf_args.append(args[i]); i += 1
    return cmd_bibsource(_pdf(pdf_args), bib_path=bib, bbl_path=bbl, force=force)


def _do_report(args):
    """pdfdrill report <pdf> [--force] [--embed] [--scale 1.0]"""
    from .commands import cmd_report
    scale, args = _opt(args, "--scale")
    pdf_args = [a for a in args if a not in ("--force", "--embed")]
    return cmd_report(_pdf(pdf_args), force="--force" in args, embed="--embed" in args,
                      scale=float(scale) if scale else 1.0)


def _do_scikgtex(args):
    """pdfdrill scikgtex <pdf> [--compile]"""
    from .commands import cmd_scikgtex
    pdf_args = [a for a in args if a != "--compile"]
    return cmd_scikgtex(_pdf(pdf_args), compile="--compile" in args)


def _do_stex(args):
    """pdfdrill stex <pdf> [--stex] [--compile]"""
    from .commands import cmd_stex
    flavor = "stex" if "--stex" in args else "latex"
    pdf_args = [a for a in args if a not in ("--stex", "--compile")]
    return cmd_stex(_pdf(pdf_args), flavor=flavor, compile="--compile" in args)


def _do_svg(args):
    """pdfdrill svg <pdf|tex> [--limit N] [--force]"""
    from .commands import cmd_svg
    pos: list[str] = []
    limit = None
    force = False
    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1]); i += 2
        elif args[i] == "--force":
            force = True; i += 1
        else:
            pos.append(args[i]); i += 1
    if not pos:
        raise ValueError("Usage: pdfdrill svg <pdf|tex> [--limit N] [--force]")
    t = Path(pos[0])
    if not t.exists():
        raise FileNotFoundError(f"Not found: {t}")
    return cmd_svg(t, limit=limit, force=force)


def _do_rulebook(args):
    """pdfdrill rulebook <pdf|md> [--force]"""
    from .commands import cmd_rulebook
    rest = [a for a in args if a != "--force"]
    return cmd_rulebook(_drilled(rest), force="--force" in args)


def _do_locate(args):
    """pdfdrill locate <pdf>"""
    from .commands import cmd_locate
    return cmd_locate(_pdf(args))


def _do_clean(args):
    """pdfdrill clean <pdf|md>"""
    from .commands import cmd_clean
    if not args:
        raise ValueError("No file specified.")
    return cmd_clean(Path(args[0]))


def _do_llmtext(args):
    """pdfdrill llmtext <pdf|md> [--delimiter %%%%] [--no-split]"""
    from .commands import cmd_llmtext
    delim, args = _opt(args, "--delimiter")
    rest = [a for a in args if a != "--no-split"]
    return cmd_llmtext(_drilled(rest), delimiter=delim or "%%%%",
                       split="--no-split" not in args)


def _do_visionocr(args):
    """pdfdrill visionocr <pdf> [--ingest J] [--dpi N] [--pages N|N-M|all] [--force]"""
    from .commands import cmd_visionocr
    ingest, args = _opt(args, "--ingest")
    dpi, args = _opt(args, "--dpi")
    pages_s, args = _opt(args, "--pages")
    force = "--force" in args
    rest = [a for a in args if a != "--force"]
    if not rest:
        raise ValueError("No file specified.")
    pages = None
    if pages_s and pages_s != "all":
        pages = []
        for part in pages_s.split(","):
            if "-" in part:
                a, b = part.split("-", 1)
                pages.extend(range(int(a), int(b) + 1))
            else:
                pages.append(int(part))
    return cmd_visionocr(_pdf(rest), ingest=ingest, dpi=int(dpi) if dpi else 200,
                         pages=pages, force=force)


def _do_mathcheck(args):
    """pdfdrill mathcheck <pdf|md> [--limit N]  — flag flattened (non-LaTeX) formulas"""
    from .commands import cmd_mathcheck
    lim, rest = _opt(args, "--limit")
    if not rest:
        raise ValueError("No file specified.")
    return cmd_mathcheck(_drilled(rest), limit=int(lim) if lim else 8)


def _do_classify(args):
    """pdfdrill classify <pdf|md> [--k N]  — MSC/subject classification via vocabnet"""
    from .commands import cmd_classify
    k, rest = _opt(args, "--k")
    if not rest:
        raise ValueError("No file specified.")
    return cmd_classify(_drilled(rest), k=int(k) if k else 8)


def _do_identifiers(args):
    """pdfdrill identifiers <pdf>"""
    from .commands import cmd_identifiers
    return cmd_identifiers(_pdf(args))


def _do_booktoc(args):
    """pdfdrill booktoc <pdf>"""
    from .commands import cmd_booktoc
    return cmd_booktoc(_pdf(args))


def _do_gaps(args):
    """pdfdrill gaps <pdf|md>"""
    from .commands import cmd_gaps
    return cmd_gaps(_drilled(args))


def _do_markdown(args):
    """pdfdrill markdown <file.md> [--bibkey K] [--force]"""
    from .commands import cmd_markdown
    bibkey, args = _opt(args, "--bibkey")
    rest = [a for a in args if a != "--force"]
    if not rest:
        raise ValueError("No Markdown file specified.")
    return cmd_markdown(Path(rest[0]), bibkey=bibkey, force="--force" in args)


def _do_latexbook(args):
    """pdfdrill latexbook <book.tex> [--bibkey K] [--force] [--no-svg]"""
    from .commands import cmd_latexbook
    pos: list[str] = []
    bibkey = None
    force = False
    no_svg = False
    i = 0
    while i < len(args):
        if args[i] == "--bibkey" and i + 1 < len(args):
            bibkey = args[i + 1]; i += 2
        elif args[i] == "--force":
            force = True; i += 1
        elif args[i] == "--no-svg":
            no_svg = True; i += 1
        else:
            pos.append(args[i]); i += 1
    if not pos:
        raise ValueError("Usage: pdfdrill latexbook <book.tex> [--bibkey K] [--force] [--no-svg]")
    t = Path(pos[0])
    if not t.exists():
        raise FileNotFoundError(f"Not found: {t}")
    return cmd_latexbook(t, bibkey=bibkey, force=force, no_svg=no_svg)


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


def _do_citedrill(args):
    """pdfdrill citedrill <pdf|md> [--limit N] [--force]  — drill into citations:
    find download links + fetch the cited PDFs, stamp drill status on each Reference."""
    from .commands import cmd_citedrill
    limit, rest = _opt(args, "--limit")
    rest = [a for a in rest if a != "--force"]
    return cmd_citedrill(_drilled(rest), limit=int(limit) if limit else None,
                         force="--force" in args)


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
    # Primary: the help body GENERATED from the canonical commands.yaml manifest
    # (`tools/skillsync.py render-help`), so --help can never drift from the
    # command surface again. Falls back to the hand-written text below when the
    # generated file isn't present (e.g. a partial checkout).
    _gen = Path(__file__).with_name("_help_generated.txt")
    if _gen.exists():
        print(_gen.read_text().rstrip())
        return
    print("""pdfdrill — portable PDF drill-down toolkit

Input: <pdf> may be a local path OR an https URL from a known host. arXiv URLs/ids
(https://arxiv.org/abs/<id>, /pdf/<id>, or a bare 2510.11170v2) download the PDF
once (cached) and unlock the FREE routes — `abstract` reads the abs page and
`latex` downloads the e-print .tgz (gold equations), so MathPix is skipped by
default (use `mathpix --force` to override).

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
  pdfdrill rasterize <pdf>     Rasterize page(s) to PNG/JPEG for visual inspection (pdftoppm) → sidecar; --pages N|N-M|all --dpi 150. Read the images to see charts/equations/layout
  pdfdrill attachments <pdf>   List embedded file attachments (pdfdetach + pypdf); --extract saves them to the sidecar. Surfaces embedded spreadsheets/data invisible to text/MathPix
  pdfdrill formfields <pdf>    Read interactive AcroForm field values (pypdf get_fields): name/value/type/options. For government/Formulare PDFs
  pdfdrill extractimages <pdf> Extract embedded raster image BYTES to files (pdfimages -png); --pages N-M --all-formats. Vector charts excluded (use rasterize)
  pdfdrill tables <pdf>        Extract tables KEYLESS offline (pdfplumber extract_tables) → tables.json + tables.md; --pages N-M
  pdfdrill mathpix <pdf>       Download MathPix OCR (lines.json, md, tex.zip); --force re-uploads
  pdfdrill ocr <pdf>           MathPix-free OCR: tesseract → MathPix-compatible lines.json (--lang eng+equ, --ppi N). Plain text only (no LaTeX/CDN)
  pdfdrill continuity <pdf>    Full-page OCR of the MARGINS → page-sequence markers (Seite N von M / Fortsetzung) MathPix's content crop drops; attaches seq to Page objects
  pdfdrill pageside <pdf>     Classify each page recto/verso (book left/right) from page-number parity+position + side-note column asymmetry + sequence alternation; attaches page_side to model Pages (column roles flip with the side)
  pdfdrill entities <pdf>      Commercial entities per page: IBAN (mod-97 validated + BLZ/Konto/bank), BIC, German address, Steuer-/Kassen-/Aktenzeichen. Zero external tools
  pdfdrill segment <pdf>       Partition a scanned bundle into ordered documents (by sender/identifier + continuity number); flags duplicate copies
  pdfdrill elements <pdf>      Find layout elements (postal address / BOM line) via the geometric-attention GNN over tesseract word boxes → content-addressed tiddlers (--model M.npz)
  pdfdrill semantic <pdf>      Build the semantic graph (CSP): extractors become sensors emitting evidence; entities (Company/Person/BankAccount) accumulate it. --store graph.json accumulates ACROSS documents
  pdfdrill fontid <pdf>        VISUAL font id for scanned/OCR input (no font layer): WORD crops → torch-free ONNX font-classify → vote WITHIN each OCR block, so font is reported per text FIELD (heading/body/fine-print), not one doc vote. Per-field confidence; weak on scanned generic sans. --limit 12 --ppi 200
  pdfdrill spellqc <pdf>       Dictionary-assisted de-hyphenation QC (hunspell via spylls→enchant→.dic-set, on-demand per language): join/keep/REVIEW each line-break hyphen. Surfaces OCR fragments to fix
  pdfdrill stex <pdf>          Project the semantic graph to enriched LaTeX: acronyms/glossary/Table-of-Symbols/index (--compile runs lualatex), or sTeX smodule/symdecl/symref (--stex). Needs `semantic` first
  pdfdrill scikgtex <pdf>      Project to SciKGTeX-annotated LaTeX → compiled PDF carries ORKG contribution metadata (title/authors/field + research-problem/method/result roles + numeric facts + bib-DOI links) as XMP/RDF. --compile (lualatex + vendored scikgtex)
  pdfdrill qr <pdf>            Scan QR codes & barcodes (zxing-cpp): GiroCode/EPC payment QR (creditor/IBAN/amount/reference) + Data Matrix franking marks — confirmation data outside the text layer. --dpi 300 --formats QRCode,DataMatrix
  pdfdrill ordered <pdf>       Segment an ORDERED scan stack into documents (gap scoring + DataMatrix tracking codes → 2-level mailing/letter-enclosure). Commercial provenance (publisher=sender, receiver). --threshold 0.5. (Shuffled bundle → use `segment`)
  pdfdrill autosegment <pdf>   AUTO-PICK ordered vs shuffled: contiguous per-sender runs → `ordered` (gap scorer); interleaved → `segment` (signature grouping). Then runs the right one
  pdfdrill selftest <pdf|dir>  DIAGNOSTIC GRID: run the command battery across a PDF (or every PDF in a folder), log OK/⊘-n/a/✗-ERROR + the actual result per command → selftest.log. --full adds entities/elements/semantic
  pdfdrill model <pdf>         Build unified docmodel from lines.json (auto-chains mathpix, falls back to tesseract ocr if no MathPix); --bibkey KEY sets the tiddler prefix (persisted)
  pdfdrill compare <pdf>       LaTeX | KaTeX | MathPix-image comparison HTML (auto-chains model)
  pdfdrill report <pdf>        Full inline+display math report (formula-report.html). --scale N scales each KaTeX render to the CDN image height (1.0=same, 2.0=200%); --embed
  pdfdrill latex <pdf>         Ingest author .tex/.tgz as a `tex` provenance (original+expanded LaTeX); --tex <path>
  pdfdrill latexbook <book.tex> Source-only model + TikZ/table SVGs + KaTeX formula report from LaTeX (no PDF/MathPix); --no-svg to skip rendering
  pdfdrill markdown <md>      Build a source-only model from LLM-summary Markdown (yt2tw route): sections/paragraphs/math/lists + cite{} commands linked to the gold ```bibtex appendix (or the numbered References list). --bibkey K
  pdfdrill identifiers <pdf>  Front-matter scan (scoped by the booktoc offset): checksum-valid ISBN/ISSN/DOI/arXiv + German ids + ALL-CAPS named-entity candidates (publisher/author)
  pdfdrill booktoc <pdf>      Greppable TOC with printed→PDF page alignment (front-matter offset from title↔section matches): grep a chapter/section name → its PDF page
  pdfdrill gaps <pdf|md>      Report MISSING information (cohomology-as-linter): acronyms used but never expanded, undeclared math symbols, novelty claims without citations, unmatched in-text citations
  pdfdrill llmtext <pdf|md>   Flat LLM dump: per unit the tiddler title + paragraph text / formula latex, document order, units split on double line breaks + separated by --delimiter (default %%%%); empty formulas skipped
  pdfdrill clean <pdf|md>     Strip MathPix LaTeX residuals from the model: a leading section* command merged into a paragraph -> the title alone + kind/refnum fields (so semantic analysis sees plain text)
  pdfdrill locate <pdf>       Locate embedded images on their pages (canonical pt/top-left coords + normalized [0,1] + PDF object number), detect full-page/template images, and COMPARE to MathPix regions (IoU) incl. MathPix-only figures
  pdfdrill rulebook <pdf|md>  Claims/definitions -> kitems (fixpoint, evidence spans) -> rulebook.md: one supported/accepted statement per line with a [->k:hash] drill-down anchor + kitem tiddlers
  pdfdrill svg <pdf|tex>       Render TikZ diagrams + tables to SVG via latex->dvisvgm (KaTeX can't); embeds in the report
  pdfdrill folder <dir>        Build the full structure for every PDF in <dir> from existing
                               .lines.json/.bib/.md — runs all levels, NO MathPix/Perplexity calls
  pdfdrill snip <pdf>          OCR each equation crop via MathPix Snip (/v3/text) → competing column; --limit N
  pdfdrill snip <pdf> --image <path|url>            Deliver+OCR ANY special image (not just equations)
  pdfdrill snip <pdf> --page N --rect x0,y0,x1,y1   Rasterize+deliver a region crop (PNG to Read) + OCR it; the crop is delivered even if OCR is unavailable
  pdfdrill candidates <pdf>    Export equation crops as a manifest for an LLM to read; --provider P --limit N
  pdfdrill ingest <pdf> <json> Attach externally-produced {eq_id,latex} candidates as a provenance column; --provider P
  pdfdrill vision <pdf>        GPT-4o vision reads every MathPix CDN crop (incl. table-cell images) → math/TikZ/gnuplot/table as the `openai` provenance; --limit N (needs OPENAI_API_KEY)
  pdfdrill embedimages <pdf>   Lift pdfimages + pdfplumber image rects into the model as EmbeddedImage nodes (pixel size/encoding/ppi + page rect), fused onto MathPix crops they contain
  pdfdrill geometry <pdf>      Fuse pdftotext -tsv layout (indent/margins) onto the model — substrate for block detection
  pdfdrill tiddlers <pdf>      Emit a TiddlyWiki JSON tiddler array (latex/displayMode/canonical_uri/width/height) for quick inspection; --bibkey KEY sets the title prefix + filename. Diagram SVGs inline by default; --embed-svg=false writes them to .drill/svg/<title>.svg and references via _canonical_uri (leaner store)
  pdfdrill translate <pdf>     DeepL-translate the document IN PLACE (--to EN-US --from RU): writes the changed tiddler file (translated text field) AND a bi-layer Markdown <bibkey>.md (translation + hidden source, CSS toggle); original kept under <field>_source (needs DEEPL_API_KEY)
  pdfdrill lists <pdf>         Nest flat ListItems into recursive List blocks using fused indentation (auto-chains geometry)
  pdfdrill algorithms <pdf>    Reconstruct Algorithm blocks from MathPix pseudocode lines (caption + indented steps)
  pdfdrill annotate <pdf>      Promote hyperlink annotations into the model as first-class Link nodes (uri + rect Region)
  pdfdrill score <pdf>         Score equations by cross-provenance agreement + snip confidence; flags review candidates
  pdfdrill nlp <pdf>           Stanza NLP over prose (POS/lemma/dependency + NER → props['nlp']); --limit N --pages N --types T,T  (optional [nlp] extra)
  pdfdrill escalate <pdf>      Phase-3: export flagged equations for a second LLM reading; --limit N
  pdfdrill relearn <pdf>       Phase-3: re-score after ingest; report resolved vs still-flagged
  pdfdrill eqnums <pdf>        Fuse equation numbers ("(N)") from margin geometry for ||FO/||FREF transclusion
  pdfdrill bibliography <pdf>  Parse the References section into Reference nodes (citekey/author/year/text)
  pdfdrill bibsource <pdf>     Ingest the author's GOLD bibliography (--bbl file.bbl + --bib file.bib): alpha label↔citekey↔fields, links in-text citations by label. No API.
  pdfdrill bibfetch <pdf>      Enrich References with full BibTeX via Perplexity SONAR; --limit N (needs PERPLEXITY_API_KEY)
  pdfdrill toc <pdf>           Table of contents
  pdfdrill abstract <pdf>      Abstract from first pages
  pdfdrill fonts <pdf>         Font analysis, math font detection
  pdfdrill status <pdf>        What is already known
  pdfdrill doctor              Requirement check: system tools (poppler/tesseract/LaTeX+dvisvgm), Python deps, API keys + the apt-get fix line

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


def _do_skill(args):
    """pdfdrill skill --emit DIR | --json | --check  (read-only; bundled SKILL folder)"""
    from .skill_cmd import run
    return run(args)


def _do_steps(args):
    """pdfdrill steps <cmd> <pdf|md> — show the prerequisite chain for a command
    (what's already done, what `--ensure` would auto-run first)."""
    from . import planner
    if len(args) < 2:
        raise ValueError("usage: pdfdrill steps <cmd> <pdf>")
    return planner.describe(args[0], _drilled(args[1:]))


def _do_remath(args):
    """pdfdrill remath <pdf> [--pages N|N-M|all] [--force] — rebuild MathPix-quality
    Markdown (LaTeX math) from rendered pages via Claude delegation (keyless)."""
    from .commands import cmd_remath
    pages_s, rest = _opt(args, "--pages")
    rest = [a for a in rest if a != "--force"]
    pages = None
    if pages_s and pages_s.lower() != "all":
        if "-" in pages_s:
            a, b = pages_s.split("-", 1); pages = list(range(int(a), int(b) + 1))
        else:
            pages = [int(pages_s)]
    return cmd_remath(_pdf(rest), pages=pages, force="--force" in args)


def _do_retrieve(args):
    """pdfdrill retrieve <pdf|md> "<question>" [--k N] [--json] — top-k relevant
    units as grounded context (the chat-proxy question transformation)."""
    from .commands import cmd_retrieve
    k, rest = _opt(args, "--k")
    as_json = "--json" in rest
    rest = [a for a in rest if a != "--json"]
    if len(rest) < 2:
        raise ValueError('usage: pdfdrill retrieve <pdf> "<question>" [--k N] [--json]')
    return cmd_retrieve(_drilled(rest[:1]), rest[1], k=int(k) if k else 8,
                        as_json=as_json)


def _do_combine(args):
    """pdfdrill combine <doc> <doc> [...] --out FILE [--force] — merge several
    drilled docs into one combined store for multi-document chat/retrieve."""
    from .commands import cmd_combine
    out, rest = _opt(args, "--out")
    force = "--force" in rest
    rest = [a for a in rest if a != "--force"]
    if not out:
        raise ValueError('usage: pdfdrill combine <doc> <doc> … --out FILE [--force]')
    if not rest:
        raise ValueError("combine needs at least one input document.")
    pdfs = [_drilled([a]) for a in rest]
    return cmd_combine(Path(out), pdfs, force=force)


def _do_chatlog(args):
    """pdfdrill chatlog <pdf|md> --question Q --answer A [--units id,id] [--model M]
    — store one Q&A turn (transcript + answer kitem in the semantic graph)."""
    from .commands import cmd_chatlog
    q, rest = _opt(args, "--question")
    a, rest = _opt(rest, "--answer")
    units, rest = _opt(rest, "--units")
    model, rest = _opt(rest, "--model")
    if not rest or q is None or a is None:
        raise ValueError('usage: pdfdrill chatlog <pdf> --question Q --answer A '
                         '[--units id,id] [--model M]')
    return cmd_chatlog(_drilled(rest), q, a, units=units or "", model=model or "")


# Module-level command table — the single dispatch surface, also read by
# `pdfdrill skill --check` and the skill-sync drift gate (manifest <-> HANDLERS).
HANDLERS = {
        "doctor": _do_doctor,
        "config": _do_config,
        "artifacts": _do_artifacts,
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
        "ocr": _do_ocr,
        "continuity": _do_continuity,
        "pageside": _do_pageside,
        "entities": _do_entities,
        "segment": _do_segment,
        "elements": _do_elements,
        "semantic": _do_semantic,
        "qr": _do_qr,
        "fontid": _do_fontid,
        "spellqc": _do_spellqc,
        "ordered": _do_ordered,
        "autosegment": _do_autosegment,
        "selftest": _do_selftest,
        "rasterize": _do_rasterize,
        "attachments": _do_attachments,
        "formfields": _do_formfields,
        "extractimages": _do_extractimages,
        "tables": _do_tables,
        "model": _do_model,
        "compare": _do_compare,
        "snip": _do_snip,
        "candidates": _do_candidates,
        "ingest": _do_ingest,
        "vision": _do_vision,
        "llm": _do_llm,
        "embedimages": _do_embedimages,
        "geometry": _do_geometry,
        "tiddlers": _do_tiddlers,
        "translate": _do_translate,
        "lists": _do_lists,
        "algorithms": _do_algorithms,
        "annotate": _do_annotate,
        "score": _do_score,
        "nlp": _do_nlp,
        "escalate": _do_escalate,
        "relearn": _do_relearn,
        "eqnums": _do_eqnums,
        "bibliography": _do_bibliography,
        "bibsource": _do_bibsource,
        "bibfetch": _do_bibfetch,
        "citedrill": _do_citedrill,
        "report": _do_report,
        "folder": _do_folder,
        "latex": _do_latex,
        "latexbook": _do_latexbook,
        "markdown": _do_markdown,
        "identifiers": _do_identifiers,
        "booktoc": _do_booktoc,
        "gaps": _do_gaps,
        "llmtext": _do_llmtext,
        "mathcheck": _do_mathcheck,
        "visionocr": _do_visionocr,
        "classify": _do_classify,
        "clean": _do_clean,
        "locate": _do_locate,
        "rulebook": _do_rulebook,
        "svg": _do_svg,
        "stex": _do_stex,
        "scikgtex": _do_scikgtex,
        "skill": _do_skill,
        "steps": _do_steps,
        "retrieve": _do_retrieve,
        "combine": _do_combine,
        "chatlog": _do_chatlog,
        "remath": _do_remath,
    }
