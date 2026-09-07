#!/usr/bin/env bash
#
# drill_full_sandbox.sh — drill_full.sh as the Claude.ai sandbox runs it.
#
#   bash tools/drill_full_sandbox.sh <pdf|url|arxiv-id> [bibkey]
#
# It is a WRAPPER, not a copy. The sandbox differs from the plain script in
# exactly two behaviours, and both are knobs in drill_full.sh itself:
#
#   DRILL_LOAD_ENV=1          source $REPO/.env into the SHELL, so the
#                             script's own `[ -n "${MATHPIX_APP_ID:-}" ]`
#                             guard can fire (pdfdrill reads .env internally,
#                             but a shell guard cannot see that).
#   DRILL_MATHPIX_NO_FORCE=1  never `mathpix --force` when <doc>.lines.json is
#                             already cached — --force re-uploads and
#                             re-charges.
#
# It was a 200-line COPY until 647. Two long scripts kept "in step" by
# discipline is exactly the drift HANDOVER-RULES rule 11 is about: the failure
# recording could then be right in one and absent in the other, and a run of
# the wrong one would read clean either way. Wrapping is the smaller change and
# the one that cannot drift.
set -uo pipefail
export DRILL_LOAD_ENV=1
export DRILL_MATHPIX_NO_FORCE=1
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/drill_full.sh" "$@"
