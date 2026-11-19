r"""The ratchet's paragraph counter, and its one known false positive.

`mid_sentence` -- a paragraph beginning lower-case after one that did not end
in sentence punctuation -- is the fault the owner sees on a page. On
2312.11532 p7 it also catches eight topic word lists, which are not faults:

    spacecraft, orbit, module, capsule, endeavour
    bank, investment, firm, supervisory, stock
    senate, legislation, republican, procedural, congress

They begin lower-case because they are lists. Counted as faults they made
5a3b3977 look like a regression of +8 on that document when its genuine count
was unchanged at 30.

So a word list is defined, counted apart, and tested BOTH WAYS: the list is
excluded AND a lower-case continuation of prose is still counted. The
definition is fixed here before the next document is looked at --
three or more comma-separated items, each of at most two words, no sentence
punctuation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.paracount import counts, is_word_list  # noqa: E402


def test_the_eight_topic_lists_of_2312_11532_are_word_lists():
    for t in ("spacecraft, orbit, module, capsule, endeavour",
              "bank, investment, firm, supervisory, stock",
              "waterfront, marina, park, center, downtown",
              "senate, legislation, republican, procedural, congress",
              "japan, Japanese, tokyo, hokkaido, fuji",
              "school, kindergarten, mathematics, education, elementary",
              "gubernatorial, campaign, democratic, race, election",
              "military, american, pentagon, command, force"):
        assert is_word_list(t) is True, t


def test_a_sentence_with_commas_is_not_a_word_list():
    """The other way round, which is what stops the exclusion hiding faults."""
    assert is_word_list(
        "values were used, and also the ones with the lowest number") is False
    assert is_word_list("mains: (1) document clustering, tackled by the") is False
    assert is_word_list("as generative and non-generative models, as: LDA") is False


def test_two_items_are_not_a_list():
    assert is_word_list("bank, investment") is False


def test_items_of_three_words_are_not_a_list():
    assert is_word_list("the quick brown, a lazy dog, one more thing") is False


def test_a_lower_case_continuation_of_prose_is_still_counted():
    c = counts(["A sentence that runs on",
                "and continues here in the next paragraph"])
    assert c["mid_sentence"] == 1, c
    assert c["word_lists"] == 0, c


def test_a_word_list_after_a_paragraph_is_not_counted_as_a_fault():
    c = counts(["Topics discovered by the model",
                "spacecraft, orbit, module, capsule, endeavour"])
    assert c["mid_sentence"] == 0, c
    assert c["word_lists"] == 1, c


def test_a_paragraph_after_a_full_stop_is_never_a_fault():
    c = counts(["A sentence that ends properly.",
                "and this begins lower-case but follows a full stop"])
    assert c["mid_sentence"] == 0, c


def test_a_fragment_is_counted_and_has_no_false_positives():
    c = counts(["A real paragraph here.", "x", "ρ"])
    assert c["fragments"] == 2, c
    assert c["paragraphs"] == 3, c
