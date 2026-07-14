"""
Known-host URL sources — let every pdfdrill command work directly on an https
URL, and reach for the cheapest sufficient route per host.

The motivating case is arXiv: given an `arxiv.org` argument we DON'T need to pay
MathPix at all. The abstract is on the abs page (free), and the author's LaTeX
source — the *gold* form of every equation — is a free `e-print` .tgz download.
So `pdfdrill abstract https://arxiv.org/abs/<id>` answers from the abs page, and
`pdfdrill latex https://arxiv.org/abs/<id>` builds from the downloaded source,
both without a MathPix credit.

  KNOWN_HOSTS  — host substring → kind ("arxiv", …). Extend per new host.
  parse_arxiv_id / arxiv_urls / parse_arxiv_abs_html  — PURE (unit-tested).
  fetch_arxiv_metadata / download / resolve_input / download_arxiv_source  — net
    (via the shared net.urlopen wrapper, so a sandbox block degrades cleanly).

The "api for the .tgz" the download button hides is just the stable endpoint
`https://arxiv.org/e-print/<id>` (it streams the gzip source tarball directly).
"""
from __future__ import annotations

import re
import shutil
import unicodedata
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

from . import net

# Invisible/whitespace codepoints a paste from a rendered page or a chat widget
# can silently append to a filename (a trailing NBSP, zero-width space, BOM, or
# bidi mark), making Path.exists() fail on the first try and succeed on a clean
# retype — the "first not found, then found" symptom.
_INVISIBLE = "".join(chr(c) for c in (
    0x09, 0x0A, 0x0D, 0x20, 0xA0, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F,
    0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2060, 0xFEFF))


def _path_variants(arg: str):
    """Yield plausible on-disk spellings of a pasted local path, most-literal
    first: as-is, trimmed of invisible/whitespace junk, Unicode NFC/NFD
    normalized (macOS pastes decomposed accents; Linux disks are usually NFC),
    and percent-decoded (a copied URL fragment: %20 -> space, %c3%bc -> umlaut).
    Battle-proven stdlib only (unicodedata + urllib.parse.unquote)."""
    seen: set = set()

    def emit(s: str):
        if s and s not in seen:
            seen.add(s)
            return True
        return False

    bases = [arg, arg.strip().strip(_INVISIBLE)]
    for b in list(bases):
        if "%" in b:
            bases.append(unquote(b))
            bases.append(unquote(b).strip().strip(_INVISIBLE))
    out = []
    for b in bases:
        for form in (b, unicodedata.normalize("NFC", b),
                     unicodedata.normalize("NFD", b)):
            if emit(form):
                out.append(form)
    return out


def existing_local_path(arg: str) -> Optional[Path]:
    """Return the real Path for a pasted LOCAL path — trying invisible-char
    trimming, Unicode NFC/NFD normalization, and percent-decoding — or None when
    nothing on disk matches (never invents a file). URLs / bare ids yield None.
    This is what makes `pdfdrill <cmd> "<pasted name>"` robust to copy artifacts."""
    if is_url(arg):
        return None
    for cand in _path_variants(arg):
        try:
            p = Path(cand).expanduser()
        except (ValueError, OSError):
            continue
        if p.is_file():                      # a PDF/md input is a FILE, never a dir
            return p
    return None

# host substring (after stripping a leading www.) → source kind
KNOWN_HOSTS = {
    "arxiv.org": "arxiv",
    "export.arxiv.org": "arxiv",
}


def is_url(s: str) -> bool:
    return isinstance(s, str) and bool(re.match(r"https?://", s.strip(), re.I))


def host_of(s: str) -> str:
    return urlparse(s).netloc.lower()


def known_host(s: str) -> Optional[str]:
    """Return the source kind for a URL whose host is in KNOWN_HOSTS, else None."""
    if not is_url(s):
        return None
    host = host_of(s)
    host = host[4:] if host.startswith("www.") else host
    return KNOWN_HOSTS.get(host)


# ---------------------------------------------------------------------------
# arXiv (pure helpers)
# ---------------------------------------------------------------------------

# new-style id (1501.00001 / 2510.11170v2) or old-style (math/0309136, hep-th/9901001)
_ARXIV_NEW = r"\d{4}\.\d{4,5}(?:v\d+)?"
_ARXIV_OLD = r"[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?"
_ARXIV_ANY = re.compile(rf"(?:arxiv:)?({_ARXIV_NEW}|{_ARXIV_OLD})", re.I)


def parse_arxiv_id(s: str) -> Optional[str]:
    """Extract an arXiv id from any spelling: an abs/pdf/e-print URL, an
    `arXiv:..` token, or a bare id (new- or old-style). A trailing `.pdf` is
    dropped. Returns None when the string carries no arXiv id."""
    if not s:
        return None
    text = s.strip()
    # only treat a URL as arXiv when it is actually an arxiv host
    if is_url(text) and known_host(text) != "arxiv":
        return None
    text = re.sub(r"\.pdf$", "", text, flags=re.I)
    m = _ARXIV_ANY.search(text)
    if not m:
        return None
    return m.group(1)


