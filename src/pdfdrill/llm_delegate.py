"""
pdfdrill.llm_delegate — keyless LLM fallback by delegating to the *Claude that
is already running pdfdrill*.

Three pdfdrill providers need a hosted chat-LLM:

  - openai_vision     : an unresolved image crop  -> structured {selector, ...} JSON
  - perplexity_client : a truncated reference      -> full BibTeX / download links

(MathPix is OCR, not chat — full-page OCR already falls back to keyless
tesseract via ocr_lines.py; DeepL already degrades to returning the original
text. So the *only* hard gaps when no API keys exist are these two.)

The observation that makes a good fallback possible: pdfdrill is, in practice,
almost always executed *by a Claude agent* — either inside the Claude.ai code
sandbox, or under the Claude Code CLI on the user's own machine. In both cases
a fully capable multimodal LLM is right there. Rather than exit with "set a
key", route the sub-task to it.

Runtime detection (highest precedence first)::

    CLI      a `claude` binary is on PATH, or CLAUDECODE / CLAUDE_CODE_* is set.
             -> SYNCHRONOUS: shell out to `claude -p <prompt> --output-format
                json --allowedTools Read`, referencing the crop path in the
                prompt so Claude Code reads it. Parse `.result` back.

    SANDBOX  IS_SANDBOX=yes (the Claude.ai code sandbox) and no claude binary.
             -> DEFERRED: pdfdrill cannot itself call an LLM (no key, no
                binary), but the agent driving the bash session can. pdfdrill
                writes a request file, prints a machine-readable INSTRUCTION
                block the agent fulfils (it can *see* the crop), and ingests
                the agent's response file on the next invocation. The protocol
                is documented in the SKILL so any Claude agent knows the
                contract.

    NONE     neither -> raise DelegateUnavailable; the caller keeps its
             existing "set OPENAI_API_KEY / PERPLEXITY_API_KEY" message.

Both transports speak the SAME task contract, so a delegated result is
byte-compatible with what openai_vision / perplexity_client would have
returned, and every downstream layer is unchanged. Stdlib only.
"""
from __future__ import annotations

import enum
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Runtime detection
# ---------------------------------------------------------------------------

class Runtime(enum.Enum):
    CLI = "cli"          # Claude Code CLI present -> synchronous `claude -p`
    SANDBOX = "sandbox"  # Claude.ai code sandbox  -> deferred agent handshake
    NONE = "none"        # no Claude agent reachable


def _claude_binary() -> Optional[str]:
    """Path to the Claude Code CLI, or None. Overridable via PDFDRILL_CLAUDE_BIN
    (useful for tests and for a non-PATH install)."""
    override = os.environ.get("PDFDRILL_CLAUDE_BIN")
    if override:
        return override if (Path(override).exists() or shutil.which(override)) else None
    return shutil.which("claude")


def detect_runtime() -> Runtime:
    """Detect which Claude agent, if any, is available to delegate to.

    CLI wins over SANDBOX: a real synchronous `claude -p` is strictly better
    than the deferred handshake. An explicit PDFDRILL_DELEGATE override
    (cli|sandbox|none) short-circuits everything for testing / forcing a path.
    """
    forced = os.environ.get("PDFDRILL_DELEGATE", "").strip().lower()
    if forced in ("cli", "sandbox", "none"):
        return Runtime(forced)

    if _claude_binary() is not None:
        return Runtime.CLI
    if os.environ.get("CLAUDECODE") or any(
        k.startswith("CLAUDE_CODE") for k in os.environ
    ):
        # Claude Code env without the binary on PATH (e.g. a wrapper shell):
        # still CLI-shaped, but only usable if we can resolve the binary.
        return Runtime.CLI if _claude_binary() else Runtime.SANDBOX
    if os.environ.get("IS_SANDBOX", "").lower() in ("1", "yes", "true"):
        return Runtime.SANDBOX
    return Runtime.NONE


# ---------------------------------------------------------------------------
# Task contract
# ---------------------------------------------------------------------------

class DelegateUnavailable(RuntimeError):
    """No Claude agent reachable to satisfy a delegated task."""


