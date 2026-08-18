"""reporttex — the LaTeX formula report as a COMMAND, not a tool.

Audit A2: the generator lived in tools/, invisible to the planner, status,
and --ensure. It is now src/pdfdrill/report_tex.py behind `pdfdrill
reporttex` with a manifest entry (requires: tiddlers).
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.report_tex import (build_report, renderable, texzip_images,
                                 col_widths)


def test_reporttex_is_a_registered_command_with_manifest_entry():
    from pdfdrill.cli import HANDLERS
    assert "reporttex" in HANDLERS
    import yaml
    man = yaml.safe_load(
        (Path(__file__).resolve().parent.parent /
         ".claude/skills/pdfdrill/commands.yaml").read_text())
    cmds = man["commands"] if isinstance(man, dict) else man
    entry = next(c for c in cmds if c["name"] == "reporttex")
    assert entry.get("requires") == ["tiddlers"], \
        "reporttex must declare its dependency for the planner"


def test_renderable_rejects_the_snippet_that_hung_xelatex():
    # bh2_EQ0147: stray \end{itemize} + \[ \] — this one snippet cost a
    # 10-minute hang inside a longtable cell before validation existed.
    bad = r"\[ \left(s\right)_{1}^{4} . \] \end{itemize}"
    assert renderable(bad) == ""
    assert renderable(r"x_{5}") == "x_{5}"
    # \widehat{\}} is BALANCED (escaped brace), not a defect
    assert renderable(r"\widehat{\}}") == r"\widehat{\}}"


def test_texzip_image_names_parse_page_and_dims(tmp_path):
    (tmp_path / "images").mkdir()
    img = tmp_path / "images" / "uuid-400_1019_1078_5_106.jpg"
    img.write_bytes(b"x")
    by_key, by_page = texzip_images(tmp_path)
    assert by_key[(400, 1019, 1078)] == img
    assert by_page[400] == img


def test_col_widths_sum_within_usable_span():
    for usable in (174, 384):
        for with_image in (False, True):
            w = col_widths(usable, with_image)
            assert sum(w) <= usable - 10  # rules/padding reserve


def test_build_report_writes_all_sections(tmp_path):
    tiddlers = [
        {"title": "k_EQ0001", "latex": "a=b", "page": "003",
         "equation_number": "(1)", "width": "100"},
        {"title": "k_FO0001", "latex": "x_{5}"},
        {"title": "k_PARA_0001", "page": "002",
         "text": "see {{k_FO0001||FO}}"},
        {"title": "k_TAB_001", "page": "007", "width": "50", "height": "40"},
        {"title": "k_DIA_0001", "page": "009", "width": "80", "height": "60"},
    ]
    tp = tmp_path / "k.tiddlers.json"
    tp.write_text(json.dumps(tiddlers))
    r = build_report(tp, paper="a3", landscape=True)
    tex = (tmp_path / "report.tex").read_text()
    assert r == {"equations": 1, "formulas": 1, "tables": 1,
                 "unrecovered": 1, "out": tmp_path / "report.tex"}
    assert "a3paper,landscape" in tex
    assert "k\\_EQ0001" in tex and "(1)" in tex
    # formula first-occurrence page came from the transcluding paragraph
    assert "k\\_FO0001} & 002" in tex
    assert "Unrecovered image regions" in tex
    assert "pdfdrill vision" in tex and "inkdrill" in tex


def test_reporttex_autochain_sees_the_tiddlers_it_just_built(monkeypatch):
    """Live bug (BH3FR, 2026-08-18): cmd_tiddlers wrote the tiddler file and
    saved its OWN sidecar; cmd_reporttex re-read its stale in-memory Sidecar,
    found no tiddlers_path, and declared failure after a successful chain."""
    import pdfdrill.commands as C

    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")

        def fake_tiddlers(p, *a, **k):
            (p.parent / "doc.tiddlers.json").write_text(json.dumps(
                [{"title": "doc_EQ0001", "latex": "a=b", "page": "001",
                  "equation_number": "", "width": "10"}]))
            return "Wrote 1 TiddlyWiki tiddlers"

        monkeypatch.setattr(C, "cmd_tiddlers", fake_tiddlers)
        out = C.cmd_reporttex(pdf, images=False)
        assert "did not produce one" not in out
        assert "Wrote" in out and (Path(d) / "report.tex").is_file()
