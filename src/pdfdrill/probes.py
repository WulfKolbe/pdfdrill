"""The four cheap probes, run unconditionally at acquisition.

Measured on a 110-page A4 handbook: pdfinfo 11 ms, pdffonts 71 ms,
`pdfimages -list` 198 ms, pdftotext 212 ms — under half a second for all four,
over the WHOLE document. That is
cheaper than deciding whether to run them, so they are not behind a user
request and every later consumer reads the sidecar instead of re-running.

pdffonts is the fourth because `size` — the most-run command — needs the font
count to decide the text layer, and `fonts`/`fonts_layer` need the listing.

That half second is a 110-PAGE fact. Across the real corpus (6634 PDFs)
pdftotext and `pdfimages -list` each cost about 2 ms per page and pdffonts
about 1 ms per page (9.5 s on the 11232-page book), so on the largest document
(1511.08771, 11232 pages) the pair costs 80 SECONDS and produces 36 MB of text
and 899k image rows. pdfinfo does not scale that way — 30 ms on the same file —
and it reports the page count, so it runs first and decides. Above
PROBE_PAGE_LIMIT pages the three linear probes are DEFERRED, which is recorded
and is distinct from both "failed" and "never asked".

`pdfimages -list` is NOT superseded by the pdfminer route. They answer
different questions at different costs: the listing is one subprocess over the
whole document; pdfminer gives page-space bboxes and resolvable SMasks but
parses every page. Cheap probe always, pdfminer enrichment on demand.

`pdftotext` already separates pages with a form feed, so page-attributed text
costs nothing extra — one split of output we are already paying for, available
before any model exists.

NOT included, deliberately: `pdftotext -bbox-layout`. It is a second cheap
geometry source (274 ms here) and a genuine cross-check rather than a
duplicate, but it emits 3.1 MB of XHTML for this document — 15x the plain text
— and a sidecar is read on every command. On demand, not unconditional.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

FORM_FEED = "\f"

PROBE_VERSION = 3

# ~2 ms/page each for pdftotext and `pdfimages -list` and ~1 ms/page for
# pdffonts, so this cap is a budget of a bit over a second of probing. Above it
# they are deferred, not skipped.
PROBE_PAGE_LIMIT = int(os.environ.get("PDFDRILL_PROBE_PAGE_LIMIT") or 250)

# Bulk probe output lives BESIDE the sidecar, not in it: the sidecar is read by
# every command, and 36 MB of page text there would cost more than the probe
# saves. Same argument that keeps `pdftotext -bbox-layout` out of the set.
PAGE_TEXT_FILE = "probe-page-text.json"
IMAGES_LIST_FILE = "probe-pdfimages-list.txt"
FONTS_LIST_FILE = "probe-pdffonts.txt"


def split_pages(text: str) -> list[str]:
    """`pdftotext` output -> one entry per page.

    The form feed TERMINATES each page rather than separating pages, so a
    document ending in one yields a trailing empty string that is not a page.
    Dropping only that final artefact keeps a genuinely blank interior page —
    which is real, and which the duplex/blank-side logic elsewhere depends on.
    """
    if text is None:
        return []
    parts = text.split(FORM_FEED)
    if parts and parts[-1] == "":
        parts.pop()
    return parts


def parse_pdfinfo(text: str) -> dict[str, str]:
    """`Key: value` lines. Values may contain colons; keys may not."""
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        m = re.match(r"^([A-Za-z][A-Za-z0-9 ]*?):\s*(.*)$", line)
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def _run(cmd: list[str], timeout: float = 120.0) -> Optional[str]:
    """stdout, or None when the tool is absent or fails. A probe never raises:
    it runs unconditionally, so a missing poppler must not break acquisition."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def probe_document(pdf: Path, page_limit: "int | None" = -1) -> dict[str, Any]:
    """Run the probes. Every key is present; a failed probe is None, not absent
    — "we asked and got nothing" and "we never asked" are different, and only
    the second should make a later consumer run the tool itself.

    `page_limit=None` probes in full whatever the size (a caller who wants the
    text of a 2000-page book and is willing to wait); the default reads
    PROBE_PAGE_LIMIT.
    """
    pdf = Path(pdf)
    limit = PROBE_PAGE_LIMIT if page_limit == -1 else page_limit
    info_raw = _run(["pdfinfo", str(pdf)])
    fields = parse_pdfinfo(info_raw) if info_raw is not None else None

    pages = None
    if fields:
        try:
            pages = int(str(fields.get("Pages", "")).strip())
        except (TypeError, ValueError):
            pages = None

    deferred: list[str] = []
    if limit is not None and pages is not None and pages > limit:
        deferred = ["page_text", "pdfimages_list", "pdffonts"]
        images_raw = None
        text_raw = None
        fonts_raw = None
    else:
        fonts_raw = _run(["pdffonts", str(pdf)])
        images_raw = _run(["pdfimages", "-list", str(pdf)])
        text_raw = _run(["pdftotext", str(pdf), "-"])
    pages_text = split_pages(text_raw) if text_raw is not None else None
    return {
        "pdfinfo": fields,
        "pdfimages_list_raw": images_raw,
        "pdffonts_raw": fonts_raw,
        "page_text": pages_text,
        "page_count_text": len(pages_text) if pages_text is not None else None,
        "deferred": deferred,
        "probe_version": PROBE_VERSION,
    }


