"""The verdict every run ends with: REACHED, DEGRADED or NOT REACHED.

A projection used to say "Integrity OK" and exit 0 on a model the maths gate
had flagged. The reader of the file, often an LLM, could not see that the
inline mathematics in it was never read. The verdict states it in the output,
in the file and in the exit code.

It is not a new score. It repeats what the run already recorded:

- no model, or a model without text      -> NOT REACHED
- the maths gate's NEEDS_VISION_OCR fact,
  or a maths-bearing document whose model
  holds no formula and no equation        -> DEGRADED, maths unread
- otherwise                               -> REACHED

Whether the reading is the same ink as the page is the judge's finding
(`inkcmp-judge`), and pdfdrill does not run the judge. Every line therefore
says "ink: not judged" until a judged result is handed in (`judged=True`).
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

REACHED = "REACHED"
DEGRADED = "DEGRADED"
NOT_REACHED = "NOT REACHED"

#: 3 is already `drill`'s "a lane was reported and not run". NOT REACHED is a
#: different statement (the run finished and holds no reading), so it has its
#: own code.
EXIT = {REACHED: 0, DEGRADED: 4, NOT_REACHED: 5}

MARK = "pdfdrill verdict:"

#: Readings that hold boxes and no characters.
GEOMETRY_ONLY_SOURCES = ("yolo-geometry",)


class Verdict(NamedTuple):
    state: str
    missing: tuple
    judged: bool = False

    @property
    def exit_code(self) -> int:
        return EXIT[self.state]

    def line(self) -> str:
        parts = list(self.missing)
        if not self.judged:
            parts.append("ink: not judged")
        return f"{MARK} {self.state}" + (" — " + "; ".join(parts) if parts else "")


def decide(has_text: bool, maths_unread: bool, judged: bool = False,
           unread_chars: int = 0) -> Verdict:
    if not has_text:
        return Verdict(NOT_REACHED, ("text: no reading",), judged)
    missing = []
    if unread_chars:
        # U+FFFD in the projection: the reader met a glyph it has no character
        # for and said so. That is recorded in the text itself.
        missing.append(f"text: {unread_chars} unread character(s) (U+FFFD)")
    if maths_unread:
        missing += ["inline math: unread", "display math: unread"]
    return Verdict(DEGRADED if missing else REACHED, tuple(missing), judged)


def unread_chars(files) -> int:
    """U+FFFD count of the first projection that exists."""
    for f in files:
        try:
            return Path(f).read_text(encoding="utf-8").count("\ufffd")
        except OSError:
            continue
    return 0


def assess(pdf: Path, sc, files=()) -> Verdict:
    """The verdict for a document, from its sidecar and its projections."""
    counts = sc.get_evidence("model_object_counts", None) or {}
    has_text = bool(sc.has("MODEL_BUILT")) and any(
        counts.get(t, 0) for t in ("Paragraph", "Abstract", "Section", "ListItem",
                                   "Table", "Equation", "Formula"))
    if sc.has("MODEL_BUILT") and not counts:
        has_text = True          # a model built by a route that records no counts
    # The geometry-only lane draws boxes and reads no character: its lines
    # carry no text by construction (docs/LANES.md, lane 5).
    if (sc.get_evidence("model_source", None) or "") in GEOMETRY_ONLY_SOURCES:
        has_text = False
    maths_unread = bool(sc.has("NEEDS_VISION_OCR"))
    if has_text and not maths_unread and counts \
            and not (counts.get("Formula", 0) + counts.get("Equation", 0)):
        try:
            from . import mathqc
            maths_unread = bool(mathqc.is_math_bearing(pdf, sc)[0])
        except Exception:                                      # noqa: BLE001
            pass
    return decide(has_text, maths_unread,
                  unread_chars=unread_chars(files) if has_text else 0)


def stamp(path: Path, v: Verdict) -> bool:
    """Write the verdict as the first line of a projection; replace an older one."""
    path = Path(path)
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    if lines and MARK in lines[0]:
        lines = lines[1:]
        if lines and not lines[0].strip():
            lines = lines[1:]
    head = ("> " + v.line()) if path.suffix == ".md" else v.line()
    new = head + "\n\n" + "\n".join(lines)
    if new != text:
        path.write_text(new, encoding="utf-8")
    return True


def finish(result, v: Verdict, files=()):
    """A command's output with the verdict appended, the files stamped, and the
    exit code set. A non-zero code the command already carries is kept."""
    from .cli import Report
    for f in files:
        stamp(f, v)
    code = getattr(result, "exit_code", 0) or v.exit_code
    return Report(f"{result}\n{v.line()}", code)
