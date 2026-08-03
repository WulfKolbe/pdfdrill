# Transclusion — what it is, and how to check it

Read this before auditing pdfdrill output. Most of the "content is missing"
reports turn out to be transclusion failures, and they are invisible unless you
know what to look for.

## The idea, in one paragraph

**Transclusion is inclusion by reference.** A document does not *contain* a
formula, a table or a figure — it contains a **pointer** to one, and the pointer
is resolved when the document is displayed. The thing itself is stored exactly
once, in its own tiddler, and every place that uses it refers to it.

This is Ted Nelson's term (Project Xanadu, 1980), and TiddlyWiki implements it
natively. It is the reason pdfdrill emits a wiki rather than a flat document:
one formula, one tiddler, N references — edit the formula once and every
occurrence updates.

## What it looks like

A paragraph tiddler's `text` field contains:

```
Let {{2209.00445v3_FO0001||FO}} denote the embedding of {{2209.00445v3_FO0002||FO}},
as reported in {{2209.00445v3_REF_devlin2018||CIT}}.
```

Three things are happening:

| part | meaning |
|---|---|
| `{{ … }}` | TiddlyWiki transclusion syntax |
| `2209.00445v3_FO0001` | the **target** — the title of another tiddler, which holds the actual LaTeX |
| `\|\|FO` | the **template** — how to render it (here: as inline math via `<$latex>`) |

The paragraph stores *neither* the LaTeX nor the rendering. It stores a name.

## The template set

pdfdrill emits 16 templates. Each renders one kind of object:

| template | object | rendered as |
|---|---|---|
| `FO` | Formula (inline math) | `<$latex>` inline |
| `EQBLOCK` | Equation (display math) | centred block + number |
| `FREF` | equation reference | a link to the equation |
| `PARA` | Paragraph | `<p>` |
| `TAB` | Table | the table (SVG or LaTeX) |
| `PIC` | Picture | image |
| `DIA` | Diagram | SVG |
| `LI` | ListItem | list entry |
| `ABS` | Abstract | abstract block |
| `TOC` | Toc | table of contents |
| `SN` | Sidenote | margin note |
| `FN` | Footnote | superscript link |
| `CIT` | Citation | link to the bibliography entry |
| `PROOF` | Proof | paired to its theorem |
| `LTX` | raw LaTeX | verbatim |
| `IMG` | image tiddler | `{{title}}` |

## Where transclusions come from — TWO mechanisms

This distinction is what made the 2026-08 failure hard to see.

**1. Inline substitution (`CIT`, `FO`, `FREF`, `FN`).** The projector rewrites
markers *inside a paragraph's text string*. It works on text and never touches
the object tree.

**2. Section-body emission (`PARA`, `TAB`, `PIC`, `DIA`, `LI`, `ABS`, `TOC`,
`SN`, `EQBLOCK`).** The projector walks `section.children` and emits one
transclusion per child. It depends entirely on the **object tree** being built.

So if the tree is flat — if Sections have no `children` — mechanism 2 emits
**nothing**, while mechanism 1 keeps working perfectly. The output looks
populated (paragraphs have text, formulas and citations resolve) and yet every
table, figure and list has silently disappeared.

That is exactly what happened: 14 of 16 templates were never emitted, because
`build_source_model` bypassed the pass that fills `children`.

## How to check it — the assertions that matter

Run these against the model and the tiddlers, not against the rendered page.

```python
# 1. The tree exists. A model with sections must have children.
secs = [o for o in doc.objects.values() if o.type == "Section"]
assert not secs or sum(len(s.children or []) for s in secs) > 0
```

`children` is an **attribute** (`section.children`), *not* `props["children"]`.
Checking the wrong one reports zero on a healthy model.

```python
# 2. Positive emission. Every object type present must be transcluded.
import re, collections
used = collections.Counter()
for t in tiddlers:
    used.update(re.findall(r"\|\|([A-Z]+)\}\}", t.get("text") or ""))
# a model with N Table objects must show TAB in `used`
```

Assert what the projector **must emit**, never only what it must not. The
historical test suite asserted `"||DIA}}" not in text` and never the converse —
so a projector emitting *nothing at all* passed every check.

```python
# 3. Conservation across projections. Same model, same counts.
#    md / llmtext / tiddlers disagree  -> projector bug
#    all three missing the same thing  -> model bug
```

## Reading the numbers

Healthy output for a 16-page paper with 16 tables (2209.00445v3):

```
transclusions by template: {FO: 126, PARA: 84, CIT: 60, TAB: 16, EQBLOCK: 1}
```

Broken output for the same document:

```
transclusions by template: {FO: 126, CIT: 60}
```

`FO` and `CIT` are unchanged — they come from mechanism 1. Everything from
mechanism 2 is gone. **If you only ever see `FO` and `CIT`, the object tree is
flat.** That single reading identifies the fault immediately.

## Quick command

```bash
python3 - <<'EOF'
import json, re, collections, sys
t = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "doc.tiddlers.json"))
c = collections.Counter()
for x in t:
    c.update(re.findall(r"\|\|([A-Z]+)\}\}", x.get("text") or ""))
print(f"tiddlers={len(t)}  transclusions={sum(c.values())}  {dict(c.most_common())}")
EOF
```
