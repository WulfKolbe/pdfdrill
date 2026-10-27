r"""`pdfdrill md` emits MathPix's Markdown dialect, because the corpus is written
in it.

THE DIALECT IS NOT A PREFERENCE — IT IS MEASURED. 600 intact MathPix downloads
in the library (documents whose sidecar records a bought `md` and whose file on
disk still carries no pdfdrill front matter):

    inline math `$…$`                 100%      display `$$` on its own line  84%
    `#` / `##` headings            91% / 99%      `\section*`                    1%
    images `![](…)` with EMPTY alt     82%      image with alt text            0%
    pipe tables                        70%      `\begin{tabular}`              0%
    YAML front matter                   0%      `\tag{…}`                 1 of 600
    italic caption after an image       0%

So the projector's old output differed from the reference in exactly four
places: `\(…\)`/`\[…\]` delimiters, alt text on every image, an italicised
caption, and a YAML header. Everything else — headings, pipe tables, link
shape, `\begin{aligned}` left inside the math — already agreed.

The delimiters have a SINGLE SOURCE OF TRUTH: the conversion options pdfdrill
sends MathPix on the wire (`mathpix_client.CONVERSION_OPTIONS`). A projection
that hard-codes its own copy drifts the moment the purchase changes, and the
drift is invisible — both files render. `test_the_delimiters_are_the_ones_
pdfdrill_asks_mathpix_for` is the join.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from docmodel.core import Document, DocObject                # noqa: E402
from docops.base import OperatorConfig                       # noqa: E402
from docops.projectors import markdown as M                  # noqa: E402

BK = "doc"


def _doc(*objs, meta=None):
    d = Document()
    d.meta["bibkey"] = BK
    d.meta.update(meta or {})
    for i, o in enumerate(objs):
        o.props.setdefault("flow_index", i)
        d.add(o)
    return d


def _md(doc, **params):
    return M.MarkdownProjector(OperatorConfig(
        op="projector", classname="MarkdownProjector",
        params=params)).project(doc)


# ── the delimiters, and where they come from ────────────────────────────────

def test_the_delimiters_are_the_ones_pdfdrill_asks_mathpix_for():
    """One source of truth. If the wire options ever change, this fails here
    rather than quietly producing a dialect the corpus is not written in."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from pdfdrill.mathpix_client import CONVERSION_OPTIONS
    md_opts = CONVERSION_OPTIONS["conversion_options"]["md"]
    assert list(M.MATH_INLINE) == md_opts["math_inline_delimiters"]
    assert list(M.MATH_DISPLAY) == md_opts["math_display_delimiters"]


def test_inline_math_uses_dollar_delimiters():
    doc = _doc(DocObject(type="Paragraph", props={
        "text": 'see <$latex text="x^2" displayMode="false"/> there'}))
    out = _md(doc)
    assert "$x^2$" in out
    assert "\\(" not in out and "\\)" not in out


def test_display_math_is_dollar_dollar_on_its_own_line():
    r"""84% of the reference files put the fence on its own line. A `$$…$$` all
    on one line renders, so nothing would have caught this but a measurement."""
    doc = _doc(DocObject(type="Equation", props={"latex": "E = mc^2"}))
    out = _md(doc)
    assert re.search(r"(?m)^\$\$$", out), out
    assert re.search(r"(?ms)^\$\$\nE = mc\^2\n\$\$", out), out
    assert "\\[" not in out and "\\]" not in out


def test_a_display_widget_in_prose_also_becomes_dollar_dollar():
    doc = _doc(DocObject(type="Paragraph", props={
        "text": 'then <$latex text="a+b" displayMode="true"/>'}))
    out = _md(doc)
    assert "$$a+b$$" in out
    assert "\\[" not in out


def test_an_equation_keeps_its_number_as_plain_text():
    r"""MathPix emits `\tag{}` once in 600 files, so the number is not part of
    the math. It is still content: dropping it would lose the only handle the
    prose has on the equation it refers to."""
    doc = _doc(DocObject(type="Equation",
                         props={"latex": "E = mc^2", "refnum": "37"}))
    out = _md(doc)
    assert "(37)" in out and "\\tag" not in out


# ── the prose arrives in the OTHER MathPix dialect ──────────────────────────

