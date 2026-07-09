"""
CLI recovery of an UNQUOTED filename with spaces: the shell splits it into several
args; `_reassemble_spaced_path` collapses a leading run back into one arg when the
space-join is a real file — so `pdfdrill distill My File.pdf` works like the quoted
form. The longest existing prefix wins, so a trailing positional (page number)
survives.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.cli import _reassemble_spaced_path as R


def test_rejoins_split_filename():
    with tempfile.TemporaryDirectory() as dd:
        f = Path(dd) / "My Great Paper.pdf"
        f.write_bytes(b"%PDF-1.4")
        split = str(f).split(" ")                     # what the shell produced
        assert R(split) == [str(f)]                   # collapsed back to one arg


def test_keeps_trailing_positional():
    with tempfile.TemporaryDirectory() as dd:
        f = Path(dd) / "My File.pdf"
        f.write_bytes(b"%PDF")
        split = str(f).split(" ") + ["5"]             # e.g. `page My File.pdf 5`
        assert R(split) == [str(f), "5"]              # longest-existing prefix, 5 kept


def test_keeps_trailing_flag():
    with tempfile.TemporaryDirectory() as dd:
        f = Path(dd) / "My File.pdf"
        f.write_bytes(b"%PDF")
        split = str(f).split(" ") + ["--embed"]
        assert R(split) == [str(f), "--embed"]


def test_noop_when_first_arg_already_exists():
    with tempfile.TemporaryDirectory() as dd:
        f = Path(dd) / "nospace.pdf"
        f.write_bytes(b"%PDF")
        assert R([str(f), "extra"]) == [str(f), "extra"]   # unchanged


def test_noop_when_no_matching_file():
    assert R(["not", "a", "real", "file.pdf"]) == ["not", "a", "real", "file.pdf"]
    assert R(["https://arxiv.org/abs/2501.06699"]) == ["https://arxiv.org/abs/2501.06699"]
    assert R([]) == []


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try: t(); print(f"PASS {name}")
        except AssertionError as e: failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e: failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed: print(f"\n{len(failed)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} passed.")
