"""621 — a table whose column rules do not increase says so.

The right-edge mark rides an \\hfill to the end of the last cell. When that
cell's content already fills the line the \\hfill breaks instead of
stretching, and the mark lands at the start of the NEXT line. Measured on
2501.06662: [53.6, 122.7, 154.9, 204.1, 477.2, 767.4, 66.0] — the rightmost
rule reported at 66 bp, to the left of the first. A consumer reading those in
order gets every cell of that table wrong.
"""
import json

from pdfdrill import report_tex as rt


def _manifest(tmp_path, xs):
    rt.cellrect_reset(True)
    rt._CELLRECT["cols"] = {1: ["col%05d" % (i + 1) for i in range(len(xs))]}
    rt._CELLRECT["map"] = []
    aux = tmp_path / "report.aux"
    aux.write_text("".join(
        "\\zref@newlabel{col%05d}{\\posx{%d}\\posy{0}\\abspage{1}}\n"
        % (i + 1, int(x * rt.SP_PER_BP)) for i, x in enumerate(xs)))
    return rt.cellrect_from_aux(aux, 841.89)


def test_increasing_rules_are_not_flagged(tmp_path):
    m = _manifest(tmp_path, [50.0, 120.0, 200.0, 400.0])
    t = m["tables"][0]
    assert "ordered" not in t, t
    assert t["column_rules_bp"] == sorted(t["column_rules_bp"])


def test_a_rule_out_of_order_is_recorded_not_shipped_as_geometry(tmp_path):
    m = _manifest(tmp_path, [53.6, 122.7, 154.9, 204.1, 477.2, 767.4, 66.0])
    t = m["tables"][0]
    assert t.get("ordered") is False
    assert "not increasing" in t["why"]
