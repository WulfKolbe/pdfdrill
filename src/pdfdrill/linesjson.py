r"""The shape of a reading's page list, where more than one scan reads it.

T-0154. A `lines.json` is `{"pages": [...]}` and each page states its own
number in `"page"`. Everything that ingests a reading already reads that field
(`docmodel`'s `ingest_lines_json`, drillgroup's `pagecheck`); two scans in this
package did not, and numbered the pages by their POSITION in the list instead.

The two agree exactly as long as the reading holds every page. They stop
agreeing the moment one is missing -- a reader that skipped a page, a reading
cut to a range, an older reading -- and then every page after the gap is
reported one too low, silently, in a number that is later used to crop that
page out of the PDF.

So the rule lives in one place: a STATED page number wins; position is the
fallback for a reading that states none, which hand-made readings and several
of this suite's fixtures do.
"""
from __future__ import annotations


def page_number(page: dict, position: int) -> int:
    """The number this page states, or `position` when it states none.

    `position` is 1-based. A value that is not a page number -- `null`, a
    string, 0, a negative -- states nothing, so it falls back rather than
    propagating: the same shape as the `px_per_pt` that is present on every
    page of the corpus with the value `null` (73188fe9).

    `True` is an int in Python and would otherwise pass as page 1; a reading
    that says `"page": true` has not stated a page.
    """
    n = (page or {}).get("page")
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        return position
    return n