@dataclass(frozen=True)
class LLMTask:
    """A single LLM sub-task. `kind` selects how the result is parsed back.

    kind == "vision" : returns the openai_vision result dict
                       ({selector, math, tikzpicture, ...}). Needs image_path.
    kind == "bibtex" : returns {bibtex, citations} (perplexity enrich shape).
    kind == "links"  : returns {answer, citations} (perplexity links shape).
    """
    kind: str
    prompt: str
    image_path: Optional[str] = None
    meta: dict = field(default_factory=dict)   # free-form context (citekey, url, ...)

    @property
    def task_id(self) -> str:
        """Stable content-hash identity (blake2b) over the inputs — matches
        pdfdrill's content-hash identity convention, so the same crop+prompt
        always maps to the same request/response file and is cache-friendly."""
        h = hashlib.blake2b(digest_size=16)
        h.update(self.kind.encode())
        h.update(b"\x00")
        h.update(self.prompt.encode("utf-8"))
        if self.image_path:
            p = Path(self.image_path)
            if p.exists():
                # hash the bytes (identity follows content, not filename)
                h.update(b"\x00")
                h.update(p.read_bytes())
            else:
                h.update(b"\x00")
                h.update(self.image_path.encode("utf-8"))
        return h.hexdigest()


@dataclass
class Deferred:
    """Returned by the SANDBOX transport: the request was written but not yet
    answered. `instruction` is a human+machine-readable block telling the agent
    what to do; the caller prints it and exits cleanly."""
    tasks: list[LLMTask]
    req_dir: Path
    instruction: str


# ---------------------------------------------------------------------------
# CLI transport — synchronous `claude -p`
# ---------------------------------------------------------------------------

_SYSTEM_VISION = (
    "You are pdfdrill's vision fallback, standing in for a hosted vision API. "
    "Follow the user instructions EXACTLY and return ONLY the requested JSON "
    "object — no markdown fences, no commentary."
)
_SYSTEM_BIB = (
    "You are pdfdrill's bibliographic fallback, standing in for an online "
    "search LLM. Return ONLY what the user asks for (a BibTeX entry, or URLs), "
    "with no commentary."
)


def _cli_invoke(prompt: str, *, system: str, allow_read: bool,
                timeout: float, model: Optional[str] = None) -> str:
    """Run one headless `claude -p` and return the textual result.

    Uses --output-format json so we get a structured envelope with an is_error
    flag rather than guessing from stdout. `--allowedTools Read` lets Claude
    Code open a referenced crop file; nothing else is permitted, so the run
    cannot edit the repo. We do NOT pass --dangerously-skip-permissions: Read
    is on the safe allowlist and needs no approval.
    """
    claude = _claude_binary()
    if not claude:
        raise DelegateUnavailable("claude CLI not found on PATH")
    cmd = [claude, "-p", prompt, "--output-format", "json",
           "--append-system-prompt", system]
    if allow_read:
        cmd += ["--allowedTools", "Read"]
    if model:
        cmd += ["--model", model]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"claude -p timed out after {timeout:.0f}s") from e
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude -p exited {proc.returncode}: {proc.stderr.strip()[:300]}")
    try:
        env = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"claude -p produced non-JSON output: {proc.stdout.strip()[:300]}"
        ) from e
    if env.get("is_error"):
        raise RuntimeError(f"claude -p reported error: {env.get('result')}")
    return env.get("result", "") or ""


def _run_cli(task: LLMTask, *, timeout: float, model: Optional[str]) -> dict:
    if task.kind in ("vision", "page_md", "eq_ocr"):
        # Reference the image path so Claude Code reads it with the Read tool.
        prompt = (f"Read the image file at {Path(task.image_path).resolve()} "
                  f"and analyse it.\n\n{task.prompt}")
        text = _cli_invoke(prompt, system=_SYSTEM_VISION, allow_read=True,
                          timeout=timeout, model=model)
        if task.kind == "vision":
            return _parse_vision(text)
        if task.kind == "page_md":
            return _parse_page_md(text)
        return _parse_eq_ocr(text)
    elif task.kind in ("bibtex", "links"):
        text = _cli_invoke(task.prompt, system=_SYSTEM_BIB, allow_read=False,
                          timeout=timeout, model=model)
        return _parse_bib(task.kind, text)
    raise ValueError(f"unknown task kind: {task.kind!r}")


