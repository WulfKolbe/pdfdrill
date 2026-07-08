"""
OKF projection (docops.projectors.okf) — the docmodel → Open Knowledge Format
bundle. OKF = one Markdown-with-YAML-frontmatter file per knowledge unit; the ONE
conformance rule is a non-empty `type` in every non-reserved file's frontmatter.

Layout (cleanups): per-type SUBFOLDERS with formulas folded into equations/ and the
Abstract flattened to the root; the Toc folds INTO index.md (no toc/ file); the
redundant bibkey-root Document tiddler is dropped (index.md is the sole Document
root). All cross-references (transclusions AND `<$link>`/`<$image>` widgets) are
RELATIVE Markdown links. Pure over a tiddler list.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import yaml
from docops.projectors import okf as X


def _tiddlers():
    return [
        {"title": "D", "type": "text/markdown", "tags": "document",
         "text": "root landing"},                      # bibkey root → dropped
        {"title": "D_ABS01", "type": "text/markdown", "tags": "abstract",
         "text": "The abstract.", "caption": "Abstract"},
        {"title": "D_FO0001", "type": "text/markdown", "tags": "formula",
         "latex": "x^2", "text": "$x^2$", "caption": "x^2"},
        {"title": "D_PARA_0001", "type": "text/markdown", "tags": "paragraph",
         "text": "See {{D_FO0001||FO}} for the square.", "page": 2},
        {"title": "D_H1", "type": "text/markdown", "tags": "section",
         "caption": "Intro", "section_number": "1", "text": "# Intro"},
        {"title": "D_TOC", "type": "text/markdown", "tags": "toc",
         "text": '- 1 <$link to="D_H1">Introduction</$link> — p. 1'},
        {"title": "D_PIC0001", "type": "text/markdown", "tags": "picture",
         "text": '<$image source="cdn://x.png" width="100">', "caption": "Fig 1"},
        {"title": "D_REF_smith", "type": "text/markdown", "tags": "reference bibentry",
         "citekey": "smith2020", "text": "J. Smith. A paper. 2020.", "year": "2020"},
        {"title": "D_TB0001", "type": "text/markdown", "tags": "table",
         "text": "| a | b |\n|---|---|\n| 1 | 2 |", "caption": "Results"},
        {"title": "$:/tpl/FO", "type": "text/vnd.tiddlywiki", "tags": "template",
         "text": "<$latex>"},                          # template → skipped
    ]


def _fm(content):
    assert content.startswith("---\n")
    return yaml.safe_load(content.split("---\n", 2)[1])


def test_conformance_nonempty_type_in_every_file():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {"title": "Demo"},
                               "2026-07-08T00:00:00Z")
    for path, content in bundle.items():
        assert _fm(content).get("type"), f"{path}: missing non-empty type"


def test_folder_structure_and_flattening():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")
    assert "equations/D_FO0001.md" in bundle           # #1 formulas folded into equations/
    assert not any(p.startswith("formulas/") for p in bundle)
    assert "sections/D_H1.md" in bundle
    assert "references/D_REF_smith.md" in bundle
    assert "tables/D_TB0001.md" in bundle
    assert "figures/D_PIC0001.md" in bundle
    assert "D_ABS01.md" in bundle                       # #3 abstract flattened to root
    assert "index.md" in bundle


def test_toc_folds_into_index_no_toc_folder():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")
    assert not any(p.startswith("toc/") for p in bundle)   # #2 no toc/ file
    idx = bundle["index.md"]
    assert "[Introduction](./sections/D_H1.md)" in idx     # the TOC lives in index.md


def test_root_document_tiddler_dropped():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")   # #5
    assert "documents/D.md" not in bundle and "D.md" not in bundle
    docs = [p for p, c in bundle.items() if _fm(c).get("type") == "Document"]
    assert docs == ["index.md"]                            # index.md is the sole Document


def test_template_tiddlers_skipped():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")
    assert not any("tpl" in p.lower() or "$:" in p for p in bundle)


def test_type_resource_and_body():
    fo = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")["equations/D_FO0001.md"]
    m = _fm(fo)
    assert m["type"] == "Formula"                          # type stays Formula (folder merged)
    assert m["resource"] == "pdfdrill:D/D_FO0001"
    assert "D" in (m.get("tags") or [])
    assert "x^2" in fo and "$" in fo


def test_transclusion_rewritten_to_relative_link():
    para = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")["paragraphs/D_PARA_0001.md"]
    assert "(../equations/D_FO0001.md)" in para           # relative, into equations/
    assert "{{" not in para and "||" not in para


def test_image_widget_becomes_markdown():
    pic = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")["figures/D_PIC0001.md"]
    assert "![](cdn://x.png)" in pic
    assert "<$image" not in pic


def test_no_tiddlywiki_widgets_anywhere():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {"title": "Demo"}, "T")
    for path, content in bundle.items():
        assert "<$" not in content, f"{path}: TiddlyWiki widget leaked"


def test_table_and_reference_headings():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")
    assert "# Schema" in bundle["tables/D_TB0001.md"]
    assert "# Citations" in bundle["references/D_REF_smith.md"]


def test_index_md_is_document_with_relative_links():
    idx = X.tiddlers_to_okf(_tiddlers(), "D", {"title": "Demo", "num_pages": 3},
                            "T")["index.md"]
    assert _fm(idx)["type"] == "Document"
    assert "(./equations/D_FO0001.md)" in idx             # relative from root, merged folder


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try: t(); print(f"PASS {name}")
        except AssertionError as e: failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e: failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed: print(f"\n{len(failed)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} passed.")
