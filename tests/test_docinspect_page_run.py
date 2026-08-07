"""Run the whole inspector page and read what a reader would actually see.

Every earlier round of the language work was verified from a fragment — a string
in the emitted HTML, or one extracted function fed inputs I chose. Each agreed
with me, and each was wrong about the page: the label came from the source
stream in both modes, and the default view had no prose to re-render at all.

So this boots the SHIPPED script against a small DOM (tests/dom_shim.js), flips
the selector the way a reader does, and asserts on the text that ends up in the
document. If the tree says German while the selector says English, this fails.
"""
import json
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import docinspect

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

_SHIM = Path(__file__).resolve().parent / "dom_shim.js"


def _script_of(html: str) -> str:
    """The page's own <script> — the one holding DATA and the whole UI."""
    i = html.index("const DATA = ")
    j = html.index("</script>", i)
    return html[i:j]


def _boot(model: dict, *, body: str) -> dict:
    html = docinspect.build_inspector_html(model, pages={}, title="t")
    # concatenated, not imported: the repo is an ESM package, so `require`
    # of a plain script fails before anything is tested.
    start = html.index("<body>") + len("<body>")
    markup = html[start:html.index("<script", start)]    # markup only, no script
    assert 'id="langSel"' in markup and 'id="pageTool"' in markup
    prog = "\n".join(["globalThis.__SHIM_BODY = " + json.dumps(markup) + ";",
                      _SHIM.read_text(encoding="utf-8"),
                      _script_of(html),
                      "const OUT = {};",
                      body,
                      'console.log("@@" + JSON.stringify(OUT));'])
    p = subprocess.run(["node", "-e", prog], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-3000:]
    line = [l for l in p.stdout.splitlines() if l.startswith("@@")][-1]
    return json.loads(line[2:])


def _bilingual_model():
    """Two translated paragraphs and a section, as `pdfdrill translate` leaves
    them: the translation in the prose field, the original in its `_source`."""
    return {
        "meta": {"bibkey": "demo", "num_pages": 1,
                 "pages": [{"page": 1, "page_width": 1000, "page_height": 1400}]},
        "streams": {"mathpix_lines": {"anchors": ["a1", "a2", "a3"], "payload": {
            "a1": {"text": "Korrelation im Hubbard Modell", "_page": 1,
                   "region": {"top_left_x": 10, "top_left_y": 10, "width": 900, "height": 40}},
            "a2": {"text": "Universität zu Köln", "_page": 1,
                   "region": {"top_left_x": 10, "top_left_y": 60, "width": 900, "height": 40}},
            "a3": {"text": "Inhaltsverzeichnis", "_page": 1,
                   "region": {"top_left_x": 10, "top_left_y": 110, "width": 900, "height": 40}},
        }}},
        "objects": [
            {"id": "p1", "type": "Paragraph", "flow_index": 1,
             "props": {"page": 1, "flow_index": 1,
                       "text": "Correlation in the Hubbard Model",
                       "text_source": "Korrelation im Hubbard Modell"},
             "realizations": [{"stream": "mathpix_lines", "start": "a1", "end": "a1"}]},
            {"id": "p2", "type": "Paragraph", "flow_index": 2,
             "props": {"page": 1, "flow_index": 2,
                       "text": "University of Cologne",
                       "text_source": "Universität zu Köln"},
             "realizations": [{"stream": "mathpix_lines", "start": "a2", "end": "a2"}]},
            {"id": "s1", "type": "Section", "flow_index": 3,
             "props": {"page": 1, "flow_index": 3, "level": 1,
                       "caption": "Table of Contents",
                       "caption_source": "Inhaltsverzeichnis"},
             "realizations": [{"stream": "mathpix_lines", "start": "a3", "end": "a3"}]},
        ],
        "alignments": [],
    }


_READ = """
  init();
  function seen(){ return document.getElementById('stagewrap').allText()
                 + "\\n" + document.getElementById('tree').allText(); }
"""


def test_the_page_boots_and_defaults_to_the_translation():
    out = _boot(_bilingual_model(), body=_READ + """
      setView('reflow');
      const t = seen();
      OUT.english = t.includes("Correlation in the Hubbard Model");
      OUT.german  = t.includes("Korrelation im Hubbard Modell");
      OUT.selector = document.getElementById('langSel').value;
    """)
    assert out == {"english": True, "german": False, "selector": "translated"}


def test_choosing_the_original_shows_german_and_only_german():
    out = _boot(_bilingual_model(), body=_READ + """
      document.getElementById('langSel').value = 'original';
      document.getElementById('langSel').dispatch('change');
      const t = seen();
      OUT.german  = t.includes("Korrelation im Hubbard Modell");
      OUT.english = t.includes("Correlation in the Hubbard Model");
      OUT.view = curView;
    """)
    assert out["german"] is True
    assert out["english"] is False, "the translation is still on screen in original mode"
    assert out["view"] == "reflow", "the page view cannot show prose"


