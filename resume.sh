#!/bin/bash
# Resume this project's Claude session.
#
# DEFAULT: --continue, the most recent session. A pinned id is opt-in and never
# hardcoded, because a hardcoded one is what broke: the script pinned a session,
# the harness crashed and started a NEW session, and the script kept reopening
# the dead one. The work was not lost — it was in the session the script would
# not open. A pinned id that no longer resolves now FAILS LOUDLY rather than
# silently starting a fresh session, which is the behaviour that looked like
# lost work.
#
#   ./resume.sh                          -> most recent session
#   PDFDRILL_SESSION=<id> ./resume.sh    -> that session, or exit 3
#   ./resume.sh --session <id>           -> same
#   ./resume.sh -- <extra claude args>   -> passed through
set -uo pipefail

CLAUDE_BIN="${CLAUDE_BIN:-claude}"
SESSION="${PDFDRILL_SESSION:-}"
PASS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --session) SESSION="${2:-}"; shift 2 ;;
    --session=*) SESSION="${1#*=}"; shift ;;
    --) shift; PASS+=("$@"); break ;;
    *) PASS+=("$1"); shift ;;
  esac
done

if ! command -v "$CLAUDE_BIN" >/dev/null 2>&1; then
  echo "resume.sh: '$CLAUDE_BIN' not on PATH" >&2
  exit 2
fi

if [ -n "$SESSION" ]; then
  # A pinned id must resolve. Exit 3 and say so — never degrade to a new
  # session, which is indistinguishable from the work having vanished.
  "$CLAUDE_BIN" --resume "$SESSION" --dangerously-skip-permissions "${PASS[@]}"
  rc=$?
  # capture rc FIRST: inside the message, `$?` is the previous echo's status,
  # so the error reported "(exit 0)" for a session that had just failed.
  if [ "$rc" -ne 0 ]; then
    echo "resume.sh: session '$SESSION' did not resume (exit $rc)." >&2
    echo "           NOT falling back to a new session — that is what hid the" >&2
    echo "           work last time. Run './resume.sh' for the most recent," >&2
    echo "           or 'claude --resume' to pick from a list." >&2
    exit 3
  fi
  exit 0
fi

exec "$CLAUDE_BIN" --continue --dangerously-skip-permissions "${PASS[@]}"
