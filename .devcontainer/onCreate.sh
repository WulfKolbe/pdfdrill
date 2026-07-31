#!/usr/bin/env bash
# pdfdrill — dev container provisioning.
#
# Runs as onCreateCommand, NOT postCreateCommand: Codespaces prebuilds execute
# setup only up to onCreateCommand/updateContentCommand. Anything placed in
# postCreateCommand would be re-run on every codespace creation and would make
# the (paid) prebuild pointless for the ~4 GB TeXLive set.
#
# Single source of truth: the apt package list and the Python deps are NOT
# duplicated here. bootstrap.sh owns them; this script only supplies the
# prerequisites bootstrap.sh assumes (python3/pip/curl) and the runtimes the
# CoCalc script installs the same way (bun, uv), then calls bootstrap.sh.
#
# Idempotent: safe to re-run by hand inside a live codespace.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi

step() { printf '\n== %s ==\n' "$1"; }

# ---- 1/6  Prerequisites bootstrap.sh assumes exist ----------------------
step "1/7  base prerequisites (python3, pip, curl, unzip)"
$SUDO apt-get update -q || true
$SUDO apt-get install -y -q python3 python3-pip python3-venv curl unzip ca-certificates \
  || echo "  (apt-get failed — later steps will report what is missing)"

# --- tesseract: installed HERE, deliberately, ahead of bootstrap.sh ------
# bootstrap.sh asks for `tesseract-ocr-equ`, which does not exist in the
# Ubuntu 24.04 archive (upstream dropped equ.traineddata). apt-get is invoked
# there with the whole package array at once, so that one unknown name aborts
# the ENTIRE transaction — poppler, ghostscript, libvips and all of texlive
# would fail to install, silently (the call is `>/dev/null 2>&1 || echo`).
#
# Installing tesseract first makes bootstrap.sh's `command -v tesseract` guard
# true, so it never adds the bad name and the rest of its list installs.
# `equ` is not a loss: src/pdfdrill/ocr_lines.py already strips it from the
# lang list, and the math second pass uses MATH_LANGS = "ell+eng" — so the
# pack that path actually needs is Greek, which bootstrap.sh never installed.
step "1b/7  tesseract + language packs (eng, deu, ell)"
$SUDO apt-get install -y -q tesseract-ocr tesseract-ocr-eng tesseract-ocr-deu tesseract-ocr-ell \
  || echo "  (tesseract install failed — pdfdrill ocr will be unavailable)"

# bootstrap.sh invokes `pip`, not `pip3`. On Ubuntu 24.04 python3-pip may only
# provide pip3; give it the name it expects rather than patching bootstrap.sh.
if ! command -v pip >/dev/null 2>&1 && command -v pip3 >/dev/null 2>&1; then
  $SUDO ln -sf "$(command -v pip3)" /usr/local/bin/pip
  echo "  linked pip -> $(command -v pip3)"
fi

# ---- 2/6  bun (drillui bridge runtime + TiddlyWiki host) ----------------
step "2/7  bun"
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"
if command -v bun >/dev/null 2>&1; then
  echo "  bun already present: $(bun --version)"
