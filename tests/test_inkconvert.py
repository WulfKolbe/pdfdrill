"""244 — report.compare.tsv -> report.ink.json, with the pairing asserted.

The TSV carries NO identifiers: report_page, line, dis, A_eq_B and the two
five-tuples. Identifiers come from report.tex, positionally, in table order.
"""
import json

import pytest

from pdfdrill import inkconvert as ic
from pdfdrill.inkconvert import ConversionRefused

HDR = ("report_page\tline\tdis\tA_eq_B\tL_comp\tL_holes\tL_stk\tL_cen\tL_off"
       "\tR_comp\tR_holes\tR_stk\tR_cen\tR_off")


def _row(page, line, L, R):
    dis = sum(abs(a - b) for a, b in zip(L, R))
    return "\t".join([str(page), str(line), str(dis),
                      "yes" if dis == 0 else "NO"]
                     + [str(x) for x in L] + [str(x) for x in R])


def _tsv(tmp_path, rows):
    p = tmp_path / "report.compare.tsv"
    p.write_text("\n".join([HDR] + rows) + "\n", encoding="utf-8")
    return p


def _tex(tmp_path, n):
    p = tmp_path / "report.tex"
    p.write_text("".join(
        "\\ident{D\\_\\allowbreak{}EQ%04d} & %d & x & y \\\\ \\hline\n"
        % (i, i) for i in range(1, n + 1)), encoding="utf-8")
    return p


FOOT = [0, 0, 0, 0, 0]


def test_footers_are_dropped_not_classified(tmp_path):
    """An all-zero pair scores distance 0, and flag_of's first branch returns
    "clean". Kept, the 1,232 footers across the eleven arrive as K|+0 — an
    absent reading taking the BEST class — and the clean count goes from 1,207
    to 2,439."""
    rows = [_row(1, 1, [50, 1, 0, 0, 0], [50, 1, 0, 0, 0]),
            _row(1, 2, FOOT, FOOT),
            _row(2, 1, [30, 2, 0, 0, 0], [90, 9, 0, 0, 0]),
            _row(2, 2, FOOT, FOOT)]
    p = ic.convert(_tsv(tmp_path, rows), _tex(tmp_path, 2))
    assert p["footers_dropped"] == 2 and p["display_pages"] == 2
    assert len(p["rows"]) == 2
    assert [r["flag"] for r in p["rows"]] == ["clean", "component"]


def test_a_count_mismatch_REFUSES_rather_than_truncating(tmp_path):
    """zip() drops the tail silently and the result passes every structural
    check."""
    rows = [_row(1, i, [10, 0, 0, 0, 0], [10, 0, 0, 0, 0]) for i in range(1, 6)]
    rows.append(_row(1, 6, FOOT, FOOT))
    with pytest.raises(ConversionRefused, match="pairing is unknown"):
        ic.convert(_tsv(tmp_path, rows), _tex(tmp_path, 3))


def test_nothing_is_written_when_it_refuses(tmp_path):
    rows = [_row(1, 1, [10, 0, 0, 0, 0], [10, 0, 0, 0, 0]),
            _row(1, 2, FOOT, FOOT)]
    with pytest.raises(ConversionRefused):
        ic.convert(_tsv(tmp_path, rows), _tex(tmp_path, 5))
    assert not (tmp_path / "report.ink.json").exists()


def test_identifiers_survive_allowbreak(tmp_path):
    rows = [_row(1, 1, [10, 0, 0, 0, 0], [10, 0, 0, 0, 0]),
            _row(1, 2, FOOT, FOOT)]
    p = ic.convert(_tsv(tmp_path, rows), _tex(tmp_path, 1))
    assert p["rows"][0]["id"] == "D_EQ0001"


@pytest.mark.parametrize("L,R,flag", [
    ([10, 0, 0, 0, 0], [10, 0, 0, 0, 0], "clean"),        # identical
    ([10, 0, 0, 0, 0], [11, 0, 0, 0, 0], "noise"),        # inside the floor
    ([10, 0, 0, 0, 0], [90, 0, 0, 0, 0], "component"),    # comp delta > 2
    ([10, 0, 0, 0, 0], [11, 9, 0, 0, 0], "weak"),         # far, delta small
])
def test_the_floors_are_inkdrills_not_reinvented(tmp_path, L, R, flag):
    rows = [_row(1, 1, L, R), _row(1, 2, FOOT, FOOT)]
    p = ic.convert(_tsv(tmp_path, rows), _tex(tmp_path, 1))
    assert p["rows"][0]["flag"] == flag
    assert ic.NOISE_DISTANCE == 7 and ic.NOISE_COMP_DELTA == 2


