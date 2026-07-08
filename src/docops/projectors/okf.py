"""
OKF (Open Knowledge Format) projector — docmodel → an OKF bundle.

OKF (GoogleCloudPlatform/knowledge-catalog okf/SPEC.md) is one Markdown-with-YAML-
frontmatter file per knowledge unit; the ONE conformance rule is a non-empty `type`
in every non-reserved file's frontmatter. Cross-links are plain markdown links
`[t](./other.md)`; `index.md` is reserved (the directory listing).

This is the tiddler bundle we already build, RE-SERIALIZED: `tiddlers_to_okf` takes
the tiddler list the TiddlyWiki projector produces and emits OKF files (frontmatter
instead of a `.md.meta` sidecar; a mandatory `type` from the tiddler's kind-tag;
`{{title||TPL}}` transclusions → `[label](./title.md)` links). The `.md` files show
in drillui's Outputs and render in its markdown view like any other `.md`.
"""
from __future__ import annotations

import posixpath
import re
from collections import OrderedDict
from typing import Any

from ..base import BaseProjector

_TRANSCLUDE_RE = re.compile(r"\{\{([^{}]+?)\}\}")
_RESERVED = {"index.md", "log.md"}
# TiddlyWiki template name → a human link label (the relationship is prose, per OKF)
_LABELS = {"FO": "formula", "FREF": "formula", "EQ": "equation", "EQBLOCK": "equation",
           "PIC": "picture", "DIA": "diagram", "CIT": "citation", "FN": "footnote",
           "PROOF": "proof", "TPL": "unit"}

# OKF allows files "at any directory level" — organise units into per-type folders
# so the bundle isn't one flat pile. OKF type → folder name (irregulars mapped; the
# default pluralises the lowercased type).
_TYPE_DIR = {"Formula": "formulas", "Equation": "equations", "Paragraph": "paragraphs",
             "Section": "sections", "Reference": "references", "Citation": "citations",
             "Table": "tables", "Picture": "figures", "Diagram": "figures",
             "Footnote": "footnotes", "Page": "pages", "Concept": "concepts",
             "Abstract": "abstract", "Toc": "toc", "Sidenote": "sidenotes",
             "Listitem": "lists", "Algorithm": "algorithms", "Theorem": "theorems",
             "Proof": "proofs", "Kitem": "kitems"}

# TiddlyWiki WIDGETS that leak from the tiddler bodies — converted to Markdown so an
# OKF bundle is pure Markdown (no `<$link>`/`<$image>`/`<$latex>` syntax).
_LINK_RE = re.compile(r'<\$link\s+to="([^"]*)"\s*>(.*?)</\$link>', re.S)
_LINK_SELF_RE = re.compile(r'<\$link\s+to="([^"]*)"\s*/>')
_IMAGE_RE = re.compile(r'<\$image\s+source="([^"]*)"[^>]*?/?>')
_LATEX_RE = re.compile(r'<\$latex[^>]*>(.*?)</\$latex>', re.S)
_ANY_WIDGET_RE = re.compile(r'</?\$[a-zA-Z]+[^>]*>')


def _type_dir(typ: str) -> str:
    return _TYPE_DIR.get(typ, (typ or "unit").lower() + "s")


def _link_path(target: str, title_to_path: dict, from_path: str) -> str:
    """RELATIVE OKF link from the source file `from_path` to the target unit by
    title (`../formulas/D_FO0001.md`, `./formulas/…` from the root index), or a
    tolerated relative dead link when the target isn't in the bundle."""
    p = title_to_path.get(target)
    if not p:
        return f"./{target}.md"
    rel = posixpath.relpath(p, posixpath.dirname(from_path) or ".")
    return rel if rel.startswith(".") else "./" + rel


