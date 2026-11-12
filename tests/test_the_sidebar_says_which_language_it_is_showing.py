r"""The right panel reads in the chosen language and must SAY so.

OWNER, 2026-11-12: "Please try to show on the right side bar the selected
language while the image with the original is shown."

WHAT WAS WRONG. Nothing, in the data path — and that was the defect. Every type
renderer reads prose through one accessor, `L(e, key)` (docinspect.py), which
returns the original-language twin whenever the chosen role is `original`. So
picking DE while the photograph is up ALREADY turned the inspector German. The
panel never said the word German, the photograph cannot change, and a control
whose only effect is invisible reads as a dead control. That is the whole
report: "for a user it remains unclear".

THE RULE. The page view is EVIDENCE — a photograph of the printed page, fixed
in whatever language the printer set. The sidebar is the one place where the two
languages can both be shown, so it carries:

  * a chip naming the language it is speaking, every time it is drawn, and
  * the OTHER language's text, under its own name, folded away.

And the stage does not move when the language changes. These tests boot the
shipped page against tests/dom_shim.js and assert on the text a reader ends up
looking at, because every earlier round of this work was verified from a
fragment and every fragment agreed with me while the page was wrong.
"""
import shutil

import pytest

from test_docinspect_page_run import _bilingual_model, _boot  # same harness

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _monolingual_model():
    m = _bilingual_model()
    for o in m["objects"]:
        o["props"].pop("text_source", None)
        o["props"].pop("caption_source", None)
    return m


def test_the_header_names_the_language_the_panel_is_speaking():
    out = _boot(_bilingual_model(), body="""
      select('p1');
      OUT.en = document.getElementById('ihLang').textContent;
      const ls = document.getElementById('langSel');
      ls.value = 'original'; ls.dispatch('change');
      OUT.de = document.getElementById('ihLang').textContent;
    """)
    assert "EN" in out["en"] and "translation" in out["en"], out["en"]
    assert "DE" in out["de"] and "original" in out["de"], out["de"]


def test_the_panel_carries_the_other_language_under_its_own_name():
    """Both languages, in one place, each labelled. The photograph cannot show
    the translation and the translation cannot show the print, so the panel is
    where they have to meet."""
    out = _boot(_bilingual_model(), body="""
      select('p1');
      const other = document.getElementById('inspBody').querySelector('.otherlang');
      OUT.has_block = !!other;
      OUT.summary = other ? other.querySelector('summary').textContent : '';
      OUT.inside = other ? other.allText() : '';
      OUT.body = document.getElementById('inspBody').allText();
    """)
    assert out["has_block"], "no other-language block in the inspector"
    assert "DE" in out["summary"] and "original" in out["summary"], out["summary"]
    assert "Korrelation im Hubbard Modell" in out["inside"], \
        "the other language's text is not in the block that names it"
    # the SELECTED language comes first; the other is folded under it
    body = out["body"]
    assert body.index("Correlation in the Hubbard Model") < body.index(
        "Korrelation im Hubbard Modell"), "the other language was put first"


def test_the_block_swaps_when_the_choice_swaps():
    """In original mode the folded text is the TRANSLATION, not the original
    again — a block that always showed `alt` would show German twice."""
    out = _boot(_bilingual_model(), body="""
      const ls = document.getElementById('langSel');
      ls.value = 'original'; ls.dispatch('change');
      select('p1');
      const other = document.getElementById('inspBody').querySelector('.otherlang');
      OUT.summary = other.querySelector('summary').textContent;
      OUT.inside = other.allText();
    """)
    assert "EN" in out["summary"] and "translation" in out["summary"], out["summary"]
    assert "Correlation in the Hubbard Model" in out["inside"]


def test_an_element_with_no_twin_says_so_instead_of_claiming_a_language():
    """A Formula is the same string in both languages. Stamping it "EN ·
    translation" would be a claim about text nobody translated."""
    m = _bilingual_model()
    m["objects"].append({
        "id": "f1", "type": "Formula", "flow_index": 4,
        "props": {"page": 1, "flow_index": 4, "latex": "E = mc^2", "display": True},
        "realizations": []})
    out = _boot(m, body="""
      select('f1');
      OUT.chip = document.getElementById('ihLang').textContent;
      OUT.other = !!document.getElementById('inspBody').querySelector('.otherlang');
    """)
    assert out["other"] is False, "an untranslated element got a second-language block"
    assert "same in both" in out["chip"], out["chip"]


def test_a_monolingual_document_gets_no_chip_at_all():
    out = _boot(_monolingual_model(), body="""
      select('p1');
      OUT.chip = document.getElementById('ihLang').textContent;
      OUT.shown = document.getElementById('ihLang').style.display;
      OUT.other = !!document.getElementById('inspBody').querySelector('.otherlang');
    """)
    assert out == {"chip": "", "shown": "none", "other": False}


def test_the_photograph_does_not_move_while_the_sidebar_changes_language():
    """THE REPORTED CONFUSION, pinned. In the page view the stage is the printed
    original and a language change must leave it byte-identical; the sidebar is
    what answers the control."""
    out = _boot(_bilingual_model(), body="""
      setView('page');
      select('p1');
      OUT.stage_before = document.getElementById('stagewrap').allText();
      OUT.body_before  = document.getElementById('inspBody').allText();
      const ls = document.getElementById('langSel');
      ls.value = 'original'; ls.dispatch('change');
      OUT.stage_after = document.getElementById('stagewrap').allText();
      OUT.body_after  = document.getElementById('inspBody').allText();
      OUT.view = curView;
    """)
    assert out["view"] == "page", "the language change moved the view again"
    assert out["stage_after"] == out["stage_before"], \
        "the stage changed when only the text language was asked to change"
    assert "Korrelation im Hubbard Modell" in out["body_after"], \
        "the sidebar did not follow the language"
    assert out["body_after"] != out["body_before"], "the sidebar did not change at all"
