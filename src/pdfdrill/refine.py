"""170–174 — the refine loop: select → propose → validate → measure → accept → record.

A refinement is a claim that a low-confidence maths value should read
differently, carried through six stages that each have the right to stop it.
Nothing is applied because a model said so; a proposal is applied only after
it has been RENDERED and measured to sit closer to the scan than the value it
would replace.

    select    low-confidence rows, minus those the ink gate says are already fine
    propose   one re-transcription per surviving row            (status proposed)
    validate  four structural checks                            (status rejected)
    measure   render the proposal, measure it against the scan crop
    accept    keep it only when the ink distance FALLS          (status accepted)
    record    a provenance="change" realization; the original stays

THE INK METRIC USED HERE IS OURS, NOT INKDRILL'S.
inkdrill's five-tuple (components, holes, stacked, centred, offset) is a
ROW-level measurement produced by its own `compare`. `compare` DOES exist — I
first recorded that it did not, having read the top-level `--help`, which does
not list subcommands; its silence was not evidence of absence and I should have
run `compare --help`. The real reason it cannot serve here is narrower and only
visible once you run it: `compare` takes two columns of a RULED TABLE and needs
an ink region with >= 2 holes to build its lattice from. Handed a standalone
equation render and a scan crop it answers

    A: no cells (no ink region with >= 2 holes -- no table on this page)

which is correct: there is no table. So the row-level metric is unavailable for
a crop-level comparison, and what we do here is deliberately smaller:

    components   number of ink components in the crop  (glyph count)
    holes        total topological holes across them
    distance     |Δcomponents| + |Δholes|

Both terms are TOPOLOGICAL and therefore scale-free, which matters because a
standalone render and a 400-dpi page crop are never the same size. Area is not
used for exactly that reason: it would report a difference for a correct
transcription set in a different size. The metric answers "are these the same
symbols, with the same holes in them" and nothing else — it is a comparison of
two renderings, not a reading of either.

pdfdrill CONSUMES inkdrill output and never imports it: inkdrill runs as a
subprocess and we read its JSON, per the division of labour the ink commands
already follow.
"""
from __future__ import annotations

import json
import os
import re
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

STAGES = ("select", "propose", "validate", "measure", "accept", "record")

#: the proposing model, recorded on every proposal it writes
DEFAULT_AUTHOR = "minimax-m3"
NOVITA_MODEL = "minimax/minimax-m3"

#: raster resolution. 400 is the project floor (`pdf_reading.rasterize` will not
#: go below it), so the render is taken at the same number to keep the two
#: images comparable in stroke weight even though the metric is scale-free.
DPI = 400

CHANGES_NAME = "changes.json"


# ---------------------------------------------------------------------------
# changes.json
# ---------------------------------------------------------------------------

def changes_path(blob_dir: Path) -> Path:
    return Path(blob_dir) / CHANGES_NAME


def load_changes(path: Path) -> dict:
    p = Path(path)
    if not p.is_file():
        return {"proposals": []}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"proposals": []}
    d.setdefault("proposals", [])
    return d


def save_changes(path: Path, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False),
                   encoding="utf-8")
    os.replace(tmp, p)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def by_id(data: dict) -> dict:
    return {p["id"]: p for p in data.get("proposals", [])}


# ---------------------------------------------------------------------------
# inkdrill (subprocess only)
# ---------------------------------------------------------------------------

class InkUnavailable(RuntimeError):
    """inkdrill is not reachable — named, so a caller can say so plainly."""


def inkdrill_root() -> Path:
    """Where inkdrill lives. INKDRILL_ROOT overrides; ~/inkdrill is the default."""
    env = os.environ.get("INKDRILL_ROOT", "").strip()
    cands = [Path(env)] if env else []
    cands.append(Path.home() / "inkdrill")
    for c in cands:
        if (c / "inkdrill" / "__main__.py").is_file():
            return c
    raise InkUnavailable(
        "inkdrill not found. Set INKDRILL_ROOT to the checkout that contains "
        "inkdrill/__main__.py (tried: "
        + ", ".join(str(c) for c in cands) + ")")


def _has_phys(png: Path) -> bool:
    """True if the PNG declares a pHYs chunk.

    inkdrill REFUSES --dpi for a PNG that declares one and REQUIRES it for a
    PNG that does not, so the flag cannot be passed blind. Ghostscript writes
    pHYs; a Pillow-written crop does not.
    """
    try:
        raw = Path(png).read_bytes()
    except OSError:
        return False
    i = 8
    while i + 8 <= len(raw):
        ln = struct.unpack(">I", raw[i:i + 4])[0]
        typ = raw[i + 4:i + 8]
        if typ == b"pHYs":
            return True
        if typ == b"IDAT":
            return False
        i += 12 + ln
    return False


