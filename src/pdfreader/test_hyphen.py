"""Tests for rejoining words the typesetter broke across a line.

Measured against pdftotext on one paper: 138 words left broken here, 0 there.
"""
import project_mmd as M


class TestDehyphenate:
    def test_a_broken_word_is_rejoined(self):
        assert M.dehyphenate("sci-\nentific", set()) == "scientific"

    def test_a_real_compound_keeps_its_hyphen(self):
        """The evidence is the HYPHENATED form used mid-line, where no line
        break forced it: `top-left` and `web-based` appear that way,
        `compara-ble` and `iden-tify` do not."""
        vocab = {"web-based"}
        assert M.dehyphenate("web-\nbased", vocab) == "web-\nbased"

    def test_evidence_is_read_from_the_document(self):
        text = "a top-left corner and the top-\nleft edge"
        vocab = M._vocabulary(text)
        assert "top-left" in vocab
        assert M.dehyphenate(text, vocab).count("top-\nleft") == 1

    def test_a_line_break_hyphen_is_not_evidence(self):
        """A hyphen the typesetter inserted never appears mid-line."""
        assert "sci-entific" not in M._vocabulary("sci-\nentific nature")

    def test_ligatures_are_letters(self):
        """`difﬁ-cult` breaks after U+FB01; spelling the class as A-Za-z
        missed 31 such words."""
        assert M.dehyphenate("dif\ufb01-\ncult", set()) == "dif\ufb01cult"

    def test_a_join_that_ends_in_a_hyphen_is_retested(self):
        """A join can produce a line that ITSELF ends in a hyphen, because
        the line it absorbed ended in one. Appending straight away left 25
        words broken."""
        assert (M.dehyphenate("neigh-\nbor meth-\nod", set())
                == "neighbor method")

    def test_uppercase_after_the_break_is_not_joined(self):
        assert M.dehyphenate("end-\nNew", set()) == "end-\nNew"

    def test_a_soft_hyphen_counts(self):
        assert M.dehyphenate("sci\u00ad\nentific", set()) == "scientific"

    def test_text_without_hyphens_is_unchanged(self):
        t = "one\ntwo\nthree"
        assert M.dehyphenate(t, set()) == t

    def test_it_can_be_turned_off(self):
        import docmodel_six as D
        page = D.PageNode(page=1, rect=(0, 0, 612, 792))
        assert M.to_markdown([page], join_hyphens=False) is not None
