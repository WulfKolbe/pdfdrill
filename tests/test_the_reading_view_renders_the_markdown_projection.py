r"""Reflow becomes a READING view over a real projection, and Compare ends the
"am I looking at the page or at our reading of it" question for good.

OWNER, 2026-11-12: "We have the page view, which is only useful for the
original image and the reflow view which should be used for a rendered view in
the different languages available. ... In the reflow view only rendered text is
shown via Markdown. You can choose if you show Markdown, HTML or LaTeX."

WHAT WAS WRONG. Reflow was a FOURTH renderer. `hydrateChunk` built DOM straight
from the model through `rendererFor(e.type).render(e)`, sharing no code with
`md`, `tiddlers` or `latex`. So Reflow could disagree with the Markdown
pdfdrill actually ships and nothing anywhere would notice — a viewer built to
audit a pipeline, which could not audit the pipeline's own output.

THE DESIGN.
  * Page    — the photograph. One language: whatever the printer set.
  * Reading — our text, in a chosen LANGUAGE and a chosen FORMAT. `html` is the
              model-backed renderer (fast, page-chunked, needed by Compare);
              `md` is the `md` projection itself, rendered. Any divergence
              between the two stops being invisible.
  * Compare — page N's photograph beside page N's reading, both labelled. The
              ambiguity the owner reported becomes impossible to have.

Language and format are ORTHOGONAL: one control says WHICH text, the other says
HOW it is rendered. Conflating them is what made a single selector look broken.
"""
import shutil

import pytest

from test_docinspect_page_run import _bilingual_model, _boot

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

DE_MD = "# Inhaltsverzeichnis\n\nKorrelation im Hubbard Modell, mit $E = mc^2$.\n"
EN_MD = "# Table of Contents\n\nCorrelation in the Hubbard Model, with $E = mc^2$.\n"

MARKDOWN = {
    "de": {"code": "DE", "role": "original", "text": DE_MD},
    "en-us": {"code": "EN-US", "role": "translated", "text": EN_MD},
}

_READ = """
  function stage(){ return document.getElementById('stagewrap').allText(); }
  function say(){ return document.getElementById('stageSay').textContent; }
"""


# ── the projection is shipped with the page ─────────────────────────────────

def test_the_page_embeds_the_projection_for_each_language():
    out = _boot(_bilingual_model(), markdown=MARKDOWN, body=_READ + """
      OUT.tags = Object.keys(MD).sort();
      OUT.de = (MD['de']||{}).text.includes('Korrelation im Hubbard Modell');
    """)
    assert out == {"tags": ["de", "en-us"], "de": True}


def test_without_a_projection_there_is_no_format_switch():
    """A monolingual or un-projected document must not grow a dead control."""
    out = _boot(_bilingual_model(), body=_READ + """
      OUT.keys = Object.keys(MD).length;
      OUT.shown = document.getElementById('fmtSeg').style.display;
    """)
    assert out == {"keys": 0, "shown": "none"}


def test_the_format_switch_appears_when_a_projection_is_embedded():
    out = _boot(_bilingual_model(), markdown=MARKDOWN, body=_READ + """
      OUT.shown = document.getElementById('fmtSeg').style.display;
      OUT.buttons = document.getElementById('fmtSeg')
                   .querySelectorAll('button').map(b => b.textContent).sort();
    """)
    assert out["shown"] == ""
    assert out["buttons"] == ["HTML", "Markdown"]


# ── reading in Markdown ────────────────────────────────────────────────────

def test_choosing_markdown_shows_the_projection_and_not_the_model_renderer():
    out = _boot(_bilingual_model(), markdown=MARKDOWN, body=_READ + """
      setView('reflow'); setFmt('md');
      OUT.text = stage().includes('Correlation in the Hubbard Model');
      OUT.chunks = !!document.querySelector('.chunk');
    """)
    assert out["text"] is True, "the markdown projection is not on the stage"
    assert out["chunks"] is False, "the model-backed renderer is still running"


def test_the_markdown_follows_the_language_choice():
    """The projection is per language, so the format switch must not strand the
    reader in the other one."""
    out = _boot(_bilingual_model(), markdown=MARKDOWN, body=_READ + """
      setView('reflow'); setFmt('md');
      const ls = document.getElementById('langSel');
      ls.value = 'original'; ls.dispatch('change');
      OUT.de = stage().includes('Korrelation im Hubbard Modell');
      OUT.en = stage().includes('Correlation in the Hubbard Model');
    """)
    assert out == {"de": True, "en": False}


def test_without_the_markdown_renderer_the_source_is_shown_and_said():
    """`marked` comes from a CDN and the shim has none — which is also the
    offline case. The reader must get the Markdown as text plus a sentence
    saying why it is not rendered, never a blank stage."""
    out = _boot(_bilingual_model(), markdown=MARKDOWN, body=_READ + """
      setView('reflow'); setFmt('md');
      OUT.text = stage().includes('Correlation in the Hubbard Model');
      OUT.raw = !!document.querySelector('.mdraw');
    """)
    assert out == {"text": True, "raw": True}


def test_the_format_choice_survives_a_page_change():
    out = _boot(_bilingual_model(), markdown=MARKDOWN, body=_READ + """
      setView('reflow'); setFmt('md');
      for (let p = 1; p <= 5; p++) { curPage = p; refreshStage(); }
      OUT.fmt = curFmt;
      OUT.text = stage().includes('Correlation in the Hubbard Model');
    """)
    assert out == {"fmt": "md", "text": True}


# ── compare ────────────────────────────────────────────────────────────────

def test_compare_shows_the_photograph_and_the_reading_side_by_side():
    out = _boot(_bilingual_model(), body=_READ + """
      setView('compare');
      OUT.panes = document.querySelectorAll('.cmp-pane').length;
      OUT.evidence = !!document.querySelector('.cmp-evidence');
      OUT.reading = !!document.querySelector('.cmp-reading');
      OUT.text = stage().includes('Correlation in the Hubbard Model');
    """)
    assert out["panes"] == 2, "compare is not two panes"
    assert out["evidence"] is True and out["reading"] is True
    assert out["text"] is True, "the reading pane has no text"


def test_the_compare_caption_names_which_side_is_which():
    out = _boot(_bilingual_model(), body=_READ + """
      setView('compare');
      OUT.say = say();
    """)
    s = out["say"].lower()
    assert "left" in s and "right" in s, out["say"]
    assert "photograph" in s, out["say"]


def test_the_three_views_are_offered_by_name():
    out = _boot(_bilingual_model(), body=_READ + """
      OUT.views = document.getElementById('viewSeg')
                   .querySelectorAll('button').map(b => b.textContent);
    """)
    assert out["views"] == ["Page", "Reading", "Compare"], (
        "the three views a reader is offered, in order")


def test_the_compare_reading_pane_follows_the_language():
    out = _boot(_bilingual_model(), body=_READ + """
      setView('compare');
      const ls = document.getElementById('langSel');
      ls.value = 'original'; ls.dispatch('change');
      OUT.de = stage().includes('Korrelation im Hubbard Modell');
      OUT.en = stage().includes('Correlation in the Hubbard Model');
      OUT.view = curView;
    """)
    assert out == {"de": True, "en": False, "view": "compare"}
