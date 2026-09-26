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
    # viXra, added 805 after fourteen library folders turned out to be its
    # e-prints arriving as anonymous generic URLs. It is NOT arXiv with a
    # different name and three differences matter downstream, each stated at
    # the function that carries it: its ids collide with arXiv's pre-2015
    # shape, its PDF URL requires the version, and it has no LaTeX source at
    # all.
    "vixra.org": "vixra",
}

#: Which archives serve the LaTeX SOURCE of a paper, not just a rendering.
#: arXiv's e-print endpoint gives the author's .tex; viXra hosts only the PDF
#: its author uploaded. A route that assumes symmetry here fetches a 404 and
#: reports it as "no source found", which reads like a missing file rather than
#: an archive that never had one.
ARCHIVES_WITH_LATEX_SOURCE = frozenset({"arxiv"})


def is_url(s: str) -> bool:
    return isinstance(s, str) and bool(re.match(r"https?://", s.strip(), re.I))


def file_uri_to_path(s: str) -> Optional[str]:
    """A `file://` URI → its local filesystem path (RFC 8089), else None.

    A `file://` link IS a local file wearing a URI scheme — a browser / file
    manager hands it out with that prefix and percent-encoding (`A%20B.pdf`).
    Empty or `localhost` host is local (decoded, so downstream sees a plain
    path); a real remote host is NOT a local path and returns None. Anything not
    a file URI returns None so callers pass it through untouched."""
    from urllib.request import url2pathname
    if not isinstance(s, str):
        return None
    s = s.strip()
    if not s.lower().startswith("file:"):
        return None
    parts = urlparse(s)
    if parts.scheme.lower() != "file":
        return None
    if parts.netloc and parts.netloc.lower() != "localhost":
        return None
    return url2pathname(parts.path)


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
    # 806 — THE SAME GATE `bare_arxiv_id` HAS. It was missing here, and this is
    # the function `_augment_bibtex` falls back to when reading an id off a
    # FILENAME. A viXra e-print named `1702.0234.pdf` therefore resolved as a
    # pre-2015 arXiv id, arXiv zero-padded it, and the document was cited as
    # "Preliminary Design Study of the Hollow Electron Lens for LHC" —
    # a real paper, a different archive, and a bibliography that is simply
    # wrong. Found by the viXra tests, not by reading the code.
    if arxiv_id_shape_error(m.group(1)):
        return None
    return m.group(1)


_BARE_ARXIV = re.compile(rf"(?:arxiv:)?({_ARXIV_NEW}|{_ARXIV_OLD})$", re.I)


def arxiv_id_shape_error(s: str) -> Optional[str]:
    r"""Why this new-style arXiv id cannot be right, or None if it can.

    THE SCHEME CHANGED, AND ARXIV IS LENIENT ABOUT IT. Identifiers ran
    `YYMM.NNNN` from 0704 to 1412 and `YYMM.NNNNN` from 1501 on. A regex of
    `\d{4}\.\d{4,5}` accepts both for any month, so a TRUNCATED modern id
    passes — and arXiv's server does not refuse it, it ZERO-PADS it:

        asked for  2609.2497   -> served 2609.02497
                                  "RINSE: Robust Target-Time Normality …"
        wanted     2609.24972  -> "RRSI: Regularized Recursive Self-Improvement …"

    One dropped character, a different real paper, no error anywhere, and a
    folder whose name states an id its contents do not have. That is the worst
    shape a download failure can take, because every later command believes the
    name.

    Checked, not guessed: the digit count is a function of the date printed in
    the id itself.
    """
    if not s:
        return None
    text = re.sub(r"\.pdf$", "", s.strip(), flags=re.I)
    text = re.sub(r"^arxiv:", "", text, flags=re.I)
    m = re.fullmatch(r"(\d{4})\.(\d{3,6})(v\d+)?", text)
    if not m:
        return None                      # not new-style: nothing to say here
    yymm, num = m.group(1), m.group(2)
    mm = int(yymm[2:])
    if not (1 <= mm <= 12):
        return (f"{s!r} is not an arXiv id: {yymm} has month {yymm[2:]}, "
                f"and an id's first four digits are YYMM.")
    if int(yymm) < 704:
        return (f"{s!r} is not an arXiv id: the YYMM.NNNN scheme starts at "
                f"0704 (April 2007).")
    want = 4 if int(yymm) <= 1412 else 5
    if len(num) != want:
        era = ("up to 1412 ids have FOUR digits after the dot"
               if want == 4 else
               "from 1501 on ids have FIVE digits after the dot")
        msg = (f"{s!r} cannot be an arXiv id: {era}, and this has "
               f"{len(num)}. arXiv would not refuse it — it ZERO-PADS, and "
               f"serves a different paper.")
        # A FOUR-DIGIT ID AFTER 2015 IS PROBABLY NOT A TYPO. viXra numbers
        # every year `YYMM.NNNN`, which is arXiv's PRE-2015 shape, so the two
        # schemes collide for exactly these ids. 14 folders in this library are
        # viXra e-prints named correctly for their source — checked against
        # vixra.org, titles matching — and telling their owner to "check the
        # id" would be advice about the wrong archive.
        if want == 5 and len(num) == 4:
            msg += (" If it is a viXra id, this shape is CORRECT there and "
                    "wrong only for arXiv: pdfdrill has no viXra route, so "
                    "pass the URL (https://vixra.org/pdf/<id>.pdf) or a local "
                    "file instead of a bare id.")
        else:
            msg += " Check the id against its listing."
        return msg
    return None


