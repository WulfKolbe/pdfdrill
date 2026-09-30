#!/usr/bin/env bash
# pdf2mmd.sh — convert a born-digital PDF into Markdown with LaTeX injected,
# plus the 250-dpi page images that make the deferred-maths crop links resolve.
#
#   ./pdf2mmd.sh book.pdf                 # whole document
#   ./pdf2mmd.sh book.pdf 60-80           # a page range
#   ./pdf2mmd.sh book.pdf 60-80 out/      # and where to put it
#   SERVE=1 ./pdf2mmd.sh book.pdf 60-80   # start the crop server afterwards
#
# WHY TWO RESOLUTIONS
#   The page images exist to be looked at, and 250 dpi is enough for that. It
#   is also exactly what MathPix renders at (measured: 250.05 dpi on every page
#   of a 377-page book), so a rectangle from a lines.json needs no rescaling.
#   Anything TOPOLOGICAL must not use them: measured against a 1200-dpi
#   reference, a 250-dpi raster gets the component count wrong for 2.6% of
#   isolated glyphs and the hole count wrong for 6.7%; at 400 dpi that is 0.5%
#   and 5.2%. A 7pt alpha is two components at 250 dpi and one at 400. So
#   inkdrill-grade rasters come from `inspectserver.py --pdf` on demand at 400
#   dpi, and are never stored here.
#
# EXIT CODES
#   0 ok   1 usage   2 missing dependency   3 conversion failed

set -euo pipefail

usage() {
    sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-1}"
}

[ $# -ge 1 ] || usage 1
case "$1" in -h|--help) usage 0 ;; esac

PDF="$1"
PAGES="${2:-all}"
OUT="${3:-./mmd-out}"
DPI="${VIEW_DPI:-250}"
PORT="${PORT:-8000}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

[ -f "$PDF" ] || { echo "no such file: $PDF" >&2; exit 1; }

# ---- dependencies ---------------------------------------------------------
need() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "missing dependency: $1${2:+  ($2)}" >&2; exit 2; }
}
need python3
need gs "Ghostscript — pdfdrill's only sanctioned rasterizer"

# ---- pick the interpreter -------------------------------------------------
# The patched pdfminer lives in its own venv by default so it cannot disturb
# any other tool that pins a released pdfminer.six.
PY="${PDFMM_PYTHON:-}"
if [ -z "$PY" ]; then
    if [ -x "$HERE/.pdfmm-venv/bin/python" ]; then
        PY="$HERE/.pdfmm-venv/bin/python"
    else
        PY="python3"
    fi
fi

# The check is not "does pdfminer import" -- stock pdfminer imports fine and
# then silently produces output with no glyph identity in it, which looks like
# a recognition failure rather than a missing dependency.
if ! "$PY" - <<'PYCHK' 2>/dev/null
import inspect, sys
from pdfminer.layout import LTChar
sys.exit(0 if "glyphname" in inspect.getsource(LTChar.__init__) else 1)
PYCHK
then
    cat >&2 <<EOF
This build of pdfminer.six does not expose glyph identity, so the maths in
your PDF would come out as (cid:N) with no LaTeX at all.

  interpreter tried: $PY

pdf2mmd needs a small patch to pdfminer.six (~160 additive lines, five files,
no change to existing behaviour). Build it once:

  $HERE/install-pdfminer-fork.sh

That creates an isolated venv at $HERE/.pdfmm-venv and leaves your system
pdfminer.six alone; pdf2mmd.sh then finds it automatically. If you keep it
elsewhere:

  PDFMM_PYTHON=/path/to/venv/bin/python $0 ...

To check an existing install:

  $HERE/install-pdfminer-fork.sh --check
EOF
    exit 2
fi

# ---- the toolkit's own files ---------------------------------------------
# These import each other, so a missing one surfaces as a ModuleNotFoundError
# from deep inside Python rather than as "you did not copy this file".
missing=""
for m in pdf2mmd.py docmodel_six.py docpack.py equations.py structure.py texmap.py project_mmd.py; do
    [ -f "$HERE/$m" ] || missing="$missing $m"
done
if [ -n "$missing" ]; then
    cat >&2 <<EOF
Missing module(s) next to pdf2mmd.sh:$missing

  looked in: $HERE

The converter needs all of these in one folder:
  pdf2mmd.sh  pdf2mmd.py  docmodel_six.py  structure.py  texmap.py  project_mmd.py
