"""
tools/tiddlers_to_md.py — tiddlers.json → per-tiddler .md + .md.meta export
(the on-disk TiddlyWiki/llmwiki form for the Claude.ai sandbox).
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import tiddlers_to_md as T


def test_tiddler_files_text_to_md_fields_to_meta():
    md, meta = T.tiddler_files({
        "title": "K_H19", "type": "text/markdown",
        "tags": "section K", "caption": "Proof of Lemma",
        "text": "# {{!!caption}}\n\nbody.", "label": "thm:scaling",
        "lean4": "theorem t :=\n  by sorry"})        # multi-line field
    assert md == "# {{!!caption}}\n\nbody."           # text → .md verbatim
    lines = meta.splitlines()
    assert lines[0] == "title: K_H19"                 # identity fields lead
    assert "type: text/markdown" in lines
    assert "label: thm:scaling" in lines
    assert "text:" not in meta                        # text is NOT in .meta
    # multi-line field collapsed to single line (TiddlyWiki .meta is single-line)
    assert "lean4: theorem t :=   by sorry" in meta


def test_export_writes_files_and_disambiguates():
    tiddlers = [
        {"title": "K_H1", "type": "text/markdown", "text": "alpha"},
        {"title": "K/H1", "type": "text/markdown", "text": "beta"},   # → same safe name
        {"title": "FO", "type": "text/vnd.tiddlywiki", "text": "<$latex/>"},
    ]
    with tempfile.TemporaryDirectory() as dd:
        n, out = T.export_tiddlers(tiddlers, dd, bibkey="2110.11150")
        assert n == 3
        assert out.name == "2110.11150"               # per-document folder
        assert (out / "K_H1.md").read_text() == "alpha"
        assert (out / "K_H1.md.meta").exists()
        # the colliding title got a distinct file (K_H1 vs K_H1~1)
        mds = sorted(p.name for p in out.glob("*.md"))
        assert "K_H1.md" in mds and "K_H1~1.md" in mds
        # the template tiddler keeps its wikitext type in the meta
        assert "type: text/vnd.tiddlywiki" in (out / "FO.md.meta").read_text()


def test_safe_filename():
    assert T.safe_filename("2110.11150_THM0003") == "2110.11150_THM0003"
    assert T.safe_filename('a/b:c*?"<>|') == "a_b_c_"
    assert T.safe_filename("") == "untitled"


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
