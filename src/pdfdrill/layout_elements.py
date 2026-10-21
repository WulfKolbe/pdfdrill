"""
Layout-element layer — glue between pdfdrill and the vendored `tsv_gcn` GNN.

`tsv_gcn` is a pure-NumPy geometric-attention GNN over Tesseract TSV word boxes
that isolates structured layout elements (postal **addresses**, **BOM line
items**) the same way the MathPix layer isolates equations as LaTeX: each found
element gets a content-addressed identity (blake3, or sha256 fallback) and is
emitted as a TiddlyWiki tiddler (`<bibkey>_<TYPE>_<serial>`) with data fields,
a normalised `geo-projection`, and a learned `projection` embedding.

This module is the thin, **additive** wiring: it takes the document's word
boxes from `word_boxes` (the PDF's own text layer) as one combined TSV, and
calls the two public `tsv_gcn` entry points —
`crosscheck(tsv_path, model_path)` and `emit_tiddlers(tsv_path, model_path,
bibkey, source)`. It never touches the docmodel/docops pipeline; the result is
written to the sidecar as a `layout` layer + a sibling tiddlers file by the
`pdfdrill elements` command.

It degrades gracefully on every missing piece: NumPy absent, no text layer to
take word boxes from, no trained `.npz` model AND no `extract_addresses`
heuristic — each returns a clear, actionable message instead of raising. The GNN path needs a model the
caller supplies via `--model` (train one with `python -m pdfdrill.tsv_gcn
train …`); the heuristic-only path needs the optional `extract_addresses`
module on PYTHONPATH.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Optional


def numpy_available() -> bool:
    return importlib.util.find_spec("numpy") is not None


def tools_available() -> tuple[bool, str]:
    """Return (ok, message). The element layer needs NumPy (the GNN); the word
    boxes come from the PDF's own text layer, so nothing is rendered or OCR'd."""
    if not numpy_available():
        return False, ("the layout-element GNN needs NumPy. Install it with "
                       "`pip install 'pdfdrill[layout]'` (blake3; numpy is a "
                       "base dependency since 905p).")
    return True, ""


# ---------------------------------------------------------------------------
# The combined TSV the GNN consumes
# ---------------------------------------------------------------------------

def build_combined_tsv(pdf: Path, out_dir: Path, *, ppi: int = 300,
                       lang: str = "deu+eng") -> str:
    """ONE 12-column TSV for the whole document, from the PDF's own text layer.

    An address is found by what it SAYS and where it sits, so this layer needs a
    word with its text — which is the text layer's to give and no free lane's to
    read off a scan. The per-page renumbering this function used to do is gone
    with the per-image OCR calls that needed it: `pdftotext -tsv` numbers its own
    pages. `out_dir`, `ppi` and `lang` are accepted and unused — nothing is
    rendered here any more.

    Returns "" when the document has no text layer; `analyze` turns that into
    `word_boxes.no_words_note`, which names the lane rather than a binary.
    """
    from . import word_boxes
    tsv, _source = word_boxes.combined_tsv(Path(pdf))
    return tsv


# ---------------------------------------------------------------------------
# Optional libpostal component parsing (graceful — None when absent)
# ---------------------------------------------------------------------------

def _preload_libpostal() -> bool:
    """Make `libpostal.so` loadable for the `postal` C-extension without root or
    LD_LIBRARY_PATH. A from-source `make install` puts the lib in /usr/local/lib,
    which is NOT in the default linker cache unless `ldconfig` was run — so
    `import postal._parser` fails with "libpostal.so.1: cannot open shared object
    file" even though everything is installed. We dlopen the lib RTLD_GLOBAL
    first; the subsequent extension import then finds the soname already
    resident. Returns True if a lib was loaded (or already is)."""
    import ctypes
    import glob
    dirs = ["/usr/local/lib", "/usr/lib", "/usr/lib/x86_64-linux-gnu",
            "/opt/homebrew/lib", "/usr/local/lib64", "/lib"]
    names = ["libpostal.so.1", "libpostal.so", "libpostal.1.dylib", "libpostal.dylib"]
    cands = [f"{d}/{n}" for d in dirs for n in names]
    cands += sorted(g for d in dirs for g in glob.glob(f"{d}/libpostal.so*"))
    for cand in cands:
        try:
            ctypes.CDLL(cand, mode=ctypes.RTLD_GLOBAL)
            return True
        except OSError:
            continue
    return False


def _libpostal_parser():
    """Return libpostal's `parse_address` or None. libpostal (pypostal `postal`)
    is a CRF address parser trained on ~1B OSM/OpenAddresses records; it *parses*
    a known address string into components but cannot *find* addresses on a page
    — which is why it runs AFTER the heuristic/GNN locates the block. We try the
    plain import; if the shared lib isn't on the loader path we ctypes-preload it
    and retry. Returns None only when libpostal is genuinely absent."""
    try:
        from postal.parser import parse_address  # type: ignore
        return parse_address
    except Exception:
        if _preload_libpostal():
            try:
                from postal.parser import parse_address  # type: ignore
                return parse_address
            except Exception:
                return None
        return None


def _enrich_with_libpostal(addresses: list[dict]) -> int:
    """Parse each heuristic address's raw block text into clean components
    (road/house_number/postcode/city/…) via libpostal, in place. Only fills
    addresses that lack components (so it never clobbers GNN per-word labels).
    Returns the count enriched; a no-op (0) when libpostal is unavailable."""
    parse_fn = _libpostal_parser()
    if parse_fn is None:
        return 0
    from .extract_addresses import parse_components
    n = 0
    for e in addresses:
        if e.get("kind") != "address" or e.get("components"):
            continue
        txt = e.get("text") or e.get("heuristic_text") or ""
        if not txt:
            continue
        comp = parse_components(parse_fn, txt)
        if comp:
            e["components"] = comp
            e["parsed_by"] = "libpostal"
            n += 1
    return n


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def find_elements(pdf: Path, *, model_path: Optional[Path], bibkey: str,
                  source: Optional[str], blob_dir: Path, ppi: int = 300,
                  lang: str = "deu+eng", force: bool = False) -> dict[str, Any]:
    """Render → combined TSV → tsv_gcn, returning a result dict:
        {available, message, tiddlers, elements, tsv_path, source, model}
    `available` is False (with a `message`) when a prerequisite is missing.
    `elements` is the reconciled-address provenance summary; `tiddlers` the full
    emitted tiddler array (address + BOM-line) when a model is supplied."""
    ok, msg = tools_available()
    if not ok:
        return {"available": False, "message": msg, "tiddlers": [],
                "elements": [], "tsv_path": None}

    from . import tsv_gcn  # lazy: importing pulls in NumPy

    source = source or pdf.name
    blob_dir.mkdir(parents=True, exist_ok=True)
    tsv_path = blob_dir / "elements.tsv"
    if force or not tsv_path.exists():
        tsv = build_combined_tsv(pdf, blob_dir / "elements_pages", ppi=ppi, lang=lang)
        if not tsv.strip():
            from . import word_boxes
            return {"available": False, "tsv_path": None, "tiddlers": [],
                    "elements": [],
                    "message": word_boxes.no_words_note(
                        pdf, what="word boxes for the element layer")}
        tsv_path.write_text(tsv, encoding="utf-8")

    model = str(model_path) if model_path else None

    if model is None and not tsv_gcn._HAVE_EA:
        return {"available": False, "tsv_path": str(tsv_path),
                "tiddlers": [], "elements": [],
                "message": (
                    "no element source available: pass --model <model.npz> to "
                    "run the GNN (train one with `python -m pdfdrill.tsv_gcn "
                    "synth <dir> && python -m pdfdrill.tsv_gcn train <dir>/*.tsv "
                    "--labels-dir <dir> -o model.npz`), or put the "
                    "`extract_addresses` heuristic module on PYTHONPATH for the "
                    "address-only path. The combined page TSV was written to "
                    f"{tsv_path.name}.")}

    # Cross-check addresses (GNN ∩ heuristic) — works with a model, a heuristic,
    # or both; tags each address gnn+heuristic / gnn-only / heuristic-only.
    reconciled, _nodes = tsv_gcn.crosscheck(str(tsv_path), model)

    # Optional libpostal upgrade: parse heuristic address blocks into clean
    # components (road/house_number/postcode/city). Graceful no-op when absent.
    n_libpostal = _enrich_with_libpostal(reconciled)

    if model is not None:
        # Full element set (addresses + BOM lines) with projection embeddings.
        tiddlers = tsv_gcn.emit_tiddlers(str(tsv_path), model, bibkey, source)
    else:
        # Heuristic-only: emit the reconciled addresses as tiddlers (now carrying
        # libpostal components when available).
        serials: dict[str, int] = {}
        tiddlers = []
        for e in reconciled:
            code = tsv_gcn.TYPE_CODE.get(e["kind"], "LO")
            serials[code] = serials.get(code, 0) + 1
            tiddlers.append(tsv_gcn.element_to_tiddler(e, bibkey, serials[code], source))

    return {"available": True, "message": "", "tiddlers": tiddlers,
            "elements": reconciled, "tsv_path": str(tsv_path),
            "source": source, "model": model, "libpostal_enriched": n_libpostal}
