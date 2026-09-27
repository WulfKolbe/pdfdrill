# Transclusion in the model — design

> *"'rebuilds prose from the line stream by offsets' indicates for me that the
> docmodel structure has no transclusions at all because it keeps the input
> immutable. The immutable input for a translation is a text with transclusions
> and the output is again a text with transclusions … I would like get a
> translation inside the docmodel structure so that we have page numbers and
> headers and footers fixed during the translation for re-alignment of the text
> versions. The final result should be a LaTeX out with much better LaTeX
> properties as the input, including BibTeX data in bib files and glossaries and
> symbol table and all internal links of the original document. For all this we
> need transclusions."*

The diagnosis is correct and is the root of the audit's F6. This is the design
that follows from it. Nothing here is implemented yet.

## 1. What is true today

**Transclusion is a projector artifact, not a model fact.** The TiddlyWiki
projector builds `subs_by_line` — `{line anchor: [(offset, length,
replacement)]}` — and splices `{{title||TPL}}` into a paragraph rebuilt from the
immutable `mathpix_lines` stream. Offsets index *that line's* text. Nothing about
a transclusion is stored.

Consequences, each already observed:

| observed | cause |
|---|---|
| a translated `props["text"]` never reaches the tiddlers (audit F6) | the projector reads the stream, not the prop |
| a ListItem's math is a `<$latex>` widget where a Paragraph's is a transclusion (`docs/HANDOVER.md`) | offsets are per-line; a ListItem's content is a *join* of its children |
| `tiddlers` must warn "the wiki has reverted to the ORIGINAL language" | same |
| the translation is kept alive by a tiddler-level pass **plus** a memory file | two mechanisms because the model holds neither |

**What already exists and must be built on, not beside:**

- `Stream` / `Anchor` / `Realization(role=…)` / `Alignment(kind, left, right)`.
  Derived text already gets its own stream: **121 `dehyphenated_para_*` and 105
  `latex_fo_*` streams** on `1-s2.0-S2590118425000565-main` alone. The pattern
  this design needs is the pattern the model already uses.
- `Alignment` is live for `geometry`, `cites`, `image_region` — and for nothing
  else. `kind="translation"` is a new value, not a new mechanism.
- `heading_cleanup.materialize_transclusions` — writes the projected marker text
  back into `props["text"]`. The bridge exists; it stores a **string**.
- `latex_pipeline` — already turns markers into `\Expr{i}` + a `.dat` array
  (define once, reference by index), emits the `\cite` map and `02-bibliography.bib`.
  Its own docstring names `03-glossary.tex` as "next".
- `transclusion_render` — renders markers to other forms (`typed_gloss`).
- `TEMPLATES` in `tiddlywiki.py` — the per-template rendering, keyed `FO`, `FREF`,
  `CIT`, `FN`, `PIC`, `DIA`, `TAB`, `REF`.
- **Page, header and footer objects are already pinned**: no `Page` entry exists
  in `_TRANSLATE_MODEL_FIELD`, so translation never touches them. Half the
  re-alignment requirement holds today.

## 2. The segment contract

A prose object's text becomes a list of segments. This is the whole design; the
rest follows.

```python
props["segments"] = [
    {"t": "text", "s": "The energy "},
    {"t": "ref",  "obj": "obj_ab12", "tpl": "FO"},
    {"t": "text", "s": " grows as "},
]
```

- `t` is `"text"` or `"ref"`. No other kind; a third would be a new contract.
- `"text"` carries `s`, the literal prose. **Only these are translatable.**
- `"ref"` carries `obj` (the target DocObject id) and `tpl` (the rendering
  template, a key of `TEMPLATES`). It carries **no text**: the text is the
  target's, and duplicating it is how the two drift apart.
- Concatenating the rendered segments reproduces the prose. `props["text"]` stays
  as the **rendered-flat** form for readers that want a plain string, derived
  from the segments and never the source of truth.

