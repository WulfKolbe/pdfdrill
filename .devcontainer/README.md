# .devcontainer — how the dev container is provisioned

Notes for whoever maintains this container. Nobody needs to read this to *use*
pdfdrill — [README](../README.md) and [QUICKSTART](../QUICKSTART.md) are the
user-facing story. This file exists so the detail has somewhere to live that is
not in a first-time reader's way.

Opening this repo in a container (GitHub Codespaces, or VS Code's *Dev
Containers: Reopen in Container*) gives you the full toolchain — ghostscript,
poppler, tesseract, the TeXLive/dvisvgm set, bun, uv, TiddlyWiki — without
installing any of it on your own machine.

## Files

| File | Role |
|------|------|
| `devcontainer.json` | image, ports, environment, VS Code settings |
| `onCreate.sh` | one-time provisioning, run as `onCreateCommand` |
| `verify.sh` | diagnostic; independent named tests, exit status = failure count |

## Relationship to drillspace

[drillspace](https://github.com/WulfKolbe/drillspace) is the *click-and-try
playground* — a separate repo whose whole purpose is a one-click Codespace with
sample PDFs already in the tree. This container is provisioned by the same
scripts, with one deliberate difference: **drillspace disables pdfdrill's
preflight attestation gate (`PDFDRILL_NO_PREFLIGHT=1`); this one does not.**

Here you are working *on* pdfdrill, so the gate behaves exactly as it does in
every other environment — that is the behaviour you need to be able to see and
test. If a task genuinely needs it off (CI-style batch runs, scripted tests),
set it per-command rather than container-wide:

```bash
PDFDRILL_NO_PREFLIGHT=1 python3 -m pdfdrill <cmd> <pdf>
```

## Why `onCreateCommand` and not `postCreateCommand`

Codespaces prebuilds execute setup only up to `onCreateCommand` /
`updateContentCommand`. Anything in `postCreateCommand` re-runs on *every*
codespace creation, which would make a prebuild pointless for the ~4 GB TeX
set. Keep provisioning where it is.

Configure prebuilds at **Settings → Codespaces → Set up prebuild**. Note a
**fork does not inherit** the upstream repo's prebuilds.

## Single source of truth for dependencies

`onCreate.sh` does **not** duplicate the apt package list or the Python deps.
`bootstrap.sh` owns them. `onCreate.sh` only supplies what `bootstrap.sh`
assumes exists (python3 / pip / curl), installs the runtimes `cocalc-setup.sh`
installs the same way (bun, uv), then calls `bootstrap.sh`. Add a dependency in
`bootstrap.sh` and every environment — container, CoCalc, bare sandbox — picks
it up.

## PATH: why three mechanisms

`bun`, `uv` and `tiddlywiki` install under `$HOME` (`/home/vscode/...`), which
is not on the default `PATH`. Each mechanism alone has a failure mode, so all
three are used:

1. **`devcontainer.json` `remoteEnv`** — applies to VS Code and what it spawns.
   Note it is a *literal* `/home/vscode/...`, pinned by `"remoteUser":
   "vscode"`. It must not interpolate `${containerEnv:HOME}`: that reads the
   *image's* environment, the base image sets no `HOME`, and it expands to the
   dead entry `/.bun/bin`.
2. **`~/.bashrc`** — covers interactive terminals. bun's installer usually
   writes such a block itself, but skips it in some non-interactive installs,
   so we do not depend on that.
3. **`/usr/local/bin` symlinks** (`onCreate.sh` step 7/7) — the backstop.
   First on every default `PATH`, independent of `HOME`, rc files,
   login-vs-interactive shells and `remoteEnv`. This is the layer that
   actually guarantees resolution.

### T8 in `verify.sh`

T1 and T7 resolve binaries using whatever `PATH` the caller happened to have,
so a tool can pass there and still be missing from a fresh terminal. That is
exactly how a `bun: command not found` once slipped past a provisioning run
that reported success.

T8 re-resolves `bun`, `uv` and `tiddlywiki` via `env -i` — a shell inheriting
nothing — and so reproduces what a new terminal actually sees. `onCreate.sh`
prints the same clean-shell check at the end of provisioning, putting the
failure in the creation log rather than in a confused user's terminal.

## Known upstream quirks handled here

- **`tesseract-ocr-equ` does not exist** in the Ubuntu 24.04 archive (upstream
  dropped `equ.traineddata`). `bootstrap.sh` passes its whole package array to
  one `apt-get` call, so that single unknown name would abort the entire
  transaction — poppler, ghostscript, libvips and all of TeXLive — silently,
  because the call is `>/dev/null 2>&1 || echo`. `onCreate.sh` installs
  tesseract *first* so `bootstrap.sh`'s `command -v tesseract` guard is true
  and the bad name is never added. `equ` is no loss: `src/pdfdrill/ocr_lines.py`
  strips it from the lang list and the math second pass uses
  `MATH_LANGS = "ell+eng"` — so the pack that path needs is Greek, which
  `bootstrap.sh` never installed and `onCreate.sh` does.
- **`pip` vs `pip3`** — `bootstrap.sh` invokes `pip`; Ubuntu 24.04's
  `python3-pip` may provide only `pip3`. `onCreate.sh` symlinks it.
- **PEP 668** — `tools/imageserver/install.sh` calls plain `pip install`, which
  Ubuntu 24.04 refuses (`externally-managed-environment`). `onCreate.sh` sets
  `PIP_BREAK_SYSTEM_PACKAGES=1` for that call rather than patching the script.

## Verifying a container

```bash
bash .devcontainer/verify.sh    # exit status = number of failed tests
python3 -m pdfdrill doctor      # pdfdrill's own requirement check
```