# Image task kinds that can share ONE claude -p call (see _run_cli_batch).
_BATCHABLE = ("vision", "page_md", "eq_ocr")
# Max images per batched call — keep each combined response bounded (and well
# under output limits) while still amortizing the startup tax. 23 pages -> 3
# calls instead of 23.
_CLI_BATCH_MAX = 10

# NOTE: this whole delegation path exists only because no MathPix key is present.
# MathPix does this same page->LaTeX OCR natively, far FASTER and CHEAPER than
# round-tripping every page through a general LLM (each `claude -p` re-pays the
# Claude Code startup cost; even batched, an LLM page read is dearer than a
# MathPix call). If you have any volume of math PDFs, a MathPix key is the right
# tool — pricing: https://mathpix.com/pricing/all


def _coerce_result(kind: str, raw: Any) -> dict:
    """Turn one image's value from a batched JSON response into the same result
    dict the single-task parser returns, regardless of whether the agent nested
    it as parsed JSON or as a string."""
    if kind == "page_md":
        if isinstance(raw, dict) and "markdown" in raw:
            return raw
        return _parse_page_md(raw if isinstance(raw, str) else json.dumps(raw))
    if kind == "eq_ocr":
        if isinstance(raw, dict) and "records" in raw:
            return raw
        if isinstance(raw, (list, dict)):
            return _parse_eq_ocr(json.dumps(raw))
        return _parse_eq_ocr(str(raw))
    if kind == "vision":
        return _parse_vision(json.dumps(raw) if not isinstance(raw, str) else raw)
    raise ValueError(f"non-batchable kind: {kind!r}")


def _parse_batch_object(text: str) -> dict:
    """Parse a combined {task_id: result} object from the agent's reply."""
    s = _strip_fences(text or "")
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        i, j = s.find("{"), s.rfind("}")
        if i >= 0 and j > i:
            try:
                obj = json.loads(s[i:j + 1])
            except json.JSONDecodeError:
                return {}
        else:
            return {}
    return obj if isinstance(obj, dict) else {}


def _run_cli_batch(tasks: "list[LLMTask]", *, timeout: float,
                   model: Optional[str]) -> dict:
    """Run a homogeneous batch of image tasks in ONE `claude -p` call.

    Each `claude -p` re-instantiates the full Claude Code harness (~180K tokens of
    cached system prompt), so one-subprocess-per-page pays that tax N times. We
    instead reference every page image in a single prompt and ask for one JSON
    object mapping each task_id to that image's result, paying the tax ONCE per
    chunk. (Still slower/dearer than MathPix — https://mathpix.com/pricing/all .)
    Returns {task_id: result_dict} for every id the model answered; a missing id
    is simply absent so the caller can retry it singly.
    """
    kind = tasks[0].kind
    # SHORT ordinal ids (img1, img2, …) — a model echoes these reliably, whereas
    # asking it to repeat 32-char hex task_ids as JSON keys is fragile. Map back
    # to the real task_id by position.
    sids = {f"img{i + 1}": t for i, t in enumerate(tasks)}
    header = [
        f"You will analyse {len(tasks)} separate page images. For EACH image, read "
        f"the file at its path and apply the instructions to THAT image only. "
        f"Return ONLY one JSON object mapping each id to that image's result "
        f"(no prose, no code fence):",
        '  {"img1": <result for img1>, "img2": <result for img2>, ...}',
        "",
        "Images (id -> file path):",
    ]
    for sid, t in sids.items():
        header.append(f"  {sid}: {Path(t.image_path).resolve()}")
    prompts = {t.prompt for t in tasks}
    if len(prompts) == 1:
        header += ["", "Instructions to apply to EVERY image:", tasks[0].prompt]
    else:
        header += ["", "Per-image instructions (by id):"]
        for sid, t in sids.items():
            header.append(f"--- {sid} ---\n{t.prompt}")
    header += ["", "Each id's value must be exactly what its instructions ask for "
               "(e.g. the JSON array for eq_ocr, the Markdown string for page_md). "
               "Return the single mapping object and nothing else."]
    prompt = "\n".join(header)
    text = _cli_invoke(prompt, system=_SYSTEM_VISION, allow_read=True,
                       timeout=timeout, model=model)
    obj = _parse_batch_object(text)
    out: dict = {}
    for sid, t in sids.items():
        if sid not in obj:
            continue
        try:
            out[t.task_id] = _coerce_result(kind, obj[sid])
        except Exception:
            pass        # leave unanswered -> caller retries singly
    return out


