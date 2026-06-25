"""`pdfdrill conclusion` — retrieve the document's concluding paragraphs.

Finds the conclusion SECTION by a heading heuristic over the Section captions
(the TOC), preferring a strong match ("Conclusion") before the References/Appendix
boundary; returns its paragraphs in flow order. Falls back to the final body
paragraphs when no conclusion section is named. Distinct from the Abstract (which
gives goal/method, not results).
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import conclusion as C


def _o(t, fi=None, text="", caption="", **extra):
    p = {"flow_index": fi, "text": text, "caption": caption}
    p.update(extra)
    return types.SimpleNamespace(type=t, id=f"id{fi}", props=p)


def _doc(objs):
    return objs


def test_find_conclusion_section_strong_before_appendix():
    objs = [
        _o("Section", 1, caption="Introduction"),
        _o("Section", 50, caption="Empirical Analysis"),
        _o("Section", 90, caption="Conclusion and Future Work"),
        _o("Section", 95, caption="Appendix"),
        _o("Section", 99, caption="References"),
    ]
    sec = C.find_conclusion_section(objs)
    assert sec is not None and "Conclusion" in sec.props["caption"]


def test_conclusion_text_collects_flow_range_paragraphs():
    objs = [
        _o("Section", 10, caption="Results"),
        _o("Paragraph", 11, text="A result paragraph."),
        _o("Section", 20, caption="Conclusion"),
        _o("Paragraph", 21, text="We showed X on small examples."),
        _o("Paragraph", 22, text="Future work will scale it."),
        _o("Section", 30, caption="References"),
        _o("Paragraph", 31, text="Smith 2020 ..."),     # a ref-region para, excluded
    ]
    res = C.conclusion_text(objs)
    assert res["source"] == "section" and res["section"] == "Conclusion"
    assert res["paragraphs"] == ["We showed X on small examples.",
                                 "Future work will scale it."]


def test_medium_keyword_discussion_near_end():
    objs = [
        _o("Section", 5, caption="Introduction"),
        _o("Section", 40, caption="Discussion"),
        _o("Paragraph", 41, text="Discussion body."),
        _o("Section", 50, caption="References"),
    ]
    sec = C.find_conclusion_section(objs)
    assert sec is not None and sec.props["caption"] == "Discussion"


def test_fallback_to_final_paragraphs_no_conclusion_section():
    objs = [
        _o("Section", 1, caption="Introduction"),
        _o("Paragraph", 2, text="p1"),
        _o("Paragraph", 3, text="p2"),
        _o("Paragraph", 4, text="p3"),
        _o("Section", 5, caption="References"),
        _o("Paragraph", 6, text="ref tail"),       # excluded (after end boundary)
    ]
    res = C.conclusion_text(objs, final_n=2)
    assert res["source"] == "final_paragraphs"
    assert res["paragraphs"] == ["p2", "p3"]        # last 2 of the MAIN body


if __name__ == "__main__":
    for fn in [test_find_conclusion_section_strong_before_appendix,
               test_conclusion_text_collects_flow_range_paragraphs,
               test_medium_keyword_discussion_near_end,
               test_fallback_to_final_paragraphs_no_conclusion_section]:
        fn(); print("PASS", fn.__name__)
    print("\nAll tests passed.")
