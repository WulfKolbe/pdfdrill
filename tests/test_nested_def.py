"""A `\\def` inside another definition's body is not a definition of its own.

The collector scanned for every `\\def\\name` in the preamble, so a multi-line
definition whose BODY contains one emitted the inner text a second time, as a
standalone definition. Lifted out of its context the parameters are unbound:

    \\def\\lst@OpLiteratekey#1\\@nil@{\\let\\lst@ifxopliterate\\lst@if
                                  \\def\\lst@opliterate{#1}}

yielded, additionally, `\\def\\lst@opliterate{#1}` — and `#1` with no parameter
text is `! Illegal parameter number in definition of \\lst@opliterate`, which
failed all 9 TikZ/table graphics of a real thesis (AKolbe-BA, listings hacks in
its preamble).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.latex_source import _collect_macro_defs


def test_nested_def_is_not_emitted_separately():
    pre = (r"\def\lst@OpLiteratekey#1\@nil@{\let\lst@ifxopliterate\lst@if" "\n"
           r"                             \def\lst@opliterate{#1}}" "\n")
    defs = _collect_macro_defs(pre)
    assert len(defs) == 1, defs
    assert defs[0].startswith(r"\def\lst@OpLiteratekey")
    assert not any(d.strip() == r"\def\lst@opliterate{#1}" for d in defs)


def test_sibling_defs_are_both_kept():
    """Only NESTED ones are skipped — two independent defs must both survive."""
    pre = "\\def\\aa{1}\n\\def\\bb{2}\n"
    defs = [d.strip() for d in _collect_macro_defs(pre)]
    assert defs == ["\\def\\aa{1}", "\\def\\bb{2}"], defs


def test_def_inside_a_newcommand_body_is_skipped():
    pre = r"\newcommand{\outer}[1]{\def\inner{#1}\inner}" "\n"
    defs = _collect_macro_defs(pre)
    assert len(defs) == 1 and defs[0].startswith(r"\newcommand{\outer}"), defs