def _widgets_to_markdown(text: str, title_to_path: dict, from_path: str) -> str:
    """Convert every TiddlyWiki widget to Markdown: `<$link to="X">L</$link>` →
    `[L](rel/path)`, `<$image source="U">` → `![](U)`, `<$latex>B</$latex>` →
    `$B$`; strip any leftover widget tag so no `<$…>` survives."""
    text = _LINK_RE.sub(
        lambda m: f"[{m.group(2).strip()}]({_link_path(m.group(1), title_to_path, from_path)})", text)
    text = _LINK_SELF_RE.sub(
        lambda m: f"[{m.group(1)}]({_link_path(m.group(1), title_to_path, from_path)})", text)
    text = _IMAGE_RE.sub(lambda m: f"![]({m.group(1)})", text)
    text = _LATEX_RE.sub(lambda m: f"${m.group(1).strip()}$", text)
    return _ANY_WIDGET_RE.sub("", text)


# --- YAML frontmatter (precise, so a URI's scheme-colon stays unquoted) ---------
def _scalar(s: Any) -> str:
    s = str(s)
    special = bool(s) and s[0] in "[{\"'#&*!|>%@`?,-"
    if "\n" in s or ": " in s or s != s.strip() or s.endswith(":") or special:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'
    return s


def _fm_block(fm: "OrderedDict") -> str:
    lines = ["---"]
    for k, v in fm.items():
        if v is None or v == "" or v == []:
            continue
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(_scalar(x) for x in v)}]")
        else:
            lines.append(f"{k}: {_scalar(v)}")
    lines.append("---")
    return "\n".join(lines)


# --- tiddler → OKF -------------------------------------------------------------
def _is_template(t: dict) -> bool:
    """A TiddlyWiki template/widget tiddler is machinery, not a knowledge unit."""
    ct = (t.get("type") or "").lower()
    return "vnd.tiddlywiki" in ct or "template" in (t.get("tags") or "").split()


def _okf_type(t: dict) -> str:
    """OKF's required `type` = the DocObject kind, which is the tiddler's first tag
    (formula/equation/paragraph/reference/table/section/…). Default 'Concept'."""
    tags = (t.get("tags") or "").split()
    return tags[0].capitalize() if tags else "Concept"


def _first_sentence(text: str, limit: int = 160) -> str:
    s = " ".join((text or "").split())
    cut = s.find(". ")
    if 0 < cut < limit:
        return s[:cut + 1]
    return s[:limit]


def _rewrite_transclusions(text: str, t: dict, title_to_path: dict, from_path: str,
                           as_link: bool = True) -> str:
    """`{{title||TPL}}` → `[label](rel/folder/title.md)` (relative; or the bare
    `label` when `as_link=False`, for a frontmatter description); `{{!!field}}` →
    the tiddler's own field value (a section's `! {{!!caption}}` inlines caption)."""
    def repl(m: "re.Match") -> str:
        body = m.group(1).strip()
        if body.startswith("!!"):
            return str(t.get(body[2:], "") or "")
        target = body.split("||")[0].strip()
        tpl = body.split("||")[1].strip() if "||" in body else ""
        label = _LABELS.get(tpl, tpl.lower()) or target
        return (f"[{label}]({_link_path(target, title_to_path, from_path)})"
                if as_link else label)
    return _TRANSCLUDE_RE.sub(repl, text or "")


def _to_markdown(text: str, t: dict, title_to_path: dict, from_path: str) -> str:
    """Full body conversion: transclusions + TiddlyWiki widgets → Markdown."""
    return _widgets_to_markdown(
        _rewrite_transclusions(text or "", t, title_to_path, from_path),
        title_to_path, from_path)


def _strip_md_links(s: str) -> str:
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)          # images → gone
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)   # links → their label


# extra tiddler fields worth preserving as OKF custom keys (OKF: preserve unknowns)
_KEEP_FIELDS = ("refnum", "page", "section_number", "level", "citekey", "year",
                "entry_type", "equation_number", "kind", "language")


def _okf_body(t: dict, typ: str, title_to_path: dict, from_path: str) -> str:
    text = _to_markdown(t.get("text") or "", t, title_to_path, from_path)
    latex = (t.get("latex") or "").strip()
    if typ in ("Formula", "Equation") and latex:
        display = bool(t.get("displayMode")) or typ == "Equation"
        return f"$$ {latex} $$" if display else f"${latex}$"
    if typ == "Table":
        return "# Schema\n\n" + text
    if typ == "Reference":
        body = "# Citations\n\n" + text
        bib = (t.get("bibtex") or "").strip()
        if bib:
            body += "\n\n```bibtex\n" + bib + "\n```"
        return body
    return text


