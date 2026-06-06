# pdfdrill — bug: `compare` HTML calls KaTeX before it loads (red ReferenceError)

> **Status: open.** Found on the published demo wikis. The emitted
> `*-compare.html` shows a red `ReferenceError: katex is not defined` in the
> KaTeX column for every equation, even though KaTeX loads fine.

## Symptom

In `pdfdrill compare <pdf>` output, every `.katex-cell` renders as red error
text like:

    p_{t, j}}, \quad i \in \mathcal{I}_{t}^{(K)},
    ReferenceError: katex is not defined

The CSS/CDN are correct; KaTeX *does* load. The problem is **timing**.

## Root cause

The compare template loads KaTeX with `defer`:

    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>

…but emits the render loop as a **bare inline `<script>`** at the bottom:

    <script>
    document.querySelectorAll(".katex-cell").forEach(function (el) {
      ...
      katex.render(tex, el, {displayMode: true, throwOnError: false});   // katex undefined here
    ...

A `defer`'d external script executes **after** the document is parsed (just
before `DOMContentLoaded`). A bare inline script executes **the moment the
parser reaches it** — i.e. *before* the deferred KaTeX has run. So `katex` is
undefined, the `catch` fires, and `el.textContent = String(e)` paints the red
error.

`pdfdrill report` does NOT have this bug — its template wraps the same loop in
`document.addEventListener("DOMContentLoaded", …)`, which runs after deferred
scripts. The two generators diverged.

## Fix

Wrap the `compare` render loop in `DOMContentLoaded`, matching `report`:

    <script>
    document.addEventListener("DOMContentLoaded", function () {
      document.querySelectorAll(".katex-cell").forEach(function (el) { ... });
    });
    </script>

(Equivalent alternatives: a `katex`-ready poll, or dropping `defer` — but the
`DOMContentLoaded` wrap is what `report` already uses, so prefer it for
consistency. One shared HTML-emit helper for both report and compare would stop
this class of drift.)

## Acceptance

- A freshly generated `*-compare.html` opened in a browser renders all
  `.katex-cell` cells via KaTeX with **zero** `.render-error` cells and no
  `pageerror`.
- Regression check: same for `report` (already passing).

## Note

The already-published `heimUFT-compare.html` and
`kolbe2018hubbard-compare.html` were hand-patched with this exact wrap and
browser-verified (310/310 and 115/115 non-empty cells render, 0 errors). This CR
is to fix the **generator** so future output is correct.

## Priority

Medium — it's cosmetic-but-glaring: the QC artifact whose whole job is to show
rendered math instead shows a wall of red errors.
