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
    import json
    from docops.projectors.tiddlywiki import TiddlyWikiProjector
    from docops.base import OperatorConfig

    bib = doc.meta.get("bibkey", "DOC")
    tids = json.loads(TiddlyWikiProjector(
        OperatorConfig(op="projector", classname="TiddlyWikiProjector")).project(doc))
    by_title = {t["title"]: t.get("text", "") for t in tids}
    flow = lambda o: o.props.get("flow_index") or 0
    n = 0
    for i, p in enumerate(sorted(doc.objects_of_type("Paragraph"), key=flow), 1):
        new = (by_title.get(f"{bib}_PARA_{i:04d}") or "").strip()
        if new and new != (p.props.get("text") or "").strip():
            p.props.setdefault("text_source", p.props.get("text", ""))
            p.props["text"] = new
            n += 1
    return n


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
        if promote and norm and norm not in existing:
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
