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

import base64
import netrc
import os
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


# A browser-like User-Agent. Many hosts (aclanthology.org, Cloudflare-fronted
# sites, …) reject urllib's default "Python-urllib/X.Y" with 403/418 even for a
# public PDF; a normal UA gets the bytes. Applied to every string-URL request.
_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _netrc_auth(host: str):
    """(login, password) for `host` from ~/.netrc (or $NETRC), or None. Never
    raises — a missing/malformed .netrc simply yields no credentials."""
    try:
        path = os.environ.get("NETRC")
        rc = netrc.netrc(path) if path else netrc.netrc()
    except (FileNotFoundError, netrc.NetrcParseError, OSError):
        return None
    auth = rc.authenticators(host)
    if not auth:
        return None
    login, _account, password = auth
    if login and password is not None:
        return (login, password)
    return None


def _credentials_for(host: str):
    """The (user, password) to authenticate `host` with, or None. Precedence:
    a matching .netrc entry first (the standard host-keyed store), then env
    PDFDRILL_HTTP_USER/PDFDRILL_HTTP_PASSWORD — the env pair applies only to
    PDFDRILL_HTTP_AUTH_HOST when that is set, else to any host (single-host
    setup). Credentials are NEVER read from a committed file."""
    nrc = _netrc_auth(host)
    if nrc:
        return nrc
    user = os.environ.get("PDFDRILL_HTTP_USER")
    pw = os.environ.get("PDFDRILL_HTTP_PASSWORD")
    if not user or pw is None:
        return None
    scope = os.environ.get("PDFDRILL_HTTP_AUTH_HOST")
    if scope and scope.strip().lower() != (host or "").strip().lower():
        return None
    return (user, pw)


def apply_credentials(req: urllib.request.Request, host: str | None = None):
    """Attach an HTTP Basic `Authorization` header to `req` when credentials
    for its host are configured (see `_credentials_for`). An Authorization
    header already on the Request is left untouched. Returns the same Request."""
    if req.has_header("Authorization"):
        return req
    host = host or _host(req)
    cred = _credentials_for(host)
    if cred:
        token = base64.b64encode(f"{cred[0]}:{cred[1]}".encode()).decode()
        req.add_header("Authorization", "Basic " + token)
    return req


def urlopen(req, timeout: float | None = None, *, host: str | None = None):
    """`urllib.request.urlopen` that raises `NetworkBlocked` (friendly message)
    on a connection-level failure or an egress-proxy block, and otherwise
    behaves identically (HTTP statuses from the host propagate as `HTTPError`).

    A browser `User-Agent` is attached (string URL → wrapped in a Request; a
    Request without one → header added) so anti-bot hosts don't 403/418 a public
    download.
    """
    host = host or _host(req)
    # Offline switch: PDFDRILL_OFFLINE=1 refuses ALL outbound network up front, so
    # every paid/keyed route (mathpix upload, vision, bibfetch, translate, URL/
    # arXiv downloads) degrades gracefully with NO spend — regardless of any
    # env- OR file-based credentials. Used by the test harness's keyless mode.
    if os.environ.get("PDFDRILL_OFFLINE"):
        raise NetworkBlocked(
            f"Offline mode (PDFDRILL_OFFLINE=1): outbound network to {host} is "
            f"disabled, so no paid/keyed route runs. Unset PDFDRILL_OFFLINE to "
            f"allow network. Offline routes (model from lines.json, ocr, "
            f"latexbook, report, …) need no network.")
    if isinstance(req, str):
        req = urllib.request.Request(req, headers={"User-Agent": _UA})
    elif isinstance(req, urllib.request.Request) and not req.has_header("User-agent"):
        req.add_header("User-Agent", _UA)
    apply_credentials(req, host)               # HTTP Basic for an auth-walled host
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
