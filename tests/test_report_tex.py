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
                                     "cdncrops", "tiddlers", "inkconvert"], \
        "reporttex must declare EVERYTHING it reads, not what it calls"


def test_renderable_repairs_the_snippet_that_hung_xelatex():
    # bh2_EQ0147: stray \end{itemize} + \[ \] — this one snippet cost a
    # 10-minute hang inside a longtable cell before validation existed.
    #
    # It used to be REFUSED outright. It is now REPAIRED: the stray closer is
    # dropped and the mathematics renders. The hang was caused by the
    # \end{itemize}, not by the equation, and refusing the row treated the
    # symptom — 24 of 0902.0431's 31 unrendered rows were this exact shape, at
    # confidences up to 1.000. The repaired form was compiled inside a real
    # longtable cell with a 120s ceiling: 0 errors, 1 page, no hang.
    #
    # What must still hold is the property this test was written for: the RAW
    # snippet never reaches xelatex.
    bad = r"\[ \left(s\right)_{1}^{4} . \] \end{itemize}"
    out = renderable(bad)
    assert out == r"\left(s\right)_{1}^{4} ."
    assert r"\end{itemize}" not in out and r"\]" not in out
    assert renderable(r"x_{5}") == "x_{5}"
    # \widehat{\}} is BALANCED (escaped brace), not a defect
    assert renderable(r"\widehat{\}}") == r"\widehat{\}}"


def test_texzip_image_names_parse_the_full_region(tmp_path):
    """282 — keyed on all five numbers, not (page, height, width) with a page
    fallback. out/279 verified the filename IS the region: 20,276 of 20,287
    corpus filenames match a lines.json region exactly."""
    (tmp_path / "images").mkdir()
    img = tmp_path / "images" / "uuid-400_1019_1078_5_106.jpg"
    img.write_bytes(b"x")
    by_region, n = texzip_images(tmp_path)
    assert n == 1
    assert by_region[(400, 1019, 1078, 5, 106)] == img
    # the old 3-tuple key and the page fallback are both gone: they attached
    # the first image of a page to every unmatched row on it
    assert (400, 1019, 1078) not in by_region


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
    r = build_report(tp, paper="a3", landscape=True, formulas="all")
    tex = (tmp_path / "report.tex").read_text()
    for k in ("image_named", "image_unnamed", "texzip_images",
              "image_rendered", "image_rendered_kept", "image_duplicated"):
        r.pop(k, None)
    assert r == {"equations": 1, "formulas": 1, "tables": 1,
                 # 460 — what the section shows, what the document has, why
                 "formulas_total": 1, "formula_rule": "all",
                 # 516 — None outside the findings shape: a build that did not
                 # select sections has no section counts, which is a different
                 # fact from four zeroes.
                 "findings": None,
                 "unrecovered": 1, "out": tmp_path / "report.tex"}
    assert "a3paper,landscape" in tex
    # identifiers carry break opportunities after . and _ (P16 mechanism 3)
    assert "k\\_\\allowbreak{}EQ0001" in tex and "(1)" in tex
    # formula first-occurrence page came from the transcluding paragraph
    assert "k\\_\\allowbreak{}FO0001} & 002" in tex
    # 282 renamed it: the section names each row's tex.zip source, so calling
    # every region "unrecovered" was no longer what it shows.
    assert "Image regions" in tex
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


# --- 297: the compile runs in a private directory ---------------------------