def test_math_already_in_the_prose_is_redelimited():
    r"""The model is built from `lines.json`, which delimits inline math
    `\(…\)` whatever the md options say — 80 occurrences and no `$` at all in
    DML_003-2010-1_16.lines.json. `_unwidget` never touched these, so the first
    projection after the delimiter change still carried 28 of them."""
    doc = _doc(DocObject(type="Paragraph", props={
        "text": r"Wolska \({ }^{1}\) and Grigore \({ }^{2}\)"}))
    out = _md(doc)
    assert "${ }^{1}$" in out and "${ }^{2}$" in out
    assert "\\(" not in out and "\\)" not in out


def test_a_display_span_in_the_prose_becomes_a_double_fence():
    doc = _doc(DocObject(type="Paragraph", props={
        "text": r"so \[a = b\] follows"}))
    out = _md(doc)
    assert "$$a = b$$" in out and "\\[" not in out


def test_a_literal_dollar_in_the_prose_is_escaped():
    r"""`escape_dollar: True` is in the options pdfdrill sends, and 58 of 400
    intact downloads carry a `\$`. A bare one would open mathematics."""
    doc = _doc(DocObject(type="Paragraph", props={"text": "it costs 5$ or less"}))
    out = _md(doc)
    assert r"5\$ or less" in out


def test_a_dollar_inside_the_math_is_left_alone():
    """The escaping must not reach into a formula — that would change the
    equation, not its delimiters."""
    doc = _doc(DocObject(type="Paragraph", props={
        "text": r"price \(a \$ b\) here"}))
    out = _md(doc)
    assert r"$a \$ b$" in out


def test_the_dollar_escaping_does_not_eat_a_latex_widget():
    """The regression the first version of this caused: `<$latex …/>` begins
    with a dollar, so escaping every bare one left `<\\$latex` behind and
    `_unwidget` matched nothing — the widget source went out as prose."""
    doc = _doc(DocObject(type="Paragraph", props={
        "text": 'see <$latex text="x^2" displayMode="false"/> and 5$ too'}))
    out = _md(doc)
    assert "$x^2$" in out and "$latex" not in out
    assert r"5\$ too" in out


def test_an_already_escaped_dollar_is_not_escaped_twice():
    doc = _doc(DocObject(type="Paragraph", props={"text": r"5\$ only"}))
    out = _md(doc)
    assert r"5\$ only" in out and r"\\$" not in out


# ── the three remaining differences ─────────────────────────────────────────

def test_an_image_carries_no_alt_text(tmp_path):
    """0 of 600 reference files carry alt text. The caption is not lost — it is
    emitted below the image, where MathPix puts it."""
    (tmp_path / "doc_PIC_0001.jpg").write_bytes(b"\xff\xd8\xff")
    doc = _doc(DocObject(type="Picture", props={"caption": "A photo"}))
    out = _md(doc, crops_dir=str(tmp_path), crops_base="report-crops")
    assert "![](report-crops/doc_PIC_0001.jpg)" in out
    assert "![A photo]" not in out
    assert "A photo" in out, "the caption itself must survive"


def test_a_caption_is_plain_text_not_italics(tmp_path):
    (tmp_path / "doc_PIC_0001.jpg").write_bytes(b"\xff\xd8\xff")
    doc = _doc(DocObject(type="Picture", props={"caption": "Figure 1: a photo"}))
    out = _md(doc, crops_dir=str(tmp_path), crops_base="report-crops")
    assert "Figure 1: a photo" in out
    assert "*Figure 1: a photo*" not in out


def test_there_is_no_yaml_front_matter_by_default():
    doc = _doc(DocObject(type="Paragraph", props={"text": "hello"}),
               meta={"title": "T"})
    out = _md(doc)
    assert not out.startswith("---"), out[:200]
    assert "generator: pdfdrill" not in out


def test_front_matter_is_still_available_when_asked_for():
    """The header is useful to a reader who wants one; it is simply not what
    MathPix writes, so it is no longer the default."""
    doc = _doc(DocObject(type="Paragraph", props={"text": "hello"}),
               meta={"title": "T"})
    out = _md(doc, front_matter=True)
    assert out.startswith("---") and "generator: pdfdrill" in out


# ── what must NOT change ────────────────────────────────────────────────────

def test_headings_and_pipe_tables_are_unchanged():
    r"""91%/99% `#`/`##` and 70% pipe tables in the reference: the projector was
    already right here, and a `\section*` "improvement" would move it away."""
    doc = _doc(DocObject(type="Section", props={"caption": "Intro", "level": 1}))
    out = _md(doc)
    assert re.search(r"(?m)^#+ Intro", out), out
    assert "\\section" not in out
