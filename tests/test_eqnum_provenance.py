"""A derived prop must record the stream span it came from.

The invariant the drillcheck audit proposed, in its words: for every DocObject
prop derived from stream text, either the prop is byte-identical to the span, or
an Alignment records the span it came from. Everything measured passed except
`equation_number`, which is a destructively-rewritten copy with nothing pointing
back — and it is the only field that was corrupted, because nothing could
recover the input once the rewrite went wrong.

`eqnums` did build an `Alignment(kind="equation_number")`, but only in the
geometry-recovery branch. The MathPix branch — 58 of 61 equations on this thesis
— set the prop and returned. The number's anchor was known at pairing time and
thrown away.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.modules.equation import EquationProcessor as EP


class _Stream:
    def __init__(self, payload):
        self.payload = payload


def _page(items):
    payload, anchors = {}, []
    for i, (typ, y, text) in enumerate(items):
        a = f"a{i}"
        payload[a] = {"type": typ, "text": text, "_page": 1,
                      "region": {"top_left_y": y, "height": 10}}
        anchors.append(a)
    return anchors, _Stream(payload)


def test_pairing_reports_the_anchor_the_number_came_from():
    """Without the anchor there is nothing to point an Alignment at, and the
    rewritten string becomes the only record of the input."""
    anchors, stream = _page([
        ("math", 100, "a=b"), ("equation_number", 105, r"\((2.5)\)"),
    ])
    ep = EP.__new__(EP)
    paired = ep._match_equation_numbers(anchors, stream)
    assert paired == {"a0": ("2.5", "a1")}, paired


def test_the_anchor_is_the_nearest_number_not_merely_the_first():
    anchors, stream = _page([
        ("equation_number", 10, "(1.1)"),
        ("math", 300, "a=b"),
        ("equation_number", 305, "(9.9)"),
    ])
    ep = EP.__new__(EP)
    assert ep._match_equation_numbers(anchors, stream)["a1"] == ("9.9", "a2")


def test_the_equation_carries_the_anchor_into_its_props():
    """So `eqnums` can attach the Alignment without re-deriving the pairing."""
    import inspect
    src = inspect.getsource(EP)
    assert "refnum_anchor" in src


def test_eqnums_records_an_alignment_for_a_mathpix_number():
    import inspect
    from pdfdrill import eqnums
    body = inspect.getsource(eqnums.fuse_equation_numbers)
    mathpix_branch = body.split("region = o.props.get")[0]
    assert "equation_number" in mathpix_branch and "Alignment" in mathpix_branch, \
        "the MathPix branch still records no provenance for the number"


def test_the_anchor_is_stored_as_an_id_string_not_an_object():
    """props are serialised to JSON: an Anchor object round-trips as its repr
    (`Anchor(a_abfd…)`), which then matches no anchor at all."""
    class _A:
        def __init__(self, i): self.id = i
        def __repr__(self): return f"Anchor({self.id})"
    payload = {_A("e1"): {"type": "math", "text": "a=b", "_page": 1,
                          "region": {"top_left_y": 100, "height": 10}},
               _A("n1"): {"type": "equation_number", "text": "(2.4)", "_page": 1,
                          "region": {"top_left_y": 105, "height": 10}}}
    anchors = list(payload)
    ep = EP.__new__(EP)
    out = ep._match_equation_numbers(anchors, _Stream(payload))
    (_num, anchor_id), = out.values()
    assert isinstance(anchor_id, str) and anchor_id == "n1", anchor_id
