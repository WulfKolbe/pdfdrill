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


# --- 689: the guard used to pass by testing nothing -------------------------

def _eprint_tar(path, *names):
    import io, tarfile
    with tarfile.open(str(path), "w:gz") as tf:
        for n in names:
            data = b"\\documentclass{article}\n"
            info = tarfile.TarInfo(n); info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


def test_tex_names_reads_a_gzipped_single_tex(tmp_path):
    """0902.0431's e-print is gzip(SpEcxp.tex) — no tar, no zip. `tex_names`
    knew only zips and bare `.tex`, so it returned [] and the caller recorded
    `latex_source_checked = "no .tex member to test"`: the guard PASSED having
    tested nothing. The gzip FNAME header is where the real name lives."""
    import gzip, io
    from pdfdrill import author_source as A
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", filename="SpEcxp.tex") as g:
        g.write(b"\\documentclass[a4]{article}\n")
    p = tmp_path / "0902.0431.gz"; p.write_bytes(buf.getvalue())
    assert A.tex_names(p) == ["SpEcxp"]
    assert A.classify(p, {"1deb350a-8d75-4da5-b1ec-153e0bfd7145"}) == (
        "author", "no .tex member is named by a MathPix image_id")


def test_tex_names_reads_a_gzipped_tar(tmp_path):
    from pdfdrill import author_source as A
    p = tmp_path / "2101.00001.tgz"
    _eprint_tar(p, "main.tex", "fig.pdf", "sec/intro.tex")
    assert sorted(A.tex_names(p)) == ["intro", "main"]


def test_mathpix_texzip_is_still_refused_when_renamed_to_an_eprint(tmp_path):
    """The evasion the extension fix makes reachable: MathPix's own `.tex.zip`
    copied to `<stem>.tgz`. It is a ZIP whatever it is called, and the test is
    IDENTITY — the .tex stem is this document's image_id — so the name buys
    nothing."""
    import zipfile
    from pdfdrill import author_source as A
    iid = "1deb350a-8d75-4da5-b1ec-153e0bfd7145"
    p = tmp_path / "0902.0431.tgz"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(f"{iid}.tex", "\\documentclass{article}")
    kind, why = A.classify(p, {iid})
    assert kind == "mathpix", (kind, why)
    try:
        A.assert_author_source(p, known_ids={iid})
    except A.MathPixSourceRefused as e:
        assert iid in str(e)
    else:
        raise AssertionError("a renamed MathPix tex.zip was accepted as gold")