def _run_cli_all(tasks: "list[LLMTask]", *, timeout: float,
                 model: Optional[str]) -> dict:
    """Resolve every task via the CLI, batching same-kind image tasks into
    chunked single calls and running the rest one-by-one. Any image task the
    batch left unanswered (model dropped an id) is retried as a single call."""
    results: dict = {}
    batchable = [t for t in tasks if t.kind in _BATCHABLE and t.image_path]
    singles = [t for t in tasks if t not in batchable]

    by_kind: dict = {}
    for t in batchable:
        by_kind.setdefault(t.kind, []).append(t)
    for kind, group in by_kind.items():
        for i in range(0, len(group), _CLI_BATCH_MAX):
            chunk = group[i:i + _CLI_BATCH_MAX]
            if len(chunk) == 1:
                results[chunk[0].task_id] = _run_cli(
                    chunk[0], timeout=timeout, model=model)
                continue
            # scale the subprocess timeout with chunk size (one call, many pages)
            bt = min(max(timeout, 30.0 * len(chunk)), 1800.0)
            try:
                results.update(_run_cli_batch(chunk, timeout=bt, model=model))
            except Exception:
                pass        # whole-batch failure -> per-task below
            for t in chunk:                       # fill any gaps singly
                if t.task_id not in results:
                    try:
                        results[t.task_id] = _run_cli(t, timeout=timeout, model=model)
                    except Exception:
                        pass
    for t in singles:
        results[t.task_id] = _run_cli(t, timeout=timeout, model=model)
    return results


# ---------------------------------------------------------------------------
# Result parsing — identical to what the real providers return
# ---------------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def _parse_vision(text: str) -> dict:
    """Parse the agent's reply into the openai_vision result dict."""
    s = _strip_fences(text)
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        # last resort: find the first {...} span
        i, j = s.find("{"), s.rfind("}")
        if i >= 0 and j > i:
            obj = json.loads(s[i:j + 1])
        else:
            raise
    if not isinstance(obj, dict) or "selector" not in obj:
        raise RuntimeError("vision result missing 'selector'")
    return obj


def _parse_page_md(text: str) -> dict:
    """Parse a page→MathPix-Markdown reply: {markdown, given_up}. The sentinel (or
    empty output) means the model honestly declined — don't ingest a guess."""
    from . import openai_vision as ov
    s = (text or "").strip()
    if s.startswith("```") and s.rstrip().endswith("```"):   # whole page fenced
        s = _strip_fences(s)
    given_up = (not s) or (ov.GIVE_UP_SENTINEL in s)
    return {"markdown": "" if given_up else s, "given_up": given_up}


def _parse_eq_ocr(text: str) -> dict:
    """Parse an equation-OCR reply into {records:[{page,number,latex,kind}]}.

    The agent returns a JSON array (possibly fenced). Anything that doesn't parse
    to a list of latex-bearing objects yields an empty record set — a page with
    no readable display math is a valid, common answer, never an error."""
    s = _strip_fences(text or "")
    try:
        arr = json.loads(s)
    except json.JSONDecodeError:
        i, j = s.find("["), s.rfind("]")
        if i >= 0 and j > i:
            try:
                arr = json.loads(s[i:j + 1])
            except json.JSONDecodeError:
                return {"records": []}
        else:
            return {"records": []}
    if not isinstance(arr, list):
        return {"records": []}
    records = []
    for r in arr:
        if not isinstance(r, dict):
            continue
        latex = (r.get("latex") or "").strip()
        if not latex:
            continue
        kind = r.get("kind") if r.get("kind") in ("equation", "math") else "equation"
        num = r.get("number")
        records.append({
            "page": r.get("page"),
            "number": str(num).strip() if num not in (None, "") else None,
            "latex": latex,
            "kind": kind,
        })
    return {"records": records}