and, for the crop server and the installer:
  inspectserver.py  install-pdfminer-fork.sh  pdfminer-glyph-identity.patch
EOF
    exit 2
fi

# A file can be present but stale -- copied from an older set, so its imports
# no longer line up. Import them all once, up front, and show Python's own
# error rather than letting it surface mid-conversion.
if ! err=$(cd "$HERE" && "$PY" -c "import docmodel_six as docmodel, docpack, equations, structure, texmap, project_mmd" 2>&1); then
    cat >&2 <<EOF
The converter's modules are present but do not import cleanly:

$err

This usually means one file is from an older copy. Replace all of
  pdf2mmd.py docmodel_six.py structure.py texmap.py project_mmd.py
from the same set.
EOF
    exit 2
fi

STEM="$(basename "${PDF%.*}")"
# Page images are namespaced BY DOCUMENT. They used to share one folder, so
# converting a second document into the same output directory silently reused
# the first one's renders -- the caption said "An XML Document as a Tree" and
# the crop showed a type hierarchy from an entirely different book.
PAGEDIR="$OUT/inspect/pages/$STEM"
mkdir -p "$OUT" "$PAGEDIR"

echo "== pdf2mmd: $STEM  pages=$PAGES  ->  $OUT"

# ---- 1. convert -----------------------------------------------------------
# The docmodel is built ONCE and every format is projected from it, so the
# Markdown, the LaTeX and the lines.json cannot drift apart.
"$PY" "$HERE/pdf2mmd.py" "$PDF" \
        --pages "$PAGES" \
        --out "$OUT" \
        --doc-id "$STEM" \
        --image-base "http://localhost:${PORT}" \
    || { echo "conversion failed" >&2; exit 3; }

# ---- 2. render the view pages --------------------------------------------
# Only the pages actually converted, and only at viewing resolution.
first=1; last=0
if [ "$PAGES" = "all" ]; then
    last=$("$PY" -c "
import sys
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
with open(sys.argv[1],'rb') as fh:
    print(sum(1 for _ in PDFPage.create_pages(PDFDocument(PDFParser(fh)))))
" "$PDF")
elif [[ "$PAGES" == *-* ]]; then
    first="${PAGES%%-*}"; last="${PAGES##*-}"
else
    first="$PAGES"; last="$PAGES"
fi

echo "== rendering view pages ${first}..${last} at ${DPI} dpi"
for ((p = first; p <= last; p++)); do
    target="$PAGEDIR/p${p}.png"
    [ -f "$target" ] && continue
    # png16m: Ghostscript does not halftone truecolour, so the image carries
    # the document's content rather than the rasterizer's dithering
    gs -q -dNOPAUSE -dBATCH -dSAFER -sDEVICE=png16m -r"$DPI" \
       -dFirstPage="$p" -dLastPage="$p" \
       -sOutputFile="$target" "$PDF"
done
rendered=$(ls -1 "$PAGEDIR"/p*.png 2>/dev/null | wc -l)
echo "   $rendered page image(s) in $PAGEDIR"
# A manifest lets the image server check it was pointed at the right folder.
printf '{"document": "%s", "dpi": %s, "pages": %s}\n' \
    "$STEM" "$DPI" "$rendered" > "$PAGEDIR/manifest.json"

# ---- 3. report ------------------------------------------------------------
echo
cat "$OUT/$STEM.report.txt"
cat <<EOF
outputs
  $OUT/$STEM.md            Markdown + LaTeX
  $OUT/$STEM.tex           LaTeX
  $OUT/$STEM.lines.json    geometry
  $OUT/$STEM.fonts.md      type-size evidence for the heading levels
  $OUT/$STEM.report.txt    this summary

Deferred maths appears as a crop link. It resolves once the image server runs:

  $PY $HERE/inspectserver.py --pages "$PAGEDIR" \\
          --lines "$OUT/$STEM.lines.json" --pdf "$PDF" --port $PORT

Then /cropped/... serves the ${DPI}-dpi view crops and
     /render/pN.png?dpi=400 rasterizes on demand for topology work.
EOF

if [ "${SERVE:-0}" = "1" ]; then
    echo
    exec "$PY" "$HERE/inspectserver.py" \
        --pages "$PAGEDIR" \
        --lines "$OUT/$STEM.lines.json" \
        --pdf "$PDF" --port "$PORT"
fi