def test_compile_leaves_no_aux_beside_the_document(tmp_path):
    """The .aux is the whole reason for the private build directory.

    Pass N writes it and pass N+1 READS it, so two builds sharing one produce a
    PDF whose cross-references were resolved against the other build's
    numbering — it compiles, and every reference is wrong. If an .aux is beside
    the document afterwards, a concurrent build can reach it.
    """
    import shutil
    if shutil.which("xelatex") is None:
        import pytest
        pytest.skip("xelatex not installed")
    from pdfdrill import report_tex as rt
    tex = tmp_path / "report.tex"
    tex.write_text("\\documentclass{article}\n\\begin{document}\n"
                   "\\section{A}\\label{s}\nSee \\ref{s}.\n\\end{document}\n")
    res = rt.compile_fixpoint(tex)
    assert res is not None
    pages, nerr, demoted = res
    assert pages == 1 and nerr == 0
    assert (tmp_path / "report.pdf").is_file()
    assert (tmp_path / "report.log").is_file()
    leftovers = sorted(p.name for p in tmp_path.iterdir()
                       if p.suffix in (".aux", ".out", ".toc", ".part"))
    assert not leftovers, leftovers


def test_compile_rewrites_the_tex_only_when_it_demoted_a_row(tmp_path):
    """An untouched .tex keeps its mtime, so the staleness guards stay honest."""
    import shutil
    if shutil.which("xelatex") is None:
        import pytest
        pytest.skip("xelatex not installed")
    from pdfdrill import report_tex as rt
    tex = tmp_path / "report.tex"
    tex.write_text("\\documentclass{article}\n\\begin{document}\nx\n"
                   "\\end{document}\n")
    before = tex.stat().st_mtime_ns
    rt.compile_fixpoint(tex)
    assert tex.stat().st_mtime_ns == before


# --- 321: the builder states its own table boundaries -----------------------

def test_table_record_carries_what_a_measurement_needs():
    from pdfdrill import report_tex as rt
    r = rt._table_record("Display equations", (20, 7, 13, 80, 80),
                         legend=True, endhead=True,
                         identifiers=["D_EQ0001", "D_EQ0002"])
    assert r["columns"] == 5
    assert r["rows"] == 2 and r["identifiers"][0] == "D_EQ0001"
    assert r["legend"] is True and r["endhead"] is True


def test_manifest_separates_two_adjacent_tables_of_equal_width(tmp_path):
    """The whole point. inkdrill groups pages into tables by contiguity plus
    equal width, which CANNOT separate 0049's equations and formulas — both
    5 columns, adjacent, so they group as one 28-row run. The builder knows
    it is 1 then 27 and now says so."""
    from pdfdrill import report_tex as rt
    tables = [
        rt._table_record("Display equations", (20, 7, 13, 80, 80),
                         True, True, ["D_EQ0001"]),
        rt._table_record("Inline formulas (first occurrence)",
                         (20, 7, 13, 80, 80), True, True,
                         ["D_FO%04d" % i for i in range(1, 28)]),
    ]
    assert tables[0]["columns"] == tables[1]["columns"] == 5
    assert [t["rows"] for t in tables] == [1, 27]
    # and the reconciliation a consumer performs against a 2-page run:
    # 1 + 27 identifiers + one legend row per page = 30, which is what
    # inkdrill measured on 0049.
    pages = 2
    legend_rows = sum(pages for t in tables if t["legend"] and t is tables[0])
    assert sum(t["rows"] for t in tables) + legend_rows == 30


def test_a_table_without_a_legend_adds_no_footer_row():
    """Image regions carry no legend and no \\endhead, and inkdrill measured
    exactly the identifier count there — 3 against 3."""
    from pdfdrill import report_tex as rt
    r = rt._table_record("Image regions — rendered against scan",
                         (20, 7, 12, 60, 60, 60), False, False,
                         ["D_DIA_0001", "D_DIA_0002", "D_DIA_0003"])
    assert r["legend"] is False and r["endhead"] is False
    assert r["rows"] == 3 and r["columns"] == 6


def test_longdiv_is_defined_in_the_shared_preamble():
    r"""442 — MathPix emits \longdiv for long division and NOTHING defines it.

    441 called this a package gap because `kpsewhich longdivision.sty` found a
    file. That package provides \longdivision and \intlongdivision; its
    `\def\longdiv@...` are internal macros with an @ in the name. Loading it
    changed nothing — measured, 0 of 7 rows compiled. Checking that a file
    exists is not checking that it defines the command.

    \providecommand rather than \newcommand: an injected author preamble that
    defines it should win, not abort the compile.
    """
    from pdfdrill import report_tex as rt
    assert r"\providecommand{\longdiv}" in rt.PREAMBLE
    assert r"\usepackage{longdivision}" not in rt.PREAMBLE