def _okf_file(t: dict, bibkey: str, timestamp: str, title_to_path: dict) -> str:
    typ = _okf_type(t)
    from_path = title_to_path[t["title"]]
    title = t.get("caption") or t.get("title") or ""
    latex = (t.get("latex") or "").strip()
    desc = t.get("caption") or (latex or _first_sentence(_strip_md_links(
        _to_markdown(t.get("text") or "", t, title_to_path, from_path))))
    tags = [x for x in (t.get("tags") or "").split()]
    if bibkey and bibkey not in tags:
        tags.append(bibkey)
    resource = (t.get("canonical_uri") or t.get("_canonical_uri")
                or f"pdfdrill:{bibkey}/{t.get('title', '')}")
    fm: "OrderedDict" = OrderedDict()
    fm["type"] = typ                              # REQUIRED, always non-empty
    fm["title"] = title
    fm["description"] = desc
    fm["resource"] = resource
    fm["tags"] = tags
    fm["timestamp"] = timestamp
    for k in _KEEP_FIELDS:                        # preserve extra fields
        if t.get(k) not in (None, ""):
            fm[k] = t[k]
    return _fm_block(fm) + "\n\n" + _okf_body(t, typ, title_to_path, from_path) + "\n"


def _index_md(units: list, bibkey: str, meta: dict, timestamp: str,
              title_to_path: dict) -> str:
    fm: "OrderedDict" = OrderedDict()
    fm["type"] = "Document"
    fm["title"] = meta.get("title") or bibkey
    fm["description"] = meta.get("description") or meta.get("abstract") or ""
    fm["tags"] = [bibkey] if bibkey else []
    fm["timestamp"] = timestamp
    if meta.get("num_pages"):
        fm["pages"] = meta["num_pages"]
    out = [_fm_block(fm), "", f"# {meta.get('title') or bibkey}", ""]
    groups: "OrderedDict" = OrderedDict()
    for t in units:
        groups.setdefault(_okf_type(t), []).append(t)
    for typ, items in groups.items():
        out.append(f"## {typ} ({len(items)})")
        for t in items[:500]:
            cap = str(t.get("caption") or t.get("title") or "")[:80].replace("\n", " ")
            out.append(f"- [{cap or t.get('title')}]({_link_path(t.get('title'), title_to_path, 'index.md')})")
        out.append("")
    return "\n".join(out)


def tiddlers_to_okf(tiddlers: list, bibkey: str, meta: dict,
                    timestamp: str) -> "dict[str, str]":
    """The pure core: a tiddler list → an OKF bundle {relative_path: content}.
    One `<title>.md` per non-template tiddler + a reserved `index.md`."""
    units = [t for t in tiddlers if not _is_template(t) and t.get("title")]
    # Per-type folder layout + a title→path map, so cross-links resolve to the
    # right subfolder as bundle-absolute OKF links (`/formulas/D_FO0001.md`).
    title_to_path = {t["title"]: f"{_type_dir(_okf_type(t))}/{t['title']}.md"
                     for t in units}
    bundle: "dict[str, str]" = {}
    for t in units:
        bundle[title_to_path[t["title"]]] = _okf_file(t, bibkey, timestamp,
                                                      title_to_path)
    bundle["index.md"] = _index_md(units, bibkey, meta or {}, timestamp,
                                   title_to_path)
    return bundle


class OKFProjector(BaseProjector):
    """Projects a Document into an OKF bundle (dict path→content) by re-serializing
    the TiddlyWiki tiddler list."""

    def output_extension(self) -> str:
        return ".okf"

    def project(self, doc: "Any") -> "dict[str, str]":
        import json
        from datetime import datetime, timezone
        from .tiddlywiki import TiddlyWikiProjector
        from ..base import OperatorConfig

        tj = TiddlyWikiProjector(OperatorConfig(
            op="projector", classname="TiddlyWikiProjector", params={})).project(doc)
        tiddlers = json.loads(tj)
        bibkey = doc.meta.get("bibkey", "DOC")
        ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return tiddlers_to_okf(tiddlers, bibkey, doc.meta, ts)
