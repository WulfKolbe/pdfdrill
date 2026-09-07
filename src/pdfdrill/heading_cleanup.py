"""
Heading-residual cleanup — strip MathPix's leaked LaTeX sectioning commands.

MathPix often returns a heading as `\\section*{Title}` and merges it with the
following prose into ONE Paragraph object. The raw command in `props["text"]`
disturbs semantic analysis (claim/gap extraction, the LLM dump). This cleaner,
applied to a Paragraph whose text STARTS with a sectioning command:

  * lifts the title out of the command (and a leading number out of the title),
  * records `kind` (section/subsection/...) and `refnum` (the number, "" if
    unnumbered like `\\section*`),
  * rewrites the text to the title alone followed by whatever prose came after
    — the LaTeX command is gone, no content is lost, and the `\\n\\n` split
    downstream keeps the heading separate from the body.

Pure + idempotent (a cleaned paragraph no longer starts with a command).
Non-destructive to structure: the Paragraph stays a Paragraph (the user's
"title alone + kind + refnum" choice), so transclusion offsets are untouched.
"""
from __future__ import annotations

import re

_CMD = r"(chapter|part|section|subsection|subsubsection|paragraph|subparagraph)"
# a LEADING sectioning command: optional whitespace + an optional stray
# wrapping "{" (MathPix sometimes emits `{\section*{TITLE}.`), then \cmd*{TITLE}
_LEAD = re.compile(r"^\s*\{?\s*\\" + _CMD + r"\*?\s*\{")
_LEAD_NUM = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s+")


