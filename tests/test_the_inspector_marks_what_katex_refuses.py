r"""An unrenderable formula was shown as KaTeX's own error text, and counted
as rendered.

T-0080 item 2 (drillgroup, owner 2026-10-27): "The inspector shows
`latex_original` as text and renders `latex`", with a KaTeX-unrenderable
formula MARKED rather than shown as error text. The gate: KaTeX 0.16.9 failures
on 1702.06385, 2210.01629v3 and one paper with diagrams go to 0 or each is
listed, counted with the inspector's own KaTeX.

THREE DEFECTS, all of them quiet:

  1. `throwOnError: false`. KaTeX's default behaviour on a formula it cannot
     parse is to put its own error INTO the output as red text containing the
     source. So the `catch` in `renderMath` never fired, the page showed
     `\tikzcd` as a red string where a diagram belongs, and any count of
     failures was zero. Measured over the drill library: 6,373 of 23,608
     expanded display equations are refused by this very version.

  2. ONE grey box for two different things. `katex-missing` was used both for
     "KaTeX did not load" (offline, CDN blocked) and for "KaTeX refused this
     formula". A reader could not tell a broken formula from a broken network,
     and the second is not a statement about the formula at all.

  3. `props["latex_original"]` is EMPTY on the documents this is for.
     `cmd_injectlatex` attaches the author's form to the matched equation as a
     `provenance="tex"` realization and only writes props when there was no
     MathPix scaffold. Measured on the two gate papers after
     `pdfdrill injectlatex`: of 254 maths objects, 0 carried
     `props["latex_original"]` and 27 carried it on a realization. A props-only
     reader would have shipped a feature that does nothing on its own gate.

The count is taken ONCE over every maths element at load (`katexAudit`), not
accumulated by `renderMath`: the inspector renders lazily, so a tally built
while rendering reports what the reader has scrolled past and would say
"0 refused" about a document whose every formula is refused.
"""
import json
import shutil

import pytest

from pdfdrill import docinspect
from tests.test_docinspect_page_run import _boot, _bilingual_model

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node not installed")

#: A KaTeX that renders everything except the one control sequence, with the
#: real message shape. NOT the real KaTeX: the point here is the page's
#: behaviour on a refusal, and `tests/test_a_formula_carries_no_latex_only_
#: command.py` is where the real renderer's verdict is measured.
_FAKE_KATEX = r"""
globalThis.__noKatex = 0;
globalThis.katex = {
  /* `/tikzcd/` and NOT `/\\tikzcd/`: there is no backslash in
   * `\begin{tikzcd}`, so the backslashed form matched nothing and this fake
   * rendered everything — the test passed against a page that was never
   * asked to refuse. Measured while writing it. */
  _bad: /tikzcd/,
  _check(t){ if(this._bad.test(t)) {
      /* the message shape KaTeX 0.16.9 really produces for the largest group
       * of real refusals: 1,072 equations across 17 documents are `tikzcd`. */
      throw new Error("KaTeX parse error: No such environment: tikzcd at "
                      + "position 1: \\begin{tikzcd}"); } },
  render(t, into, o){ this._check(t); into.innerHTML = '<span class="katex">'+t+'</span>'; },
  renderToString(t, o){ this._check(t); return '<span class="katex">'+t+'</span>'; },
};
"""


