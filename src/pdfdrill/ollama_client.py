"""Gemma-4 on a LOCAL Ollama host — the model lane with no account at all.

WHY THIS IS A PROVIDER AND NOT AN OVERRIDE
------------------------------------------
`gemma_client.chat_completion_full` is already a generic OpenAI-compatible
transport (base URL + key + `extra_body`), and Ollama serves that protocol at
`<host>/v1/chat/completions`. So pointing the existing Gemma client at a local
host needs no new transport — and the same argument the Makora entry makes
applies here: the HOST's properties are what a provider entry is for.

What is a property of this host, and nowhere else:

* **No key.** There is nothing to spend and nothing to leak, so availability
  cannot be answered by looking for a credential. It is answered by asking the
  host which models it has — the one honest question, and the only one that
  distinguishes "configured" from "running".
* **It reasons unless told not to.** Measured on gemma4:26b here, 2026-11-25:
  `max_tokens` 20 and no guard returned `content: ""` with the whole budget
  spent in a `reasoning` field the OpenAI envelope does not carry — an empty
  page, not a short one. With `{"reasoning_effort": "none"}` the same prompt
  answered `OK` in 2 completion tokens. This is the same quirk Makora has, and
  it is sent for the same reason.
* **It is on the user's own network.** The host string is configuration, never
  an artefact: `provider_record()` reports the MODEL, so a reading, a log line
  or a report never carries the machine's name.

THE DPI THIS DOES NOT CHANGE
----------------------------
`gemma_reader` renders at its own resolution and cuts the page into strips; the
provider only answers a prompt. So this module adds no second render path, and
a reading made here is the same artefact — `source: gemma4-ink-yolo`, same
names beside the PDF — read by a host that charges nothing.

A DAEMON THAT HAPPENS TO LISTEN IS NOT A LANE, and this is the lesson that
cost 13 test failures. The first version asked only whether something answered
at `OLLAMA_HOST` or `http://localhost:11434` — and on this machine something
does, so `route`, `drill`, `doctor` and the budget guard all changed their
answers, and eleven tests that pin the METERED path failed because of a daemon
none of them knows about. A lane whose availability depends on which daemons
run on the machine is not a lane and its measurements are not measurements.

So the host must be DECLARED TO PDFDRILL — `ollama_host` in `pdfdrill config`,
or `PDFDRILL_OLLAMA_HOST` for one run — and then answer. The shell's own
`OLLAMA_HOST` is deliberately NOT consulted: it is Ollama's variable, set for
other reasons on machines that never asked pdfdrill for anything, and reading
it would put the lane back at the mercy of the environment. `doctor` prints the
value to declare, so the step is one line and visible.

Configuration, first that answers:

    PDFDRILL_OLLAMA_HOST     declares the host, for one run
    ollama_host  (config)    declares it permanently — `pdfdrill config`
    (nothing)                no lane

and the model `PDFDRILL_OLLAMA_MODEL`, `ollama_model` (config), else
`gemma4:26b`.

Pure stdlib.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from . import config
from .env import get

#: Ollama's default listen address.
DEFAULT_HOST = "http://localhost:11434"
#: The model the board's scan rows were read with (gemma4:26b, Q4_K_M).
DEFAULT_MODEL = "gemma4:26b"
#: Sent with every call: without it the model spends the completion budget in a
#: `reasoning` field the OpenAI envelope drops, and the page comes back empty.
EXTRA_BODY = {"reasoning_effort": "none"}
#: The availability probe is a `GET /api/tags`. It must be quick enough to sit
#: in a routing decision and in `doctor`.
PROBE_TIMEOUT = 2.0
#: A 26B model reading one page strip was measured at 24 s on this host, so a
#: whole page of strips is minutes, not seconds.
TIMEOUT = 600.0

_probe: Optional[tuple] = None          # cached (ok, detail) of the last probe


def host() -> str:
    """The DECLARED host, without a trailing slash, or "" when none is."""
    return (get("PDFDRILL_OLLAMA_HOST", "")
            or str(config.get("ollama_host", "") or "")).rstrip("/")


def declared() -> bool:
    """Has a host been declared to pdfdrill? Asked before anything is probed,
    because the probe is what made the install's answer depend on the
    machine."""
    return bool(host())


def base_url() -> str:
    """The OpenAI-compatible base URL (`gemma_client` appends the route), or ""
    when no host is declared."""
    h = host()
    if not h:
        return ""
    if not h.startswith(("http://", "https://")):
        h = "http://" + h               # a declaration may be bare host:port
    return h.rstrip("/") + "/v1"


def model() -> str:
    return (get("PDFDRILL_OLLAMA_MODEL", "")
            or str(config.get("ollama_model", "") or "")
            or DEFAULT_MODEL)


def hostname() -> str:
    """The host's name only, for a message to the person running the command.
    Never written into a reading, a log or a report."""
    h = base_url()
    return urllib.parse.urlparse(h).hostname or h or "(none declared)"


def reset_cache() -> None:
    global _probe
    _probe = None


def models(timeout: float = PROBE_TIMEOUT) -> list[str]:
    """The model names the host serves, or [] when it does not answer.

    Deliberately NOT routed through `net.urlopen`: that function's job is to
    turn a blocked OUTBOUND host into a typed refusal naming the host, and
    this is a machine on the user's own network whose name stays out of
    messages.
    """
    base = base_url()
    if not base:
        return []
    url = base[: -len("/v1")] + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return []
    out = []
    for m in (data.get("models") or []):
        name = m.get("name") or m.get("model") or ""
        if name:
            out.append(name)
    return out


def probe(refresh: bool = False) -> tuple:
    """(ok, detail). Cached per process: a routing decision asks this, and so
    does `doctor`, and neither should cost a second round trip."""
    global _probe
    if _probe is not None and not refresh:
        return _probe
    if get("PDFDRILL_OFFLINE", ""):
        _probe = (False, "PDFDRILL_OFFLINE=1")
        return _probe
    if get("PDFDRILL_SANDBOX", ""):
        # The keyless sandbox has no such host; answering otherwise would make
        # `route`, `drill` and `doctor` disagree with the install they describe.
        _probe = (False, "PDFDRILL_SANDBOX=1")
        return _probe
    if not declared():
        _probe = (False, "no host declared")
        return _probe
    have = models()
    if not have:
        _probe = (False, f"no answer from {hostname()}")
        return _probe
    want = model()
    if want in have or any(h.split(":")[0] == want.split(":")[0] for h in have):
        _probe = (True, want)
        return _probe
    _probe = (False, f"{hostname()} serves {len(have)} model(s), not {want}")
    return _probe


def available() -> bool:
    return probe()[0]


def why_unavailable() -> str:
    """Grounded absence: what was asked and what answered."""
    ok, detail = probe()
    if ok:
        return ""
    return (f"local Ollama: {detail}. Declare the host with `ollama_host` in "
            f"`pdfdrill config` (or PDFDRILL_OLLAMA_HOST for one run) and the "
            f"model with `ollama_model` (default {DEFAULT_MODEL}); the shell's "
            f"own OLLAMA_HOST is not read, because a daemon that happens to "
            f"listen is not a lane.")


def provider_record() -> str:
    """What goes into the artefact: the model, never the machine."""
    return f"ollama/{model()}"
