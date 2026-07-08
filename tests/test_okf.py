"""
OKF projection (docops.projectors.okf) — the docmodel → Open Knowledge Format
bundle. OKF = one Markdown-with-YAML-frontmatter file per knowledge unit; the ONE
conformance rule is a non-empty `type` in every non-reserved file's frontmatter.

OKF allows a FOLDER structure ("files at any directory level") and bundle-absolute
links `[t](/tables/x.md)`, so units are organised into per-type subfolders and ALL
cross-references (transclusions AND TiddlyWiki `<$link>`/`<$image>` widgets) are
emitted as Markdown links — never TiddlyWiki syntax. Pure over a tiddler list.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import yaml
from docops.projectors import okf as X


def _tiddlers():
    return [
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


def test_folder_structure_by_type():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")
    assert "formulas/D_FO0001.md" in bundle
    assert "sections/D_H1.md" in bundle
    assert "references/D_REF_smith.md" in bundle
    assert "tables/D_TB0001.md" in bundle
    assert "figures/D_PIC0001.md" in bundle           # Picture → figures/
    assert "index.md" in bundle                        # reserved, at the root


def test_template_tiddlers_skipped():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")
    assert not any("tpl" in p.lower() or "$:" in p for p in bundle)


def test_type_from_kind_and_resource_and_body():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")
    fo = bundle["formulas/D_FO0001.md"]
    m = _fm(fo)
    assert m["type"] == "Formula"
    assert m["resource"] == "pdfdrill:D/D_FO0001"
    assert "D" in (m.get("tags") or [])
    assert "x^2" in fo and "$" in fo


def test_transclusion_rewritten_to_bundle_absolute_link():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")
    para = bundle["paragraphs/D_PARA_0001.md"]
    assert "(/formulas/D_FO0001.md)" in para           # bundle-absolute markdown link
    assert "{{" not in para and "||" not in para


def test_tiddlywiki_link_widget_becomes_markdown():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")
    toc = bundle["toc/D_TOC.md"]
    assert "[Introduction](/sections/D_H1.md)" in toc  # <$link> → markdown link
    assert "<$link" not in toc and "</$link>" not in toc


def test_image_widget_becomes_markdown():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")
    pic = bundle["figures/D_PIC0001.md"]
    assert "![](cdn://x.png)" in pic                    # <$image> → markdown image
    assert "<$image" not in pic


def test_no_tiddlywiki_widgets_anywhere():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {"title": "Demo"}, "T")
    for path, content in bundle.items():
        assert "<$" not in content, f"{path}: TiddlyWiki widget leaked"


def test_table_and_reference_headings():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")
    assert "# Schema" in bundle["tables/D_TB0001.md"]
    assert "# Citations" in bundle["references/D_REF_smith.md"]


def test_index_md_is_document_with_folder_links():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {"title": "Demo",
                               "num_pages": 3}, "T")
    idx = bundle["index.md"]
    assert _fm(idx)["type"] == "Document"
    assert "(/formulas/D_FO0001.md)" in idx            # bundle-absolute folder link


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try: t(); print(f"PASS {name}")
        except AssertionError as e: failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e: failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed: print(f"\n{len(failed)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} passed.")