def bare_arxiv_id(s: str) -> Optional[str]:
    """The arXiv id IFF the WHOLE argument is a bare id (optionally `arXiv:`-
    prefixed, with a trailing `.pdf` allowed) — NOT a URL and NOT an id merely
    embedded in a path. So `2510.11170v2` resolves, but `data/2312.11532.pdf`
    (a real-looking local path) does not. This is the fix for the skill gotcha
    where `pdfdrill latex 2510.11170` failed with `Not found`."""
    if not s or is_url(s):
        return None
    text = re.sub(r"\.pdf$", "", s.strip(), flags=re.I)
    if arxiv_id_shape_error(text):
        return None                      # malformed: refuse, never zero-pad
    m = _BARE_ARXIV.fullmatch(text)
    return m.group(1) if m else None


#: A viXra id is `YYMM.NNNN`, optionally versioned. That is arXiv's PRE-2015
#: shape, so the two collide for every id after 1412 — which is why a BARE id is
#: never read as viXra (see `parse_vixra_id`).
_VIXRA_ID = r"\d{4}\.\d{4}(?:v\d+)?"
_VIXRA_URL = re.compile(rf"vixra\.org/(?:abs|pdf)/({_VIXRA_ID})", re.I)


def parse_vixra_id(s: str) -> Optional[str]:
    """The viXra id from a viXra URL or an explicit `viXra:` token, else None.

    A URL OR AN EXPLICIT PREFIX, NEVER A BARE ID. `2505.0100` is a well-formed
    viXra id and an equally well-formed arXiv id of the pre-2015 era, and
    nothing in the string says which archive is meant. Guessing would swap one
    archive's paper for another's — the failure 804 exists to prevent — so a
    bare id stays unresolved and the caller is told to give a URL.
    """
    if not isinstance(s, str) or not s.strip():
        return None
    text = re.sub(r"\.pdf$", "", s.strip(), flags=re.I)
    m = _VIXRA_URL.search(text)
    if m:
        return m.group(1)
    m = re.fullmatch(rf"vixra:\s*({_VIXRA_ID})", text, re.I)
    return m.group(1) if m else None


def vixra_urls(vixra_id: str) -> dict[str, str]:
    """`abs` and `pdf` for a viXra id. There is no `eprint` key, deliberately.

    THE PDF URL REQUIRES THE VERSION. Measured: `/pdf/1702.0234.pdf` answers
    404 and `/pdf/1702.0234v1.pdf` answers 200. arXiv serves the unversioned
    form and viXra does not, so an id with no version has no PDF URL until the
    abs page names the current one — which is what `fetch_vixra_metadata`
    returns as `pdf_url`.
    """
    # The abs page is UNVERSIONED — it lists every version of the record — so a
    # versioned id keeps its version only for the PDF.
    bare = re.sub(r"v\d+$", "", vixra_id)
    out = {"abs": f"https://vixra.org/abs/{bare}"}
    if re.search(r"v\d+$", vixra_id):
        out["pdf"] = f"https://vixra.org/pdf/{vixra_id}.pdf"
    return out


