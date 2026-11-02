r"""The free structure gate on a Markdown projection, and its denominator.

The owner audited d09.md by hand and found several errors per line from the
first content page: a chapter title split into three `#` headings above its own
`## Chapter 1`, section 1.1 continued by a `##` one level shallower than the
`###` it continues, and display equations emitted as `##` headings so the math
was neither isolated nor delimited. Their instruction was to stop finding this
by reading: "I am not need on check on this low level!"

Measured on that document (514 pages, pdf2mmd2's reading, `pdfdrill md`):
272 findings — E3 math-as-heading 128, E1 level-inversion 86, E2 heading-run
48, E4 continuation-heading 10 — with 18 of them on page 18 alone.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import mdstructure as S

# the shapes, taken verbatim from d09 section 1.1
D09_SECTION_1_1 = """\
## Chapter 1

# Interaction of a Charged Particle

# with Strong Plane Electromagnetic

# Wave in Vacuum

### 1.1 Classical Dynamics of a Particle in the Field

## of Strong Plane Electromagnetic Wave

The motion of a charged particle is described by
the relativistic equation

## p = p + e E(τ)dτ, (1.5)

where the field is transverse.
"""


def _kinds(text):
    return [f.kind for f in S.check(text)]


def test_a_display_equation_as_a_heading_is_found():
    f = [x for x in S.check(D09_SECTION_1_1) if x.kind == S.MATH_AS_HEADING]
    assert len(f) == 1, S.check(D09_SECTION_1_1)
    assert "(1.5)" in f[0].text


def test_a_continuation_one_level_shallower_is_an_inversion():
    """`### 1.1 …` then `## of Strong …` — the owner's "make no sense in a
    hierarchy"."""
    f = [x for x in S.check(D09_SECTION_1_1)
         if x.kind == S.LEVEL_INVERSION and x.text.startswith("of Strong")]
    assert f, _kinds(D09_SECTION_1_1)


def test_a_fragmented_title_is_found():
    """Three `#` lines for one chapter title, with no prose between them."""
    f = [x for x in S.check(D09_SECTION_1_1)
         if x.kind in (S.HEADING_RUN, S.CONTINUATION_HEADING, S.LEVEL_INVERSION)]
    assert len(f) >= 3, _kinds(D09_SECTION_1_1)


def test_one_line_one_error():
    """The classes overlap, so each offending line is counted once — otherwise
    the owner's < 1/page threshold counts one defect three times."""
    f = S.check(D09_SECTION_1_1)
    assert len(f) == len({x.line for x in f}), f


def test_a_sane_projection_has_no_findings():
    good = """\
# A Book

## Chapter 1

Some prose that follows the heading.

### 1.1 A Section

More prose here, and an isolated display equation:

$$p = p_0 + eE(\\tau)\\,d\\tau$$

Closing prose.
"""
    assert S.check(good) == [], S.check(good)


def test_prose_headings_are_not_mistaken_for_maths():
    """A title containing a number or an `=` in words must not count."""
    for t in ("# Chapter 2 Results", "## The Dirac Equation",
              "### 3.2 Scattering Cross Sections"):
        assert S.check(t + "\n\nprose\n") == [], t


def test_the_verdict_refuses_to_use_the_document_mean():
    """THE DENOMINATOR TRAP. The first version divided all errors by all pages:
    d09 scored 0.529/page and printed "PASSES" about the projection the owner
    had just condemned. Without a reading to attribute pages, there is no
    verdict — not a passing one."""
    f = S.check(D09_SECTION_1_1)
    out = S.summary(f, 514)                    # no reading
    assert "NO VERDICT" in out, out
    assert "PASSES" not in out, out


def test_the_verdict_turns_on_the_worst_page():
    reading = {"pages": [
        {"page": 7, "lines": [{"text": "Interaction of a Charged Particle"},
                              {"text": "with Strong Plane Electromagnetic"},
                              {"text": "Wave in Vacuum"},
                              {"text": "of Strong Plane Electromagnetic Wave"},
                              {"text": "p = p + e E(τ)dτ, (1.5)"}]},
        {"page": 8, "lines": [{"text": "unrelated prose"}]},
    ]}
    f = S.check(D09_SECTION_1_1)
    page, n = S.worst_page(f, reading)
    assert page == 7, (page, n)
    assert n >= 4, n
    out = S.summary(f, 514, reading)
    # BOTH numbers, each labelled for what it is. The rate is the owner's
    # stated bar ("below 1/page"); the worst page is the clustering signal that
    # the rate alone misses. Reporting the worst page AS the stated bar was a
    # mislabel — pdf2mmd2's d08 is 0.012/page and would "fail" on one error in
    # 347 pages — so the summary states both and claims no combined verdict
    # until the owner sets one.
    assert "page 7" in out, out
    assert "Worst single page" in out, out
    assert "/page" in out, out