def test_switching_back_to_english_really_replaces_the_german():
    """The reported failure: 'if switch to English I see Korrelation im Hubbard
    Modell'. Going back must leave no original-language text behind."""
    out = _boot(_bilingual_model(), body=_READ + """
      const ls = document.getElementById('langSel');
      ls.value = 'original';   ls.dispatch('change');
      ls.value = 'translated'; ls.dispatch('change');
      const t = seen();
      OUT.english = t.includes("Correlation in the Hubbard Model");
      OUT.german  = t.includes("Korrelation im Hubbard Modell");
      OUT.caption_en = t.includes("Table of Contents");
      OUT.caption_de = t.includes("Inhaltsverzeichnis");
    """)
    assert out == {"english": True, "german": False,
                   "caption_en": True, "caption_de": False}


def test_the_tree_and_the_reflow_never_disagree_about_the_language():
    """They are two views of one choice; one lagging is what made the control
    look broken while it was in fact working."""
    out = _boot(_bilingual_model(), body=_READ + """
      const ls = document.getElementById('langSel');
      ls.value = 'original'; ls.dispatch('change');
      const stage = document.getElementById('stagewrap').allText();
      const tree  = document.getElementById('tree').allText();
      OUT.stage_de = stage.includes("Korrelation im Hubbard Modell");
      OUT.tree_de  = tree.includes("Korrelation im Hubbard Modell");
      OUT.stage_en = stage.includes("Correlation in the Hubbard Model");
      OUT.tree_en  = tree.includes("Correlation in the Hubbard Model");
    """)
    assert out == {"stage_de": True, "tree_de": True,
                   "stage_en": False, "tree_en": False}


def test_a_monolingual_document_shows_no_selector_at_all():
    m = _bilingual_model()
    for o in m["objects"]:
        o["props"].pop("text_source", None)
        o["props"].pop("caption_source", None)
    out = _boot(m, body=_READ + """
      OUT.hidden = document.getElementById('langTool').style.display;
      OUT.langs = LANGS.length;
    """)
    assert out == {"hidden": "none", "langs": 0}


def _model_with_toc():
    m = _bilingual_model()
    m["streams"]["mathpix_lines"]["anchors"].append("a4")
    m["streams"]["mathpix_lines"]["payload"]["a4"] = {
        "text": "1 Einleitung ..... 1", "_page": 1,
        "region": {"top_left_x": 10, "top_left_y": 160, "width": 900, "height": 40}}
    m["objects"].append({
        "id": "toc", "type": "Toc", "flow_index": 4,
        "props": {"page": 1, "flow_index": 4,
                  "entries": ["1 Einleitung ..... 1", "1 Einleitung", "..... 1"]},
        "realizations": [{"stream": "mathpix_lines", "start": "a4", "end": "a4"}]})
    return m


def test_the_table_of_contents_follows_the_selected_language():
    """Its stored entries are the raw German OCR of the printed contents page.
    Rendering those left an untranslated block inside an English reading; it is
    derived from the sections instead, which do switch."""
    out = _boot(_model_with_toc(), body=_READ + """
      setView('reflow');
      OUT.en = seen().includes("Table of Contents");
      const ls = document.getElementById('langSel');
      ls.value='original'; ls.dispatch('change');
      const t = seen();
      OUT.de = t.includes("Inhaltsverzeichnis");
      OUT.raw_entry_leaked = t.includes("1 Einleitung ..... 1");
    """)
    assert out == {"en": True, "de": True, "raw_entry_leaked": False}


def test_a_toc_with_no_sections_renders_nothing_rather_than_raw_ocr():
    m = _model_with_toc()
    m["objects"] = [o for o in m["objects"] if o["type"] != "Section"]
    out = _boot(m, body=_READ + """
      setView('reflow');
      OUT.leaked = seen().includes("..... 1");
    """)
    assert out["leaked"] is False


def test_a_bilingual_document_opens_where_the_translation_is_visible():
    """Reported as "the page starts with flag showing EN while the text is DE":
    the page view is a bitmap of the printed original, so on load it showed the
    source language under a selector that said otherwise."""
    out = _boot(_bilingual_model(), body=_READ + """
      OUT.view = curView;
      OUT.role = curRole;
      OUT.english = seen().includes("Correlation in the Hubbard Model");
      OUT.german  = seen().includes("Korrelation im Hubbard Modell");
    """)
    assert out == {"view": "reflow", "role": "translated",
                   "english": True, "german": False}


def test_a_monolingual_document_still_opens_on_the_page():
    m = _bilingual_model()
    for o in m["objects"]:
        o["props"].pop("text_source", None)
        o["props"].pop("caption_source", None)
    out = _boot(m, body=_READ + "OUT.view = curView;")
    assert out == {"view": "page"}


def test_the_first_render_matches_the_view_it_says_it_is_in():
    """`init()` ended with a hard-coded renderPage(), so a bilingual document
    reported curView='reflow' while the stage held the page boxes — the state
    and the screen disagreed until the reader touched something."""
    out = _boot(_bilingual_model(), body=_READ + """
      OUT.view = curView;
      OUT.shows_prose = seen().includes("Correlation in the Hubbard Model");
    """)
    assert out == {"view": "reflow", "shows_prose": True}