else
  # Retry once: this is a single network fetch, and a transient failure here
  # cascades — step 6 (TiddlyWiki) and the drillui bridge both need bun.
  curl -fsSL https://bun.sh/install | bash \
    || { echo "  bun install failed — retrying once"; sleep 3; curl -fsSL https://bun.sh/install | bash; } \
    || echo "  (bun install failed twice — drillui and TiddlyWiki will be unavailable)"
fi
if command -v bun >/dev/null 2>&1; then
  echo "  bun $(bun --version)"
else
  echo "  !! bun NOT installed. Check network egress to bun.sh, then re-run this script."
fi

# ---- 3/6  uv + uvx ------------------------------------------------------
step "3/7  uv"
export PATH="$HOME/.local/bin:$PATH"
if command -v uv >/dev/null 2>&1; then
  echo "  uv already present: $(uv --version)"
else
  curl -LsSf https://astral.sh/uv/install.sh | sh \
    || { echo "  uv install failed — retrying once"; sleep 3; curl -LsSf https://astral.sh/uv/install.sh | sh; } \
    || echo "  (uv install failed twice)"
fi
command -v uv >/dev/null 2>&1 && echo "  uv $(uv --version)" || echo "  !! uv NOT installed."

# ---- 4/6  the repo's own bootstrap (apt set + python deps + doctor) -----
# Installs: poppler-utils, ghostscript, libvips-tools, tesseract(+eng/deu/equ),
# sane-utils, dvisvgm and the full texlive set, then pip -r requirements.txt.
step "4/7  bootstrap.sh"
bash "$ROOT/bootstrap.sh" || echo "  (bootstrap.sh reported problems — see doctor output above)"

# ---- 5/6  deep-zoom image server (pyvips) -------------------------------
# tools/imageserver/install.sh calls plain `pip install`, which Ubuntu 24.04
# refuses (PEP 668, externally-managed-environment). bootstrap.sh passes
# --break-system-packages explicitly; install.sh does not. Rather than edit the
# upstream script, grant the same permission through pip's own environment
# variable, which has identical effect and is scoped to this call.
step "5/7  imageserver (pyvips)"
PIP_BREAK_SYSTEM_PACKAGES=1 bash "$ROOT/tools/imageserver/install.sh" \
  || echo "  (imageserver install failed — re-run: PIP_BREAK_SYSTEM_PACKAGES=1 bash tools/imageserver/install.sh)"

# ---- 6/6  TiddlyWiki, hosted by bun -------------------------------------
# Installed as a bun global package so the `tiddlywiki` binary lands in
# ~/.bun/bin (already on PATH via devcontainer.json remoteEnv). The KaTeX
# plugin ships inside the tiddlywiki package itself; no separate install.
step "6/7  TiddlyWiki (bun global)"
if command -v bun >/dev/null 2>&1; then
  bun add --global tiddlywiki || echo "  (bun add tiddlywiki failed)"
  command -v tiddlywiki >/dev/null 2>&1 \
    && echo "  tiddlywiki $(tiddlywiki --version)" \
    || echo "  tiddlywiki not on PATH yet — open a new shell"
else
  echo "  bun missing — skipping TiddlyWiki"
fi

# ---- 7/7  make the user-installed tools reachable from ANY shell --------
# bun, uv and tiddlywiki install under $HOME (/home/vscode/...), which is NOT
# on the default PATH. Three independent mechanisms put them in reach, because
# each one alone has a failure mode:
#
#   a) devcontainer.json remoteEnv PATH — applies to VS Code and what it
#      spawns. It previously interpolated ${containerEnv:HOME}, which reads the
#      IMAGE's environment; the base image sets no HOME, so it expanded to
#      empty and produced the dead entry "/.bun/bin". Now a literal, pinned by
#      "remoteUser": "vscode".
#   b) ~/.bashrc — covers interactive terminals. bun's own installer usually
#      writes this, but it is skipped in some non-interactive installs, so we
#      do not depend on it happening.
#   c) /usr/local/bin symlinks — the backstop. Already on every default PATH,
#      independent of HOME, rc files, login-vs-interactive shells and remoteEnv.
#      This is the layer that actually guarantees `bun` resolves.
step "7/7  PATH reachability (symlinks + shell rc)"

RC="$HOME/.bashrc"
MARK="# >>> pdfdrill PATH >>>"
if [ -f "$RC" ] && grep -qF "$MARK" "$RC"; then
  echo "  ~/.bashrc block already present"
else
  {
    printf '\n%s\n' "$MARK"
    echo 'export BUN_INSTALL="$HOME/.bun"'
    echo 'export PATH="$HOME/.bun/bin:$HOME/.local/bin:$PATH"'
    printf '%s\n' "# <<< pdfdrill PATH <<<"
  } >> "$RC"
  echo "  appended PATH block to ~/.bashrc"
fi

for t in "$HOME/.bun/bin/bun" "$HOME/.bun/bin/bunx" \
         "$HOME/.local/bin/uv" "$HOME/.local/bin/uvx" \
         "$HOME/.bun/bin/tiddlywiki"; do
  [ -x "$t" ] || continue
  if $SUDO ln -sf "$t" "/usr/local/bin/$(basename "$t")" 2>/dev/null; then
    echo "  linked $(basename "$t") -> /usr/local/bin"
  else
    echo "  (could not link $(basename "$t") into /usr/local/bin)"
  fi
done

# Prove it: resolve from an environment that inherits nothing from this script.
echo "  reachable from a clean shell:"
for b in bun uv tiddlywiki; do
  if env -i bash -c "command -v $b" >/dev/null 2>&1; then
    echo "      OK   $b"
  else
    echo "      MISS $b   (only reachable with this script's PATH)"
  fi
done

printf '\n%s\n' "----------------------------------------------------------------"
echo " provisioning finished. Verify with:"
echo "     bash .devcontainer/verify.sh"
printf '%s\n' "----------------------------------------------------------------"