def _math_model(*, author_on="props"):
    """Three maths objects: one KaTeX renders, one it refuses, one carrying the
    author's LaTeX where `author_on` says it lives."""
    m = _bilingual_model()
    author = {"latex_original": r"|\dom(a)| = 1"}
    good = {"id": "e1", "type": "Equation", "flow_index": 7,
            "props": {"page": 1, "flow_index": 7, "latex": "E = mc^2",
                      "refnum": "1"}, "realizations": []}
    bad = {"id": "e2", "type": "Equation", "flow_index": 8,
           "props": {"page": 1, "flow_index": 8,
                     "latex": r"\begin{tikzcd} A \rar & B \end{tikzcd}",
                     "refnum": "2"}, "realizations": []}
    carrier = {"id": "f1", "type": "Formula", "flow_index": 9,
               "props": {"page": 1, "flow_index": 9,
                         "latex": r"|\mathbb{D}(a)| = 1", "display": True},
               "realizations": []}
    if author_on == "props":
        carrier["props"].update(author)
    else:
        # The realization's `latex` DIFFERS from props', which is the real
        # shape: props holds the document's own reading (MathPix or geometry)
        # and the realization holds the author's, expanded. Making them equal
        # in a fixture would hide the second rendered form entirely.
        carrier["props"]["latex"] = r"|D(a)| = 1"
        carrier["realizations"] = [
            {"stream": "tex", "role": "latex_candidate", "provenance": "tex",
             "score": 0.91,
             "props": dict(author, latex=r"|\mathbb{D}(a)| = 1")}]
    m["objects"] += [good, bad, carrier]
    return m


# ---------------------------------------------------------------------------
# What the record carries.
# ---------------------------------------------------------------------------

def _data_of(html: str) -> str:
    """The page's `DATA` payload — one line, `const DATA = {...};`."""
    i = html.index("const DATA = ") + len("const DATA = ")
    j = html.index("\n", i)
    return html[i:j].rstrip().rstrip(";")


@pytest.mark.parametrize("where,expect_from", [("props", "props"), ("tex", "tex")])
def test_the_authors_latex_reaches_the_page_from_wherever_it_lives(where, expect_from):
    """THE CASE BUILT TO FAIL for defect 3: with `author_on="tex"` a props-only
    reader finds nothing, which is the state of both gate papers."""
    data = json.loads(_data_of(docinspect.build_inspector_html(
        _math_model(author_on=where), pages={}, title="t")))
    rec = next(e for e in data["elements"] if e["id"] == "f1")
    assert rec["latex_original"] == r"|\dom(a)| = 1", rec
    assert rec["orig_from"] == expect_from, rec


def test_an_object_with_no_author_latex_says_nothing_rather_than_empty_string():
    """An absent provenance must be ABSENT, not `""` — a reader that tests for
    the key would otherwise draw an empty "author's latex" section under every
    formula in a document that has none."""
    data = json.loads(_data_of(docinspect.build_inspector_html(
        _math_model(), pages={}, title="t")))
    rec = next(e for e in data["elements"] if e["id"] == "e1")
    assert "latex_original" not in rec and "orig_from" not in rec, rec


# ---------------------------------------------------------------------------
# What the page does with it.
# ---------------------------------------------------------------------------

def test_a_refused_formula_is_marked_and_its_source_is_not_red_error_text():
    out = _boot(_math_model(), pre=_FAKE_KATEX, body="""
      const bad = EL.find(e=>e.id==='e2'), good = EL.find(e=>e.id==='e1');
      const nb = rendererFor(bad.type).render(bad);
      const ng = rendererFor(good.type).render(good);
      OUT.bad_marked   = nb.querySelectorAll('.katex-refused').length;
      OUT.bad_rendered = nb.querySelectorAll('.katex').length;
      OUT.bad_says_why = nb.allText().includes('no tikzcd environment in KaTeX');
      OUT.bad_keeps_src = nb.allText().includes('tikzcd');
      OUT.good_rendered = ng.querySelectorAll('.katex').length;
      OUT.good_marked   = ng.querySelectorAll('.katex-refused').length;
      OUT.no_missing_class = nb.querySelectorAll('.katex-missing').length;
    """)
    assert out == {"bad_marked": 1, "bad_rendered": 0, "bad_says_why": True,
                   "bad_keeps_src": True, "good_rendered": 1, "good_marked": 0,
                   "no_missing_class": 0}


