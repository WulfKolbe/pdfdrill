"""
OpenAI GPT-4o vision client — extract LaTeX/TikZ/gnuplot from an image crop
that OCR (MathPix) left unresolved.

Python port of the proven `~/MX/mathpix_images` flow (llmUtils.js / imagetester.js
+ prompt.txt): send a base64 image to `gpt-4o` with a structured-JSON schema, get
back a `selector` (empty | math | commutative_diagram | gnuplot | tikzpicture |
tensor) plus the corresponding code. Stdlib only (urllib) — no `openai` package.

Credentials: `OPENAI_API_KEY` from the environment / git-ignored `.env`
(see `pdfdrill.env`). The key NEVER enters version control. This is the third
competing provenance alongside MathPix and MathPix-Snip; results attach to the
docmodel as a `provenance="openai"` `latex_candidate` realization.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from typing import Any, Optional

from . import net
from .env import get
from . import prompts

API_ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-2024-08-06"

# THE VISION SELECTOR. 466 moved it to docs/prompts/ and checked the comment
# that used to stand here: "ported verbatim from mathpix_images/prompt.txt".
# It is not verbatim — 123 diff lines, and 6 selectors became 16. Both
# ancestors are in docs/prompts/ under their own dates.
DEFAULT_PROMPT = prompts.load("vision-selector")

# Targeted prompt for images whose caption/title names a graph/subgraph — these
# are vertex+edge drawings that reconstruct cleanly as TikZ (see cmd_vision,
# which selects this prompt when the owning object's caption matches).
GRAPH_TIKZ_PROMPT = prompts.load("vision-graph-tikz")

# Targeted prompt for images whose caption/context names a molecule/compound/
# reaction — drawn structures reconstruct cleanly as chemfig (see cmd_vision,
# which selects this prompt when the owning object's caption matches).
CHEM_STRUCTURE_PROMPT = prompts.load("vision-chem-structure")

# --------------------------------------------------------------------------- #
# Full-page MathPix-replacement prompt.
#
# tesseract (the keyless OCR fallback) produces a plain-text layer with NO LaTeX,
# so equations never become `{{…||FO}}` transclusions and the whole transclusion
# model collapses. When there is no MathPix key, the only way to recover the math
# is a multimodal model reading the RENDERED page and re-emitting MathPix-quality
# Markdown — inline `\( … \)`, display `$$ … $$` on their own lines — which
# `markdown_source` ingests into real Equation objects. This is the prompt for
# that "rebuild the MathPix .md, or honestly give up" task (see `pdfdrill remath`).
# --------------------------------------------------------------------------- #
GIVE_UP_SENTINEL = "PDFDRILL_CANNOT_RECONSTRUCT"

MATHPIX_MD_PROMPT = prompts.load("vision-mathpix-md")

# Equation-only OCR: extract just the display equations from ONE page image as
# structured records (page/number/latex/kind) — the keyless equivalent of
# MathPix's equation isolation. Used by `pdfdrill visionocr` to fold real
# Equation nodes back into a tesseract lines.json without re-transcribing prose.
EQ_OCR_PROMPT = prompts.load("vision-equation-ocr")

# json_schema enforcing the response shape.
_SCHEMA = {
    "name": "img_repl",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "selector": {"type": "string"},
            "text": {"type": "string"},
            "table": {"type": "string"},
            "math": {"type": "string"},
            "annotated_math": {"type": "string"},
            "annotation_overlay": {"type": "string"},
            "mhchem": {"type": "string"},
            "chemfig": {"type": "string"},
            "commutative_diagram": {"type": "string"},
            "gnuplot": {"type": "string"},
            "csv_data": {"type": "string"},
            "tikzpicture": {"type": "string"},
            "tensor": {"type": "string"},
            "description": {"type": "string"},
        },
        "additionalProperties": False,
    },
}


def available() -> bool:
    return bool(get("OPENAI_API_KEY", ""))


def _api_key() -> str:
    key = get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError(
            "OpenAI credentials missing. Set OPENAI_API_KEY in the environment "
            "or copy .env.example to .env and fill it in "
            "(https://platform.openai.com/api-keys)."
        )
    return key


def _image_bytes(image: str, timeout: float) -> bytes:
    """Load image bytes from a local path or an http(s)/data URL."""
    if image.startswith("data:"):
        return base64.b64decode(image.split(",", 1)[1])
    if image.startswith(("http://", "https://")):
        with net.urlopen(image, timeout=timeout) as resp:
            return resp.read()
    with open(image, "rb") as f:
        return f.read()


def analyze_image(
    image: str,
    *,
    prompt: str = DEFAULT_PROMPT,
    model: str = DEFAULT_MODEL,
    timeout: float = 90.0,
) -> dict[str, Any]:
    """Send one image (path / URL / data URI) to GPT-4o vision; return the
    parsed result dict (selector + math/tikzpicture/gnuplot/csv_data/...)."""
    b64 = base64.b64encode(_image_bytes(image, timeout)).decode("ascii")
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
        "response_format": {"type": "json_schema", "json_schema": _SCHEMA},
        "max_tokens": 2000,
        "temperature": 0,
    }
    req = urllib.request.Request(
        API_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {_api_key()}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with net.urlopen(req, timeout=timeout, host="api.openai.com") as resp:
            envelope = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"OpenAI HTTP {e.code}: {body}") from e
    content = envelope["choices"][0]["message"]["content"]
    return json.loads(content)


# Map a vision result to a (kind, latex) pair for the model. `kind` mirrors the
# selector so downstream code can decide rendering (KaTeX vs TikZ→SVG vs table).
_FIELD_BY_SELECTOR = {
    "text": "text",
    "handwriting": "text",
    "table": "table",
    "math": "math",
    "annotated_math": "annotated_math",
    "chemical_equation": "mhchem",
    "chemical_structure": "chemfig",
    "commutative_diagram": "commutative_diagram",
    "tikzpicture": "tikzpicture",
    "tensor": "tensor",
    "gnuplot": "gnuplot",
    "diagram": "description",
    "chart": "description",
    "photo": "description",
    "logo": "description",
}


_MD_FENCE_RE = re.compile(r"^\s*(?:```|~~~)[^\n]*\n?|\n?(?:```|~~~)\s*$")


def _strip_fences(code: str) -> str:
    """Drop markdown code fences the model sometimes adds despite instructions."""
    return _MD_FENCE_RE.sub("", code).strip()


def _normalize_mhchem(code: str) -> str:
    """Normalize a chemical_equation result to a bare ``\\ce{...}`` expression.

    The model may return ``$\\ce{...}$``, ``\\ce{...}``, or the raw formula
    (``2H2 + O2 -> 2H2O``). Strip math delimiters; wrap in ``\\ce{}`` when the
    command is missing — mhchem's \\ce works in text and math mode alike, so
    the bare command compiles directly in the standalone SVG snippet AND
    renders in KaTeX (mhchem extension) when wrapped by the report pages.
    """
    code = _strip_fences(code).strip("$").strip()
    if not code:
        return ""
    # The model often writes the heat symbol over a reaction arrow as
    # \textDelta (textgreek package, NOT in the SVG preamble); math-mode
    # \Delta compiles everywhere mhchem does.
    code = re.sub(r"\\text\{\\textDelta\}|\\textDelta\b", r"$\\Delta$", code)
    if "\\ce{" in code or "\\ce {" in code:
        return code
    return "\\ce{" + code + "}"


def _normalize_chemfig(code: str) -> str:
    """Normalize a chemical_structure result to compilable chemfig body code.

    Accepts ``\\chemfig{...}``, a ``\\schemestart``/``chemfig`` reaction-scheme
    block, or a bare bond spec (``H_3C-CH_2-OH``) which gets wrapped in
    ``\\chemfig{}``. Output is body-only LaTeX, ready for the standalone
    latex->dvisvgm route (the preamble loads the chemfig package).
    """
    code = _strip_fences(code).strip("$").strip()
    if not code:
        return ""
    if ("\\chemfig" in code or "\\schemestart" in code
            or "\\begin{chemfig}" in code):
        return code
    return "\\chemfig{" + code + "}"


def compose_annotated_math(maths: str, overlay: str) -> str:
    """One snippet carrying BOTH the mathematics and the marks outside it.

    Every other selector fills one field and returns one string. This one
    cannot: the whole point of the class is that the annotation is NOT part of
    the expression. Returning the array alone loses the arrows; returning the
    overlay alone loses the mathematics; and merging them into one array is the
    failure being prevented — out/189 found a row-reduction where MathPix had
    read the annotation INTO a cell, giving `0 & 0 & \\uparrow-1 & 1 & 0`.

    So the two are COMPOSED, not chosen between: the mathematics becomes a
    TikZ node called `M`, and the overlay draws around it. The result begins
    with \\begin{tikzpicture}, which is what svg.is_latex_graphic already
    recognises, so it renders by the existing TikZ route with no new plumbing.

    With no overlay the maths is returned unwrapped — a node with nothing
    drawn around it would be a tikzpicture pretending to be an annotation.
    """
    maths = (maths or "").strip().strip("$").strip()
    overlay = (overlay or "").strip()
    if not maths:
        return overlay
    if not overlay:
        return maths
    # a full tikzpicture in the overlay field: take its body, keep one picture
    m = re.search(r"\\begin\{tikzpicture\}(?:\[[^]]*\])?(.*)\\end\{tikzpicture\}",
                  overlay, re.S)
    if m:
        overlay = m.group(1).strip()
    return ("\\begin{tikzpicture}[baseline=(M.base)]\n"
            "\\node[inner sep=1pt] (M) {$" + maths + "$};\n"
            + overlay + "\n\\end{tikzpicture}")


def result_to_latex(result: dict[str, Any]) -> tuple[str, str]:
    """Return (selector, latex_or_code) from a vision result.

    For math the surrounding ``$$`` are stripped (the model stores bare LaTeX).
    For gnuplot the script is returned (csv_data stays on the raw result).
    chemical_equation is normalized to a bare ``\\ce{...}`` (mhchem) and
    chemical_structure to ``\\chemfig{...}``/``\\schemestart...`` body code, so
    both are directly compilable by the TikZ/table SVG route (svg.py).
    """
    selector = (result.get("selector") or "").strip()
    field = _FIELD_BY_SELECTOR.get(selector)
    code = (result.get(field) or "").strip() if field else ""
    if selector == "annotated_math":
        return selector, compose_annotated_math(
            code, (result.get("annotation_overlay") or "").strip())
    if selector == "math":
        code = code.strip("$").strip()
    elif selector == "chemical_equation":
        code = _normalize_mhchem(code)
    elif selector == "chemical_structure":
        code = _normalize_chemfig(code)
    return selector, code