def ink_signature(png: Path, *, dpi: int = DPI, timeout: float = 180.0) -> dict:
    """{components, holes} for one PNG, measured by inkdrill.

    Raises InkUnavailable when inkdrill cannot run at all; returns a signature
    with components=0 for an image it reads but finds no ink in (a blank
    render is a real, reportable outcome, not an error).
    """
    root = inkdrill_root()
    cmd = ["python3", "-m", "inkdrill", str(png), "--glyphs", "--page-number", "1"]
    if not _has_phys(Path(png)):
        cmd += ["--dpi", str(dpi)]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run(cmd, cwd=str(root), env=env, capture_output=True,
                       text=True, timeout=timeout)
    if r.returncode != 0 or not (r.stdout or "").strip():
        raise InkUnavailable(
            f"inkdrill failed on {Path(png).name}: "
            f"{(r.stderr or r.stdout or '').strip()[-300:]}")
    try:
        doc = json.loads(r.stdout)
    except ValueError as e:
        raise InkUnavailable(f"inkdrill emitted non-JSON on {png}: {e}") from e
    comps = holes = glyphs = 0
    seen: set = set()
    for page in doc.get("pages", []) or []:
        for line in page.get("lines", []) or []:
            if line.get("type") != "glyph":
                continue
            ink = line.get("ink") or {}
            glyphs += 1
            seen.update(ink.keys())
            comps += int(ink.get("components") or 0)
            holes += int(ink.get("holes") or 0)
    # SCHEMA ASSERTION — the guarantee that spans two sessions.
    #
    # inkdrill belongs to another session and this reads its field names.
    # Nobody owns that agreement: it cannot assert it because it does not know
    # who consumes the output, and it was never asserted here because it was
    # never produced here. If `holes` is renamed, the loop above silently
    # contributes 0 for every glyph — HALF THE METRIC disappears and every
    # distance becomes a confident wrong number, with no error anywhere.
    #
    # Key PRESENCE is the right test, not value: a page of hole-free glyphs
    # carries "holes": 0, while a renamed field carries no such key at all.
    if glyphs:
        missing = [k for k in ("components", "holes") if k not in seen]
        if missing:
            raise InkUnavailable(
                f"inkdrill emitted {glyphs} glyph(s) but none carries "
                f"{', '.join(missing)} — its output schema has changed and the "
                f"crop ink distance would silently lose that term. Keys seen: "
                f"{sorted(seen)}")
    return {"components": comps, "holes": holes}


def measurable(sig: dict) -> bool:
    """True when a signature can serve as a REFERENCE to measure against.

    A scan crop with no ink components is not a measurement of an empty
    region — it is the shape every failure takes: a region scaled wrong, a
    crop off the page, a blank strip between paragraphs, an image inkdrill
    read but found nothing in. Treating it as a reference is not merely
    useless, it INVERTS the metric:

        scan blank, original renders 40 glyphs  ->  ink_before = 45
        scan blank, proposal renders 12 glyphs  ->  ink_after  = 13
        accepted, delta -32

    That is the gate rewarding a proposal for deleting content, and doing it
    most enthusiastically for the emptiest proposal. Blank against blank is
    worse still: distance 0, which the ink gate reads as "the render already
    matches the scan" and skips.

    So zero ink in the reference is refused, and the row is reported as
    unmeasurable rather than measured. A guard that says how much it looked at
    cannot quietly become a guard that looked at nothing.
    """
    return int((sig or {}).get("components", 0)) > 0


def ink_distance(a: dict, b: dict) -> int:
    """L1 over the scale-free terms. Symmetric; 0 means topologically equal."""
    return (abs(int(a.get("components", 0)) - int(b.get("components", 0)))
            + abs(int(a.get("holes", 0)) - int(b.get("holes", 0))))


# ---------------------------------------------------------------------------
# rendering and cropping
# ---------------------------------------------------------------------------

def _render_preamble() -> str:
    """The standalone preamble, sharing the report's own blackboard-digit fix.

    These two MUST agree. The ink comparison measures this render against the
    scan of a REPORT page; if the report typesets \\mathbb{1} as a blackboard
    one and this renders it as U+22AE, the measurement reports a difference
    that neither the OCR nor the page contains — a defect manufactured by the
    instrument.
    """
    from .report_tex import MATHBB_DIGITS
    return ("\\documentclass[preview,border=2pt]{standalone}\n"
            "\\usepackage{amsmath,amssymb,amsfonts,mathtools}\n"
            + MATHBB_DIGITS + "\\begin{document}\n")