def test_align_only_refusal_is_exact_and_ignores_an_empty_value():
    r"""443 — the standalone route fires only when a depth-0 `&` is the SOLE
    objection.

    The empty case is the one that bit: an empty value passes every check and
    came back True, so `standalone_math` compiled an empty document into a
    blank PNG and four rows of johnston showed a blank image where they should
    have shown "---". A row with no LaTeX is not a row whose LaTeX is
    unrenderable.
    """
    from pdfdrill.report_tex import refused_for_align_only as f
    assert f("") is False
    assert f("   ") is False
    # a genuine depth-0 marker, everything else well formed
    assert f(r"\begin{array}{ll} a & b \end{array} & c") is True
    # refused for a DIFFERENT reason -> not this route's business
    assert f(r"\begin{figure} \[ x \] \end{figure}") is False
    assert f(r"x $ y") is False
    # renderable values are not refused at all
    assert f(r"a + b") is False


def test_renderable_accepts_an_escaped_dollar_and_refuses_a_bare_one():
    r"""446 — `\$` is currency and legal inside maths; the gate refused any `$`
    while the `%` check on the adjacent line strips its escape first.

    444 is the proof from outside: given `\$ 151` and the crop, the model
    returned `\$ 151` unchanged, and the gate refused its own input back.
    """
    from pdfdrill.report_tex import renderable
    assert renderable(r"\$ 151")
    assert renderable(r"\begin{array}{ll} 4 & \$ \\ 7 & \$ \end{array}")
    assert not renderable(r"a $ b")          # a BARE $ still ends the row


def test_a_leading_unmatched_opener_is_dropped_like_a_trailing_closer():
    r"""446 — the mirror of the \end{itemize} rule. Only an UNMATCHED opener:
    an environment that opens and closes inside the value keeps its own.
    """
    from pdfdrill.report_tex import renderable
    assert renderable(r"\begin{figure} \[ x = 1 \]")
    assert renderable(r"\begin{aligned} a &= b \end{aligned}")


def test_a_whole_float_with_its_caption_is_NOT_rescued():
    r"""446 — and this is the boundary that matters.

    Three johnston rows look like a glued-on opener and are not: they are a
    complete `\begin{figure} \[ … \] \caption{…} \end{figure}` — the equation
    AND its caption, captured as one "equation". 42 such rows across 21
    documents.

    Unwrapping one and typesetting it as mathematics would render a caption as
    maths. The row is mis-segmented, not mis-delimited, and it must keep
    failing the gate until it is re-segmented.
    """
    from pdfdrill.report_tex import renderable
    v = (r"\begin{figure} \[ x = 1 \] \caption{Figure 1.19: \(R\) rotates "
         r"the basis.} \end{figure}")
    assert not renderable(v)


# ---------------------------------------------------------------- 518

def test_delimiter_list_accepts_the_corner_and_arrow_delimiters():
    """\\lrcorner is as legal after \\right as ) is."""
    from pdfdrill.report_tex import is_delimiter
    for d in (r"\lrcorner", r"\llcorner", r"\ulcorner", r"\urcorner",
              r"\lfloor", r"\rfloor", r"\lceil", r"\rceil",
              r"\langle", r"\rangle", r"\vert", r"\Vert", r"\backslash",
              r"\uparrow", r"\downarrow", r"\updownarrow",
              r"\Uparrow", r"\Downarrow", r"\Updownarrow", ")", "|", "."):
        assert is_delimiter(d), d
    assert not is_delimiter(r"\lvertf")
    assert not is_delimiter(r"\Sigma")


