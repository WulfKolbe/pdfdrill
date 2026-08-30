# Failure classes

Each is stated as a rule, with the instance that cost enough to learn it.
Most were found more than once.

## Silent success

**A build that succeeds while losing content is the dominant failure here.**

- `(not rendered)` placeholders measured as if they were mathematics — 63 of
  401 component-class findings, and they ranked *first* in a queue sorted by
  distance
- a missing preamble package dropping 967 equations, while every isolated
  reproduction succeeded because isolation used the *healthy* path
- `\begin{Form}` omitted, so AcroForm fields vanish with **no warning in the
  log** and the PDF builds
- `pdfdrill model` printing "Built unified model" on a no-op
- a fallback font that is a **text** font switch and does nothing inside `$...$`
- four escape flags sent as the strings `"true"`/`"false"`, where the one asked
  to be **off** is the one that is **on** — in a write-only field whose only
  witness is the shape of the output three months later

`\mathbb{1}` is the purest instance: it compiles with zero errors and sets a
negated turnstile. Not a missing glyph — **a different valid symbol**.

## Population errors

**A threshold fitted on one document describes that document.** `0902.0431`
supplied 37% of one measurement and 19% of another.

**A pooled ratio and a per-unit paired test can point opposite ways.** Pooled
17.2% against an 11.5% null inverted to z = −4.88 per row.

**A ratio whose denominator excludes most of the population is not a rate.**
74% of rows had no rule to be near.

**Always report with-and-without** for any document supplying more than ~15% of
rows. And **narrowing a population until a knee appears is choosing the
population from the answer**.

## Positional keys

**They fail whenever a collection can change length.** `sorted()[18]`, report
column indices, a compare table keyed on `(type, flow_index)` reporting 501
phantom changes after six objects were inserted, a longtable continuation
footer displacing one row per page break. A multiset diff needs neither stable
ids nor stable positions.

**And a key that looks unique often isn't**: a title prefix matching the wrong
book, `glob("*.lines.json")[0]` in a folder holding several, a tex.zip present
in both `texzip/` and `texsrc/` so every crop counted twice.

## A check that shares the error it checks for

**It confirms the error instead of catching it.**

- a retrofit reported "stripped from 0 files" and "already had one: 0", both
  computed with the same double-escaped pattern that made the operation fail.
  Only asking *how many files carry two stamps* found it — 151
- two concurrent runs whose **compile counts agreed exactly**, because xelatex
  never read the shared PNGs, while every ink number diverged 2–4×
- a hardcoded `False` for `scale_stable`, whose resulting "zero S corpus-wide"
  was then cited as evidence the branch could not fire
- two link checkers agreeing at zero, because one required a `.md` suffix and
  so never saw the LaTeX that produced the other's 33

## A comparison of two different quantities

**It produces a confident, meaningless number.** Raw `cell_grid` under an old
rule against fully-filtered output under a new one made 47 of 50 pages look
changed — the filters were the only difference. Make the rule an argument so
both sides run through identical filtering.

## Absence proves nothing

**A corpus scan cannot prove absence.** `"equation"`, `"figure"` and
`"caption"` occur zero times in `lines.json` but are emitted by the visionocr
route and asserted by tests. Removing them turned the suite red.

**A type-level contract cannot see a field-level gap.** Every type carrying
`subtype` was claimed, so 1.2M unread values sat under a green check.

**Replaying a branch is not running the pipeline.** A `font_size` claim of
34,128 was really 2, because `HeaderProcessor` returned early on 79% of
headers.

**An empty class in a two-class comparison is the first thing to check** — a
detector that included the equation's left-hand side made "delimited, nothing
outside" unreachable.

**And the shape of an output is often the tell**: 210 of 210 rows in one class,
or every figure scoring identically, is a broken count rather than a finding.

## Audits

**An audit claiming something is unhandled must show the handler failing**, not
the handler's absence from where it was expected. `code` was called "dropped
entirely" when 43,553 of 44,689 lines already survived; `molecule` when
`PictureProcessor` had always matched it; `figure_label`'s meaning was asserted
from its name without reading a single value.

## Fallbacks

**A fallback is often the defect.** An image index falling back to the page's
first image gave same-size figures the same wrong filename — and *a named
source that can be the wrong picture is worse than none*.

**Prefer a property of the thing over a measurement of its neighbours**:
containment over a size floor, content over a width floor, a shape test over a
height threshold. And **provenance stays unrecorded rather than wrong**.

## Consumers that cannot audit

**A weak signal must not be shipped to a consumer that cannot check it.** An
LLM told *"a space is required at character 14"* cannot tell a measured space
from a collapsed median. It would place the command, the LaTeX would compile,
and the output would look correct.

**A model told something false about a picture it can see is worse off than one
told nothing.** Hence: an *around* row carries a direction; an *overlapping*
row says overlapping and invents nothing.

## Shell and tooling

- `pkill -f` with a pattern matching its own command line **kills the shell** —
  twice in one day, taking a running corpus pass with it
- `until ! pgrep -f "..."` where the watcher's own command line contains the
  pattern **can never terminate**
- `;` between a test run and `git commit` masks the exit code; a red suite was
  pushed that way
- `ps aux` truncates the command column, so a liveness check reported a running
  process as dead
- git does not support **trailing comments** in `.gitignore`, so annotating
  patterns inline turned `build/tw/` into a pattern matching nothing and
  committed the residue the cleanup existed to remove
- a shared work directory produced an image that looked like a perfectly good
  measurement **of something else** — page 260 of one book served as page 313
  of another
