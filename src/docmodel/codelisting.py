"""079 — `lstlisting` in an author e-print becomes a `CodeListing` DocObject.

Source code is not mathematics and must not be routed through the math path:
its body is VERBATIM — whitespace, indentation and line breaks are content, and
a normaliser that trims them destroys the object it is describing. So the body
is captured byte-exactly between the delimiters and never touched.

Why the e-print rather than the OCR: out/078 measured 97 documents opening
`algorithm` and 41 opening `lstlisting` in author sources, against 18 of 3,297
in MathPix `lines.json`. The population that needs reconstructing from pixels
is 0.5%; the population with source available is where the work is.

Handles both forms:
    \\begin{lstlisting}[opts] ... \\end{lstlisting}     inline body
    \\lstinputlisting[opts]{path}                       body in another file

`algorithm` is deliberately NOT handled here. A pseudocode float is a different
object with its own environments (algorithm2e, algorithmic, algpseudocode) and
its own semantics; putting it in a CodeListing would mean calling pseudocode
source code.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator

_BEGIN = re.compile(r"\\begin\s*\{lstlisting\}", re.M)
_END = re.compile(r"\\end\s*\{lstlisting\}")
_INPUT = re.compile(r"\\lstinputlisting\s*(\[)?", re.M)
#: strip the formatting wrapper authors put round a caption — \texttt{Foo},
#: \verb|Foo|, \mbox{Foo} — to recover the name underneath. Applied repeatedly
#: because \texttt{\small Foo} nests.
_WRAP = re.compile(r"\\(?:texttt|textsf|textbf|textit|emph|mbox|small|"
                   r"footnotesize|scriptsize|tiny|normalsize)\s*\{")
#: a BARE declaration, which takes no argument and so is invisible to _WRAP:
#: `\texttt{\small foo}` unwraps to `\small foo`, and without this the
#: caption keeps the command as if it were part of the name.
_DECL = re.compile(r"\\(?:small|footnotesize|scriptsize|tiny|normalsize|large|"
                   r"Large|bfseries|itshape|ttfamily|sffamily|rmfamily)\s*")


def _balanced(s: str, i: int, open_ch: str, close_ch: str) -> tuple[str, int]:
    """Body of the group starting at s[i]==open_ch, and the index past it.

    Returns ("", i) when the group never closes, so a truncated file yields
    nothing rather than swallowing the rest of the document.
    """
    if i >= len(s) or s[i] != open_ch:
        return "", i
    depth, j = 0, i
    while j < len(s):
        c = s[j]
        if c == "\\":                       # \{ and \} are literal, not depth
            j += 2
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return "", i


def split_options(opts: str) -> dict[str, str]:
    """`language=Julia, caption={\\texttt{X}}, label={lst:X}` -> dict.

    Splits on TOP-LEVEL commas only: `caption={A, B}` is one option, not two.
    Keys are lowercased; values keep their case and are stripped of one outer
    brace pair. A bare flag (`numbers`) maps to "".
    """
    out: dict[str, str] = {}
    key, buf, depth, i = None, [], 0, 0
    def flush():
        raw = "".join(buf).strip()
        if key is not None:
            v = raw
            if v.startswith("{") and v.endswith("}"):
                v = v[1:-1]
            out[key.strip().lower()] = v
        elif raw:
            out[raw.lower()] = ""
    while i < len(opts):
        c = opts[i]
        if c == "\\":
            buf.append(opts[i:i + 2]); i += 2; continue
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        if depth == 0 and c == "=" and key is None:
            key = "".join(buf); buf = []; i += 1; continue
        if depth == 0 and c == ",":
            flush(); key, buf = None, []; i += 1; continue
        buf.append(c); i += 1
    flush()
    return out


def clean_caption(cap: str) -> str:
    """The name under the formatting. `\\texttt{BraKet}` -> `BraKet`."""
    s = cap.strip()
    while True:
        m = _WRAP.search(s)
        if not m:
            break
        inner, end = _balanced(s, m.end() - 1, "{", "}")
        if not inner and end == m.end() - 1:
            break
        s = s[:m.start()] + inner + s[end:]
    return _DECL.sub("", s).strip()


@dataclass
class Listing:
    """One lstlisting occurrence, with where it came from."""
    body: str                       # VERBATIM — never normalised
    language: str = ""
    caption: str = ""               # cleaned of \texttt{} etc.
    caption_raw: str = ""
    label: str = ""
    source_file: str = ""
    source_line: int = 0            # 1-based line of the \begin / \lstinputlisting
    external: str = ""              # path, for \lstinputlisting
    options: dict = field(default_factory=dict)

    def props(self, bibkey: str = "") -> dict:
        p = {"language": self.language, "caption": self.caption,
             "caption_raw": self.caption_raw, "label": self.label,
             "body": self.body, "source_file": self.source_file,
             "source_line": self.source_line, "lines": self.body.count("\n") + 1
             if self.body else 0}
        if self.external:
            p["external_path"] = self.external
        if bibkey:
            p["bibkey"] = bibkey
        return p


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def parse_listings(text: str, source_file: str = "") -> Iterator[Listing]:
    """Every lstlisting in `text`, inline and \\lstinputlisting alike."""
    for m in _BEGIN.finditer(text):
        i = m.end()
        opts = ""
        if i < len(text) and text[i] == "[":
            opts, i = _balanced(text, i, "[", "]")
        # the body starts after the newline that ends the \begin line, so the
        # delimiter's own line break is not part of the code
        if i < len(text) and text[i] == "\n":
            i += 1
        e = _END.search(text, i)
        if not e:
            continue                       # unterminated: emit nothing
        body = text[i:e.start()]
        if body.endswith("\n"):
            body = body[:-1]
        o = split_options(opts)
        cap = o.get("caption", "")
        yield Listing(body=body, language=o.get("language", ""),
                      caption=clean_caption(cap), caption_raw=cap,
                      label=o.get("label", ""), source_file=source_file,
                      source_line=_line_of(text, m.start()), options=o)
    for m in _INPUT.finditer(text):
        i = m.end() - (1 if m.group(1) else 0)
        opts = ""
        if i < len(text) and text[i] == "[":
            opts, i = _balanced(text, i, "[", "]")
        while i < len(text) and text[i] in " \t":
            i += 1
        path, _ = _balanced(text, i, "{", "}")
        if not path:
            continue
        o = split_options(opts)
        cap = o.get("caption", "")
        yield Listing(body="", language=o.get("language", ""),
                      caption=clean_caption(cap), caption_raw=cap,
                      label=o.get("label", ""), source_file=source_file,
                      source_line=_line_of(text, m.start()),
                      external=path.strip(), options=o)


def to_docobjects(listings, bibkey: str = ""):
    """`Listing`s -> `DocObject`s of type CodeListing, in order."""
    from docmodel.core import DocObject
    return [DocObject(type="CodeListing", props=l.props(bibkey)) for l in listings]
