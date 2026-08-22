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
    assert entry.get("requires") == ["model", "geometry", "injectlatex",
                                     "cdncrops", "tiddlers"], \
        "reporttex must declare EVERYTHING it reads, not what it calls"


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
    # identifiers carry break opportunities after . and _ (P16 mechanism 3)
    assert "k\\_\\allowbreak{}EQ0001" in tex and "(1)" in tex
    # formula first-occurrence page came from the transcluding paragraph
    assert "k\\_\\allowbreak{}FO0001} & 002" in tex
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


def test_renderable_rejects_bare_align_markers_outside_environments():
    """Live hang (0902.0431 EQ0035, 2026-08-18): a bare & or \\\\ outside any
    environment is a longtable tab mark — TeX loops in error recovery."""
    assert renderable(r"a & b = c") == ""
    assert renderable(r"a \\ b") == ""
    assert renderable(
        r"\begin{aligned} a &= b \\ c &= d \end{aligned}") != ""
    assert renderable(r"a \& b") != ""       # escaped & is fine


def test_renderable_rejects_plain_tex_cr_family_macros():
    """Second live hang on 0902.0431: \\displaylines carries \\cr internally
    — invisible to the bare-& check, still a tab-mark recovery loop."""
    assert renderable(r"\displaylines{\hfill a=b \hfill}") == ""
    assert renderable(r"\eqalign{a&=b}") == ""
    assert renderable(r"a \cr b") == ""
    assert renderable(r"\crossproduct") != "" if True else None


def test_braces_shield_align_markers_from_the_longtable_scanner():
    r"""User 2026-08-19 (0711.0273): \substack{a \\ b} is a macro ARGUMENT,
    not an environment — braces shield the \\ from the alignment scanner, so
    it compiles inside a cell (verified with a probe longtable, 0 errors).
    The brace-blind guard demoted every 'multi-line text under an integral'
    equation to (not rendered): 3 of that document's 14 equations."""
    from pdfdrill.report_tex import has_bare_align_marker
    real = (r"Z\left(G_{N}, \Lambda\right)=\int_{\substack{\text { spacetime }"
            r" \\ \text { geometries } g \in \mathcal{G}}} \mathcal{D} g "
            r"\mathrm{e}^{i S^{\mathrm{EH}}[g]},")
    assert renderable(real)                       # renders again
    assert not has_bare_align_marker(r"\substack{a \\ b}")
    assert not has_bare_align_marker(r"\text{x} \& y")     # escaped &
    assert has_bare_align_marker(r"a & b")                 # depth 0: real
    assert has_bare_align_marker(r"a \\ b")
    assert has_bare_align_marker(r"\frac{p}{q} \\[2pt] r")


def test_source_column_never_breaks_after_a_backslash():
    r"""The break opportunity goes BEFORE the backslash. After it, a wrapped
    line ended with a naked `\` and the next started `mathrm{e}...`; copied
    out of the PDF that compiles to the literal letters "mathrme" — the
    defect the user pasted (0711.0273)."""
    from pdfdrill.report_tex import esc_text
    out = esc_text(r"\mathcal{D} g \mathrm{e}")
    assert r"\textbackslash{}\allowbreak{}" not in out     # never after
    assert r"\allowbreak{}\textbackslash{}" in out         # always before


def test_source_column_has_no_leading_penalty():
    r"""\allowbreak is \penalty0; at the START of a p{} cell TeX breaks there
    and the cell gets an EMPTY first line. Measured cost when it slipped in:
    WDorg4 83 pages vs 60 (+38%), corpus 941 -> 1,080 (inkdrill, 2026-08-20)."""
    from pdfdrill.report_tex import esc_text
    out = esc_text(r"\begin{aligned} a &= b \end{aligned}")
    assert not out.startswith(r"\allowbreak{}")
    assert out.startswith(r"\textbackslash{}")
    # interior breaks are still there, still before the backslash
    assert r"\allowbreak{}\textbackslash{}" in out
    assert r"\textbackslash{}\allowbreak{}" not in out


def test_error_counter_ignores_content_lines_that_start_with_bang():
    r"""A TeX error line is '! <message>'; a line starting '!}' is CONTENT
    echoed inside an Underfull-hbox report. Counting bare '^!' reported a
    phantom error on 1407.7814 after the trailing_punct migration — a false
    FAILURE, the mirror of handover rule 11's masked success."""
    import re
    log = ("Underfull \\hbox (badness 10000) in paragraph at lines 48--48\n"
           "!} \n"
           " []\n"
           "! Undefined control sequence.\n")
    assert len(re.findall(r"^!", log, re.M)) == 2      # the old, wrong count
    assert len(re.findall(r"^! ", log, re.M)) == 1     # the real error only


