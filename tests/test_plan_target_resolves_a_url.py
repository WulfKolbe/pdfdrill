r"""D3 — a URL or a bare id names a document the planner can already find.

THE DEFECT (measured 2026-11-10 on arxiv.2209.02970)
----------------------------------------------------
`--ensure` plans against `cli.plan_target(pdf_arg)`. For a URL that returned
the token itself, and `Path("https://arxiv.org/pdf/2209.02970")` collapses to
`https:/arxiv.org/pdf/2209.02970`, which does not exist. Every `done_when` then
resolves against a path that is not there, so nothing looks done:

    plan_target(url)                 -> https:/arxiv.org/pdf/2209.02970  (absent)
    resolve_steps("md", that)        -> ['model', 'md']
    resolve_steps("md", the real pdf)-> ['md']

So `--ensure` re-ran `model` on a document whose model was sixty seconds old,
and `pdfdrill steps md <url>` — which resolves the argument properly — printed
"prerequisites satisfied" about the same document in the same minute. Two
planners, one document, two answers.

This is rule 896 one case short. 896 fixed the FOLDER and BARE-LIBRARY-NAME
forms, which is what drillui used then; drillui's `add <url>` stores the URL, so
every later command in that session carried the one spelling still unresolved.

WHAT THE FIX MAY NOT DO
-----------------------
`plan_target` is documented "LOCAL lookups only ... planning must not acquire
anything". Resolving a URL must therefore stay a lookup: map the URL to the
name the archive document ALREADY has on disk (`sources.archive_stem`) and ask
the library. A URL for a document not yet fetched still answers with the token,
unresolved, because there is genuinely no plan to compute until it is fetched —
and no test here may let a download happen.
"""
import json
from pathlib import Path

import pytest

from pdfdrill import cli, planner, sources


# A real arXiv id shape: YYMM.NNNNN, and the MM must be a month —
# `1234.56789` is rejected by `arxiv_id_shape_error` (month 34), which is
# the right answer and made a first draft of this fixture meaningless.
ARXIV_ID = "2301.09999"
STEM = f"arxiv.{ARXIV_ID}"


@pytest.fixture
def library(tmp_path, monkeypatch):
    """A library holding ONE already-fetched arXiv document, and a guarantee
    that nothing in this module reaches the network."""
    root = tmp_path / "lib"
    doc = root / STEM
    doc.mkdir(parents=True)
    pdf = doc / f"{STEM}.pdf"
    pdf.write_bytes(b"%PDF-1.5\n%%EOF\n")

    from pdfdrill import config
    monkeypatch.setattr(config, "library_root", lambda: root)

    def no_network(*a, **k):                     # noqa: ANN002
        raise AssertionError("planning must not acquire anything")
    from pdfdrill import net
    monkeypatch.setattr(net, "urlopen", no_network)
    return pdf


@pytest.mark.parametrize("arg", [
    f"https://arxiv.org/pdf/{ARXIV_ID}",         # the form drillui's `add` stores
    f"https://arxiv.org/abs/{ARXIV_ID}",
    f"https://arxiv.org/pdf/{ARXIV_ID}.pdf",
    f"arXiv:{ARXIV_ID}",
    ARXIV_ID,                                    # already worked; pinned so it keeps working
    STEM,                                        # ditto, the bare library name (rule 896)
])
def test_every_spelling_of_one_document_plans_against_that_document(arg, library):
    """One document, six spellings, one plan. The URL forms are the ones that
    returned a non-existent path and made every `done_when` read as not-done."""
    assert cli.plan_target(arg) == library


def test_the_url_form_is_not_turned_into_a_bogus_path(library):
    got = cli.plan_target(f"https://arxiv.org/pdf/{ARXIV_ID}")
    assert got.exists(), f"plan_target returned {got}, which does not exist"
    assert "https:" not in str(got)


def test_the_plan_is_the_documents_plan_not_the_tokens(library, monkeypatch):
    """The consequence the owner felt: the same document must not need `model`
    when its model is already there. Measured before the fix as
    ['model','md'] for the URL and ['md'] for the file."""
    # a model on disk is what `done_when: model` looks for
    (library.parent / "model.docmodel.json").write_text(json.dumps({"objects": {}}))
    by_file, _ = planner.resolve_steps("md", library)
    by_url, _ = planner.resolve_steps("md", cli.plan_target(
        f"https://arxiv.org/pdf/{ARXIV_ID}"))
    assert by_url == by_file, (
        f"the URL plans {by_url} and the file plans {by_file} for one document")


def test_a_document_not_in_the_library_stays_unresolved(library):
    """A URL for something never fetched has no plan to compute, and resolving
    it must not be attempted by fetching it. The token comes back as before."""
    arg = "https://arxiv.org/pdf/2302.09998"
    got = cli.plan_target(arg)
    assert not got.exists()
    assert str(got).endswith("2302.09998")


def test_a_non_arxiv_url_is_not_mistaken_for_an_arxiv_document(library):
    """`parse_arxiv_id` must not fire on another host's URL that happens to
    carry digits — the viXra case rule 806 already closed one level down."""
    arg = "https://pmc.ncbi.nlm.nih.gov/articles/PMC9975443/pdf/221_2023_Article_6580.pdf"
    assert cli.plan_target(arg) != library


def test_the_resolution_is_a_lookup_and_never_a_download(library):
    """The fixture fails the test if `net.urlopen` is touched. Pinned as its own
    test so the guarantee is named, not merely a side effect of the fixture."""
    for arg in (f"https://arxiv.org/pdf/{ARXIV_ID}", "https://arxiv.org/pdf/2302.09998"):
        cli.plan_target(arg)                     # must not raise


def test_archive_stem_is_the_naming_this_relies_on():
    """`plan_target` maps a URL to the name the document has ON DISK. If that
    naming ever changes, this test says so here rather than letting the planner
    silently stop finding documents."""
    assert sources.archive_stem("arxiv", ARXIV_ID) == STEM
    assert sources.parse_arxiv_id(f"https://arxiv.org/pdf/{ARXIV_ID}") == ARXIV_ID
