#!/usr/bin/env python3
"""
extract_addresses.py — pull postal addresses out of OCR output, using geometry
when available (Tesseract TSV / box) and libpostal (pypostal) for parsing, with
optional invoice2data template extraction for structured invoice fields.

Why three layers:

  * libpostal's parse_address() only *parses* a string you already believe is an
    address; it cannot find addresses in free text. So we detect candidates
    first, then parse.

  * Flattened OCR text loses block structure, which is exactly what tells a
    recipient block apart from a sender footer in a two-column invoice. Tesseract
    TSV/box output carries the geometry that lets us rebuild that structure.

  * invoice2data adds template-driven field extraction (invoice number, totals,
    dates) AND can capture an address block by regex with high precision for
    known issuers. We feed those captured blocks back through libpostal.

Input formats (--format auto picks by extension):
  text / md   plain or markdown OCR text          (no geometry)
  tsv         `tesseract IMG out tsv`              (word boxes + block/par/line + conf)
  box         `tesseract IMG out makebox`          (char boxes, bottom-left origin)

Geometry readers reconstruct lines and emit a blank boundary segment wherever a
block changes or a vertical gap opens, so the same upward-context detector works
unchanged and never merges two spatially separate blocks.

Stage dependencies:
  candidate detection + TSV/box parsing  -> pure Python (run with --no-parse)
  address component parsing              -> libpostal + `postal`
  invoice field / address-block capture  -> invoice2data (+ its template YAML)

Usage:
  extract_addresses.py FILE... [--format auto|text|tsv|box] [--min-conf N]
                       [--no-parse] [--expand] [--json]
                       [--i2d TEMPLATE_DIR] [--require road postcode city ...]

Examples:
  extract_addresses.py page-20.md
  tesseract page-20.png stdout tsv > page-20.tsv && extract_addresses.py page-20.tsv
  extract_addresses.py page-20.tsv --min-conf 60 --json
  extract_addresses.py invoice.tsv --i2d ./templates --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

# ---------------------------------------------------------------------------
# Detection heuristics (DE-tuned; override the anchor with --postcode)
# ---------------------------------------------------------------------------
# A German PLZ is 5 digits FOLLOWED by a city word. That trailing letter is what
# separates "51515 Kürten" from invoice/customer/HRB numbers and phone groups,
# none of which are followed by a letter. German thousands use '.', so money like
# "22.870" never even forms a 5-digit run.
DEFAULT_POSTCODE = r"(?<!\d)\d{5}(?!\d)\s*,?\s*[A-Za-zÄÖÜäöüß]"

SEPARATORS = re.compile(r"\s*(?:[•·|;]|,)\s*")
MD_LEAD = re.compile(r"^\s*(?:[#>]+\s*|[-*+]\s+|\d+\.\s+)")
MD_INLINE = re.compile(r"[`*_]{1,3}")
MD_RULE = re.compile(r"^\s*([-*_=])\1{2,}\s*$")

BBox = tuple[int, int, int, int]  # (x0, y0, x1, y1) in the source's pixel space


@dataclass
class Segment:
    text: str                       # "" marks a blank line / block boundary
    line: int                       # source line no. (text) or reconstructed idx
    bbox: BBox | None = None
    conf: float | None = None       # min word confidence on the line (TSV)


# ---------------------------------------------------------------------------
# Reader: plain / markdown text
# ---------------------------------------------------------------------------
def _strip_markdown(line: str) -> str:
    if MD_RULE.match(line):
        return ""
    line = MD_LEAD.sub("", line)
    line = MD_INLINE.sub("", line)
    return re.sub(r"[ \t]+", " ", line).strip()


def read_text(raw: str) -> list[Segment]:
    segs: list[Segment] = []
    for i, line in enumerate(raw.splitlines(), start=1):
        clean = _strip_markdown(line)
        if not clean:
            segs.append(Segment("", i))
            continue
        parts = [p.strip() for p in SEPARATORS.split(clean) if p.strip()]
        for p in (parts or [clean]):
            segs.append(Segment(p, i))
    return segs


# ---------------------------------------------------------------------------
# Reader: Tesseract TSV  (level page block par line word left top w h conf text)
# ---------------------------------------------------------------------------
def read_tsv(raw: str, min_conf: float = 0.0) -> list[Segment]:
    lines: dict[tuple[int, int, int, int], list] = {}
    order: list[tuple[int, int, int, int]] = []
    for row in raw.splitlines():
        if not row.strip():
            continue
        f = row.split("\t")
        if f[0] == "level":            # header row
            continue
        if len(f) < 12:                # structural row without a text column
            f = f + [""] * (12 - len(f))
        try:
            level = int(f[0])
            page, block, par, ln = int(f[1]), int(f[2]), int(f[3]), int(f[4])
            left, top, w, h = int(f[6]), int(f[7]), int(f[8]), int(f[9])
            conf = float(f[10])
        except ValueError:
            continue
        if level != 5:
            continue
        text = f[11].strip()
        if not text or conf < min_conf:
            continue
        key = (page, block, par, ln)
        if key not in lines:
            lines[key] = []
            order.append(key)          # encounter order = Tesseract reading order
        lines[key].append((left, top, w, h, conf, text))

    segs: list[Segment] = []
    prev_block: int | None = None
    idx = 0
    for key in order:
        _, block, _, _ = key
        words = sorted(lines[key], key=lambda r: r[0])
        text = " ".join(w[5] for w in words)
        x0 = min(w[0] for w in words)
        y0 = min(w[1] for w in words)
        x1 = max(w[0] + w[2] for w in words)
        y1 = max(w[1] + w[3] for w in words)
        conf = min(w[4] for w in words)
        idx += 1
        if prev_block is not None and block != prev_block:
            segs.append(Segment("", idx))           # column / block boundary
        segs.append(Segment(text, idx, (x0, y0, x1, y1), conf))
        prev_block = block
    return segs


# ---------------------------------------------------------------------------
# Reader: Tesseract makebox  (char left bottom right top [page]) bottom-left origin
# ---------------------------------------------------------------------------
def read_box(raw: str, space_factor: float = 0.6,
             para_gap_factor: float = 1.6) -> list[Segment]:
    chars = []
    for row in raw.splitlines():
        if not row.strip():
            continue
        f = row.split()
        if len(f) < 5:
            continue
        sym = f[0]
        try:
            left, bottom, right, top = int(f[1]), int(f[2]), int(f[3]), int(f[4])
        except ValueError:
            continue
        if sym in ("\t", ""):
            continue
        chars.append((sym, left, bottom, right, top))
    if not chars:
        return []

    medh = median([t - b for _, _, b, _, t in chars]) or 1
    medw = median([r - l for _, l, _, r, _ in chars]) or 1

    # cluster chars into lines by vertical centre (y increases upward)
    buckets: list[dict] = []
    for c in sorted(chars, key=lambda c: -((c[2] + c[4]) / 2)):
        cy = (c[2] + c[4]) / 2
        for L in buckets:
            if abs(L["cy"] - cy) <= medh * 0.7:
                L["cy"] = (L["cy"] * L["n"] + cy) / (L["n"] + 1)
                L["n"] += 1
                L["chars"].append(c)
                break
        else:
            buckets.append({"cy": cy, "n": 1, "chars": [c]})

    buckets.sort(key=lambda L: -L["cy"])             # top of page first
    segs: list[Segment] = []
    idx = 0
    prev_bottom: int | None = None
    for L in buckets:
        cs = sorted(L["chars"], key=lambda c: c[1])  # left to right
        text, prev_right = "", None
        for sym, left, _b, right, _t in cs:
            if prev_right is not None and (left - prev_right) > medw * space_factor:
                text += " "
            text += sym
            prev_right = right
        text = text.strip()
        if not text:
            continue
        x0 = min(c[1] for c in cs)
        x1 = max(c[3] for c in cs)
        ytop = max(c[4] for c in cs)
        ybot = min(c[2] for c in cs)
        idx += 1
        if prev_bottom is not None and (prev_bottom - ytop) > medh * para_gap_factor:
            segs.append(Segment("", idx))            # paragraph break
        segs.append(Segment(text, idx, (x0, ytop, x1, ybot), None))
        prev_bottom = ybot
    return segs


def resolve_format(path: Path, fmt: str) -> str:
    if fmt != "auto":
        return fmt
    return {".tsv": "tsv", ".box": "box"}.get(path.suffix.lower(), "text")


def load_segments(path: Path, fmt: str, min_conf: float) -> tuple[list[Segment], str]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    fmt = resolve_format(path, fmt)
    if fmt == "tsv":
        return read_tsv(raw, min_conf), raw
    if fmt == "box":
        return read_box(raw), raw
    return read_text(raw), raw


def to_plaintext(segs: list[Segment]) -> str:
    """Reconstruct newline-delimited text (for invoice2data) from segments."""
    return "\n".join(s.text for s in segs)


# ---------------------------------------------------------------------------
# Candidate detection
# ---------------------------------------------------------------------------
@dataclass
class Candidate:
    text: str
    lines: tuple[int, int]
    bbox: BBox | None = None
    conf: float | None = None


def _union(boxes: list[BBox]) -> BBox | None:
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def find_candidates(segs: list[Segment], anchor: re.Pattern,
                    context: int, max_ctx_len: int) -> list[Candidate]:
    out: list[Candidate] = []
    for idx, seg in enumerate(segs):
        if not seg.text or not anchor.search(seg.text):
            continue
        collected: list[Segment] = []
        j = idx - 1
        while j >= 0 and len(collected) < context:
            prev = segs[j]
            if not prev.text or len(prev.text) > max_ctx_len or anchor.search(prev.text):
                break
            collected.append(prev)
            j -= 1
        collected.reverse()
        members = collected + [seg]
        confs = [m.conf for m in members if m.conf is not None]
        out.append(Candidate(
            text=", ".join(m.text for m in members),
            lines=(members[0].line, seg.line),
            bbox=_union([m.bbox for m in members]),
            conf=min(confs) if confs else None,
        ))
    seen, uniq = set(), []
    for c in out:
        key = re.sub(r"\s+", " ", c.text).lower().strip(" ,")
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


# ---------------------------------------------------------------------------
# libpostal
# ---------------------------------------------------------------------------
def _preload_libpostal_lib() -> bool:
    """dlopen libpostal.so RTLD_GLOBAL so the `postal` C-extension imports even
    when the lib lives in /usr/local/lib without `ldconfig` having been run (a
    from-source `make install` leaves it off the default loader path). No root,
    no LD_LIBRARY_PATH needed."""
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


def load_parser():
    try:
        from postal.parser import parse_address  # type: ignore
        return parse_address
    except ImportError:
        # The binding may be installed but libpostal.so off the loader path;
        # preload it and retry before giving up.
        if _preload_libpostal_lib():
            try:
                from postal.parser import parse_address  # type: ignore
                return parse_address
            except ImportError:
                pass
        sys.stderr.write(
            "error: 'postal' (libpostal) not installed. Build libpostal, then "
            "`pip install postal`. https://github.com/openvenues/pypostal\n"
            "Run with --no-parse to inspect candidates without it.\n")
        sys.exit(2)


def parse_components(parse_fn, text: str) -> dict[str, str]:
    out: dict[str, list[str]] = {}
    for value, label in parse_fn(text):
        out.setdefault(label, []).append(value)
    return {k: " ".join(v) for k, v in out.items()}


def is_valid(comp: dict[str, str], required: set[str]) -> bool:
    req = set(required)
    if {"road", "house_number"} <= req:
        if not (comp.get("road") or comp.get("house_number")):
            return False
        req -= {"road", "house_number"}
    return all(comp.get(k) for k in req)


# ---------------------------------------------------------------------------
# invoice2data
# ---------------------------------------------------------------------------
ADDR_FIELD = re.compile(r"address|addr|anschrift|empf[äa]nger|recipient|absender|issuer_addr", re.I)


def _import_invoice_template():
    """InvoiceTemplate moved between layouts; 0.2.x is flat, newer is nested."""
    try:
        from invoice2data.template import InvoiceTemplate          # 0.2.x
        return InvoiceTemplate
    except ImportError:
        from invoice2data.extract.invoice_template import InvoiceTemplate  # >=0.3
        return InvoiceTemplate


def _load_templates(template_dir: str) -> list:
    """PyYAML-6-safe loader. invoice2data 0.2.36's own read_templates calls
    yaml.load() without a Loader, which PyYAML>=6 rejects, so we load here and
    build the template objects ourselves (and skip the date/amount/invoice_number
    assertion so address-only templates are allowed)."""
    import os
    import yaml
    InvoiceTemplate = _import_invoice_template()
    out = []
    for root, _dirs, files in os.walk(template_dir):
        for name in sorted(files):
            if not name.endswith((".yml", ".yaml")):
                continue
            with open(os.path.join(root, name), encoding="utf-8") as fh:
                tpl = yaml.safe_load(fh)
            tpl["template_name"] = name
            if "keywords" not in tpl:
                continue
            if not isinstance(tpl["keywords"], list):
                tpl["keywords"] = [tpl["keywords"]]
            out.append(InvoiceTemplate(tpl))
    return out


def run_invoice2data(plain_text: str, template_dir: str) -> dict | None:
    """Drive templates directly (extract_data in 0.2.36 hard-codes pdftotext and
    has no input_module, so it can't consume OCR text). This loop mirrors
    extract_data's internals: prepare -> match -> extract, minus the PDF step."""
    try:
        import invoice2data  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "error: invoice2data not installed. `pip install invoice2data==0.2.36`\n")
        sys.exit(2)
    import logging
    logging.getLogger("invoice2data").setLevel(logging.ERROR)
    logging.disable(logging.WARNING)            # mute its "didn't match" notices
    try:
        for t in _load_templates(template_dir):
            optimized = t.prepare_input(plain_text)
            if t.matches_input(optimized):
                return t.extract(optimized) or None
        return None
    finally:
        logging.disable(logging.NOTSET)