def test_report_preamble_carries_the_same_packages_as_the_standalone_renderer():
    r"""48 demoted rows were \mathscr and \llbracket: the report preamble had
    amsmath/amssymb but not mathrsfs/stmaryrd, which the standalone renderer
    has carried since task 022. The equations rendered perfectly alone and
    threw 'Undefined control sequence' inside the report, so every isolated
    reproduction succeeded and the cause hid for three hypotheses.
    0707.4470: 31 rows demoted before, 0 after."""
    from pdfdrill.report_tex import PREAMBLE
    import inspect
    from pdfdrill import commands
    standalone_src = inspect.getsource(commands.cmd_standalone)
    for pkg in ("mathrsfs", "stmaryrd", "amsmath", "amssymb"):
        assert pkg in PREAMBLE, f"report preamble is missing {pkg}"
        assert pkg in standalone_src, f"standalone renderer is missing {pkg}"


def test_confidence_flag_only_below_the_threshold():
    """064: the flag fires strictly below CONF_THRESHOLD, and never on an
    absent or unparseable value — a missing reading must not read as a
    confident one."""
    from pdfdrill.report_tex import CONF_THRESHOLD, conf_flag
    assert conf_flag("0.0405") == "\\lowconf{0.041}"
    assert conf_flag(CONF_THRESHOLD - 0.001).startswith("\\lowconf")
    assert conf_flag(CONF_THRESHOLD) == ""        # strict <, boundary excluded
    assert conf_flag("0.9") == ""
    for absent in ("", None, "abc", object()):
        assert conf_flag(absent) == "", absent


def test_confidence_flag_lands_in_the_identifier_column_only():
    """The mark goes in the ident column. Source/Rendered/Scan must stay
    byte-identical or the consumer's per-column ink probe moves for a reason
    that has nothing to do with the mathematics (HANDOVER rule 16)."""
    from pdfdrill.report_tex import row
    lo = row("K_EQ1", "a+b", "12", conf="0.02")
    hi = row("K_EQ1", "a+b", "12", conf="0.99")
    assert "\\lowconf{0.020}" in lo and "\\lowconf" not in hi
    # 099 gave confidence its own column, so the Conf. cell now legitimately
    # differs between the two. What must still be untouched is what the
    # consumer measures: Source, Rendered and Scan — everything from index 3.
    assert lo.split("&")[3:] == hi.split("&")[3:]


def test_rows_for_equation_tuple_arity_matches_every_unpack_site():
    """The eq tuple grew from 6 to 7 fields. Last time it grew, reporttex
    broke on all four books while the tests still passed, because nothing
    exercised the unpack. This asserts the arity the builder actually emits
    and that build_report consumes it."""
    import inspect

    from pdfdrill import report_tex
    tids = [{"title": "K_EQ1", "latex": "a+b", "page": "3",
             "equation_number": "(1)", "width": "100",
             "trailing_punct": ".", "confidence": "0.02"}]
    _fo, eq, _tab, _dia = report_tex.rows_for(tids, "K")
    assert len(eq) == 1 and len(eq[0]) == 7, eq
    assert eq[0][6] == "0.02"
    src = inspect.getsource(report_tex.build_report)
    for line in src.splitlines():
        if line.strip().endswith("in eq:"):
            names = line.split("for", 1)[1].split(" in ")[0]
            assert len([n for n in names.split(",") if n.strip()]) == 7, line


def test_confidence_cell_bands():
    """099: green >= 0.9, amber 0.5-0.9, red < 0.5, and an absent value is a
    dash — never a colour. A blank green square would assert a reading that
    was never taken."""
    from pdfdrill.report_tex import conf_cell
    assert "confgreen" in conf_cell("0.95") and "0.950" in conf_cell("0.95")
    assert "confamber" in conf_cell(0.661)
    assert "confred" in conf_cell(0.448)
    assert "confgreen" in conf_cell(0.9)      # boundary belongs to green
    assert "confamber" in conf_cell(0.5)      # boundary belongs to amber
    for absent in ("", None, "abc"):
        assert conf_cell(absent) == "---", absent


def test_row_has_the_confidence_column_and_scan_stays_last():
    """The Conf. column goes third. The consumer reads the LAST TWO columns,
    so Rendered and Scan must remain the final pair."""
    from pdfdrill.report_tex import row
    cells = row("K_EQ1", "a+b", "12", image="IMG", conf="0.42").split("&")
    assert len(cells) == 6
    assert "confred" in cells[2]
    assert "FitMath" in cells[4] and "IMG" in cells[5]


def test_col_widths_still_sum_to_the_span():
    """Adding a column must not overflow the page: the widths plus the
    tabcolsep reserve have to fit what geometry gives us."""
    from pdfdrill.report_tex import col_widths
    for usable in (261, 174):
        for img in (True, False):
            w = col_widths(usable, img)
            assert len(w) == (6 if img else 5)
            assert sum(w) <= usable, (usable, img, w, sum(w))
            assert all(x > 0 for x in w)
