"""276 — renaming a drilled folder, built on 275's inventory.

The rule that shapes every line of this: a drilled arXiv folder is NAMED for the
arXiv id, and the id is printed down the margin of page 1. So the old name is in
the OCR text, in `pdfinfo.Title`, in the derived BibTeX and in the page prose. A
substitution over the folder would rewrite the document's own words. Everything
here edits a NAMED FIELD or moves a FILE.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from pdfdrill.renamefolder import (RenameRefused, plan, rename_folder,
                                   rename_report_tex, residue, stem_files)


def _folder(tmp_path: Path, stem="0008113v1") -> Path:
    f = tmp_path / stem
    (f / "report-crops").mkdir(parents=True)
    (f / "okf" / stem).mkdir(parents=True)
    (f / f"{stem}.pdf").write_bytes(b"%PDF-1.4\n")
    # The document's own words contain the stem — this is the trap.
    (f / f"{stem}.lines.json").write_text(json.dumps(
        {"pages": [{"lines": [{"text": f"arXiv:quant-ph/{stem} 25 Aug 2000"}]}]}))
    (f / f"{stem}.drill.json").write_text(json.dumps({
        "pdf": f"{stem}.pdf",
        "evidence": {"bibkey": stem,
                     "tiddlers_path": f"{stem}.tiddlers.json",
                     "okf_path": f"okf/{stem}",
                     "pdfinfo": {"Title": f"arXiv:quant-ph/{stem} 25 Aug 2000"},
                     "mathpix_files": [{"path": f"{stem}.lines.json"}]}}))
    (f / f"{stem}.tiddlers.json").write_text(json.dumps([
        {"title": f"{stem}_EQ0001", "tags": f"equation {stem}", "text": "x"},
        {"title": f"{stem}_PAGE_001", "tags": f"page {stem}",
         "text": f"Page 1 of *{stem}*."},
        {"title": f"{stem}_H1", "tags": f"section {stem}",
         "text": f"{{{{{stem}_EQ0001||EQ}}}}"},
    ]))
    (f / "model.docmodel.json").write_text(json.dumps({
        "meta": {"bibkey": stem, "root_id": stem,
                 "source_path": f"/lib/{stem}/{stem}.lines.json"},
        "objects": [
            {"id": stem, "type": "Document", "props": {"bibkey": stem}},
            {"id": "o1", "type": "Paragraph",
             "props": {"bibkey": stem, "parent_section": f"{stem}_H1",
                       "text": f"see arXiv:quant-ph/{stem} for details"}},
        ]}))
    (f / "model.docpack.json").write_text(json.dumps({"meta": {"bibkey": stem}}))
    (f / "report.tex").write_text(
        "\\section*{%s — formula report}\n"
        "\\ident{%s\\_\\allowbreak{}EQ0001}\n"
        "\\includegraphics[width=1cm]{report-crops/%s_EQ0001.jpg}\n" % (stem, stem, stem))
    (f / "report-crops" / f"{stem}_EQ0001.jpg").write_bytes(b"\xff\xd8" + b"x" * 900)
    (f / "okf" / stem / f"{stem}_ABS01.md").write_text(
        f"---\ntype: Abstract\ntags: [abstract, {stem}]\n"
        f"resource: pdfdrill:{stem}/{stem}_ABS01\n---\n\n"
        f"See [equation](../equations/{stem}_EQ0001.md) and arXiv:quant-ph/{stem}.\n")
    return f


def test_plan_refuses_an_existing_target(tmp_path):
    f = _folder(tmp_path)
    (tmp_path / "taken").mkdir()
    with pytest.raises(RenameRefused):
        plan(f, "taken")


@pytest.mark.parametrize("bad", ["", ".", "..", "a/b"])
def test_plan_refuses_an_unusable_name(tmp_path, bad):
    with pytest.raises(RenameRefused):
        plan(_folder(tmp_path), bad)


def test_stem_files_does_not_catch_model_or_report(tmp_path):
    f = _folder(tmp_path)
    names = {p.name for p in stem_files(f, "0008113v1")}
    assert "model.docmodel.json" not in names and "report.tex" not in names
    assert "0008113v1.pdf" in names and "0008113v1.lines.json" in names


def test_the_documents_own_words_are_never_rewritten(tmp_path):
    f = _folder(tmp_path)
    r = rename_folder(f, "blume2000optimal", "blume2000optimal")
    d = r["folder"]
    lines = (d / "blume2000optimal.lines.json").read_text()
    assert "arXiv:quant-ph/0008113v1 25 Aug 2000" in lines
    sc = json.loads((d / "blume2000optimal.drill.json").read_text())
    assert sc["evidence"]["pdfinfo"]["Title"] == "arXiv:quant-ph/0008113v1 25 Aug 2000"
    m = json.loads((d / "model.docmodel.json").read_text())
    para = [o for o in m["objects"] if o["type"] == "Paragraph"][0]
    assert "arXiv:quant-ph/0008113v1" in para["props"]["text"]


def test_paths_and_identifiers_are_retargeted(tmp_path):
    r = rename_folder(_folder(tmp_path), "blume2000optimal", "blume2000optimal")
    d = r["folder"]
    m = json.loads((d / "model.docmodel.json").read_text())
    assert m["meta"]["bibkey"] == "blume2000optimal"
    assert m["meta"]["root_id"] == "blume2000optimal"
    assert m["meta"]["source_path"].endswith(
        "blume2000optimal/blume2000optimal.lines.json")
    doc = [o for o in m["objects"] if o["type"] == "Document"][0]
    assert doc["id"] == "blume2000optimal"          # the object, not just root_id
    assert all(o["props"]["bibkey"] == "blume2000optimal" for o in m["objects"])
    para = [o for o in m["objects"] if o["type"] == "Paragraph"][0]
    assert para["props"]["parent_section"] == "blume2000optimal_H1"
    sc = json.loads((d / "blume2000optimal.drill.json").read_text())
    assert sc["pdf"] == "blume2000optimal.pdf"
    assert sc["evidence"]["bibkey"] == "blume2000optimal"
    assert sc["evidence"]["okf_path"] == "okf/blume2000optimal"
    # nested path lists, missed by a top-level `*_path` KEY rule
    assert sc["evidence"]["mathpix_files"][0]["path"] == "blume2000optimal.lines.json"
    assert (d / sc["evidence"]["mathpix_files"][0]["path"]).exists()


def test_prior_names_are_recorded_on_the_model(tmp_path):
    r = rename_folder(_folder(tmp_path), "blume2000optimal", "blume2000optimal")
    meta = json.loads((r["folder"] / "model.docmodel.json").read_text())["meta"]
    assert meta["folder_history"] == ["0008113v1"]
    assert meta["bibkey_history"] == ["0008113v1"]


def test_tiddler_titles_tags_and_body_references_all_move(tmp_path):
    r = rename_folder(_folder(tmp_path), "blume2000optimal", "blume2000optimal")
    td = json.loads((r["folder"] / "blume2000optimal.tiddlers.json").read_text())
    assert all(t["title"].startswith("blume2000optimal") for t in td)
    assert all("0008113v1" not in t["tags"].split() for t in td)
    h1 = [t for t in td if t["title"].endswith("_H1")][0]
    assert h1["text"] == "{{blume2000optimal_EQ0001||EQ}}"   # the reference follows


def test_crops_and_the_okf_bundle_move_with_their_links(tmp_path):
    r = rename_folder(_folder(tmp_path), "blume2000optimal", "blume2000optimal")
    d = r["folder"]
    assert (d / "report-crops" / "blume2000optimal_EQ0001.jpg").exists()
    assert (d / "okf" / "blume2000optimal" / "blume2000optimal_ABS01.md").exists()
    md = (d / "okf" / "blume2000optimal" / "blume2000optimal_ABS01.md").read_text()
    assert "../equations/blume2000optimal_EQ0001.md" in md
    assert "pdfdrill:blume2000optimal/blume2000optimal_ABS01" in md
    assert "tags: [abstract, blume2000optimal]" in md
    assert "arXiv:quant-ph/0008113v1" in md          # prose untouched


def test_report_tex_handles_the_latex_escaped_underscore(tmp_path):
    f = _folder(tmp_path)
    n = rename_report_tex(f / "report.tex", "0008113v1", "blume2000optimal")
    tex = (f / "report.tex").read_text()
    assert n == 3
    assert "\\ident{blume2000optimal\\_\\allowbreak{}EQ0001}" in tex
    assert "report-crops/blume2000optimal_EQ0001.jpg" in tex
    assert "\\section*{blume2000optimal — formula report}" in tex
    assert "0008113v1" not in tex


def test_the_docpack_is_invalidated_not_edited(tmp_path):
    r = rename_folder(_folder(tmp_path), "blume2000optimal", "blume2000optimal")
    assert not (r["folder"] / "model.docpack.json").exists()
    assert r["docpack_invalidated"] is True


def test_renaming_the_folder_alone_leaves_the_namespace_intact(tmp_path):
    # The stem and the bibkey are separable — 264 showed they already diverge.
    r = rename_folder(_folder(tmp_path), "newfolder")
    d = r["folder"]
    assert d.name == "newfolder"
    assert (d / "newfolder.pdf").exists()
    td = json.loads((d / "newfolder.tiddlers.json").read_text())
    assert all(t["title"].startswith("0008113v1") for t in td)
    m = json.loads((d / "model.docmodel.json").read_text())
    assert m["meta"]["bibkey"] == "0008113v1"
    assert m["meta"]["folder_history"] == ["0008113v1"]


def test_residue_separates_the_documents_words_from_real_leftovers(tmp_path):
    r = rename_folder(_folder(tmp_path), "blume2000optimal", "blume2000optimal")
    res = residue(r["folder"], "0008113v1", "0008113v1")
    assert "blume2000optimal.lines.json" in res["expected"]
    # the Page tiddler's display prose is the known remaining case
    assert res["UNEXPECTED"], "the classifier must not report a clean sweep"
