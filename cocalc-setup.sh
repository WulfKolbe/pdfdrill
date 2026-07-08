#!/usr/bin/env bash
# CoCalc.ai setup for pdfdrill + drillui.
#
# The CoCalc "standard" image ships without poppler, the LaTeX/dvisvgm SVG
# toolchain, bun, or uv — all of which pdfdrill and the drillui web terminal
# need. On CoCalc you DO have: `pip install`, `sudo apt-get`, and write access
# to ~/.local/bin and ~/.bun. This script uses exactly those.
#
# Run once from the repo root:
#   bash cocalc-setup.sh
#
# Then open a fresh shell (so bun/uv land on PATH) and launch the web terminal:
#   bun run tools/drillui_bridge.ts            # empty; `add <doc>` later
#   bun run tools/drillui_bridge.ts data/paper.pdf
#
# Opening it in the browser + the WebSocket connection string are CoCalc-
# specific — see COCALC.md (this script prints the short version at the end).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi

PROFILE="$HOME/.bashrc"
add_to_profile() {  # append a line to ~/.bashrc once (idempotent)
  local line="$1" marker="$2"
  grep -qsF "$marker" "$PROFILE" 2>/dev/null || printf '%s\n' "$line" >> "$PROFILE"
}

echo "== 1/4  System packages the CoCalc image is missing (sudo apt-get) =="
if command -v apt-get >/dev/null 2>&1; then
  $SUDO apt-get update -q || true
  # The known-good minimal set for the drillui + LaTeX-SVG paths on CoCalc.
  # bootstrap.sh (step 4) adds the rest (ghostscript, tesseract, libvips) and
  # skips whatever is already present, so latex/dvisvgm here keep it from
  # pulling the full texlive set.
  $SUDO apt-get install -y poppler-utils dvisvgm texlive-latex-extra \
    || echo "  (apt-get failed for one or more packages — see the doctor check at the end)"
else
  echo "  apt-get not found — are you on the CoCalc standard image? Skipping."
fi

echo
echo "== 2/4  bun  (the drillui bridge runtime) =="
if command -v bun >/dev/null 2>&1 || [ -x "$HOME/.bun/bin/bun" ]; then
  echo "  bun already installed"
else
  curl -fsSL https://bun.sh/install | bash
fi
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"
add_to_profile 'export BUN_INSTALL="$HOME/.bun"'            'BUN_INSTALL'
add_to_profile 'export PATH="$BUN_INSTALL/bin:$PATH"'       'BUN_INSTALL/bin'
if command -v bun >/dev/null 2>&1; then echo "  bun $(bun --version)"; else
  echo "  bun installed but not on PATH in THIS shell — open a new shell, or:"
  echo "      export PATH=\"\$HOME/.bun/bin:\$PATH\""
fi

echo
echo "== 3/4  uv + uvx  (into ~/.local/bin) =="
if command -v uv >/dev/null 2>&1 || [ -x "$HOME/.local/bin/uv" ]; then
  echo "  uv already installed"
else
  # Astral's installer targets ~/.local/bin by default (no sudo).
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
add_to_profile 'export PATH="$HOME/.local/bin:$PATH"'       '.local/bin'
if command -v uv >/dev/null 2>&1; then echo "  uv $(uv --version)"; else
  echo "  uv installed but not on PATH in THIS shell — open a new shell, or:"
  echo "      export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo
echo "== 4/4  Shared Python + system deps (bootstrap.sh) =="
# bootstrap.sh installs the Python deps via pip and the remaining apt packages
# (ghostscript, tesseract, libvips), then runs `pdfdrill doctor`.
bash "$ROOT/bootstrap.sh"

echo
echo "──────────────────────────────────────────────────────────────────────"
echo " pdfdrill + drillui are set up on CoCalc."
echo
echo " 1. Open a FRESH shell (so bun + uv are on PATH), then launch:"
echo "        bun run tools/drillui_bridge.ts            # serves on :8787"
echo
echo " 2. In your browser, open the CoCalc-forwarded port 8787:"
echo "        https://<HOST>/\$COCALC_PROJECT_ID/server/8787/"
echo "    (\$COCALC_PROJECT_ID = ${COCALC_PROJECT_ID:-<your project id>};"
echo "     <HOST> is the host-....cocalc.ai in your CoCalc browser URL.)"
echo
echo " 3. If drillui shows 'Bridge not reachable', paste this into its Connect"
echo "    box — it is the SAME URL as the page, with https→wss and /ws appended:"
echo "        wss://<HOST>/\$COCALC_PROJECT_ID/server/8787/ws"
echo
echo " Full walkthrough + troubleshooting: COCALC.md"
echo "──────────────────────────────────────────────────────────────────────"
