r"""301 — the figure join is scored against a known answer, not assumed."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import figurejoin as fj                       # noqa: E402

PID = "abab828b-61e2-4095-ac03-1e28612cc14a"


def _doc(tmp_path, author_tex, regions):
    """A texsrc/ holding the author's source and a MathPix tex.zip."""
    (tmp_path / "main.tex").write_text(
        "\\documentclass{article}\n" + author_tex)
    z = tmp_path / PID
    (z / "images").mkdir(parents=True)
    body = []
    for name, cap in regions:
        (z / "images" / (name + ".jpg")).write_bytes(b"\xff\xd8")
        body.append("\\begin{figure}\n\\includegraphics{%s}\n"
                    "\\caption{%s}\n\\end{figure}\n" % (name, cap))
    (z / (PID + ".tex")).write_text(
        "\\graphicspath{{./images/}}\n" + "".join(body))
    return tmp_path


def test_caption_anchors_a_pair(tmp_path):
    d = _doc(tmp_path,
             "\\begin{figure}\\includegraphics{fig/a}"
             "\\caption{Comparison of natural and mathematical language}"
             "\\end{figure}\n",
             [("%s-036_931_1623_350_249" % PID,
               "Figure 8: Comparison of natural and mathematical language")])
    t = fj.ground_truth(d)
    assert len(t["pairs"]) == 1
    assert t["pairs"][0]["region"] == (36, 931, 1623, 350, 249)


def test_two_subfigures_sharing_a_caption_are_not_a_known_pair(tmp_path):
    """A caption names the FLOAT. Two subfigures both anchor to one region,
    which is two claims on one answer — keeping either would let a join be
    scored as right about a pair nobody knows."""
    d = _doc(tmp_path,
             "\\begin{figure}\n\\includegraphics{fig/one}\n"
             "\\includegraphics{fig/two}\n"
             "\\caption{Understanding the decompositions of the matrix}\n"
             "\\end{figure}\n",
             [("%s-053_1359_819_889_380" % PID,
               "Figure 3: Understanding the decompositions of the matrix")])
    t = fj.ground_truth(d)
    assert t["pairs"] == []
    assert len(t["contested"]) == 1
    assert sorted(t["contested"][0]["claimed_by"]) == ["fig/one", "fig/two"]


def test_a_short_caption_anchors_nothing(tmp_path):
    """'Results' recurs; a run that short would pair figures by coincidence."""
    d = _doc(tmp_path,
             "\\begin{figure}\\includegraphics{fig/a}\\caption{Results}"
             "\\end{figure}\n",
             [("%s-001_10_10_10_10" % PID, "Figure 1: Results")])
    t = fj.ground_truth(d)
    assert t["pairs"] == []
    assert len(t["unanchored"]) == 1


def test_document_order_follows_input_not_filename(tmp_path):
    r"""`four.tex` sorts before `one.tex`; a join on that order is wrong from
    its first pair."""
    (tmp_path / "one.tex").write_text("\\includegraphics{first}\n")
    (tmp_path / "four.tex").write_text("\\includegraphics{second}\n")
    (tmp_path / "main.tex").write_text(
        "\\documentclass{book}\n\\input{one}\n\\input{four}\n")
    got = fj.document_order(tmp_path)
    assert [c["file"] for c in got] == ["first", "second"]


def test_score_counts_a_confident_wrong_answer_as_wrong(tmp_path):
    """The ordinal join returns a value for every pair. An answer that is
    always produced and sometimes wrong is indistinguishable from one that is
    right, until it is scored."""
    truth = {"pairs": [{"author_index": 0, "file": "a", "region": (5, 1, 2, 3, 4)},
                       {"author_index": 1, "file": "b", "region": (6, 1, 2, 3, 4)}]}
    inferred = {"map": {0: (5, 1, 2, 3, 4), 1: (9, 9, 9, 9, 9)}}
    s = fj.score(truth, inferred)
    assert s["checkable"] == 2 and s["matched"] == 1 and s["wrong"] == 1
    assert s["not_inferred"] == 0
