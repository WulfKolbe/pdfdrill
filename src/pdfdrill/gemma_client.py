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
from . import prompts

# Novita.ai OpenAI-compatible endpoint. The chat route is <base>/chat/completions.
DEFAULT_BASE_URL = "https://api.novita.ai/v3/openai"
DEFAULT_MODEL = "google/gemma-4-26b-a4b-it"
SYSTEM_PROMPT = prompts.load("gemma-system")

# The tested table prompt, vendored verbatim from ~/Gemma4/latex-table-prompt.md.
TABLE_PROMPT = prompts.load("gemma-table")


# --------------------------------------------------------------------------- #
#  Makora — a second host for the same model, with its own key and its own
#  metered balance.
# --------------------------------------------------------------------------- #
#
# WHY A SEPARATE PROVIDER AND NOT `NOVITA_API_BASE=https://…makora…`.
# `_base_url()` already honours an override, so pointing the Gemma client at
# Makora needs no code — and doing it that way is wrong twice over. The
# Makora key would live under the name `NOVITA_API_KEY`, so `doctor` would
# report a Novita credential that is not one and a leaked key would be
# misattributed; and the two hosts do not behave the same, so there would be
# no place to put the difference.
#
# The difference that matters: Makora needs `{"reasoning_effort": "none"}` or
# it reasons its way into a loop on an image prompt, and it hung on requests
# carrying four or more images (measured 2026-10-18 by the project this
# reader came from). Both are properties of the HOST, which is what a
# provider entry is for.
MAKORA_BASE_URL = "https://inference.makora.com/v1"
MAKORA_MODEL = "google/gemma-4-26B-A4B"
#: Makora's balance is a fixed prepayment, not a rate limit: when it empties
#: the endpoint stops answering, mid-document. `gemma_reader.read_preflight`
#: estimates against `PDFDRILL_OCR_BUDGET_EUR` before the first call.
MAKORA_EXTRA_BODY = {"reasoning_effort": "none"}
#: At or above this many images in one request the host was measured to hang.
MAKORA_MAX_IMAGES = 3


def available() -> bool:
    return bool(get("NOVITA_API_KEY", ""))


def makora_available() -> bool:
    return bool(get("MAKORA_API_KEY", ""))


def makora_base_url() -> str:
    return get("MAKORA_BASE_URL", "") or MAKORA_BASE_URL


def makora_model() -> str:
    return get("MAKORA_MODEL", "") or MAKORA_MODEL


def makora_api_key() -> str:
    key = get("MAKORA_API_KEY", "")
    if not key:
        raise RuntimeError(
            "Makora credentials missing. Set MAKORA_API_KEY in the "
            "environment or in the git-ignored .env (see .env.example). The "
            "account is a fixed prepayment — set PDFDRILL_OCR_BUDGET_EUR to "
            "the remaining balance so a read is refused rather than cut off "
            "half-way.")
    return key


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


def chat_completion_full(
    prompt: str,
    images: Optional[list] = None,
    *,
    model: str,
    base_url: str,
    api_key: str,
    system: str = SYSTEM_PROMPT,
    max_tokens: int = 4000,
    temperature: float = 0.2,
    timeout: float = 120.0,
    extra_body: Optional[dict] = None,
) -> dict:
    """One OpenAI-compatible chat call, with everything the ENVELOPE carried.

    `chat_completion` returns the text, which is all four of its existing
    callers want. This returns the text PLUS `usage` and `finish_reason`,
    because a metered account needs them:

    * `usage` is the only honest basis for what a call cost. `callog` records
      it (`log_call(usage=…)`), so "how much has this document spent" is a
      question the call log can answer instead of the provider's dashboard.
    * `finish_reason` distinguishes a page the model finished from one it was
      cut off on at `max_tokens`. A truncated page is a page whose last lines
      are missing, and it costs the same as a complete one.

    `extra_body` is merged into the request. Some OpenAI-compatible hosts need
    a field that is not in the protocol — the measured case is a host that
    loops on an image prompt unless `{"reasoning_effort": "none"}` is sent —
    and a transport with no way to pass one cannot talk to them at all.

    `images` is a LIST: several page strips are one call, which is how a page
    is read at better than the host's fixed per-image token budget.
    """
    content: Any = prompt
    if images:
        content = [{"type": "text", "text": prompt}]
        for img in images:
            content.append({"type": "image_url",
                            "image_url": {"url": to_data_url(img, timeout)}})
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": content}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if extra_body:
        payload.update(extra_body)
    endpoint = base_url.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    host = urllib.parse.urlparse(endpoint).hostname or "api.novita.ai"
    try:
        with net.urlopen(req, timeout=timeout, host=host) as resp:
            envelope = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"{host} HTTP {e.code}: {body}") from e
    choice = (envelope.get("choices") or [{}])[0]
    return {
        "text": (choice.get("message") or {}).get("content") or "",
        "finish_reason": choice.get("finish_reason") or "",
        "usage": envelope.get("usage") or {},
        "model": envelope.get("model") or model,
        "host": host,
    }


def chat_completion(
    prompt: str,
    image: Optional[str] = None,
    *,
    model: str,
    base_url: str,
    api_key: str,
    system: str = SYSTEM_PROMPT,
    max_tokens: int = 4000,
    temperature: float = 0.2,
    timeout: float = 120.0,
    extra_body: Optional[dict] = None,
) -> str:
    """ONE generic OpenAI-compatible chat call (stdlib urllib) — the shared
    transport for every provider speaking this protocol (Gemma on Novita,
    Mercury diffusion, …). `image` optional: a text-only prompt makes a plain
    chat request (the Mercury fast-text route).

    Returns the text. `chat_completion_full` returns the usage with it.
    """
    return chat_completion_full(
        prompt, [image] if image is not None else None, model=model,
        base_url=base_url, api_key=api_key, system=system,
        max_tokens=max_tokens, temperature=temperature, timeout=timeout,
        extra_body=extra_body)["text"]


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
    return chat_completion(prompt, image, model=model or _model(),
                           base_url=_base_url(), api_key=_api_key(),
                           max_tokens=max_tokens, temperature=temperature,
                           timeout=timeout)


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
