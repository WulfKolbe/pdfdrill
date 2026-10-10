"""898 — a volume is an archive, and its papers are its entries.

A proceedings volume, an edited book or a journal issue is one PDF holding
several independent works. Reading all of it to reach a few of them is the
whole cost: the four ICDAR 2026 volumes are 2,663 pages, and the six papers
whose titles name mathematics are 106 of them (4.0%).

So this lists the members first, like `unzip -l`, and hands one on like
`unzip archive member`. The analogy holds further than it looks: the
provenance a member needs — (volume, PDF pages) — IS its path inside the
archive, and the pages belonging to no member (front matter, part dividers,
the author index) are the archive's directories.

WHERE THE ANALOGY BREAKS, and this is what the design has to answer: a zip's
central directory is authoritative and self-contained. A PDF has no such
record, so the listing is a JOIN over several sources and must name which
source gave each field. Measured on all four ICDAR 2026 volumes:

  * `pdftotext` + Springer's chapter-opener footer — every member's own first
    page prints `https://doi.org/10.1007/<isbn>_<n>` and, on the same line,
    `pp. <first>-<last>` of the PRINTED pagination. 148 of 148 members found;
    their printed ranges agree with the publisher's Crossref deposit on 148 of
    148, with 0 differences and 0 absent. So the member's identity and its
    length come from the document itself and Crossref is a CHECK, not a
    dependency — which is what an independent truth source has to be.
  * `pdfminer`'s outline — `chapter.N` destinations give each member's exact
    title, 148 of 148.

THE TRAP THIS AVOIDS. A member's last PDF page is NOT the next member's first
minus one. Springer prints a part-divider page before each topical section and
strips its blank verso, so divider pages belong to no member and the
printed-to-PDF offset is piecewise: +19 throughout volumes II and III, but TEN
distinct offsets in volume I and two in volume IV. Computing the end from the
outline alone reported 14 of 148 members as disagreeing with Crossref; every
one of those was an artefact of that rule, and the publisher's metadata was
right each time. The length therefore comes from the printed range, and the
result is verified against the printed folio on the computed last page — 148
of 148 agree.

A boundary no source establishes is ABSENT, not guessed: a volume whose pages
carry no opener footer yields no members, and says so.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

#: Springer's chapter-opener footer, printed on the FIRST page of every member.
#: `_\s*` because a line-break artefact put a space between the underscore and
#: the chapter number on 978-3-032-36039-7_28 — one member in 148, and without
#: the tolerance that volume reported 40 members instead of 41.
_OPENER = re.compile(r"https://doi\.org/(10\.\d{4,9}/([\w.-]+?)_\s*(\d+))")

#: `pp. 611-628` on that same footer line — the PRINTED pagination, which is
#: what the publisher deposits and what a citation names.
_RANGE = re.compile(r"\bpp\.\s*(\d+)\s*[–—-]\s*(\d+)")

#: a running head's own page number: a short numeric line near the page top
_FOLIO = re.compile(r"^\d{1,4}$")

LISTING_SUFFIX = ".members.json"


class VolumeError(Exception):
    """The volume cannot be listed or a member cannot be handed on."""


def listing_path(pdf: Path) -> Path:
    name = pdf.name
    stem = name[:-4] if name.lower().endswith(".pdf") else name
    return pdf.parent / f"{stem}{LISTING_SUFFIX}"


def page_texts(pdf: Path) -> list[str]:
    """Each page's text, in order. One `pdftotext` for the whole document:
    measured at 2.7 s for 727 pages / 86 MB, where per-page calls would pay
    the open cost 727 times."""
    try:
        out = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True,
                             text=True, errors="replace")
    except OSError as e:                    # noqa: PERF203
        raise VolumeError(f"pdftotext is not available: {e}") from e
    if out.returncode != 0:
        raise VolumeError(f"pdftotext failed on {pdf.name}: "
                          f"{(out.stderr or '').strip()[:200]}")
    pages = out.stdout.split("\f")
    # pdftotext ends with a trailing form feed, so the last split is empty
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def folio_of(text: str) -> "int | None":
    """The printed page number in a page's running head, or None.

    The first THREE lines are inspected, not the first: a verso page puts the
    number first, a recto page puts the running-head title first and the number
    second. Reading only the first line found the folio on 26 of 40 members and
    looked like a 14-member mismatch.
    """
    for line in [l.strip() for l in text.strip().splitlines()[:3]]:
        if _FOLIO.fullmatch(line):
            return int(line)
    return None


def _openers(pages: list[str]) -> dict:
    """{(id-stem, member number): (pdf page, printed first, printed last)}.

    The FIRST page carrying a member's opener footer wins: the same DOI appears
    again in sibling papers' reference lists, which is why a bare DOI search
    found 71 members in a 40-member volume.
    """
    found: dict = {}
    for i, text in enumerate(pages, 1):
        for _doi, stem, num in _OPENER.findall(text):
            key = (stem, int(num))
            if key in found:
                continue
            rng = _RANGE.search(text)
            doi = re.sub(r"_\s*", "_", _doi)      # the line-break artefact
            found[key] = ((i, int(rng.group(1)), int(rng.group(2)), doi)
                          if rng else (i, None, None, doi))
    return found


def _dominant_stem(found: dict) -> "str | None":
    """The identifier stem that opens the most members — the volume's own.

    A volume's pages name sibling volumes too (a reference to another part of
    the same proceedings). The volume is the one that opens chapters here.
    """
    if not found:
        return None
    count: dict = {}
    for stem, _n in found:
        count[stem] = count.get(stem, 0) + 1
    return max(count, key=lambda s: count[s])


def outline_titles(pdf: Path) -> dict:
    """{member number: exact title} from the PDF outline's `chapter.N`
    destinations. `{}` when the document has no outline — the titles are then
    absent rather than read off the page, because a title lifted from a page
    image is a reading and this listing is a join."""
    try:
        from pdfminer.pdfparser import PDFParser
        from pdfminer.pdfdocument import PDFDocument
    except ImportError:                     # pragma: no cover
        return {}
    titles: dict = {}
    try:
        with open(pdf, "rb") as fh:
            doc = PDFDocument(PDFParser(fh))
            for _level, title, dest, action, _se in doc.get_outlines():
                raw = dest
                if raw is None and action is not None:
                    try:
                        raw = action.resolve().get("D")
                    except Exception:       # noqa: BLE001
                        raw = None
                s = raw.decode("latin-1", "replace") if isinstance(raw, bytes) \
                    else str(raw)
                m = re.fullmatch(r"chapter\.(\d+)", s)
                if m and title:
                    titles.setdefault(int(m.group(1)), str(title).strip())
    except Exception:                       # noqa: BLE001
        return {}                           # no outline is not a failure
    return titles


def build(pdf: Path) -> dict:
    """The archive listing: members, the pages belonging to none, and the
    source of every field."""
    pages = page_texts(pdf)
    found = _openers(pages)
    stem = _dominant_stem(found)
    titles = outline_titles(pdf)
    members = []
    for (s, num) in sorted((k for k in found if k[0] == stem),
                           key=lambda k: k[1]):
        first, pf, pl, doi = found[(s, num)]
        last = first + (pl - pf) if pf is not None else None
        rec = {
            "index": len(members) + 1,
            "member": num,
            "doi": doi,
            "title": titles.get(num),
            "title_source": "pdf outline chapter.%d" % num if num in titles
                            else None,
            "pdf_first_page": first,
            "pdf_first_page_source": "chapter-opener footer on that page",
            "pdf_last_page": last,
            "pdf_last_page_source": ("printed range on the opener footer"
                                     if last else None),
            "pdf_pages": (last - first + 1) if last else None,
            "printed_first_page": pf,
            "printed_last_page": pl,
            "printed_source": "chapter-opener footer on the member's own "
                              "first page" if pf is not None else None,
        }
        if last is not None and last <= len(pages):
            f = folio_of(pages[last - 1])
            rec["folio_on_last_page"] = f
            rec["folio_agrees"] = (f == pl)
        else:
            rec["folio_on_last_page"] = None
            rec["folio_agrees"] = None
        members.append(rec)
    inside = set()
    for rec in members:
        if rec["pdf_last_page"]:
            inside |= set(range(rec["pdf_first_page"], rec["pdf_last_page"] + 1))
    body_from = min((r["pdf_first_page"] for r in members), default=None)
    orphans = []
    if body_from is not None:
        for p in range(body_from, len(pages) + 1):
            if p in inside:
                continue
            lines = [l.strip() for l in pages[p - 1].strip().splitlines()
                     if l.strip()]
            orphans.append({"page": p,
                            "first_line": lines[0][:80] if lines else ""})
    return {
        "volume": {
            "pdf": str(pdf),
            "pdf_pages": len(pages),
            "identifier_stem": stem,
            "members": len(members),
            "front_matter_pages": (body_from - 1) if body_from else len(pages),
            "orphan_pages_after_body": len(orphans),
            "accounted": ((body_from - 1) if body_from else 0)
                         + len(inside) + len(orphans) == len(pages),
        },
        "members": members,
        "orphans": orphans,
        "sources": {
            "member_identity_and_length":
                "the chapter-opener footer printed on each member's own first "
                "page (https://doi.org/<doi> ... pp. <first>-<last>)",
            "title": "the PDF outline's chapter.N destinations (pdfminer)",
            "verification":
                "the printed folio read from the computed last page",
            "not_used":
                "the next member's first page minus one — Springer part "
                "dividers belong to no member and their blank versos are "
                "stripped, so that rule over-counts (14 of 148 on ICDAR 2026)",
            "external_check":
                "the publisher's chapter deposit at api.crossref.org "
                "(filter=isbn:) — never fetched here; the listing is complete "
                "without it",
        },
    }


def write_listing(pdf: Path, data: dict) -> Path:
    p = listing_path(pdf)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(p)
    return p


def read_listing(pdf: Path) -> "dict | None":
    p = listing_path(pdf)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def select(data: dict, match: str) -> list:
    """The members whose title matches `match` (a case-insensitive regex).

    A title match is a CANDIDATE LIST, never a judgement of relevance — on
    ICDAR 2026 a keyword match on math, formula, table and layout gave 42
    titles, most of them about handwriting. The caller decides.
    """
    try:
        rx = re.compile(match, re.I)
    except re.error as e:
        raise VolumeError(f"--match {match!r} is not a regular expression: {e}") \
            from e
    return [m for m in data.get("members") or []
            if m.get("title") and rx.search(m["title"])]


def slug(title: str, words: int = 5) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return "-".join([w for w in s.split("-") if w][:words])


def bibkey_for(data: dict, member: dict, prefix: str = "") -> str:
    stem = (data["volume"].get("identifier_stem") or "volume").strip("-_.")
    base = prefix or stem
    return f"{base}-m{member['member']:02d}-{slug(member.get('title') or '')}".strip("-")


def unpack(pdf: Path, data: dict, member: dict, out_dir: Path,
           prefix: str = "") -> dict:
    """Write one member as its own document folder, and record where it came
    from.

    The cut is `pikepdf` (a qpdf binding): measured on an 18-page member of an
    86 MB volume, pikepdf gives 2.6 MB in 0.2 s, the `qpdf` CLI 5.2 MB in
    1.8 s, and `pdfseparate` + `pdfunite` 101 MB in 75 s — poppler carries the
    volume's whole shared resource tree into every page.

    The member's own title and DOI are written into its metadata. Without
    that it inherits the VOLUME's `/Info /Title`, and all 148 members of a
    proceedings volume are named "Document Analysis and Recognition – ICDAR
    2026" — one name for 148 documents, in a tool whose titles become bibkeys.
    """
    try:
        import pikepdf
    except ImportError as e:                # pragma: no cover
        raise VolumeError(
            "unpacking a member needs pikepdf (a qpdf binding): "
            "`pip install pikepdf`. Listing the members needs nothing extra."
        ) from e
    first, last = member.get("pdf_first_page"), member.get("pdf_last_page")
    if not first or not last:
        raise VolumeError(
            f"member {member.get('member')} has no established page range — "
            f"no source gave its length, so it is absent, not guessed")
    key = bibkey_for(data, member, prefix)
    folder = out_dir / key
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{key}.pdf"
    with pikepdf.open(str(pdf)) as src:
        if last > len(src.pages):
            raise VolumeError(
                f"member {member['member']} ends at page {last} but the "
                f"volume has {len(src.pages)}")
        out = pikepdf.Pdf.new()
        for i in range(first - 1, last):
            out.pages.append(src.pages[i])
        title = member.get("title") or key
        with out.open_metadata() as md:
            md["dc:title"] = title
        out.docinfo["/Title"] = title
        if member.get("doi"):
            out.docinfo["/Subject"] = (
                f"{member['doi']} — from {Path(pdf).name}, printed pp. "
                f"{member.get('printed_first_page')}-"
                f"{member.get('printed_last_page')}")
        out.save(str(target))
    rec = dict(member)
    rec.update({
        "bibkey": key,
        "pdf": str(target),
        "volume_pdf": str(pdf),
        "volume_pdf_pages": data["volume"]["pdf_pages"],
        "volume_identifier_stem": data["volume"].get("identifier_stem"),
        "unpacked_by": "pikepdf page copy",
    })
    (folder / "volume-provenance.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    return rec


# --------------------------------------------------------------- the roll-up
#: `members` says WHICH works a volume holds; `profile` says what is on each
#: PAGE. Neither answers the question that decides where money goes — which of
#: these 148 papers carries display mathematics — and the answer is a join, not
#: a reading: the page properties already measured, intersected with each
#: member's own page range. Measured on ICDAR 2026: 2,663 pages in four
#: volumes, 591 in the 34 papers worth reading. The join is free and instant;
#: the `profile` it reads is free but NOT instant (it reads every glyph on
#: every page), which is why it is a declared prerequisite and not a flag.
PROFILE_SUFFIX = ".profile.json"
ROLLUP_SUFFIX = ".memberprofile.json"

#: Most decision-relevant first — these are the properties a reader is
#: choosing BY. Anything `profile` establishes that is not here still appears,
#: after them; nothing is dropped for not being on the list.
_PROP_ORDER = ("equation", "inline-math", "frame", "listing", "diagram",
               "no-text-layer", "invisible-text", "inline-code",
               "rotated-text", "coloured-fill", "coloured-frame")


def profile_path(pdf: Path) -> Path:
    return pdf.with_suffix(PROFILE_SUFFIX)


def rollup_path(pdf: Path) -> Path:
    return pdf.with_suffix(ROLLUP_SUFFIX)


def read_profile(pdf: Path, pdf_pages: "int | None" = None) -> dict:
    """The page properties measured for this PDF, or a refusal that names the
    command which produces them.

    Two refusals, both learned elsewhere in this tree: a reading older than
    the document it describes is never silently served, and a page count that
    disagrees with the listing's means one of the two is of another document —
    the page NUMBER is the key the join turns on, so a frame shifted by one is
    a wrong answer that looks right.
    """
    p = profile_path(pdf)
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError:
        raise VolumeError(
            "no page properties beside %s — run `pdfdrill profile %s` first. "
            "It is free, keyless and offline, and it reads every page's "
            "glyphs once, so on a volume it takes minutes, not seconds."
            % (pdf.name, pdf.name)) from None
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise VolumeError("%s is not readable JSON (%s) — rebuild it with "
                          "`pdfdrill profile %s`" % (p.name, e, pdf.name)) \
            from e
    try:
        if p.stat().st_mtime < pdf.stat().st_mtime:
            raise VolumeError(
                "%s is older than %s — the properties describe an earlier "
                "reading of the document. Rebuild with `pdfdrill profile %s`."
                % (p.name, pdf.name, pdf.name))
    except OSError:
        pass
    got = int(data.get("pages") or 0)
    if pdf_pages is not None and got != pdf_pages:
        raise VolumeError(
            "%s profiles %d page(s) and the listing counts %d in %s — one of "
            "them is of a different document, and the page number is the key "
            "the roll-up joins on. Rebuild both: `pdfdrill profile %s`, "
            "`pdfdrill members %s --force`."
            % (p.name, got, pdf_pages, pdf.name, pdf.name, pdf.name))
    return data


def _where_pages(profile: dict) -> dict:
    """{property: set of 1-based PDF page numbers} from a profile.json."""
    out: dict = {}
    for k, v in (profile.get("where") or {}).items():
        out[k] = {int(x) for x in (v or [])}
    return out


def _ordered(props) -> list:
    """Decision-relevant properties first, then whatever else was measured."""
    known = [k for k in _PROP_ORDER if k in props]
    return known + sorted(k for k in props if k not in _PROP_ORDER)


def rollup(listing: dict, profile: dict) -> dict:
    """Each member's page properties — `profile`'s per-page measurements
    intersected with the member's own PDF page range.

    A member whose page range is not established gets no properties: absent,
    not empty. The denominator travels with every count (`pages_total`),
    because "12 pages carry an equation" is a different claim in a 17-page
    paper and in a 700-page volume.
    """
    where = _where_pages(profile)
    members = []
    for m in listing.get("members") or []:
        first, last = m.get("pdf_first_page"), m.get("pdf_last_page")
        rec = {
            "member": m.get("member"),
            "doi": m.get("doi"),
            "title": m.get("title"),
            "pdf_first_page": first,
            "pdf_last_page": last,
            "pages_total": m.get("pdf_pages"),
        }
        if not first or not last:
            rec["props"] = None
            rec["props_source"] = ("the member's page range is not "
                                   "established, so nothing is rolled up")
            members.append(rec)
            continue
        span = last - first + 1
        props = {}
        for k, pages in where.items():
            hit = sorted(p for p in pages if first <= p <= last)
            if hit:
                props[k] = {"pages": len(hit), "of": span, "first": hit[0]}
        rec["props"] = props
        rec["props_source"] = ("pages %d-%d of %s, as measured by `profile`"
                               % (first, last, PROFILE_SUFFIX.lstrip(".")))
        members.append(rec)

    inside = {p for m in members if m.get("props") is not None
              for p in range(m["pdf_first_page"], m["pdf_last_page"] + 1)}
    outside = {}
    for k, pages in where.items():
        n = len([p for p in pages if p not in inside])
        if n:
            outside[k] = n

    by_prop = {}
    for k in _ordered(where):
        carriers = [m for m in members if (m.get("props") or {}).get(k)]
        by_prop[k] = {
            "members": len(carriers),
            "pages_in_those_members": sum(m["pages_total"] or 0
                                          for m in carriers),
            "pages_carrying": sum((m["props"][k]["pages"]) for m in carriers),
            "pages_in_volume": len(where[k]),
        }
    return {
        "volume": dict(listing.get("volume") or {}),
        "profile": {
            "pages": profile.get("pages"),
            "pages_carrying_anything": len(profile.get("page_props") or {}),
            "properties": _ordered(where),
        },
        "members": members,
        "by_property": by_prop,
        "outside_every_member": outside,
        "sources": {
            "member_ranges": "<stem>%s (see its own `sources`)" % LISTING_SUFFIX,
            "page_properties": "<stem>%s, written by `pdfdrill profile` — "
                               "free, keyless, offline, one glyph reading of "
                               "every page" % PROFILE_SUFFIX,
            "join": "the member's PDF page range intersected with the pages "
                    "each property was established on; no page is read again",
            "absent_not_false": "a property a page does not carry is ABSENT "
                                "from that page, not false — `profile`'s own "
                                "doctrine, kept here: a zero cell is printed "
                                "as `-`",
        },
    }


def write_rollup(pdf: Path, data: dict) -> Path:
    p = rollup_path(pdf)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(p)
    return p


def read_rollup(pdf: Path) -> "dict | None":
    try:
        return json.loads(rollup_path(pdf).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
