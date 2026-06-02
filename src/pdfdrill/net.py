"""
Outbound-HTTP helper with graceful sandbox-accessibility handling.

The four network routes (mathpix, snip, vision, bibfetch) call out via urllib.
In a locked-down sandbox (e.g. claude.ai) an outbound host that isn't enabled
fails at the connection layer (`URLError`/`OSError`/timeout) — or, behind an
egress proxy, as an HTTP 403/407/502 with a tell-tale body. Bare urllib lets
that escape as a stack trace. `urlopen()` here converts those into a typed
`NetworkBlocked` carrying a clear, actionable message that names the host and
points at the offline routes; genuine HTTP statuses from the host (401 auth,
429 rate, …) propagate unchanged so callers format them as before.
"""
from __future__ import annotations

import re
import socket
import urllib.error
import urllib.parse
import urllib.request

# Status codes + body hints that indicate an egress/proxy block rather than a
# genuine application response.
_BLOCK_CODES = {403, 407, 451, 502, 503}
_BLOCK_HINT = re.compile(
    r"block|not allowed|forbidden host|disallowed|egress|proxy|sandbox|"
    r"enable .*access|outbound|tunnel", re.I)


class NetworkBlocked(RuntimeError):
    """Raised when an outbound host is unreachable / blocked by the sandbox."""


def _host(req) -> str:
    url = req.full_url if isinstance(req, urllib.request.Request) else str(req)
    return urllib.parse.urlsplit(url).netloc or url


def friendly_message(host: str, detail: object) -> str:
    return (
        f"Network access to {host} appears blocked or unreachable in this "
        f"sandbox (the connection could not be established). If you're on "
        f"claude.ai, allow outbound access to {host} in your sandbox/network "
        f"settings and retry. No network is needed for the offline routes — "
        f"build the model from an existing lines.json, or use `ocr`, "
        f"`latexbook`, `embedimages`, `report`. (detail: {detail})"
    )


def urlopen(req, timeout: float | None = None, *, host: str | None = None):
    """`urllib.request.urlopen` that raises `NetworkBlocked` (friendly message)
    on a connection-level failure or an egress-proxy block, and otherwise
    behaves identically (HTTP statuses from the host propagate as `HTTPError`).
    """
    host = host or _host(req)
    try:
        if timeout is None:
            return urllib.request.urlopen(req)
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:        # host (or proxy) responded
        if e.code in _BLOCK_CODES:
            try:
                body = e.read().decode("utf-8", "replace")[:500]
            except Exception:
                body = ""
            if _BLOCK_HINT.search(body) or _BLOCK_HINT.search(str(e.reason or "")):
                raise NetworkBlocked(friendly_message(host, f"HTTP {e.code} {e.reason}")) from e
        raise
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        raise NetworkBlocked(friendly_message(host, e)) from e
