#!/usr/bin/env bash
# install.sh — set up pdf2mmd from the files sitting next to this script.
#
# There is NO PAYLOAD IN THIS FILE. It is plain text from top to bottom, it
# extracts nothing, and it decodes nothing. Everything it installs is already
# a readable file in this directory, which is the point: a restricted VM that
# refuses self-extracting scripts can still run this one, and an auditor can
# read every line of what it will do before running it.
#
#   ./install.sh                 check the files, build the venv, run the tests
#   ./install.sh --check         check only; build nothing
#   ./install.sh --no-venv       check the files, skip the venv
#   ./install.sh --no-tests      build the venv, skip the tests
#   ./install.sh --rebuild       rebuild the venv even if a working one exists
#   ./install.sh --venv DIR      put the venv somewhere else
#
# WHAT IT NEEDS
#   python3 3.10+, git, and network access ONCE to clone pdfminer.six.
#   ghostscript only for the render and crop tools, not for reading PDFs.
#
# WHAT IT TOUCHES
#   This directory, and the venv (default ./.pdfmm-venv). Nothing else. Your
#   system pdfminer.six is not modified; other tools that pin
#   `pdfminer.six==<release>` keep working.
#
# EXIT CODES
#   0 ok   1 usage   2 missing dependency   3 files missing or build failed
#   4 tests failed

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="$HERE/.pdfmm-venv"
DO_VENV=1
DO_TESTS=1
CHECK_ONLY=0
REBUILD=0

while [ $# -gt 0 ]; do
    case "$1" in
        --check)     CHECK_ONLY=1; shift ;;
        --no-venv)   DO_VENV=0; shift ;;
        --no-tests)  DO_TESTS=0; shift ;;
        --rebuild)   REBUILD=1; shift ;;
        --venv)      VENV="$2"; shift 2 ;;
        -h|--help)   sed -n '2,29p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1  (try --help)" >&2; exit 1 ;;
    esac
done

say()  { printf '%s\n' "$*"; }
fail() { printf '!! %s\n' "$*" >&2; }

# --- 1. the files ----------------------------------------------------------
# Named explicitly rather than globbed, so a missing module is an error here
# and not an ImportError in the middle of someone's corpus run.

MODULES="docmodel_six.py structure.py texmap.py project_mmd.py psstream.py
         equations.py docpack.py trajectory.py texpackages.py testpaths.py
         mathpix_merge.py inventory.py linescompare.py mdcompare.py
         dpitopo.py inspectserver.py pdf2mmd.py"
SCRIPTS="pdf2mmd.sh install-pdfminer-fork.sh"
FORK="pdfminer-glyph-identity.patch"

say "== files"
missing=0
for f in $MODULES $SCRIPTS $FORK; do
    if [ ! -f "$HERE/$f" ]; then fail "missing: $f"; missing=1; fi
done
[ "$missing" -eq 0 ] || { fail "install from the directory the files are in"; exit 3; }

tests=$(ls "$HERE"/test_*.py 2>/dev/null | wc -l | tr -d ' ')
say "   $(printf '%s\n' $MODULES | wc -l | tr -d ' ') modules, ${tests} test files, the pdfminer patch"

# A file that is present but not ours is worth knowing about: an older
# install leaves modules behind that this one never overwrites, and they sit
# in every test count for ever. Reported, never deleted -- deleting files in
# someone's directory is not this script's business.
for f in "$HERE"/test_*.py; do
    b="$(basename "$f")"
    case " $(cd "$HERE" && ls test_*.py | tr '\n' ' ') " in *" $b "*) ;; esac
done
if [ -f "$HERE/test_docmodel.py" ]; then
    say "   note: test_docmodel.py is here but is not part of this release."
    say "         It is from an older install and its tests can never run."
    say "         Remove it if you want the test counts to mean something."
fi

if [ "$CHECK_ONLY" -eq 1 ]; then
    say "== check only; nothing built"
    exit 0
fi

# --- 2. dependencies -------------------------------------------------------
say "== dependencies"
for cmd in python3 git; do
    command -v "$cmd" >/dev/null 2>&1 || { fail "$cmd not found"; exit 2; }
done
PYV="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
case "$PYV" in
    3.1[0-9]|3.[2-9][0-9]) say "   python3 $PYV" ;;
    *) fail "python3 $PYV is too old; 3.10+ needed"; exit 2 ;;
esac
command -v gs >/dev/null 2>&1 \
    && say "   ghostscript present" \
    || say "   ghostscript absent (only the render and crop tools need it)"

# --- 3. the patched pdfminer ----------------------------------------------
# Delegated to install-pdfminer-fork.sh, which is also plain text and also
# extracts nothing: it clones pdfminer.six, pins a commit, applies the
# glyph-identity patch and builds the result into the venv.
if [ "$DO_VENV" -eq 1 ]; then
    say "== patched pdfminer.six"
    args="--venv $VENV"
    [ "$REBUILD" -eq 1 ] && args="$args --rebuild"
    # shellcheck disable=SC2086
    if ! bash "$HERE/install-pdfminer-fork.sh" $args; then
        fail "the pdfminer build failed; see the output above"
        exit 3
    fi
else
    say "== venv skipped (--no-venv)"
fi

PY="$VENV/bin/python"
[ -x "$PY" ] || PY="python3"

# --- 4. does it actually read a PDF ---------------------------------------
# A venv that imports is not a venv that works. The patch exists to expose
# glyph names; if that is missing, everything downstream silently degrades to
# guessing, so it is checked here rather than discovered on a corpus.
if [ -x "$VENV/bin/python" ]; then
    say "== glyph identity"
    if "$PY" - <<'PYEOF'
import inspect
import sys
try:
    from pdfminer.layout import LTChar
except Exception as exc:
    print("   cannot import pdfminer:", exc)
    sys.exit(1)
# The attribute is assigned as `self.glyphname = ...`, which does NOT appear
# in `__init__.__code__.co_varnames` -- the first version of this check
# looked there and failed every install while the fork's own verifier was
# passing two lines above. Read the source instead: it is the only place the
# patch is visible without a PDF to parse.
try:
    src = inspect.getsource(LTChar.__init__)
except Exception as exc:
    print("   cannot read LTChar source:", exc)
    sys.exit(1)
if "glyphname" not in src:
    print("   LTChar does not set glyphname: the patch did not take")
    sys.exit(1)
print("   LTChar sets glyphname")
PYEOF
    then :; else fail "the patched pdfminer is not in $VENV"; exit 3; fi
fi

# --- 5. tests --------------------------------------------------------------
# About 450 run anywhere. The rest need real PDFs, which are not shipped
# (they are copyrighted). Point PDF2MMD_TEST_PDF and friends at your own to
# run those too; the gates are per TEST, so the number you see is the number
# that can run here.
if [ "$DO_TESTS" -eq 1 ] && [ -x "$VENV/bin/python" ]; then
    say "== tests"
    if ! "$PY" -m pytest -q --tb=line "$HERE"; then
        fail "tests failed"
        exit 4
    fi
elif [ "$DO_TESTS" -eq 1 ]; then
    say "== tests skipped (no venv)"
fi

say ""
say "ready."
say "   ./pdf2mmd.sh paper.pdf"
say "writes mmd-out/paper.md, .lines.json, .equations.json and the reports."
[ -x "$VENV/bin/python" ] && say "   python: $PY"
exit 0
