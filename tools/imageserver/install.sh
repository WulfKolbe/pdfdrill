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
if pip install -e '.[imageserver]'; then
  echo "  installed via  pip install -e '.[imageserver]'"
else
  echo "  (the editable extra failed — installing the packages directly)"
  pip install 'pyvips[binary]>=2.2' 'pillow>=10.0'
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
