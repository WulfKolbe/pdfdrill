"""269 — the qualified field reference `{{Title!!field}}`.

TiddlyWiki writes `{{0049_H5!!caption}}` for "the caption field OF tiddler
0049_H5". `_rewrite_transclusions` tested only `body.startswith("!!")`, so a
qualified reference fell through to the link branch and the WHOLE string became
a tiddler title — `[0049_H5!!caption](./0049_H5!!caption.md)`, a path that
cannot exist. 190 of the 192 dead links in the corpus sample were this.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docops.projectors.okf import (_rewrite_transclusions, _to_markdown,
                                   tiddlers_to_okf)


_PATHS = {"K_H5": "sections/K_H5.md", "K_H4": "sections/K_H4.md"}
_BY_TITLE = {
    "K_H5": {"title": "K_H5", "caption": "4.1 Representation Model", "level": "2"},
    "K_H4": {"title": "K_H4", "caption": "4 Model"},
}


def _rw(text, from_path="sections/K_H4.md"):
    return _rewrite_transclusions(text, _BY_TITLE["K_H4"], _PATHS, from_path,
                                  by_title=_BY_TITLE)


def test_a_qualified_reference_resolves_the_value_and_links_to_the_target():
    assert _rw("{{K_H5!!caption}}") == "[4.1 Representation Model](./K_H5.md)"


def test_the_emitted_href_never_contains_the_field_accessor():
    out = _rw("{{K_H5!!caption}}")
    assert "!!" not in out
    assert "K_H5!!caption.md" not in out


def test_a_qualified_reference_to_any_field_not_just_caption():
    assert _rw("{{K_H5!!level}}") == "[2](./K_H5.md)"


def test_an_unqualified_reference_still_reads_the_CURRENT_tiddler():
    # `{{!!caption}}` must keep inlining the bare value, with no link.
    assert _rw("# {{!!caption}}") == "# 4 Model"


def test_a_template_transclusion_is_untouched():
    assert _rw("{{K_H5||TPL}}") == "[unit](./K_H5.md)"


def test_an_unknown_target_degrades_to_the_title_not_to_a_bad_path():
    out = _rewrite_transclusions("{{K_H9!!caption}}", _BY_TITLE["K_H4"],
                                 _PATHS, "sections/K_H4.md", by_title=_BY_TITLE)
    assert out == "[K_H9](./K_H9.md)"
    assert "!!" not in out


def test_a_missing_by_title_index_still_never_emits_a_path_with_bangs():
    # Degrades to a link labelled by the title; the old code produced
    # `./K_H5!!caption.md`, which is the thing that must not come back.
    out = _rewrite_transclusions("{{K_H5!!caption}}", _BY_TITLE["K_H4"],
                                 _PATHS, "sections/K_H4.md")
    assert "!!" not in out


def test_as_link_false_gives_the_bare_value_for_a_description():
    out = _rewrite_transclusions("{{K_H5!!caption}}", _BY_TITLE["K_H4"],
                                 _PATHS, "sections/K_H4.md",
                                 as_link=False, by_title=_BY_TITLE)
    assert out == "4.1 Representation Model"


def test_end_to_end_the_bundle_link_points_at_a_file_it_writes():
    tiddlers = [
        {"title": "K_H4", "tags": "section", "text": "{{K_H5!!caption}}",
         "caption": "4 Model"},
        {"title": "K_H5", "tags": "section", "text": "body",
         "caption": "4.1 Representation Model"},
    ]
    bundle = tiddlers_to_okf(tiddlers, "K", {}, "T")
    body = bundle["sections/K_H4.md"]
    assert "[4.1 Representation Model](./K_H5.md)" in body
    assert "sections/K_H5.md" in bundle       # the target really is written
    assert "!!" not in body


# ---- 270: the self-closing widget whose value was stripped with the tag ----

from docops.projectors.okf import _self_widgets_to_markdown, _okf_body


def test_an_image_widget_becomes_markdown_content():
    t = {"canonical_uri": "https://cdn.mathpix.com/cropped/a-1.jpg?h=1&w=2",
         "width": "200", "height": "100"}
    out = _self_widgets_to_markdown(
        "<$image source={{!!canonical_uri}} width={{!!width}} "
        "height={{!!height}}/>", t)
    assert out == "![](https://cdn.mathpix.com/cropped/a-1.jpg?h=1&w=2)"


def test_a_latex_widget_becomes_inline_or_display_math():
    t = {"latex": "E = m c^{2}", "displayMode": ""}
    assert _self_widgets_to_markdown(
        "<$latex text={{!!latex}} displayMode={{!!displayMode}} />", t) == "$E = m c^{2}$"
    t2 = {"latex": "E = m c^{2}"}
    assert _self_widgets_to_markdown(
        "<$latex text={{!!latex}} displayMode=true />", t2) == "$$ E = m c^{2} $$"


def test_a_latex_body_with_spaces_braces_and_slashes_survives_whole():
    # The reason this runs BEFORE transclusion: once inlined, the attribute
    # cannot be delimited again without guessing where it ends.
    tex = r"\max _{x}\left[\sqrt{a/b}\right)^{2} > 0"
    out = _self_widgets_to_markdown(
        "<$latex text={{!!latex}} displayMode=true />", {"latex": tex})
    assert out == f"$$ {tex} $$"


def test_a_widget_whose_field_is_empty_emits_nothing_not_a_stub():
    assert _self_widgets_to_markdown(
        "<$image source={{!!canonical_uri}} />", {"canonical_uri": ""}) == ""
    assert _self_widgets_to_markdown(
        "<$latex text={{!!latex}} />", {"latex": ""}) == ""


def test_a_quoted_attribute_still_works():
    assert _self_widgets_to_markdown('<$image source="http://x/i.png"/>', {}) \
        == "![](http://x/i.png)"


def test_a_paired_latex_widget_is_left_to_the_existing_converter():
    # <$latex>body</$latex> is NOT self-closing; _widgets_to_markdown owns it.
    txt = "<$latex>a+b</$latex>"
    assert _self_widgets_to_markdown(txt, {}) == txt


def test_the_picture_body_is_populated_end_to_end():
    t = {"title": "K_PIC_0001", "tags": "picture",
         "canonical_uri": "http://cdn/x.jpg", "width": "10", "height": "5",
         "text": "<$image source={{!!canonical_uri}} width={{!!width}} "
                 "height={{!!height}}/>"}
    body = _okf_body(t, "Picture", {"K_PIC_0001": "figures/K_PIC_0001.md"},
                     "figures/K_PIC_0001.md", {"K_PIC_0001": t})
    assert body.strip() == "![](http://cdn/x.jpg)"
