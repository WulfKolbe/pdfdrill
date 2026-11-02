"""A pdf2mmd2 reading must be usable through the documented layout.

The owner added a pdf2mmd2 output in drillui — `add <run>/d09/d09.lines.json`,
then `md` — and got:

    d09.lines.json is a SCANNED PDF (no text layer) — `pdfdrill md` extracts
    the text layer and finds nothing. Run `pdfdrill gemmaocr …` (METERED) …

Wrong three times over: it is not a PDF, it is not scanned, and the file is the
READING — the one thing in the tree that already holds the text, 514 pages of
it with `title` and `section_header` types. `cli._pdf` had no case for a
reading FILE (896 taught it about a reading FOLDER), so the reading became the
"document", got a `d09.lines.json.drill/` sidecar of its own, and a text-layer
extraction was attempted on a JSON file. The owner's fix is the right one — let
pdf2mmd2 write the layout pdfdrill already documents — and these tests hold
both ends of it.

THE ACCEPTED LAYOUT (`sidecar.blob_dir_for`: self-contained iff
`parent.name == pdf.stem`; `pagelines.lines_json`: the reading is
`pdf.parent/<stem>.lines.json`):

    <out>/<name>/<name>.pdf          the document
    <out>/<name>/<name>.lines.json   the reading, BESIDE it
    <out>/<name>/<name>.lines/       the per-page files

Measured on the owner's d09 once the document sat beside the reading:
`pdfdrill md` gave 51 `#`, 474 `##`, 90 `###` and 1,879 `$$` fences over 514
pages — fully sectioned, from the reading rather than the text layer.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import cli, pagelines, sidecar

_MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def _accepted_layout(root: Path, name: str = "d09") -> Path:
    """What pdf2mmd2 is to write: one folder named after the document."""
    d = root / name
    d.mkdir(parents=True)
    pdf = d / f"{name}.pdf"
    pdf.write_bytes(_MINIMAL_PDF)
    (d / f"{name}.lines.json").write_text('{"pages": []}')
    (d / f"{name}.lines").mkdir()
    return pdf


def test_the_accepted_layout_is_self_contained(tmp_path):
    """The folder IS the sidecar, so the reading and the artifacts sit together."""
    pdf = _accepted_layout(tmp_path)
    blob, js = sidecar.blob_dir_for(pdf)
    assert blob == pdf.parent, "the doc folder should BE the blob dir"
    assert js == pdf.parent / "d09.drill.json"


def test_the_reading_is_found_beside_the_document(tmp_path):
    pdf = _accepted_layout(tmp_path)
    assert pagelines.lines_json(pdf) == pdf.parent / "d09.lines.json"
    assert pagelines.lines_json(pdf).is_file(), "the reading must be beside the PDF"


def test_the_reading_path_resolves_to_its_document(tmp_path):
    """Handing in the reading itself must find the document, not become one."""
    pdf = _accepted_layout(tmp_path)
    got = cli._pdf([str(pdf.parent / "d09.lines.json")])
    assert Path(got).resolve() == pdf.resolve(), got


def test_a_relative_reading_path_resolves_too(tmp_path, monkeypatch):
    """The drillui case, and the bug the first fix had: `Path('x.lines.json')
    .parent.parent` is `.`, not the directory above, so a relative argument
    collapsed and the document one level up was reported missing. It cost an
    acceptance run to see, because the absolute-path test passed."""
    pdf = _accepted_layout(tmp_path)
    monkeypatch.chdir(pdf.parent)
    got = cli._pdf(["d09.lines.json"])
    assert Path(got).resolve() == pdf.resolve(), got


def test_the_document_one_level_up_is_found(tmp_path):
    """pdf2mmd2's CURRENT layout — reading in `<name>/`, document at `<run>/`.
    Accepted so today's outputs keep working, but it is not the layout to write:
    the reading is then NOT beside the document, so a projector finds no reading
    and silently falls back to the text layer."""
    d = tmp_path / "d09"
    d.mkdir()
    (d / "d09.lines.json").write_text('{"pages": []}')
    pdf = tmp_path / "d09.pdf"
    pdf.write_bytes(_MINIMAL_PDF)
    got = cli._pdf([str(d / "d09.lines.json")])
    assert Path(got).name == "d09.pdf", got


def test_a_reading_with_no_document_says_so_and_does_not_claim_a_scan(tmp_path):
    """The message the owner actually got is the thing under test."""
    d = tmp_path / "d09"
    d.mkdir()
    reading = d / "d09.lines.json"
    reading.write_text('{"pages": []}')
    with pytest.raises(FileNotFoundError) as e:
        cli._pdf([str(reading)])
    msg = str(e.value)
    assert "READING, not a document" in msg, msg
    for lie in ("SCANNED", "scanned", "no text layer"):
        assert lie not in msg, f"still claims {lie!r}: {msg}"


def test_a_plain_pdf_argument_is_untouched(tmp_path):
    """The owner's preference — call pdfdrill with the PDF name — must not
    change behaviour for everything that already passes a PDF."""
    pdf = _accepted_layout(tmp_path)
    assert Path(cli._pdf([str(pdf)])).resolve() == pdf.resolve()
