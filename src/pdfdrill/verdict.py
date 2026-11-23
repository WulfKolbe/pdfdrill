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
(`inkcmp-judge`). T-0153 #2: pdfdrill runs it when, and only when, one is
configured (`pagejudge.judge_path` — `PDFDRILL_JUDGE`, then the config key
`judge`, then nothing), and then ITS NUMBERS DECIDE:

- the judge faulted ink      -> DEGRADED, with its own counts, exit 4
- the judge found none       -> REACHED, exit 0
- no judge, or a page it
  could not measure          -> "ink: not judged", exactly as before

The middle case is the point. `REACHED` means "nothing known missing", and on
a page the judge has just faulted that is false — so a verdict that could not
see the judge was making a promise it had no way to keep (coordinator,
T-0153 #2).

A CLEAN JUDGEMENT ALSO CLEARS THE MATHS WARNING. `maths_unread` is a guess
from the document's fonts; the judge is a measurement of the same page's ink.
When the judge says every glyph is accounted for, the guess has been answered.
"""
from __future__ import annotations

import re
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
    #: `pagejudge.Ink`, when a judge ran. It owns the "ink:" clause.
    ink: "object | None" = None

    @property
    def exit_code(self) -> int:
        return EXIT[self.state]

    def line(self) -> str:
        parts = list(self.missing)
        if self.ink is not None:
            parts.append(self.ink.line())
        elif not self.judged:
            parts.append("ink: not judged")
        return f"{MARK} {self.state}" + (" — " + "; ".join(parts) if parts else "")


def decide(has_text: bool, maths_unread: bool, judged: bool = False,
           unread_chars: int = 0, ink=None) -> Verdict:
    if not has_text:
        return Verdict(NOT_REACHED, ("text: no reading",), judged, ink)
    # THE JUDGE DECIDES WHEN IT HAS MEASURED THE PAGE. `ink.faults is None`
    # means it could not (FONT_UNMAPPED / NOT_COMPILED / NO_TEXT, or it did not
    # run): that is an absence of evidence, so the model's own counts answer,
    # as they always did.
    if ink is not None and getattr(ink, "faults", None) is not None:
        if ink.faults:
            return Verdict(DEGRADED, (), judged, ink)
        # Clean ink answers the maths guess too — see the module docstring.
        return Verdict(REACHED, (), judged, ink)
    missing = []
    if unread_chars:
        # U+FFFD in the projection: the reader met a glyph it has no character
        # for and said so. That is recorded in the text itself.
        missing.append(f"text: {unread_chars} unread character(s) (U+FFFD)")
    if maths_unread:
        missing += ["inline math: unread", "display math: unread"]
    return Verdict(DEGRADED if missing else REACHED, tuple(missing), judged,
                   ink)


#: Two or more letters or digits in a row: a word, as opposed to a bullet, a
#: table rule or a lone page number.
_A_WORD = re.compile(r"[^\W_]{2,}")


def _has_words(f) -> bool:
    """Does this projection hold words of the DOCUMENT's own?

    Every line carrying the verdict's own mark is dropped first. `stamp()`
    prepends it, so the file a second run reads begins with the sentence that
    says there is no reading, and "NOT", "REACHED", "text" and "judged" are
    all words by any test that does not know to skip them.
    """
    try:
        text = Path(f).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    body = "\n".join(l for l in text.splitlines() if MARK not in l)
    return bool(_A_WORD.search(body))


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
    # T-0153 — A PROJECTION WITH WORDS IN IT IS A READING.
    #
    # `has_text` came only from `MODEL_BUILT` and the model's object counts,
    # and `md` writes an `md` layer and NO model. So, measured on a fresh
    # folder (coordinator, on ada1b845):
    #
    #   $ pdfdrill md 1805.01788-p0003.pdf                        exit=5
    #   Extracted 2963 words of Markdown across 3 pages. Detected 75 inline
    #   and 1 display math expressions, 17 references.
    #   pdfdrill verdict: NOT REACHED — text: no reading; ink: not judged
    #
    # A run that read the whole document reported that it had read nothing, on
    # the first command a user is likely to type — and `has_text` False also
    # skips the judge, so the line said "not judged" WITH one configured.
    #
    # THE WORD COUNT IS TAKEN FROM THE LAYER, NOT FROM THE FILE, and that is
    # not a detail: `stamp()` writes the verdict INTO the projection, so on a
    # second run the file BEGINS with "NOT REACHED — text: no reading". A
    # reading inferred by reading the file would infer it from the sentence
    # saying there is none. `set_layer("md", …)` records `words` at write
    # time, before any stamp.
    # `getattr`, not `sc.layers`: this function asks a sidecar only for what it
    # needs, and it did not need the layers before. The suite's own stub
    # sidecar (`test_every_output_carries_its_verdict._SC`) implements `has`
    # and `get_evidence` and nothing else, which is a fair record of the
    # contract that existed — and requiring a new attribute that this test can
    # do without would be production code made fragile to please itself.
    _layers = getattr(sc, "layers", None) or {}
    if not has_text:
        for _name in ("md", "mmd"):
            if int((_layers.get(_name) or {}).get("words") or 0) > 0:
                has_text = True
                break
    # ...and for a projection that records no count of its own (`llmtext`
    # writes `*.llm.txt`), the file is read — with every verdict stamp dropped
    # first, for the reason above.
    if not has_text and files:
        has_text = any(_has_words(f) for f in files)
    # The geometry-only lane draws boxes and reads no character: its lines
    # carry no text by construction (docs/LANES.md, lane 5). It is a VETO and
    # it runs last, so a projection built from it cannot vote around it.
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
                  unread_chars=unread_chars(files) if has_text else 0,
                  ink=_ink_for(pdf, sc) if has_text else None)


def _ink_for(pdf: Path, sc):
    """Run the configured ink judge over this document, or None.

    T-0153 #2. Nothing happens unless `PDFDRILL_JUDGE` or the config key
    `judge` names an executable, so the default install is unchanged and the
    line still reads "ink: not judged".

    THE ROUTE IS THE LANE'S. The judge's glyph route compares the page's own
    glyphs against the reading's; a scan has none to compare, and its scan
    route measures missing ink, invented components and hole mismatches
    instead. Its residual is not comparable with a glyph-route one
    (board_run `_scan1`), which is why `pagejudge.faults` reduces it to a sign
    for this gate and never reports it as a number here.

    The work goes in the SIDECAR's blob directory, not beside the PDF: the
    judge writes page renders of about 15 MB each, and the house rule is no
    stray files in the user's folder.
    """
    try:
        from . import pagejudge
        if pagejudge.judge_path() is None:
            return None
        from .commands import _lines_json_path
        lines = _lines_json_path(pdf)
        pages = int(sc.get_evidence("pages", 0) or 0)
        # THE LANE DECIDES THE ROUTE, NOT `needs_ocr`.
        #
        # Measured on BH1 p113 (acceptance, PDFDRILL_JUDGE set): `needs_ocr` is
        # FALSE for a scan carrying an OCR underlay, because the document does
        # have a text layer -- that is the whole point of T-0153 #1. So the
        # judge took the GLYPH route on a scan and reported 1313 findings,
        # 1308 of them "wrong shape". That is not a finding about the reading;
        # it is the glyph route's assumptions failing on a page whose glyph
        # positions are an OCR estimate. docs/LANES.md and the board both use
        # `--route scan` there, and the board keeps its number in a separate
        # field because the two residuals are not comparable.
        #
        # So the question is asked of the one pure function that owns it.
        from . import ocr_router as _r
        _dec = _r.route_for_sidecar(sc)
        scanned = bool(_dec.underlay
                       or _dec.lane in ("gemma", "mathpix", "geometry"))
        return pagejudge.judge_document(
            pdf, lines, pages,
            route="scan" if scanned else "glyph",
            work=Path(sc.blob_dir) / "judge")
    except Exception:                                        # noqa: BLE001
        # A judge that blows up is not a finding. The line stays "not judged",
        # which is the truth, rather than turning a broken tool into a fault
        # against the reading.
        return None


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
