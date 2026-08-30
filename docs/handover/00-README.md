# pdfdrill / inkdrill — handover

Written 2026-08-30. Four files, read in order.

| file | what it holds |
|---|---|
| `01-state.md` | where each workstream stands, what is running, what is blocked |
| `02-mathpix.md` | the vendor correspondence: eight defects, five withdrawals, what they confirmed |
| `03-constants.md` | every measured number that a later task must not re-derive by guess |
| `04-lessons.md` | the failure classes, each with the instance that taught it |

## Who does what

**Wulf** audits. He does not write the code; the CLIs do.

**Two Claude Code CLIs**, one per repo (`pdfdrill`, `inkdrill`), plus one for
LLMWiki. Each has a heavily reduced input budget, so tasks are written **one
atomic step per message**, ending with *"Commit, push, then stop."* Results go
to `out/NNN.txt` in the relevant repo.

A CLI that refuses a task, or reports that the task's premise is false, is
doing the job. That has happened perhaps fifteen times in this sequence and
was right nearly every time.

## The three standing rules

**Read before building.** `docs/TRANSCLUSION.md`, `docs/layers/`, and
`pdfdrill --help`. Capabilities have been reinvented at least three times
because nothing forced a look — `cmd_tiddlers`, `cmd_okf`, and the
declared-column check that had already been specified and left unbuilt.

**Measure before claiming.** An audit saying something is unhandled must show
the handler failing, not the handler's absence from where it was expected.
Three of my own task descriptions were wrong this way.

**A fact that lives only in a chat is a fact that will be lost.** The durable
places are `corpus_types.json`, the field contract, `commands.yaml`, and the
props inventory — all generated, all committed, all machine-checked.

## Repos and artefacts

- `github.com/WulfKolbe/pdfdrill` — the pipeline
- `github.com/WulfKolbe/inkdrill` — the ink measurement
- `pdfdrill.github.io/reports/` — eleven published QC reports
- `github.com/WulfKolbe/GA` — the wiki, with an `audit/` review channel
- `~/pdfdrill-library/` — ~1,350 drilled documents, one folder each