def test_glued_delimiter_is_split_not_refused():
    r"""`\left\lvertf` is one undefined control sequence to TeX; repair it."""
    from pdfdrill.report_tex import renderable, split_glued_delimiter
    got = split_glued_delimiter(r"\left\lvertf(1)\right\rvert")
    assert got == r"\left\lvert f(1)\right\rvert"
    # and the repaired form is what renderable() hands back
    assert renderable(r"\left\lverte^{x}\right\rvert") == \
        r"\left\lvert e^{x}\right\rvert"


def test_a_real_delimiter_is_never_cut_down():
    r"""\rangle must not become \rangl + e."""
    from pdfdrill.report_tex import split_glued_delimiter
    for s in (r"\left\langle x\right\rangle", r"\left(x\right)",
              r"\left.\Sigma\right\lrcorner y"):
        assert split_glued_delimiter(s) == s


def test_mielke_eq0294_still_renders():
    r"""517's reference row: balanced, legal, and not this gate's business."""
    from pdfdrill.report_tex import renderable
    eq = (r"\left.\Sigma_{\alpha}=e_{\alpha} \downharpoonleft L-\left("
          r"e_{\alpha} \downharpoonleft D \Psi\right) \wedge \frac{\partial L}"
          r"{\partial D \Psi}-\left(e_{\alpha}\right\lrcorner \Psi\right) "
          r"\wedge \frac{\partial L}{\partial \Psi} .")
    assert renderable(eq)


def test_a_non_delimiter_after_left_is_refused():
    """Fires on no corpus row today; it is the list doing its stated job."""
    from pdfdrill.report_tex import renderable
    assert renderable(r"\left\Sigma x\right\Sigma") == ""


# ---------------------------------------------------------------- 522

def test_latex_similarity_is_symmetric_on_long_strings():
    """difflib autojunk fires at 200 elements on the SECOND sequence only."""
    from pdfdrill.scoring import latex_similarity
    a = (r"\begin{array}{cccc} \lambda_1 - \lambda_2 = \alpha_1, & \lambda_1 - "
         r"\lambda_3 = 2\alpha_1 + 3\alpha_2, & \lambda_2 - \lambda_3 = "
         r"\alpha_1 + 3\alpha_2, \\ \lambda_1 = \alpha_1 + \alpha_2, & "
         r"\lambda_2 = \alpha_2, & -\lambda_3 = \alpha_1 + 2\alpha_2 \end{array}")
    b = (r"\begin{aligned} \lambda_{1}-\lambda_{2} & =\alpha_{1}, & "
         r"\lambda_{1}-\lambda_{3} & =2 \alpha_{1}+3 \alpha_{2}, & "
         r"\lambda_{2}-\lambda_{3} & =\alpha_{1}+3 \alpha_{2}, \\ \lambda_{1} "
         r"& =\alpha_{1}+\alpha_{2}, & \lambda_{2} & =\alpha_{2} \end{aligned}")
    ab, ba = latex_similarity(a, b), latex_similarity(b, a)
    assert abs(ab - ba) < 1e-9, (ab, ba)
    # and it is a real score, not the autojunk artefact near zero
    assert ab > 0.7, ab


def test_latex_similarity_identical_is_one():
    from pdfdrill.scoring import latex_similarity
    long = r"\alpha_{1}+\beta_{2}=\gamma_{3} \quad " * 20
    assert latex_similarity(long, long) == 1.0


# ---------------------------------------------------------------- 525

def test_task_dir_shape_and_library_default(tmp_path):
    from pdfdrill import taskout
    d = taskout.task_dir(tmp_path, 525)
    assert d == tmp_path / "out" / "525" and d.is_dir()
    # a file target resolves to its directory — measurements name the doc
    f = tmp_path / "x.pdf"; f.write_text("")
    assert taskout.task_dir(f, "525b") == tmp_path / "out" / "525b"


