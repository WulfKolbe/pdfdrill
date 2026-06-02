"""
DeepL translation client (DeepL API v2, stdlib urllib — no `deepl-node`/SDK).

Ported from the tested `~/MX/tiddly-translation` project (src/deepl.ts): each
translatable tiddler field is sent to DeepL, the translation replaces the field,
and the original is preserved under `org_<field>` (see commands.cmd_translate).

Credentials: `DEEPL_API_KEY` from the environment / git-ignored `.env`. A free
key ends in `:fx` and uses the api-free host; otherwise the pro host is used.
Network calls go through `net.urlopen`, so a blocked sandbox host yields a clear
`NetworkBlocked` message rather than a stack trace. Graceful: empty text is
returned as-is, and a quota/error returns the ORIGINAL text (never crashes a
batch).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from . import net
from .env import get

FREE_HOST = "https://api-free.deepl.com"
PRO_HOST = "https://api.deepl.com"


def available() -> bool:
    return bool(get("DEEPL_API_KEY", ""))


def _api_key() -> str:
    key = get("DEEPL_API_KEY", "")
    if not key:
        raise RuntimeError(
            "DeepL credentials missing. Set DEEPL_API_KEY in the environment "
            "or copy .env.example to .env and fill it in "
            "(https://www.deepl.com/your-account/keys)."
        )
    return key


def _endpoint(key: str) -> str:
    host = FREE_HOST if key.rstrip().endswith(":fx") else PRO_HOST
    return f"{host}/v2/translate"


def translate_batch(texts: list[str], target_lang: str,
                    source_lang: str | None = None, timeout: float = 60.0) -> list[str]:
    """Translate a list of texts in one DeepL request; returns a same-length
    list (order preserved). Empty/whitespace items pass through untouched. On a
    DeepL error (quota, bad request) the ORIGINAL texts are returned so a batch
    never aborts. Raises NetworkBlocked only when the host is unreachable."""
    if not texts:
        return []
    idx = [i for i, t in enumerate(texts) if (t or "").strip()]
    if not idx:
        return list(texts)
    key = _api_key()
    fields = [("text", texts[i]) for i in idx]
    fields.append(("target_lang", target_lang.upper()))
    if source_lang:
        fields.append(("source_lang", source_lang.upper()))
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        _endpoint(key), data=data, method="POST",
        headers={"Authorization": f"DeepL-Auth-Key {key}",
                 "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with net.urlopen(req, timeout=timeout, host=urllib.parse.urlsplit(_endpoint(key)).netloc) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except net.NetworkBlocked:
        raise
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        # Quota/auth/bad-request: degrade to the originals rather than abort.
        return list(texts)
    except Exception:
        return list(texts)

    out = list(texts)
    translations = payload.get("translations") or []
    for slot, tr in zip(idx, translations):
        out[slot] = tr.get("text", texts[slot])
    return out


def translate_text(text: str, target_lang: str,
                   source_lang: str | None = None, timeout: float = 60.0) -> str:
    """Translate a single string (convenience over translate_batch)."""
    if not text or not text.strip():
        return text
    return translate_batch([text], target_lang, source_lang, timeout)[0]
