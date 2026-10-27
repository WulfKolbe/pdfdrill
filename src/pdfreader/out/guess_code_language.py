#!/usr/bin/env python3
"""guess_code_language — the programming-language guesser, run as a TOOL.

`whats_that_code` requires google-re2, lxml, pygments, pyrankvote,
tree-sitter and tree-sitter-language-pack. pdf2mmd is a flat folder plus a
patched pdfminer, and none of that belongs in it: a reader that cannot be
installed without a tree-sitter binary is a worse reader.

So it is a TOOL, not an import. This script runs under its own interpreter
and speaks JSON over the pipe:

    {"id": "<the code>"}   in     ->    {"id": "python"}   out

    $PDF2MMD_LANG_PY    the interpreter that has it (default ~/.wtc-venv)

Absent or broken, the caller gets `{"__error__": …}` and the language stays
unknown -- which is the correct answer when nothing was asked.

THE NAME AND THE STRUCTURE ARE BOTH DELIBERATE, and both were defects.

This file was called `langdetect.py`, which is also a package this project
declares in its `lang` extra. The name alone was harmless until something put
`src/pdfreader/out` on `sys.path` -- pytest's prepend import mode does, for
any `test_*.py` in this directory -- and from then on `import langdetect`
found THIS FILE in every process that followed.

And the import guard used to run at module level and end in `sys.exit(0)`.
For a tool reading a pipe that is right. For an importer it is fatal and
UNCATCHABLE: `SystemExit` inherits from `BaseException`, so
`features.extract_language`'s `except Exception` around its own
`from langdetect import …` could not see it, and a function documented to
always answer took its caller down instead -- exiting 0, with this file's
error JSON as the process's last word. Measured: 33 test failures, varying
with collection order (2026-10-26).

Hence: the work is in `main()`, under `__main__`, and importing this file
does nothing at all.
"""
import json
import sys


def _guesser():
    """The imported function, or None with the reason -- never an exit."""
    try:
        from whats_that_code.election import guess_language_all_methods as guess
    except Exception as exc:                                    # noqa: BLE001
        return None, str(exc)[:200]
    return guess, None


def main(argv=None) -> int:
    guess, why = _guesser()
    if guess is None:
        print(json.dumps({"__error__": why}))
        return 0                       # the protocol: one JSON object, exit 0
    data = json.load(sys.stdin)
    out = {}
    for key, code in data.items():
        try:
            out[key] = guess(code=code) or ""
        except Exception:                                       # noqa: BLE001
            out[key] = ""
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
