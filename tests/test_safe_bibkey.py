"""
_safe_bibkey — a filesystem/URL-safe bibkey for artifact filenames. A doc whose
bibkey came from a spaced filename stem produced `... Language Models.distill.html`
(spaces), which drillui's whitespace-splitting path scanner truncated to
`Models.distill.html` → 404. Slugify spaces/hostile chars; keep clean ids as-is.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.commands import _safe_bibkey as S


def test_spaces_become_underscores():
    assert S("Verbalizable Representations Form a Global Workspace") \
        == "Verbalizable_Representations_Form_a_Global_Workspace"
    assert " " not in S("My Great Paper")


def test_clean_arxiv_id_preserved():
    assert S("2004.05631v1") == "2004.05631v1"
    assert S("math_0309136") == "math_0309136"


def test_hostile_chars_sanitized():
    assert "/" not in S("a/b\\c:d")
    assert S("a/b") == "a_b"
    assert S("café déjà.pdf") .replace("_", "")  # no exception, produces something


def test_never_empty():
    assert S("") == "doc"
    assert S("   ") == "doc"
    assert S("///") == "doc"


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try: t(); print(f"PASS {name}")
        except AssertionError as e: failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e: failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed: print(f"\n{len(failed)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} passed.")
