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
