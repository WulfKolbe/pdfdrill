r"""A bibkey with a space, a parenthesis or a `+` produced an EMPTY report table.

The TiddlyWiki projector sanitises every tiddler title
(`re.sub(r"[^A-Za-z0-9_\-\.]", "_", t)`), so `1611.03955 (1)_EQ0001` is stored
as `1611.03955__1__EQ0001`. `build_report` derived its prefix from the FILENAME
and matched the RAW form, so `rows_for` matched nothing and the report said
"0 inline formulas, 0 display equations" for a document whose model held 85
equations and 377 formulas.

Library-wide: 81 documents, 2,676 equations and 6,132 inline formulas hidden —
every one a directory whose name carries a character the projector rewrites.
The report was not empty because the math was missing; it was empty because the
two sides spelled the same key differently.
"""
import re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.report_tex import rows_for, first_pages, sanitize_title


def _tiddlers(prefix):
    return [
        {"title": f"{prefix}_EQ0001", "latex": "a = b", "page": "1"},
        {"title": f"{prefix}_EQ0002", "latex": r"\frac{x}{y}", "page": "2"},
        {"title": f"{prefix}_FO0001", "latex": r"\alpha", "page": "1"},
        {"title": f"{prefix}_TAB0001", "latex": "t", "page": "3"},
        {"title": f"{prefix}_PARA_0001", "text": "prose", "page": "1"},
    ]


def test_bibkey_with_space_and_parens_still_matches():
    """The real 1611.03955 (1) shape."""
    bibkey = "1611.03955 (1)"
    tids = _tiddlers(sanitize_title(bibkey))          # what the projector wrote
    assert tids[0]["title"] == "1611.03955__1__EQ0001"
    fo, eq, tab, dia = rows_for(tids, bibkey)         # what the report passes
    assert (len(eq), len(fo), len(tab)) == (2, 1, 1)


def test_plain_bibkey_unaffected():
    """The 2,214 documents whose names need no rewriting must behave as before —
    a fix that only worked for the broken case would be a different bug."""
    bibkey = "2604.11744"
    fo, eq, tab, dia = rows_for(_tiddlers(bibkey), bibkey)
    assert (len(eq), len(fo), len(tab)) == (2, 1, 1)


def test_other_rewritten_characters():
    """`+`, `&`, `#` and non-ASCII letters are rewritten too (IDG1+2handout was
    in the affected set)."""
    for bibkey in ["IDG1+2handout", "a&b", "Müller 2019", "x#y", "Math - 2023 v2"]:
        fo, eq, tab, dia = rows_for(_tiddlers(sanitize_title(bibkey)), bibkey)
        assert len(eq) == 2, bibkey


def test_sanitizer_agrees_with_the_projector():
    """report_tex keeps its OWN copy of the sanitiser to avoid importing the
    whole docops/docmodel chain. Two copies of one rule is how they drift, so
    assert they agree — this test is the reason the copy is allowed."""
    from docops.projectors.tiddlywiki import _sanitize_title
    for t in ["1611.03955 (1)_EQ0001", "IDG1+2handout_FO1", "a b", "x(y)",
              "ok_-.1", "Math Methods - 2023_EQ1", "Müller_EQ1", "", "_-.",
              "100%_EQ1", "a/b\\c_EQ1"]:
        assert sanitize_title(t) == _sanitize_title(t), t


def test_first_pages_uses_the_same_key():
    """`first_pages` matches transclusions `{{key_FO...||...}}` and had the same
    raw-key bug; a fix to rows_for alone would leave inline formulas page-less."""
    bibkey = "1611.03955 (1)"
    pref = sanitize_title(bibkey)
    tids = [{"title": f"{pref}_PARA_0001", "page": "7",
             "text": "see {{%s_FO0001||tmpl}} here" % pref}]
    assert first_pages(tids, bibkey) == {f"{pref}_FO0001": "7"}


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
