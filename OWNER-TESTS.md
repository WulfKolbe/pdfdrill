# OWNER-TESTS — the commands the owner types, and what must appear

One line each. **No paths, no prefixes, no environment variables, no flags you
were not told to use.** Type the line in any empty folder. `pdfdrill selftest`
runs exactly these lines and checks exactly these expectations.

Owner, 2026-11-10: *"I have lost more less any trust in the CLIs ... I want to
call basic program code and see the results ... organize tests that does not
use any path, prefixes, or complex command lines."*

Every line prints the code it ran on first:

    pdfdrill main 0b4a6926 2026-11-10

`MODIFIED` is appended when the working tree differs from that commit, and
`NOT ON MAIN` when the commit is not on `origin/main`. If you see either, the
program is not what `origin/main` holds — which is the whole point of the line.

---

## A. Does it run at all (offline, no key, no network)

| # | command | what must appear |
|---|---|---|
| A1 | `pdfdrill doctor` | a `Code:` block naming entry point, branch, commit, tree, origin/main; then `System tools:` with `pdftotext`, `gs`, `pdfinfo` all `[OK ]` |
| A2 | `pdfdrill config` | `config file :` and a `library_root` |
| A3 | `pdfdrill help` | the command list, and no Python traceback |
| A4 | `pdfdrill nonsense-command` | `Unknown command: nonsense-command`, and exit 1 — not a traceback, and not silence |

## B. Does it read a document it already has (offline, no key)

These name a document by its bare arXiv id. Nothing is downloaded if the
library already holds it; `pdfdrill` resolves the id itself.

| # | command | what must appear |
|---|---|---|
| B1 | `pdfdrill size 2209.02970` | `21` pages |
| B2 | `pdfdrill route 2209.02970` | a named lane, and the words `text layer` or `LaTeX` |
| B3 | `pdfdrill steps md 2209.02970` | `prerequisites satisfied` — NOT a plan containing `model` (that was defect D3) |
| B4 | `pdfdrill fonts 2209.02970` | a font table including a `MicrosoftYaHei` row |

## C. Does it produce the output, and quickly

| # | command | what must appear |
|---|---|---|
| C1 | `pdfdrill md 2209.02970` | `Markdown from the author's LaTeX source`, a `.md` written, **in under 10 seconds** (it took 476 s before defect D2 was fixed) |
| C2 | `pdfdrill model 2209.02970` | an object count including `Paragraph`, and `source='latex'` |

**C1's time limit is the test.** The command returned the right bytes before D2
was fixed; what was wrong was that it took eight minutes, so drillui killed it
at 180 s and the owner saw a timeout. A test that only checked the output would
have passed throughout.

## D. Known not to run yet

| # | command | why it is NOT RUN |
|---|---|---|
| C1, C2, D1 | `pdfdrill md 2209.02970`, `pdfdrill model 2209.02970` | The preflight gate exits 2 with *"BLOCKED until you attest that you read the SKILL"*. The attestation is per working directory, so it must be repeated in every new folder. An owner decision is open: gate only non-interactive callers, let the acceptance runner alone bypass it, or drop it. Until then `pdfdrill acceptance` reports these lines as NOT RUN rather than passing or failing them. |

| D2 | *no command at all* | **No pdfdrill command names a non-math font, or any font's encoding.** `pdfdrill fonts` answers "Uses 89 font families. including math fonts (CMMI6, …)" and `pdfdrill fonts_layer` answers "Found 92 font records across 90 families. Math fonts: 6 (…)". Both read all 92 records; neither names one that is not a math font. So the owner cannot discover from any command that this document carries `BCDFEE+MicrosoftYaHei`, `CID TrueType`, `Identity-H`, `uni no` — the row that predicts the 216 glyphs dropped from page 1 (defect D1). Recorded as a known gap (defect D5); not fixed. |

A line that cannot run is **NOT RUN**. It is not a pass, and `pdfdrill acceptance` says so
in its summary rather than leaving it out — a test suite that quietly omits what
it cannot do reports a health it has not measured.
