#!/usr/bin/env bash
# One-shot setup for a fresh sandbox: install Python + system deps, confirm ready.
#   git clone … ~/pdfdrill && cd ~/pdfdrill && bash bootstrap.sh
#   (or)  tar -xzf pdfdrill.tgz -C ~/pdfdrill && cd ~/pdfdrill && bash bootstrap.sh
#
# Installs (best-effort, only what's missing):
#   - Python deps (pdfplumber, pydantic) via pip
#   - ghostscript                    -> the ONLY page rasterizer (>=400 DPI:
#     OCR/vision/layout/image-locate all render via gs; required)
#   - poppler-utils                  -> pdftotext/pdfimages/pdfinfo (core)
#   - LaTeX DVI toolchain + dvisvgm  -> TikZ/table SVG route (`pdfdrill svg`,
#     `latexbook`): latex/pdflatex/dvips + dvisvgm + tikz/standalone packages
# System installs use apt-get when present (Debian/Ubuntu, e.g. the Claude.ai
# sandbox); on other distros they're skipped and reported in the final check.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# ---- Python deps --------------------------------------------------------
pip install --quiet --break-system-packages -r requirements.txt 2>/dev/null \
  || pip install --quiet --break-system-packages \
       "pdfminer.six>=20221105" "pdfplumber>=0.11" "pydantic>=2.0" "pypdf>=4.0" \
  || true

# ---- System deps (apt-get, best-effort) ---------------------------------
SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi

if command -v apt-get >/dev/null 2>&1; then
  PKGS=()
  command -v pdftotext >/dev/null 2>&1 || PKGS+=(poppler-utils)
  # Ghostscript is the PRIMARY page rasterizer (>=400 DPI; far better OCR/vision
  # fidelity than poppler/fitz — gs-400 94.9% vs fitz-300 82%).
  command -v gs >/dev/null 2>&1 || PKGS+=(ghostscript)
  # libvips (dzsave) — builds the local 600-DPI DZI pyramid for `pdfdrill
  # pyramid`/`imageserve` (the MathPix-free image source). Optional but installed
  # here so the image stack works out of the box.
  command -v vips >/dev/null 2>&1 || PKGS+=(libvips-tools)
  # NO OCR ENGINE. tesseract used to be installed here for `pdfdrill ocr`; both
  # are gone. Which reading a document gets is docs/LANES.md's decision, and the
  # last lane (`gemmaocr --geometry-only`) is free and needs no engine at all.
  # SANE — the scanner ADF acquisition route (`pdfdrill scan`). Optional: only a
  # box with a scanner needs it; every other route is unaffected without it.
  command -v scanimage >/dev/null 2>&1 || PKGS+=(sane-utils)
  # LaTeX DVI toolchain + dvisvgm — needed for the TikZ/table SVG route.
  # If either `latex` or `dvisvgm` is missing, install the whole support set
  # (a present `latex` alone isn't enough — TikZ needs texlive-pictures, the
  # standalone class lives in texlive-latex-extra, etc.).
  if ! command -v latex >/dev/null 2>&1 || ! command -v dvisvgm >/dev/null 2>&1; then
    PKGS+=(dvisvgm texlive-latex-base texlive-latex-recommended \
           texlive-latex-extra texlive-pictures texlive-fonts-recommended \
           texlive-fonts-extra texlive-science texlive-plain-generic \
           texlive-binaries)
  fi
  if [ "${#PKGS[@]}" -gt 0 ]; then
    echo "Installing missing system packages: ${PKGS[*]}"
    $SUDO apt-get update -q >/dev/null 2>&1 || true
    $SUDO apt-get install -y -q "${PKGS[@]}" >/dev/null 2>&1 \
      || echo "  (apt-get install failed — see the requirement check below)"
  fi
else
  echo "note: apt-get not found — skipping system-package install (non-Debian host)."
fi

# ---- .env hint ----------------------------------------------------------
if [ ! -f .env ] && [ -f .env.example ]; then
  echo "note: no .env found. For mathpix/snip/bibfetch/vision:  cp .env.example .env  and fill in."
fi

# ---- Requirement check (also available anytime via: pdfdrill doctor) ----
echo
PYTHONPATH=src python3 -m pdfdrill doctor || true

echo
echo "pdfdrill ready.  Run:  PYTHONPATH=src python3 -m pdfdrill <cmd> <pdf>"
echo
echo "FIRST, unlock the build commands (per working directory). size/route/doctor"
echo "already answer; model/report/inspect/md/drill are BLOCKED until you ack that"
echo "you read the SKILL, because the output looks authoritative and is silently"
echo "wrong when used without the usage rules:"
echo "    pdfdrill preflight                          # the rules, and where the SKILL is"
echo "    tail -3 .claude/skills/pdfdrill/SKILL.md    # the DRILL-… token is the line"
echo "                                                #   ABOVE the END marker; tail -1"
echo "                                                #   gives you the marker"
echo "    pdfdrill preflight --ack <TOKEN>            # paste the token you just read"
echo "  The token is a checksum of the SKILL body and changes with it; read it from"
echo "  the file. Automation that has read the rules sets PDFDRILL_NO_PREFLIGHT=1."
echo
echo "  THEN, offline math (no key):  PYTHONPATH=src python3 -m pdfdrill report <pdf>"
