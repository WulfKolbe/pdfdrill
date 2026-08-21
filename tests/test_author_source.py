"""065 — a candidate 'author' source must not be MathPix's own output."""
import json
import zipfile

import pytest

from pdfdrill.author_source import (MathPixSourceRefused, assert_author_source,
                                    classify, image_ids)

IID = "1deb350a-8d75-4da5-b1ec-153e0bfd7145"


def _lines(tmp_path, iid=IID, pages=3):
    p = tmp_path / "d.lines.json"
    p.write_text(json.dumps(
        {"pages": [{"page": i + 1, "image_id": f"{iid}-{i+1:03d}"}
                   for i in range(pages)]}))
    return p


def _zip(tmp_path, name, stem):
    z = tmp_path / name
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr(f"{stem}/{stem}.tex", "\\documentclass{article}")
    return z


def test_image_ids_strips_the_page_suffix(tmp_path):
    assert image_ids(_lines(tmp_path)) == {IID}


def test_mathpix_texzip_is_refused_by_identity(tmp_path):
    z = _zip(tmp_path, "d.tex.zip", IID)
    with pytest.raises(MathPixSourceRefused) as ei:
        assert_author_source(z, _lines(tmp_path))
    assert IID in str(ei.value)
    assert ei.value.path == z and ei.value.remedy


def test_author_eprint_is_accepted(tmp_path):
    z = _zip(tmp_path, "author.zip", "SpEcxp")
    assert_author_source(z, _lines(tmp_path))          # must not raise
    assert classify(z, {IID})[0] == "author"


def test_a_uuid_from_another_document_is_suspect_not_refused(tmp_path):
    """Shape alone is not proof. Refusing on it would reject an author who
    happens to name a file that way, so this reports rather than raises."""
    other = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    z = _zip(tmp_path, "d.tex.zip", other)
    kind, why = classify(z, {IID})
    assert kind == "suspect" and other in why
    assert_author_source(z, _lines(tmp_path))          # reported, not refused


def test_no_lines_json_cannot_manufacture_a_refusal(tmp_path):
    """With no image_ids to compare against, identity is untestable — the
    check must not invent a verdict from nothing."""
    z = _zip(tmp_path, "d.tex.zip", IID)
    assert classify(z, set())[0] == "suspect"
    assert_author_source(z, tmp_path / "missing.lines.json")


def test_plain_tex_named_by_an_image_id_is_also_refused(tmp_path):
    """The zip is the common carrier, not the defining property."""
    t = tmp_path / f"{IID}.tex"
    t.write_text("x")
    with pytest.raises(MathPixSourceRefused):
        assert_author_source(t, _lines(tmp_path))