def _parse_bib(kind: str, text: str) -> dict:
    """Reuse perplexity_client's own parsers so the shape is identical."""
    try:
        from . import perplexity_client as pc
    except ImportError:                      # run as a bare script (python file.py)
        from pdfdrill import perplexity_client as pc
    if kind == "bibtex":
        parsed = pc.parse_response(text)
        return {"bibtex": parsed["bibtex"], "citations": parsed["citations"],
                "fields": pc.parse_bibtex_fields(parsed["bibtex"])}
    # links: the provider returns {answer, citations}; the agent returns URLs
    # one per line. Hand the raw text back as `answer` (citedrill.extract_links
    # de-dups downstream, exactly as for the real Sonar answer).
    return {"answer": text, "citations": []}


# ---------------------------------------------------------------------------
# SANDBOX transport — deferred request/response handshake via files
# ---------------------------------------------------------------------------

REQ_SUFFIX = ".req.json"
RESP_SUFFIX = ".resp.json"


def _llm_dir(drill_dir: Path) -> Path:
    d = Path(drill_dir) / "llm"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_request(task: LLMTask, llm_dir: Path) -> Path:
    req = {
        "task_id": task.task_id,
        "kind": task.kind,
        "prompt": task.prompt,
        "image_path": (str(Path(task.image_path).resolve())
                       if task.image_path else None),
        "meta": task.meta,
        "created": time.time(),
        "schema": _SCHEMA_HINT.get(task.kind, ""),
    }
    p = llm_dir / (task.task_id + REQ_SUFFIX)
    p.write_text(json.dumps(req, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _read_response(task: LLMTask, llm_dir: Path) -> Optional[dict]:
    p = llm_dir / (task.task_id + RESP_SUFFIX)
    if not p.exists():
        return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    result = obj.get("result")
    if result is None:
        return None
    # `result` is the JSON the provider would have returned; if the agent wrote
    # it as a string, parse it through the same path as the CLI transport.
    if task.kind == "vision":
        return result if isinstance(result, dict) else _parse_vision(str(result))
    if task.kind == "page_md":
        return result if isinstance(result, dict) else _parse_page_md(str(result))
    if task.kind == "eq_ocr":
        return result if isinstance(result, dict) else _parse_eq_ocr(str(result))
    return result if isinstance(result, dict) else _parse_bib(task.kind, str(result))


_SCHEMA_HINT = {
    "vision": ('Return JSON: {"selector": "...", and ONLY the one field named '
               'by selector filled} — see the prompt for the field list.'),
    "page_md": ("Return this page as MathPix-Markdown (inline \\(..\\), display "
                "$$..$$ on their own lines), or EXACTLY PDFDRILL_CANNOT_RECONSTRUCT."),
    "eq_ocr": ('Return a JSON array of this page\'s display equations: '
               '[{"page":int,"number":str|null,"latex":"<LaTeX, keep _{}/^{}/\\\\frac>",'
               '"kind":"equation"|"math"}], or [] if none. Never fabricate.'),
    "bibtex": "Return a fenced ```bibtex block with one complete @entry{...}.",
    "links": "Return one downloadable URL per line, most direct first. No prose.",
}


def _instruction_block(tasks: list[LLMTask], llm_dir: Path) -> str:
    """The machine-readable block pdfdrill prints so the driving Claude agent
    knows exactly how to satisfy the pending requests. Kept terse and literal."""
    n_vis = sum(1 for t in tasks if t.kind == "vision")
    n_bib = sum(1 for t in tasks if t.kind in ("bibtex", "links"))
    lines = [
        "=== PDFDRILL-LLM-DELEGATION (sandbox) ===================================",
        f"No API keys present. {len(tasks)} LLM task(s) deferred to YOU, the Claude",
        f"agent running pdfdrill ({n_vis} vision, {n_bib} bibliographic). pdfdrill",
        "has no key and CANNOT call a model — so YOU ARE THE MODEL for these tasks.",
        "",
        "*** DO NOT use tesseract / pix2tex / pdftotext / any OCR or image-to-text",
        "    tool to answer these. ***  These tasks exist precisely BECAUSE OCR",
        "    cannot do them: vision must recover LaTeX / TikZ / commutative-diagram /",
        "    chemfig STRUCTURE from the crop (use your OWN sight), and bibtex/links",
        "    must WEB-SEARCH the real publication. An OCR transcription is a WRONG",
        "    answer and defeats the purpose. Do the task yourself with the prompt.",
        "",
        f"Requests are in: {llm_dir}",
        f"  *{REQ_SUFFIX}  — one per task: {{task_id, kind, prompt, image_path, schema}}",
        f"  (or run `pdfdrill llm <pdf> --show` to dump every open prompt at once)",
        "",
        "To satisfy them, for EACH <task_id>.req.json:",
        "  1. Read the request. If kind=vision, VIEW the image at image_path",
        "     directly (you can see it) — read it, do not OCR it. Else read prompt.",
        "  2. Do exactly what `prompt` asks, honouring `schema` (web-search for",
        "     bibtex/links; emit compilable LaTeX/TikZ for vision).",
        f"  3. Write {llm_dir}/<task_id>{RESP_SUFFIX} containing:",
        '        {"task_id": "<id>", "kind": "<kind>", "result": <obj-or-string>}',
        "     where `result` is the JSON object the prompt asks for (vision), or",
        "     the BibTeX/URL text (bibtex/links). A JSON object or a raw string",
        "     are both accepted — pdfdrill parses either.",
        "  4. Re-run the SAME pdfdrill command. It will find the responses,",
        "     ingest them, and continue. (`pdfdrill llm --status <pdf>` lists",
        "     what is still pending; `--show` dumps all open prompts at once.)",
        "========================================================================",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def delegate_batch(
    tasks: list[LLMTask],
    *,
    drill_dir: Optional[Path] = None,
    runtime: Optional[Runtime] = None,
    timeout: float = 120.0,
    model: Optional[str] = None,
) -> tuple[dict[str, dict], Optional[Deferred]]:
    """Satisfy a batch of LLM tasks via whichever Claude agent is available.

    Returns (results, deferred):
      - results : {task_id: result_dict} for every task already answered.
      - deferred: a Deferred (with the agent INSTRUCTION) if we are in the
                  SANDBOX and some tasks are still unanswered, else None.

    CLI    : runs each task synchronously now; deferred is always None.
    SANDBOX: returns any responses already on disk; for the rest it writes
             request files and returns a Deferred. The caller prints
             deferred.instruction and stops; on the next run the now-present
             responses come back in `results`.
    NONE   : raises DelegateUnavailable.
    """
    rt = runtime or detect_runtime()
    if rt is Runtime.NONE:
        raise DelegateUnavailable(
            "no Claude agent available (no claude CLI on PATH, and neither "
            "CLAUDECODE/CLAUDE_CODE_* nor IS_SANDBOX is set) — set OPENAI_API_KEY "
            "/ PERPLEXITY_API_KEY, or run under Claude Code / the Claude.ai "
            "sandbox. If you ARE in the sandbox but it isn't detected, force it "
            "with PDFDRILL_DELEGATE=sandbox (check with `pdfdrill llm <pdf> "
            "--runtime`).")

    results: dict[str, dict] = {}

    if rt is Runtime.CLI:
        # Batch same-kind image tasks into chunked single calls (amortize the
        # Claude Code startup tax); text tasks run one-by-one. MathPix would do
        # the page->LaTeX OCR faster/cheaper — https://mathpix.com/pricing/all
        results = _run_cli_all(tasks, timeout=timeout, model=model)
        return results, None

    # SANDBOX
    if drill_dir is None:
        raise ValueError("sandbox delegation needs drill_dir for the handshake")
    llm_dir = _llm_dir(drill_dir)
    pending: list[LLMTask] = []
    for t in tasks:
        resp = _read_response(t, llm_dir)
        if resp is not None:
            results[t.task_id] = resp
        else:
            _write_request(t, llm_dir)
            pending.append(t)
    deferred = None
    if pending:
        deferred = Deferred(tasks=pending, req_dir=llm_dir,
                           instruction=_instruction_block(pending, llm_dir))
    return results, deferred


def delegate(task: LLMTask, **kw) -> dict:
    """Single-task convenience. In the SANDBOX, an unanswered task raises
    DelegateUnavailable carrying the agent instruction (use delegate_batch for
    the clean deferred flow)."""
    results, deferred = delegate_batch([task], **kw)
    if task.task_id in results:
        return results[task.task_id]
    if deferred is not None:
        raise DelegateUnavailable(deferred.instruction)
    raise DelegateUnavailable("task could not be satisfied")


# ---------------------------------------------------------------------------
# Driver helpers for the `pdfdrill llm` subcommand (the SKILL/tool surface)
# ---------------------------------------------------------------------------

def pending_requests(drill_dir: Path) -> list[dict]:
    """All open requests (request file present, no response yet)."""
    llm_dir = Path(drill_dir) / "llm"
    if not llm_dir.exists():
        return []
    out = []
    for req in sorted(llm_dir.glob("*" + REQ_SUFFIX)):
        tid = req.name[:-len(REQ_SUFFIX)]
        if (llm_dir / (tid + RESP_SUFFIX)).exists():
            continue
        try:
            out.append(json.loads(req.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


# ---------------------------------------------------------------------------
# Self-test: detection + a full sandbox round-trip with a simulated agent.
# ---------------------------------------------------------------------------

def _selftest() -> int:
    import tempfile

    failures = 0

    def check(name, cond):
        nonlocal failures
        print(f"  [{'ok' if cond else 'FAIL'}] {name}")
        if not cond:
            failures += 1

    print("llm_delegate self-test")

    # --- detection overrides ---
    os.environ["PDFDRILL_DELEGATE"] = "sandbox"
    check("forced sandbox", detect_runtime() is Runtime.SANDBOX)
    os.environ["PDFDRILL_DELEGATE"] = "none"
    check("forced none", detect_runtime() is Runtime.NONE)
    os.environ["PDFDRILL_DELEGATE"] = "cli"
    check("forced cli", detect_runtime() is Runtime.CLI)
    del os.environ["PDFDRILL_DELEGATE"]

    # --- task identity is content-stable ---
    t1 = LLMTask("bibtex", "prompt A")
    t2 = LLMTask("bibtex", "prompt A")
    t3 = LLMTask("bibtex", "prompt B")
    check("task_id stable for same input", t1.task_id == t2.task_id)
    check("task_id differs for different input", t1.task_id != t3.task_id)

    # --- NONE raises ---
    try:
        delegate_batch([t1], runtime=Runtime.NONE)
        check("NONE raises", False)
    except DelegateUnavailable:
        check("NONE raises", True)

    # --- full SANDBOX round-trip with a simulated agent ---
    with tempfile.TemporaryDirectory() as td:
        drill = Path(td) / "doc.drill"
        vis = LLMTask("vision", openai_default := "classify this", image_path=None)
        bib = LLMTask("bibtex", "make bibtex for Foo 2020")

        # pass 1: nothing on disk -> deferred, request files written
        res, deferred = delegate_batch([vis, bib], drill_dir=drill,
                                      runtime=Runtime.SANDBOX)
        check("pass1 nothing answered", res == {})
        check("pass1 deferred returned", deferred is not None and
              len(deferred.tasks) == 2)
        reqs = pending_requests(drill)
        check("pass1 two requests pending", len(reqs) == 2)
        check("instruction names the dir", str(deferred.req_dir) in deferred.instruction)

        # simulate the agent answering both
        llm_dir = drill / "llm"
        (llm_dir / (vis.task_id + RESP_SUFFIX)).write_text(json.dumps({
            "task_id": vis.task_id, "kind": "vision",
            "result": {"selector": "math", "math": "x^2 + y^2 = r^2"},
        }))
        # agent writes bibtex as a raw fenced string (the lenient path)
        (llm_dir / (bib.task_id + RESP_SUFFIX)).write_text(json.dumps({
            "task_id": bib.task_id, "kind": "bibtex",
            "result": "```bibtex\n@article{foo2020, title={Foo}, year={2020}}\n```",
        }))

        # pass 2: responses present -> results filled, no deferral
        res2, deferred2 = delegate_batch([vis, bib], drill_dir=drill,
                                        runtime=Runtime.SANDBOX)
        check("pass2 nothing deferred", deferred2 is None)
        check("vision result parsed", res2[vis.task_id]["selector"] == "math")
        check("vision math field", res2[vis.task_id]["math"].startswith("x^2"))
        check("bibtex parsed from fenced string",
              "foo2020" in res2[bib.task_id]["bibtex"])
        check("bibtex fields extracted",
              res2[bib.task_id]["fields"].get("year") == "2020")
        check("no requests pending after answers", pending_requests(drill) == [])

    print("PASS" if failures == 0 else f"{failures} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
