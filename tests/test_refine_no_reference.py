"""T-0024 items 2 and 3 — half a comparison is not a comparison.

`select` writes `ink_before` (the distance from the scan to the reading
already in the model) only for the rows its own ink gate reached. `measure`
writes `ink_after` for every validated row, gated or not. So a row can arrive
with one half of a comparison, and before this:

  * `accept` evaluated `after < before` on it — `int < None`, a TypeError.
    The run ended there, which is BEFORE `record`, so proposals that had
    already been accepted and verified were never attached to the model.
  * `measure` wrote `after - (before or 0)`, which is `after`: a positive
    delta that reads as a proposal that worsened the reading by exactly its
    own distance from the scan. And it counted the row as measured.

A row with no reference is neither accepted nor rejected: nothing about it has
been found wanting. It is counted as what it is and left proposed, so a later
run that gates it can still decide.
"""
from __future__ import annotations

import pytest

from pdfdrill import refine as rf


# ── the verdict ────────────────────────────────────────────────────────────

def test_a_closer_proposal_is_accepted():
    assert rf.ink_verdict(40, 12) == rf.ACCEPTED


def test_an_equal_or_worse_proposal_is_no_improvement():
    assert rf.ink_verdict(12, 12) == rf.NO_IMPROVEMENT
    assert rf.ink_verdict(12, 40) == rf.NO_IMPROVEMENT


def test_a_missing_reference_does_not_raise():
    """The TypeError this closes: `12 < None`."""
    assert rf.ink_verdict(None, 12) == rf.NO_REFERENCE


def test_a_missing_reference_is_not_a_rejection():
    assert rf.ink_verdict(None, 12) != rf.NO_IMPROVEMENT


def test_a_missing_measurement_is_also_no_reference():
    assert rf.ink_verdict(40, None) == rf.NO_REFERENCE
    assert rf.ink_verdict(None, None) == rf.NO_REFERENCE


def test_zero_is_a_reference_not_an_absence():
    """A proposal that matches the scan exactly has `ink_after` 0, and a
    reading that already matched has `ink_before` 0. Falsy, both of them."""
    assert rf.ink_verdict(0, 0) == rf.NO_IMPROVEMENT
    assert rf.ink_verdict(5, 0) == rf.ACCEPTED
    assert rf.ink_verdict(0, 5) == rf.NO_IMPROVEMENT


# ── the delta ──────────────────────────────────────────────────────────────

def test_delta_is_the_improvement_as_a_negative_number():
    assert rf.ink_delta(40, 12) == -28


def test_delta_without_a_reference_is_absent_not_the_whole_distance():
    """`after - (before or 0)` gave 12 here: a measurement nobody made."""
    assert rf.ink_delta(None, 12) is None


def test_delta_of_zero_against_zero_is_zero_not_none():
    assert rf.ink_delta(0, 0) == 0


@pytest.mark.parametrize("before,after", [(0, 7), (7, 0)])
def test_a_falsy_half_still_yields_a_delta(before, after):
    assert rf.ink_delta(before, after) == after - before