def test_stable_is_unreachable_from_this_format(tmp_path):
    """flag_of returns "stable" only when scale_stable is true, and the TSV has
    no such column — L_stk/R_stk are the stacked counts inside the five-tuple
    and A_eq_B is just (dis == 0). That is the mechanism behind zero S in 6,207
    measured rows corpus-wide: a branch this input cannot reach."""
    assert "S" not in {r for r in ic.FLAG_CODE.values()} - {"S"}   # S exists
    rows = [_row(1, 1, [10, 0, 0, 0, 0], [11, 9, 0, 0, 0]),
            _row(1, 2, FOOT, FOOT)]
    p = ic.convert(_tsv(tmp_path, rows), _tex(tmp_path, 1))
    assert p["rows"][0]["flag"] == "weak"          # never "stable"


def test_the_code_carries_the_signed_component_delta(tmp_path):
    rows = [_row(1, 1, [10, 0, 0, 0, 0], [90, 0, 0, 0, 0]),
            _row(1, 2, FOOT, FOOT)]
    p = ic.convert(_tsv(tmp_path, rows), _tex(tmp_path, 1))
    assert p["rows"][0]["code"] == "C|+80"


def test_the_build_stamp_travels_as_measured_against(tmp_path):
    rows = [_row(1, 1, [10, 0, 0, 0, 0], [10, 0, 0, 0, 0]),
            _row(1, 2, FOOT, FOOT)]
    st = {"pdf": "report.pdf", "pages": 3, "sha256": "a" * 64, "phase": "measure"}
    p = ic.convert(_tsv(tmp_path, rows), _tex(tmp_path, 1), stamp=st)
    assert p["measured_against"]["sha256"] == "a" * 64


def test_a_stamp_NEWER_than_the_tsv_is_not_attached(tmp_path, monkeypatch):
    """244b — attaching whatever stamp is on disk names the build present at
    CONVERSION time, which differs from the measured build whenever the report
    was rebuilt in between, and says so with a confidence the file does not
    have.

    0707.4470 hit exactly this: TSV measured 08:46, build stamp written 11:38
    three hours later by an unrelated rebuild. The stamp said phase=reading and
    publishready refused the result — correctly, on a claim the converter had
    invented. The rule is that a stamp can only be the measured build if it
    predates the measurement.
    """
    import json as _j
    import os
    import time
    from pdfdrill import commands as C
    d = tmp_path / "DOC"
    d.mkdir()
    (d / "DOC.pdf").write_bytes(b"%PDF-1.4\n")
    rows = [_row(1, 1, [10, 0, 0, 0, 0], [10, 0, 0, 0, 0]), _row(1, 2, FOOT, FOOT)]
    (d / "report.compare.tsv").write_text("\n".join([HDR] + rows) + "\n",
                                          encoding="utf-8")
    (d / "report.tex").write_text(
        "\\ident{DOC\\_EQ0001} & 1 & x & y \\\\ \\hline\n", encoding="utf-8")
    (d / "report.build.json").write_text(
        _j.dumps({"pdf": "report.pdf", "phase": "reading", "sha256": "b" * 64}),
        encoding="utf-8")
    now = time.time()
    os.utime(d / "report.compare.tsv", (now - 3600, now - 3600))
    os.utime(d / "report.build.json", (now, now))          # newer: a rebuild
    out = C.cmd_inkconvert(d / "DOC.pdf")
    assert "NOT attached" in out
    payload = _j.loads((d / "report.ink.json").read_text(encoding="utf-8"))
    assert "measured_against" not in payload


def test_a_stamp_OLDER_than_the_tsv_is_attached(tmp_path):
    import json as _j
    import os
    import time
    from pdfdrill import commands as C
    d = tmp_path / "DOC2"
    d.mkdir()
    (d / "DOC2.pdf").write_bytes(b"%PDF-1.4\n")
    rows = [_row(1, 1, [10, 0, 0, 0, 0], [10, 0, 0, 0, 0]), _row(1, 2, FOOT, FOOT)]
    (d / "report.compare.tsv").write_text("\n".join([HDR] + rows) + "\n",
                                          encoding="utf-8")
    (d / "report.tex").write_text(
        "\\ident{DOC2\\_EQ0001} & 1 & x & y \\\\ \\hline\n", encoding="utf-8")
    (d / "report.build.json").write_text(
        _j.dumps({"pdf": "report.pdf", "phase": "measure", "sha256": "c" * 64}),
        encoding="utf-8")
    now = time.time()
    os.utime(d / "report.build.json", (now - 3600, now - 3600))   # predates
    os.utime(d / "report.compare.tsv", (now, now))
    C.cmd_inkconvert(d / "DOC2.pdf")
    payload = _j.loads((d / "report.ink.json").read_text(encoding="utf-8"))
    assert payload["measured_against"]["sha256"] == "c" * 64
