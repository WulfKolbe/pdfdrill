"""065 — assert a candidate LaTeX source really is the AUTHOR's.

MathPix returns a `<stem>.tex.zip` alongside its `lines.json`. It looks exactly
like an e-print — a zip with a .tex and figures — but it is MathPix's own
reconstruction of the page. Comparing a MathPix reading against it compares
MathPix with itself.

That is not hypothetical. In out/063, `0902.0431.tex.zip` was reached for as
"the author's source"; its only .tex is named `1deb350a-…-153e0bfd7145.tex`,
which is the document's MathPix `image_id`, and line 4651 of it reproduces
MathPix's output character for character — including a printed `0` misread as
the letter `a`. Rendering it as the author's LaTeX would have produced a
near-zero distance and a confident, false conclusion that MathPix matched the
page. The real e-print was the other file, `0902.0431.tgz`, which is not a tar
at all but a single gzipped `SpEcxp.tex`.

`cmd_injectlatex` already PREFERS the e-print, but falls back to the .tex.zip
when no e-print is present — so a document that never had its source fetched
silently acquires MathPix output as its gold reference, and every comparison
downstream reads as agreement. This module makes that refusal explicit and
typed, in the shape `net.NetworkBlocked` uses: named, specific, never a stack
trace.

The test is IDENTITY, not a guess about zip contents: a .tex whose stem is one
of the document's own MathPix image_ids. A UUID-shaped name alone is only a
weak signal and is reported as `suspect`, never as proof.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

#: MathPix names each page image `<uuid>-<page>`; the tex.zip's .tex carries
#: the bare uuid.
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class MathPixSourceRefused(Exception):
    """A candidate 'author' source is MathPix's own output.

    Carries the evidence so the caller can print WHY without re-deriving it.
    """

    def __init__(self, path: Path, reason: str, remedy: str = ""):
        self.path, self.reason, self.remedy = Path(path), reason, remedy
        msg = f"{Path(path).name} is not the author's LaTeX: {reason}"
        if remedy:
            msg += f" {remedy}"
        super().__init__(msg)


def image_ids(lines_json: Path) -> set[str]:
    """Every MathPix image_id in a lines.json, with the page suffix stripped."""
    out: set[str] = set()
    try:
        data = json.loads(Path(lines_json).read_text(errors="replace"))
    except Exception:
        return out
    for page in data.get("pages", []):
        iid = page.get("image_id") or ""
        if iid:
            out.add(iid.rsplit("-", 1)[0])
    return out


def tex_names(path: Path) -> list[str]:
    """The .tex member stems of a zip, or the single stem of a plain .tex."""
    p = Path(path)
    if p.suffix.lower() == ".zip" or p.name.lower().endswith(".tex.zip"):
        try:
            with zipfile.ZipFile(p) as z:
                return [Path(n).stem for n in z.namelist()
                        if n.lower().endswith(".tex")]
        except Exception:
            return []
    if p.suffix.lower() == ".tex":
        return [p.stem]
    return []


def classify(path: Path, known_ids: set[str] | None = None) -> tuple[str, str]:
    """('mathpix' | 'suspect' | 'author', reason).

    'mathpix'  — a .tex named by one of THIS document's image_ids. Identity,
                 not inference.
    'suspect'  — a .tex named by a bare UUID we cannot tie to this document.
                 Reported, never treated as proof: refusing on shape alone
                 would reject an author who happens to name a file that way.
    'author'   — nothing indicates MathPix authorship. Absence of evidence,
                 and the docstring says so rather than promising gold.
    """
    names = tex_names(path)
    if not names:
        return "author", "no .tex member to test"
    ids = known_ids or set()
    for stem in names:
        if stem in ids:
            return "mathpix", (f"its .tex is named {stem}.tex, which is this "
                               f"document's MathPix image_id")
    for stem in names:
        if _UUID.match(stem):
            return "suspect", (f"its .tex is named {stem}.tex — a bare UUID, "
                               f"the shape MathPix uses, but not an image_id "
                               f"of this document")
    return "author", "no .tex member is named by a MathPix image_id"


def assert_author_source(path: Path, lines_json: Path | None = None,
                         known_ids: set[str] | None = None) -> str:
    """Raise MathPixSourceRefused if `path` is MathPix's own reconstruction.

    Returns the classification reason when the source is accepted, so a caller
    can record WHAT was checked rather than only that something was.
    """
    ids = known_ids if known_ids is not None else (
        image_ids(lines_json) if lines_json else set())
    kind, why = classify(path, ids)
    if kind == "mathpix":
        raise MathPixSourceRefused(
            path, why,
            remedy=("Comparing against it compares MathPix with itself. Use "
                    "the author's e-print (.tgz / .tar.gz), or pass an "
                    "explicit --tex."))
    return why