_BARE_ARXIV = re.compile(rf"(?:arxiv:)?({_ARXIV_NEW}|{_ARXIV_OLD})$", re.I)


def bare_arxiv_id(s: str) -> Optional[str]:
    """The arXiv id IFF the WHOLE argument is a bare id (optionally `arXiv:`-
    prefixed, with a trailing `.pdf` allowed) — NOT a URL and NOT an id merely
    embedded in a path. So `2510.11170v2` resolves, but `data/2312.11532.pdf`
    (a real-looking local path) does not. This is the fix for the skill gotcha
    where `pdfdrill latex 2510.11170` failed with `Not found`."""
    if not s or is_url(s):
        return None
    text = re.sub(r"\.pdf$", "", s.strip(), flags=re.I)
    m = _BARE_ARXIV.fullmatch(text)
    return m.group(1) if m else None


def arxiv_urls(arxiv_id: str) -> dict[str, str]:
    """abs / pdf / e-print URLs for an arXiv id (version preserved if present)."""
    return {
        "abs": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf": f"https://arxiv.org/pdf/{arxiv_id}",
        "eprint": f"https://arxiv.org/e-print/{arxiv_id}",
    }


def _strip_tags(html: str) -> str:
    html = re.sub(r'<span class="descriptor">.*?</span>', " ", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def parse_arxiv_abs_html(html: str) -> dict:
    """Parse title / authors / abstract / primary category from an arXiv abs page.
    Pure string work (no bs4), so it is fully unit-tested offline."""
    out: dict = {"title": "", "authors": [], "abstract": "", "primary_category": "",
                 "subjects": ""}
    t = re.search(r'<h1 class="title[^"]*">(.*?)</h1>', html, re.S | re.I)
    if t:
        out["title"] = _strip_tags(t.group(1))
    a = re.search(r'<blockquote class="abstract[^"]*">(.*?)</blockquote>', html, re.S | re.I)
    if a:
        out["abstract"] = _strip_tags(a.group(1))
    au = re.search(r'<div class="authors">(.*?)</div>', html, re.S | re.I)
    if au:
        names = re.findall(r"<a[^>]*>(.*?)</a>", au.group(1), re.S | re.I)
        out["authors"] = [re.sub(r"\s+", " ", n).strip() for n in names]
    su = re.search(r'<td class="tablecell subjects">(.*?)</td>', html, re.S | re.I)
    if su:
        out["subjects"] = _strip_tags(su.group(1))
        ps = re.search(r'<span class="primary-subject">(.*?)</span>', su.group(1), re.S | re.I)
        primary = _strip_tags(ps.group(1)) if ps else out["subjects"]
        code = re.search(r"\(([a-zA-Z\-]+\.[A-Za-z]{2})\)", primary)
        out["primary_category"] = code.group(1) if code else ""
    return out


# ---------------------------------------------------------------------------
# Network routes (degrade cleanly via net.urlopen)
# ---------------------------------------------------------------------------

def fetch_arxiv_metadata(arxiv_id: str) -> dict:
    """Free metadata (title/authors/abstract/category) from the arXiv abs page."""
    url = arxiv_urls(arxiv_id)["abs"]
    with net.urlopen(url, host="arxiv.org") as r:
        html = r.read().decode("utf-8", "replace")
    meta = parse_arxiv_abs_html(html)
    meta["arxiv_id"] = arxiv_id
    return meta


def download(url: str, dest: Path) -> Path:
    """Stream a URL to `dest` (bounded RAM). Returns dest. Raises NetworkBlocked
    / HTTPError via net.urlopen on failure."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with net.urlopen(url, host=host_of(url)) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f, length=4 * 1024 * 1024)
    return dest


def download_arxiv_source(arxiv_id: str, dest_dir: Path) -> Path:
    """Download the arXiv e-print source tarball to `<dest_dir>/<id>.tgz`
    (the endpoint the abs-page download button hides). Idempotent."""
    safe = arxiv_id.replace("/", "_")
    dest = Path(dest_dir) / f"{safe}.tgz"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    return download(arxiv_urls(arxiv_id)["eprint"], dest)


def _safe_filename(url: str) -> str:
    # percent-decode first so "The%20C%2B%2B.pdf" → "The C++.pdf" → a readable,
    # filesystem-safe "The_C___.pdf" rather than "The_20C_2B_2B.pdf".
    name = Path(urlparse(unquote(url)).path).name or "download"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return re.sub(r"[^\w.\-]", "_", name)


def _place_download(base: Path, tmp: Path, digest: str, reg: dict) -> Path:
    """Move the freshly-downloaded `tmp` into place. The clean `<basename>.pdf`
    is used if free or already holding IDENTICAL content (dedup by content hash);
    a colliding URL with DIFFERENT content gets `<stem>-<hash8>.pdf` — so two
    papers sharing a basename never clobber. The registry supplies known hashes;
    a legacy file not in it is hashed once."""
    from . import download_registry as _dl

    def _content_hash(p: Path) -> str:
        h = _dl.hash_for_filename(reg, p.name)
        return h if h is not None else _dl.hash_file(p)[0]

    if not (base.exists() and base.stat().st_size > 0):
        tmp.replace(base)
        return base
    if _content_hash(base) == digest:                   # identical content already
        tmp.unlink()
        return base
    hashed = base.with_name(f"{base.stem}-{digest[:8]}{base.suffix}")
    if hashed.exists() and hashed.stat().st_size > 0 and _content_hash(hashed) == digest:
        tmp.unlink()
        return hashed
    tmp.replace(hashed)
    return hashed


def _doc_dest(root: Path, filename: str) -> Path:
    """Place a DOWNLOAD in its self-contained doc folder: `root/<stem>/<filename>`
    (the library layout — the PDF lives inside its own folder next to its
    artifacts). Creates the folder."""
    folder = root / Path(filename).stem
    folder.mkdir(parents=True, exist_ok=True)
    return folder / filename


def resolve_input(arg: str, dest_dir: Optional[Path] = None) -> dict:
    """Resolve a command argument to a local PDF path.

    Returns {"path": Path, "source": kind|None, "arxiv_id": id|None}. A local
    file passes through unchanged (no network, not moved). A known-host URL is
    downloaded once (cached) into its own self-contained doc folder:
    arXiv → `<library>/<id>/<id>.pdf`; any other http(s) URL →
    `<library>/<stem>/<file>`. Idempotent: an existing non-empty target is reused.
    """
    if dest_dir is None:
        from . import config as _cfg
        dest_dir = _cfg.library_root()      # config library_root, else download_dir
    dest_dir = Path(dest_dir)
    if not is_url(arg):
        # expand `~`/`~user` ($HOME shorthand) so `~/x.pdf` resolves like the
        # absolute path; harmless on a bare arXiv id (no leading ~).
        arg = str(Path(arg).expanduser())
        # a real local FILE always wins (even if it is named like an arXiv id) —
        # resolving paste artifacts (invisible chars / NFD accents / %-encoding).
        # MUST be a file, not a directory: the self-contained doc folder is named
        # after the bare id (`2509.26251v2/`), so `Path("2509.26251v2").exists()`
        # would match that FOLDER and hand `size` a directory to stat (the bogus
        # "0-page scan, needs_ocr" bug). is_file() lets the bare-id branch below
        # resolve to `<folder>/<id>.pdf` instead.
        local = Path(arg) if Path(arg).is_file() else existing_local_path(arg)
        if local is not None:
            return {"path": local, "source": None, "arxiv_id": None}
        # otherwise a BARE arXiv id is downloaded as arXiv (the skill gotcha fix)
        arxiv_id = bare_arxiv_id(arg)
        if arxiv_id:
            dest = _doc_dest(dest_dir, f"{arxiv_id.replace('/', '_')}.pdf")
            if not (dest.exists() and dest.stat().st_size > 0):
                download(arxiv_urls(arxiv_id)["pdf"], dest)
            return {"path": dest, "source": "arxiv", "arxiv_id": arxiv_id}
        # not a URL, not a local file, not a bare id → let the caller raise
        return {"path": Path(arg), "source": None, "arxiv_id": None}

    kind = known_host(arg)
    if kind == "arxiv":
        arxiv_id = parse_arxiv_id(arg)
        if not arxiv_id:
            raise ValueError(
                f"{arg!r} is an arXiv URL but carries no valid id "
                f"(expected e.g. 2604.17042 or math/0309136). Check the id.")
        dest = _doc_dest(dest_dir, f"{arxiv_id.replace('/', '_')}.pdf")
        if not (dest.exists() and dest.stat().st_size > 0):
            download(arxiv_urls(arxiv_id)["pdf"], dest)
        return {"path": dest, "source": "arxiv", "arxiv_id": arxiv_id}

    # generic http(s): one registry (pdfdrill-downloads.json) logs every download
    # by URL → filename + BLAKE3 content hash. A re-resolve is a registry lookup
    # (true cache by URL); same-basename papers from different URLs get distinct,
    # content-hash-suffixed files instead of clobbering (identical content dedups).
    from . import download_registry as _dl
    reg = _dl.load(dest_dir)
    hit = reg.get(arg)
    if hit:
        p = dest_dir / hit["filename"]
        if p.exists() and p.stat().st_size > 0:
            return {"path": p, "source": "url", "arxiv_id": None}
    base = _doc_dest(dest_dir, _safe_filename(arg))   # <library>/<stem>/<file>
    tmp = base.parent / f"{base.stem}.download-tmp{base.suffix}"
    download(arg, tmp)
    digest, algo = _dl.hash_file(tmp)
    final = _place_download(base, tmp, digest, reg)
    # registry filename is relative to the library root (e.g. "<stem>/<file>") so
    # the lookup `dest_dir / hit["filename"]` resolves inside the doc folder.
    _dl.record(dest_dir, arg, str(final.relative_to(dest_dir)), digest, algo,
               final.stat().st_size if final.exists() else 0)
    return {"path": final, "source": "url", "arxiv_id": None}
