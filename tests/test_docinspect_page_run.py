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


def _two_page_model():
    m = _bilingual_model()
    m["meta"]["num_pages"] = 2
    m["meta"]["pages"].append({"page": 2, "page_width": 1000, "page_height": 1400})
    st = m["streams"]["mathpix_lines"]
    st["anchors"].append("b1")
    st["payload"]["b1"] = {"text": "Zweite Seite", "_page": 2,
                           "region": {"top_left_x": 10, "top_left_y": 10,
                                      "width": 900, "height": 40}}
    m["objects"].append({
        "id": "p9", "type": "Paragraph", "flow_index": 9,
        "props": {"page": 2, "flow_index": 9, "text": "Second page body",
                  "text_source": "Zweite Seite"},
        "realizations": [{"stream": "mathpix_lines", "start": "b1", "end": "b1"}]})
    return m


def test_the_page_selector_reaches_other_pages_in_the_reflow_view():
    """A bilingual document now opens on Reflow, where the reflow is continuous
    and the page selector used to drive only the page-image view — so choosing
    a page did nothing and the rest of the document was unreachable."""
    out = _boot(_two_page_model(), body=_READ + """
      OUT.view = curView;
      const sel = document.getElementById('pageSel');
      sel.value = 2; sel.dispatch('change');
      OUT.curPage = curPage;
      const i = CHUNKS.findIndex(c => c.p0 !== null && 2 >= c.p0 && 2 <= c.p1);
      OUT.found = i >= 0;
      OUT.hydrated = i >= 0 ? !!CHUNKS[i].hydrated : false;
      OUT.scrolled = i >= 0 ? !!CHUNKS[i].node._scrolledIntoView : false;
      OUT.text_present = seen().includes("Second page body");
    """)
    assert out == {"view": "reflow", "curPage": 2, "found": True,
                   "hydrated": True, "scrolled": True, "text_present": True}


def test_the_page_selector_still_switches_pages_in_the_page_view():
    out = _boot(_two_page_model(), body=_READ + """
      setView('page');
      const sel = document.getElementById('pageSel');
      sel.value = 2; sel.dispatch('change');
      OUT.curPage = curPage;
      OUT.view = curView;
      OUT.stage = document.getElementById('stagewrap').children.map(c=>c.className).join(",");
    """)
    assert out["curPage"] == 2 and out["view"] == "page"
    assert "stage" in out["stage"]


def test_the_page_control_is_not_dimmed_when_it_still_works():
    """It was greyed out off the page view to say "inactive there" — now it
    works in both, so dimming it tells the reader the opposite of the truth."""
    out = _boot(_two_page_model(), body=_READ + """
      OUT.op_reflow = String(document.getElementById('pageTool').style.opacity || '1');
      setView('page');
      OUT.op_page = String(document.getElementById('pageTool').style.opacity || '1');
    """)
    assert out == {"op_reflow": "1", "op_page": "1"}


def _inline_math_model():
    m = _bilingual_model()
    st = m["streams"]["mathpix_lines"]
    st["anchors"].append("c1")
    st["payload"]["c1"] = {"text": "Here pi is the permutation.", "_page": 1,
                           "region": {"top_left_x": 10, "top_left_y": 200,
                                      "width": 900, "height": 40}}
    m["objects"] += [
        {"id": "p7", "type": "Paragraph", "flow_index": 7,
         "props": {"page": 1, "flow_index": 7,
                   "text": "Here, \\(\\pi \\in S_{n}\\) is the permutation, and "
                           "\\(\\operatorname{sign}(\\pi)=1\\) for even ones."},
         "realizations": [{"stream": "mathpix_lines", "start": "c1", "end": "c1"}]},
        {"id": "f7", "type": "Formula", "flow_index": 8,
         "props": {"page": 1, "flow_index": 8, "latex": "\\pi \\in S_{n}",
                   "display": False}, "realizations": []},
        {"id": "f8", "type": "Formula", "flow_index": 9,
         "props": {"page": 1, "flow_index": 9, "latex": "E = mc^2",
                   "display": True}, "realizations": []},
    ]
    return m


def test_inline_math_in_a_paragraph_is_rendered_not_shown_as_latex():
    """The generic renderer set textContent, so a sentence displayed its own
    source: "Here, \\(\\pi \\in S_{n}\\) is the permutation". Math has to go
    through the math renderer like every other formula on the page."""
    out = _boot(_inline_math_model(), body=_READ + """
      const p = EL.find(e=>e.id==='p7');
      const n = rendererFor(p.type).render(p);
      OUT.math_nodes = n.querySelectorAll('.katex-missing').length;   // no katex in the shim
      const t = n.allText();
      OUT.prose_kept = t.includes("is the permutation") && t.includes("for even ones");
      OUT.delims_gone = !t.includes("\\\\(") && !t.includes("\\\\)");
    """)
    assert out == {"math_nodes": 2, "prose_kept": True, "delims_gone": True}


def test_an_inline_formula_is_not_repeated_as_its_own_block():
    """Inline Formula objects are CONSTITUENTS of their paragraph — the
    paragraph already shows them. Rendering each one again put six duplicate
    fragments between a sentence and the display equation it introduces."""
    out = _boot(_inline_math_model(), body=_READ + """
      const inline = EL.find(e=>e.id==='f7'), block = EL.find(e=>e.id==='f8');
      OUT.inline = rendererFor(inline.type).render(inline) === null;
      OUT.block = rendererFor(block.type).render(block) !== null;
    """)
    assert out == {"inline": True, "block": True}


def test_a_display_equation_still_renders_after_its_paragraph():
    out = _boot(_inline_math_model(), body=_READ + """
      setView('reflow');
      const t = seen();
      OUT.has_display = t.includes("E = mc^2");
    """)
    assert out["has_display"] is True


def _link_model():
    m = _bilingual_model()
    for i in range(3):                       # TOC hyperlinks, annotation layer
        m["objects"].append({
            "id": f"l{i}", "type": "Link", "flow_index": 100 + i,
            "props": {"page": 2, "flow_index": 100 + i,
                      "uri": "https://example.org/x", "anchor_text": "see"},
            "realizations": []})
    m["objects"].append({
        "id": "pz", "type": "Paragraph", "flow_index": 99,
        "props": {"page": 40, "flow_index": 99, "text": "Last body paragraph."},
        "realizations": []})
    return m


def test_link_annotations_do_not_become_blocks_in_the_reading_flow():
    """A Link is an annotation, not content. Thirty-four of them, all carrying
    the contents page, were appended after the last page of the document and
    produced a "page 2" block at the end of a 42-page reflow."""
    out = _boot(_link_model(), body=_READ + """
      buildChunks();
      OUT.link_chunks = CHUNKS.filter(c => c.els.some(e => e.type === 'Link')).length;
      let prev = null, back = 0;
      CHUNKS.forEach(c => { if (prev !== null && c.p0 != null && c.p0 < prev) back++;
                            if (c.p1 != null) prev = c.p1; });
      OUT.backwards = back;
      OUT.last_label = chunkLabel(CHUNKS[CHUNKS.length - 1]);
    """)
    assert out == {"link_chunks": 0, "backwards": 0, "last_label": "page 40"}


def test_a_link_is_still_a_first_class_element_elsewhere():
    """Excluded from the READING flow only — it keeps its tree row and record."""
    out = _boot(_link_model(), body=_READ + """
      OUT.in_data = EL.some(e => e.type === 'Link');
      OUT.has_renderer = !!rendererFor('Link');
    """)
    assert out == {"in_data": True, "has_renderer": True}
