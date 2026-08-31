# Reclassifying an Equation as a Diagram — the design

434. A design report, not a build. Nothing here is implemented.

MathPix sometimes reads a TikZ figure as display mathematics: the region is
right, the type is wrong, and the LaTeX it returns is a plausible-looking
equation that renders to something the page does not contain. The Cardona
volume is where this happens at scale — 1,012 measured rows, 23 of them
`component`.

## The shape of the change

Three parts, and the first two are what make it a report rather than an
overwrite.

**1. The Equation object STAYS.** It keeps its id, its region, its
realizations and its MathPix confidence, and gains a note recording that its
CONTENT was reclassified — not that it was wrong, but that a successor now
carries the reading. Deleting it would destroy the evidence that MathPix read
this region as mathematics, which is the finding.

**2. A new Diagram object is created under its own key**, carrying the TikZ,
the basis it was derived from, its own confidence, and the ink verification
that accepted it. It is a new object with a new id, not a mutation.

**3. The transclusions move; the old object points at the successor.** The
section body stops transcluding `{{key_EQ0001||EQBLOCK}}` and starts
transcluding `{{key_DIA0007||DIA}}`. The Equation keeps a `successor` prop
naming the new key.

That last point is the whole design. A reader who follows the old key must
arrive somewhere, and an auditor asking "what did MathPix originally read
here" must still be able to.

## Which projections read the transclusion

Eight distinct parsers, and they do not agree on what they match. That
disagreement is the risk.

| where | regex | what it matches |
|---|---|---|
| `docops/projectors/tiddlywiki.py:53` | `\{\{([^{}]+?)\}\}` | any |
| `docops/projectors/okf.py:24` | `\{\{([^{}]+?)\}\}` | any |
| `docops/transclusion_render.py:29` | `\{\{([^{}]*)\}\}` | any |
| `docops/nlp_stanza.py:100` | `\{\{([^{}]*)\}\}` | any |
| `semantic/concepts.py:213` | `\{\{[^{}]*\}\}` | any |
| `docops/projectors/latex_pipeline.py:31` | `\{\{([^\|{}]+?)\|\|([A-Z]+)\}\}` | target **and template** |
| `pdfdrill/commands.py:6152` | `\{\{([^}\|]+)\|\|(FO\|EQ\|FREF)\}\}` | **FO, EQ, FREF only** |
| `pdfdrill/report_tex.py:62` | `\{\{(<bibkey>_(?:FOX?_?\w+))\|\|` | **FO / FOX only** |

**The five generic ones follow the pointer for free.** They rewrite or count
whatever target they find, so a `_DIA` key where an `_EQ` key used to be is
handled without knowing anything about the change.

**The three filtered ones are the hazard**, and they fail in two different
ways:

- `latex_pipeline` captures the TEMPLATE as well, so it will see `||DIA`
  where it expected `||EQBLOCK` and must have a branch for it. A missing
  branch here is a visible failure — the marker is matched and unhandled.
- `commands.py:6152` and `report_tex.first_pages` match a FIXED SET of
  templates. A `||DIA` marker is not matched at all, so it is **invisible**:
  no error, no unhandled marker, just a row that stops being counted. That is
  the failure mode this project keeps meeting — a filter nobody chose,
  silently narrowing a population.

`first_pages` maps a title to the page of the first tiddler transcluding it;
a reclassified object would simply lose its page.

## What report.tex does today, unchanged

`rows_for` buckets by TITLE, not by template:

```
_(FOX?|EQ|TAB|DIA|PIC)
```

so a new `_DIA` title lands in the `dia` bucket — the "Image regions" section
— without any change. That is correct: a diagram belongs there.

But the old Equation still matches `_EQ` and still lands in the equations
section, so the report would show BOTH rows. That is the RIGHT outcome and it
needs one addition: the equation row must render its note rather than its
LaTeX, the way a demoted row already shows `\emph{(not rendered)}` and a
refined row shows `[refined: …]` beside its identifier (233). The reader sees
that MathPix read mathematics here, that the reading was superseded, and
where the successor is.

## The integrity check must learn about it

`tiddlywiki.py` reports `dangling` (a transclusion whose target does not
exist) and `orphan_synthetic` (a tiddler nothing references). After a
reclassification the old EQ tiddler is referenced by nothing, so it becomes an
orphan — correctly, by the current rule, and wrongly as a matter of fact,
because it is deliberately retained. The rule needs to exempt an object that
carries a `successor`.

## What the new element compiles to

**SVG, for every HTML surface — because KaTeX cannot render a
`tikzpicture`.** That is not a preference; the `svg` command's own summary
says it: "Render TikZ diagrams + tables to SVG via latex→dvisvgm (KaTeX
can't)".

A Diagram tiddler already has two routes and the projector chooses between
them (`tiddlywiki.py:764-785`):

| condition | tiddler body |
|---|---|
| an `svg` prop exists | `{{!!svg_tiddler}}` — the SVG inline in a field |
| a MathPix `cdn_url` | the `DIA` template, `<$image source={{!!canonical_uri}}>` |

A reclassified equation has TikZ and no CDN crop of a diagram, so it takes the
first route, and `pdfdrill svg` is what fills it. Per surface:

| surface | renders as |
|---|---|
| TiddlyWiki / HTML | inline SVG via `svg_tiddler` |
| `report.pdf` (xelatex) | the TikZ compiled directly — no SVG needed |
| `formula-report.html` | SVG; KaTeX cannot do it |
| OKF bundle | the SVG file, linked |

## The ordering this implies

`svg` must run before the tiddler projection, or the Diagram tiddler is empty
— which is already true today and already warned about: `tiddlers` prints
"N table/diagram(s) carry LaTeX source but no rendered SVG yet — run
`pdfdrill svg` then `pdfdrill tiddlers --force`". Reclassification adds
members to that population, so the warning gets louder rather than the failure
getting newer.

## What must be true before any of this is built

435 landed first for this reason. A reclassification changes the model, and
every report built from the previous model is then wrong about the object it
names — silently, until `publishready` began refusing a report whose
`model_sha256` has moved. Without that guard this change would have made
every existing report quietly incorrect, and the Cardona volume would have
been the first place it happened at scale.
