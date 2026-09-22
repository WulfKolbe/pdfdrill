r"""773 — apply the 696 bracket repair, where the AUTHOR'S SOURCE licenses it.

`brackets.repair()` has existed since 696 and nothing ever called it. The
publish gate names the repair in its own refusal message —

    28 shown reading(s) pair a `\left.` with a typed `\right` while a plain
    opener of that type is open (apply the 696 bracket repair): …

— and there was no command to obey it with. Same shape as `listing_cell`
(695a) and `brackets.repair` itself: written, tested, unreachable.

WHAT LICENSES THE REPAIR. `refine.chosen_latex` shows a refinement only when
what verified it is evidence about IDENTITY (686), and structural
plausibility is not that. The evidence used here is the author's own e-print,
at DOCUMENT scope: if `\left.` does not occur in it at all, then no `\left.`
in any reading of that document is the author's, and deleting one cannot be
changing what he wrote. On 1205.5935v1 (Chisolm, *Geometric Algebra*) the
e-print is 6,050 lines and contains zero.

That is a narrower claim than "this equation is correct" and a stronger one
than per-equation matching can make here: 9 of that document's 28 repairable
readings are multi-row `aligned` blocks MathPix merged, which `injectlatex`
never paired with a source equation, so there is no per-equation gold for
them at all.

A document whose author DOES write `\left.` is refused outright. There the
basis does not hold and the repair needs per-equation evidence, which this
module does not attempt.
"""
from __future__ import annotations

import datetime
import gzip
import tarfile
from pathlib import Path

#: What the repair is recorded as having been verified by. In
#: `refine.IDENTITY_EVIDENCE`, so `chosen_latex` will show the result.
VERIFIED_BY = "source"


def author_source(doc_dir: Path) -> "tuple[str, str]":
    r"""(text, filename) of the author's e-print, or ("", "").

    NEVER the `.tex.zip` — that is MathPix's own reconstruction (065), and a
    repair verified against it would be verified against the reading it is
    repairing.
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
                    return "".join(out), p.name
        except Exception:                                  # noqa: BLE001
            continue
    for p in d.glob("*.gz"):
        if p.name.endswith((".tgz", ".tar.gz")):
            continue
        try:
            return gzip.decompress(p.read_bytes()).decode("utf-8", "replace"), p.name
        except Exception:                                  # noqa: BLE001
            continue
    return "", ""


def basis_holds(src: str) -> bool:
    r"""Does the document-scope claim hold: the author never writes `\left.`?"""
    return bool(src) and "\\left." not in src


def candidates(doc, src_file: str) -> list:
    r"""[(object id, original, repaired, pairs)] for every repairable reading.

    A repair may not turn a RENDERING row into a non-rendering one. It is not
    asked to rescue a row that already did not render: 1205.5935v1_EQ0357
    fails `display_safe` before AND after, on a `sized_type_mismatch` this
    repair does not touch, and refusing it there would leave the one defect
    the repair does fix standing in a row nobody can read either way.
    """
    from . import brackets, refine, report_tex as rt
    out = []
    for oid, obj in doc.objects.items():
        if obj.type not in ("Equation", "Formula"):
            continue
        shown, _ev = refine.chosen_latex(obj)
        if not brackets.repairable(shown):
            continue
        cand, pairs = brackets.repair(shown)
        if not pairs or cand == shown or brackets.repairable(cand):
            continue
        if not rt.display_safe(cand) and rt.display_safe(shown):
            continue
        out.append((oid, shown, cand, pairs))
    return out


def proposal(shown: str, cand: str, pairs: int, src_file: str) -> dict:
    """The record `refine.record_one` wants, saying what actually verified it."""
    return {
        "proposed": cand,
        "verified_by": VERIFIED_BY,
        "basis": "source",
        "author": "pdfdrill 696 bracket repair",
        "at": datetime.datetime.now(datetime.timezone.utc)
              .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evidence": {
            "source_file": src_file,
            "claim": ("the author's e-print contains no `\\left.` anywhere, so "
                      "the `\\left.` in this reading is not the author's"),
            "left_dot_in_source": 0,
            "pairs_repaired": pairs,
            "original": shown,
        },
    }
