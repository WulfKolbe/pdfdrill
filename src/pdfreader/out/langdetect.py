#!/usr/bin/env python3
"""langdetect — the language guesser, run OUTSIDE pdf2mmd's venv.

`whats_that_code` requires google-re2, lxml, pygments, pyrankvote,
tree-sitter and tree-sitter-language-pack. pdf2mmd is a flat folder plus a
patched pdfminer, and none of that belongs in it: a reader that cannot be
installed without a tree-sitter binary is a worse reader.

So it is a TOOL, not an import. This script runs under its own interpreter
and speaks JSON over the pipe:

    {"id": "<the code>"}   in     ->    {"id": "python"}   out

    $PDF2MMD_LANG_PY    the interpreter that has it (default ~/.wtc-venv)

Absent or broken, the caller gets nothing back and the language stays
unknown -- which is the correct answer when nothing was asked.
"""
import json
import sys

try:
    from whats_that_code.election import guess_language_all_methods as guess
except Exception as exc:                                    # noqa: BLE001
    print(json.dumps({"__error__": str(exc)[:200]}))
    sys.exit(0)

data = json.load(sys.stdin)
out = {}
for key, code in data.items():
    try:
        out[key] = guess(code=code) or ""
    except Exception:                                       # noqa: BLE001
        out[key] = ""
print(json.dumps(out))
