r"""The author's figures are where the author's source is.

T-0156. `_DEFAULT_PREAMBLE` emits `\graphicspath{{./}{../}}`: `./` is the
`latex/` directory the compile runs in, `../` is the document folder, where
OUR OWN `report-crops/` live. That is why 2507.21892v1 compiles clean with 18
`\includegraphics` — its images are ours and `../` reaches them. An author's
own path (`figures/DVS_image.png`) reaches neither, because `cmd_latex`
unpacks the source at `<blob_dir>/texsrc/` and writes the .tex to
`<blob_dir>/latex/`.

AND A MISSING IMAGE IS FATAL UNDER XELATEX, which is why this cost a whole
document rather than one figure. xetex pipes its DVI to xdvipdfmx:

    xdvipdfmx:fatal: Image inclusion failed. Could not find file: figures/…
    No output PDF file written.

xdvipdfmx aborts, xetex dies of the broken pipe (returncode -13), and the log
is truncated mid-word. 2102.08145 produced NO document for this reason, and
its 34 errors and 0.0% word coverage were CONSEQUENCES. The truncated log's
last line named `\unitfrac`, which had nothing to do with it.

MEASURED on the real .tex with one entry added:

    plain     rc=-13   34 errors   NO pages    4 unable-to-load
    withsrc   rc=1     30 errors   27 pages    0 unable-to-load

TWO CONDITIONS, AND THE SECOND ONE WAS WRONG ONCE. The entry is a RELATIVE
path, so it is correct only when the source sits beside the output, and the
projector is TOLD that folder (`crops_dir`'s parent is `sc.blob_dir`). The
first version instead probed for a sibling `latex/` directory — pdfdrill's own
output directory, which `cmd_latex` creates on the line AFTER
`projector.project(doc)` and which the audit runner removes first. On a clean
run that probe ALWAYS failed and the entry was never emitted; it passed only
where an earlier run had left `latex/` behind. `test_the_entry_is_emitted_
before_the_latex_directory_exists` pins it.
"""
import pytest

from docops.projectors.latex_pipeline import (add_source_graphicspath,
                                              source_graphics_entry)

PRE = "\\documentclass{article}\n\\graphicspath{{./}{../}}\n\\begin{document}\n"


@pytest.fixture()
def doc(tmp_path):
    """A document folder with the source unpacked beside the PDF.

    Deliberately WITHOUT a `latex/` directory: that is the state at
    projection time.
    """
    (tmp_path / "texsrc").mkdir()
    (tmp_path / "doc.pdf").write_bytes(b"%PDF-1.4\n")
    return tmp_path


def test_the_entry_is_relative_to_the_document_folder(doc):
    assert source_graphics_entry({"latex_source_dir": str(doc / "texsrc")},
                                 doc) == "{../texsrc/}"


def test_the_entry_is_emitted_before_the_latex_directory_exists(doc):
    """The regression. `latex/` does not exist when `project` runs."""
    assert not (doc / "latex").exists()
    assert source_graphics_entry({"latex_source_dir": str(doc / "texsrc")},
                                 doc) == "{../texsrc/}"
    (doc / "latex").mkdir()             # and it makes no difference either way
    assert source_graphics_entry({"latex_source_dir": str(doc / "texsrc")},
                                 doc) == "{../texsrc/}"


def test_a_source_outside_the_document_folder_gets_no_entry(doc, tmp_path):
    """No absolute fallback, and not only for portability.

    A source directory outside the document folder is a path on this machine,
    and for a library document it is a path THROUGH THE LIBRARY —
    `1503.00301`'s is `pdfdrill-library/<folder>/<sub>`. An absolute entry
    would write a library folder name into the projected .tex, which is an
    output file, and the owner's rule keeps those names out of source, logs
    and messages. A relative entry would simply be wrong. Nothing is lost:
    in that case the figures are not beside the document either, so the fix
    is to copy them in.
    """
    elsewhere = tmp_path.parent / "elsewhere"
    elsewhere.mkdir(exist_ok=True)
    assert source_graphics_entry({"latex_source_dir": str(elsewhere)},
                                 doc) == ""


