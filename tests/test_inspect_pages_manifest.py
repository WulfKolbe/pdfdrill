"""819e — `pdfdrill inspect` names the document its page images came from.

The crop servers (`pdf2mmd/inspectserver.py`,
`tools/imageserver/mathpix_server.py`) check `manifest.json` before serving,
because "page images used to share one folder across documents, so a crop could
show a figure from an entirely different book under the right caption".
`pdf2mmd.sh` writes it; `pdfdrill inspect` is the OTHER renderer of the same
folder and did not — so the check could never run, and every session opened with
a warning telling the user to re-run pdf2mmd for pages pdfdrill had rendered.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pdfdrill.commands import _write_pages_manifest                # noqa: E402


def test_the_manifest_names_the_document_and_counts_the_pages(tmp_path):
    for n in (1, 2, 3):
        (tmp_path / f"p{n}.png").write_bytes(b"x")
    _write_pages_manifest(tmp_path, Path("/lib/arxiv.2609.12039.pdf"), 400)
    got = json.loads((tmp_path / "manifest.json").read_text())
    assert got == {"document": "arxiv.2609.12039", "dpi": 400, "pages": 3}


def test_the_page_count_does_not_double_count_the_originals(tmp_path):
    """The folder keeps `page-<NNNN>.png` beside the `p<N>.png` aliases, and
    `p*.png` matches both — 38 for a 19-page paper on the first run."""
    for n in (1, 2):
        (tmp_path / f"p{n}.png").write_bytes(b"x")
        (tmp_path / f"page-{n:04d}.png").write_bytes(b"x")
    _write_pages_manifest(tmp_path, Path("/lib/doc.pdf"), 400)
    assert json.loads((tmp_path / "manifest.json").read_text())["pages"] == 2


def test_the_shape_is_the_one_the_servers_read(tmp_path):
    """`document` is what the server compares against its --pages/--lines
    arguments; the other two are informational. Keys, not extras."""
    (tmp_path / "p1.png").write_bytes(b"x")
    _write_pages_manifest(tmp_path, Path("/lib/doc.pdf"), 250)
    got = json.loads((tmp_path / "manifest.json").read_text())
    assert set(got) == {"document", "dpi", "pages"}


def test_an_unwritable_folder_is_not_fatal(tmp_path):
    """A missing manifest costs a warning; failing the inspect build over one
    would be worse."""
    missing = tmp_path / "does-not-exist"
    _write_pages_manifest(missing, Path("/lib/doc.pdf"), 400)   # must not raise


def test_inspect_writes_it():
    src = (Path(__file__).resolve().parents[1]
           / "src" / "pdfdrill" / "commands.py").read_text()
    body = src.split("def _inspect_pages_dir(", 1)[1].split("\ndef ", 1)[0]
    assert "_write_pages_manifest" in body


# ── 820 — the manifest is also the library-wide crop index ───────────────────

def test_the_manifest_indexes_the_image_ids_and_the_coordinate_space(tmp_path):
    """A library-wide crop server needs (image_id -> page) and the coordinate
    space `scale()` divides by. Measured over 400 corpus documents: 12,742
    distinct image_ids, ZERO collisions — so an id already identifies
    (document, page) and one server can hold the whole library with NO url
    changing. Reading 747 small manifests is instant; reading 1,494 lines.json,
    some of them 10 MB, took minutes."""
    import json as _json
    doc = tmp_path / "arxiv.2609.12039"
    (doc / "inspect" / "pages").mkdir(parents=True)
    (doc / "arxiv.2609.12039.pdf").write_bytes(b"%PDF")
    (doc / "inspect" / "pages" / "p1.png").write_bytes(b"x")
    (doc / "arxiv.2609.12039.lines.json").write_text(_json.dumps({"pages": [
        {"page": 1, "image_id": "bfbc5ae4-01",
         "page_width": 2125, "page_height": 2750, "lines": []},
        {"page": 2, "image_id": "bfbc5ae4-02",
         "page_width": 2125, "page_height": 2750, "lines": []},
    ]}))
    _write_pages_manifest(doc / "inspect" / "pages",
                          doc / "arxiv.2609.12039.pdf", 400)
    got = json.loads((doc / "inspect" / "pages" / "manifest.json").read_text())
    assert got["image_ids"] == {"bfbc5ae4-01": 1, "bfbc5ae4-02": 2}
    assert got["coord"] == [2125, 2750]


def test_no_lines_json_means_no_index_and_no_crash(tmp_path):
    """The keyless case: a document with no lines.json has no MathPix-shaped crop
    URLs to resolve either, so there is nothing to index."""
    doc = tmp_path / "plain"
    (doc / "inspect" / "pages").mkdir(parents=True)
    (doc / "plain.pdf").write_bytes(b"%PDF")
    (doc / "inspect" / "pages" / "p1.png").write_bytes(b"x")
    _write_pages_manifest(doc / "inspect" / "pages", doc / "plain.pdf", 400)
    got = json.loads((doc / "inspect" / "pages" / "manifest.json").read_text())
    assert "image_ids" not in got and "coord" not in got
    assert got["document"] == "plain"


def test_a_corrupt_lines_json_does_not_fail_the_inspect_build(tmp_path):
    doc = tmp_path / "broken"
    (doc / "inspect" / "pages").mkdir(parents=True)
    (doc / "broken.pdf").write_bytes(b"%PDF")
    (doc / "inspect" / "pages" / "p1.png").write_bytes(b"x")
    (doc / "broken.lines.json").write_text('{"pages": [ TRUNCATED')
    _write_pages_manifest(doc / "inspect" / "pages", doc / "broken.pdf", 400)
    assert (doc / "inspect" / "pages" / "manifest.json").is_file()
