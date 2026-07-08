"""
OKF projection (docops.projectors.okf) — the docmodel → Open Knowledge Format
bundle. OKF = one Markdown-with-YAML-frontmatter file per knowledge unit; the ONE
conformance rule is a non-empty `type` in every non-reserved file's frontmatter.
Pure over a synthetic tiddler list (the OKF core re-serializes the tiddler bundle
the TiddlyWiki projector already builds).
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
        {"title": "D_REF_smith", "type": "text/markdown", "tags": "reference bibentry",
         "citekey": "smith2020", "text": "J. Smith. A paper. 2020.", "year": "2020"},
        {"title": "D_TB0001", "type": "text/markdown", "tags": "table",
         "text": "| a | b |\n|---|---|\n| 1 | 2 |", "caption": "Results"},
        {"title": "$:/tpl/FO", "type": "text/vnd.tiddlywiki", "tags": "template",
         "text": "<$latex>"},                          # template → skipped
    ]


def _fm(content):
    """Parse the leading YAML frontmatter block of an OKF file."""
    assert content.startswith("---\n")
    block = content.split("---\n", 2)[1]
    return yaml.safe_load(block)


def test_conformance_nonempty_type_in_every_file():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {"title": "Demo"},
                               "2026-07-08T00:00:00Z")
    for path, content in bundle.items():
        meta = _fm(content)
        assert meta.get("type"), f"{path}: missing non-empty type"   # the OKF rule


def test_template_tiddlers_skipped():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")
    assert not any("tpl" in p.lower() or "$:" in p for p in bundle)


def test_type_from_kind_and_resource_and_body():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")
    fo = bundle["D_FO0001.md"]
    m = _fm(fo)
    assert m["type"] == "Formula"
    assert m["resource"] == "pdfdrill:D/D_FO0001"
    assert "D" in (m.get("tags") or [])                # bibkey tag present
    assert "x^2" in fo and "$" in fo                   # renderable math body


def test_transclusion_rewritten_to_okf_link():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")
    para = bundle["D_PARA_0001.md"]
    assert "(./D_FO0001.md)" in para                   # OKF relative link
    assert "{{" not in para and "||" not in para       # no raw transclusion left


def test_table_under_schema_heading():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")
    tb = bundle["D_TB0001.md"]
    assert "# Schema" in tb and "| a | b |" in tb


def test_reference_under_citations():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {}, "T")
    ref = bundle["D_REF_smith.md"]
    assert _fm(ref)["type"] == "Reference"
    assert "# Citations" in ref


def test_index_md_is_document_with_links():
    bundle = X.tiddlers_to_okf(_tiddlers(), "D", {"title": "Demo",
                               "num_pages": 3}, "T")
    assert "index.md" in bundle
    idx = bundle["index.md"]
    assert _fm(idx)["type"] == "Document"
    assert "(./D_FO0001.md)" in idx or "D_FO0001" in idx   # links the units


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try: t(); print(f"PASS {name}")
        except AssertionError as e: failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e: failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed: print(f"\n{len(failed)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} passed.")
