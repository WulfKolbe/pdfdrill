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
#   ./install-pdfminer-fork.sh --here           # into the ACTIVE interpreter
#                                               #   (the right mode inside a venv,
#                                               #   where --user cannot work)
#   ./install-pdfminer-fork.sh --venv ~/.pdfmm  # a venv somewhere else
#   ./install-pdfminer-fork.sh --check          # only verify what is installed
#   ./install-pdfminer-fork.sh --rebuild        # rebuild even if one works
#   ./install-pdfminer-fork.sh --here --with-pdf2mmd-extras
#                                               # …and pdf2mmd's own deps
#                                               #   (pillow scipy pytest). The
#                                               #   venv mode installs them
#                                               #   anyway; --here/--user do
#                                               #   NOT without this flag.
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
# EXTRAS — pdf2mmd's own runtime/test deps, NOT the fork's.
#
# They used to be installed in all three modes. An auditing session (finding G)
# named what that does outside the venv: `bootstrap.sh` calls this script in
# `--here` mode to get ONE thing, `LTChar.glyphname`, and got scipy, pillow and
# pytest put into the user's active environment as well — unasked, unannounced,
# and scipy is tens of megabytes. A script that installs a patch may not also
# install a toolchain. In the venv mode they stay, because that venv exists for
# pdf2mmd and nothing else imports from it; in the other two they are opt-in.
EXTRAS="pillow scipy pytest"
WITH_EXTRAS=0
CHECK=0        # a separate flag, so --check and --venv can be combined in
               # either order; as modes they silently overrode each other

while [ $# -gt 0 ]; do
    case "$1" in
        --user)   MODE="user"; shift ;;
        --here)   MODE="here"; shift ;;
        --venv)   VENV="$2"; shift 2 ;;
        --check)  CHECK=1; shift ;;
        --rebuild) REBUILD=1; shift ;;
        --with-pdf2mmd-extras) WITH_EXTRAS=1; shift ;;
        -h|--help) sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
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
    # BOTH interpreters are REPORTED; only ONE of them decides the exit code.
    #
    # 905o made this check both, because checking only the venv masked a
    # clobbered user-site install. But it then set rc=0 if EITHER answered yes,
    # and an auditing session (finding F) found what that means: `bootstrap.sh`
    # gates the build on `--check >/dev/null 2>&1`, so on a machine with a good
    # pdf2mmd venv and stock pdfminer in the active interpreter the check
    # succeeded, the build was skipped, the NOTE went to a discarded stdout,
    # and the install ended with no `LTChar.glyphname` — silently, which is the
    # whole failure class P1 belongs to.
    #
    # A check answers for the interpreter THAT WILL IMPORT IT. pdfdrill imports
    # pdfminer from the active `python3`, so that is the answer; the venv is
    # pdf2mmd's and is information, never the verdict.
    echo "checking python3 (the active interpreter — the one pdfdrill imports from)"
    if (cd / && verify "python3"); then
        rc=0
    else
        rc=3
        echo "  -> the ACTIVE interpreter does NOT have the patched pdfminer" >&2
    fi
    if [ -x "$VENV/bin/python" ]; then
        echo "also checking $VENV/bin/python (pdf2mmd's venv — reported, not the verdict)"
        if (cd / && verify "$VENV/bin/python"); then
            if [ "$rc" != "0" ]; then
                echo
                echo "NOTE: the venv has it, the active \`python3\` does NOT, and"
                echo "pdfdrill's glyph-identity features follow the active one, so"
                echo "they are NOT available. This check therefore FAILS. Restore:"
                echo "  bash vendor/install-pdfminer-fork.sh --here --rebuild   # in a venv"
                echo "  bash vendor/install-pdfminer-fork.sh --user --rebuild   # outside one"
            fi
        else
            echo "  -> the venv does NOT have it either" >&2
        fi
    fi
    [ "$rc" = "0" ] && echo "the patched build is in place"
    exit "$rc"
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

# ---- the version has to satisfy the pin that would otherwise replace it ----
# P1 (found by an auditing session, 2026-10-20): `pip install -r
# requirements.txt` and `pip install -e .` both REMOVE this build, and so does
# CoCalc's imageserver install. Nothing in pdfdrill asks for that — pdfdrill's
# own pin is `pdfminer.six>=20221105`. pdfPLUMBER pins `pdfminer.six==<release>`
# EXACTLY, so pip resolves that pin, sees setuptools-scm's git-describe version
# (`20260108.dev6+ga18de2a9c`, which is NOT equal to 20260107), and installs
# stock pdfminer over the patch. The install then looks clean and
# `LTChar.glyphname` is gone.
#
# A LOCAL VERSION SEGMENT is exactly the PEP 440 tool for this: `20260107+…`
# satisfies `==20260107` (checked: packaging.SpecifierSet('==20260107')
# .contains('20260107+ga18de2a9c') is True), while still naming itself as a
# local build. So the build is versioned as the release pdfplumber asks for,
# plus the upstream sha — and pip leaves it alone instead of replacing it.
#
# The release is READ from the installed pdfplumber rather than hardcoded, so a
# future pdfplumber that pins a different one keeps working.
pin_release() {
    python3 - <<'PYV' 2>/dev/null
import re
try:
    import importlib.metadata as md
    for r in md.requires("pdfplumber") or []:
        m = re.match(r"\s*pdfminer\.six\s*==\s*([^\s,;]+)", r)
        if m:
            print(m.group(1)); break
except Exception:
    pass
PYV
}

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

