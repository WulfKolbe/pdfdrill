r"""A command that SUCCEEDS must not be reported as a failure.

A downloaded filename can carry bytes that are not valid UTF-8 — real case:
`Dihedral homologi p\xe5 skjemaer og \xe9tale descent (Arthur M\xe5rtensson)`.
Python surfaces those as surrogate escapes, and `print()`ing one to a UTF-8
stdout raises UnicodeEncodeError. That raise happened inside the try around the
handler, so the CLI printed `Error [UnicodeEncodeError]` and exited 1 for a
`reporttex` run that had already written report.tex and compiled a 21-page
report.pdf with 229 equations. The work was done; only the summary could not be
spelled, and the exit code claimed otherwise.
"""
import io, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.cli import _emit

#: what a non-UTF-8 filename looks like after os.fsdecode
SURROGATE = "Dihedral homologi p\udce5 skjemaer og \udce9tale descent"


class _Utf8Stream(io.TextIOWrapper):
    """A strict UTF-8 text stream, like a real piped stdout."""
    def __init__(self):
        self._raw = io.BytesIO()
        super().__init__(self._raw, encoding="utf-8", errors="strict",
                         newline="")

    def value(self) -> bytes:
        self.flush()
        return self._raw.getvalue()


def test_plain_print_would_raise():
    """Pin the precondition — without it the other tests prove nothing."""
    s = _Utf8Stream()
    try:
        print(SURROGATE, file=s)
    except UnicodeEncodeError:
        return
    raise AssertionError("expected UnicodeEncodeError; the bug cannot recur")


def test_emit_does_not_raise_and_writes_the_bytes():
    s = _Utf8Stream()
    _emit(SURROGATE, s)                       # must not raise
    out = s.value()
    assert b"Dihedral homologi p" in out
    assert out.endswith(b"\n")
    # surrogateescape round-trips to the ORIGINAL bytes, so a consumer piping
    # this back into the shell gets the real name
    assert b"\xe5" in out and b"\xe9" in out


def test_emit_normal_text_is_unchanged():
    """The overwhelmingly common path must behave exactly like print()."""
    s = _Utf8Stream()
    _emit("2604.11744 — 28 equations", s)
    assert s.value().decode("utf-8") == "2604.11744 — 28 equations\n"


def test_emit_falls_back_when_surrogateescape_is_refused():
    """An ascii stream cannot encode the accents even as escapes; `replace`
    keeps the line readable rather than losing the output entirely."""
    raw = io.BytesIO()
    s = io.TextIOWrapper(raw, encoding="ascii", errors="strict", newline="")
    _emit(SURROGATE, s)
    raw.seek(0)
    assert b"Dihedral homologi p" in raw.getvalue()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