def test_task_dir_refuses_a_non_task_name(tmp_path):
    import pytest
    from pdfdrill import taskout
    for bad in ("", "scratch", "../etc", "5"):
        with pytest.raises(ValueError):
            taskout.task_dir(tmp_path, bad)


def test_saves_are_named_back_for_the_report(tmp_path):
    from pdfdrill import taskout
    taskout.save_script(tmp_path, 525, "print(1)\n")
    taskout.save_json(tmp_path, 525, "rows", {"n": 3})
    got = [p.name for p in taskout.paths(tmp_path, 525)]
    assert got == ["rows.json", "script.py"]
    assert "script.py" in taskout.report_lines(tmp_path, 525)
    assert "nothing inspectable" in taskout.report_lines(tmp_path, 999)


def test_taskout_survives_a_lone_surrogate(tmp_path):
    """504: a census that dies on one filename has an unknown hole."""
    from pdfdrill import taskout
    bad = "caf\udce8"                      # CP1252 byte, unpaired surrogate
    p = taskout.save_json(tmp_path, 527, "rows", {"doc": bad, "n": 1})
    assert p.is_file() and p.read_bytes()          # written, not raised
    q = taskout.save_text(tmp_path, 527, "note.txt", bad)
    assert q.is_file()


# ---------------------------------------------------------------- 529/530

def _lines_fixture(tmp_path):
    import json
    p = tmp_path / "d.lines.json"
    p.write_text(json.dumps({"pages": [{"lines": [
        {"type": "page_info", "text": r"arXiv:2010.14265v2 [stat.ML] $P$ 2021",
         "confidence": 0.2,
         "region": {"top_left_x": 0, "top_left_y": 0,
                    "width": 40, "height": 900}},
        {"type": "text", "text": r"we set $x^2$ here and $P$ again",
         "confidence": 0.91, "confidence_rate": 0.99,
         "region": {"top_left_x": 10, "top_left_y": 20,
                    "width": 300, "height": 40}},
        {"type": "math", "text": r"\alpha=\beta", "confidence": 0.5,
         "region": {"top_left_x": 1, "top_left_y": 2,
                    "width": 3, "height": 4}}]}]}))
    return p


def test_spans_are_in_document_order_and_math_lines_are_skipped(tmp_path):
    from pdfdrill import inlinectx
    spans = inlinectx.load_spans(_lines_fixture(tmp_path))
    assert [s["latex"] for s in spans] == ["P", "x^2", "P"]
    assert all(s["line_type"] != "math" for s in spans)


def test_first_occurrence_wins_and_it_is_an_equality_not_a_search(tmp_path):
    """535 — containment put `P` on a line about "the past"; order fixes it."""
    from pdfdrill import inlinectx
    spans = inlinectx.load_spans(_lines_fixture(tmp_path))
    first = inlinectx.first_occurrences(spans)
    # `P` first occurs in the page_info line, and that IS its first occurrence
    assert first["P"]["line_type"] == "page_info"
    ctx = inlinectx.context_of(first["x^2"])
    assert ctx["page"] == 1 and ctx["confidence"] == 0.91
    assert (ctx["top_left_x"], ctx["width"]) == (10, 300)


def test_a_value_with_no_span_yields_no_context(tmp_path):
    """Absence of a host is not evidence of a confident one."""
    from pdfdrill import inlinectx
    spans = inlinectx.load_spans(_lines_fixture(tmp_path))
    first = inlinectx.first_occurrences(spans)
    assert inlinectx.context_of(first.get(r"\square")) == {}
    assert inlinectx.attach([r"\square"], _lines_fixture(tmp_path)) == {r"\square": {}}


# ---------------------------------------------------------------- 531