def test_a_renderer_that_did_not_load_is_a_different_mark():
    """Defect 2. No `pre`, so the shim's own `__noKatex = 1` stands — which is
    what an offline reader gets. The formula must NOT be marked as refused:
    nothing was tried, and saying otherwise blames the document for the
    network."""
    out = _boot(_math_model(), body="""
      const bad = EL.find(e=>e.id==='e2');
      const n = rendererFor(bad.type).render(bad);
      OUT.missing = n.querySelectorAll('.katex-missing').length;
      OUT.refused = n.querySelectorAll('.katex-refused').length;
      OUT.banner = document.getElementById('katexAudit').allText();
    """)
    assert out["missing"] == 1 and out["refused"] == 0, out
    assert "KaTeX did not load" in out["banner"], out["banner"]
    assert "refused" not in out["banner"].split("nothing was refused")[0], out["banner"]


def test_the_audit_counts_and_lists_every_refusal_at_load():
    out = _boot(_math_model(), pre=_FAKE_KATEX, body="""
      OUT.banner = document.getElementById('katexAudit').allText();
      OUT.hook = (window.__katexRefused||[]).map(b=>b.id);
      OUT.why  = (window.__katexRefused||[]).map(b=>b.why);
    """)
    assert out["hook"] == ["e2"], out
    assert out["why"] == ["no tikzcd environment in KaTeX"], out
    assert "refused 1 of 3 rendered forms" in out["banner"], out["banner"]
    assert "e2" in out["banner"], out["banner"]
    assert "each one listed, none hidden" in out["banner"], out["banner"]


def test_the_audit_does_not_depend_on_what_has_been_rendered():
    """The reason it is a pass of its own: nothing has been scrolled to, no
    detail pane opened, and the count is still complete."""
    out = _boot(_math_model(), pre=_FAKE_KATEX, body="""
      OUT.n = (window.__katexRefused||[]).length;
      OUT.stage_empty = document.getElementById('stagewrap')
                          .querySelectorAll('.katex-refused').length;
    """)
    assert out["n"] == 1, out


def test_a_document_that_renders_cleanly_says_so_with_its_population():
    m = _math_model()
    m["objects"] = [o for o in m["objects"] if o["id"] != "e2"]
    out = _boot(m, pre=_FAKE_KATEX, body="""
      OUT.banner = document.getElementById('katexAudit').allText();
      OUT.n = (window.__katexRefused||[]).length;
    """)
    assert out["n"] == 0
    assert "renders every formula" in out["banner"], out["banner"]
    assert "2 formulas" in out["banner"], out["banner"]
    assert "1 with the author's latex" in out["banner"], out["banner"]
    assert "2 rendered forms in all" in out["banner"], out["banner"]


def test_the_inspector_shows_the_authors_latex_as_text_and_renders_the_other():
    """The owner's sentence, as two assertions: `latex_original` appears as
    text in its own section, and the thing that goes through the renderer is
    `latex`. Rendering the author's form would put a red error where the
    provenance belongs — it still holds the macros the author defined."""
    out = _boot(_math_model(author_on="tex"), pre=_FAKE_KATEX, body="""
      const e = EL.find(el=>el.id==='f1');
      const host = document.createElement('div');
      host.innerHTML = rendererFor(e.type).detail(e);
      OUT.html = host.innerHTML;
    """)
    h = out["html"]
    assert r"|\dom(a)| = 1" in h, h                  # the author's form, as text
    assert "author's latex" in h and "tex provenance" in h, h
    assert "match 0.91" in h, h
    # and the author's form is NOT the thing handed to the renderer
    assert 'data-eq="|\\mathbb{D}(a)| = 1"' in h.replace("&amp;", "&") or \
           r"data-eq=\"|\mathbb{D}(a)| = 1\"" in h, h
    assert r'data-eq="|\dom(a)| = 1"' not in h, h


