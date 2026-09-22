r"""769 — is the author LaTeX on this model actually the AUTHOR's?

`injectlatex` attaches the author's own equation to each matched Equation as a
`latex_eq_<nnnn>` stream realized with role `latex_source`. Everything that
verifies a reading against "the source" reads those streams, so if they hold
MathPix's own reconstruction instead, every such verification compares MathPix
with itself and reads as agreement. That is out/063, and 065's
`author_source.assert_author_source` refuses the `.tex.zip` at ingest time for
exactly this reason.

065 guards the INPUT. Nothing looked at what is already on disk. Measured on
1205.5935v1 (Chisolm, *Geometric Algebra*):

    author's e-print   GA_notes.tex          \left.  x   0
    MathPix's          1205.5935v1.tex.zip   \left.  x 224
    model's latex_eq_0062 stream                     x   2

and the stream's text occurs verbatim (whitespace-normalised) inside the
tex.zip and nowhere in the e-print. The sidecar for that document records
`latex_source = '1205.5935v1.tgz'` -- the right file name over the wrong
file's content, which is worse than no record at all.

This module only ASKS. It reconstructs each injected stream and reports which
of the two candidate sources contains it. Repair is a separate decision,
because for a document with no e-print on disk there is nothing to repair
WITH, and the honest outcome there is to drop the false gold rather than keep
it.
"""
from __future__ import annotations

import gzip
import re
import tarfile
import zipfile
from pathlib import Path

#: Only the equation streams `injectlatex` writes. Named per equation, so the
#: verdict can be per equation rather than per document.
_EQ_STREAM = re.compile(r"^latex_eq_\d+$")

#: How much of a stream to look for in a candidate source. Long enough that a
#: match is not a coincidence, short enough to survive the whitespace the
#: extractor reflows. 120 characters is ~2 lines of LaTeX.
PROBE = 120

#: Below this a stream carries no evidence either way -- `\alpha` occurs in
#: both sources and in every other document.
MIN_TEXT = 24

FROM_ZIP = "mathpix"
FROM_EPRINT = "author"
UNKNOWN = "unknown"


def norm(text: str) -> str:
    """Whitespace-collapsed, for asking whether one text contains another."""
    return re.sub(r"\s+", " ", text or "").strip()


def stream_text(doc, name: str) -> str:
    r"""The text of one injected stream, rebuilt from its per-codepoint payload."""
    st = doc.streams.get(name)
    if st is None:
        return ""
    return "".join((st.payload.get(a) or {}).get("codepoint", "")
                   for a in st.anchors)


def injected_streams(doc) -> list:
    """The names of every `latex_eq_<nnnn>` stream on this model, in order."""
    return sorted((n for n in doc.streams if _EQ_STREAM.match(str(n))),
                  key=lambda n: (len(n), n))


def mathpix_tex(doc_dir: Path) -> str:
    """The text of MathPix's own `<stem>.tex.zip`, or ""."""
    z = next(iter(Path(doc_dir).glob("*.tex.zip")), None)
    if z is None:
        return ""
    try:
        with zipfile.ZipFile(z) as zf:
            return "".join(zf.read(n).decode("utf-8", "replace")
                           for n in zf.namelist() if n.endswith(".tex"))
    except Exception:                                     # noqa: BLE001
        return ""


def author_tex(doc_dir: Path) -> str:
    r"""The text of the author's e-print, or "".

    `.tgz`/`.tar.gz`, and a bare `.gz` because arXiv serves a single-file
    submission as gzip(paper.tex) — 689 found that one. NEVER the `.tex.zip`:
    that is the file this module exists to tell apart.
    """
    d = Path(doc_dir)
    for p in list(d.glob("*.tgz")) + list(d.glob("*.tar.gz")):
        try:
            with tarfile.open(p) as tf:
                out = []
                for m in tf.getmembers():
                    if not m.name.endswith(".tex"):
                        continue
                    f = tf.extractfile(m)
                    if f is not None:
                        out.append(f.read().decode("utf-8", "replace"))
                if out:
                    return "".join(out)
        except Exception:                                 # noqa: BLE001
            continue
    for p in d.glob("*.gz"):
        if p.name.endswith((".tgz", ".tar.gz")):
            continue
        try:
            return gzip.decompress(p.read_bytes()).decode("utf-8", "replace")
        except Exception:                                 # noqa: BLE001
            continue
    return ""


def classify(text: str, zip_text: str, eprint_text: str) -> str:
    r"""Which source contains this stream.

    The e-print wins a tie. MathPix's reconstruction of a paper reproduces
    long stretches of it correctly, so a string in BOTH is not evidence of
    contamination — only a string in the zip and NOT in the e-print is.
    """
    t = norm(text)
    if len(t) < MIN_TEXT:
        return UNKNOWN
    probe = t[:PROBE]
    if eprint_text and probe in eprint_text:
        return FROM_EPRINT
    if zip_text and probe in zip_text:
        return FROM_ZIP
    return UNKNOWN


def audit(doc, doc_dir: Path) -> dict:
    """What the injected author LaTeX on this model actually is.

    {streams, mathpix, author, unknown, has_eprint, verdicts: {stream: verdict}}
    """
    zt = norm(mathpix_tex(doc_dir))
    et = norm(author_tex(doc_dir))
    verdicts = {}
    for name in injected_streams(doc):
        verdicts[name] = classify(stream_text(doc, name), zt, et)
    counts = {FROM_ZIP: 0, FROM_EPRINT: 0, UNKNOWN: 0}
    for v in verdicts.values():
        counts[v] += 1
    return {
        "streams": len(verdicts),
        "mathpix": counts[FROM_ZIP],
        "author": counts[FROM_EPRINT],
        "unknown": counts[UNKNOWN],
        "has_eprint": bool(et),
        "verdicts": verdicts,
    }


def verdict_line(a: dict, bibkey: str = "") -> str:
    """One line a human can act on."""
    if not a["streams"]:
        return "%s: no injected author LaTeX on this model" % (bibkey or "model")
    if not a["mathpix"]:
        return ("%s: %d injected equation(s), none of them MathPix's own output"
                % (bibkey or "model", a["streams"]))
    fix = ("re-run `pdfdrill injectlatex --force` (the author's e-print is here)"
           if a["has_eprint"] else
           "no author e-print on disk: this gold cannot be repaired, only dropped")
    return ("%s: %d of %d injected equation(s) are MathPix's OWN tex.zip, not the "
            "author's — %s" % (bibkey or "model", a["mathpix"], a["streams"], fix))
