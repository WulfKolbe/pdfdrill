"""Namespace a dvisvgm SVG's internal ids so several can share one document.

dvisvgm names its glyph paths per FILE — `<path id="g0-48" …/>` referenced by
`<use xlink:href="#g0-48"/>` — so the names restart at g0-1 in every figure it
renders. Inline two of them into one HTML page and the second figure's `use`
elements resolve to the FIRST figure's glyphs, because an id is document-global
and the first definition wins.

Measured on kolbe2018hubbard: 9 inline SVGs, 25 ids defined more than once
(`page1` nine times), and 112 of 336 glyph references — 33% — drawing a glyph
from a different figure. It is silent: the figure renders, with wrong letters.

Found by the external `drillcheck` audit (`svg_idns.py`), whose interface
contract this implements.

    namespace_svg_ids(svg, token) -> svg with every id and every LOCAL fragment
    reference prefixed by `token`.

A reference to an id this document does not define is left alone: a dangling
reference must stay dangling rather than silently start resolving elsewhere.
"""
from __future__ import annotations

import re

_ID_DEF = re.compile(r"""\bid\s*=\s*(['"])([^'"]+)\1""")
_FRAG_REF = re.compile(r"""\b(xlink:href|href)\s*=\s*(['"])#([^'"]+)\2""")
_URL_REF = re.compile(r"""url\(\s*#([^)\s]+)\s*\)""")
_TOKEN_OK = re.compile(r"^[A-Za-z0-9_-]+$")


def collect_ids(svg: str) -> set[str]:
    """Every id DEFINED in this SVG."""
    if not isinstance(svg, str):
        return set()
    return {m.group(2) for m in _ID_DEF.finditer(svg)}


def safe_token(raw: str) -> str:
    """A DocObject id reduced to the id-prefix charset, never empty."""
    t = re.sub(r"[^A-Za-z0-9_-]+", "", str(raw or ""))
    return (t or "x") + "-"


def namespace_svg_ids(svg: str, token: str) -> str:
    """Prefix every id and every local fragment reference with `token`."""
    if not isinstance(svg, str) or not svg:
        return svg
    if not _TOKEN_OK.match(token or ""):
        raise ValueError(f"token must match [A-Za-z0-9_-]+, got {token!r}")
    defined = collect_ids(svg)
    if not defined:
        return svg

    def _def(m):
        q, name = m.group(1), m.group(2)
        return f"id={q}{token}{name}{q}"

    def _frag(m):
        attr, q, name = m.group(1), m.group(2), m.group(3)
        return m.group(0) if name not in defined else f"{attr}={q}#{token}{name}{q}"

    def _url(m):
        name = m.group(1)
        return m.group(0) if name not in defined else f"url(#{token}{name})"

    out = _ID_DEF.sub(_def, svg)
    out = _FRAG_REF.sub(_frag, out)
    return _URL_REF.sub(_url, out)


def inline_body(svg, token: str | None = None) -> str:
    """A dvisvgm document reduced to its root `<svg>` element, ready to inline.

    `token` namespaces the ids — pass one whenever the result shares a document
    with another SVG, which is every caller that inlines more than one.
    """
    if not isinstance(svg, str):
        return ""
    i = svg.find("<svg")
    if i < 0:
        return ""
    j = svg.rfind("</svg>")
    body = svg[i:j + 6] if j > i else svg[i:]
    return namespace_svg_ids(body, token) if token else body