def _vixra_category(html: str) -> str:
    """The subject from the breadcrumb, e.g. `Algebra`."""
    # `_strip_tags` removes markup and leaves ENTITIES: the breadcrumb reads
    # `viXra.org &gt; Algebra &gt; viXra:1702.0234`, so it has to be unescaped
    # before a `>` can be matched. The page title also contains `viXra.org` and
    # no `>`, which is why the pattern needs both separators.
    from html import unescape
    flat = re.sub(r"\s+", " ", unescape(_strip_tags(html)))
    m = re.search(r"viXra\.org\s*>\s*([^>]+?)\s*>", flat)
    return m.group(1).strip() if m else ""


def parse_vixra_abs_html(html: str) -> dict:
    """title / authors / abstract / category / pdf_url from a viXra abs page."""
    def one(pat: str, flags=re.S | re.I) -> str:
        m = re.search(pat, html, flags)
        return re.sub(r"\s+", " ", _strip_tags(m.group(1))).strip() if m else ""
    authors = [re.sub(r"\s+", " ", a).strip() for a in
               re.findall(r'href="/author/[^"]*"[^>]*>([^<]+)<', html, re.I)]
    pdf = re.search(r'href="(/pdf/[^"]+\.pdf)"', html, re.I)
    return {
        "title": one(r'<div id="flow">.*?<h2[^>]*>(.*?)</h2>'),
        "authors": authors,
        "abstract": one(r'<div id="abstract"[^>]*>(.*?)</div>'),
        # The category is in the BREADCRUMB (`viXra.org > Algebra >
        # viXra:1702.0234`), which carries tags between its parts — so it is
        # matched on the stripped text, not the markup.
        "category": _vixra_category(html),
        "pdf_url": f"https://vixra.org{pdf.group(1)}" if pdf else "",
    }


def fetch_vixra_metadata(vixra_id: str) -> dict:
    """Free metadata from the viXra abs page, including the versioned PDF URL
    that `vixra_urls` cannot know for an unversioned id."""
    with net.urlopen(vixra_urls(vixra_id)["abs"], host="vixra.org") as r:
        html = r.read().decode("utf-8", "replace")
    meta = parse_vixra_abs_html(html)
    meta["vixra_id"] = vixra_id
    return meta


def no_latex_source_reason(kind: str) -> Optional[str]:
    """Why this archive cannot supply LaTeX, or None if it can."""
    if not kind or kind in ARCHIVES_WITH_LATEX_SOURCE:
        return None
    if kind == "vixra":
        return ("viXra hosts only the PDF its author uploaded — it has no "
                "e-print endpoint and never had the .tex. The keyless math "
                "route for such a document is `visionocr`, not `latex`.")
    return f"{kind} is not known to serve LaTeX source."


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


class NoLatexSource(RuntimeError):
    """arXiv has no LaTeX source for this id — the e-print endpoint served the
    PDF itself (a PDF-only submission)."""


def looks_like_pdf_bytes(head: bytes) -> bool:
    """True when the payload is a PDF (magic `%PDF`, allowing leading junk)."""
    return b"%PDF" in (head or b"")[:1024]


def looks_like_source_archive(head: bytes) -> bool:
    """True for something that can plausibly be an arXiv e-print: a gzip/tar
    stream, or a bare (uncompressed) LaTeX file. Explicitly False for a PDF."""
    h = head or b""
    if looks_like_pdf_bytes(h):
        return False
    if h[:2] == b"\x1f\x8b":                      # gzip (.tar.gz / gzipped .tex)
        return True
    if h[257:262] == b"ustar":                    # plain tar
        return True
    # a bare .tex submission (arXiv serves it uncompressed for single files)
    probe = h[:2048].lstrip()
    return probe.startswith(b"\\") or probe.startswith(b"%")


#: The extensions an e-print can legitimately land under, newest lookup first.
#: `.gz` is here because arXiv serves a SINGLE-FILE submission as gzip(paper.tex)
#: — not gzip(tar(...)) — and 689 found seven lookups that would miss it.
EPRINT_SUFFIXES = (".tgz", ".tar.gz", ".gz", ".tar", ".tex")


