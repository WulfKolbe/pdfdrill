#!/usr/bin/env bash
# One-shot setup for a fresh sandbox: install deps, confirm ready.
#   tar -xzf pdfdrill.tgz -C ~/pdfdrill && cd ~/pdfdrill && bash bootstrap.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

pip install --quiet --break-system-packages -r requirements.txt 2>/dev/null \
  || pip install --quiet --break-system-packages "pdfplumber>=0.11" "pydantic>=2.0" \
  || true

if [ ! -f .env ] && [ -f .env.example ]; then
  echo "note: no .env found. For mathpix/snip/bibfetch:  cp .env.example .env  and fill in."
fi

echo "pdfdrill ready.  Run:  PYTHONPATH=src python3 -m pdfdrill <cmd> <pdf>"
echo "  offline math (no key):  PYTHONPATH=src python3 -m pdfdrill report <pdf>"
