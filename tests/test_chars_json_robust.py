"""
The .chars.json pdfplumber dump for a 1000-page book is 687-825MB; a non-atomic
write killed mid-dump (400s timeout) left a TRUNCATED file that persisted, and
every later `md`/`drill` re-read it → the same "Expecting ':' delimiter" at ~EOF.
Fix: write atomically (never truncated) + a cheap tail check so a pre-existing
truncated dump is regenerated instead of re-parsed.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands as C


def test_complete_json_file_detected():
    with tempfile.TemporaryDirectory() as d:
        good = Path(d) / "good.json"
        good.write_text('{"source": "x", "pages": [{"a": 1}]}')
        assert C._json_file_looks_complete(good) is True


def test_truncated_json_file_detected():
    with tempfile.TemporaryDirectory() as d:
        bad = Path(d) / "bad.json"
        # a dump cut off mid-content (no closing brace) — the harness case
        bad.write_text('{"source": "x", "pages": [{"a": 1}, {"b": 2')
        assert C._json_file_looks_complete(bad) is False


def test_missing_or_empty_is_incomplete():
    with tempfile.TemporaryDirectory() as d:
        assert C._json_file_looks_complete(Path(d) / "nope.json") is False
        empty = Path(d) / "e.json"; empty.write_text("")
        assert C._json_file_looks_complete(empty) is False


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try: t(); print(f"PASS {name}")
        except AssertionError as e: failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e: failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed: print(f"\n{len(failed)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} passed.")