def i2d_address_fields(result: dict) -> list[tuple[str, str]]:
    """(field_name, value) pairs whose NAME marks them as postal. Keying on the
    name (not a value scan) avoids misreading fields like desc='Invoice 18285
    from ...' where an invoice number resembles a 'PLZ + word' anchor."""
    out = []
    for name, val in result.items():
        if isinstance(val, str) and ADDR_FIELD.search(name):
            out.append((name, " ".join(val.split())))
    return out


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
FIELD_ORDER = ["house", "house_number", "road", "unit", "level", "postcode",
               "city", "city_district", "suburb", "state", "country"]


@dataclass
class Address:
    raw: str
    components: dict[str, str]
    lines: tuple[int, int]
    source: str
    bbox: BBox | None = None
    conf: float | None = None
    expansions: list[str] = field(default_factory=list)


def fmt_addr_pretty(a: Address) -> str:
    span = f"{a.lines[0]}-{a.lines[1]}" if a.lines[1] != a.lines[0] else str(a.lines[1])
    head = f"[{a.source}:{span}]"
    if a.bbox:
        head += f" bbox={a.bbox}"
    if a.conf is not None:
        head += f" conf={a.conf:.0f}"
    lines = [f"{head}  {a.raw}"]
    keys = [k for k in FIELD_ORDER if k in a.components]
    keys += [k for k in a.components if k not in FIELD_ORDER]
    lines += [f"    {k:<13} {a.components[k]}" for k in keys]
    for i, e in enumerate(a.expansions):
        lines.append(f"    {'expansions' if i == 0 else '':<13} {e}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Extract postal addresses from OCR output via libpostal, with "
                    "Tesseract-geometry block detection and invoice2data templates.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--format", choices=["auto", "text", "tsv", "box"], default="auto",
                    help="input reader (default: by file extension)")
    ap.add_argument("--min-conf", type=float, default=0.0,
                    help="drop TSV words below this confidence (default 0)")
    ap.add_argument("--no-parse", action="store_true",
                    help="stop after candidate detection (no libpostal needed)")
    ap.add_argument("--expand", action="store_true",
                    help="include libpostal expand_address() normalisations")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--context", type=int, default=3)
    ap.add_argument("--max-ctx-len", type=int, default=50)
    ap.add_argument("--require", nargs="*", default=["road", "postcode", "city"],
                    metavar="FIELD")
    ap.add_argument("--postcode", default=DEFAULT_POSTCODE)
    ap.add_argument("--i2d", metavar="TEMPLATE_DIR",
                    help="also run invoice2data with templates from this folder")
    args = ap.parse_args(argv)

    try:
        anchor = re.compile(args.postcode)
    except re.error as e:
        sys.stderr.write(f"error: bad --postcode regex: {e}\n")
        return 2

    parse_fn = None if args.no_parse else load_parser()
    expand_fn = None
    if args.expand and not args.no_parse:
        from postal.expand import expand_address  # type: ignore
        expand_fn = expand_address
    required = set(args.require)

    all_cands: list[tuple[str, list[Candidate]]] = []
    i2d_addr_seen: list[tuple[str, list[tuple[str, str]]]] = []
    addrs: list[Address] = []
    invoices: list[dict] = []

    for path in args.files:
        try:
            segs, raw = load_segments(path, args.format, args.min_conf)
        except OSError as e:
            sys.stderr.write(f"warning: cannot read {path}: {e}\n")
            continue
        cands = find_candidates(segs, anchor, args.context, args.max_ctx_len)
        all_cands.append((path.name, cands))

        # invoice2data: structured fields + template-captured address blocks.
        # Feed it raw text for text/markdown (templates rely on original layout);
        # for tsv/box there is no original text, so use the reconstruction.
        i2d_fields: list[tuple[str, str]] = []
        if args.i2d:
            fmt = resolve_format(path, args.format)
            i2d_text = raw if fmt == "text" else to_plaintext(segs)
            result = run_invoice2data(i2d_text, args.i2d)
            if result:
                invoices.append({"source": path.name,
                                 **{k: (v.isoformat() if hasattr(v, "isoformat") else v)
                                    for k, v in result.items()}})
                i2d_fields = i2d_address_fields(result)
        i2d_addr_seen.append((path.name, i2d_fields))

        if args.no_parse:
            continue
        for c in cands:
            comp = parse_components(parse_fn, c.text)
            if not is_valid(comp, required):
                continue
            exps = []
            if expand_fn:
                try:
                    exps = list(expand_fn(c.text))[:5]
                except Exception:
                    exps = []
            addrs.append(Address(c.text, comp, c.lines, path.name, c.bbox, c.conf, exps))
        for fname, val in i2d_fields:
            comp = parse_components(parse_fn, val)
            if is_valid(comp, required):
                addrs.append(Address(val, comp, (0, 0), f"{path.name} (i2d:{fname})"))

    # de-dupe parsed addresses on key components
    if not args.no_parse:
        seen, dedup = set(), []
        for a in addrs:
            k = tuple(a.components.get(x, "").lower()
                      for x in ("road", "house_number", "postcode", "city"))
            if k not in seen:
                seen.add(k)
                dedup.append(a)
        addrs = dedup

    # ---- emit ----
    if args.no_parse:
        if args.json:
            payload = {"candidates": [
                {"source": s, "items": [
                    {"text": c.text, "lines": list(c.lines),
                     **({"bbox": list(c.bbox)} if c.bbox else {}),
                     **({"conf": c.conf} if c.conf is not None else {})}
                    for c in cs]} for s, cs in all_cands]}
            i2d_payload = [{"source": s, "fields": dict(fs)}
                           for s, fs in i2d_addr_seen if fs]
            if i2d_payload:
                payload["i2d_address_fields"] = i2d_payload
            if invoices:
                payload["invoices"] = invoices
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            for inv in invoices:
                print(f"# invoice2data [{inv['source']}]")
                for k, v in inv.items():
                    if k != "source":
                        print(f"    {k:<18} {v}")
            for s, cs in all_cands:
                print(f"# {s}: {len(cs)} candidate(s)")
                for c in cs:
                    span = (f"{c.lines[0]}-{c.lines[1]}"
                            if c.lines[1] != c.lines[0] else str(c.lines[1]))
                    geo = f" bbox={c.bbox}" if c.bbox else ""
                    print(f"  [{span}]{geo} {c.text}")
            for s, fs in i2d_addr_seen:
                for fname, val in fs:
                    print(f"  [i2d:{fname}] {val}")
        return 0

    if args.json:
        payload: dict = {"addresses": [
            {"source": a.source, "lines": list(a.lines), "raw": a.raw,
             "components": a.components,
             **({"bbox": list(a.bbox)} if a.bbox else {}),
             **({"conf": a.conf} if a.conf is not None else {}),
             **({"expansions": a.expansions} if a.expansions else {})}
            for a in addrs]}
        if invoices:
            payload["invoices"] = invoices
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if invoices:
            for inv in invoices:
                print(f"# invoice2data [{inv['source']}]")
                for k, v in inv.items():
                    if k != "source":
                        print(f"    {k:<18} {v}")
            print()
        print("\n\n".join(fmt_addr_pretty(a) for a in addrs)
              if addrs else "No addresses found.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
        sys.exit(0)