def test_without_a_document_folder_nothing_is_emitted(doc):
    # a relative path cannot be justified if we do not know what it is
    # relative TO
    assert source_graphics_entry({"latex_source_dir": str(doc / "texsrc")},
                                 None) == ""


@pytest.mark.parametrize("meta", [{}, None, {"latex_source_dir": ""},
                                  {"latex_source_dir": "/nonexistent/xyz"}])
def test_no_source_means_no_entry(meta, doc):
    assert source_graphics_entry(meta, doc) == ""


def test_the_entry_joins_the_existing_search_path(doc):
    out = add_source_graphicspath(
        PRE, {"latex_source_dir": str(doc / "texsrc")}, doc)
    assert "\\graphicspath{{./}{../}{../texsrc/}}" in out, out
    assert "{./}" in out and "{../}" in out


def test_a_preamble_with_no_graphicspath_gets_one(doc):
    out = add_source_graphicspath(
        "\\documentclass{article}\n",
        {"latex_source_dir": str(doc / "texsrc")}, doc)
    assert "\\graphicspath{{./}{../}{../texsrc/}}" in out


def test_applying_it_twice_changes_nothing(doc):
    meta = {"latex_source_dir": str(doc / "texsrc")}
    once = add_source_graphicspath(PRE, meta, doc)
    assert add_source_graphicspath(once, meta, doc) == once


def test_a_preamble_without_a_source_is_untouched(doc):
    assert add_source_graphicspath(PRE, {}, doc) == PRE


def test_an_unbalanced_graphicspath_is_left_alone(doc):
    broken = "\\graphicspath{{./}\n"          # never closed
    out = add_source_graphicspath(
        broken, {"latex_source_dir": str(doc / "texsrc")}, doc)
    assert out == broken


def test_the_source_directory_name_is_not_hardcoded(tmp_path):
    (tmp_path / "doc.pdf").write_bytes(b"%PDF-1.4\n")
    for name in ("texsrc", "src", "e-print"):
        d = tmp_path / name
        d.mkdir()
        assert source_graphics_entry({"latex_source_dir": str(d)},
                                     tmp_path) == "{../%s/}" % name


def test_no_projected_tex_can_carry_a_machine_path(doc):
    for meta in ({"latex_source_dir": str(doc / "texsrc")},
                 {"latex_source_dir": "/home/someone/pdfdrill-library/x/y"}):
        out = add_source_graphicspath(PRE, meta, doc)
        assert "/home/" not in out, out


def test_the_projector_puts_it_in_the_preamble(doc):
    """End to end through `project`, with the params `cmd_latex` passes."""
    from docmodel import DocObject, Document

    from docops.base import OperatorConfig
    from docops.projectors.latex import LaTeXProjector

    model = Document()
    model.meta["latex_source_dir"] = str(doc / "texsrc")
    model.add(DocObject(type="Paragraph", props={"text": "a paragraph."}))
    tex = LaTeXProjector(OperatorConfig(
        op="projector", classname="LaTeXProjector",
        params={"crops_dir": str(doc / "report-crops"),
                "crops_base": "report-crops"})).project(model)
    assert "{../texsrc/}" in tex, tex[:400]


def test_a_document_with_no_source_gets_the_plain_path(doc):
    from docmodel import DocObject, Document

    from docops.base import OperatorConfig
    from docops.projectors.latex import LaTeXProjector

    model = Document()
    model.add(DocObject(type="Paragraph", props={"text": "a paragraph."}))
    tex = LaTeXProjector(OperatorConfig(
        op="projector", classname="LaTeXProjector",
        params={"crops_dir": str(doc / "report-crops")})).project(model)
    assert "\\graphicspath{{./}{../}}" in tex
    assert "texsrc" not in tex