def _balanced(text: str, open_pos: int) -> int:
    """Index just past the matching '}' for the '{' at open_pos (or -1)."""
    depth = 0
    for i in range(open_pos, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


_FOOTNOTETEXT = re.compile(r"\\footnotetext\s*\{")
_FN_ANCHOR = re.compile(r"^\s*\\?\(?\s*\{\s*\}\s*\^\s*\{?(\d+)\}?\s*\\?\)?\s*")


def _para_lines(doc, para):
    """[(anchor, text)] for the mathpix lines the paragraph's surface covers."""
    st = doc.streams.get("mathpix_lines")
    if st is None:
        return []
    out = []
    for r in para.realizations:
        if r.stream != "mathpix_lines" or r.role != "surface" or r.start is None:
            continue
        try:
            span = st.slice_anchors(r.start, r.end if r.end is not None else r.start)
        except KeyError:
            continue
        for a in span:
            p = st.payload[a]
            out.append((a, p.get("text_display") or p.get("text") or ""))
    return out


def _footnote_extents(doc, para, refnums: list[str], heads=(0,)):
    """Where each footnote of one group actually sits, line by line.

    Returns one entry per refnum, in reading order, or None for a refnum whose
    label is not on any line of the paragraph (nothing is then guessed):

        {"line": i, "offset": o, "own": (first, last) | None}

    636: the cleanup used to copy the PARAGRAPH's realizations onto every
    Footnote it made, so one line was claimed by a Paragraph and by up to four
    Footnotes at once — all 35 `Footnote+Paragraph` doubly-claimed anchors on
    penev_A. Claiming only the label's own line instead traded that for 193
    lines claimed by NOTHING: two thirds of these paragraphs are pure footnote
    text and the Footnote was the only claimant they had. So the claim is the
    footnote's real extent: the lines it owns WHOLE (covering), and an inline
    sub-anchor for a line it SHARES — with prose before it, or with the next
    footnote's number after it. `\\footnotetext{` and whitespace are markup,
    not another object's content, so a line carrying only those before the
    label is still owned whole.
    """
    from docmodel.footnote_split import LABEL
    lines = _para_lines(doc, para)
    if not lines:
        return [None] * len(refnums)
    found: list = []
    li, ci = 0, 0                                  # scan cursor: line, column
    for refnum in refnums:
        hit = None
        for j in range(li, len(lines)):
            for m in LABEL.finditer(lines[j][1]):
                if m.group(1) == refnum and (j > li or m.start() >= ci):
                    hit = (j, m.start())
                    break
            if hit:
                break
        if hit is None:
            found.append(None)
            continue
        li, ci = hit[0], hit[1] + 1
        found.append(hit)
    # A group's FIRST body starts where the GROUP starts, not at its number:
    # whatever precedes the first label is a footnote spilling in from the
    # previous page, and split_bodies keeps it on this body (it invents no owner
    # for it). Two penev_A blocks are that shape — 11 lines that would otherwise
    # be claimed by nothing while their text sits in a Footnote.
    #
    # THE BACK-OFF MAY NOT REACH INTO A PREVIOUS GROUP. A paragraph can carry
    # two `\footnotetext{…}` groups; searching from the previous group's HEAD
    # found that group's own opener again, so group 2 claimed group 1's lines
    # whole and the two overlapped (a Footnote+Footnote pair in `conserve`).
    # The floor is just past the previous group's LAST located label.
    ordered = [h for h in sorted(heads) if h < len(found)]
    for gi, h in enumerate(ordered):
        if found[h] is None:
            continue
        lo_line, lo_col = 0, 0
        if gi:
            prior = [f for f in found[ordered[gi - 1]:h] if f is not None]
            if prior:
                lo_line, lo_col = max(prior)[0], max(prior)[1] + 1
        for j in range(lo_line, found[h][0] + 1):
            m = _FOOTNOTETEXT.search(lines[j][1], lo_col if j == lo_line else 0)
            if m and (j, m.start()) <= found[h]:
                found[h] = (j, m.start())
                break
    out = []
    for k, hit in enumerate(found):
        if hit is None:
            out.append(None)
            continue
        i, off = hit
        prefix = _FOOTNOTETEXT.sub("", lines[i][1][:off]).strip()
        nxt = next((h for h in found[k + 1:] if h is not None), None)
        last = (nxt[0] - 1) if nxt else len(lines) - 1
        first = i if not prefix else i + 1
        own = (first, last) if first <= last else None
        out.append({"line": i, "offset": off, "own": own,
                    "shared": bool(prefix), "lines": lines})
    return out


def extract_footnote_paragraphs(doc) -> int:
    """Lift `\\footnotetext{...}` that MathPix left inside a Paragraph (a plain
    `text` line, so the FootnoteProcessor never saw it) into proper Footnote
    objects — so they transclude (`{{<fn>||FN}}`) like any other footnote.

    Parses the `\\({ }^{N}\\)` anchor for `refnum`, strips it from the content,
    and removes the `\\footnotetext{...}` span from the paragraph (the paragraph
    is dropped if nothing else remains). Idempotent. Returns the count.

    636: MathPix puts every footnote of a page into ONE group, so one object
    used to take the lot — 15 of the 25 penev_A bodies this made ended with the
    NEXT footnote's printed number and its first words. Each label now closes
    the body before it (`docmodel.footnote_split`), and each body claims its
    line inline instead of the paragraph's whole span."""
    from docmodel.core import DocObject
    from docmodel import footnote_split as fsplit
    n = 0
    orphan = 0
    unlocated = 0
    drop: list[str] = []
    add: list[DocObject] = []
    for o in doc.objects.values():
        if o.type != "Paragraph":
            continue
        text = o.props.get("text") or ""
        if "\\footnotetext" not in text:
            continue
        new_parts: list[str] = []
        pos = 0
        groups: list[list] = []
        for m in _FOOTNOTETEXT.finditer(text):
            new_parts.append(text[pos:m.start()])
            brace = m.end() - 1
            end = _balanced(text, brace)
            if end < 0:
                new_parts.append(text[m.start():])
                pos = len(text)
                break
            group = text[brace + 1:end - 1]
            pos = end
            segs = fsplit.split_bodies(group)
            if not segs:                       # no label — one body, as before
                segs = [fsplit.Segment(refnum="", start=0, end=len(group),
                                       body=group.strip())]
            groups.append(segs)
        # One ordered scan of the paragraph's lines for ALL its groups, so a
        # second group's numbers cannot match the first group's lines.
        flat = [s.refnum for segs in groups for s in segs]
        heads = {0}
        k = 0
        for segs in groups[:-1]:
            k += len(segs)
            heads.add(k)
        extents_flat = _footnote_extents(doc, o, flat, heads)
        base = 0
        for segs in groups:
            extents = extents_flat[base:base + len(segs)]
            base += len(segs)
            for i, seg in enumerate(segs):
                body = seg.body
                refnum = seg.refnum
                if i == 0:                     # the loose leading spellings, as before
                    am = _FN_ANCHOR.match(body)
                    if am:
                        refnum = refnum or am.group(1)
                        body = body[am.end():].strip()
                orphan += 1 if seg.tail_unassigned else 0
                props = {
                    "refnum": refnum,
                    "anchor_marker": f"{{ }}^{{{refnum}}}" if refnum else "",
                    "content": body, "page": o.props.get("page"),
                    "bibkey": o.props.get("bibkey"), "added_by": "footnote_cleanup"}
                # Only when the paragraph HAS one: `_sort_by_flow` defaults an
                # ABSENT flow_index to 10**9, but a key present and None makes
                # two footnotes incomparable and the projection raises.
                if o.props.get("flow_index") is not None:
                    props["flow_index"] = o.props["flow_index"]
                if i:
                    props["split_index"] = i
                if seg.tail_unassigned:
                    props["tail_unassigned"] = True
                fn = DocObject(type="Footnote", props=props)
                ext = extents[i] if i < len(extents) else None
                for r in o.realizations:       # share provenance to the source
                    if ext is not None and r.stream == "mathpix_lines" \
                            and r.role == "surface":
                        continue               # replaced by the footnote's own extent
                    fn.add_realization(r)
                if ext is None:
                    unlocated += 1
                else:
                    from docmodel.core import Realization
                    lines = ext["lines"]
                    if ext["shared"]:          # prose before it on that line
                        li, off = ext["line"], ext["offset"]
                        fn.add_realization(Realization(
                            stream="mathpix_lines", start=lines[li][0],
                            end=lines[li][0], role="surface",
                            props={"offset": off,
                                   "length": len(lines[li][1]) - off}))
                    if ext["own"]:             # the lines it owns whole
                        a, b = ext["own"]
                        fn.add_realization(Realization(
                            stream="mathpix_lines", start=lines[a][0],
                            end=lines[b][0], role="surface"))
                    elif not ext["shared"]:    # shares its line with the NEXT number
                        li, off = ext["line"], ext["offset"]
                        fn.add_realization(Realization(
                            stream="mathpix_lines", start=lines[li][0],
                            end=lines[li][0], role="surface",
                            props={"offset": off,
                                   "length": len(lines[li][1]) - off}))
                add.append(fn)
                n += 1
        new_parts.append(text[pos:])
        remaining = re.sub(r"\s+", " ", "".join(new_parts)).strip()
        if remaining:
            o.props["text"] = remaining
        else:
            drop.append(o.id)
    for fn in add:
        doc.add(fn)
    for pid in drop:
        doc.objects.pop(pid, None)
    if orphan:
        doc.meta["footnote_orphan_tail"] = \
            int(doc.meta.get("footnote_orphan_tail") or 0) + orphan
    if unlocated:
        doc.meta["footnote_span_not_located"] = \
            int(doc.meta.get("footnote_span_not_located") or 0) + unlocated
    return n


def materialize_transclusions(doc) -> int:
    """Write the TiddlyWiki projector's TRANSCLUDED paragraph text back into the
    model's `props["text"]`, so every consumer that reads the canonical text
    (llmtext, semantic, markdown) sees `{{<eq>||FO}}` / `{{<fn>||FN}}` tokens
    instead of raw inline math (`\\(X\\)`) or footnote markers — matching what
    the tiddlers already show. The projector rebuilds transclusions from the
    immutable source stream, so this is idempotent and re-running the tiddler
    projector afterwards is unaffected (it ignores `props["text"]`).

    Run AFTER `extract_footnote_paragraphs` so footnote markers resolve to
    `{{||FN}}`. The original text is preserved under `text_source` on first
    materialization. Returns the count of paragraphs changed."""
    bib = doc.meta.get("bibkey", "DOC")
    by_title = _projected_paragraphs(doc)
    flow = lambda o: o.props.get("flow_index") or 0
    n = 0
    from docops.projectors.tiddlywiki import title_for

    for i, p in enumerate(sorted(doc.objects_of_type("Paragraph"), key=flow), 1):
        # The projector builds from the IMMUTABLE SOURCE stream, i.e. the
        # document's ORIGINAL language. Writing that over a translation puts the
        # original back AND — via setdefault — leaves text_source equal to text,
        # so the paragraph still looks translated to anything that merely checks
        # the twin exists. A twin that DIFFERS is the evidence; its presence is
        # not. This destroyed 23 translated paragraphs before it was caught.
        if is_translated(p, "text"):
            continue
        new = (by_title.get(title_for(bib, "Paragraph", i)) or "").strip()
        if new and new != (p.props.get("text") or "").strip():
            p.props.setdefault("text_source", p.props.get("text", ""))
            p.props["text"] = new
            n += 1
    return n


def is_translated(obj, field: str) -> bool:
    """True when `field` carries a translation — a `<field>_source` twin whose
    text DIFFERS. Materialization writes an identical twin, so mere presence
    proves nothing."""
    props = getattr(obj, "props", {}) or {}
    src = props.get(field + "_source")
    cur = props.get(field)
    return (isinstance(src, str) and isinstance(cur, str)
            and bool(src.strip()) and src != cur)


def _projected_paragraphs(doc) -> dict:
    """title -> transcluded text, from the TiddlyWiki projector. Split out so a
    test can supply the projection without building a whole Document."""
    import json
    from docops.projectors.tiddlywiki import TiddlyWikiProjector
    from docops.base import OperatorConfig
    tids = json.loads(TiddlyWikiProjector(
        OperatorConfig(op="projector", classname="TiddlyWikiProjector")).project(doc))
    return {t["title"]: t.get("text", "") for t in tids}


_LEAD_ALPHA = re.compile(r"^([A-Z])[.)]\s+")     # appendix letter "A. ", "B) "
_LEVEL = {"chapter": 0, "part": 0, "section": 1, "subsection": 2,
          "subsubsection": 3, "paragraph": 4, "subparagraph": 5}


def clean_heading_residuals(doc, promote: bool = True) -> int:
    """Every Paragraph whose text begins with a sectioning command is a MathPix
    HEADING that leaked into prose. Split it: PROMOTE the heading to a `Section`
    (unless one already exists for it) and keep ONLY the prose in the Paragraph — a
    heading-only paragraph is dropped. So an LLM never reads a heading as body, the
    inspect box stops at the frame, and appendix headings ('A. Dataset Split
    Details') become real Sections (refnum='A', is_appendix). Returns #paragraphs
    changed."""
    from docmodel.core import DocObject

    def _norm_cap(cap: str) -> str:                   # strip a leading A./2.3 + lower
        c = (cap or "").strip()
        am, nm = _LEAD_ALPHA.match(c), _LEAD_NUM.match(c)
        c = c[am.end():] if am else (c[nm.end():] if nm else c)
        return c.strip().lower()

    existing = set()                                  # section captions already present
    for o in doc.objects.values():
        if o.type == "Section":
            c = _norm_cap(o.props.get("caption") or o.props.get("title") or "")
            if c:
                existing.add(c)
    # 573 — the flow positions already occupied by a Section, so a heading
    # cannot be promoted on top of one the other producer already made.
    _section_flows = set()
    for o in doc.objects.values():
        if o.type == "Section":
            try:
                _section_flows.add(int(o.props.get("flow_index")))
            except (TypeError, ValueError):
                pass
    n = 0
    add: "list[DocObject]" = []
    drop: "list[str]" = []
    for o in list(doc.objects.values()):
        if o.type != "Paragraph":
            continue
        text = o.props.get("text") or ""
        m = _LEAD.search(text)
        if not m:
            continue
        cmd = m.group(1)
        brace = m.end() - 1                           # the title-opening '{'
        end = _balanced(text, brace)
        if end < 0:
            continue
        title = text[brace + 1:end - 1].strip()
        # strip a leading `}`/`.` the brace-wrapped form leaves ("{\section*{X}.")
        rest = re.sub(r"^[\s.}]+", "", text[end:])
        # lift a leading appendix LETTER ("A. …") or NUMBER ("2.3 …") into refnum
        refnum, is_app = "", False
        am, nm = _LEAD_ALPHA.match(title), _LEAD_NUM.match(title)
        if am:
            refnum, title, is_app = am.group(1), title[am.end():].strip(), True
        elif nm:
            refnum, title = nm.group(1), title[nm.end():].strip()
        norm = title.strip().lower()
        # 573 — DE-DUPLICATE ON POSITION, NOT ON CAPTION.
        #
        # The caption guard above cannot see these: the line-based producer
        # reads the HEADER LINE and this one reads the PARAGRAPH that begins
        # with the same heading, and the two disagree about where the caption
        # ends. johnston flow 2 is "Introduction" and flow 3 is "Introduction
        # to Linear and Matrix" — the same heading, normalising to different
        # strings, so `norm not in existing` was true and a second Section was
        # added. 152 of 152 cmd-less Sections in the corpus sat at exactly
        # flow_index+1 after a cmd-bearing one; the pairing was total.
        #
        # A heading that already has a Section within one flow position is
        # that Section. Position is the thing both producers agree on.
        _f = o.props.get("flow_index")
        try:
            _f = int(_f)
        except (TypeError, ValueError):
            _f = None
        _adjacent = _f is not None and (
            _f in _section_flows or (_f - 1) in _section_flows)
        if promote and norm and norm not in existing and not _adjacent:
            add.append(DocObject(type="Section", props={
                "caption": title, "title": title, "kind": cmd,
                "level": _LEVEL.get(cmd, 1), "refnum": refnum, "is_appendix": is_app,
                "page": o.props.get("page"), "region": o.props.get("region"),
                "flow_index": o.props.get("flow_index"),
                "parent_section": o.props.get("parent_section"),
                "bibkey": o.props.get("bibkey"), "added_by": "heading_promote"}))
            existing.add(norm)
        if rest:                                      # keep ONLY the prose
            o.props["text"] = rest
            o.props["kind"] = cmd
            o.props["refnum"] = refnum
            o.props["heading_residual_cleaned"] = True
        else:                                         # heading-only paragraph → drop
            drop.append(o.id)
        n += 1
    for s in add:
        doc.add(s)
    for oid in drop:
        doc.objects.pop(oid, None)
    # Appendix marker for a MathPix model (no `\appendix` signal): a top-level
    # Section whose caption is LETTER-numbered (A., B., …) is an appendix — lift the
    # letter into refnum + flag is_appendix, so it's treated like a chapter heading.
    for o in doc.objects.values():
        if o.type != "Section" or o.props.get("is_appendix"):
            continue
        am = _LEAD_ALPHA.match((o.props.get("caption") or "").strip())
        if am and not o.props.get("refnum"):
            o.props["refnum"] = am.group(1)
            o.props["caption"] = (o.props.get("caption") or "").strip()[am.end():].strip()
            o.props["title"] = o.props["caption"]
            o.props["is_appendix"] = True
    return n


# ---------------------------------------------------------------------------
# Front-matter LaTeX commands in prose
# ---------------------------------------------------------------------------
#
# A merged model keeps the author's title-page LaTeX verbatim, so a Paragraph's
# text can literally be `\title{ … }`. The braced ARGUMENT is the prose; the
# command is markup nobody meant to read, and every projector was showing it.

# Commands whose braced argument IS the text.
_UNWRAP = ("title", "author", "date", "institute", "institution",
           "affiliation", "subtitle", "thanks")
_UNWRAP_RE = re.compile(r"\\(" + "|".join(_UNWRAP) + r")\s*\{")

# Layout-only commands that carry no text at all.
_DROP_RE = re.compile(
    r"\\(?:maketitle|newpage|clearpage|cleardoublepage|noindent|hfill|hrule"
    r"|bigskip|medskip|smallskip|centering|raggedright|tableofcontents)\b"
    r"|\\(?:vspace|hspace|vskip|hskip)\*?\s*\{[^{}]*\}"
    r"|\\(?:vspace|hspace)\*?\s*[-\d.]+\s*(?:cm|mm|pt|em|ex|in)\b")

_BREAK_RE = re.compile(r"\\\\\s*(?:\[[^\]]*\])?")     # \\ and \\[2ex]


def unwrap_frontmatter_commands(text: str) -> str:
    """`\\title{X}` -> `X`, `\\\\` -> a line break, layout commands -> nothing.

    An UNBALANCED command is left exactly as it is: half-unwrapping would drop
    the closing brace and silently truncate the text, and a visible `\\title{`
    is better than prose that quietly lost its tail.
    """
    if not isinstance(text, str) or "\\" not in text:
        return text if isinstance(text, str) else ""
    out = text
    while True:
        m = _UNWRAP_RE.search(out)
        if not m:
            break
        end = _balanced(out, m.end() - 1)      # index JUST PAST the closing brace
        if end < 0:
            break                                     # unbalanced — leave it
        inner = out[m.end():end - 1].strip()
        out = out[:m.start()] + inner + out[end:]
    out = _DROP_RE.sub("", out)
    out = _BREAK_RE.sub("\n", out)
    # collapse the whitespace the removals leave behind, keeping paragraph breaks
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r" *\n[ \t]*", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


_FRONTMATTER_FIELDS = ("text", "content", "caption")
# The prose types, plus the caption-bearing figure/table types — the same set
# `translate` covers, so a caption is cleaned in whichever language it is in.
# Formula/Equation/Link/Page are deliberately outside: their strings are the
# content, not markup wrapped around it.
_FRONTMATTER_TYPES = {"Paragraph", "Abstract", "Section", "ListItem",
                      "Footnote", "Sidenote", "Caption", "Toc",
                      "Picture", "Diagram", "Chart", "Figure", "Table"}


def clean_frontmatter(doc) -> int:
    """Unwrap front-matter commands in every prose object, IN PLACE.

    Both the field and its `<field>_source` twin: a bilingual document that came
    out clean in one language and marked up in the other would make the language
    switch look like it changed the content. Idempotent; math/image objects are
    never touched (their LaTeX is the content, not markup around it).
    """
    changed = 0
    for obj in doc.objects.values():
        if obj.type not in _FRONTMATTER_TYPES:
            continue
        touched = False
        for field in _FRONTMATTER_FIELDS:
            for key in (field, field + "_source"):
                val = obj.props.get(key)
                if not isinstance(val, str) or "\\" not in val:
                    continue
                new = unwrap_frontmatter_commands(val)
                if new != val:
                    obj.props[key] = new
                    touched = True
        if touched:
            changed += 1
    return changed


# ---------------------------------------------------------------------------
# Section pages
# ---------------------------------------------------------------------------

# A heading may legitimately print at the foot of the page before its body, so
# only a gap LARGER than this counts as wrong.
_SECTION_PAGE_SLACK = 1


def repair_section_pages(doc) -> int:
    """Give each Section the page its CONTENT starts on, where the two disagree
    by more than a page. Returns the number repaired.

    MathPix reads the printed table of contents as a run of headings, so Section
    objects take their page from the TOC page — 35 of 38 in one thesis claimed
    page 2 while their content ran from page 6 to 40. That shows up as page
    labels marching 5, 2, 6, 2, 7 down a reflow, but it also breaks `booktoc`
    (which derives the front-matter offset from the section pages), the
    inspector's page boxes, and any answer to "which page is section X on".

    The original is preserved under `page_before_repair`, so the change is
    auditable and a wrong repair is recoverable.
    """
    first_page: dict = {}
    for obj in doc.objects.values():
        sid = obj.props.get("parent_section")
        page = obj.props.get("page")
        if not sid or not isinstance(page, int) or obj.type == "Section":
            continue
        flow = obj.props.get("flow_index") or 0
        cur = first_page.get(sid)
        if cur is None or flow < cur[0]:
            first_page[sid] = (flow, page)

    # Fall back to the next placed content in READING ORDER for a section that
    # owns no children — two in the thesis had none and stayed on the contents
    # page. Ownership still wins where it exists: proximity is the weaker signal.
    placed = sorted(
        ((o.props.get("flow_index") or 0), o.props.get("page"))
        for o in doc.objects.values()
        if o.type not in ("Section", "Link")
        and isinstance(o.props.get("page"), int)
        and o.props.get("flow_index") is not None)

    n = 0
    for sec in doc.objects_of_type("Section"):
        hit = first_page.get(getattr(sec, "id", None))
        if hit:
            content_page = hit[1]
        else:
            sf = sec.props.get("flow_index")
            nxt = [p for f, p in placed if sf is not None and f > sf]
            if not nxt:
                continue                   # nothing after it — leave it alone
            content_page = nxt[0]
        page = sec.props.get("page")
        if not isinstance(page, int):
            continue
        if abs(page - content_page) <= _SECTION_PAGE_SLACK:
            continue                       # a heading at the foot of the page
        sec.props.setdefault("page_before_repair", page)
        sec.props["page"] = content_page
        n += 1
    return n
