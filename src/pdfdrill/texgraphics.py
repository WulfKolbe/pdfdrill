r"""298 — every `\includegraphics` in the author's own sources.

The tex.zip gives us MathPix's view of a figure: a crop, named by the region
5-tuple, that may carry annotation MathPix drew. The author's sources give the
other view: the file they actually included, and the options they included it
with. `trim`/`clip` matter because a trimmed inclusion means the file on disk
is LARGER than what the page shows — joining a crop to an untrimmed file and
calling them the same picture would be wrong in a way that looks right.

Parsing is brace-matched rather than regex-captured. `trim={1 2 3 4}` and
`\includegraphics[width=.5\linewidth]{figs/a_b}` both defeat a `\[([^]]*)\]`
pattern, and a wrong option set is worse than none: it is a measurement of the
author's intent that the author never expressed.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Extensions graphicx searches, in the order it searches them. A reference
#: without a suffix (`figs/primal-dual`) is the common form.
GRAPHICS_EXT = (".pdf", ".png", ".jpg", ".jpeg", ".eps", ".ps", ".PDF", ".PNG",
                ".JPG", ".JPEG", ".EPS")

#: The options worth reporting separately. `trim`/`clip` change what part of
#: the file reaches the page; the rest change only its size on the page.
GEOMETRY_OPTS = ("trim", "clip", "viewport", "bb")
SIZE_OPTS = ("width", "height", "scale", "angle", "keepaspectratio")

_INCLUDE = re.compile(r"\\includegraphics\*?\s*(?=[\[{])")
_BEGIN = re.compile(r"\\begin\s*\{([^}]*)\}")
_END = re.compile(r"\\end\s*\{([^}]*)\}")
_GRAPHICSPATH = re.compile(r"\\graphicspath\s*\{")
_COMMENT = re.compile(r"(?<!\\)%.*$", re.M)


def _matched(text: str, i: int, open_ch: str, close_ch: str):
    """Return (inner, index-after-close) for the group starting at `text[i]`."""
    if i >= len(text) or text[i] != open_ch:
        return None, i
    depth = 0
    j = i
    while j < len(text):
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return text[i + 1:j], j + 1
        j += 1
    return None, i


def _skip_ws(text: str, i: int) -> int:
    while i < len(text) and text[i] in " \t\r\n":
        i += 1
    return i


def parse_options(raw: str) -> dict:
    r"""`trim={1 2 3 4}, clip, width=.5\linewidth` -> a dict.

    A bare key (`clip`) maps to True. Splitting is brace-aware so a comma
    inside `trim={...}` does not start a new option.
    """
    out, depth, cur = {}, 0, []
    for ch in raw:
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
        if ch == "," and depth <= 0:
            _one(out, "".join(cur))
            cur = []
        else:
            cur.append(ch)
    _one(out, "".join(cur))
    return out


def _one(out: dict, item: str) -> None:
    item = item.strip()
    if not item:
        return
    if "=" in item:
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip().strip("{}").strip()
    else:
        out[item] = True


def graphicspath(text: str) -> list:
    r"""The directories `\graphicspath{{figs/}{./}}` adds to the search."""
    m = _GRAPHICSPATH.search(text)
    if not m:
        return []
    inner, _ = _matched(text, m.end() - 1, "{", "}")
    if not inner:
        return []
    return [g.strip() for g in re.findall(r"\{([^{}]*)\}", inner) if g.strip()]


def _environments(text: str, upto: int) -> list:
    """The \\begin/\\end stack open at character `upto`."""
    stack = []
    for m in re.finditer(r"\\(begin|end)\s*\{([^}]*)\}", text[:upto]):
        if m.group(1) == "begin":
            stack.append(m.group(2))
        elif stack and stack[-1] == m.group(2):
            stack.pop()
        elif m.group(2) in stack:                 # unbalanced source; unwind
            while stack and stack.pop() != m.group(2):
                pass
    return stack


def _overlay_node(text: str, start: int) -> bool:
    r"""Is this inclusion the body of a TikZ node placed over the page?

    `\node[...] at (x,y) {\includegraphics{...}}` inside a tikzpicture, or a
    tikzpicture declared `[overlay]`. Both mean the file is positioned by TikZ
    rather than by the float, so its rectangle is not the float's rectangle.
    """
    back = text[max(0, start - 400):start]
    if re.search(r"\\node\b[^;]*$", back) and "{" in back[-200:]:
        return True
    return bool(re.search(r"\\begin\s*\{tikzpicture\}\s*\[[^\]]*overlay", back))


def _caption_for(text: str, pos: int, caps: list) -> str:
    r"""The caption of the float containing `pos`.

    Scoped to the enclosing figure/table so a caption belonging to the NEXT
    float is never attached to this one — that mis-attachment would corrupt a
    join built on caption text while looking like a successful match.
    """
    for env in ("figure", "table", "wrapfigure", "subfigure"):
        span = enclosing_span(text, pos, env)
        if span:
            inside = [c for c in caps if span[0] <= c["pos"] < span[1]]
            if inside:
                return inside[0]["text"]
    return ""


def calls(text: str, source: str = "") -> list:
    r"""Every `\includegraphics` in `text`, in document order."""
    body = _COMMENT.sub("", text)
    caps = captions(body)
    out = []
    for m in _INCLUDE.finditer(body):
        i = _skip_ws(body, m.end())
        opts_raw = ""
        if i < len(body) and body[i] == "[":
            inner, i = _matched(body, i, "[", "]")
            opts_raw = inner or ""
            i = _skip_ws(body, i)
        ref, _ = _matched(body, i, "{", "}")
        if ref is None:
            continue                              # malformed; not a call
        opts = parse_options(opts_raw)
        envs = _environments(body, m.start())
        cap = _caption_for(body, m.start(), caps)
        out.append({
            "source": source,
            "pos": m.start(),
            "caption": cap,
            "caption_plain": plain(cap) if cap else "",
            "line": body[:m.start()].count("\n") + 1,
            "file": ref.strip(),
            "options": opts,
            "options_raw": opts_raw,
            "environments": envs,
            "in_figure": any(e.startswith("figure") or e == "wrapfigure"
                             for e in envs),
            "in_tikzpicture": "tikzpicture" in envs,
            "overlay_node": ("tikzpicture" in envs
                             and _overlay_node(body, m.start())),
            "has_trim_or_clip": any(k in opts for k in GEOMETRY_OPTS),
            "size_options": {k: v for k, v in opts.items() if k in SIZE_OPTS},
        })
    return out


def resolve(ref: str, roots: list) -> "Path | None":
    """The file on disk a reference names, or None.

    graphicx appends an extension only when the reference has none, so a
    reference that already ends in `.pdf` is tried verbatim first.
    """
    # `\includegraphics{"plots/a b/"fig.pdf}` — graphicx's own quoting for a
    # path with spaces or dots. The quotes are syntax, not part of the name.
    ref = ref.strip().replace('"', "")
    for root in roots:
        p = Path(root) / ref
        if p.is_file():
            return p
        if not p.suffix:
            for ext in GRAPHICS_EXT:
                q = p.with_name(p.name + ext)
                if q.is_file():
                    return q
        else:
            # `figs/a.b.pdf` truncated to `figs/a.b` by a stripped suffix
            for ext in GRAPHICS_EXT:
                q = Path(str(p) + ext)
                if q.is_file():
                    return q
    return None


#: A MathPix tex.zip unpacked INSIDE the author's source tree. Its .tex sits in
#: a directory named after the process id and its inclusions are the region
#: 5-tuple, so counting it as author source doubles the call count and reports
#: MathPix's own crops as figures the author chose.
_PROCESS_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_FIVE_TUPLE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f-]{27}-(\d+)_(\d+)_(\d+)_(\d+)_(\d+)$")


def is_texzip_tex(tex: Path, src_dir: Path) -> bool:
    """Is this .tex MathPix's own, rather than the author's?"""
    try:
        rel = tex.relative_to(src_dir)
    except ValueError:
        return False
    return any(_PROCESS_ID.match(part) for part in rel.parts[:-1])


def region_tuple(ref: str):
    """The (page, h, w, y, x) a MathPix crop name encodes, or None."""
    m = _FIVE_TUPLE.match(Path(ref).stem if "." in Path(ref).name else ref)
    return tuple(int(g) for g in m.groups()) if m else None


def scan(src_dir: Path) -> dict:
    r"""Every inclusion under `src_dir`, with each file resolved on disk.

    `\graphicspath` is resolved against the declaring FILE's directory, not
    against the source root. A chapter in `chapters/` that declares
    `{./images/}` means `chapters/images/`; resolving it from the root reported
    134 of one document's 234 inclusions as missing files that were on disk all
    along.
    """
    src_dir = Path(src_dir)
    texs = sorted(p for p in src_dir.rglob("*.tex") if p.is_file())
    texts = {}
    all_paths = []
    for t in texs:
        try:
            texts[t] = t.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        all_paths.extend(graphicspath(texts[t]))
    # `\graphicspath` is a document-wide setting written once in the preamble,
    # and the chapters that use it never repeat it. Collecting it per file made
    # every inclusion in an \input chapter unresolvable -- 34 of 34 in one
    # document, whose figures were on disk exactly where the preamble said.
    all_paths = list(dict.fromkeys(all_paths))
    found = []
    for t, text in texts.items():
        mine = calls(text, source=str(t.relative_to(src_dir)))
        # Its own directory first (a relative reference beats a declared path),
        # then the declared paths against both the file and the tree root --
        # a chapter in a subdirectory may mean either.
        roots = ([t.parent] + [t.parent / g for g in all_paths]
                 + [src_dir] + [src_dir / g for g in all_paths])
        zipsrc = is_texzip_tex(t, src_dir)
        for c in mine:
            c["mathpix_texzip"] = zipsrc
            c["region"] = region_tuple(c["file"])
            r = resolve(c["file"], roots)
            c["resolved"] = str(r.relative_to(src_dir)) if r else None
            c["bytes"] = r.stat().st_size if r else None
        found.extend(mine)
    return {
        "tex_files": len(texs),
        "author_tex_files": sum(1 for t in texs if not is_texzip_tex(t, src_dir)),
        "graphicspath": list(dict.fromkeys(all_paths)),
        "calls": found,
    }


def summarise(scanned: dict, author_only: bool = True) -> dict:
    """Counts over the AUTHOR's inclusions by default.

    MathPix's own tex.zip is excluded unless asked for: its inclusions are
    crops of the page, not figures the author wrote, and mixing them makes the
    author's figure count wrong in the direction that looks like more work.
    """
    c = scanned["calls"]
    if author_only:
        c = [x for x in c if not x.get("mathpix_texzip")]
    return {
        "texzip_calls": sum(1 for x in scanned["calls"]
                            if x.get("mathpix_texzip")),
        "calls": len(c),
        "resolved": sum(1 for x in c if x["resolved"]),
        "unresolved": sum(1 for x in c if not x["resolved"]),
        "with_trim_or_clip": sum(1 for x in c if x["has_trim_or_clip"]),
        "in_figure": sum(1 for x in c if x["in_figure"]),
        "in_tikzpicture": sum(1 for x in c if x["in_tikzpicture"]),
        "overlay_node": sum(1 for x in c if x["overlay_node"]),
        "bare": sum(1 for x in c if not x["in_figure"]
                    and not x["in_tikzpicture"]),
        "distinct_files": len({x["file"] for x in c}),
    }

_CAPTION = re.compile(r"\\caption\*?\s*(?=[\[{])")


def captions(text: str) -> list:
    r"""Every `\caption{...}` with its character offset, brace-matched.

    `\caption[short]{long}` carries an optional short form first, and a
    caption body routinely contains braces (`\gls{nmf}`, `$x^{2}$`), so the
    body cannot be taken with `\{([^}]*)\}`.
    """
    out = []
    for m in _CAPTION.finditer(text):
        i = _skip_ws(text, m.end())
        if i < len(text) and text[i] == "[":
            _, i = _matched(text, i, "[", "]")
            i = _skip_ws(text, i)
        body, _ = _matched(text, i, "{", "}")
        if body is not None:
            out.append({"pos": m.start(), "text": body})
    return out


#: LaTeX a caption carries that OCR renders as its plain content, or drops.
_MACRO_ARG = re.compile(r"\\(?:gls|Gls|acrshort|acrlong|acrfull|emph|textit|"
                        r"textbf|texttt|rev|text|mbox|ensuremath)\s*\{")
_ANY_CMD = re.compile(r"\\[a-zA-Z@]+\*?")
_WS = re.compile(r"\s+")


def plain(text: str) -> str:
    r"""A caption reduced to the words OCR would have read.

    `\caption{\rev{F1-Score of \acrshort{nmfft} for various models}}` and the
    OCR's "F1-Score of NMF-FT for various models" must reduce to something a
    substring test can align. Macro ARGUMENTS are kept (they are printed);
    the macro names and the braces are not.
    """
    prev = None
    while prev != text:
        prev = text
        m = _MACRO_ARG.search(text)
        if m:
            inner, end = _matched(text, m.end() - 1, "{", "}")
            if inner is not None:
                text = text[:m.start()] + inner + text[end:]
    text = _ANY_CMD.sub(" ", text)
    text = text.replace("{", " ").replace("}", " ").replace("$", " ")
    text = re.sub(r"[^0-9A-Za-z ]+", " ", text)
    return _WS.sub(" ", text).strip().lower()


def enclosing_span(text: str, pos: int, env: str = "figure"):
    r"""The `\begin{env}...\end{env}` span containing `pos`, or None."""
    starts = [m.start() for m in
              re.finditer(r"\\begin\s*\{" + env + r"\*?\}", text)
              if m.start() < pos]
    if not starts:
        return None
    b = starts[-1]
    m = re.search(r"\\end\s*\{" + env + r"\*?\}", text[b:])
    e = b + m.end() if m else len(text)
    return (b, e) if b <= pos < e else None


_NODE = re.compile(r"\\node\b")
_DRAW = re.compile(r"\\draw\b")


def tikz_siblings(text: str, pos: int) -> dict:
    r"""What else the enclosing tikzpicture draws besides this inclusion (335).

    A picture placed by a node with NO siblings is just an image with extra
    steps — the tikzpicture adds nothing a reader can see. A picture with
    sibling `\node`s or `\draw`s is the annotation-over-figure case: the
    author drew ON the image, so the page shows something the base file does
    not, and a crop of the page is not a crop of the file.

    The node holding the inclusion is not counted as its own sibling.
    """
    span = enclosing_span(text, pos, "tikzpicture")
    if not span:
        return {"nodes": 0, "draws": 0, "siblings": 0}
    body = text[span[0]:span[1]]
    own = 0
    m = re.search(r"\\node\b[^;]*$", text[span[0]:pos])
    if m:
        own = 1                       # the \node whose body is this image
    nodes = max(0, len(_NODE.findall(body)) - own)
    draws = len(_DRAW.findall(body))
    return {"nodes": nodes, "draws": draws, "siblings": nodes + draws}