def test_the_authors_reading_is_a_second_renderable_form():
    r"""Without this the author's LaTeX reaches the page as TEXT ONLY, and the
    owner's goal — an inspect page with pdf2mmd2's geometry AND the author's
    LaTeX — is half met. Measured on the three gate documents: 15, 12 and 9
    objects carry an author's reading that nothing rendered."""
    data = json.loads(_data_of(docinspect.build_inspector_html(
        _math_model(author_on="tex"), pages={}, title="t")))
    rec = next(e for e in data["elements"] if e["id"] == "f1")
    assert rec["latex_author"] == r"|\mathbb{D}(a)| = 1", rec
    assert rec["latex"] == r"|D(a)| = 1", (
        "the document's own reading must stay the one `latex` names")


def test_an_author_reading_identical_to_the_documents_is_not_duplicated():
    """Two blocks showing the same string is noise, not provenance."""
    m = _math_model(author_on="tex")
    f1 = next(o for o in m["objects"] if o["id"] == "f1")
    f1["props"]["latex"] = f1["realizations"][0]["props"]["latex"]
    data = json.loads(_data_of(docinspect.build_inspector_html(
        m, pages={}, title="t")))
    rec = next(e for e in data["elements"] if e["id"] == "f1")
    assert "latex_author" not in rec, rec
    assert rec["latex_original"], "the author's SOURCE is still provenance"


def test_the_detail_pane_renders_the_authors_reading_under_its_own_heading():
    """Asserted on the MARKUP, not through `querySelectorAll`: the dom shim
    stores `innerHTML` as a string and does not parse it into nodes, so a
    selector over it finds nothing and the test would pass for every possible
    output. Measured — `n_render` came back 0 with both blocks present."""
    out = _boot(_math_model(author_on="tex"), pre=_FAKE_KATEX, body="""
      const e = EL.find(el=>el.id==='f1');
      OUT.html = rendererFor(e.type).detail(e);
    """)
    h = out["html"]
    assert h.count('data-eq="') == 2, h        # the document's, and the author's
    assert "author's reading" in h, h
    # in that order: the document's own reading first, the author's beneath it
    assert h.index('data-eq="|D(a)| = 1"') < h.index(r'data-eq="|\mathbb{D}(a)| = 1"'), h


def test_the_audit_counts_the_authors_reading_too():
    r"""THE CASE BUILT TO FAIL. Before the resolution pass the author's reading
    was the half that did not render: 13 of these were refused on 1702.06385,
    every one of them for \ensuremath or \xspace. Counting one form per object
    would have reported 0 refused on exactly that document."""
    m = _math_model(author_on="tex")
    f1 = next(o for o in m["objects"] if o["id"] == "f1")
    f1["realizations"][0]["props"]["latex"] = r"\begin{tikzcd} A \end{tikzcd}"
    out = _boot(m, pre=_FAKE_KATEX, body="""
      OUT.bad = (window.__katexRefused||[]).map(b=>b.id+':'+b.which);
      OUT.banner = document.getElementById('katexAudit').allText();
    """)
    assert out["bad"] == ["e2:latex", "f1:author's reading"], out
    assert "refused 2 of 4 rendered forms" in out["banner"], out["banner"]


def test_the_two_marks_are_styled_differently_in_the_shipped_css():
    """They are the whole of defect 2, and a reader tells them apart by sight
    before reading either."""
    html = docinspect.build_inspector_html(_math_model(), pages={}, title="t")
    assert ".katex-refused{" in html and ".katex-missing{" in html
    assert ".katex-audit{" in html


def test_the_page_asks_katex_not_to_swallow_its_own_errors():
    """Defect 1, at the source. `throwOnError:false` anywhere in the page
    script puts the error back inside the output and this whole file passes
    while the page lies."""
    html = docinspect.build_inspector_html(_math_model(), pages={}, title="t")
    assert "throwOnError:false" not in html.replace(" ", "")
    assert html.replace(" ", "").count("throwOnError:true") >= 2, (
        "both the per-element render and the audit pass must ask for the throw")
    assert "strict:false" in html.replace(" ", ""), (
        "the audit and the page must use the same strictness as the measure, "
        "or the page's count and the measured count are different numbers")