**Why a list rather than the marker string we already have.** A string needs a
regex in every reader (there are at least four today: `latex_pipeline._MARKER`,
`transclusion_render`, `conserve`, `okf`), it cannot say where a ref *is* without
re-deriving an offset, and it cannot survive an edit — which is exactly what a
translation is.

**Identity.** `obj` is the DocObject id, not the tiddler title. A title is a
*rendering* of identity (`title_for` numbers objects per type in flow order), so
a title-keyed ref breaks the moment numbering shifts. Titles stay where they
belong — in the projectors.

## 3. Translation

The requirement — *input with transclusions, output with transclusions* — is
satisfied structurally: a translator never sees a `ref`, so it cannot damage one.

**The constraint that kills the naive implementation.** Text segments cannot be
translated independently and reassembled. Word order moves *across* a ref:

```
DE  "die Energie \(E\) wächst"      → segments: ["die Energie ", ref, " wächst"]
EN  "the energy \(E\) grows"         — fine
DE  "\(E\) ist die Energie"          → EN "the energy is \(E\)"   ← ref MOVED
```

Sending `"die Energie "` and `" wächst"` as two strings yields two fragments no
grammar joins. So **the whole prose of an object is sent as one string with each
ref rendered as an untranslatable placeholder**, and the reply is re-segmented.

DeepL supports this directly: `tag_handling=xml` with `ignore_tags`
(their published API; **not measured here** — the first implementation task is a
one-call probe that proves a tag survives a real round trip).

```
send:   The energy <x i="1"/> grows as <x i="2"/>.
        tag_handling=xml   ignore_tags=x
reply:  Die Energie <x i="1"/> wächst wie <x i="2"/>.
re-segment on <x i="…"/> → segments, refs restored by index
```

**Where the translation lives.** A second realization, following the pattern the
model already uses for derived text:

```python
Realization(stream=f"translated_{lang}_{n:04d}", role="translated",
            props={"lang": "EN-US", "source_lang": "DE"})
```

with the translated segments in that stream's payload, and

```python
Alignment(kind="translation",
          left=Range(stream="mathpix_lines", start=…, end=…),   # the source
          right=Range(stream="translated_EN-US_0001"),          # the target
          props={"lang": "EN-US", "refs": [obj ids, in order]})
```

`refs` is the re-alignment key the user asked for: the refs are **identical in
both languages and in the same order**, so they are fixed points. Page numbers,
headers and footers are fixed points too — they are never translated, so a
`Page` object's own text is the same in both versions.

**A round trip that must hold, and must be a test:** segments → tagged string →
(identity translator) → re-segment → the original segment list, byte for byte.
A translation that cannot survive an identity function cannot survive DeepL.

### The `text_source` collision, fixed by construction

`_source` is written by **two** passes today:
`materialize_transclusions` stores the pre-transclusion original under
`text_source`, and `translate` stores the pre-**translation** original under the
same key and *skips any object that already has it*. On a cleaned document
translate therefore skipped every materialised paragraph: **74 of 175 fields
translated, 95 of 105 long paragraphs left German, and success reported**
(recorded in `tests/test_translate.py::test_translate_is_not_fooled_by_a_
materialised_source_field`).

With segments the collision cannot arise: the source language is a *realization*,
not a shadow field. `text_source` is then only a compatibility artifact and
`_TRANSLATE_FIELD` / `_TRANSLATE_MODEL_FIELD` — the two hand-synced maps that
disagree about `listitem` (audit F7) — collapse into one question: *does this
object have segments?*

## 4. What each projector does with a ref

One structure, rendered per the user's three rules. The rules stop being three
implementations.

| projector | a `ref` becomes | rule |
|---|---|---|
| tiddlywiki | `{{<title_for(obj)>||<tpl>}}` | mandatory (R1) |
| latex | `\Expr{i}` into the `.dat` array; `CIT`→`\cite{key}`; `FREF`→`\ref{label}` | optional (R2) |
| markdown | rendered in place — `\(…\)`, `![](crop)`, `[n]` | never (R3) |
| llm_compact | `**F12**` + the appendix | its own form (R5) |
| llm_text / plaintext | expanded inline | — |
| okf | `![](url)` / plain text | — |