RENDER_PREAMBLE = _render_preamble()


def render_latex(latex: str, out_png: Path, *, dpi: int = DPI,
                 timeout: float = 180.0) -> tuple[Optional[Path], str]:
    """Compile one maths value standalone and rasterize it. (path, error).

    xelatex, not pdflatex — the project's rule, and the engine the formula
    report already requires. Never raises: a failure is the error string, which
    the validate stage reports as a rejection reason.
    """
    if not (latex or "").strip():
        return None, "empty value"
    src = RENDER_PREAMBLE + "$\\displaystyle " + latex + "$\n\\end{document}\n"
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tex = Path(td) / "snippet.tex"
        tex.write_text(src, encoding="utf-8")
        try:
            proc = subprocess.run(
                ["xelatex", "-interaction=nonstopmode", "-halt-on-error",
                 "-no-shell-escape", "-output-directory", td, str(tex)],
                capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None, f"xelatex timed out after {timeout:.0f}s"
        except FileNotFoundError:
            return None, "xelatex not on PATH"
        pdf = Path(td) / "snippet.pdf"
        if not pdf.is_file():
            return None, _tex_error(proc.stdout or "")
        try:
            subprocess.run(
                ["gs", "-sDEVICE=png16m", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                 f"-r{dpi}", f"-sOutputFile={out_png}", str(pdf)],
                capture_output=True, text=True, check=True, timeout=timeout)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            return None, f"ghostscript failed: {e}"
    return (out_png, "") if out_png.is_file() else (None, "no raster produced")


_TEX_ERR = re.compile(r"^! (.+)$", re.M)


def _tex_error(log: str) -> str:
    m = _TEX_ERR.search(log or "")
    return ("xelatex: " + m.group(1).strip()) if m else "xelatex produced no PDF"


def scan_crop(pdf: Path, page: int, region: dict, out_png: Path,
              *, page_width: float, dpi: int = DPI) -> Optional[Path]:
    """The scan under `region`, cropped from a freshly rasterized page.

    MathPix regions are in ITS OWN page-image pixels (2125 px wide for a
    612 pt page = 250 dpi), and `rasterize` will not go below 400 dpi. Cropping
    with unscaled coordinates therefore lands on the wrong part of the page —
    it did here, silently, and the crop looked plausible. Every coordinate is
    scaled by (raster width / MathPix page width).
    """
    from . import pdf_reading
    from PIL import Image

    # Refuse BEFORE rasterizing. Without a page width the crop cannot be
    # placed, so rendering the page first is a 400-dpi Ghostscript run whose
    # only possible outcome is None.
    if not page_width:
        return None
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    imgs = pdf_reading.rasterize(pdf, out_png.parent / "_pages",
                                 pages=[page], dpi=dpi)
    if not imgs:
        return None
    im = Image.open(imgs[0])
    s = im.size[0] / float(page_width)
    x0 = int(region["top_left_x"] * s)
    y0 = int(region["top_left_y"] * s)
    x1 = int((region["top_left_x"] + region["width"]) * s)
    y1 = int((region["top_left_y"] + region["height"]) * s)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(im.size[0], x1), min(im.size[1], y1)
    if x1 <= x0 or y1 <= y0:
        return None
    # RGB: inkdrill reads ghostscript png16m only — a greyscale PNG is refused
    # at the IHDR, which reads as "no ink" if the error is swallowed.
    im.convert("RGB").crop((x0, y0, x1, y1)).save(out_png)
    return out_png


# ---------------------------------------------------------------------------
# stage 1 — select
# ---------------------------------------------------------------------------

MATH_TYPES = ("Equation", "Formula")


def candidates(doc, *, max_conf: float, limit: Optional[int] = None) -> list:
    """Low-confidence maths objects, worst first.

    A missing confidence is NOT a candidate: `None <= 0.5` is a TypeError in
    Python 3 and an unscored row is not a doubted row — it is a row nobody
    scored, which is out/160's problem and not this one.
    """
    out = []
    for o in doc.objects.values():
        if o.type not in MATH_TYPES:
            continue
        c = (o.props or {}).get("confidence")
        if not isinstance(c, (int, float)) or isinstance(c, bool):
            continue
        if c > max_conf:
            continue
        out.append(o)
    out.sort(key=lambda o: (o.props.get("confidence"), o.id))
    return out[:limit] if limit else out


@dataclass
class GateResult:
    kept: list
    skipped: list          # (obj, reason)
    baseline: dict         # obj id -> {"scan":sig,"render":sig,"distance":d}


def ink_gate(pdf: Path, doc, objs: list, work: Path, *,
             page_widths: dict, dpi: int = DPI) -> GateResult:
    """Measure each candidate as it stands; drop the ones nothing can improve.

    A row whose CURRENT render already matches the scan topologically has
    nothing for a proposal to fix, and asking a model to rewrite it can only
    make it worse. A row we cannot measure is also dropped, with its reason —
    an unmeasurable row must not be silently treated as a clean one.
    """
    kept, skipped, baseline = [], [], {}
    for o in objs:
        pr = o.props or {}
        region, page = pr.get("region"), pr.get("page")
        latex = pr.get("latex") or ""
        if not region or not page:
            skipped.append((o, "no region on the object"))
            continue
        pw = page_widths.get(int(page))
        if not pw:
            skipped.append((o, f"no MathPix page_width recorded for page {page}"))
            continue
        stem = work / o.id
        try:
            crop = scan_crop(pdf, int(page), region, stem.with_suffix(".scan.png"),
                             page_width=pw, dpi=dpi)
        except Exception as e:                      # noqa: BLE001 - reported
            skipped.append((o, f"scan crop failed: {e}"))
            continue
        if crop is None:
            skipped.append((o, "scan crop failed"))
            continue
        rend, err = render_latex(latex, stem.with_suffix(".before.png"), dpi=dpi)
        if rend is None:
            # The CURRENT value does not compile. That is a real finding and
            # the row is still a candidate — but there is no baseline to beat,
            # so it is measured as "absent ink" rather than skipped.
            try:
                sig_scan = ink_signature(crop, dpi=dpi)
            except InkUnavailable as e:
                skipped.append((o, f"ink unavailable: {e}"))
                continue
            if not measurable(sig_scan):
                skipped.append((o, "scan crop has no ink — nothing to measure against"))
                continue
            baseline[o.id] = {"scan": sig_scan,
                              "render": {"components": 0, "holes": 0},
                              "distance": ink_distance(sig_scan, {}),
                              "note": f"current value does not compile ({err})"}
            kept.append(o)
            continue
        try:
            sig_scan = ink_signature(crop, dpi=dpi)
            sig_rend = ink_signature(rend, dpi=dpi)
        except InkUnavailable as e:
            skipped.append((o, f"ink unavailable: {e}"))
            continue
        if not measurable(sig_scan):
            skipped.append((o, "scan crop has no ink — nothing to measure against"))
            continue
        d = ink_distance(sig_scan, sig_rend)
        baseline[o.id] = {"scan": sig_scan, "render": sig_rend, "distance": d}
        if d == 0:
            skipped.append((o, "ink gate: render already matches the scan (distance 0)"))
            continue
        kept.append(o)
    return GateResult(kept=kept, skipped=skipped, baseline=baseline)


# ---------------------------------------------------------------------------
# stage 2 — propose
# ---------------------------------------------------------------------------

PROPOSE_SYSTEM = (
    "You re-transcribe mathematics from OCR output. You return LaTeX and "
    "nothing else: no prose, no code fence, no delimiters, no explanation. "
    "Preserve the mathematical content exactly; fix only transcription damage."
)

#: VARIANT C (out/113). Four prompt variants were measured on 19 crops:
#:     A  image alone                     median delta +146
#:     B  image + notation hint           median delta +196
#:     C  image + THE EXISTING READING    median delta   -8
#:     D  C + hint and schema             median delta   -6
#: Showing the model MathPix's own reading is the only thing that helped;
#: from the image alone the model produced something FURTHER from the scan
#: than MathPix's reading was, on the very rows MathPix was least sure of.
#: So the crop and the prior are sent together, and a run without the crop is
#: not variant C -- it is a fourth thing nobody measured.
PROPOSE_PROMPT_C = """The image is a crop of one printed equation from a scanned page.

An OCR service read it as the LaTeX below, with confidence {conf}. That reading
may be right, or may have lost or merged rows, dropped cells from an aligned
table, or run two columns of the page together.

Correct it AGAINST THE IMAGE. Rules:
  - return the LaTeX body only, no $ or \\[ delimiters and no code fence
  - keep every environment balanced
  - if it is a table of numbers, every row must have the same number of cells
  - prefer the existing reading where the image does not contradict it

THE OCR'S READING:
{latex}
"""

PROPOSE_PROMPT = """This LaTeX came from OCR of a printed equation and its confidence is {conf}.
It may have lost or merged rows, dropped cells from an aligned table, or run two
columns of the page together.

Return a corrected LaTeX body for the SAME equation. Rules:
  - return the body only, with no $ or \\[ delimiters and no code fence
  - keep every environment balanced
  - if it is a table of numbers, every row must have the same number of cells
  - do not invent content you cannot see in the source below

SOURCE:
{latex}
"""


def _novita_chat(prompt: str, *, system: str, model: str, max_tokens: int,
                 timeout: float, crop=None) -> tuple[str, str, str]:
    """(content, finish_reason, error) from an OpenAI-compatible endpoint.

    Its own transport rather than `gemma_client.chat_completion` for one
    reason: that helper returns the content string alone, and this stage has to
    be able to tell "the model declined" from "the model ran out of budget
    before it said anything". minimax-m3 is a REASONING model — it spends
    completion tokens thinking before it emits a character, so a budget that is
    generous for a chat reply returns an empty string here, with
    finish_reason="length" as the only evidence of what happened.
    """
    import urllib.request
    from .env import get
    from . import net

    key = get("NOVITA_API_KEY", "")
    if not key:
        return "", "", "NOVITA_API_KEY is not set"
    base = (get("NOVITA_BASE_URL", "") or get("NOVITA_API_BASE", "")
            or "https://api.novita.ai/v3/openai")
    content: Any = prompt
    if crop:
        import base64
        b64 = base64.b64encode(Path(crop).read_bytes()).decode()
        content = [{"type": "text", "text": prompt},
                   {"type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"}}]
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": content}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
    try:
        with net.urlopen(req, host="api.novita.ai", timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:                          # noqa: BLE001 - reported
        return "", "", f"{type(e).__name__}: {e}"
    choices = d.get("choices") or []
    if not choices:
        return "", "", "no choices in response"
    ch = choices[0]
    msg = ch.get("message") or {}
    return (msg.get("content") or ""), (ch.get("finish_reason") or ""), ""


#: A reasoning model spends this budget thinking BEFORE it answers, and the
#: budget is the whole story on whether a reply arrives at all. Measured on one
#: 672-character root table from 0902.0431:
#:
#:     max_tokens   finish   completion tokens   content
#:      4,000       length         4,000         (none)
#:     16,000       length        16,000         (none)
#:     40,000       stop          36,810         680 chars, in 243 s
#:
#: It reasoned 93,495 characters about a 672-character equation. Disabling
#: thinking via chat_template_kwargs={"thinking": false} does NOT work on this
#: endpoint — it still reasoned 8,170 characters and still returned nothing.
#: So the budget has to be paid, and the stage runs its calls concurrently
#: rather than waiting four minutes a row.
PROPOSE_MAX_TOKENS = 40000

#: concurrent propose calls. The work is entirely network-bound.
PROPOSE_WORKERS = 4


def propose_one(latex: str, conf: float, *, model: str = NOVITA_MODEL,
                timeout: float = 900.0, crop=None,
                max_tokens: int = PROPOSE_MAX_TOKENS) -> tuple[str, str]:
    """(proposed_latex, error). Never raises.

    With `crop`, this is VARIANT C: the scan image AND the existing reading.
    Without it, the model is asked to repair LaTeX it cannot see the source
    of, which is not any of the four variants out/113 measured.
    """
    prompt = (PROPOSE_PROMPT_C if crop else PROPOSE_PROMPT).format(
        conf=f"{conf:.4f}", latex=latex)
    txt, finish, err = _novita_chat(
        prompt, system=PROPOSE_SYSTEM, model=model, max_tokens=max_tokens,
        timeout=timeout, crop=crop)
    if err:
        return "", err
    cleaned = _clean_reply(txt)
    if not cleaned:
        if finish == "length":
            return "", (f"reply empty: the model used all {max_tokens} tokens "
                        f"reasoning and emitted no content")
        return "", f"reply empty (finish_reason={finish or 'unknown'})"
    return cleaned, ""


_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")
_WRAP = (("\\[", "\\]"), ("$$", "$$"), ("\\(", "\\)"), ("$", "$"))


def _clean_reply(text: str) -> str:
    """Strip fences and any outer math delimiters the model added anyway."""
    t = _FENCE.sub("", (text or "").strip()).strip()
    changed = True
    while changed:
        changed = False
        for a, b in _WRAP:
            if len(t) >= len(a) + len(b) and t.startswith(a) and t.endswith(b):
                t = t[len(a):-len(b)].strip()
                changed = True
    return t


# ---------------------------------------------------------------------------
# stage 3 — validate
# ---------------------------------------------------------------------------

#: rejection reasons, as they appear in changes.json and in the counts
R_WIDTH = "width uniformity"
R_CONFUSE = "digit misread as a letter"
R_ENV = "environment balance"
R_CJK = "CJK"
R_COMPILE = "standalone compile"
R_EMPTY = "empty proposal"
R_NOCHANGE = "identical to the original"


def validate_one(proposed: str, *, original: str = "",
                 work: Optional[Path] = None, dpi: int = DPI) -> tuple[bool, str, str]:
    """(ok, reason, detail). The four checks, cheapest first.

    Compile is last on purpose: it is the only one that costs a subprocess, and
    a value that fails a structural check should never reach xelatex — a
    malformed table compiles perfectly well and looks like a table.
    """
    from . import env_balance as _eb
    from . import changereq as _cr
    from . import report_tex as _rt

    if not (proposed or "").strip():
        return False, R_EMPTY, "the model returned nothing"
    if original and proposed.strip() == original.strip():
        return False, R_NOCHANGE, "no change proposed"

    ok, detail = _cr.check_uniform_widths(proposed)
    if not ok:
        return False, R_WIDTH, detail

    # 187: the signal the old width check caught by accident, now named. A
    # lone letter inside an otherwise-numeric table is a misread digit.
    conf = _cr.confusable_cells(proposed)
    if conf:
        c = conf[0]
        return False, R_CONFUSE, (
            f"table {c['table']} row {c['row']} col {c['col']}: "
            f"'{c['cell']}' where '{c['likely']}' belongs"
            + (f" (+{len(conf) - 1} more)" if len(conf) > 1 else ""))

    d = _eb.env_defect(proposed)
    if d:
        return False, R_ENV, json.dumps(d, ensure_ascii=False)

    cjk = _rt.cjk_defect(proposed)
    if cjk:
        return False, R_CJK, cjk

    if work is not None:
        png, err = render_latex(proposed, Path(work) / "validate.png", dpi=dpi)
        if png is None:
            return False, R_COMPILE, err
    return True, "", ""


# ---------------------------------------------------------------------------
# stage 6 — record
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 230 — the second acceptance route: the author's own e-print
# ---------------------------------------------------------------------------
#
# The ink gate cannot reach every row. An INLINE formula has no region and no
# crop (out/125), so there is nothing to render a proposal against — and the
# one row out/229 identified is exactly that shape. What it does have is an
# arXiv e-print, which is gold.
#
# This route is a CHECK, not a flag. A requester says "the author wrote X"; the
# gate goes to the author's source, finds the site by its surrounding prose, and
# reads off what is actually there. A proposal is accepted only when the value
# the SOURCE yields equals the value proposed. Trusting `basis: eprint` would
# have made the whole loop bypassable by asserting a word.

VERIFIED_INK = "ink"
#: 232 names this route `source` — the author's own source is the evidence.
#: out/230 shipped it as "eprint"; both spellings are accepted on input so a
#: request written against either wording still routes, and both normalise to
#: `source` in what gets recorded. A stored record with two names for one
#: thing is a reconciliation problem for whoever reads it later.
VERIFIED_SOURCE = "source"
SOURCE_BASES = ("source", "eprint")
VERIFIED_EPRINT = VERIFIED_SOURCE        # out/230 spelling, kept resolvable

#: math spans in either dialect — MathPix writes \(...\), authors write $...$
_MATH_SPAN = re.compile(r"\$\$.*?\$\$|\$.*?\$|\\\(.*?\\\)|\\\[.*?\\\]", re.S)


def author_eprint(pdf: Path) -> "tuple[str, str]":
    """(text, filename) of the AUTHOR's e-print, or ("", "").

    ONLY `<stem>.tgz` / `.tar.gz`. Never `<stem>.tex.zip`, which sits in the
    same directory and is MATHPIX's own LaTeX output — out/229 nearly used it
    as gold and it agreed with the markdown perfectly, because it IS the
    markdown. A verification that reads the thing it is verifying confirms
    anything you like.
    """
    from . import latex_source
    pdf = Path(pdf)
    for suffix in (".tgz", ".tar.gz"):
        cand = pdf.with_suffix("") if pdf.suffix == ".pdf" else pdf
        cand = Path(str(cand) + suffix)
        if cand.is_file():
            return latex_source.read_source(str(cand))
    return "", ""


def _ctx_words(s: str, n: int, *, tail: bool) -> list:
    """The n alphabetic words at one end of `s`, with math spans removed.

    Words only: the author writes `$1$-form` where MathPix writes `1-form`, so
    digits and punctuation disagree at every site and prove nothing. What both
    render identically is the prose around the mathematics.
    """
    w = re.findall(r"[A-Za-z]+", _MATH_SPAN.sub(" ", s))
    return w[-n:] if tail else w[:n]


def containing_text(doc, obj_id: str) -> str:
    """The flow text that carries this object's value inline, or "".

    An inline Formula is also written into its paragraph's text, which is where
    its prose context lives. Nothing else in the model has it.
    """
    obj = doc.objects.get(obj_id)
    if obj is None:
        return ""
    latex = (obj.props or {}).get("latex") or ""
    if not latex:
        return ""
    needle = "\\(" + latex + "\\)"
    for other in doc.objects.values():
        text = (other.props or {}).get("text") or ""
        if needle in text:
            return text
    return ""


def eprint_value(doc, obj_id: str, src: str, *,
                 before: int = 8, after: int = 5) -> "tuple[str, dict]":
    """(the author's value at this object's site, evidence). ("", why) on failure.

    Derived, not asserted: locate the object's surrounding prose in the author
    source and read the math span that sits there.
    """
    obj = doc.objects.get(obj_id)
    if obj is None:
        return "", {"reason": "object not in the model"}
    latex = (obj.props or {}).get("latex") or ""
    para = containing_text(doc, obj_id)
    if not para:
        return "", {"reason": "no flow text carries this value inline — "
                              "cannot locate the site by its prose"}
    needle = "\\(" + latex + "\\)"
    i = para.index(needle)
    bw = _ctx_words(para[:i], before, tail=True)
    aw = _ctx_words(para[i + len(needle):], after, tail=False)
    if len(bw) < 3:
        return "", {"reason": "too little prose before the value to locate it "
                              "(%d words)" % len(bw)}

    # blank the math out of the source, keeping offsets, so word positions in
    # the prose stay true and no word inside a formula can match
    masked = _MATH_SPAN.sub(lambda m: " " * len(m.group(0)), src)
    toks = [(m.group(0), m.start(), m.end())
            for m in re.finditer(r"[A-Za-z]+", masked)]
    seq = [t[0] for t in toks]
    hits = [k for k in range(len(seq) - len(bw) + 1) if seq[k:k + len(bw)] == bw]
    if not hits:
        return "", {"reason": "the prose before this value does not occur in "
                              "the author source", "context": " ".join(bw)}
    if len(hits) > 1:
        # An ambiguous site is a refusal, not a coin toss. Widening the window
        # would be a fix; guessing would be the defect this loop exists to stop.
        return "", {"reason": "the prose before this value occurs %d times in "
                              "the author source — site is ambiguous"
                              % len(hits), "context": " ".join(bw)}
    end = toks[hits[0] + len(bw) - 1][2]
    m = _MATH_SPAN.search(src, end)
    if not m:
        return "", {"reason": "no mathematics follows that prose in the author "
                              "source"}
    post = _ctx_words(src[m.end():m.end() + 400], len(aw), tail=False)
    if aw and post[:len(aw)] != aw:
        return "", {"reason": "the prose AFTER the value disagrees with the "
                              "author source", "expected": " ".join(aw),
                    "found": " ".join(post[:len(aw)])}
    raw = m.group(0)
    val = re.sub(r"^\$\$?|\$\$?$|^\\\(|\\\)$|^\\\[|\\\]$", "", raw).strip()
    return val, {"source_span": raw, "context_before": " ".join(bw),
                 "context_after": " ".join(aw), "occurrences": len(hits)}


def same_latex(a: str, b: str) -> bool:
    """LaTeX equality up to whitespace — `\\mathcal {J}` is `\\mathcal{J}`."""
    norm = lambda s: re.sub(r"\s+", "", s or "")
    return norm(a) == norm(b)


REFINED_STREAM = "refined"
REFINED_FIELD = "latex_refined"


def record_one(doc, obj_id: str, prop: dict) -> bool:
    """Attach an accepted proposal as evidence. The original value is untouched.

    The refined text lands in a TWIN prop (`latex_refined`), never over
    `latex`, and a realization with provenance="change" carries the same value
    so `modeldiff` can find the evidence path behind it. An edit nobody signed
    is exactly what modeldiff counts separately, and this one is signed.
    """
    from docmodel.core import Realization

    obj = doc.objects.get(obj_id)
    if obj is None:
        return False
    if not prop.get("verified_by"):
        raise ValueError(
            "refusing to record %s: the proposal does not say what verified "
            "it. A record whose provenance is guessed is worth less than no "
            "record." % obj_id)
    # 232 — REPLACE, do not append. Re-running record (a corrected basis, a
    # re-verified proposal) used to leave both realizations on the object, and
    # a reader finding two `change` records for one value has no way to tell
    # which one the prop came from.
    obj.realizations = [r for r in obj.realizations
                        if not (getattr(r, "stream", None) == REFINED_STREAM
                                and getattr(r, "role", None) == "latex_candidate")]
    stream = doc.ensure_stream(REFINED_STREAM)
    anchor = stream.append(**{
        "text": prop["proposed"], "object": obj_id,
        "author": prop.get("author", DEFAULT_AUTHOR),
    })
    obj.props[REFINED_FIELD] = prop["proposed"]
    obj.add_realization(Realization(
        stream=REFINED_STREAM, start=anchor, end=anchor,
        role="latex_candidate", provenance="change",
        props={
            REFINED_FIELD: prop["proposed"],
            # 230: the verification that ACTUALLY happened. This was the
            # literal string "ink" regardless of how the proposal had been
            # accepted, so a row verified any other way would have been
            # recorded as ink-verified — a claim about an instrument that
            # never ran. record_one refuses a proposal that does not say.
            "verified_by": prop["verified_by"],
            "ink_before": prop.get("ink_before"),
            "ink_after": prop.get("ink_after"),
            "ink_delta": prop.get("ink_delta"),
            "evidence": prop.get("evidence"),
            "basis": prop.get("basis", "inferred"),
            "author": prop.get("author", DEFAULT_AUTHOR),
            "at": prop.get("at") or _now(),
        }))
    return True


def identifiers(doc, bibkey: str) -> dict:
    """{object id: "<bibkey>_EQ0515"} — the projector's OWN numbering.

    Delegated to `tiddlywiki.math_titles`, which its docstring calls the
    authoritative numbering, rather than re-derived here. A second
    implementation drifts: mine did, immediately and by one, because I
    enumerated from 0 where the projector counts from 1 — which renamed every
    row in the corpus by one place and pointed EQ0515 at its neighbour.

    Object ids are what changes.json keys on, because they survive a projection
    change; identifiers are what a reader searches for, because they are what
    the report and the auditor's notes use. Both are recorded.
    """
    try:
        from docops.projectors.tiddlywiki import math_titles
    except Exception:                               # noqa: BLE001
        return {}
    try:
        return math_titles(doc, bibkey)
    except Exception:                               # noqa: BLE001
        return {}


def parse_stages(spec: Optional[str]) -> list:
    """Stage list from a --stages string; every stage when empty.

    An unknown name is an error rather than a silent no-op: `--stages propse`
    running zero stages and reporting success is the failure mode this whole
    command exists to avoid.
    """
    if not (spec or "").strip():
        return list(STAGES)
    want = [s.strip() for s in str(spec).split(",") if s.strip()]
    bad = [s for s in want if s not in STAGES]
    if bad:
        raise ValueError(
            f"unknown stage(s): {', '.join(bad)} — known: {', '.join(STAGES)}")
    return [s for s in STAGES if s in want]        # canonical order


def mathpix_page_widths(blob_dir: Path) -> dict:
    """{page number: MathPix page-image width in px}, from its lines.json.

    PER PAGE, not one width for the document. Reading page 1's width and
    applying it everywhere is the same defect as not scaling at all, just
    rarer: 11 of 305 documents in this corpus carry more than one page_width
    (e.g. 2066 and 2125 in the same file), and on those the crop for a page of
    the other size is scaled wrong and still looks like a plausible piece of a
    maths page.

    A page with no recorded width is ABSENT from the mapping rather than
    defaulted, so the caller refuses to crop it instead of cropping it wrongly.
    """
    out: dict = {}
    for p in sorted(Path(blob_dir).glob("*.lines.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for page in d.get("pages", []) or []:
            w, n = page.get("page_width"), page.get("page")
            if w and n is not None:
                out.setdefault(int(n), float(w))
    return out
