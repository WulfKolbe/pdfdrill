r"""A reference carries the link we already hold.

T-0156, the owner's THIRD requirement. The model holds the links: of 256
References across the eight audit e-prints, 89 carry a full `bibtex` record,
41 of those hold a DOI, 2 a url and 2 an eprint. None of it reached the page —
256 printed entries carried no link of any kind, and both compiled PDFs held
ZERO external URI annotations.

`\url`, NOT `\href{…}{doi:…}`, AND THE DIFFERENCE WAS MEASURED. Adding
`\href{https://doi.org/X}{doi:X}` to 40 entries of arxiv.2402.03975 took its
error count 43 -> 55: a DOI like `10.1007/978-3-642-22006-7_13` puts an
underscore in the DISPLAYED text, and each one is "Missing $ inserted". The
same 40 entries with `\url` give 40 links and leave the errors at 43. The
naive form is the one I would have written without running the experiment.

The `.bib` is not the mechanism and is not replaced. `_bibitem`'s own reason
stands: a `.bib` needs a two-pass bibtex compile, so the self-contained
`thebibliography` is the default, and `bib_database` keeps writing the
database beside it.
"""
import pytest

from docops.projectors.latex_pipeline import _bibitem, reference_link


class _Ref:
    def __init__(self, **props):
        self.props = props


def test_a_doi_becomes_a_resolver_link():
    r = _Ref(bibtex="@article{k, doi = {10.1007/978-3-642-22006-7_13}}")
    assert reference_link(r) == \
        "\\url{https://doi.org/10.1007/978-3-642-22006-7_13}"


def test_the_underscore_that_broke_the_naive_form_is_carried_safely():
    """`\\href{…}{doi:…X_13}` is "Missing $ inserted"; `\\url` is not."""
    link = reference_link(_Ref(bibtex="@a{k, doi={10.1007/978-3-642-22006-7_13}}"))
    assert link.startswith("\\url{")
    assert "_13" in link            # carried verbatim, not escaped away
    assert "doi:" not in link       # no displayed text to break


def test_an_explicit_url_is_used_when_there_is_no_doi():
    assert reference_link(_Ref(bibtex="@misc{k, url = {https://example.org/a_b}}")) \
        == "\\url{https://example.org/a_b}"


def test_an_arxiv_eprint_becomes_an_abs_link():
    assert reference_link(_Ref(bibtex="@misc{k, eprint = {2402.03975}}")) == \
        "\\url{https://arxiv.org/abs/2402.03975}"


def test_the_doi_wins_over_the_others():
    r = _Ref(bibtex="@a{k, doi={10.1/x}, url={https://e.org/y}, eprint={1234}}")
    assert reference_link(r) == "\\url{https://doi.org/10.1/x}"


def test_a_stub_gets_no_link():
    """A stub is a cited key with nothing behind it — 41 of the 256. A link
    would make it read as a resolved entry."""
    r = _Ref(stub=True, bibtex="@a{k, doi={10.1/x}}")
    assert reference_link(r) == ""


@pytest.mark.parametrize("record", ["", "@a{k, title={No link here}}",
                                    "@misc{k, url = {not-a-url}}",
                                    "@a{k, doi = {}}"])
def test_nothing_to_link_means_no_link(record):
    assert reference_link(_Ref(bibtex=record)) == ""


def test_a_reference_with_no_record_at_all():
    assert reference_link(_Ref()) == ""


def test_the_bibitem_carries_the_link():
    r = _Ref(citekey="smith2020", author="Smith", year="2020",
             title="A paper", bibtex="@a{smith2020, doi={10.1/x}}")
    out = _bibitem(r)
    assert out.startswith("\\bibitem{smith2020}")
    assert "Smith" in out and "2020" in out
    assert out.endswith("\\url{https://doi.org/10.1/x}")


def test_a_bibitem_without_a_link_is_unchanged_in_shape():
    r = _Ref(citekey="smith2020", author="Smith", year="2020", title="A paper")
    out = _bibitem(r)
    assert out == "\\bibitem{smith2020} Smith (2020) A paper"


def test_a_stub_bibitem_stays_visibly_unresolved():
    out = _bibitem(_Ref(citekey="ghost", stub=True,
                        bibtex="@a{ghost, doi={10.1/x}}"))
    assert "unresolved" in out
    assert "url" not in out
