"""Execute the inspector's REAL language JavaScript, not a description of it.

The Python half can only assert that `id="langSel"` appears in a string — which
says nothing about whether the switch works. The behaviour the user asked for
lives entirely in the client: pick a language once, then keep paging without
re-picking. So this extracts the shipped language block out of the template and
runs it in node against stubs, where "the choice survives a page change" is a
statement that can actually be checked.

Skipped when node is absent — the feature still ships, it is just unverified
here, and saying so beats a green suite that tested nothing.
"""
import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import docinspect

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

_START = "const LANGS = DATA.languages || [];"
_END = "/* ---------- KaTeX helper ---------- */"


def _language_block() -> str:
    """The shipped block, verbatim — not a copy that can drift from it."""
    tpl = docinspect._TEMPLATE
    i = tpl.index(_START)
    j = tpl.index(_END, i)
    return tpl[i:j]


def _run(js_body: str, *, languages, elements=(), saved=None, bibkey="demo") -> dict:
    """Run the real block plus `js_body`, return whatever it puts in `OUT`.

    `saved` is MUTATED like a real localStorage, so a caller can carry one
    store across two documents and see whether they interfere."""
    harness = textwrap.dedent("""
        const DATA = %s;
        const EL = DATA.elements, byId = {}; EL.forEach(e => byId[e.id] = e);
        const IMAGE_CATS = new Set(["Picture","Diagram","Chart"]);
        let selId = null, curPage = 1;
        const _store = %s;
        globalThis.localStorage = {
          getItem: k => (k in _store ? _store[k] : null),
          setItem: (k, v) => { _store[k] = String(v); },
        };
        let RENDERS = 0;
        function refreshStage(){ RENDERS++; }
        function buildTree(){ RENDERS++; }
        function renderInspector(){ RENDERS++; }
        function document_stub(){}
        const document = { getElementById: () => ({ value: "" }) };
        const OUT = {};
        %s
        %s
        OUT.__store__ = _store;
        console.log(JSON.stringify(OUT));
    """) % (
        json.dumps({"bibkey": bibkey, "title": bibkey,
                    "languages": list(languages), "elements": list(elements)}),
        json.dumps(saved or {}),
        _language_block(),
        js_body,
    )
    p = subprocess.run(["node", "-e", harness], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout.strip().splitlines()[-1])
    store = out.pop("__store__", {})
    if saved is not None:                      # write back, like a real browser
        saved.clear(); saved.update(store)
    return out


_DE_EN = [{"code": "en", "role": "translated", "flag": "F1", "label": "EN"},
          {"code": "de", "role": "original", "flag": "F2", "label": "DE"}]
_PARA = {"id": "p1", "type": "Paragraph", "page": 1, "label": "Hello world",
         "text": "Hello world", "alt": {"text": "Hallo Welt"}}


def test_default_is_the_translation_and_switching_yields_the_original():
    out = _run("""
        OUT.before = L(byId.p1, 'text');
        setLang('original');
        OUT.after = L(byId.p1, 'text');
        setLang('translated');
        OUT.back = L(byId.p1, 'text');
    """, languages=_DE_EN, elements=[_PARA])
    assert out == {"before": "Hello world", "after": "Hallo Welt",
                   "back": "Hello world"}


def test_the_choice_survives_page_changes():
    """The user's actual requirement. Paging touches curPage; it must not touch
    the language, so the same element still reads in the chosen language after
    an arbitrary number of page turns."""
    out = _run("""
        setLang('original');
        for (let p = 1; p <= 40; p++) { curPage = p; refreshStage(); }
        OUT.text = L(byId.p1, 'text');
        OUT.role = curRole;
    """, languages=_DE_EN, elements=[_PARA])
    assert out == {"text": "Hallo Welt", "role": "original"}


def test_the_choice_is_persisted_and_restored_on_reopen():
    out = _run("OUT.saved = localStorage.getItem('docinspect.lang.demo');",
               languages=_DE_EN, elements=[_PARA])
    assert out["saved"] is None                      # nothing written until chosen

    out = _run("setLang('original'); OUT.saved = localStorage.getItem('docinspect.lang.demo');",
               languages=_DE_EN, elements=[_PARA])
    assert out["saved"] == "original"

    reopened = _run("OUT.role = curRole; OUT.text = L(byId.p1, 'text');",
                    languages=_DE_EN, elements=[_PARA],
                    saved={"docinspect.lang.demo": "original"})
    assert reopened == {"role": "original", "text": "Hallo Welt"}


def test_two_documents_keep_separate_choices():
    """Reading one document in the original must not flip the next document
    the user opens — the stored key is per bibkey, in ONE shared store."""
    store: dict = {}
    _run("setLang('original');", languages=_DE_EN, elements=[_PARA],
         saved=store, bibkey="paperA")
    assert any("paperA" in k for k in store), store

    other = _run("OUT.role = curRole;", languages=_DE_EN, elements=[_PARA],
                 saved=store, bibkey="paperB")
    assert other["role"] == "translated"          # B untouched by A

    again = _run("OUT.role = curRole;", languages=_DE_EN, elements=[_PARA],
                 saved=store, bibkey="paperA")
    assert again["role"] == "original"            # A remembered


def test_an_element_with_no_twin_keeps_showing_the_only_text_it_has():
    """Partial translation degrades per element — never to an empty page."""
    only = {"id": "p2", "type": "Paragraph", "page": 1, "label": "untouched",
            "text": "untouched"}
    out = _run("setLang('original'); OUT.text = L(byId.p2, 'text');",
               languages=_DE_EN, elements=[only])
    assert out["text"] == "untouched"


def test_monolingual_document_never_switches():
    """With no second language, `original` is not reachable — so a stale stored
    value (or a stray call) cannot blank a monolingual document."""
    out = _run("""
        OUT.orig0 = isOriginal();
        setLang('original');
        OUT.orig1 = isOriginal();
        OUT.text = L(byId.p1, 'text');
    """, languages=[], elements=[_PARA],
        saved={"docinspect.lang.demo": "original"})
    assert out == {"orig0": False, "orig1": False, "text": "Hello world"}


def test_labels_follow_the_selected_language():
    fig = {"id": "d1", "type": "Diagram", "page": 1, "refnum": "3",
           "label": "Fig 3 — Lattice", "caption": "Lattice",
           "alt": {"caption": "Gitter"}}
    out = _run("""
        OUT.tr = labelOf(byId.d1);
        setLang('original');
        OUT.or = labelOf(byId.d1);
    """, languages=_DE_EN, elements=[fig])
    assert out["tr"] == "Fig 3 — Lattice"
    assert out["or"] == "Fig 3 — Gitter"          # refnum kept, caption switched
