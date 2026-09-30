
## 814 — heading weight, and the run-in heading (2026-09-26)

A reader asked whether subsections exist and reported "subsection without
number but indented bold headline, clearly identified because the text ends
with a larger white space and without a point". They do exist — LaTeX's
`\paragraph`, level 4 — and two things stopped us finding them.

### The bold face nobody recognised

`is_bold("NimbusRomNo9L-Medi")` was False. URW named Times' BOLD weight
"Medium", and `\textbf` under `times`/`mathptmx` resolves to `ptmb`, which
embeds as exactly that — pdfLaTeX's default Times substitute, so the commonest
bold face in the corpus. Measured over `probe-pdffonts.txt` for the whole
library: **480 readings in 380 documents**, with `-MediItal` in another 112.

Which weight `Medi` is, settled by co-occurrence rather than by the name: of
393 documents using the family, **376 carry both `-Regu` and `-Medi`** (so Medi
is the bold) and only 4 have `Medi` alone. Scoped to `NimbusRomNo9L` on
purpose — `NimbusSanL` and `NimbusMonL` spell their bold `-Bold`, and a blanket
`medium` rule also matches `NunitoExtraLight-Medium`, `Flama-Ultralight`,
`GoogleSymbolsRounded-Medium`, none of which is bold. `-Bol`, a truncated
`-Bold`, was missing too (`NimbusSan-Bol`, 11 readings).

Effect, `section_header` lines per document:

| document | before | after |
|---|---|---|
| 2609.26891 | 1 | 34 |
| 2510.04618 | 43 | 47 |
| others measured | unchanged | unchanged |

2609.26891 went from ONE heading to 34: `Abstract`, `1 Introduction`,
`4 Case Studies`, `4.1 Long-Horizon with Long-Range Recall`, `5 Related Work`,
`6 Conclusion`, `References`, `B Extensibility via Hooks in JAZ`… every one of
them previously invisible.

### The run-in heading

`\paragraph{Analysis: Finance Benchmark}` sets its title bold at BODY SIZE and
lets the prose run on from it after a 1 em space, so heading and paragraph
share a baseline and therefore one LineNode. `heading_level` asks whether the
LINE is bold; this line is bold only at the front, so the heading was read as
the first three words of a paragraph.

`runin_heading` finds the split. Constants measured on 2510.04618 p7-p9:

- separator gap **9.96-10.21pt at a 10.0pt body size = 1.00 em**
- ordinary inter-glyph gap on the same pages: **median 2.75pt, p90 3.71pt (0.37 em)**
- so the threshold is **0.6 em** — in the empty band between the two
  populations, and relative to the line's own font rather than absolute.

28 found in 2510.04618, all genuine: `Brevity Bias`, `Context Collapse`,
`Evaluation Metrics`, `Base LLM`, `Analysis: AppWorld`,
`Analysis: Finance Benchmark`, `Robustness to Reflection Quality`…
`to_lines_json` emits them as two line records, the heading's rectangle ending
at the last bold glyph and the prose's starting at the first plain one, so the
split is visible in the inspect view and a crop of either is right.

### Why 1-s2.0-S2590118425000565-main is the good test case

Its levels are separated by WEIGHT AND SLOPE, all at one size:

| level | face | size |
|---|---|---|
| section (`2. Background`, `References`) | CharisSIL-**Bold** | 8.0 |
| subsection (`2.1. Conflict-free…`) | CharisSIL-*Italic* | 8.0 |
| body | CharisSIL | 8.0 |

`levels_by_font_size` ranks a document's DISTINCT heading sizes, so this
document yields one rank and its whole tree flattens. Nothing here reads the
italic subsection face yet — `heading_level` tests bold only — which is why
pdf2mmd still types just 2 of its ~19 headings. That is the open item, and the
fix is a slope test beside the weight test, not another size threshold.

### Open, measured, not fixed

- **Italic as a heading weight.** See above: 17 of 19 headings missed on
  1-s2.0-S2590118425000565-main.
- **`1 INTRODUCTION` typed `authors`** on 2510.04618. `_front_matter` runs the
  author block from the line after the title to the first heading on the page —
  and when that heading is not recognised, the block swallows it.
- **Four table header rows typed `section_header`** on 2510.04618
  (`Method GTLabels Test-Normal Test-Challenge Average…`). A guard keyed on
  `table_regions` was written and REMOVED: it suppressed 0 on all five
  documents measured, because `table_regions` finds no table on those pages at
  all (0 on p7, while the MathPix lane reports 7 Tables in the document). The
  root cause is table detection, not heading detection.
- **A bold sentence inside a callout box.** Guarded for the weakest branch
  only — at body size a trailing full stop now refutes a heading (2609.26891
  p2: 36 → 34). A bold sentence without a full stop still passes.