def is_probed(sc: Any) -> bool:
    """Has this document been probed already? Absence of the record, not
    emptiness of a result — a document with no images is probed and has none."""
    try:
        return bool(sc.get_evidence("probe_version"))
    except Exception:
        return False


def _blob(sc: Any, name: str) -> Optional[Path]:
    """Path beside the sidecar for one bulk artefact, or None if unavailable."""
    d = getattr(sc, "blob_dir", None)
    if d is None:
        return None
    try:
        d = Path(d)
        d.mkdir(parents=True, exist_ok=True)
        return d / name
    except Exception:                       # noqa: BLE001
        return None


def store(sc: Any, probe: dict) -> None:
    """Persist the probe. Counts and fields go in the sidecar; the two bulk
    artefacts go in files beside it (see PAGE_TEXT_FILE) so the always-read
    sidecar does not grow with the document."""
    sc.set_evidence("probe_version", probe.get("probe_version", PROBE_VERSION))
    if probe.get("deferred"):
        sc.set_evidence("probe_deferred", list(probe["deferred"]))
    if probe.get("pdfinfo") is not None:
        sc.set_evidence("pdfinfo_fields", probe["pdfinfo"])

    if probe.get("page_text") is not None:
        sc.set_evidence("page_count_text",
                        probe.get("page_count_text") or len(probe["page_text"]))
        f = _blob(sc, PAGE_TEXT_FILE)
        if f is not None:
            try:
                f.write_text(json.dumps(probe["page_text"]), encoding="utf-8")
            except OSError:
                pass

    if probe.get("pdffonts_raw") is not None:
        raw = probe["pdffonts_raw"]
        rows = raw.strip().splitlines()
        sc.set_evidence("font_count", max(0, len(rows) - 2))    # two header rows
        f = _blob(sc, FONTS_LIST_FILE)
        if f is not None:
            try:
                f.write_text(raw, encoding="utf-8")
            except OSError:
                pass

    if probe.get("pdfimages_list_raw") is not None:
        raw = probe["pdfimages_list_raw"]
        rows = raw.strip().splitlines()
        sc.set_evidence("image_count", max(0, len(rows) - 2))   # two header rows
        f = _blob(sc, IMAGES_LIST_FILE)
        if f is not None:
            try:
                f.write_text(raw, encoding="utf-8")
            except OSError:
                pass


def ensure(pdf: Path, sc: Any) -> bool:
    """Probe unless already probed. True when this call did the work.

    Acquisition calls this; a consumer that finds an unprobed sidecar (an older
    document, or one acquired before this existed) can call it too rather than
    shelling out itself.
    """
    if is_probed(sc):
        return False
    store(sc, probe_document(pdf))
    try:
        sc.save()
    except Exception:                       # noqa: BLE001
        pass
    return True


# --------------------------------------------------------------- consumer reads
# Each takes only the sidecar: there is deliberately no path back to a
# subprocess from here, so "consumer re-ran the tool" cannot happen by accident.

def pdfinfo_fields(sc: Any) -> Optional[dict]:
    try:
        v = sc.get_evidence("pdfinfo_fields")
    except Exception:                       # noqa: BLE001
        return None
    return v if isinstance(v, dict) else None


def page_count(sc: Any) -> Optional[int]:
    """Pages per pdfinfo. None when unprobed, unreadable, or non-numeric — a
    guess here would silently truncate a page range."""
    f = pdfinfo_fields(sc)
    if not f:
        return None
    try:
        return int(str(f.get("Pages", "")).strip())
    except (TypeError, ValueError):
        return None


def producer(sc: Any) -> Optional[str]:
    f = pdfinfo_fields(sc)
    return None if f is None else f.get("Producer", "")


def image_count(sc: Any) -> Optional[int]:
    """Embedded raster images, counted from `pdfimages -list` at probe time.

    None means we have no listing (unprobed, deferred, or pdfimages absent);
    0 means we have one and it is empty. The caller that used -1 for both could
    not tell "no images" from "no pdfimages".
    """
    try:
        v = sc.get_evidence("image_count")
    except Exception:                       # noqa: BLE001
        return None
    return v if isinstance(v, int) else None


def font_count(sc: Any) -> Optional[int]:
    """Distinct fonts per pdffonts. None when unprobed or deferred; 0 when the
    listing is empty — a scan, which is exactly what the caller wants to know."""
    try:
        v = sc.get_evidence("font_count")
    except Exception:                       # noqa: BLE001
        return None
    return v if isinstance(v, int) else None


def pdffonts_list(sc: Any) -> Optional[str]:
    """The stored `pdffonts` output, loaded from beside the sidecar."""
    return _read_blob(sc, FONTS_LIST_FILE)


def pdfimages_list(sc: Any) -> Optional[str]:
    """The stored `pdfimages -list` output, loaded from beside the sidecar."""
    return _read_blob(sc, IMAGES_LIST_FILE)


def _read_blob(sc: Any, name: str) -> Optional[str]:
    f = _blob(sc, name)
    if f is None or not f.exists():
        return None
    try:
        return f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def page_texts(sc: Any) -> Optional[list]:
    """All page text, loaded on demand — never in the sidecar."""
    f = _blob(sc, PAGE_TEXT_FILE)
    if f is None or not f.exists():
        return None
    try:
        v = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return v if isinstance(v, list) else None


def page_text(sc: Any, page: int) -> Optional[str]:
    """Text of one 1-based page from the stored probe, without touching the PDF."""
    pages = page_texts(sc)
    if pages is None or not (1 <= page <= len(pages)):
        return None
    return pages[page - 1]
