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


def clean_heading_residuals(doc) -> int:
    """Clean every Paragraph whose text begins with a sectioning command.
    Returns the number changed."""
    n = 0
    for o in doc.objects.values():
        if o.type != "Paragraph":
            continue
        text = o.props.get("text") or ""
        m = _LEAD.search(text)
        if not m:
            continue
        cmd = m.group(1)
        brace = m.end() - 1          # the title-opening '{' (match ends on it)
        end = _balanced(text, brace)
        if end < 0:
            continue
        title = text[brace + 1:end - 1].strip()
        rest = text[end:].lstrip()
        # lift a leading number ("2.3 Cellular Sheaves") into refnum
        refnum = ""
        nm = _LEAD_NUM.match(title)
        if nm:
            refnum = nm.group(1)
            title = title[nm.end():].strip()
        new_text = title if not rest else f"{title}\n\n{rest}"
        o.props["text"] = new_text
        o.props["kind"] = cmd
        o.props["refnum"] = refnum
        o.props["heading_residual_cleaned"] = True
        n += 1
    return n
