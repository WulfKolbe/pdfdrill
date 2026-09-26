"""An arXiv id's digit count is a function of its own date — 804.

The scheme ran `YYMM.NNNN` from 0704 to 1412 and `YYMM.NNNNN` from 1501 on. Our
regex was `\\d{4}\\.\\d{4,5}` for every month, so a TRUNCATED modern id passed —
and arXiv does not refuse such a request, it ZERO-PADS it:

    asked for  2609.2497   -> served 2609.02497
                              "RINSE: Robust Target-Time Normality Estimation …"
    wanted     2609.24972  -> "RRSI: Regularized Recursive Self-Improvement …"

One dropped character, a different real paper, no error at either end, and a
library folder whose name stated an id its contents did not have. Every later
command believed the name. Both titles above were fetched from arxiv.org to
confirm the mechanism rather than assume it.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.sources import arxiv_id_shape_error, bare_arxiv_id, parse_arxiv_id


@pytest.mark.parametrize("aid", [
    "0704.0001", "1412.1234", "1501.00001", "2609.24972", "2609.24972v2",
    "arXiv:2609.24972", "2609.24972.pdf",
])
def test_a_well_formed_id_is_accepted(aid):
    assert arxiv_id_shape_error(aid) is None
    assert bare_arxiv_id(aid)


@pytest.mark.parametrize("aid,why", [
    ("2609.2497", "five digits from 1501 on"),
    ("1501.1234", "five digits from 1501 on"),
    ("1412.12345", "four digits up to 1412"),
    ("2613.00001", "month 13"),
    ("0703.0001", "the scheme starts at 0704"),
])
def test_a_malformed_id_is_refused_and_says_why(aid, why):
    err = arxiv_id_shape_error(aid)
    assert err, f"{aid} was accepted ({why})"
    assert aid in err


@pytest.mark.parametrize("aid", ["2609.2497", "1501.1234", "1412.12345"])
def test_nothing_malformed_reaches_a_download(aid):
    """THE POINT. `bare_arxiv_id` returning None is what stops the fetch, and
    a wrong paper served at HTTP 200 is worse than any refusal."""
    assert bare_arxiv_id(aid) is None


def test_an_old_style_id_is_untouched():
    """`math/0309136` predates the scheme this checks and must pass through."""
    assert arxiv_id_shape_error("math/0309136") is None
    assert bare_arxiv_id("math/0309136") == "math/0309136"


def test_a_non_id_says_nothing():
    """A check that volunteers an opinion about every string is noise."""
    for s in ("", "Zwiebeln", "notes.pdf", "https://example.com/x.pdf"):
        assert arxiv_id_shape_error(s) is None


def test_a_url_carrying_a_malformed_id_is_not_silently_fixed():
    """`parse_arxiv_id` reads any spelling, including a URL. A URL is not a
    licence to zero-pad either."""
    assert parse_arxiv_id("https://arxiv.org/abs/2609.24972") == "2609.24972"


def test_a_four_digit_id_after_2015_names_vixra():
    """A FOUR-DIGIT ID AFTER 2015 IS PROBABLY NOT A TYPO. viXra numbers every
    year `YYMM.NNNN`, which is arXiv's PRE-2015 shape, so the two schemes
    collide for exactly these ids.

    Fourteen folders in the measured library are viXra e-prints named correctly
    for their source — verified against vixra.org, titles matching, including
    `1506.0005` "A New Method for High-Resolution Frequency Measurements" and
    `2306.0024` "Location and Radius of a Triangle's Incircle Via Geometric
    Algebra". Telling their owner to "check the id" is advice about the wrong
    archive.
    """
    err = arxiv_id_shape_error("2505.0100v1")
    assert "viXra" in err and "vixra.org" in err
    assert "no viXra route" in err


def test_the_other_direction_is_still_read_as_a_typo():
    """Five digits BEFORE 2015 has no second archive behind it."""
    err = arxiv_id_shape_error("1412.12345")
    assert "viXra" not in err
    assert "Check the id against its listing." in err