def eprint_suffix_for(head: bytes, path: "Path | None" = None) -> str:
    r"""The extension a payload should wear, from its bytes.

    689 — `download_arxiv_source` wrote `<id>.tgz` UNCONDITIONALLY. The
    endpoint serves three different things and only one of them is a tarball:

        gzipped tar   multi-file submission          .tgz
        plain gzip    ONE .tex, gzip'd               .gz
        bare text     one uncompressed .tex          .tex

    0902.0431 is the middle case — `gzip compressed data, was "SpEcxp.tex"`,
    and `tarfile.is_tarfile` says no — so it sat on disk as `0902.0431.tgz`,
    which is not true. `latex_source.read_source` sniffs content and reads it
    correctly (its own comment at :308 says why that branch exists), so nothing
    broke; but the name was a lie, a reader was misled by it, and the seven
    places that match on the extension would not have found a correctly-named
    `.gz`.
    """
    h = head or b""
    if h[:2] == b"\x1f\x8b":
        # gzip. Is it a gzipped TAR, or a gzipped single file?
        if path is not None:
            try:
                import tarfile as _tf
                if _tf.is_tarfile(str(path)):
                    return ".tgz"
            except Exception:
                pass
        return ".gz"
    if h[257:262] == b"ustar":
        return ".tar"
    return ".tex"


def download_arxiv_source(arxiv_id: str, dest_dir: Path) -> Path:
    """Download the arXiv e-print source, named for WHAT IT IS. Idempotent.

    Not every arXiv submission HAS LaTeX: for a PDF-only submission the e-print
    endpoint serves the PDF itself. That used to be written straight to
    `<id>.tgz` — a PDF wearing a tarball name, which then failed to unpack far
    downstream with a confusing error. Sniff the payload and raise
    `NoLatexSource` instead, leaving no bogus tarball behind.

    689 — and the same endpoint serves a gzipped single `.tex` as often as a
    tarball, so the extension is now chosen by `eprint_suffix_for` rather than
    assumed. An e-print cached under any of `EPRINT_SUFFIXES` by an older build
    is returned as it stands: renaming a file a user may have referenced is not
    this function's business, and every consumer sniffs content anyway.
    """
    safe = arxiv_id.replace("/", "_")
    for suf in EPRINT_SUFFIXES:
        cached = Path(dest_dir) / f"{safe}{suf}"
        if cached.exists() and cached.stat().st_size > 0:
            # a file cached by an older build may itself be a mislabelled PDF
            if looks_like_pdf_bytes(cached.read_bytes()[:1024]):
                try:
                    cached.unlink()
                except OSError:
                    pass
            else:
                return cached
    dest = Path(dest_dir) / f"{safe}.download"
    out = download(arxiv_urls(arxiv_id)["eprint"], dest)
    try:
        head = Path(out).read_bytes()[:4096]
    except OSError:
        return out
    if not looks_like_source_archive(head):
        try:
            Path(out).unlink()
        except OSError:
            pass
        what = "the PDF itself" if looks_like_pdf_bytes(head) else "a non-archive payload"
        raise NoLatexSource(
            f"arXiv has no LaTeX source for {arxiv_id}: the e-print endpoint "
            f"served {what} (a PDF-only submission). Use the PDF routes "
            f"(`pdfdrill model` / `mathpix`) — there is no .tex to ingest.")
    # 689 — name it for what it is, now that the bytes are known.
    final = Path(dest_dir) / f"{safe}{eprint_suffix_for(head, Path(out))}"
    if Path(out) != final:
        try:
            Path(out).replace(final)
            return final
        except OSError:
            return Path(out)
    return final


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


def _download_into_doc_folder(url: str, dest: Path) -> None:
    """Download to `dest`, and leave NO empty folder behind if it fails.

    `_doc_dest` creates the doc folder before the bytes arrive, so a download
    that raised left `<library>/<id>/` empty — and an empty doc folder is worse
    than no folder at all: `pdf_in_folder` finds no PDF, the bare name stops
    resolving, and `add <id>` answers "Not found" for a document the user can
    see a directory for. Four of them were sitting in the library.
    """
    made = dest.parent
    try:
        download(url, dest)
    except BaseException:
        try:
            if made.is_dir() and not any(made.iterdir()):
                made.rmdir()
        except OSError:
            pass
        raise


