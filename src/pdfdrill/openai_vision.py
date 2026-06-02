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
import urllib.error
import urllib.request
from typing import Any, Optional

from . import net
from .env import get

API_ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-2024-08-06"

# The classification prompt (ported verbatim from mathpix_images/prompt.txt).
DEFAULT_PROMPT = """You are given a base64-encoded image crop that an OCR service could NOT resolve and left as a raw image. Identify what it contains and return a JSON object with this structure:

{
  "selector": "text|handwriting|table|math|commutative_diagram|gnuplot|tikzpicture|tensor|diagram|chart|photo|logo|empty",
  "text": "verbatim transcription of printed OR handwritten text",
  "table": "LaTeX tabular for a data table",
  "math": "LaTeX math expression",
  "commutative_diagram": "tikz-cd code",
  "gnuplot": "GnuPlot script reproducing a plot",
  "csv_data": "extracted plot data as CSV",
  "tikzpicture": "tikzpicture LaTeX code",
  "tensor": "tensor diagram LaTeX code",
  "description": "concise factual description for diagram/chart/photo/logo"
}

CLASSIFICATION RULES — fill ONLY the field named by selector.
- "text" - printed prose/labels/numbers/addresses. Transcribe verbatim into "text".
- "handwriting" - cursive or hand-printed writing. Transcribe your best reading into "text".
- "table" - rows/columns of text or numbers. Fill "table" with a \\begin{tabular}...\\end{tabular} reproducing every visible cell, row by row.
- "math" - a math expression. Fill "math" with LaTeX in $$ delimiters.
- "commutative_diagram" - fill "commutative_diagram" with tikz-cd code.
- "gnuplot" - a data plot: fill "csv_data" with every readable data point (CSV, header row, x in column 1) AND "gnuplot" with a complete self-contained script reading 'data.csv'.
- "tikzpicture" - general TikZ-style line drawing. Fill "tikzpicture".
- "tensor" - tensor network diagram. Fill "tensor".
- "diagram" / "chart" / "photo" / "logo" - a picture with no transcribable text. Fill "description".
- "empty" - ONLY for a genuinely blank/featureless area.

IMPORTANT: faint, low-contrast, light-grey, or cursive content is NOT empty. If you can perceive ANY strokes, glyphs, lines, or marks, classify and extract them (use "handwriting" or "text" for writing, "diagram" otherwise). Reserve "empty" for a truly blank crop.

Return ONLY the JSON object. No markdown fences, no explanation."""

# Targeted prompt for images whose caption/title names a graph/subgraph — these
# are vertex+edge drawings that reconstruct cleanly as TikZ (see cmd_vision,
# which selects this prompt when the owning object's caption matches).
GRAPH_TIKZ_PROMPT = """This image is a GRAPH or SUBGRAPH diagram (vertices and edges) that OCR could not resolve. Reconstruct it as a faithful, standalone TikZ picture:
- place every vertex (node) in roughly its observed position;
- draw every edge between the correct vertices;
- preserve colour/emphasis (e.g. a red or highlighted complete-bipartite subgraph) using the matching TikZ colour;
- transcribe any vertex/edge labels you can read.
Return a JSON object: {"selector":"tikzpicture","tikzpicture":"\\\\begin{tikzpicture} ... \\\\end{tikzpicture}"} with ONLY the tikzpicture field filled. No markdown fences, no explanation."""

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
    "commutative_diagram": "commutative_diagram",
    "tikzpicture": "tikzpicture",
    "tensor": "tensor",
    "gnuplot": "gnuplot",
    "diagram": "description",
    "chart": "description",
    "photo": "description",
    "logo": "description",
}


def result_to_latex(result: dict[str, Any]) -> tuple[str, str]:
    """Return (selector, latex_or_code) from a vision result.

    For math the surrounding ``$$`` are stripped (the model stores bare LaTeX).
    For gnuplot the script is returned (csv_data stays on the raw result).
    """
    selector = (result.get("selector") or "").strip()
    field = _FIELD_BY_SELECTOR.get(selector)
    code = (result.get(field) or "").strip() if field else ""
    if selector == "math":
        code = code.strip("$").strip()
    return selector, code
