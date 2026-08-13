#!/bin/bash
# Continue the MOST RECENT conversation in this directory.
#
# This used to pin a session id (`--resume 7baec1d2-…`). After a crash the
# harness starts a NEW session, so the pinned id resumed the dead one and the
# work looked lost — it was not, it was in the new session. `--continue` always
# picks the latest, which is what "resume" was meant to mean.
#
# To reopen a SPECIFIC older session instead:  claude --resume <session-id>
# To pick one from a list:                     claude --resume
exec claude --continue --dangerously-skip-permissions "$@"