def adopt_into_doc_folder(pdf: Path, root: Path) -> Path:
    """Move a loose PDF in the library ROOT into its own doc folder.

    The layout the user asks for — one folder per document, everything under
    it — is what a DOWNLOAD already gets. A PDF copied into the library by
    hand did not: it stayed at the root and `blob_dir_for` fell back to the
    legacy layout, so one document became four entries beside each other
    (`x.pdf`, `x.pdf.drill/`, `x.pdf.drill.json`, `x.profile.json`). Told to
    drill a list of papers, an agent produces exactly that, and then has to
    tidy up after itself.

    Only in the library root, and only while the document has NO artifacts
    yet: then the move is a rename of a single file and there is no reference
    to break. Anywhere else — someone's Downloads folder, a working
    directory — nothing is ever moved.
    """
    if pdf.parent.resolve() != Path(root).resolve():
        return pdf                                  # not ours to reorganise
    if pdf.parent.name == pdf.stem:
        return pdf                                  # already self-contained
    # ANY sibling already named after this document means work exists that the
    # move would separate from it — not only `.drill`/`.drill.json` but
    # `<stem>.lines.json`, `<stem>.md`, `<stem>.tex.zip`, `<stem>.profile.json`.
    # Moving the PDF away from its own lines.json would silently re-acquire it,
    # paid route included. Every one of the five loose PDFs in the library has
    # such a sibling, so adoption touches genuinely new files only.
    prefix = f"{pdf.stem}."
    try:
        for sib in pdf.parent.iterdir():
            if sib.name != pdf.name and sib.name.startswith(prefix):
                return pdf                          # already worked on
    except OSError:
        return pdf
    folder = pdf.parent / pdf.stem
    target = folder / pdf.name
    if target.exists():
        return pdf
    try:
        folder.mkdir(parents=True, exist_ok=True)
        pdf.replace(target)
    except OSError:
        return pdf
    return target


def pdf_in_folder(folder: Path) -> "Path | None":
    """The PDF inside a self-contained doc FOLDER: `<folder>/<folder-name>.pdf`
    preferred (the library layout), else the sole `*.pdf` if there is exactly one.
    None if `folder` isn't a directory or has no unambiguous PDF. This is what
    lets you REOPEN a drilled doc by its folder — `pdfdrill md <stem>/` (or the
    bare `<stem>`) instead of the full `<stem>/<stem>.pdf`."""
    try:
        if not folder.is_dir():
            return None
    except OSError:
        return None
    folder = folder.absolute()                    # a relative arg → absolute path
    named = folder / f"{folder.name}.pdf"
    if named.is_file():
        return named
    pdfs = sorted(folder.glob("*.pdf"))
    return pdfs[0] if len(pdfs) == 1 else None


