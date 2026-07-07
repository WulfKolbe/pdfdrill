# `pdfdrill context` — structural projection of the docmodel into an LLM context

Status: approved (brainstorm 2026-07-07). First cut = structural + IDF selection;
per-aspect embedding rankers are a pluggable seam, built later.

## Motivation

PDFDRILL is a **semantic context provider**, not a storage layer. The docmodel is
the canonical IR; every output (markdown, tiddlers, bibtex, LaTeX, an LLM context)
is codegen from it. `context` is the codegen backend that answers a *query* with a
**projection**: a small set of typed docmodel objects rendered to Markdown with
metadata and object ids, capped to a token budget. The LLM sees a projection, never
the whole document and never a filename.

This is a deterministic, **structural RAG retriever**: same shape as embedding RAG
(query → top-k chunks → inject) but retrieval is structural (typed objects + IDF +
type/section/concept filters) and each chunk is a real docmodel object with true
metadata, not an arbitrary text window.

## Command surface

```
pdfdrill context <pdf> ["free-text query"] \
    [--type definition,formula,theorem,figure,table,reference,concept] \
    [--concept "<name>"] \
    [--section <number|caption>] \
    [--k N] [--max-tokens N] [--out FILE]
```

Examples:
- `context heim.pdf --concept "transdimension" --type definition,formula`
- `context 2302.07629.pdf "which alignment metric?" --max-tokens 3000`
- `context paper.pdf --type theorem`

Fast DocGraph read path (auto-builds/refreshes the model like other read commands).
Output: Markdown to stdout, or `--out FILE`.

## Selection (the pluggable part)

Selection = filter ∩ rank, over the retrievable units (`retrieve.gather_units`,
which already yields prose / math-by-LaTeX / concepts / measurement units, each
`{id, type, text}`).

- **Filters** (structural, deterministic): `--type` (DocObject type set), `--section`
  (section_number/parent-section match), `--concept` (the named-concept layer: the
  Concept's definition site + its occurrence objects). Filters compose.
- **Rank**: a free-text query ranks the filtered units. The ranker is a REGISTERED,
  PLUGGABLE component (`RANKERS` dict + `register_ranker(aspect, fn)`), keyed by
  ASPECT. The default `structural` ranker reuses `retrieve`'s IDF scoring (`_index`
  + shared-token IDF sum). With no query, order is flow-order.
  - **Seam for the user's investigation:** future aspect rankers register here
    without touching the projection core — e.g. `register_ranker("math",
    specter2_math_rank)` (allenai/specter2, RobBobin/math-embed on LaTeX),
    `register_ranker("citation", crossref_rank)`. `--aspect math|citation|text`
    (later) picks the ranker; default is `structural`. Rankers are optional and
    lazy — absent deps degrade to `structural`, never a hard failure.

A `Ranker` is `fn(query: str, units: list[dict]) -> list[dict]` returning units with
a `score` field, most-relevant first. That is the ONLY contract embedding engines
must satisfy.

## Rendering

Each selected object → a Markdown block led by a compact metadata comment, then its
content:

```markdown
<!-- id=huh2024_FO0044 type=Formula page=7 section=3.2 refnum=(12) score=1.83 -->
$$ \{\gamma^m,\gamma^n\}=2\delta^{mn} $$
```

Metadata (`page`, `section`, `refnum`) is read from the node props (enriched by an
id→node map; `gather_units` carries only id/type/text). A trailer reports what was
projected and the estimated token count. `--max-tokens` greedily fills to budget
(chars/4 estimate) and states how many units were dropped. Every block carries the
id so the LLM can drill deeper (`pdfdrill <cmd> <pdf>` on that id) — ids, never
filenames.

## Reuse / new code

Reuse: `retrieve.gather_units` + `retrieve._index`/`retrieve` (IDF), `classify.
_strip_latex`, the DocGraph read path, the named-concept layer (`--concept`). New =
one `src/pdfdrill/context.py` (filters + ranker registry + markdown renderer +
token budget) + a thin `cmd_context` + CLI/manifest wiring. No storage, no
embeddings in this cut.

## Deferred

- Embedding rankers (SPECTER2 / math-embed / crossref) — the user is investigating;
  the registry seam is ready for them.
- The SQL-like **projection language** (`FROM…WHERE…PROJECT…FORMAT…LIMIT`).
- `--all-papers` cross-document synthesis (needs `combine`).
- Non-markdown `--format` targets (tiddlers/latex — projectors exist, not wired).
- Persisting projections into the git library (the separate "drill library" spec).

## Test plan

`tests/test_context.py` (pure, offline, a fake doc of typed nodes):
- filter by `--type` (only those types survive);
- `--section` filter;
- `--concept` pulls the concept + its occurrences;
- free-text ranks by IDF (relevant unit first), cites the id;
- markdown block carries the metadata header + id; trailer counts tokens;
- `--max-tokens` truncates and reports the drop;
- ranker registry: a registered fake `aspect` ranker is used; absent → `structural`.
`cmd_context` wiring test (built fixture model → non-empty markdown with ids).
