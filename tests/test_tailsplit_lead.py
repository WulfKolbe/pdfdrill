"""095 — text_tail strips trailing commentary only, and only after maths."""
from pdfdrill.mathqc import text_tail

PACK = (r"\text { Pack }_{<\omega} \text {-complete } \text { Rr } "
        r"\text { Pack }_{2} \text {-complete. }")


def test_a_leading_run_is_never_stripped():
    """out/093: removing `\\text{ Pack }` leaves `_{<\\omega}`, which is not a
    smaller expression — it is not an expression."""
    lead, _trail = text_tail(PACK)
    assert lead is None


def test_a_sentence_keeps_its_trailing_run_too():
    """The whole line is prose. Its final run is part of the sentence, not a
    comment on an expression, so nothing is split off."""
    assert text_tail(PACK)[1] is None


def test_maths_followed_by_prose_still_splits():
    """The behaviour text_tail exists for must survive the restriction."""
    _l, trail = text_tail(r"x^{2}+y^{2}=z^{2} \text { where } n \text { is even }")
    assert trail and "is even" in trail


def test_a_line_opening_with_mathrm_is_prose_too():
    """\\mathrm is the same shape as \\text here: `\\mathrm{d}x` opens with a
    prose run by this test, and that is the conservative direction."""
    assert text_tail(r"\mathrm{d}x \text { with respect to time }")[1] is None


def test_the_opening_token_decides_not_the_residue():
    """Judging on what survives after removing the \\text{} groups admits a
    lone subscript — `_{2}` leaves the string "2", which reads as mathematics
    and is not. The opening token is the test."""
    lead, trail = text_tail(r"\text { pack }_{2} \text {-complete. }")
    assert lead is None and trail is None
