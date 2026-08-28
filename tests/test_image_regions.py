"""282 — the image-regions section names its tex.zip source by region 5-tuple.

out/279 established the filename IS the key:
`<process-id>-<page>_<height>_<width>_<top_left_y>_<top_left_x>.jpg`, and
20,276 of 20,287 corpus filenames match a region in their own document's
lines.json exactly. So the association is a dictionary lookup, not a guess.

The section used to key on `(page, height, width)` and fall back to "any image
on that page", which attached the first image of a page to every unmatched row
on it — a named source that could be the wrong picture.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.report_tex import texzip_images


def _zip(tmp_path, *names):
    d = tmp_path / "texzip" / "abc"
    d.mkdir(parents=True)
    for n in names:
        (d / n).write_bytes(b"\xff\xd8" + b"x" * 600)
    return d


def test_the_index_is_keyed_on_the_full_five_tuple(tmp_path):
    d = _zip(tmp_path, "abc-04_548_852_666_640.jpg", "abc-10_517_918_440_595.jpg")
    reg, n = texzip_images(d)
    assert n == 2
    assert set(reg) == {(4, 548, 852, 666, 640), (10, 517, 918, 440, 595)}


def test_two_figures_on_one_page_stay_distinct(tmp_path):
    """The old key was (page, height, width) with a page fallback, so a second
    figure on page 10 took the first one's file."""
    d = _zip(tmp_path, "abc-10_517_918_440_595.jpg", "abc-10_690_1217_1248_459.jpg")
    reg, _ = texzip_images(d)
    assert len(reg) == 2
    assert reg[(10, 517, 918, 440, 595)].name != reg[(10, 690, 1217, 1248, 459)].name


def test_same_size_figures_on_one_page_are_not_collapsed(tmp_path):
    """Identical height and width, different position — the 3-tuple key made
    these one entry."""
    d = _zip(tmp_path, "abc-07_300_400_100_50.jpg", "abc-07_300_400_900_50.jpg")
    reg, _ = texzip_images(d)
    assert len(reg) == 2


def test_a_zip_with_no_images_reports_zero_not_an_empty_index(tmp_path):
    """285 of 1,216 corpus tex.zips hold no image at all. That must not read
    like a lookup that failed."""
    d = tmp_path / "texzip" / "abc"
    d.mkdir(parents=True)
    (d / "abc.tex").write_text("\\documentclass{article}")
    reg, n = texzip_images(d)
    assert (reg, n) == ({}, 0)


def test_an_unparseable_filename_is_counted_but_not_indexed(tmp_path):
    d = _zip(tmp_path, "abc-04_548_852_666_640.jpg", "logo.jpg")
    reg, n = texzip_images(d)
    assert n == 2 and len(reg) == 1


def test_the_section_distinguishes_the_three_no_source_cases():
    """A row with no named file must say WHICH of the three it is: no zip, a
    zip holding no images, or a zip that has images but none for this region."""
    import inspect
    from pdfdrill import report_tex
    src = inspect.getsource(report_tex.build_report)
    assert "no tex.zip" in src
    assert "tex.zip holds no images" in src
    assert "no image for this region" in src


def test_naming_the_file_does_not_claim_the_latex_is_right():
    """281 is still open: the filename says which file, not that its
    tikzpicture or tabular renders to what is on the page."""
    import inspect
    from pdfdrill import report_tex
    src = inspect.getsource(report_tex.build_report)
    assert "does NOT" in src and "renders to" in src


# ---- 284: rendering a region's own LaTeX beside its crop -------------------

from pdfdrill.report_tex import region_render, _ampersand_safe, _demote_line


def test_a_picture_environment_is_scaled_into_the_cell():
    out = region_render(r"\begin{tikzpicture}\draw(0,0)--(1,1);\end{tikzpicture}", 40)
    assert out.startswith(r"\resizebox{40.0mm}{!}{")
    assert r"\begin{tikzpicture}" in out


def test_tikzcd_gets_the_ampersand_replacement_it_needs_in_a_table_cell():
    r"""A tikzcd uses `&` as its cell separator and so does the longtable it
    sits in — pgf reports "Single ampersand used with wrong catcode", 239
    characters land in nullfont and the row is demoted. tikz-cd's own
    `[ampersand replacement=\&]` is the remedy, verified compiling standalone."""
    out = region_render(r"\begin{tikzcd} A\arrow[r]&B \end{tikzcd}", 40)
    assert r"ampersand replacement=\&" in out
    assert r"\arrow[r]\&B" in out


def test_existing_tikzcd_options_are_kept_not_clobbered():
    out = region_render(r"\begin{tikzcd}[sep=small] A&B \end{tikzcd}", 40)
    assert "sep=small" in out and r"ampersand replacement=\&" in out


def test_a_tikzpicture_with_a_bare_ampersand_is_refused():
    """A \matrix node uses `&` and tikzpicture has no replacement option, so it
    cannot go in a table cell. Refused rather than guessed at."""
    assert region_render(r"\begin{tikzpicture}\matrix{a&b\\};\end{tikzpicture}", 40) == ""


def test_an_unknown_environment_is_refused_not_set_as_maths():
    """The first version matched only tikzpicture and let everything else fall
    through to renderable(), which set `\begin{tikzcd}…` as MATH — 658 corpus
    rows of commutative diagram handed to the math parser, and 2208.01506 then
    produced NO pdf at all."""
    for env in ("axis", "groupplot", "minipage", "itemize", "comment"):
        assert region_render("\\begin{%s} x \\end{%s}" % (env, env), 40) == ""


def test_a_listing_is_set_as_text_not_as_a_verbatim_environment():
    out = region_render("\\begin{lstlisting}[mathescape=true]\n>f:=2\n\\end{lstlisting}")
    assert out.startswith(r"{\ttfamily\tiny")
    assert "lstlisting" not in out


def test_math_still_goes_through_renderable():
    assert r"\displaystyle" in region_render(r"\begin{array}{c}a\end{array}")
    assert region_render("") == ""


def test_the_fixpoint_can_demote_a_picture_cell():
    """It used to substitute `$\displaystyle …$` only, so a failing picture row
    could not be demoted: the loop found no change, broke, and left the errors
    in the document."""
    line = (r"\ident{X} & 4 & src & \resizebox{40mm}{!}{\begin{tikzcd}"
            r"A\arrow[r]\&B\end{tikzcd}} & crop \\ \hline")
    out = _demote_line(line)
    assert r"\emph{(not rendered)}" in out
    assert "resizebox" not in out
    assert "& crop \\\\ \\hline" in out          # the other cells survive


def test_demote_leaves_a_row_with_nothing_to_demote_alone():
    line = r"\ident{Z} & 4 & s & t & c \\ \hline"
    assert _demote_line(line) == line


def test_ampersand_safe_passes_through_when_there_is_no_ampersand():
    body = r"\begin{tikzcd} A \end{tikzcd}"
    assert _ampersand_safe(body, "tikzcd") == body
