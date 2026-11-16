r"""A row's demotion belongs to that row, not to its position in the report.

THE DEFECT. `inkconvert.convert` read each measured row's render status as

    rendered = did_render[len(out)]

an index into `report_tex.demoted_flags(tex_body)` — the whole report's EQ
rows, in table order. 614 had already established that the TSV may hold FEWER
rows than the tex names: a row broken across a page break bounds no rectangle
on either side (613/619), so `inkmeasure` measures it on neither and leaves it
out. From the first such row onward, every TSV row was given ANOTHER row's
demotion.

MEASURED over the 514 staged documents in work/run-files/t0131-measure/run
that carry a built measurement (report.compare.tsv + report.tex): every single
one has fewer TSV rows than tex rows, and 71 of them hold at least one row
whose `rendered` flag belongs to a different row — 777 rows in all. The worst:

    sigma26-086    354 of 741      sigma26-087     90 of 265
    sigma26-085     53 of 238      sigma26-081     23 of 165
    BH2             16 of 290      1511.08771       8 of 401

The other 443 are not correct by construction, only lucky: the shifted rows
happened to carry the same boolean.

WHY IT MATTERS. `rendered` decides the `unrendered` / `U` class, and a demoted
row's distance measures the italic words "(not rendered)" against a scan rather
than two readings disagreeing. judge.py's `unrendered_ids` measured the cost:
four unrelated non-compiling candidates — `\nosuchmacrohere`, `\frac`,
`\begin{array}{c} a & b`, `\frac{1}{ \nosuchmacro{x` — every one came back
distance 10, comp_delta 2, flag `weak`, rendered TRUE. A garbage answer
flattered as a near miss, and the flag pointing at the wrong row makes it worse
in both directions.

THE FIX. `report_tex.demoted_by_ident` reads the same lines and keys them by
the identifier that is already in the cell, and `convert` uses it whenever the
TSV carries identifiers. The positional form stays, because every TSV written
before 614 has no identifier column and those files must keep reading exactly
as they did.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import inkconvert as ic
from pdfdrill import report_tex as rt

#: Three rows in the report; the MIDDLE one is the demoted one, and the one
#: 614 leaves out of the TSV.
_TEX = "\n".join([
    r"\ident{doc\_EQ0001}~ & 1 & $x$ & scan & 0 & 0 \\",
    r"\ident{doc\_EQ0002}~ & 2 & \emph{(not rendered)} & scan & 0 & 0 \\",
    r"\ident{doc\_EQ0003}~ & 3 & $z$ & scan & 0 & 0 \\",
])

_HDR = ("identifier\treport_page\tline\t"
        + "\t".join(ic.FIVE_L) + "\t" + "\t".join(ic.FIVE_R) + "\tA_eq_B")


def _tsv(tmp: Path, idents):
    lines = [_HDR]
    for n, i in enumerate(idents, 1):
        lines.append("\t".join([i, "1", str(n)] + ["1"] * 5 + ["1"] * 5
                               + ["yes"]))
    p = tmp / "report.compare.tsv"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _tex_file(tmp: Path):
    p = tmp / "report.tex"
    p.write_text(_TEX, encoding="utf-8")
    return p


def test_the_positional_list_is_the_defect_this_fixes():
    """Kept as the statement of the bug: position 1 of a TSV missing EQ0002
    is EQ0003, and position 1 of the tex is EQ0002, which did not render."""
    assert rt.demoted_flags(_TEX) == [True, False, True]


def test_a_row_that_compiled_is_not_given_another_rows_demotion(tmp_path):
    rows = {r["id"]: r for r in
            ic.convert(_tsv(tmp_path, ["doc_EQ0001", "doc_EQ0003"]),
                       _tex_file(tmp_path))["rows"]}
    assert rows["doc_EQ0001"]["rendered"] is True
    assert rows["doc_EQ0003"]["rendered"] is True, \
        "EQ0003 compiled; it was given EQ0002's demotion"
    assert rows["doc_EQ0003"]["flag"] != "unrendered"


def test_the_row_that_was_demoted_still_reads_as_demoted(tmp_path):
    """The fix corrects the aim, and must not lose the signal."""
    rows = {r["id"]: r for r in
            ic.convert(_tsv(tmp_path, ["doc_EQ0001", "doc_EQ0002",
                                       "doc_EQ0003"]),
                       _tex_file(tmp_path))["rows"]}
    assert rows["doc_EQ0002"]["rendered"] is False, \
        "the row the report demoted is reported as rendered"
    assert rows["doc_EQ0002"]["flag"] == "unrendered"


def test_a_tsv_with_no_identifier_column_still_pairs_positionally(tmp_path):
    """Every TSV written before 614 carries no identifier, and `convert`
    derives the pairing from report.tex for those. They must read as they
    always did — including, for such a file, the positional demotion."""
    hdr = ("report_page\tline\t" + "\t".join(ic.FIVE_L) + "\t"
           + "\t".join(ic.FIVE_R))
    body = [hdr]
    for n in range(3):
        body.append("\t".join(["1", str(n + 1)] + ["1"] * 5 + ["1"] * 5))
    tsv = tmp_path / "report.compare.tsv"
    tsv.write_text("\n".join(body) + "\n", encoding="utf-8")
    got = ic.convert(tsv, _tex_file(tmp_path))["rows"]
    assert [r["rendered"] for r in got] == [True, False, True]


def test_an_identifier_the_tex_does_not_name_falls_back_rather_than_raising(
        tmp_path):
    """A TSV naming a row the tex does not is a pairing the converter already
    refuses on COUNT; where the count happens to agree, the lookup must not
    raise a KeyError on top of it."""
    rows = ic.convert(_tsv(tmp_path, ["doc_EQ0001", "doc_EQ9999",
                                      "doc_EQ0003"]),
                      _tex_file(tmp_path))["rows"]
    assert len(rows) == 3
    assert {r["id"] for r in rows} == {"doc_EQ0001", "doc_EQ9999",
                                       "doc_EQ0003"}


def test_the_escapes_a_real_report_prints_are_undone():
    r"""The key has to be the identifier the TSV carries, and the cell is not
    spelled that way. This line is copied verbatim out of
    j.nuclphysb.2018.09.006's report.tex: the projector escapes `_` and
    inserts `\allowbreak{}` after every punctuation mark, so the cell reads

        \ident{j.\allowbreak{}nuclphysb.\allowbreak{}…006\_\allowbreak{}EQ0210}

    for the row the TSV calls `j.nuclphysb.2018.09.006_EQ0210`. A key cleaned
    any other way joins nothing, and a lookup that joins nothing falls back to
    the positional answer silently — which is the defect, restored.
    """
    line = (r"\ident{j.\allowbreak{}nuclphysb.\allowbreak{}2018.\allowbreak{}"
            r"09.\allowbreak{}006\_\allowbreak{}EQ0210}~\eqnum{(210)} & 1 & "
            r"$x$ & scan \\")
    assert rt.demoted_by_ident(line) == {
        "j.nuclphysb.2018.09.006_EQ0210": True}


def test_the_two_readings_agree_on_a_real_whole_report():
    r"""And they must agree on COUNT for a report where nothing straddles,
    or the fix would change a measurement nobody asked it to change. Measured
    on the same document: 220 rows by position, 220 by identifier."""
    line = "\n".join(
        r"\ident{doc\_\allowbreak{}EQ%04d}~\eqnum{(%d)} & %d & $x$ & scan \\"
        % (n, n, n) for n in range(1, 21))
    assert len(rt.demoted_flags(line)) == len(rt.demoted_by_ident(line)) == 20