WANT="$(pin_release || true)"
if [ -n "${WANT:-}" ]; then
    SHA="$(git rev-parse --short=10 HEAD)"
    export SETUPTOOLS_SCM_PRETEND_VERSION="${WANT}+glyphid.g${SHA}"
    echo "== versioning this build $SETUPTOOLS_SCM_PRETEND_VERSION"
    echo "   (pdfplumber pins pdfminer.six==$WANT; a local segment satisfies it,"
    echo "    so a later pip run resolves the pin to THIS build instead of"
    echo "    replacing it with stock pdfminer — see P1 in the header)"
else
    echo "== no pdfplumber pin found; leaving the version to setuptools-scm" >&2
    echo "   A later \`pip install\` may replace this build. Re-run --check after." >&2
fi

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
    # pytest, because the README tells you to run the tests from it. This is
    # the ONE mode where they belong: the venv is built for pdf2mmd and nothing
    # else uses it. See EXTRAS below for why the other two modes dropped them.
    echo "== installing pdf2mmd's own deps into the venv (pillow scipy pytest)"
    "$PY" -m pip install -q $EXTRAS
elif [ "$MODE" = "here" ]; then
    # INTO THE ACTIVE INTERPRETER. `pip install --user` REFUSES inside a venv
    # ("User site-packages are not visible in this virtualenv"), so on the
    # documented install — fresh clone, fresh venv, bootstrap.sh — the --user
    # mode cannot put the fork anywhere. This mode installs into whatever
    # python3 is active, which in a venv is the venv and outside one is the
    # system/user interpreter pip would choose anyway.
    PY="python3"
    echo "== installing into the active interpreter ($("$PY" -c 'import sys;print(sys.prefix)'))"
    "$PY" -m pip install -q "$BUILD/src"
    if [ "$WITH_EXTRAS" = "1" ]; then
        echo "== installing pdf2mmd's own deps as asked ($EXTRAS)"
        "$PY" -m pip install -q $EXTRAS
    fi
else
    PY="python3"
    echo "== installing with pip --user"
    "$PY" -m pip install -q --user "$BUILD/src"
    if [ "$WITH_EXTRAS" = "1" ]; then
        echo "== installing pdf2mmd's own deps as asked ($EXTRAS)"
        "$PY" -m pip install -q --user $EXTRAS
    fi
fi

echo "== verifying"
# Leave the build tree first. Verifying from inside it imports the SOURCE
# directory rather than the installed package, so the check would pass and the
# installation still be broken once the temporary build tree is removed.
cd /
verify "$PY" || { echo "verification FAILED — not usable" >&2; exit 3; }

# Verifying the FEATURE is not enough to know the build will still be here
# tomorrow: P1 is about a later `pip install` replacing it. So report the one
# fact that predicts that — whether the installed version satisfies the pin pip
# will resolve.
WANT="${WANT:-$(pin_release || true)}" \
PDFMM_PY="$PY" "$PY" - <<'PYS' || true
import os
want = os.environ.get("WANT") or ""
try:
    import importlib.metadata as md
    v = md.version("pdfminer.six")
except Exception as exc:                                      # noqa: BLE001
    print(f"  ! cannot read the installed pdfminer version ({exc})"); raise SystemExit(0)
if not want:
    print(f"  ! pdfplumber pin unknown; version {v} may be replaced by a later pip run")
    raise SystemExit(0)
try:
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version
    ok = SpecifierSet(f"=={want}").contains(Version(v))
except Exception:                                              # noqa: BLE001
    ok = v.split("+")[0] == want
if ok:
    print(f"  survives a later pip run: {v} satisfies pdfplumber's pdfminer.six=={want}")
else:
    print(f"  ! WILL BE REPLACED: {v} does not satisfy pdfplumber's "
          f"pdfminer.six=={want}. The next `pip install` of anything that pulls "
          f"pdfplumber removes this build (P1). Re-run this script after it, or "
          f"use the venv mode (the default), which pip never touches.")
PYS

echo
if [ "$MODE" = "here" ]; then
    cat <<EOF
Done, installed into the active interpreter. To undo:
  python3 -m pip uninstall pdfminer.six && python3 -m pip install pdfminer.six
EOF
elif [ "$MODE" = "venv" ]; then
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