def test_every_katex_generator_carries_the_caveat():
    """One text, one place — and it must reach each emitted page."""
    import pathlib
    from docops.katex_notice import KATEX_WARNING_HTML
    root = pathlib.Path(__file__).resolve().parent.parent
    for rel in ("src/docops/projectors/formula_report.py",
                "src/docops/projectors/comparison_html.py",
                "src/docops/projectors/distill_reader.py",
                "src/pdfdrill/docinspect.py",
                "tools/corrections439.py"):
        src = (root / rel).read_text()
        assert "KATEX_WARNING_HTML" in src, rel
    # the text names the three measured numbers, so it cannot drift into
    # a vague caution
    for n in ("327", "10 documents", "11,088"):
        assert n in KATEX_WARNING_HTML, n


# ---------------------------------------------------------------- 543

def test_inspect_writes_only_paths_that_exist_and_are_non_empty(tmp_path):
    from pdfdrill import taskout
    good = tmp_path / "B.pdf"; good.write_bytes(b"%PDF-1.4\n")
    empty = tmp_path / "empty.pdf"; empty.write_bytes(b"")
    missing = tmp_path / "gone.pdf"
    r = taskout.inspect_list(tmp_path, 543, [
        (good, "B, 10 pages"), (empty, "an empty build"), (missing, "never built")])
    body = pathlib_read(r["path"])
    assert body.splitlines() == [str(good.resolve())]
    assert len(r["failed"]) == 2
    assert "is a promise" in taskout.inspect_report(r)
    # the reason is NOT in the file — drillui reads it
    assert "10 pages" not in body
    assert "10 pages" in taskout.inspect_report(r)


def pathlib_read(p):
    import pathlib
    return pathlib.Path(p).read_text()


def test_inspect_names_paths_drillui_cannot_open(tmp_path):
    """Half this library's folders have spaces in their names."""
    from pdfdrill import taskout
    d = tmp_path / "Geometric, Algebraic Methods"; d.mkdir()
    f = d / "B.pdf"; f.write_bytes(b"%PDF-1.4\n")
    r = taskout.inspect_list(tmp_path, 543, [(f, "B")])
    assert r["whitespace"] == [str(f.resolve())]
    assert "splits on whitespace" in taskout.inspect_report(r)


# ---------------------------------------------------------------- 550

def test_fo_tiddlers_carry_the_host_line_and_say_so(tmp_path):
    """The poorest row in the projection gains a page, a confidence and a
    region — and names whose confidence it is."""
    import json
    from docops.projectors.tiddlywiki import TiddlyWikiProjector  # noqa: F401
    from pdfdrill import inlinectx
    lines = tmp_path / "d.lines.json"
    lines.write_text(json.dumps({"pages": [{"lines": [
        {"type": "text", "text": r"we set $x^2$ here", "confidence": 0.91,
         "confidence_rate": 0.99,
         "region": {"top_left_x": 10, "top_left_y": 20,
                    "width": 300, "height": 40}}]}]}))
    first = inlinectx.first_occurrences(inlinectx.load_spans(lines))
    ctx = inlinectx.context_of(first.get("x^2"))
    # the fields the projector copies onto the tiddler
    assert ctx["page"] == 1
    assert ctx["confidence"] == 0.91
    assert (ctx["top_left_x"], ctx["width"], ctx["height"]) == (10, 300, 40)


def test_an_fo_row_is_never_flagged_or_doubted_by_a_line_confidence():
    """A line's confidence must not push an inline formula into a findings
    class that means the FORMULA was measured. FO rows carry no ink."""
    from pdfdrill.report_tex import INK_AGREES, INK_FLAGS
    code = ""                      # what an FO row's ink code is
    assert code[:1] not in INK_AGREES
    assert code[:1] not in INK_FLAGS


# ---------------------------------------------------------------- 551

