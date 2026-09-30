"""814 — the run-in heading, and the bold face URW called "Medium"."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import texmap                                              # noqa: E402


# ── the bold face nobody recognised ──────────────────────────────────────────

@pytest.mark.parametrize("face", [
    # `\textbf` under times/mathptmx resolves to ptmb, which embeds as this.
    # pdfLaTeX's default Times substitute: 480 readings in 380 corpus documents.
    "NimbusRomNo9L-Medi",
    "NimbusRomNo9L-MediItal",
    "NimbusSan-Bol",             # a truncated `-Bold`
    # unchanged
    "CharisSIL-Bold", "CMBX12", "Times-Bold", "NimbusSanL-Bold",
    "URWPalladioL-Bold", "NimbusMonL-Bold",
])
def test_is_bold(face):
    assert texmap.is_bold(face)


@pytest.mark.parametrize("face", [
    "NimbusRomNo9L-Regu", "NimbusRomNo9L-ReguItal", "NimbusSanL-Regu",
    "CharisSIL", "CharisSIL-Italic",
    # A BLANKET `medium` rule would have caught all of these, and none is bold.
    # `NimbusSanL` and `NimbusMonL` spell their own bold `-Bold`, which is why
    # the rule is scoped to the NimbusRomNo9L family.
    "NunitoExtraLight-Medium", "Flama-Ultralight", "HelveticaNeue-Medium",
    "Avenir-Medium", "PingFangSC-Medium", "GoogleSymbolsRounded-Medium",
])
def test_is_not_bold(face):
    assert not texmap.is_bold(face)


# ── the run-in heading ───────────────────────────────────────────────────────

BODY = 10.0


class _G:
    """A glyph: enough of GlyphNode for the detector."""
    def __init__(self, text, x0, x1, bold, size=BODY, math=False):
        self.text, self.rect = text, (x0, 0.0, x1, size)
        self.fontname = "ABCDEF+NimbusRomNo9L-" + ("Medi" if bold else "Regu")
        self.size, self.is_math = size, math
        self.tex = type("T", (), {"latex": None})()
        self.glyphname = text
        self.id = text


class _Line:
    def __init__(self, glyphs):
        self.glyphs, self.rotated, self.type = glyphs, False, "text"
        self.rect = (glyphs[0].rect[0], 0.0, glyphs[-1].rect[2], BODY)
        self.spans, self.rules = [], []


class _FP:
    """Font profile: rank 0 is body size."""
    def rank(self, size):
        return 0 if abs(size - BODY) < 0.3 else 1

    def clearly_larger(self, size):
        return size > BODY * 1.2


def _mk(head, rest, sep=10.0, advance=5.0, bold_rest=False, size=BODY):
    """Lay a line out: `head` bold, then a `sep` gap, then `rest`."""
    gl, x = [], 0.0
    for ch in head:
        gl.append(_G(ch, x, x + advance, True, size)); x += advance
    x += sep
    for ch in rest:
        gl.append(_G(ch, x, x + advance, bold_rest, size)); x += advance
    return _Line(gl)


def _split(line):
    import project_mmd as P
    return P.runin_heading(line, _FP())


def test_the_reported_case():
    """`**Analysis: Finance Benchmark** As shown in Table 2, ACE delivers …`
    Measured on 2510.04618: the separator is 9.96pt at a 10.0pt body size
    (1.00 em) while the ordinary inter-glyph gap has median 2.75pt (0.37 em)."""
    ln = _mk("Analysis: Finance Benchmark", "As shown in Table 2, ACE delivers")
    assert _split(ln) == len("Analysis: Finance Benchmark")


def test_a_gap_no_wider_than_a_word_space_is_not_a_run_in():
    """This is the whole discriminator. Without it, any sentence opening with a
    bold clause becomes a heading."""
    assert _split(_mk("Some bold words", "and then the prose", sep=2.75)) == 0


def test_the_gap_scales_with_the_font_not_an_absolute_constant():
    small = _mk("Heading here", "and the prose follows", sep=4.0, size=6.0)
    assert _split(small) == 0            # rank != 0 for 6.0 under this profile
    big = _mk("Heading here", "and the prose follows", sep=4.0)
    assert _split(big) == 0              # 4.0pt < 0.6 * 10.0


def test_an_all_bold_line_is_an_ordinary_heading_not_a_run_in():
    """`heading_level` ranks a fully bold line; claiming it here would flatten
    every such heading to level 4."""
    assert _split(_mk("A whole bold heading", "still bold", bold_rest=True)) == 0


def test_a_bold_sentence_ending_in_a_full_stop_is_not_a_heading():
    assert _split(_mk("This is a bold sentence.", "And another one here")) == 0


def test_a_heading_ending_in_a_colon_is_still_a_heading():
    ln = _mk("Key Instructions:", "read the playbook first and then act")
    assert _split(ln) == len("Key Instructions:")


def test_a_bold_run_too_long_to_be_a_label_is_emphasis():
    head = "x" * 70
    assert _split(_mk(head, "and the prose continues here")) == 0


def test_a_bold_label_with_only_a_word_after_it_is_not_a_heading():
    assert _split(_mk("Fig. 2.", "Compression")) == 0


def test_a_line_with_no_bold_prefix_is_untouched():
    ln = _mk("", "ordinary prose all the way across")
    assert _split(ln) == 0


# ── it reaches the lines.json as two lines ───────────────────────────────────

@pytest.mark.skipif(not Path("/home/wkolbe/pdfdrill-library/2510.04618/"
                             "2510.04618.pdf").is_file(),
                    reason="corpus document not present")
def test_the_split_reaches_the_lines_json_with_its_own_rectangle():
    import docmodel_six as dm
    pages = dm.build("/home/wkolbe/pdfdrill-library/2510.04618/2510.04618.pdf")
    d = dm.to_lines_json(pages, doc_id="t")
    lvl4 = [(p["page"], i, l) for p in d["pages"]
            for i, l in enumerate(p["lines"])
            if l["type"] == "section_header" and l.get("level") == 4]
    assert len(lvl4) >= 20
    texts = {l["text"] for _, _, l in lvl4}
    assert "Analysis: Finance Benchmark" in texts
    assert "Base LLM" in texts                 # the word gap is the line's own
    # no scaffolding leaks into the output
    assert not any("runin_split" in l or "runin_level" in l
                   for p in d["pages"] for l in p["lines"])
    # the heading's own rectangle, and the prose right after it
    for p in d["pages"]:
        for i, l in enumerate(p["lines"]):
            if l.get("level") == 4 and l["text"] == "Analysis: Finance Benchmark":
                nxt = p["lines"][i + 1]
                assert nxt["text"].startswith("As shown in Table 2")
                assert l["region"]["width"] > 0
                # the prose starts to the RIGHT of where the heading ends
                assert (nxt["region"]["top_left_x"]
                        > l["region"]["top_left_x"] + l["region"]["width"])
                return
    pytest.fail("the reported heading was not found")
