# pdfdrill — change request: centralize the product name/URL (rename-readiness)

Motivation: an unrelated company operates at **pdfdrill.com**. We may later need
to rename to avoid trademark confusion, so the product name should live in ONE
place, not be sprinkled across the code as a string literal. The website already
carries a non-affiliation disclaimer; this CR makes the CLI rename-ready.

## Scope: user-facing STRINGS only (safe, do now)

Add a small module, e.g. `src/pdfdrill/branding.py`:

    APP_NAME = "pdfdrill"          # display name
    APP_URL  = "https://github.com/WulfKolbe/pdfdrill"
    TAGLINE  = "token-economical drill-down PDF extraction + PDF→LaTeX OCR QC"

Route through it: the `--help` header/usage banner, the `doctor` output, any
"Built … / Wrote …" prose lines, README-generated text, and any log prefixes
that print the name. Replace literal "pdfdrill" in **messages** with `APP_NAME`.

### Acceptance
- `grep -rn '"pdfdrill"' src/pdfdrill/` shows no literal product name in
  user-facing strings (command-dispatch keys excluded — see below).
- Changing `APP_NAME` once changes every banner/prose mention.

## Out of scope here (bigger, breaking — flag, don't do silently)

These are NOT just strings; renaming them breaks users' files and muscle memory,
so they need a deliberate migration plan, not a variable:

- the console-script / invocation name `pdfdrill` (`pyproject [project.scripts]`)
- the Python package name `pdfdrill`
- on-disk conventions: `<pdf>.drill.json`, `<pdf>.pdf.drill/`, the `drill` verb,
  `*.tiddlers.json`
- the default bibkey / tiddler-prefix behavior

Recommend: document these as the "hard rename surface" in `CLAUDE.md` /
`CONTRIBUTING` so a future rename has a checklist. Do NOT parameterize them now.

## Priority
Low-effort, high option-value. Do the strings module; list the hard surface.
Unrelated to functionality — schedule whenever convenient.
