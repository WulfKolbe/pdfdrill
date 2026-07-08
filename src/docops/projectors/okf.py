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


def _rewrite_transclusions(text: str, t: dict, as_link: bool = True) -> str:
    """`{{title||TPL}}` → `[label](./title.md)` (or the bare `label` when
    `as_link=False`, for a frontmatter description); `{{!!field}}` → the tiddler's
    own field value (so a section's `! {{!!caption}}` inlines its caption)."""
    def repl(m: "re.Match") -> str:
        body = m.group(1).strip()
        if body.startswith("!!"):
            return str(t.get(body[2:], "") or "")
        target = body.split("||")[0].strip()
        tpl = body.split("||")[1].strip() if "||" in body else ""
        label = _LABELS.get(tpl, tpl.lower()) or target
        return f"[{label}](./{target}.md)" if as_link else label
    return _TRANSCLUDE_RE.sub(repl, text or "")


# extra tiddler fields worth preserving as OKF custom keys (OKF: preserve unknowns)
_KEEP_FIELDS = ("refnum", "page", "section_number", "level", "citekey", "year",
                "entry_type", "equation_number", "kind", "language")


def _okf_body(t: dict, typ: str) -> str:
    text = _rewrite_transclusions(t.get("text") or "", t)
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


def _okf_file(t: dict, bibkey: str, timestamp: str) -> str:
    typ = _okf_type(t)
    title = t.get("caption") or t.get("title") or ""
    latex = (t.get("latex") or "").strip()
    desc = t.get("caption") or (latex or _first_sentence(
        _rewrite_transclusions(t.get("text") or "", t, as_link=False)))
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
    return _fm_block(fm) + "\n\n" + _okf_body(t, typ) + "\n"


def _index_md(units: list, bibkey: str, meta: dict, timestamp: str) -> str:
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
            out.append(f"- [{cap or t.get('title')}](./{t.get('title')}.md)")
        out.append("")
    return "\n".join(out)


def tiddlers_to_okf(tiddlers: list, bibkey: str, meta: dict,
                    timestamp: str) -> "dict[str, str]":
    """The pure core: a tiddler list → an OKF bundle {relative_path: content}.
    One `<title>.md` per non-template tiddler + a reserved `index.md`."""
    units = [t for t in tiddlers if not _is_template(t) and t.get("title")]
    bundle: "dict[str, str]" = {}
    for t in units:
        fname = f"{t['title']}.md"
        if fname in _RESERVED:                    # never clobber a reserved name
            fname = f"{t['title']}_.md"
        bundle[fname] = _okf_file(t, bibkey, timestamp)
    bundle["index.md"] = _index_md(units, bibkey, meta or {}, timestamp)
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
