#!/usr/bin/env bash
# Install the dependencies for `pdfdrill pyramid` / `pdfdrill imageserve` — the
# local, MathPix-free deep-zoom image server (a 600-DPI Ghostscript DZI pyramid +
# viewer). Needs:
#   * pyvips  — DZI tiling (`dzsave`). `pyvips[binary]` BUNDLES libvips, so NO
#               apt package and NO root are required (ideal on CoCalc).
#   * pillow  — the region crops.
#   * gs      — the rasterizer (a hard pdfdrill requirement; bootstrap.sh installs
#               it). Not pip-installable.
#
# Repeat the install ANYTIME with:
#     bash tools/imageserver/install.sh
#
# (Equivalent one-liner: pip install 'pdfdrill[imageserver]')
set -e
cd "$(dirname "$0")/../.."        # repo root

echo "== pdfdrill pyramid / imageserver install =="

# pyvips[binary] ships a bundled libvips → no apt, no root. Prefer the editable
# extra (uses the repo's pyproject); fall back to installing the packages directly.
# P1 (auditing session, 2026-10-20): this pip step removes the patched pdfminer
# fork the same way bootstrap.sh did — pdfplumber pins pdfminer.six exactly and
# pip resolves that pin over the fork. Notice it here too; the CoCalc path was
# the one install route that still did it silently.

if pip install -e '.[imageserver]'; then
  echo "  installed via  pip install -e '.[imageserver]'"
else
  echo "  (the editable extra failed — installing the packages directly)"
  pip install 'pyvips[binary]>=2.2' 'pillow>=10.0'
fi

# ENSURE, not restore — see bootstrap.sh. A fresh venv never had the fork, so a
# conditional restore builds nothing and the install ends with stock pdfminer.
# `pip install --user` REFUSES inside a venv, and the documented install is a
# fresh venv — so pick the mode that can actually place the build.
if python3 -c 'import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)' 2>/dev/null; then
  FORK_MODE="--here"
else
  FORK_MODE="--user"
fi
if ! bash vendor/install-pdfminer-fork.sh --check >/dev/null 2>&1; then
  echo "  note: building the patched pdfminer (LTChar.glyphname)."
  bash vendor/install-pdfminer-fork.sh "$FORK_MODE" --rebuild >/dev/null 2>&1 \
    && echo "  done." \
    || echo "  BUILD FAILED — run: bash vendor/install-pdfminer-fork.sh "$FORK_MODE" --rebuild"
fi

# Ghostscript is the rasterizer — not pip-installable.
if ! command -v gs >/dev/null 2>&1; then
  echo "  NOTE: Ghostscript (gs) is missing — install it too:"
  echo "        sudo apt-get install -y ghostscript"
fi

# Verify pyvips actually imports (the bundled libvips loads).
python3 - <<'PY'
import sys
try:
    import pyvips
    print(f"  [ok] pyvips {pyvips.__version__} imports (bundled libvips loaded)")
except Exception as e:
    sys.exit(f"  [FAIL] pyvips still not importable: {e}\n"
             f"        try:  pip install --force-reinstall 'pyvips[binary]'")
PY

echo "== done — now:  pdfdrill pyramid <pdf>   (then: pdfdrill imageserve <pdf>) =="
