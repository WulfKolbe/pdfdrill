"""
commands._display_path — safe relative-path display. Bug A (sandbox test): cmd_svg
built its success message with `debug_dir.relative_to(target.parent)`, but Sidecar
absolutizes pdf_path (so debug_dir is absolute) while a relative CLI arg leaves
target.parent == '.' — relative_to then raises ValueError and svg crashes AFTER
rendering the SVGs fine. _display_path must never raise: it returns the relative
form when possible, else the path unchanged.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands as C


def test_relative_when_under_base():
    p = Path("/home/u/paper.pdf.drill/svg/tex")
    assert str(C._display_path(p, Path("/home/u"))) == "paper.pdf.drill/svg/tex"


def test_absolute_path_with_dot_base_does_not_raise():
    # the exact Bug A shape: absolute debug_dir, base '.' → return path, no crash
    p = Path("/abs/paper.pdf.drill/svg/tex")
    assert C._display_path(p, Path(".")) == p


def test_unrelated_paths_return_path():
    p = Path("/a/b/c")
    assert C._display_path(p, Path("/x/y")) == p


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try:
            t(); print(f"PASS {name}")
        except AssertionError as e:
            failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e:
            failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