def test_a_clean_page_passes_with_a_reading():
    reading = {"pages": [{"page": 1, "lines": [{"text": "A Book"}]}]}
    out = S.summary([], 1, reading)
    assert "0 errors" in out and "passes" in out.lower(), out


def test_a_repeated_heading_is_not_piled_onto_one_page():
    """pdf2mmd2 found this: keeping only the FIRST page a text occurs on put all
    three `# Bibliography` headings of d09 — the ends of three chapters — on
    page 49, inflating it to 4 errors where it carries 2. The verdict turns on
    the worst page, so an inflated page is a false FAIL, as bad as the false
    PASS the document mean gave. The k-th occurrence belongs to the k-th page."""
    md = """\
# Bibliography

# Trailing

## Bibliography

## Trailing
"""
    reading = {"pages": [
        {"page": 10, "lines": [{"text": "Bibliography"}, {"text": "Trailing"}]},
        {"page": 20, "lines": [{"text": "Bibliography"}, {"text": "Trailing"}]},
    ]}
    f = S.check(md)
    assert f, "the fixture should produce findings"
    by = S.attribute(f, reading)
    placed = {k: v for k, v in by.items() if k is not None}
    assert set(placed) == {10, 20}, placed
    assert all(len(v) <= 2 for v in placed.values()), placed


def test_more_occurrences_than_the_reading_has_do_not_wrap_to_the_first():
    """A projection can repeat a text more often than the reading does. Those
    extras attribute to the LAST page carrying it, never back to the first —
    wrapping would re-inflate an early page."""
    md = "# A\n\n# B\n\n## A\n\n## B\n\n### A\n\n### B\n"
    reading = {"pages": [{"page": 5, "lines": [{"text": "A"}, {"text": "B"}]}]}
    by = S.attribute(S.check(md), reading)
    assert set(k for k in by if k is not None) == {5}, by


def test_a_numbered_exercise_heading_is_not_an_equation():
    """`## 8.2 Verify equation (8.27).` cites an equation; it is not one. The
    first bound ("a numbered line with <= 2 prose words") flagged it, and
    pdf2mmd2's d04 rose by one error after a genuine fix because of this rule —
    which they booked against themselves until it was traced here."""
    for t in ("8.2 Verify equation (8.27).",
              "8.3 Show that the cross section is given by (8.31).",
              "3.4 Derive (3.12) from (3.9)."):
        assert not S._is_math(t), t


def test_a_numbered_line_with_no_prose_is_still_an_equation():
    """The case the bound exists for: symbols and an equation number, no words."""
    for t in ("∇ × B , (3.4)", "(1.20)", "p = p + e E(τ)dτ, (1.5)"):
        assert S._is_math(t), t


def test_the_histogram_buckets_and_keeps_unplaced_separate():
    """The distribution is what a per-page cap must be set from, and an
    unplaceable finding must never be counted as a clean page: on one measured
    document 135 of 254 findings could not be placed."""
    md = "# A\n\n# B\n\n# Nowhere\n"
    reading = {"pages": [{"page": 1, "lines": [{"text": "A"}, {"text": "B"}]}]}
    f = S.check(md)
    h = S.histogram(f, reading, page_count=10)
    assert h["unplaced"] >= 1, h
    assert h["p0"] == 9, h            # 10 pages, 1 carries findings
    assert h["p1"] + h["p2"] + h["p3+"] == 1, h


def test_the_summary_carries_the_distribution():
    reading = {"pages": [{"page": 7, "lines": [
        {"text": "Interaction of a Charged Particle"},
        {"text": "with Strong Plane Electromagnetic"},
        {"text": "Wave in Vacuum"}]}]}
    out = S.summary(S.check(D09_SECTION_1_1), 514, reading)
    assert "clean" in out and "with 1" in out and "unplaceable" in out, out
