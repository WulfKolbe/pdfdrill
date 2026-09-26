#!/usr/bin/env bash
# Put the host into every archive folder's name, on a machine whose paths are
# not this machine's.
#
#   ./tools/rename-library-hosts.sh                      # dry run, library auto-found
#   ./tools/rename-library-hosts.sh --apply              # rename
#   ./tools/rename-library-hosts.sh ~/ws/pdfdrill-library --apply
#
# THE CAPABILITY IS `pdfdrill relocate`, not this file. A migration that lives
# only in tools/ is invisible to `steps`, `--ensure` and the planner (audit A4),
# so the rename itself is a registered command with `--library` and a dry-run
# default. All this script does is FIND the two paths — the checkout and the
# library — on a host where neither is where it is here, and refuse to guess
# when it cannot.
set -uo pipefail

APPLY=0; ASSUME_YES=0; LIB=""
for a in "$@"; do
  case "$a" in
    --apply) APPLY=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
    -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "unknown option: $a" >&2; exit 2 ;;
    *)  LIB="$a" ;;
  esac
done

# ── the checkout: this script's own grandparent, so a clone anywhere works ────
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRILL="$HERE/pdfdrill"
if [ ! -x "$DRILL" ]; then
  echo "No pdfdrill wrapper at $DRILL — is this a PDFDRILL checkout?" >&2
  exit 1
fi

# ── the library: argument, env, config, then the usual places ─────────────────
# A NAMED PATH NEVER FALLS BACK. Searching on from a path the user typed means
# that a typo, or a stale $PDFDRILL_LIBRARY, silently renames a DIFFERENT
# library — on the wrong machine's copy, 519 folders deep, with no error. If it
# was named, it exists or the script stops.
NAMED=""
if [ -n "$LIB" ]; then NAMED="argument"
elif [ -n "${PDFDRILL_LIBRARY:-}" ]; then LIB="$PDFDRILL_LIBRARY"; NAMED="\$PDFDRILL_LIBRARY"
fi
if [ -n "$NAMED" ] && [ ! -d "$LIB" ]; then
  echo "The library named by $NAMED does not exist: $LIB" >&2
  echo "Refusing to look elsewhere — a fallback here renames the wrong library." >&2
  exit 1
fi
if [ -z "$LIB" ]; then
  LIB="$("$DRILL" config 2>/dev/null | awk '/^  library_root/ {print $3}')"
fi
if [ -z "$LIB" ] || [ ! -d "$LIB" ]; then
  for c in "$HOME/workspace/pdfdrill-library" "$HOME/pdfdrill-library" \
           "$HOME/MX/pdfdrill-library" "/srv/pdfdrill-library"; do
    [ -d "$c" ] && { LIB="$c"; break; }
  done
fi
if [ -z "$LIB" ] || [ ! -d "$LIB" ]; then
  cat >&2 <<'MSG'
Cannot find the library. Name it, and nothing is guessed:
  ./tools/rename-library-hosts.sh /path/to/pdfdrill-library [--apply]
or set it once:  pdfdrill config --library-root /path/to/pdfdrill-library
MSG
  exit 1
fi
LIB="$(cd "$LIB" && pwd)"

# A directory that merely exists is not a library. One doc folder holding its
# own PDF is the cheap proof — and it is the same test `relocate` uses.
if ! find "$LIB" -mindepth 2 -maxdepth 2 -name '*.pdf' -print -quit | grep -q .; then
  echo "$LIB holds no <stem>/<stem>.pdf — that is not a pdfdrill library." >&2
  exit 1
fi

echo "checkout : $HERE"
echo "library  : $LIB"
echo "folders  : $(find "$LIB" -mindepth 1 -maxdepth 1 -type d | wc -l)"
echo

# A rename pulls a folder out from under anything serving it; the bridge then
# 404s on a path that was valid a second ago, which reads as a drillui bug.
if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ':8787'; then
  echo "! Something is listening on :8787 — stop the drillui bridge first," >&2
  echo "  or a request mid-rename gets a 404 for a folder that is moving." >&2
  [ "$APPLY" = 1 ] && [ "$ASSUME_YES" = 0 ] && { echo "  Refusing; pass --yes to override." >&2; exit 1; }
  echo
fi

export PDFDRILL_NO_PREFLIGHT=1 PYTHONDONTWRITEBYTECODE=1

echo "=== DRY RUN ==============================================="
"$DRILL" relocate --library "$LIB" || exit $?
echo

if [ "$APPLY" != 1 ]; then
  echo "Dry run only. Re-run with --apply to rename."
  exit 0
fi

if [ "$ASSUME_YES" != 1 ]; then
  printf 'Apply the plan above to %s ? [y/N] ' "$LIB"
  read -r reply </dev/tty || reply=""
  case "$reply" in y|Y|yes|YES) ;; *) echo "Aborted; nothing moved."; exit 0 ;; esac
fi

echo
echo "=== APPLY ================================================="
"$DRILL" relocate --library "$LIB" --apply
