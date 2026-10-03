#!/usr/bin/env bash
# install-pdfminer-fork.sh — build the patched pdfminer.six that pdf2mmd needs.
#
# pdf2mmd depends on glyph identity that stock pdfminer.six parses and then
# discards: the PostScript glyph name behind `(cid:N)`, the character code, and
# the text rendering mode. The patch is ~160 additive lines across five files
# and changes no existing behaviour (verified byte-identical over 1.16M LTChar
# records), but it is not upstream, so it has to be built.
#
#   ./install-pdfminer-fork.sh                  # isolated venv (recommended)
#   ./install-pdfminer-fork.sh --user           # pip --user, no venv
#   ./install-pdfminer-fork.sh --venv ~/.pdfmm  # a venv somewhere else
#   ./install-pdfminer-fork.sh --check          # only verify what is installed
#   ./install-pdfminer-fork.sh --rebuild        # rebuild even if one works
#
# The venv is the default BECAUSE it leaves your existing pdfminer.six alone.
# Other tools that pin `pdfminer.six==<release>` keep working; only pdf2mmd
# uses the patched build.
#
# EXIT CODES
#   0 ok   1 usage   2 missing dependency   3 build or verification failed

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH="$HERE/pdfminer-glyph-identity.patch"
UPSTREAM="https://github.com/pdfminer/pdfminer.six.git"
# The commit the patch was made against. It also applies to the tip as of
# writing; pinning keeps the build reproducible if upstream moves.
PIN="a18de2a"
VENV="$HERE/.pdfmm-venv"
MODE="venv"
REBUILD=0
CHECK=0        # a separate flag, so --check and --venv can be combined in
               # either order; as modes they silently overrode each other

while [ $# -gt 0 ]; do
    case "$1" in
        --user)   MODE="user"; shift ;;
        --venv)   VENV="$2"; shift 2 ;;
        --check)  CHECK=1; shift ;;
        --rebuild) REBUILD=1; shift ;;
        -h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 1 ;;
    esac
done

# ---- what "installed correctly" means -------------------------------------
# Not "the import works": stock pdfminer imports fine and silently produces
# output with no glyph identity in it. The check exercises the actual feature.
verify() {
    "$1" - <<'PY'
import sys
try:
    from pdfminer.encodingdb import EncodingDB
    from pdfminer.layout import LTChar
    from pdfminer.pdffont import PDFFont
except ImportError as exc:
    print(f"  pdfminer not importable: {exc}"); sys.exit(1)

ok = True
if not hasattr(PDFFont, "to_glyphname"):
    print("  PDFFont.to_glyphname missing"); ok = False
if not hasattr(EncodingDB, "get_encoding_names"):
    print("  EncodingDB.get_encoding_names missing"); ok = False
import inspect
src = inspect.getsource(LTChar.__init__)
for attr in ("cid", "glyphname", "render_mode"):
    if attr not in src:
        print(f"  LTChar.{attr} missing"); ok = False

if ok:
    # the feature itself: a TeX maths name with no Unicode equivalent
    from pdfminer.psparser import PSLiteral
    diff = [2] + [PSLiteral(n) for n in
                  ("theta", "chi", "lscript", "theta1", "alpha", "star")]
    names = EncodingDB.get_encoding_names("StandardEncoding", diff)
    uni = EncodingDB.get_encoding("StandardEncoding", diff)
    if names.get(7) != "star":
        print(f"  cid 7 resolved to {names.get(7)!r}, expected 'star'"); ok = False
    elif 7 in uni:
        print("  unexpected: 'star' has a Unicode mapping here"); ok = False
    else:
        import pdfminer
        print(f"  ok: pdfminer {pdfminer.__version__} at {pdfminer.__file__}")
        print("  cid 7 -> 'star'  (no Unicode equivalent; stock gives (cid:7))")
sys.exit(0 if ok else 1)
PY
}

if [ "$CHECK" = "1" ]; then
    PY="python3"
    [ -x "$VENV/bin/python" ] && PY="$VENV/bin/python"
    echo "checking $PY"
    verify "$PY" && { echo "the patched build is in place"; exit 0; }
    echo "this python does NOT have the patched pdfminer" >&2
    exit 3
