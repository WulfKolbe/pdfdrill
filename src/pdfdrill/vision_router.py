"""
vision_router — ONE routing layer over every vision/text LLM call.

THE STATE MACHINE DECIDES, NOT THE USER. Every prompt-driven capability the
toolchain has (table→LaTeX, equation OCR, page→Markdown, graph→TikZ, chemistry,
the upcoming scanned-commercial-document analyses) is a registered TASK: a
prompt + an ordered provider preference. `route(task)` picks the first
AVAILABLE provider (keys present) in that order; `run(task, image=…)` executes
it and returns the uniform snip-shaped record — so a command asks for a TASK
and never names a model.

The provider table (the routing facts):
  mathpix   the ONLY promptless provider (native image→LaTeX OCR) — preferred
            wherever it natively does the task (equations); paid per call.
  gemma     Gemma-4 vision on Novita.ai — very cheap, prompt-driven; the
            default cheap vision route (tables proven via TABLE_PROMPT).
  makora    the SAME Gemma-4, on Makora — cheapest and fastest measured
            (0.000718 EUR/page, 3-6 s/page), its own MAKORA_API_KEY, and a
            FIXED PREPAID balance that stops answering when it empties.
  mercury   the Mercury DIFFUSION model — very fast, TEXT-only; the fast-text
            route (no vision). Reached via its own base URL (MERCURY_API_BASE,
            default Inception) or Novita's hosting; key MERCURY_API_KEY else
            NOVITA_API_KEY.
  openai    GPT-4o vision — the heavy structured-JSON route (graphs/chem).
  delegate  the keyless Claude delegation (llm_delegate) — the fallback when
            no key at all is present but a Claude agent runs pdfdrill.

Extending (the commercial-document prompts land here):
    from pdfdrill import vision_router
    vision_router.register_task("commercial_invoice",
        prompt=INVOICE_PROMPT, providers=("gemma", "openai", "delegate"))
Then any command calls vision_router.run("commercial_invoice", image=crop).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .env import get
from . import prompts


# --------------------------------------------------------------------------- #
#  Providers
# --------------------------------------------------------------------------- #

@dataclass
class Provider:
    name: str
    kind: str                    # "vision" | "text" | "both"
    promptless: bool             # MathPix only: the task needs no prompt
    cost_rank: int               # lower = cheaper (routing tiebreak)
    available: Callable[[], bool]


def _mathpix_available() -> bool:
    return bool(get("MATHPIX_APP_ID", "") and get("MATHPIX_APP_KEY", ""))


def _gemma_available() -> bool:
    from . import gemma_client
    return gemma_client.available()


def _makora_available() -> bool:
    from . import gemma_client
    return gemma_client.makora_available()


def _mercury_available() -> bool:
    return bool(get("MERCURY_API_KEY", "") or get("NOVITA_API_KEY", ""))


def _openai_available() -> bool:
    from . import openai_vision
    return openai_vision.available()


def _delegate_available() -> bool:
    from . import llm_delegate
    return llm_delegate.detect_runtime() != llm_delegate.Runtime.NONE


PROVIDERS: dict[str, Provider] = {p.name: p for p in [
    Provider("mathpix", "vision", promptless=True, cost_rank=2,
             available=_mathpix_available),
    Provider("gemma", "vision", promptless=False, cost_rank=1,
             available=_gemma_available),
    # Makora: the same model, measured at 0.000718 EUR/page against Novita's
    # 20-30 s/page — cheapest and fastest, so rank 0. Its balance is a fixed
    # prepayment, which is why `gemma_reader` preflights a budget before the
    # first call rather than relying on the rank alone.
    Provider("makora", "vision", promptless=False, cost_rank=0,
             available=_makora_available),
    Provider("mercury", "text", promptless=False, cost_rank=1,
             available=_mercury_available),
    Provider("openai", "vision", promptless=False, cost_rank=3,
             available=_openai_available),
    Provider("delegate", "both", promptless=False, cost_rank=4,
             available=_delegate_available),
]}


# --------------------------------------------------------------------------- #
#  Tasks — prompt + provider preference order
# --------------------------------------------------------------------------- #

@dataclass
class Task:
    name: str
    kind: str                                  # "vision" | "text"
    prompt: Optional[str]                      # None → promptless-capable task
    providers: tuple                           # preference order


TASKS: dict[str, Task] = {}


def register_task(name: str, *, prompt: Optional[str], providers: tuple,
                  kind: str = "vision") -> Task:
    """Register (or replace) a task. This is where the user's new prompts land
    — e.g. the scanned-commercial-document analyses."""
    t = Task(name=name, kind=kind, prompt=prompt, providers=tuple(providers))
    TASKS[name] = t
    return t


def _builtin_tasks() -> None:
    from . import gemma_client, openai_vision
    register_task("equation_ocr",
                  prompt=openai_vision.EQ_OCR_PROMPT,
                  providers=("mathpix", "gemma", "openai", "delegate"))
    register_task("table_to_latex",
                  prompt=gemma_client.TABLE_PROMPT,
                  providers=("gemma", "openai", "mathpix", "delegate"))
    register_task("page_markdown",
                  prompt=openai_vision.MATHPIX_MD_PROMPT,
                  providers=("makora", "gemma", "openai", "delegate"))
    # The reader's own task (`gemma_reader`): a whole page, in strips, to
    # Markdown with LaTeX. Its prompt is a FILE (466), so it is loaded by
    # name rather than held in a Python string.
    register_task("page_ocr_markdown",
                  prompt=prompts.load("page-ocr-markdown"),
                  providers=("makora", "gemma", "openai", "delegate"))
    register_task("graph_tikz",
                  prompt=openai_vision.GRAPH_TIKZ_PROMPT,
                  providers=("openai", "gemma", "delegate"))
    register_task("chem_structure",
                  prompt=openai_vision.CHEM_STRUCTURE_PROMPT,
                  providers=("openai", "gemma", "delegate"))
    register_task("image_classify",
                  prompt=openai_vision.DEFAULT_PROMPT,
                  providers=("openai", "gemma", "delegate"))
    # fast text (no image): Mercury diffusion first — the caller supplies the
    # prompt at run() time (summaries, reformatting, quick answers).
    register_task("fast_text", prompt=None,
                  providers=("mercury", "gemma", "delegate"), kind="text")


_builtin_tasks()


# --------------------------------------------------------------------------- #
#  Routing — the state-machine decision
# --------------------------------------------------------------------------- #

def route(task: str) -> tuple[Optional[str], Optional[str]]:
    """(provider_name, prompt) for a task: the first AVAILABLE provider in the
    task's preference order. A promptless provider gets prompt=None (MathPix
    needs no instruction); a prompt-driven one gets the task's prompt.
    (None, <reason>) when nothing is available — grounded absence."""
    t = TASKS.get(task)
    if t is None:
        raise KeyError(f"unknown task: {task!r} (register_task first; known: "
                       f"{', '.join(sorted(TASKS))})")
    for name in t.providers:
        p = PROVIDERS.get(name)
        if p is None or not p.available():
            continue
        return name, (None if p.promptless else t.prompt)
    return None, (f"no provider available for task {task!r} — checked "
                  f"{', '.join(t.providers)}; set the corresponding API key "
                  f"(.env) or run under a Claude agent for the delegate route.")


# --------------------------------------------------------------------------- #
#  Execution — uniform record out, whatever the provider
# --------------------------------------------------------------------------- #

def _call_mathpix(task, prompt, image, text, **kw):
    from .mathpix_snip import snip_result
    return snip_result(image)


def _call_gemma(task, prompt, image, text, **kw):
    from . import gemma_client as gc
    # SEVERAL images in one call, when the caller sends them. A page is read
    # as overlapping strips because a host scales each image to a fixed token
    # budget, so strips and not dpi are what add detail — and a provider that
    # silently takes only the first strip returns the top sixth of the page
    # as though it were the page. (Measured as a TypeError the first time the
    # reader routed here instead of to `makora`: `analyze_image` has no
    # `images` parameter, which is the better failure of the two.)
    images = kw.pop("images", None) or ([image] if image else None)
    if images:
        rec = gc.chat_completion_full(
            prompt, images, model=kw.pop("model", None) or gc._model(),
            base_url=gc._base_url(), api_key=gc._api_key(), **kw)
    else:
        rec = gc.chat_completion_full(
            prompt or text, None, model=gc._model(),
            base_url=gc._base_url(), api_key=gc._api_key(), **kw)
    return {"provenance": "gemma", "latex": gc.strip_latex_fence(rec["text"]),
            "text": rec["text"], "confidence": None, "lines": [],
            "usage": rec["usage"], "finish_reason": rec["finish_reason"],
            "model": rec["model"]}


def _call_mercury(task, prompt, image, text, **kw):
    from . import gemma_client
    base = (get("MERCURY_API_BASE", "") or get("NOVITA_BASE_URL", "")
            or get("NOVITA_API_BASE", "") or "https://api.inception.ai/v1")
    key = get("MERCURY_API_KEY", "") or get("NOVITA_API_KEY", "")
    model = get("MERCURY_MODEL", "") or "mercury-coder"
    raw = gemma_client.chat_completion((prompt or "") + ("\n\n" + text if text else ""),
                                       model=model, base_url=base, api_key=key)
    return {"provenance": "mercury", "latex": "", "text": raw,
            "confidence": None, "lines": []}


def _call_openai(task, prompt, image, text, **kw):
    from . import openai_vision
    # This provider takes ONE image. A caller that sent several (a page in
    # strips) gets the first, which is the top of the page — so say so in the
    # record rather than return a sixth of a page as the page.
    images = kw.pop("images", None)
    kw.pop("max_tokens", None)
    res = openai_vision.analyze_image(image, prompt=prompt, **kw)
    if images and len(images) > 1:
        res = dict(res)
        res["partial"] = ("this provider takes one image; %d strips were sent "
                          "and only the first was read" % len(images))
    latex = res.get("latex") or res.get("latex_code") or ""
    return {"provenance": "openai", "latex": latex,
            "text": res.get("text", "") or str(res), "confidence": None,
            "lines": [], "selector": res.get("selector"),
            "partial": res.get("partial", "")}


def _call_delegate(task, prompt, image, text, **kw):
    from . import llm_delegate
    raise RuntimeError(
        "delegate route: use the llm_delegate handshake commands "
        "(pdfdrill vision / visionocr / remath) — the router names it as the "
        f"fallback for {task!r} but a synchronous run() call cannot block on "
        "the sandbox file handshake.")


def _call_makora(task, prompt, image, text, **kw):
    """The same model as `gemma`, on a host with its own key and its own
    metered balance. Carries `usage` back so the caller can record what the
    call cost — the one thing a fixed-prepayment account makes essential."""
    from . import gemma_client as gc
    images = kw.pop("images", None) or ([image] if image is not None else None)
    rec = gc.chat_completion_full(
        prompt, images, model=kw.pop("model", None) or gc.makora_model(),
        base_url=gc.makora_base_url(), api_key=gc.makora_api_key(),
        extra_body={**gc.MAKORA_EXTRA_BODY, **(kw.pop("extra_body", None) or {})},
        **kw)
    return {"provenance": "makora", "latex": gc.strip_latex_fence(rec["text"]),
            "text": rec["text"], "confidence": None, "lines": [],
            "usage": rec["usage"], "finish_reason": rec["finish_reason"],
            "model": rec["model"]}


_CALLERS: dict[str, Callable] = {
    "mathpix": _call_mathpix,
    "gemma": _call_gemma,
    "makora": _call_makora,
    "mercury": _call_mercury,
    "openai": _call_openai,
    "delegate": _call_delegate,
}


def run(task: str, image: Optional[str] = None, text: Optional[str] = None,
        **kw) -> dict[str, Any]:
    """Route + execute a task; the uniform record {provider, latex, text,
    confidence, lines, …} whatever provider served it."""
    provider, prompt_or_reason = route(task)
    if provider is None:
        return {"provider": None, "error": prompt_or_reason,
                "latex": "", "text": "", "confidence": None, "lines": []}
    rec = _CALLERS[provider](task, prompt_or_reason, image, text, **kw)
    rec["provider"] = provider
    return rec
