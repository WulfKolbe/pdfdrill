r"""298 — extracting \includegraphics from the author's own sources."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import texgraphics as tg                      # noqa: E402


def test_options_are_brace_aware():
    r"""`trim={1 2 3 4}` holds a comma-free group, but `viewport={0,0,1,1}`
    does not — splitting on every comma invents four options from one."""
    c = tg.calls(r"\includegraphics[trim={1 2 3 4},clip,width=.5\linewidth]{a}")[0]
    assert c["options"] == {"trim": "1 2 3 4", "clip": True,
                            "width": r".5\linewidth"}
    assert c["has_trim_or_clip"]
    d = tg.calls(r"\includegraphics[viewport={0,0,10,10},clip]{a}")[0]
    assert d["options"]["viewport"] == "0,0,10,10"


def test_star_form_and_no_options():
    assert tg.calls(r"\includegraphics*[scale=2]{b.pdf}")[0]["file"] == "b.pdf"
    assert tg.calls(r"\includegraphics{c}")[0]["file"] == "c"


def test_comments_are_not_calls():
    r"""A commented-out figure is not in the document."""
    assert tg.calls("%% \\includegraphics{ghost}") == []
    assert len(tg.calls(r"\includegraphics{real} % \includegraphics{ghost}")) == 1
    # an ESCAPED percent is a literal, not a comment
    assert len(tg.calls(r"100\% \includegraphics{real}")) == 1


def test_environment_is_reported():
    src = (r"\begin{figure}" "\n" r"\includegraphics{a}" "\n" r"\end{figure}"
           "\n" r"\includegraphics{b}")
    a, b = tg.calls(src)
    assert a["in_figure"] and not a["in_tikzpicture"]
    assert not b["in_figure"] and not b["in_tikzpicture"]


def test_overlay_node_discriminates():
    """Every tikz inclusion is not automatically an overlay — the corpus makes
    the two counts equal, which is a property of those sources, not of this."""
    node = tg.calls(r"\begin{tikzpicture}" "\n"
                    r"\node at (0,0) {\includegraphics{a}};" "\n"
                    r"\end{tikzpicture}")[0]
    bare = tg.calls(r"\begin{tikzpicture}" "\n" r"\includegraphics{a}" "\n"
                    r"\end{tikzpicture}")[0]
    assert node["in_tikzpicture"] and node["overlay_node"]
    assert bare["in_tikzpicture"] and not bare["overlay_node"]


def test_graphicspath_is_document_wide(tmp_path):
    r"""\graphicspath is written once in the preamble; the chapters that use it
    never repeat it. Reading it per-file left 34 of 34 inclusions unresolved in
    a document whose figures were exactly where the preamble said."""
    (tmp_path / "figs").mkdir()
    (tmp_path / "figs" / "one.pdf").write_bytes(b"%PDF")
    (tmp_path / "main.tex").write_text(
        "\\graphicspath{{figs/}}\n\\input{chap}\n")
    (tmp_path / "chap.tex").write_text("\\includegraphics{one}\n")
    got = tg.scan(tmp_path)
    resolved = [c for c in got["calls"] if c["resolved"]]
    assert len(resolved) == 1
    assert resolved[0]["resolved"] == "figs/one.pdf"


def test_quoted_path_segments_resolve(tmp_path):
    r"""graphicx quotes a path with spaces: {"plots/a b/"fig.pdf}."""
    d = tmp_path / "plots" / "a b"
    d.mkdir(parents=True)
    (d / "fig.pdf").write_bytes(b"%PDF")
    (tmp_path / "m.tex").write_text('\\includegraphics{"plots/a b/"fig.pdf}\n')
    got = tg.scan(tmp_path)
    assert got["calls"][0]["resolved"] == "plots/a b/fig.pdf"


def test_mathpix_texzip_is_not_author_source(tmp_path):
    """A tex.zip unpacked inside texsrc/ doubles the author's figure count and
    reports MathPix's crops as figures the author chose."""
    pid = "abab828b-61e2-4095-ac03-1e28612cc14a"
    z = tmp_path / pid
    (z / "images").mkdir(parents=True)
    name = "%s-005_139_124_2358_1426" % pid
    (z / "images" / (name + ".jpg")).write_bytes(b"\xff\xd8")
    (z / (pid + ".tex")).write_text(
        "\\graphicspath{{./images/}}\n\\includegraphics{%s}\n" % name)
    (tmp_path / "paper.tex").write_text("\\includegraphics{mine}\n")
    got = tg.scan(tmp_path)
    summ = tg.summarise(got)
    assert summ["calls"] == 1, "the author wrote one inclusion"
    assert summ["texzip_calls"] == 1
    zc = [c for c in got["calls"] if c["mathpix_texzip"]][0]
    assert zc["region"] == (5, 139, 124, 2358, 1426)
    assert zc["resolved"].endswith(".jpg")


def test_region_tuple_only_matches_a_crop_name():
    assert tg.region_tuple("figs/primal-dual") is None
    assert tg.region_tuple("abab828b-61e2-4095-ac03-1e28612cc14a"
                           "-005_139_124_2358_1426") == (5, 139, 124, 2358, 1426)
