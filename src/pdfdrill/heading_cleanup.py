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


def extract_footnote_paragraphs(doc) -> int:
    """Lift `\\footnotetext{...}` that MathPix left inside a Paragraph (a plain
    `text` line, so the FootnoteProcessor never saw it) into proper Footnote
    objects — so they transclude (`{{<fn>||FN}}`) like any other footnote.

    Parses the `\\({ }^{N}\\)` anchor for `refnum`, strips it from the content,
    and removes the `\\footnotetext{...}` span from the paragraph (the paragraph
    is dropped if nothing else remains). Idempotent. Returns the count."""
    from docmodel.core import DocObject
    n = 0
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
        for m in _FOOTNOTETEXT.finditer(text):
            new_parts.append(text[pos:m.start()])
            brace = m.end() - 1
            end = _balanced(text, brace)
            if end < 0:
                new_parts.append(text[m.start():])
                pos = len(text)
                break
            body = text[brace + 1:end - 1].strip()
            pos = end
            am = _FN_ANCHOR.match(body)
            refnum = am.group(1) if am else ""
            if am:
                body = body[am.end():].strip()
            fn = DocObject(type="Footnote", props={
                "refnum": refnum, "anchor_marker": f"{{ }}^{{{refnum}}}" if refnum else "",
                "content": body, "page": o.props.get("page"),
                "flow_index": o.props.get("flow_index"),
                "bibkey": o.props.get("bibkey"), "added_by": "footnote_cleanup"})
            for r in o.realizations:           # share provenance to the source
                fn.add_realization(r)
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
    for i, p in enumerate(sorted(doc.objects_of_type("Paragraph"), key=flow), 1):
        # The projector builds from the IMMUTABLE SOURCE stream, i.e. the
        # document's ORIGINAL language. Writing that over a translation puts the
        # original back AND — via setdefault — leaves text_source equal to text,
        # so the paragraph still looks translated to anything that merely checks
        # the twin exists. A twin that DIFFERS is the evidence; its presence is
        # not. This destroyed 23 translated paragraphs before it was caught.
        if is_translated(p, "text"):
            continue
        new = (by_title.get(f"{bib}_PARA_{i:04d}") or "").strip()
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
