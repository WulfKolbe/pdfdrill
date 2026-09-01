"""462 — a bibkey rename must retarget the two files a measurement joins on."""
import json, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import renamefolder as rf

OLD = "Introduction to Graph and Hypergraph Theory (Vitaly I. Voloshin) (Z-Library)"
NEW = "voloshin-hypergraph"
OLD_S = "Introduction_to_Graph_and_Hypergraph_Theory__Vitaly_I._Voloshin___Z-Library_"


def test_ink_row_ids_follow_the_bibkey():
    d = {"rows": [{"id": OLD_S + "_EQ0124", "code": "N|+0"},
                  {"id": OLD_S + "_TAB_001", "code": "C|+9"}],
         "measured_against": {"sha256": "abc"}}
    assert rf._retarget_ink(d, OLD, NEW) is True
    assert [r["id"] for r in d["rows"]] == [NEW + "_EQ0124", NEW + "_TAB_001"]
    # the build stamp is not a bibkey and is left alone
    assert d["measured_against"] == {"sha256": "abc"}


def test_ink_is_untouched_when_the_bibkey_does_not_move():
    d = {"rows": [{"id": OLD_S + "_EQ0001"}]}
    assert rf._retarget_ink(d, OLD, OLD) is False
    assert d["rows"][0]["id"] == OLD_S + "_EQ0001"


def test_ink_leaves_a_row_that_is_not_ours_alone():
    d = {"rows": [{"id": "someone_else_EQ0001"}]}
    assert rf._retarget_ink(d, OLD, NEW) is False
    assert d["rows"][0]["id"] == "someone_else_EQ0001"


def test_tables_manifest_carries_both_spellings_and_both_move():
    d = {"bibkey": OLD,
         "tables": [{"caption": "Display equations",
                     "identifiers": [OLD_S + "_EQ0001", OLD_S + "_EQ0002"]}]}
    assert rf._retarget_tables(d, OLD, NEW) is True
    assert d["bibkey"] == NEW                       # raw
    assert d["tables"][0]["identifiers"] == [NEW + "_EQ0001", NEW + "_EQ0002"]


def test_a_real_rename_retargets_both(tmp_path):
    src = tmp_path / OLD
    src.mkdir()
    (src / f"{OLD}.drill.json").write_text(json.dumps(
        {"evidence": {"bibkey": OLD}}))
    (src / "report.ink.json").write_text(json.dumps(
        {"rows": [{"id": OLD_S + "_EQ0001"}]}))
    (src / "report.tables.json").write_text(json.dumps(
        {"bibkey": OLD, "tables": [{"caption": "Display equations",
                                    "identifiers": [OLD_S + "_EQ0001"]}]}))
    r = rf.rename_folder(src, OLD, NEW)
    assert r["ink_retargeted"] and r["tables_retargeted"]
    dst = r["folder"]
    ink = json.loads((dst / "report.ink.json").read_text())
    tab = json.loads((dst / "report.tables.json").read_text())
    assert ink["rows"][0]["id"] == NEW + "_EQ0001"
    assert tab["identifiers"] if False else tab["bibkey"] == NEW
    assert tab["tables"][0]["identifiers"] == [NEW + "_EQ0001"]


def test_the_ink_and_the_report_still_join_after_a_rename(tmp_path):
    """The point of the whole thing: 394's shape, checked as a join."""
    src = tmp_path / OLD
    src.mkdir()
    (src / f"{OLD}.drill.json").write_text(json.dumps(
        {"evidence": {"bibkey": OLD}}))
    (src / "report.ink.json").write_text(json.dumps(
        {"rows": [{"id": OLD_S + "_EQ0001"}, {"id": OLD_S + "_EQ0002"}]}))
    (src / "report.tables.json").write_text(json.dumps(
        {"bibkey": OLD,
         "tables": [{"caption": "Display equations",
                     "identifiers": [OLD_S + "_EQ0001", OLD_S + "_EQ0002"]}]}))
    dst = rf.rename_folder(src, OLD, NEW)["folder"]
    ink = {r["id"] for r in json.loads(
        (dst / "report.ink.json").read_text())["rows"]}
    ids = set(json.loads((dst / "report.tables.json").read_text())
              ["tables"][0]["identifiers"])
    assert ink & ids == ink, "0 matched is what an un-retargeted rename gives"
