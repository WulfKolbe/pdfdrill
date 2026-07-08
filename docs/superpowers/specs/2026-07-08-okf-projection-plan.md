# Plan — OKF projection (`pdfdrill okf`)

Status: plan. Add an OKF (Open Knowledge Format) projector + command that projects
the docmodel into an OKF bundle, displayed like `.md` files in drillui.

## What OKF is (GoogleCloudPlatform/knowledge-catalog okf/SPEC.md)

**One Markdown-with-YAML-frontmatter file per knowledge unit.** Conformance: every
non-reserved `.md` has parseable YAML frontmatter with a **non-empty `type`** field.
- Frontmatter: `type` (REQUIRED), then recommended `title`, `description`,
  `resource` (URI), `tags` (YAML list), `timestamp` (ISO 8601). Unknown keys must
  be preserved.
- Body: standard Markdown; conventional headings `# Schema`, `# Examples`,
  `# Citations`.
- Cross-links: markdown links — absolute bundle-relative `[t](/tables/x.md)` or
  relative `[t](./other.md)`. The relationship is conveyed by prose.
- Reserved files: `index.md` (directory listing), `log.md` (change history).
- Consumers must tolerate missing optional fields, unknown types, broken links.

## Why this is a small, high-reuse addition

OKF is **the tiddler bundle we already build, re-serialized**: the
`TiddlyWikiProjector` already maps every DocObject → `{title, type, tags, text,
caption, latex, page, …}`, and `tools/tiddlers_to_md.py` already writes one file per
tiddler. OKF differs only in the SERIALIZATION: metadata goes in YAML frontmatter
(not a `.md.meta` sidecar), a `type` field is mandatory, and `{{id||TPL}}`
transclusions become `[caption](./<title>.md)` markdown links. `_ARTIFACT_EXTS`
already includes `.md`, so the bundle shows in drillui's Outputs with no UI change.

## Design

**`src/docops/projectors/okf.py` — `OKFProjector(BaseProjector)`**
`project(doc) -> dict[str, str]` — a BUNDLE `{relative_path: content}`. It consumes
the tiddler list the TiddlyWiki projector already computes (reuse, don't re-walk the
model), then serializes each tiddler to one OKF file.

Per-tiddler → `<title>.md` (title is already bibkey-prefixed, e.g.
`2312.11532_FO0044`):
```
---
type: <DocObject type>            # REQUIRED: Formula / Equation / Paragraph / Section /
title: <human title / caption>    #   Reference / Table / Concept / Theorem / Picture …
description: <caption or first sentence or the latex>
resource: pdfdrill:<bibkey>/<id>  # drill-down handle; cdn_url/canonical_uri for images
tags: [<tiddler tags…>, <bibkey>]
timestamp: <build ISO-8601>
<any extra tiddler fields preserved as custom keys: refnum, page, latex_original, …>
---

<body>
```
Body by type (reusing the tiddler content):
- Paragraph/Abstract/Section → prose; `{{<id>||TPL}}` transclusions rewritten to
  OKF links `[<caption>](./<title>.md)`; a Section body lists its children as links.
- Formula/Equation → the LaTeX as `$$ … $$` (KaTeX-renderable in drillui's md view).
- Table → the markdown table under a `# Schema` heading (OKF's conventional heading
  fits a table's columns exactly).
- Reference → the entry text + the BibTeX under `# Citations`.
- Picture/Diagram → an image link (`![caption](<resource>)`); code-diagram → a fenced
  block.

**Reserved `index.md`** (the Document root): `type: Document`, `title`, `description`
(abstract), `tags: [<bibkey>]`, then a linked TOC — the fractal-index section tree
with `[caption](./<section_title>.md)` links, and per-type counts. This is the
bundle's entry point.

**Reserved `log.md`** (optional, later): the drill provenance (source species, build
timestamp, model_caps) as a change history.

**`cmd_okf(pdf, out=None)`** (fast DocGraph read path; also a combined store):
project → write the bundle under `<drill>/okf/<bibkey>/` (or `--out DIR`) →
report the file count + the `index.md` path. drillui lists the `.md` files
(Outputs panel, `.md` ext) with no change; they render in its markdown view like any
other `.md`. Manifest + skillsync as usual.

## Reuse / new code

Reuse: the TiddlyWiki projector's object→tiddler mapping (title/type/tags/body), its
transclusion regex (rewrite target, not template render), `tools/tiddlers_to_md.py`'s
file-write pattern, `_ARTIFACT_EXTS`/drillui md display. New = `okf.py` (the
frontmatter+link serializer + index.md) + `cmd_okf` + CLI/manifest.

## Test plan (`tests/test_okf.py`, pure/offline over a fixture doc)

- CONFORMANCE: every emitted non-reserved `.md` parses as YAML frontmatter (via
  `yaml.safe_load` on the block) AND has a non-empty `type` — the SPEC's one hard rule.
- field mapping: a Formula file has `type: Formula`, `$$…$$` body, `resource:
  pdfdrill:<bibkey>/<id>`, tags incl. the bibkey.
- cross-links: a Paragraph transcluding a formula emits `[<cap>](./<title>.md)`, no
  raw `{{…||FO}}`; the link target file exists in the bundle.
- a Table renders under `# Schema`; a Reference under `# Citations`.
- `index.md` exists, `type: Document`, links to sections.
- `cmd_okf` writes the bundle + returns the index path; files are under `okf/<bibkey>/`.

## Deferred

- `log.md`; round-trip (OKF → docmodel); the `# Examples` heading (no natural source
  yet); a single-file OKF concatenation (the SPEC is a bundle of files).

## First step

Implement `okf.py` (serializer + index) TDD against the conformance rule, then
`cmd_okf` + wiring, then verify a real bundle renders in drillui.
