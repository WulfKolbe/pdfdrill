# HANDOVER

Current state, current blocker, next task. Nothing else — the per-task
evidence lives in `out/NNN.txt` and `~/pdfdrill-library/out/NNN/`, and the
rules learned by defect are in **`docs/HANDOVER-RULES.md`**.

Last updated 2026-09-12, after task 676. Tasks 649-676 are this session's
run: the projection defect set (649-653), the size budget and the conserve
gate (654-656), the "(not rendered)" causes (659-668), the ink/crop identity
work (667, 670, 671), the marks command (672, 673), and the transclusion
scope work (674-676).

---

## Where the 20 published documents stand

Twenty documents are published. `penev_A` and `pdf-dc99cf88` are **retired**
from the set by decision, not by failure — the population is 20, and a check
that still reports 21 is reading a stale list. Verify with:

    python3 tools/publishcheck.py --list ~/pdfdrill-library/out/documents.json

Per document the site carries:

    evidence-equation.pdf   every display equation, six columns, unbounded
    evidence-formula.pdf    every inline formula; Page/Conf./Image are the
                            HOST LINE's, and the file says so
    evidence-table.pdf      every table, region rendered from the PDF
    evidence-image.pdf      every image region
    residuals.pdf           the action list: Corrected, Unresolved, Flagged,
                            Low confidence, Doubted — worst first
    report.pdf              retired from reading; kept as the ink chain's
                            measure build
    inspect.html            the docmodel browser (page / reflow / tree)
    formula-report.html     tables.html    <slug>.md
    report.build.json       report.ink.json

Evidence is for lookup, residuals for reading. The site copies are
Ghostscript /ebook derivatives under `<doc>/published/`; `publishcheck`
compares against `published/` when it exists.

    pdfdrill evidence <pdf> --all-kinds --pdf     # every kind, then the PDFs
    pdfdrill marks <pdf> --build                  # 673: inkdrill's marks
    pdfdrill residuals <pdf> --pdf
    pdfdrill publishready <pdf>

`report`, `breport`, `inkreport` are aliases; `reporttex` is superseded for
reading. The reports read the Document (`src/pdfdrill/reports/`), never
tiddlers, and take identifiers from `tiddlywiki.math_titles` /
`region_titles`.

Residuals are **measured on display equations only**. The 36,041 inline
formula rows have never been measured; the residuals header states when the
equations were measured and against which model.

---

## The rule that governs what may be transcluded

**674/676.** Math on a table cell, a section heading, a title, a TOC entry, a
figure label or inside a CAPTION is never an inline formula and never becomes
a `{{…||FO}}` transclusion. `src/docmodel/line_types.py` is the single
source of truth: five families named after the sentence that asked for them,
16 MathPix line types, plus `caption_anchors(doc)` for the caption span —
which is a Paragraph property (`kind: "caption"`), not a line type, because
MathPix types most captions plain `text`.

Five readers, because 1,367 models on disk predate the gate:

    docmodel/modules/formula.py       the object is never created (THE fix)
    docops/projectors/tiddlywiki.py   no substitution, and no residual FOX
    docops/projectors/latex.py        no standalone `$x$` in the .tex body
    pdfdrill/inlinectx.py             the host line is the first PROSE one
    pdfdrill/reports/from_document.py the row is not published

**675.** Refusing a transclusion leaves MathPix's own `\(...\)` in the text,
and TiddlyWiki's KaTeX does not render it. `src/docops/mathdelims.py`
converts it in place to the `<$latex .../>` widget every projection already
converts FROM — three named policies, wired at `tiddlywiki._t`. That renders
math without creating an object, so the refusal holds.

**A model rebuild is deferred.** Gate 1 only takes effect on a rebuilt model,
and a rebuild renumbers FO identifiers, which invalidates every crop and
every ink row keyed on them (667). Gates 2-5 make every published surface
correct without it. `math_titles` is deliberately untouched for the same
reason.

---

## The measurement chain, as it now works

    reporttex --cellrect   phase 1 (the MEASURE build, still report.pdf):
                           full listing, legend off, bullets off. Emits
                           pdfdrill-rows.json.
    inkdrill compare       per page, 300 vs 600 dpi
    inkmeasure.measure     claims each lattice row by the rect that CONTAINS it
    inkconvert             pairs by identifier; report.ink.json carries
                           measured_against {built_at, model_sha256, model_mtime}
    residuals              reads the ink as it stands; --measure runs the chain
    publishready           artefacts, glyphs, ink, timestamp, coverage, crops

Invariants worth keeping:

- **`zeroScan` must be 0** on the measure build.
- **The ink's `model_sha256` equals the model's** — the timestamp gate.
- **`fresh_ink` asks six content questions**, the sixth being
  `report_tex.geometry_signature()`, an AST hash of the functions that
  decide report layout (670). A layout change now invalidates a measurement.
- **The crop cache is keyed on `(page, region)`**, not on the filename (671).
- **A published row's crop must be the one the ink measured** (667,
  `reports.gate.crop_gate`, whose `GateStatus.verified` distinguishes
  "asked and passed" from "nothing to ask about").

## The size budget

**655.** `src/pdfdrill/reports/budget.py` picks a crop rung so an artefact
fits its budget: scale/quality down a fixed ladder, 1.00/q75 (62% of
original) to 0.42/q70 (17%, = 105 dpi, the floor). `conserve` is a gate with
a checked-in baseline (`src/docops/conserve.py`,
`conserve_baseline.json`) — a projection that drops objects a previous one
carried fails rather than shipping.

## inkdrill

Consumed as a **subprocess, never an import** — `docs/inkdrill-integration.md`
has the contract. `INKDRILL_ROOT` locates it; `INKDRILL_HOME` is a
deprecated alias that warns. `pdfdrill marks` (673) runs
`tools/formulamarks.py`, parses its stdout apart from its progress stderr,
and writes `marks.json` beside the document. inkdrill keys books by the
LIBRARY FOLDER NAME, pdfdrill by the site slug; the two differ for every
Z-Library book, and `inkmarks.resolve_key` tries both and says which matched.

---

## Current blocker

**Nothing is blocking the 20.** The 676 republish is the open action:
rebuild evidence + marks per document, copy to `~/pdfdrill.github.io`, push.

---

## Next task

- **Branch cleanup and the merge to main.** `main` and `master` are
  identical; which is authoritative is the user's decision. The working
  branch is `eqblobs-and-gzip-tex`, a fast-forward ahead.
- **Listings** — MathPix math expressions that are really algorithmic
  structure tables should be detected as images. The user's named next goal.
  676's caption work is the shape this wants: a TYPE, not another exclusion.
- **Inline formula measurement**, and with it moving the measure build from
  `report.pdf` to `evidence-equation.pdf`.
- **The 38 rows with no prose-typed occurrence** (676 B4, ruled and recorded,
  not closed) and **the ~11 dropped headings with no owner object** (676 B6).
- Unopened by instruction: the 58 rewritten-reading rows; the 10 empty-LaTeX
  equation objects.

---

## Three things that cost the most time here

**Report first, build second.** Every defect that cost a full run came from
specifying against data nobody had read. The environment map in 628 fired on
zero rows of 660,504.

**A number computed across build generations is not a measurement.** 575 put
a build stamp in every model for this reason; the same class recurred as a
manifest describing a build that no longer existed.

**Six subagent reports in one session had a central claim that failed on
checking** — hence rule 19. Check the number before reading the sentence
built on it, including your own.
