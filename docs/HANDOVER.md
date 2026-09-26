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

**Nothing is blocking the 20.** `tools/publishcheck.py` is green in both
directions: 20 published, 20 identical, 0 stale, and the 100 superseded
`<doc>/published/` snapshots (214 MB, 09-06) were deleted on 09-14 — every
one had a current twin in its parent folder, and the inventory is in
`out/689-published-leftovers-deleted.txt`.

The **48 held census-verified repairs** are published (690, site 3756a29):
six documents rebuilt, re-measured, READY on all six gates, publishcheck
20/20 identical. The one open item is **`penev_B`**, the 7th planned rebuild,
whose model changed for a reason nobody has explained — explain that before
rebuilding it.

**pdf2mmd** (`~/Downloads/pdf2mmd`, the pdfminer route built in a Claude.ai
chat) is reviewed read-only in `out/690.txt` and deliberately NOT integrated
until it is understood — the user's instruction of 2026-09-14.

---

## Open — a silent partial conversion has no detector

A MathPix conversion can return HTTP success with two thirds of the document
missing, and nothing in the result says so. Measured on
`20260620_Sach_Beitragsrechnung_999391621.pdf` (LVM, 3 pages), both through the
API and by hand in the web app:

| page | fonts | text layer (`pdftotext`) | in MathPix output |
|---|---|---|---|
| 1 | 11 x Type 3 | 2,183 chars | no |
| 2 | 1 x Type 3 | 211 chars | no |
| 3 | 2 x TrueType | 3,387 chars | yes |

Exactly the Type-3 pages are dropped, deterministically — two identical runs
give byte-identical output. 9 of 17 files from that source show the same shape,
each yielding 3.4-3.9 KB and in every case only the final page. The Type 3
fonts are embedded and carry ToUnicode maps, so nothing about the file is
undecodable: poppler reads page 1 without difficulty and pdf2mmd reads 6,187
glyphs across 91 lines with nothing deferred.

`conserve` cannot see this. It checks the model against the projection it
produces — both sides of a document that was already truncated before either
existed. The missing check is PDF -> model, and its input is ALREADY ON DISK
for every document: `probe-page-text.json`, written at acquisition, holds
pdftotext's per-page character count. A page with a substantial text layer and
no model content on it is the signature, and it is one comparison.

What it must NOT be is a ratio over the whole document: page 3 alone is 57% of
this file's characters, so a document-level check passes while two thirds of
the invoice is gone. Per page, or it does not detect the case it exists for.

Wire it where the cost lands: `mathpix` should refuse to report success, and
`status` should carry it, rather than a reader discovering it in a projection.

## Next task

- **LaTeX field promotion** — the user's decision of 2026-09-14, recorded in
  `docs/superpowers/specs/2026-09-14-latex-field-promotion-design.md` and in
  `docmodel.prop_contract`'s docstring. There are already TEN latex-family
  props; pdfminer LaTeX arrives shortly with authoritative symbol names and has
  nowhere to go that any reader looks at. The best reading takes the standard
  name, every other keeps a source-named copy, the WRITER promotes so no reader
  needs a flag. Four measured constraints before implementing — the sharpest
  being that ink measures the UNPROMOTED MathPix reading by name
  (`prefer_refined: False` is deliberate), so the losing copies are not
  history.
- **Listings** — MathPix math expressions that are really algorithmic
  structure tables should be detected as images. The user's named next goal.
  676's caption work is the shape this wants: a TYPE, not another exclusion.
- **The LaTeX projection of a `CodeListing`** — a branch now exists in
  `src/docops/projectors/latex.py`, and the comment above it is the SPEC,
  written from the worked example at `~/pdfdrill-library/lstgold/probe/gh/`
  (read back 16 of 16 on text, indentation and numbering). Four things it
  must keep, each learned by a defect in pdf2mmd 781:
  **the body is the program** — a listing is the opposite of an equation, so
  nothing goes inside it: no `\textcolor`, no escape markers;
  **the style is a header property** — `morekeywords` with a `keywordstyle`,
  `commentstyle`, `stringstyle`, said the way `listings` says it;
  **brace any option value carrying a bracket** — `morekeywords=[1]{for}`
  ends the environment's optional argument at `[1]` and silently drops every
  option after it: the file compiles, the listing sets, nothing is coloured;
  **`firstnumber` is not always 1** — `\lstinputlisting[firstline=10]`
  starts the gutter at 10.
  The probe also covers provenance: a caption that is an `\href` to the
  commit containing the file, with a `#L10-L25` anchor, recoverable only
  from the annotation layer. Its README records that `\href[opts]{url}{text}`
  inside `listings`' `caption=` does NOT work — `#` is TeX's parameter
  character and listings re-reads the caption, so the URL is typeset
  instead of linked.
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

## Open: a ListItem's math is a widget where a Paragraph's is a transclusion (811)

Reported by a consumer of `1-s2.0-S2590118425000565-main`: "list items carry raw
`<$latex>` widgets instead of LaTeX". Measured on that document's tiddlers:

| | n | `<$latex>` | `{{…||FO}}` |
|---|---|---|---|
| paragraph | 74 | 0 | 28 |
| listitem | 106 | 40 | 0 |

`pdfdrill tiddlers` says so itself in its integrity line — *Unreferenced
(emitted, nothing points at them): 49 FO*. Those are the formulas the list items
should be transcluding.

This is a violated contract, not a preference: `src/docmodel/line_types.py`
lists `list_item` among the PROSE types that host a transclusion, and the user's
requirement of 2026-09-2x is that transclusion in TiddlyWiki is mandatory.

**Cause.** `tiddlywiki.py:1514` routes Paragraphs through
`_transclude_paragraph`; ListItems are emitted at ~1837 as
`li.props.get("content", "")` — raw, with `mathdelims`' in-place widget still in
it. Nothing else is wrong.

**Why it is not a one-line change.** `subs_by_line` is keyed by LINE ANCHOR and
holds `(offset, length, replacement)` with offsets into *that line's* text. A
ListItem's `content` is `_from_container`'s JOIN of its children's texts, and its
surface Realization spans only the container anchor (`start == end`), whose own
text is empty. So the offsets need remapping onto the joined string — or the
ListItem's realization needs to span its children, in which case
`_transclude_paragraph` rebuilds the body from lines and re-introduces the
marker text (`1. `) that `content` deliberately strips and the tiddler carries in
its own `marker` field. Either route is a real change with its own regressions;
both need measuring before and after.
