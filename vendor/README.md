# vendor/

Third-party source this repository carries rather than depends on by path.

## `pdfminer-glyph-identity.patch`

The glyph-identity fork of **pdfminer.six**, pinned to upstream commit
**`a18de2a`**. Applied on install; see `docs/superpowers/specs/2026-09-30-pdf2mmd-integration-design.md`.

**What it does.** Stock pdfminer answers "what Unicode character is this cid?"
and drops the entry when there is no answer — which is why a `/star` or
`/lscript` from a TeX maths font arrives downstream as `(cid:7)`. The patch
adds the twin question, cid → *PostScript glyph name*: class-level `std2name` /
`mac2name` / `win2name` / `pdf2name` tables, a `get_encoding_names()`
classmethod, and `cid` / `textstate_render` threaded through
converter → device → layout.

**Why it can be vendored.** It is **purely additive: +461 / −0.**
`get_encoding` — the Unicode channel every existing caller reads — is not
touched, so the 33 files under `src/` that import pdfminer see exactly what
they saw before. `tests/test_pdfminer_fork_is_additive.py` is the gate on that
and fails if a future rebase starts removing things.

**Why it is here and not beside us.** It lived in `~/pdf2mmd` and was reached
through `PDF2MMD_HOME`. A path convention that can point at a stale tree is how
ser7 ran commit 784 for a week while this machine ran 820, and how deleting
`~/Downloads/pdf2mmd` on 2026-09-29 took `~/pdf2mmd/.pdfmm-venv` with it — the
venv was a symlink into the deleted tree. Nothing was lost only because this
patch was already tracked in git.

**Licence.** pdfminer.six is MIT. The patch is a derivative work and must stay
readable and attributed: keep it as a patch against a named upstream commit,
never as a pre-patched copy of the source.

**On upgrade.** Rebase the patch onto the new upstream commit, update the pin
above, and run the gate. If the rebase deletes anything, stop and re-read the
spec — the integration's safety argument does not survive a subtractive fork.
