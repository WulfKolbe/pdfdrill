"""
semantic/genre.py — genre inference: the BibTeX entrytype as an INFERRED
certificate (never a CLI switch). Evidence-based fold over cheap structural
signals (title tokens, dotted-leader TOC rows, bracketed block codes,
abstract/references/equations, arXiv id, a declared bibtex record), concluding
{entrytype, confidence, evidence}. The Axe-Fx-manual case is the fixture: an
@article grammar applied to an @manual document minted hundreds of bogus
citations — the genre certificate is what gates that pass.
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic import genre as G
from semantic import registry as R


def _o(id, t, **props):
    return types.SimpleNamespace(id=id, type=t, props=props)


def _manual_doc():
    """The Axe-manual shape: manual title, dotted-leader TOC rows, bracketed
    block codes, NO references/abstract."""
    objs = [_o("s1", "Section", caption="Effects Guide", flow_index=1)]
    for i in range(12):                       # dotted-leader TOC rows
        objs.append(_o(f"t{i}", "Paragraph", flow_index=2 + i,
                       text=f"5.{i} Volume/Pan [VOL{i}] ..... {100+i}"))
    objs.append(_o("p1", "Paragraph", flow_index=99,
                   text="Use the [AMP] block before the [CAB] block; see "
                        "[WAH] and [DLY] for details."))
    d = types.SimpleNamespace()
    d.objects = {o.id: o for o in objs}
    d.meta = {"title": "Axe-Fx II Owner's Manual"}
    return d


def _article_doc():
    objs = [
        _o("abs", "Abstract", text="We propose a novel method.", flow_index=1),
        _o("s1", "Section", caption="References", flow_index=2),
        _o("r1", "Reference", raw_text="[1] A. Author. A paper. 2020.",
           flow_index=3),
    ]
    for i in range(6):
        objs.append(_o(f"e{i}", "Equation", latex=f"x^{i}", flow_index=4 + i))
    d = types.SimpleNamespace()
    d.objects = {o.id: o for o in objs}
    d.meta = {"title": "A Study of Things", "arxiv_id": "2401.00001"}
    return d


def test_manual_is_inferred():
    g = G.infer_genre(_manual_doc())
    assert g["entrytype"] == "manual"
    assert g["confidence"] >= 0.7
    ev = " ".join(g["evidence"])
    assert "title" in ev and "dotted" in ev and "code" in ev


def test_article_is_inferred():
    g = G.infer_genre(_article_doc())
    assert g["entrytype"] == "article"
    assert g["confidence"] >= 0.7
    assert any("arxiv" in e.lower() for e in g["evidence"])


def test_declared_bibtex_entrytype_wins():
    """A .bib / cached record is the gold certificate — data, not a switch."""
    d = _article_doc()                        # article-shaped structure...
    d.meta["bibtex"] = {"entrytype": "manual"}   # ...but the record says manual
    g = G.infer_genre(d)
    assert g["entrytype"] == "manual" and g["confidence"] >= 0.9
    assert any("declared" in e for e in g["evidence"])


def test_ambiguous_is_honest_misc():
    d = types.SimpleNamespace()
    d.objects = {"p": _o("p", "Paragraph", text="Some plain prose.", flow_index=1)}
    d.meta = {}
    g = G.infer_genre(d)
    assert g["entrytype"] == "misc"
    assert g["confidence"] < 0.7              # never a confident guess from nothing


def test_filename_token_when_title_missing():
    """OCR models often carry no title — the bibkey/filename token is
    legitimate evidence (the live Axe case: meta title None, bibkey
    'Axe-Fx-II-Owners-Manual', 35 block codes)."""
    d = _manual_doc()
    d.meta = {"bibkey": "Axe-Fx-II-Owners-Manual"}   # no title at all
    g = G.infer_genre(d)
    assert g["entrytype"] == "manual" and g["confidence"] >= 0.7
    assert any("filename" in e for e in g["evidence"])


def test_registered():
    entry = R.get_fn("SO.GENRE.INFER")
    assert entry is not None and entry.impl is G.infer_genre


def test_genre_pass_writes_meta_and_gates_citation():
    """The pipeline half: GenrePass persists meta['genre']; CitationPass on a
    confident @manual reports n/a NAMING the genre (the Axe fix) — while the
    article path still links citations (regression covered by test_passes)."""
    from passes import PassContext, run_pipeline
    doc = _manual_doc()
    # bracketed codes minted bogus Citation objects (the observed failure)
    doc.objects["c1"] = _o("c1", "Citation", key="VOL", flow_index=50)
    ctx = PassContext(doc=doc)
    res = {r.name: r for r in run_pipeline(ctx, only={"genre", "citation"})}
    assert res["genre"].status == "ran"
    assert doc.meta["genre"]["entrytype"] == "manual"
    assert res["citation"].status == "n/a"
    assert "manual" in res["citation"].summary     # names the genre
    # idempotent
    res2 = {r.name: r for r in run_pipeline(ctx, only={"genre"})}
    assert res2["genre"].changed is False


def test_status_genre_line_pure():
    from pdfdrill.commands import _format_genre
    line = _format_genre({"entrytype": "manual", "confidence": 0.87,
                          "evidence": ["title token ('Axe-Fx II Owner's Manual')"]})
    assert line and "genre: @manual" in line[0] and "0.87" in line[0]
    assert "title token" in line[0]
    assert _format_genre({}) == []          # silent before the pass ran


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