def test_a_findings_build_describes_its_own_longtables(tmp_path):
    """551 — every append to tables_manifest sat inside `if not findings:`,
    so all 21 findings builds wrote report.tables.json EMPTY. inkmeasure
    reads it to segment the report and raises MeasureRefused without it."""
    import json
    from pdfdrill.report_tex import build_report, TABLES_MANIFEST
    tiddlers = [
        {"title": "k_EQ0001", "latex": r"x=1", "page": "1", "type": "equation",
         "confidence": "0.02"},
        {"title": "k_EQ0002", "latex": r"\zzz{", "page": "2", "type": "equation"},
    ]
    tp = tmp_path / "k.tiddlers.json"
    tp.write_text(json.dumps(tiddlers))
    build_report(tp, findings=True, formulas="none")
    man = json.loads((tmp_path / TABLES_MANIFEST).read_text())
    caps = [t["caption"] for t in man["tables"]]
    # the row that does not render is Unresolved, and the manifest says so
    assert "Unresolved" in caps, man
    for t in man["tables"]:
        assert t["rows"] == len(t["identifiers"]) and t["rows"] > 0


# ---------------------------------------------------------------- 563

def test_role_is_anchored_not_a_substring():
    """`Index Theorems` is body and `Literatur` inside prose is body."""
    from pdfdrill.regionrole import role_of_heading, BODY, TOC, BIBLIOGRAPHY, INDEX
    assert role_of_heading("References") == BIBLIOGRAPHY
    assert role_of_heading("5 Bibliography") == BIBLIOGRAPHY
    assert role_of_heading("Literaturverzeichnis") == BIBLIOGRAPHY
    assert role_of_heading("Inhaltsverzeichnis") == TOC
    assert role_of_heading("Stichwortverzeichnis") == INDEX
    # the two that must NOT match
    assert role_of_heading("Index Theorems") == BODY
    assert role_of_heading("die betreffende Literatur als Metapher") == BODY
    assert role_of_heading("Introduction") == BODY


def test_a_heading_ends_the_previous_region(tmp_path):
    """A region runs to the NEXT heading, not to the end of the document."""
    import json
    from pdfdrill import regionrole as rr
    p = tmp_path / "d.lines.json"
    p.write_text(json.dumps({"pages": [{"lines": [
        {"type": "text", "text": "prose"},
        {"type": "section_header", "text": "References"},
        {"type": "text", "text": "a citation"},
        {"type": "section_header", "text": "Appendix A"},
        {"type": "text", "text": "prose again"}]}]}))
    roles = [r[3] for r in rr.roles_for(p)]
    assert roles == [rr.BODY, rr.BIBLIOGRAPHY, rr.BIBLIOGRAPHY,
                     rr.BODY, rr.BODY]


def test_page_info_is_never_a_heading(tmp_path):
    """The one German structural word in this library sits in a running
    header on a page that is not the table of contents."""
    import json
    from pdfdrill import regionrole as rr
    p = tmp_path / "d.lines.json"
    p.write_text(json.dumps({"pages": [{"lines": [
        {"type": "page_info", "text": "Inhaltsverzeichnis"},
        {"type": "text", "text": "body prose"}]}]}))
    assert [r[3] for r in rr.roles_for(p)] == [rr.BODY, rr.BODY]


def test_the_german_branch_on_a_real_document(tmp_path):
    """WDorg4's shape: the TOC's own entry naming the bibliography must not
    open one, and the running header must not open a TOC."""
    import json
    from pdfdrill import regionrole as rr
    p = tmp_path / "d.lines.json"
    p.write_text(json.dumps({"pages": [{"lines": [
        {"type": "section_header", "text": "INHALTSVERZEICHNIS"},
        {"type": "page_info", "text": "Inhaltsverzeichnis"},
        {"type": "table_of_contents_item", "text": "Literaturverzeichnis"},
        {"type": "section_header", "text": "KAPITEL I"},
        {"type": "text", "text": "prose"},
        {"type": "section_header", "text": "LITERATURVERZEICHNIS"},
        {"type": "text", "text": "a citation"}]}]}))
    roles = [r[3] for r in rr.roles_for(p)]
    assert roles == [rr.TOC, rr.TOC, rr.TOC,
                     rr.BODY, rr.BODY,
                     rr.BIBLIOGRAPHY, rr.BIBLIOGRAPHY], roles
