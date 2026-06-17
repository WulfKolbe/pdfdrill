"""
Perplexity SONAR client for BibTeX enrichment.

Ported from the user's updateBibentries.ts. Printed references are usually
truncated, so a full structured BibTeX entry is requested from an LLM
(Perplexity `sonar`, which searches online for missing fields) rather than
parsed with a grammar. Given a Reference (citekey + author + year + the
original truncated text), `enrich` returns the full BibTeX plus citations and
the parsed author/year/title.

Credentials come from PERPLEXITY_API_KEY (env), falling back to a git-ignored
`perplexity_creds.py` — the key never enters version control.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from . import net
from typing import Optional

API_ENDPOINT = "https://api.perplexity.ai/chat/completions"
MODEL = "sonar"

_BIBTEX_BLOCK = re.compile(r"```(?:bibtex)?\s*([\s\S]*?)```", re.I)
_BIBTEX_FALLBACK = re.compile(r"(@\w+\{[\s\S]*?\n\})")
_CIT_SECTION = re.compile(r"Citations?:\s*((?:- .+\n*)+)", re.I)
_FIELD = r"{0}\s*=\s*[{{\"]([^}}\"]*)[}}\"]"


def _api_key() -> str:
    from . import perplexity_creds
    return perplexity_creds.require()


def available() -> bool:
    """True if a Perplexity API key is configured (env / .env / creds file).
    When False, cmd_bibfetch falls back to the keyless LLM-delegation path."""
    try:
        return bool(_api_key())
    except (Exception, SystemExit):    # require() raises SystemExit when unset
        return False


def bibtex_prompt(citekey: str, author: str, year: str, title: str,
                  raw_text: str) -> str:
    return (
        "Generate a complete BibTeX entry for the following reference:\n"
        f"Title: {title}\n"
        f"Authors: {author}\n"
        f"Year: {year}\n"
        f"Citation Key: {citekey}\n"
        f"Full Reference Text: {raw_text}\n"
        "Please include all available fields, search online for missing "
        "publication details if possible, and output the BibTeX entry only."
    )


def call_sonar(prompt: str, timeout: float = 60.0) -> dict:
    """POST a prompt to Perplexity; return {answer, citations}."""
    payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        API_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {_api_key()}",
                 "Content-Type": "application/json"},
    )
    try:
        with net.urlopen(req, timeout=timeout, host="api.perplexity.ai") as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Perplexity request failed: HTTP {e.code} {e.reason}") from e
    answer = (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
    citations = data.get("citations") or []
    return {"answer": answer, "citations": citations if isinstance(citations, list) else []}


def parse_response(output: str) -> dict:
    """Extract the BibTeX block and any citation list from the model output."""
    m = _BIBTEX_BLOCK.search(output) or _BIBTEX_FALLBACK.search(output)
    bibtex = m.group(1).strip() if m else ""
    citations: list[str] = []
    cm = _CIT_SECTION.search(output)
    if cm:
        for line in cm.group(1).splitlines():
            line = line.strip()
            if line.startswith("- "):
                citations.append(line[2:])
    return {"bibtex": bibtex, "citations": citations}


def parse_bibtex_fields(bibtex: str) -> dict:
    """Pull author/year/title (and entry_type) out of a BibTeX string."""
    fields: dict[str, str] = {}
    for name in ("author", "year", "title", "journal", "booktitle", "doi"):
        m = re.search(_FIELD.format(name), bibtex, re.I)
        if m:
            fields[name] = m.group(1).strip()
    et = re.match(r"\s*@(\w+)\s*\{", bibtex)
    if et:
        fields["entry_type"] = et.group(1).lower()
    return fields


def enrich(citekey: str, author: str, year: str, raw_text: str,
           title: str = "") -> dict:
    """Request and parse a full BibTeX entry. Returns
    {bibtex, citations, fields}."""
    resp = call_sonar(bibtex_prompt(citekey, author, year, title, raw_text))
    parsed = parse_response(resp["answer"])
    citations = resp["citations"] or parsed["citations"]
    return {
        "bibtex": parsed["bibtex"],
        "citations": citations,
        "fields": parse_bibtex_fields(parsed["bibtex"]),
    }


def links_prompt(title: str, author: str, year: str, raw_text: str) -> str:
    return (
        "Find every URL where the full text of this publication can be "
        "DOWNLOADED — prefer direct PDF links and free/open-access routes "
        "(arXiv, the DOI, institutional or author copies, open repositories).\n"
        f"Title: {title}\nAuthors: {author}\nYear: {year}\n"
        f"Full Reference Text: {raw_text}\n"
        "Output ONE URL per line, most directly downloadable first. "
        "No commentary."
    )


def fetch_links(title: str, author: str, year: str, raw_text: str) -> dict:
    """Ask SONAR for all downloadable links for the publication. Returns
    {links: [url, ...], answer}. `links` merges the answer's URLs with SONAR's
    own citation URLs (de-dup done downstream by citedrill.extract_links)."""
    resp = call_sonar(links_prompt(title, author, year, raw_text))
    return {"answer": resp["answer"], "citations": resp["citations"]}