`docmodel/line_types.py` already decides *whether* a host may transclude (674/676
— never on a table cell, heading, caption…). That gate is unchanged and runs at
segment-BUILD time: a refused host gets one `text` segment with the mathematics
rendered in place, which is what `mathdelims` does today.

## 5. The LaTeX endgame

With refs carrying object identity, the four outstanding outputs are lookups
rather than new machinery:

- **`.bib` file** — `latex_pipeline` stage 02 exists. A `CIT` ref names a
  Reference object; its `bibtex` prop is the entry. Already gold via
  `cmd_bibliography`.
- **Internal links** — a `FREF`/`EQ`/`PIC`/`TAB` ref names an object, and an
  object that is referenced needs a `\label`. `\ref`/`\autoref` then point at it.
  This is why the input's links can be *improved* on: a PDF's links are
  annotations, while these are structural.
- **Glossary** — `latex_pipeline` stage 03, already planned there, reusing
  `semantic.stex`. A glossary entry is a repeated term; `src/semantic/` and
  `src/vocabnet/` already hold the vocabularies.
- **Symbol table** — **nothing exists** (`\gls` appears nowhere in `src/`). The
  symbol table is the set of distinct `FO` refs whose LaTeX is a single symbol,
  which the `.dat` array already dedupes by content. It is the smallest of the
  four once segments exist.

## 6. Migration

**1,494 models on disk.** None has segments.

- `segments` is **optional**. An object without it behaves exactly as today —
  `props["text"]` is read, the projector re-derives. No model is invalidated and
  no rebuild is forced.
- A builder pass mints segments from what the TiddlyWiki projector already
  computes (`_build_inline_subs`), so the first implementation *reuses the
  existing offset logic once* instead of writing a second one. That is the only
  place offsets survive, by design: they are how segments are built, not how they
  are stored.
- `docmodel.prop_contract` holds `docs/layers/PROPS.md` to the corpus, so
  `segments` gets a row there stating who writes it and who reads it.
- A model rebuilt with `model --force` gains segments. Ordering is not a
  migration: readers prefer segments and fall back.

## 7. Risks

- **Every projector's prose path changes.** The mitigation is that segments are
  optional and each projector gains one `if segments:` branch, measured against
  its current output document by document before the fallback is removed.
- **`_build_inline_subs` is the only correct offset logic and it is per-line.**
  A ListItem's content is a join of its children, which is exactly why its math
  is a widget today. Building segments for a ListItem therefore needs the join to
  be offset-aware — the same fix the HANDOVER item names, and it is a
  prerequisite, not a side effect.
- **DeepL's tag handling is documented, not measured.** First task, one call.
- **`Range` addresses a stream by anchors**, and a translated segment list is not
  anchored per segment. Approach C (a segment stream with one anchor per segment)
  would fix that at the cost of the heaviest re-plumbing; this design instead
  puts the segment list in the stream's payload and accepts that a Range names
  the whole translated realization rather than a span inside it. If per-segment
  addressing is ever needed, C is the upgrade path and this contract does not
  block it.

## 8. Order of work

1. Probe DeepL's `tag_handling`/`ignore_tags` with one call. Everything depends on it.
2. The segment contract in `docmodel` + the identity round-trip test.
3. The builder, reusing `_build_inline_subs`; measure segment counts against
   today's transclusion counts per document (`156` on 60cfff3d1e0c8 is the
   number to reproduce).
4. TiddlyWiki reads segments when present — output must be **byte-identical** to
   today on a corpus sample. This is the safety gate for everything after it.
5. Translation on segments; `Alignment(kind="translation")`; retire the
   tiddler-level pass and the `text_source` overload.
6. LaTeX: `\label`/`\ref` from refs, then glossary (stage 03), then the symbol
   table.
7. Markdown and the rest read segments; remove the fallbacks last.

Step 4 is the gate. If the TiddlyWiki output is not byte-identical, the segment
builder is wrong and nothing later is trustworthy.
