"""
drillui `add` with filenames containing blanks and special characters
('The Everything Kids Giant Book of Jokes, Riddles and Brain Teasers
(Dahl, Wagner and Weintraub.) (z-lib.org).pdf'): the spec parser must accept
  * a QUOTED path (shell-style, via shlex) as ONE token,
  * an UNQUOTED path with spaces when the whole line names an existing file,
  * and keep the multi-doc + @list forms working.
"""
import sys
import tempfile
from pathlib import Path
import importlib.util

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

_spec = importlib.util.spec_from_file_location(
    "drillui_chat", REPO / "tools" / "drillui_chat.py")
dc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dc)

NASTY = ("The Everything Kids Giant Book of Jokes, Riddles and Brain Teasers "
         "(Dahl, Wagner and Weintraub.) (z-lib.org).pdf")


def test_quoted_path_is_one_token():
    for q in ('"', "'"):
        out = dc._expand_add_spec(f"{q}{NASTY}{q}")
        assert out == [NASTY], out


def test_unquoted_existing_file_with_spaces_is_one_token():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / NASTY
        p.write_bytes(b"%PDF-1.4")
        out = dc._expand_add_spec(str(p))          # no quotes at all
        assert out == [str(p)], out


def test_multi_doc_and_list_forms_still_work():
    out = dc._expand_add_spec("a.pdf b.pdf 2401.00001")
    assert out == ["a.pdf", "b.pdf", "2401.00001"]
    with tempfile.TemporaryDirectory() as d:
        lst = Path(d) / "more.txt"
        lst.write_text("# comment\nx.pdf\n\nhttps://arxiv.org/abs/2401.00002\n")
        out = dc._expand_add_spec(f"a.pdf @{lst}")
        assert out == ["a.pdf", "x.pdf", "https://arxiv.org/abs/2401.00002"]


def test_quoted_path_plus_more_docs():
    out = dc._expand_add_spec(f'"{NASTY}" other.pdf')
    assert out == [NASTY, "other.pdf"]


def test_suggest_path_repairs_case_and_char_typos():
    """The Axe case: 'DownLoads/axe-fx-2/Axe-Fx-II-0wners-Manual.pdf' (capital L
    + zero-for-O) must repair to the real Downloads/.../Axe-Fx-II-Owners-Manual.pdf."""
    with tempfile.TemporaryDirectory() as d:
        real = Path(d) / "Downloads" / "axe-fx-2" / "Axe-Fx-II-Owners-Manual.pdf"
        real.parent.mkdir(parents=True)
        real.write_bytes(b"%PDF-1.4")
        typo = str(Path(d) / "DownLoads" / "axe-fx-2" / "Axe-Fx-II-0wners-Manual.pdf")
        fixed = dc._suggest_path(typo)
        assert fixed is not None and Path(fixed) == real, fixed


def test_suggest_path_none_when_exists_or_absent():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "real.pdf"
        p.write_bytes(b"%PDF-1.4")
        assert dc._suggest_path(str(p)) is None            # exact hit → no suggestion
        # nothing remotely close → None (never invents a file)
        assert dc._suggest_path(str(Path(d) / "totally_unrelated_zzzzz.pdf")) is None


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
