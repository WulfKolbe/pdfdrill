"""
DeepL translation client (DeepL API v2, stdlib urllib — no `deepl-node`/SDK).

Ported from the tested `~/MX/tiddly-translation` project (src/deepl.ts): each
translatable tiddler field is sent to DeepL, the translation replaces the field,
and the original is preserved under `org_<field>` (see commands.cmd_translate).

Credentials: `DEEPL_API_KEY` from the environment / git-ignored `.env`. A free
key ends in `:fx` and uses the api-free host; otherwise the pro host is used.
Network calls go through `net.urlopen`, so a blocked sandbox host yields a clear
`NetworkBlocked` message rather than a stack trace. Empty text is returned
as-is.

815 — AN ERROR IS RAISED, NOT SWALLOWED. This used to return the ORIGINAL texts
on any HTTPError "so a batch never aborts", having first read DeepL's own error
message into a local variable and then discarded it. The result: `translate
--from CN` (DeepL's Chinese code is ZH) got a 400, every string came back
unchanged, and the command reported "Translated to EN-US via DeepL". A failed
paid call was byte-identical to a successful one, and the one artifact that
could have said so — DeepL's message — was read and thrown away.
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


class DeepLError(RuntimeError):
    """DeepL refused the request. Carries DeepL's own message."""


#: Source languages DeepL v2 accepts (`source_lang`). From DeepL's published
#: API documentation, not measured here — an unaccepted code is a 400, and the
#: point of this list is to refuse it before a paid call is made.
SOURCE_LANGS = frozenset("""
AR BG CS DA DE EL EN ES ET FI FR HE HU ID IT JA KO LT LV NB NL PL PT RO RU SK
SL SV TH TR UK VI ZH
""".split())

#: Target languages, which differ from the sources: several carry a REGION and
#: the bare code is deprecated or invalid (EN-GB/EN-US, PT-BR/PT-PT, ZH-HANS).
TARGET_LANGS = frozenset("""
AR BG CS DA DE EL EN-GB EN-US ES ES-419 ET FI FR HE HU ID IT JA KO LT LV NB NL
PL PT-BR PT-PT RO RU SK SL SV TH TR UK VI ZH ZH-HANS ZH-HANT
""".split())

#: What people type instead. `CN` is the ISO COUNTRY code for China and the
#: obvious guess for Chinese; DeepL wants the LANGUAGE code `ZH`. Each of these
#: was a silent no-op before 815.
_MISTAKES = {
    "CN": "ZH", "ZH-CN": "ZH", "CHS": "ZH", "CHT": "ZH-HANT", "JP": "JA",
    "KR": "KO", "GB": "EN-GB", "US": "EN-US", "UK": "UK", "GR": "EL",
    "CZ": "CS", "DK": "DA", "SE": "SV", "NO": "NB", "SI": "SL", "EE": "ET",
    "RS": "SR", "BR": "PT-BR", "PT": "PT-PT", "EN": "EN-US",
}


def check_lang(code: str, *, target: bool) -> "str | None":
    """None if `code` is a language DeepL accepts, else why not — BEFORE paying.

    A wrong code is not an error DeepL reports usefully once the batch is gone:
    it is a 400 whose body the client used to discard, leaving the run looking
    successful and the text untranslated.
    """
    if not code:
        return None
    up = code.strip().upper()
    allowed = TARGET_LANGS if target else SOURCE_LANGS
    if up in allowed:
        return None
    word = "target" if target else "source"
    flag = "--to" if target else "--from"          # the flags `translate` takes
    fix = _MISTAKES.get(up)
    if fix and fix in allowed:
        return (f"DeepL does not accept {code!r} as a {word} language — its code "
                f"for that is {fix}. Use `{flag} {fix}`.")
    near = sorted(c for c in allowed if c.startswith(up[:2]))
    hint = f" Did you mean {' or '.join(near)}?" if near else ""
    return (f"DeepL does not accept {code!r} as a {word} language.{hint} "
            f"Accepted {word}s: {' '.join(sorted(allowed))}")


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
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:                                    # noqa: BLE001
            pass
        # 815 — RAISE, carrying DeepL's message. Returning the originals here
        # made a refused request indistinguishable from a translated one, and
        # this very `body` — the only thing that could have said which — was
        # read and dropped on the floor.
        try:
            detail = (json.loads(body) or {}).get("message") or body
        except Exception:                                    # noqa: BLE001
            detail = body
        raise DeepLError(
            f"DeepL refused the request (HTTP {e.code}): {detail or 'no detail'}"
        ) from e
    except Exception as e:                                   # noqa: BLE001
        raise DeepLError(f"DeepL request failed: {type(e).__name__}: {e}") from e

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