fi

# A working venv is expensive to rebuild (a clone plus several pip installs)
# and rebuilding one is never what you wanted. Re-running this script to pick
# up missing MODULES is the common case, so an existing, verified venv is left
# exactly as it is.
if [ "$REBUILD" != "1" ] && [ -x "$VENV/bin/python" ] && \
        (cd / && verify "$VENV/bin/python" >/dev/null 2>&1); then
    echo "== the patched pdfminer is already installed at"
    echo "   $VENV"
    (cd / && verify "$VENV/bin/python")
    echo
    echo "Nothing to do. Use --rebuild to build it again from scratch."
    exit 0
fi

command -v git >/dev/null    || { echo "missing dependency: git" >&2; exit 2; }
command -v python3 >/dev/null || { echo "missing dependency: python3" >&2; exit 2; }
[ -f "$PATCH" ] || { echo "patch not found: $PATCH" >&2; exit 2; }

# Build inside the install folder, not in /tmp. Two reasons: a temp dir on a
# small or noexec /tmp makes this fail for no good reason, and everything this
# script touches should be visible in the folder you ran it from. It is
# removed on exit, success or failure.
BUILD="$HERE/.pdfmm-build"
rm -rf "$BUILD"
mkdir -p "$BUILD" || { echo "cannot write to $HERE" >&2; exit 3; }
trap 'rm -rf "$BUILD"' EXIT
echo "   building in $BUILD (removed when done)"

echo "== cloning pdfminer.six"
git clone -q "$UPSTREAM" "$BUILD/src"
cd "$BUILD/src"
if git cat-file -e "$PIN^{commit}" 2>/dev/null; then
    git checkout -q "$PIN"
    echo "   pinned to $PIN"
else
    echo "   ! pin $PIN not found; using the default branch" >&2
fi

echo "== applying the glyph-identity patch"
if ! git apply --check "$PATCH" 2>/dev/null; then
    echo "   patch does not apply to this checkout." >&2
    echo "   Upstream has probably moved. Re-cut the patch against the commit" >&2
    echo "   you want, or report the commit you are on." >&2
    exit 3
fi
git apply "$PATCH"
echo "   applied ($(grep -c '^diff --git' "$PATCH") files)"

if [ "$MODE" = "venv" ]; then
    echo "== creating venv at $VENV"
    python3 -m venv "$VENV" 2>/dev/null || {
        echo "   python3-venv is not available." >&2
        echo "   Install it (Debian/Ubuntu: apt install python3-venv)," >&2
        echo "   or re-run with --user." >&2
        exit 2; }
    PY="$VENV/bin/python"
    "$PY" -m pip install -q --upgrade pip >/dev/null 2>&1 || true
    echo "== installing into the venv"
    "$PY" -m pip install -q "$BUILD/src"
    # pdf2mmd itself needs these; the venv must be self-sufficient, including
    # pytest, because the README tells you to run the tests from it
    "$PY" -m pip install -q pillow scipy pytest
else
    PY="python3"
    echo "== installing with pip --user"
    "$PY" -m pip install -q --user "$BUILD/src"
    "$PY" -m pip install -q --user pillow scipy pytest
fi

echo "== verifying"
# Leave the build tree first. Verifying from inside it imports the SOURCE
# directory rather than the installed package, so the check would pass and the
# installation still be broken once the temporary build tree is removed.
cd /
verify "$PY" || { echo "verification FAILED — not usable" >&2; exit 3; }

echo
if [ "$MODE" = "venv" ]; then
    cat <<EOF
Done. pdf2mmd.sh finds this venv automatically when it sits at
  $HERE/.pdfmm-venv

If you put it elsewhere, point pdf2mmd at it:
  PDFMM_PYTHON="$PY" ./pdf2mmd.sh book.pdf 1-20

Your system pdfminer.six is untouched.
EOF
else
    cat <<EOF
Done, installed for your user. Note this REPLACES pdfminer.six for every tool
that uses your user site-packages. To undo:
  python3 -m pip uninstall pdfminer.six && python3 -m pip install pdfminer.six
EOF
fi
