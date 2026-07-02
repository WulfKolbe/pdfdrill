"""Gemma-4 vision client (via Novita.ai's OpenAI-compatible API) — a keyless-of-
MathPix route to turn a TABLE (or any) image crop into LaTeX.

This is the competing 'gemma' provenance for `pdfdrill snip --gemma`: cheap
image→LaTeX for tables when MathPix is not wanted/available. It returns the SAME
compact record shape as `mathpix_snip.snip_result` ({provenance, latex, text,
confidence, lines}) so the snip command is provider-agnostic.

Prompt + call shape are ported from the user's ~/Gemma4 reference tool
(`gemmatester.py` + `latex-table-prompt.md`): a vision chat-completion with the
page/crop image as a `data:` URL, LaTeX returned inside a ```latex code fence.

Credentials: `NOVITA_API_KEY` from the environment / git-ignored `.env`
(see `pdfdrill.env`). The key NEVER enters version control. Model + base URL are
overridable (`GEMMA_MODEL`, `NOVITA_BASE_URL` / `NOVITA_API_BASE`). Stdlib
urllib only — no `openai` package dependency (mirrors `openai_vision`).
"""
from __future__ import annotations

import base64
import json
import mimetypes
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from . import net
from .env import get

# Novita.ai OpenAI-compatible endpoint. The chat route is <base>/chat/completions.
DEFAULT_BASE_URL = "https://api.novita.ai/v3/openai"
DEFAULT_MODEL = "google/gemma-4-26b-a4b-it"
SYSTEM_PROMPT = ("You analyze document images (a page or a cropped region) and "
                 "follow the user prompt exactly.")

# The tested table prompt, vendored verbatim from ~/Gemma4/latex-table-prompt.md.
TABLE_PROMPT = r"""You are an expert in converting images of tables into high-quality LaTeX code. Given an image containing one or more tables, produce a complete LaTeX representation. Use the full power of LaTeX table features and faithfully reproduce the structure and formatting.

**Crucial structural accuracy - do not guess rows or merge cells incorrectly:**
1. Count the exact number of rows and columns. Every visible horizontal line or row separator in the image separates a new LaTeX row. Each such row **must** become one `\\` line - even if some cells are empty or if the text appears to be a continuation of the previous row's label. Do **not** combine two separate row labels into one cell.
2. Empty cells are simply nothing between two `&` characters. Example: `first column & & third column \\`.
3. Only use `\multirow` when a cell clearly spans multiple rows visually (merged with vertical border). Never use it to merge the text of two different row headers.
4. Use `\multicolumn` only when a cell visibly spans multiple columns.

**Rule style matching - very important:**
- Inspect the table's horizontal and vertical lines in the image.
- If the table uses simple horizontal lines (possibly thin/thick, full-width or partial) **and** often has vertical lines `|`, use `\hline` for full-width horizontal rules and `\cline{a-b}` for partial ones. Do **not** use `\toprule`, `\midrule`, `\bottomrule`, `\cmidrule` in this case.
- Only use `\toprule`, `\midrule`, `\bottomrule`, `\cmidrule` (from `booktabs`) if the table has a distinct professional look: heavy top/bottom rules, light middle rules, usually **no** vertical rules.

**Other formatting:**
- Use `tabular` (or `tabularx`) with appropriate specifiers (`l`, `c`, `r`, `p{<width>}`). Include `|` for vertical rules only if they appear in the image.
- Mathematical expressions: transcribe into correct LaTeX math notation. Use `$...$` for inline, `\[...\]` for display math. Convert symbols, fractions, superscripts, etc. accurately.
- Respect cell alignment and bold/italic formatting.
- Include `\caption{...}` and `\label{...}` only if the image shows a caption; otherwise omit them.
- Transcribe text exactly, correcting obvious OCR noise (e.g., "fi Iter" -> "filter").

**Package comment:**
At the very beginning of the generated code, add a comment line listing the necessary packages. **Always include at least**:
`% \usepackage{booktabs, multirow, amsmath, amsfonts}`
(Adjust if additional packages like `siunitx` are needed.)

Output only the LaTeX code inside a code block:

```latex
% \usepackage{booktabs, multirow, amsmath, amsfonts}
...
```"""


def available() -> bool:
    return bool(get("NOVITA_API_KEY", ""))


def _api_key() -> str:
    key = get("NOVITA_API_KEY", "")
    if not key:
        raise RuntimeError(
            "Novita credentials missing. Set NOVITA_API_KEY in the environment "
            "or copy .env.example to .env and fill it in "
            "(https://novita.ai/settings/key-management)."
        )
    return key


def _base_url() -> str:
    return (get("NOVITA_BASE_URL", "") or get("NOVITA_API_BASE", "")
            or DEFAULT_BASE_URL).rstrip("/")


def _model() -> str:
    return get("GEMMA_MODEL", "") or DEFAULT_MODEL


def _endpoint() -> str:
    return f"{_base_url()}/chat/completions"


def to_data_url(image: str, timeout: float = 60.0) -> str:
    """A local path / http(s) URL / data: URI → a base64 `data:` URL (what the
    vision API wants). URLs are fetched through `net.urlopen`."""
    if image.startswith("data:"):
        return image
    if image.startswith(("http://", "https://")):
        with net.urlopen(image, timeout=timeout) as resp:
            raw = resp.read()
        ctype = "image/png"
    else:
        with open(image, "rb") as f:
            raw = f.read()
        ctype = mimetypes.guess_type(image)[0] or "image/png"
    return f"data:{ctype};base64," + base64.b64encode(raw).decode("ascii")


_FENCE_RE = re.compile(r"^\s*```(?:latex|tex)?\s*\n?|\n?\s*```\s*$", re.IGNORECASE)


def strip_latex_fence(text: str) -> str:
    """Remove a leading ```latex / trailing ``` markdown fence if present."""
    t = (text or "").strip()
    if "```" in t:
        # keep the code block body: take the first fenced block if there is one
        m = re.search(r"```(?:latex|tex)?\s*\n(.*?)```", t, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
        t = _FENCE_RE.sub("", t)
    return t.strip()


def analyze_image(
    image: str,
    *,
    prompt: str = TABLE_PROMPT,
    model: Optional[str] = None,
    max_tokens: int = 4000,
    temperature: float = 0.2,
    timeout: float = 120.0,
) -> str:
    """Send one image (path / URL / data URI) to a Gemma vision model on Novita;
    return the raw assistant text (LaTeX, usually inside a ```latex fence)."""
    payload: dict[str, Any] = {
        "model": model or _model(),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": to_data_url(image, timeout)}},
            ]},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        _endpoint(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {_api_key()}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    host = urllib.parse.urlparse(_endpoint()).hostname or "api.novita.ai"
    try:
        with net.urlopen(req, timeout=timeout, host=host) as resp:
            envelope = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Novita/Gemma HTTP {e.code}: {body}") from e
    return envelope["choices"][0]["message"]["content"] or ""


def snip_result(image: str, *, prompt: str = TABLE_PROMPT, **kwargs) -> dict:
    """High-level: image → LaTeX via Gemma, returned in the SAME shape as
    `mathpix_snip.snip_result` so `pdfdrill snip` is provider-agnostic. Gemma
    supplies no confidence, so `confidence` is None and `lines` is empty."""
    raw = analyze_image(image, prompt=prompt, **kwargs)
    latex = strip_latex_fence(raw)
    return {
        "provenance": "gemma",
        "latex": latex,
        "text": raw,
        "confidence": None,
        "lines": [],
    }
