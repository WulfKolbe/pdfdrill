#!/usr/bin/env bash
# pdfdrill — dev container provisioning verification.
#
# Every check is a NAMED test that passes or fails on its own. No check depends
# on a previous one having run. Exit status is the number of failed tests.
#   bash .devcontainer/verify.sh
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
export PYTHONPATH="${PYTHONPATH:-$ROOT/src}"

PASS=0; FAIL=0
ok()   { printf '  PASS  %-28s %s\n' "$1" "${2:-}"; PASS=$((PASS+1)); }
bad()  { printf '  FAIL  %-28s %s\n' "$1" "${2:-}"; FAIL=$((FAIL+1)); }

have() {  # have <test-name> <binary> [version-flag]
  local name="$1" bin="$2" flag="${3:---version}"
  if command -v "$bin" >/dev/null 2>&1; then
    ok "$name" "$("$bin" "$flag" 2>&1 | head -1)"
  else
    bad "$name" "'$bin' not on PATH"
  fi
}

echo "── T1  runtimes ─────────────────────────────────────────────────"
have T1.1-python3     python3
have T1.2-pip         pip
have T1.3-bun         bun
have T1.4-uv          uv

echo "── T2  pdfdrill system prerequisites ────────────────────────────"
have T2.1-ghostscript gs
have T2.2-pdftotext   pdftotext -v
have T2.3-pdfinfo     pdfinfo -v
have T2.4-tesseract   tesseract
have T2.5-vips        vips

echo "── T3  LaTeX / SVG toolchain ────────────────────────────────────"
have T3.1-latex       latex
have T3.2-pdflatex    pdflatex
have T3.3-dvips       dvips -v
have T3.4-dvisvgm     dvisvgm
if command -v kpsewhich >/dev/null 2>&1; then
  for cls in standalone.cls tikz.sty amsmath.sty; do
    if kpsewhich "$cls" >/dev/null 2>&1; then ok "T3.5-$cls"; else bad "T3.5-$cls" "not found by kpsewhich"; fi
  done
else
  bad "T3.5-texmf" "kpsewhich missing"
fi

echo "── T4  tesseract language data ──────────────────────────────────"
if command -v tesseract >/dev/null 2>&1; then
  LANGS="$(tesseract --list-langs 2>&1)"
  for l in eng deu ell; do
    if printf '%s' "$LANGS" | grep -qx "$l"; then ok "T4-$l"; else bad "T4-$l" "traineddata missing"; fi
  done
else
  bad "T4" "tesseract missing"
fi

echo "── T5  Python dependencies ──────────────────────────────────────"
for mod in pdfminer pdfplumber pydantic pypdf; do
  if python3 -c "import $mod" 2>/dev/null; then ok "T5-$mod"; else bad "T5-$mod" "import failed"; fi
done
if python3 -c "import pyvips" 2>/dev/null; then ok "T5-pyvips"; else bad "T5-pyvips" "import failed (pdfdrill pyramid unavailable)"; fi

echo "── T6  pdfdrill itself ──────────────────────────────────────────"
if python3 -c "import pdfdrill" 2>/dev/null; then
  ok "T6.1-import" "PYTHONPATH=$PYTHONPATH"
else
  bad "T6.1-import" "import pdfdrill failed"
fi
if python3 -m pdfdrill doctor >/tmp/doctor.out 2>&1; then
  ok "T6.2-doctor" "exit 0"
else
  bad "T6.2-doctor" "non-zero exit — see /tmp/doctor.out"
fi

echo "── T7  TiddlyWiki on bun ────────────────────────────────────────"
have T7.1-tiddlywiki  tiddlywiki

echo "── T8  reachable from a CLEAN shell ─────────────────────────────"
# T1/T7 use whatever PATH this script inherited, so they pass even when a tool
# is only findable because of the caller's environment. bun, uv and tiddlywiki
# live under $HOME, off the default PATH — the failure mode that actually bit
# us was `bun: command not found` in a fresh terminal while provisioning had
# reported success. These tests inherit NOTHING and so reproduce that case.
for b in bun uv tiddlywiki; do
  if env -i bash -c "command -v $b" >/dev/null 2>&1; then
    ok  "T8-$b"
  else
    bad "T8-$b" "not on the default PATH — new terminals will not find it"
  fi
done

echo "─────────────────────────────────────────────────────────────────"
printf '  %d passed, %d failed\n' "$PASS" "$FAIL"
exit "$FAIL"
