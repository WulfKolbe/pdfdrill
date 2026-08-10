#!/bin/bash
# Invoke LgEval — NOT vendored. Sets the one non-obvious thing: the PARENT of
# the `lgeval` directory goes on PYTHONPATH, because evallg.py imports
# `lgeval.src.lg`, so the clone must be importable AS the package `lgeval`.
#
# PIN THE COMMIT. gitlab.com/dprl/lgeval HEAD (c94f6dd) imports
# `lgeval.msg_debug`, which the repository does not ship — it fails at import.
# 9831a3c is the last commit that runs. A fresh clone gets HEAD and will not
# work, which is the whole reason this file exists.
#
#   git clone https://gitlab.com/dprl/lgeval.git ~/.local/share/lgeval
#   git -C ~/.local/share/lgeval checkout 9831a3c
#
# github.com/DPRL/LgEval is 404; github.com/michaelyin/lgeval is Python 2
# (`print line`) and will not run on Python 3.
#
#   source tools/lgeval_env.sh
#   lgeval_score out.lg gold.lg
LGEVAL_HOME="${LGEVAL_HOME:-$HOME/.local/share/lgeval}"
LGEVAL_PIN="9831a3c"

lgeval_score() {
  if [ ! -d "$LGEVAL_HOME" ]; then
    echo "LgEval not installed at $LGEVAL_HOME — see the header of tools/lgeval_env.sh" >&2
    return 2
  fi
  local at
  at="$(git -C "$LGEVAL_HOME" rev-parse --short HEAD 2>/dev/null)"
  if [ "$at" != "$LGEVAL_PIN" ]; then
    echo "WARNING: LgEval is at $at, expected the pinned $LGEVAL_PIN;" >&2
    echo "         HEAD imports lgeval.msg_debug, which the repo does not ship." >&2
  fi
  PYTHONPATH="$(dirname "$LGEVAL_HOME")${PYTHONPATH:+:$PYTHONPATH}" \
    python3 -m lgeval.src.evallg "$@"
}