def library_pdf_for(name: str, root: Path) -> "Path | None":
    """The library document a BARE NAME means, or None.

    The self-contained layout names the folder after the document's STEM —
    `<library>/1001850/1001850.pdf` — and a user reading that folder types the
    thing they can see, which is the file: `add 1001850.pdf`. That carried an
    extension the folder does not have, so the folder lookup missed, nothing
    else matched, and the answer was "Not found" for a document sitting right
    there. `add Zwiebeln` worked and `add Zwiebeln.pdf` did not, which is not a
    distinction anyone can be expected to hold.

    Tried in order, most specific first: the folder named exactly as typed, the
    folder named by the stem, then a loose PDF at the library root (the
    pre-adoption layout, and anything dropped in by hand).
    """
    try:
        root = Path(root)
        stem = Path(name).stem
        for folder in (root / name, root / stem):
            hit = pdf_in_folder(folder)
            if hit is not None:
                return hit
        for cand in (root / name, root / f"{stem}.pdf"):
            if cand.is_file():
                return cand
    except OSError:
        return None
    return None


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
    # A file:// URI is a local file — decode it to a path so the local branch
    # below handles it (no download, not moved), like any other local path.
    _file = file_uri_to_path(arg)
    if _file is not None:
        arg = _file
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
            # NOT adopted here. `resolve_input`'s contract is that a local file
            # passes through unchanged — three tests pin it, and callers that
            # only want a path resolved must not have a file moved under them.
            # The CLI adopts, once, in `_probe_on_acquire`.
            return {"path": local, "source": None, "arxiv_id": None}
        # REOPEN by FOLDER: a directory path (`<stem>/`, or `<library>/<stem>/`) →
        # the PDF inside it. This is how you re-open an already-drilled doc in the
        # self-contained layout without typing the full `<stem>/<stem>.pdf`.
        folder = pdf_in_folder(Path(arg))
        if folder is None:
            # a BARE name matching a library doc — by folder, by STEM (the name
            # the layout uses), or as a loose file at the root — BEFORE treating
            # the name as an arXiv id to re-download.
            folder = library_pdf_for(arg, dest_dir)
        if folder is not None:
            return {"path": folder, "source": None,
                    "arxiv_id": bare_arxiv_id(folder.stem)}
        # otherwise a BARE arXiv id is downloaded as arXiv (the skill gotcha fix)
        arxiv_id = bare_arxiv_id(arg)
        if arxiv_id:
            dest = _doc_dest(dest_dir, f"{arxiv_id.replace('/', '_')}.pdf")
            if not (dest.exists() and dest.stat().st_size > 0):
                _download_into_doc_folder(arxiv_urls(arxiv_id)["pdf"], dest)
            return {"path": dest, "source": "arxiv", "arxiv_id": arxiv_id}
        # An EMPTY doc folder is the remains of a download that failed. Saying
        # "Not found" about a name the user can see a directory for is the
        # least useful true answer available; name the folder instead, so the
        # next move is obvious.
        stale = dest_dir / arg
        try:
            if stale.is_dir() and not any(stale.iterdir()):
                raise ValueError(
                    f"{arg!r} has an EMPTY doc folder at {stale} — a download "
                    f"that never finished. Re-add it by URL, or remove the "
                    f"folder and try the id again.")
        except OSError:
            pass
        # not a URL, not a local file, not a bare id → let the caller raise
        return {"path": Path(arg), "source": None, "arxiv_id": None}

    kind = known_host(arg)
    if kind == "vixra":
        vid = parse_vixra_id(arg)
        if not vid:
            raise ValueError(
                f"{arg!r} is a viXra URL but carries no id (expected e.g. "
                f"vixra.org/abs/1702.0234 or vixra.org/pdf/1702.0234v1.pdf).")
        # The abs page is the only place the CURRENT version is written, and the
        # PDF URL needs it: `/pdf/1702.0234.pdf` is a 404. So an unversioned id
        # costs one metadata request before the download; a versioned one does
        # not need it.
        pdf_url = vixra_urls(vid).get("pdf")
        if not pdf_url:
            pdf_url = fetch_vixra_metadata(vid).get("pdf_url") or ""
            if not pdf_url:
                raise ValueError(
                    f"viXra {vid} has no PDF link on its abs page.")
        dest = _doc_dest(dest_dir, f"{re.sub(r'[^0-9.v]', '_', vid)}.pdf")
        if not (dest.exists() and dest.stat().st_size > 0):
            _download_into_doc_folder(pdf_url, dest)
        return {"path": dest, "source": "vixra", "arxiv_id": None,
                "vixra_id": vid}
    if kind == "arxiv":
        arxiv_id = parse_arxiv_id(arg)
        if not arxiv_id:
            raise ValueError(
                f"{arg!r} is an arXiv URL but carries no valid id "
                f"(expected e.g. 2604.17042 or math/0309136). Check the id.")
        dest = _doc_dest(dest_dir, f"{arxiv_id.replace('/', '_')}.pdf")
        if not (dest.exists() and dest.stat().st_size > 0):
            _download_into_doc_folder(arxiv_urls(arxiv_id)["pdf"], dest)
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
    _download_into_doc_folder(arg, tmp)
    digest, algo = _dl.hash_file(tmp)
    final = _place_download(base, tmp, digest, reg)
    # registry filename is relative to the library root (e.g. "<stem>/<file>") so
    # the lookup `dest_dir / hit["filename"]` resolves inside the doc folder.
    _dl.record(dest_dir, arg, str(final.relative_to(dest_dir)), digest, algo,
               final.stat().st_size if final.exists() else 0)
    return {"path": final, "source": "url", "arxiv_id": None}
